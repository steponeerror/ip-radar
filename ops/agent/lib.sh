#!/usr/bin/env bash
# lib.sh — 判例检索注入 / 判例引用校验 / 台账 / 沙箱断言(T2;feed_freshness 等健康轮扩展归 T3)
# (T3.5 pi 统一调用面已随死引擎退役删除,2026-10-20 T3;史档在 git 历史)
# 检索只许 rg 词法,禁止 embedding(九裁决 7);判例库 docs/ops/precedents/ 无界不删。
# fixture 隔离:PRECEDENTS_DIR / LEDGER_FILE 可环境覆盖(selftest 用);沙箱根不可覆盖——
# 由本文件落位推导,保证断言对象恒为 worktree 根(任务书:不是主 checkout)。

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$AGENT_DIR/../.." && pwd)"   # worktree 根(无条件赋值:沙箱红线不变式,评审 Minor-1;环境预置不得改写)
DOCS_ROOT="${DOCS_ROOT:-$ROOT/docs}"              # 符号链接 → docs 仓
PRECEDENTS_DIR="${PRECEDENTS_DIR:-$DOCS_ROOT/ops/precedents}"
LEDGER_FILE="${LEDGER_FILE:-$DOCS_ROOT/ops/ledger.md}"

# fm_block <file> <field> — 提取 frontmatter 顶层字段值(含续行/嵌套块),拍平成一行。
# 只做摘要用,非 YAML 解析:YAML 块标示符(> / |)丢弃,续行以空格连接。
fm_block() {
  awk -v f="$2" '
    NR == 1 { if ($0 == "---") { infm = 1; next } else exit }
    infm && /^---/ { exit }
    infm {
      if (match($0, /^[A-Za-z_][A-Za-z0-9_]*:/)) {
        key = substr($0, 1, RLENGTH - 1)
        if (key == f) {
          active = 1
          rest = substr($0, RLENGTH + 1)
          sub(/^[ \t]+/, "", rest); sub(/[ \t]+$/, "", rest)
          if (rest != "" && rest !~ /^[|>]/) out = out (out == "" ? "" : " ") rest
        } else if (active) exit   # 下一个顶层字段 = 本字段块结束
        next
      }
      if (active && $0 ~ /^[ \t]/) {   # 嵌套子键/续行(reward 映射、多行 context)
        line = $0; sub(/^[ \t]+/, "", line); sub(/[ \t]+$/, "", line)
        if (line != "") out = out " " line
      } else if (active) exit
    }
    END { print out }
  ' "$1"
}

# inject_precedents <关键词>... — rg 词法检索判例库(排除 _schema.md,frontmatter/正文皆可命中,
# 多关键词 OR 语义扩大召回),输出 prompt 注入块;零命中显式一行「无判例」(Review Focus 2)。
#
# [退役注记 2026-10-24,PR #177 工具通道修复;判例 docs/ops/precedents/
# 2026-10-24-discover-dual-channel-dead] 判例检索单源已移 tools.mjs searchPrecedentsCore
# (JS 原生 rg spawn,失败面四码分类信封可诊断;本函数吞 stderr 2>/dev/null 的问题只在
# 新单源修复,本函数体零改动)。agent.mjs 宿主预注入与 search_precedents 工具已改调同源。
# 保留唯一理由 = pipeline/steps.mjs synthInput 仍调用(pipeline 面本批冻结不触);
# 两路输出 golden 字节等价由 selftest-t4 三方对拍钉死(JS 核心 = 本函数现行输出 = 入库
# 快照);pipeline 迁移 JS 单源后随 pipeline 批删除。新调用方一律用 JS 核心,勿再引本函数。
inject_precedents() {
  local kws=("$@")
  echo "### 注入判例(检索词: ${kws[*]})"
  local hits="" rg_out rg_rc=0
  if (( ${#kws[@]} )); then
    rg_out="$(rg -i -l -g '*.md' -g '!_*' \
      $(printf -- '-e %q ' "${kws[@]}") "$PRECEDENTS_DIR" 2>/dev/null)" || rg_rc=$?
  fi
  if (( rg_rc > 1 )); then
    # 评审 Minor-3:rc≥2 = 目录缺失/非法检索词等基础设施故障,必须报错,
    # 不许伪装成「无判例」(无证据≠清白);rc=1 才是真零命中。
    echo "inject_precedents: rg 检索失败(rc=$rg_rc)——基础设施故障,非「无判例」" >&2
    return 1
  fi
  hits="$(sort -u <<<"$rg_out")"
  if [[ -z "$hits" ]]; then
    echo "无判例(检索词: ${kws[*]})"
    return 0
  fi
  local f
  while IFS= read -r f; do
    echo "- $(basename "$f")"
    echo "  - context: $(fm_block "$f" context)"
    echo "  - human_ruling: $(fm_block "$f" human_ruling)"
    echo "  - reward: $(fm_block "$f" reward)"
  done <<< "$hits"
}

# verify_cited_precedents <包路径> — 解析包内「注入判例」节列出的判例文件路径,逐一校验存在;
# 编造路径 → 非零退出并打印;节缺失/既无路径又无「无判例」→ 非零(Review Focus 2:防 agent 编造判例)。
# 路径接受三种形式:相对当前目录 / docs 仓相对(docs/ops/precedents/x.md)/ 判例文件名(x.md)。
# T4 实测补丁(2026-10-19):排除类补冒号与全角顿号——模型引文「…判例:2026-…md、2026-…md」
# 旧类把 ':2026-…md' 混进 token,真实文件被误报编造(邻洞律:同族问题一次清面)。
verify_cited_precedents() {
  local pkg="$1"
  [[ -f "$pkg" ]] || { echo "verify_cited_precedents: 包不存在: $pkg" >&2; return 1; }
  local sec
  sec="$(awk '/^#+ .*注入判例/ { insec = 1; next } insec && /^#+ / { exit } insec { print }' "$pkg")"
  [[ -n "$sec" ]] || { echo "verify_cited_precedents: 包缺少「注入判例」节: $pkg" >&2; return 1; }
  local paths rc=0
  paths="$(printf '%s\n' "$sec" | awk '{
    line = $0; gsub(/`/, "", line)
    if (match(line, /[^ \t()\[\]'"'"',;。:、]+\.md/)) {
      tok = substr(line, RSTART, RLENGTH); gsub(/[),.;:、]$/, "", tok); print tok
    }
  }')"
  if [[ -z "$paths" ]]; then
    grep -q '无判例' <<< "$sec" && return 0
    echo "verify_cited_precedents: 注入判例节既无路径也无「无判例」: $pkg" >&2
    return 1
  fi
  local p n=0 bad_n=0
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    n=$((n + 1))
    if [[ -f "$p" || -f "$PRECEDENTS_DIR/$p" || -f "$ROOT/$p" || -f "$DOCS_ROOT/$p" ]]; then
      continue
    fi
    echo "verify_cited_precedents: 编造/缺失判例路径: $p" >&2
    bad_n=$((bad_n + 1))
  done <<< "$paths"
  (( bad_n == 0 )) || return 1
  echo "verify_cited_precedents: ${n} 条判例路径全部存在"
}

# ledger_append <轮次> <model> <用量行> — 追加台账一行;文件不存在则建表头(幂等:已存在不重建)。
# 用量记 pi 实报,不自行估算(九裁决 9)。
ledger_append() {
  local round="$1" model="$2" usage="$3" note="${4:-}"
  if [[ ! -f "$LEDGER_FILE" ]]; then
    mkdir -p "$(dirname "$LEDGER_FILE")"
    { echo "# 运营轮次台账"; echo; echo "| 日期 | 轮次 | model | 用量 | 备注 |"; echo "|---|---|---|---|---|"; } > "$LEDGER_FILE"
  fi
  echo "| $(date +%F) | $round | $model | $usage | $note |" >> "$LEDGER_FILE"
}

# sandbox_assert — 沙箱红线(Review Focus 1):worktree 根 git status 的 backend/ frontend/ 必须零改动;
# 污染即非零退出并打印清单。根 = 本文件落位推导(worktree 根),刻意不做环境覆盖。
sandbox_assert() {
  local out rc
  if ! out="$(git -C "$ROOT" status --porcelain -- backend/ frontend/ 2>/dev/null)"; then
    echo "sandbox_assert: git status 执行失败(worktree 根: $ROOT)" >&2
    return 1
  fi
  if [[ -n "$out" ]]; then
    echo "sandbox_assert: 主仓 backend/frontend 被改动(沙箱红线,轮次判失败):" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  return 0
}

# ── T3: 健康轮确定性检查(feed 冻结检测)──────────────────────
FEED_TIMEOUT_S=15   # 任务书:HEAD 超时 15s,失败不重试
FROZEN_DAYS=180     # 死键嫌疑门线(threatview sunset 判例:Last-Modified 冻结即判死)

# _ff_code <响应头块> — 最终 HTTP 状态码(-L 跟随后取最后一个;无状态行 = 0)。
_ff_code() {
  printf '%s' "$1" | tr -d '\r' | awk '$1 ~ /^HTTP\// { c = $2 } END { print c + 0 }'
}

# _ff_probe_once <url> — 单轮探测(HEAD 跟随重定向 → HTTP≥400/网络失败降级
# GET Range 0-0);结果经 _PR_RC(curl 原始 rc,28=超时,#166 审 P2-1)/_PR_CODE
# (最终状态码)/_PR_HDR(响应头块)传出。仅 _ff_probe 内部用(feed_freshness 的
# xargs 子壳内联)。
_ff_probe_once() {
  local url="$1"
  _PR_RC=0
  _PR_HDR="$(curl -sS -L -A ip-lookup-tool/1.0 --max-time "$FEED_TIMEOUT_S" \
        -I -o /dev/null -D - "$url" 2>/dev/null)" || _PR_RC=$?
  _PR_CODE="$(_ff_code "$_PR_HDR")"
  if (( _PR_RC )) || (( _PR_CODE >= 400 )); then    # HEAD 被拒/不支持 → GET Range 0-0
    _PR_RC=0
    _PR_HDR="$(curl -sS -L -A ip-lookup-tool/1.0 --max-time "$FEED_TIMEOUT_S" \
          -H 'Range: bytes=0-0' -o /dev/null -D - "$url" 2>/dev/null)" || _PR_RC=$?
    _PR_CODE="$(_ff_code "$_PR_HDR")"
  fi
}

# _ff_probe <url> — 单 URL 探测 → TSV 一行 url<TAB>last_modified<TAB>age_days
# [<TAB>error_family](仅 UNREACHABLE 行携带,P2 #164:VERIFY 抑制规则谓词闭集
# 消费面——http_429 限流形/http_404 重定向形是 10-23 两假异常的实测族):
#   - 401/403 → TOKEN_REQUIRED(P1 T2 降噪刀一,spec #152 §2a:匿名撞鉴权
#     墙 = 需令牌·正常——可达且响应正常,只是无凭据;不算 UNREACHABLE 不
#     算异常,与 NO-LM 同等待遇:读数保留,摘要如实提及计数);
#   - 其余失败 → UNREACHABLE + error_family(任务书契约):终末 HTTP 状态码
#     ≥400 → http_<code>(精确码:404/429/500 各自成族,与抑制规则
#     error_family 谓词值同拼写);无 HTTP 码(传输层败)→ curl rc 28
#     (--max-time 到点)= net_timeout,其余传输层败 = net_fail(#166 审
#     P2-1 收口:超时单列对齐 _ops_detectors._error_family 的 timeout 族,
#     同因超时两侧同签,「在飞不双开」对超时类生效;对拍=ops-items.mjs
#     foldErrorFamily net_timeout→timeout);
#   - 成功 → age_days 以 Last-Modified 头 floor((now-lm)/86400),缺头/不可
#     解析=NO-LM。
# 恒 rc=0:不可达是读数不是故障。
# raw.githubusercontent.com 前缀的瞬时失败(网络层/5xx/429)重试一轮再判
# (P1 T2 降噪刀三,spec #152 §2c:该域限流抖动是 2026-10-23 实证噪音源,
# HEAD 与 GET Range 各一次后仅对 raw.github 再来一轮,2s 间隔;确定性失败
# 404/401/403 不重试)。重试后仍 429 → UNREACHABLE+http_429(抑制规则库 R7
# annotate 形的消费面,首批规则 #164)。
_ff_probe() {
  local url="$1" lm epoch age fam
  _ff_probe_once "$url"
  if [[ "$url" == https://raw.githubusercontent.com/* ]] \
     && { (( _PR_RC )) || (( _PR_CODE >= 500 || _PR_CODE == 429 )); }; then
    sleep 2
    _ff_probe_once "$url"
  fi
  if (( _PR_RC == 0 )) && (( _PR_CODE == 401 || _PR_CODE == 403 )); then
    printf '%s\tTOKEN_REQUIRED\tTOKEN_REQUIRED\n' "$url"; return 0
  fi
  if (( _PR_RC )) || (( _PR_CODE >= 400 )); then
    if (( _PR_CODE >= 400 )); then fam="http_${_PR_CODE}"
    elif (( _PR_RC == 28 )); then fam="net_timeout"
    else fam="net_fail"; fi
    printf '%s\tUNREACHABLE\tUNREACHABLE\t%s\n' "$url" "$fam"; return 0
  fi
  lm="$(printf '%s' "$_PR_HDR" | tr -d '\r' | awk 'tolower($1) ~ /^last-modified:$/ { lm = $0 }
      END { if (lm != "") { sub(/^[^:]*:[ \t]*/, "", lm); print lm } }')"
  epoch="$(date -d "$lm" +%s 2>/dev/null)" || true
  if [[ -z "$lm" || -z "${epoch:-}" ]]; then
    printf '%s\tNO-LM\tNO-LM\n' "$url"; return 0
  fi
  age=$(( ( $(date +%s) - epoch ) / 86400 ))
  (( age < 0 )) && age=0    # 时钟偏移(LM 在未来)钳 0,不出负读数
  printf '%s\t%s\t%s\n' "$url" "$lm" "$age"
}

# feed_freshness <urls...> — 并发(xargs -P 8,任务书)探测 → 按 URL 序排序的 TSV。
feed_freshness() {
  (( $# )) || return 0
  export FEED_TIMEOUT_S
  export -f _ff_probe _ff_code _ff_probe_once
  printf '%s\n' "$@" | xargs -P 8 -I{} bash -c '_ff_probe "$1"' _ {} | sort -t$'\t' -k1,1
}

# freshness_flags — stdin 吃 feed_freshness TSV → 异常行(冻结≥门线=死键嫌疑 /
# 不可达);NO-LM 与 TOKEN_REQUIRED 不标(可达但缺头/需令牌·正常 ≠ 异常,
# 原始读数留给摘要员如实提及;任务书异常清单三态 + P1 T2 第四类读数)。
freshness_flags() {
  awk -F'\t' -v frozen="$FROZEN_DAYS" '
    $3 == "UNREACHABLE" { printf "%s\n", "- 不可达·建议复核: " $1 }
    $3 ~ /^[0-9]+$/ && ($3 + 0) >= frozen {
      printf "%s\n", "- 死键嫌疑·建议复核: " $1 "(冻结 " $3 " 天 ≥ " frozen " 门线;Last-Modified: " $2 ")"
    }
  '
}

# extract_feed_urls — 读人工维护清单 ops/agent/feeds.txt(健康轮探测 URL
# 事实层)。2026-10-23 事故重构:旧 rg 扫 backend/ipdb/_sources/*.py 字面量
# 混入首页 URL(dataplane 静态页 Last-Modified → 伪报冻结 291 天)、多行
# 拼接截断 URL(GeoLite 撞 GitHub 重定向 404 → 伪报不可达)、注释/
# docstring 文档 URL,且漏探 base+文件名拼出的真端点(blocklist_de/cn_isp/
# firehol/malicious_ip/rir_delegated 等)——扫描路径退役,事实由清单承载
# (每行 URL + 行内 # 标源;^# 分组头;不收录形状与维护契约见清单头注释;
# 新增/改源端点 = 同 PR 更新清单)。
# 可选 $1 = 清单路径(缺省 $AGENT_DIR/feeds.txt;selftest fixture 隔离,
# PRECEDENTS_DIR 判例同型)。
# -t = 标源对模式(P2,#164):每行出 `URL<TAB>标源名`——标源名=行内 #
# 注释首词(^[a-z0-9_]{1,32}$ 截到首个异形字符;_ops_items.dedup_key.source
# 同形,VERIFY 在飞不重问按它对齐);无注解/异形 → "-"(消费方回落 host)。
# 缺省(无 -t)零行为变化:只出 URL 列(legacy/位等价腿消费面,#163)。
extract_feed_urls() {
  local tsv=0 manifest="${AGENT_DIR}/feeds.txt"
  if [[ "${1:-}" == "-t" ]]; then tsv=1; shift; fi
  [[ "${1:-}" != "" ]] && manifest="$1"
  if (( tsv )); then
    grep -v '^#' "$manifest" | awk -F' *# *' 'NF && $1 != "" {
      gsub(/^[ \t]+|[ \t]+$/, "", $1)
      src = ($2 == "") ? "-" : $2
      sub(/[^a-z0-9_].*$/, "", src)
      if (src !~ /^[a-z0-9_]{1,32}$/) src = "-"
      print $1 "\t" src
    }' | sort -u
  else
    grep -v '^#' "$manifest" | awk 'NF { print $1 }' | sort -u
  fi
}
