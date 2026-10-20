#!/usr/bin/env bash
# lib.sh — 判例检索注入 / 判例引用校验 / 台账 / 沙箱断言(T2;feed_freshness 等健康轮扩展归 T3;
# run_pi pi 调用面归 T3.5)
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
inject_precedents() {
  local kws=("$@")
  echo "### 注入判例(检索词: ${kws[*]})"
  local hits="" rg_out rg_rc=0
  if (( ${#kws[@]} )); then
    rg_out="$(rg -i -l -g '*.md' -g '!_schema.md' \
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

# ── T3.5: pi 统一调用面 ──────────────────────
# run_pi — stdin=用户消息,argv=追加 pi 旗标(模型/工具面/--append-system-prompt 文件等)。
# 修正批四问题(2026-10-19 用户质疑查证):
# ① --no-session——print 默认持久会话,定时轮会无限灌 session store(经验在判例库不在会话);
# ② --mode json——print 模式无用量输出,九裁决 9 记账空转;解析事件流取真数:
#    最终文本/stopReason=末个 role=assistant 的 message_end;用量=全部 assistant
#    message_end 的 usage 求和(实测 2026-10-19 多回合探针:每回合重置非累计,
#    只取末事件会在工具多回合轮少数;中间回合 stopReason=toolUse 不入失败面);
#    usage/stopReason 均在 message 内层非事件顶层(同日探针);
# ③ --no-extensions——claude-mem 扩展会注入开发会话观察(customType=
#    claude-mem-context,实测 ~5k tokens);同时关 MCP/codemode——discover 动作面=
#    gh/curl/ipdb CLI,不依赖 MCP;
# ④ 工具面由调用方按轮次收紧(round.sh)。
# stdin prompt 经 '-- -' 传入、--append-system-prompt 传文件路径读文件内容,均 2026-10-19
# 实测支持(探针 /tmp 留档)。失败面(JSON 模式下 pi 不必然非零退出,必须自判):末个
# assistant message_end 的 stopReason=error/aborted、agent_settled.aborted=true、最终文本为空。
# 出参:PI_TEXT(最终文本)/PI_USAGE(紧凑串 in=.. out=.. total=.. cost=..);失败非零+原因到 stderr。
# PI_BIN 可覆盖(selftest fixture 用,不真调 pi);RUN_PI_RAW_OUT=<file> 可选——原始
# 事件流留档供审计(冒烟验 claude-mem 零注入等),不留档不落盘。
run_pi() {
  local raw errf textf rc verdict
  raw="$(mktemp)"; errf="$(mktemp)"; textf="$(mktemp)"
  if "${PI_BIN:-pi}" --mode json --no-session --no-extensions "$@" -- - \
      > "$raw" 2> "$errf"; then rc=0; else rc=$?; fi
  if (( rc != 0 )); then
    echo "run_pi: pi 进程失败(rc=$rc)" >&2; cat "$errf" >&2
    rm -f "$raw" "$errf" "$textf"; return "$rc"
  fi
  [[ -n "${RUN_PI_RAW_OUT:-}" ]] && cp "$raw" "$RUN_PI_RAW_OUT"
  verdict="$(python3 - "$raw" "$textf" <<'PY'
import json, sys
# 输出单行「ok<TAB>用量串」或「fail<TAB>原因」;最终文本写 argv[2]。
# 永不非零退出(解析器自身故障也降级为 fail 判定,不伪装成功)。
raw_path, text_path = sys.argv[1], sys.argv[2]
try:
    last, aborted = None, False
    u_in = u_out = u_tot = 0
    u_cost = 0.0
    n_usage = 0
    with open(raw_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            if ev.get('type') == 'message_end':
                msg = ev.get('message')
                if isinstance(msg, dict) and msg.get('role') == 'assistant':
                    last = ev
                    u = msg.get('usage') or {}
                    u_in += u.get('input') or 0
                    u_out += u.get('output') or 0
                    u_tot += u.get('totalTokens') or 0
                    u_cost += (u.get('cost') or {}).get('total') or 0.0
                    n_usage += 1
            elif ev.get('type') == 'agent_settled' and ev.get('aborted'):
                aborted = True
    if aborted:
        print('fail\tagent_settled.aborted=true(轮次中止)')
    elif last is None:
        print('fail\t事件流无 assistant message_end(pi 未产出?)')
    else:
        # 实测(2026-10-19 探针):usage/stopReason 在 message 内层,非事件顶层
        msg = last.get('message') or {}
        if msg.get('stopReason') in ('error', 'aborted'):
            print('fail\tstopReason=%s' % msg.get('stopReason'))
        else:
            content = msg.get('content')
            if isinstance(content, list):
                text = ''.join(p.get('text') or '' for p in content
                               if isinstance(p, dict) and p.get('type') == 'text')
            else:
                text = content if isinstance(content, str) else ''
            if not text.strip():
                print('fail\t最终文本为空')
            else:
                u_cost = round(u_cost, 8)
                print('ok\tin=%s out=%s total=%s cost=%s' % (u_in, u_out, u_tot, u_cost))
                with open(text_path, 'w', encoding='utf-8') as tf:
                    tf.write(text)
except Exception as e:
    print('fail\t事件流解析异常: %s' % e)
PY
)" || verdict="fail\t解析器调用异常"
  rm -f "$raw" "$errf"
  if [[ "${verdict%%$'\t'*}" != ok ]]; then
    echo "run_pi: ${verdict#*$'\t'}" >&2
    rm -f "$textf"; return 1
  fi
  PI_USAGE="${verdict#*$'\t'}"
  PI_TEXT="$(<"$textf")"
  rm -f "$textf"
}

# ── T3: 健康轮确定性检查(feed 冻结检测)──────────────────────
FEED_TIMEOUT_S=15   # 任务书:HEAD 超时 15s,失败不重试
FROZEN_DAYS=180     # 死键嫌疑门线(threatview sunset 判例:Last-Modified 冻结即判死)

# _ff_code <响应头块> — 最终 HTTP 状态码(-L 跟随后取最后一个;无状态行 = 0)。
_ff_code() {
  printf '%s' "$1" | tr -d '\r' | awk '$1 ~ /^HTTP\// { c = $2 } END { print c + 0 }'
}

# _ff_probe <url> — 单 URL 探测 → TSV 一行 url<TAB>last_modified<TAB>age_days。
# HEAD(跟随重定向)→ HTTP≥400/网络失败降级 GET Range 0-0 → 仍失败=UNREACHABLE
# (任务书契约);age_days 以 Last-Modified 头 floor((now-lm)/86400),缺头/不可
# 解析=NO-LM。恒 rc=0:不可达是读数不是故障;需 token 的 API(401/403)也会落
# UNREACHABLE —— 已知限,摘要员措辞「不可达≠死键」(prompts/health.md)。
_ff_probe() {
  local url="$1" hdr="" rc=0 code lm epoch age
  hdr="$(curl -sS -L -A ip-lookup-tool/1.0 --max-time "$FEED_TIMEOUT_S" \
        -I -o /dev/null -D - "$url" 2>/dev/null)" || rc=1
  code="$(_ff_code "$hdr")"
  if (( rc )) || (( code >= 400 )); then    # HEAD 被拒/不支持 → GET Range 0-0
    rc=0
    hdr="$(curl -sS -L -A ip-lookup-tool/1.0 --max-time "$FEED_TIMEOUT_S" \
          -H 'Range: bytes=0-0' -o /dev/null -D - "$url" 2>/dev/null)" || rc=1
    code="$(_ff_code "$hdr")"
  fi
  if (( rc )) || (( code >= 400 )); then
    printf '%s\tUNREACHABLE\tUNREACHABLE\n' "$url"; return 0
  fi
  lm="$(printf '%s' "$hdr" | tr -d '\r' | awk 'tolower($1) ~ /^last-modified:$/ { lm = $0 }
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
  export -f _ff_probe _ff_code
  printf '%s\n' "$@" | xargs -P 8 -I{} bash -c '_ff_probe "$1"' _ {} | sort -t$'\t' -k1,1
}

# freshness_flags — stdin 吃 feed_freshness TSV → 异常行(冻结≥门线=死键嫌疑 /
# 不可达);NO-LM 不标(可达但缺头≠异常,原始读数留给摘要员;任务书异常清单三态)。
freshness_flags() {
  awk -F'\t' -v frozen="$FROZEN_DAYS" '
    $3 == "UNREACHABLE" { printf "%s\n", "- 不可达·建议复核: " $1 }
    $3 ~ /^[0-9]+$/ && ($3 + 0) >= frozen {
      printf "%s\n", "- 死键嫌疑·建议复核: " $1 "(冻结 " $3 " 天 ≥ " frozen " 门线;Last-Modified: " $2 ")"
    }
  '
}

# extract_feed_urls — 只读扫描 backend/ipdb/_sources/*.py 的 https?:// 字面量
# (rg;任务书自选最简可靠)。排除含 {} 的 token 模板(ipinfo_lite/ip2location
# 的 {token} 占位符:无凭据不可测,其新鲜度由 scheduler mtime 侧覆盖;且避免
# 占位符落包)。结尾 .,; 剥掉(注释里句读会并入 URL);[ ] 排除(源码正则
# 字面量如 ...download/[^s] 的残片不混入;IPv6 字面量场景本仓无)。
extract_feed_urls() {
  rg -oN --no-filename 'https?://[^"'\''[:space:]()><,\[\]]+' \
    -g '*.py' "$ROOT/backend/ipdb/_sources" \
    | grep -v '[{}\\]' \
    | sed -E 's/[.,;]+$//' \
    | sort -u
}
