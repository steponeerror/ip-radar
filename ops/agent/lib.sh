#!/usr/bin/env bash
# lib.sh — 判例检索注入 / 判例引用校验 / 台账 / 沙箱断言(T2;feed_freshness 等健康轮扩展归 T3)
# 检索只许 rg 词法,禁止 embedding(九裁决 7);判例库 docs/ops/precedents/ 无界不删。
# fixture 隔离:PRECEDENTS_DIR / LEDGER_FILE 可环境覆盖(selftest 用);沙箱根不可覆盖——
# 由本文件落位推导,保证断言对象恒为 worktree 根(任务书:不是主 checkout)。

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$(cd "$AGENT_DIR/../.." && pwd)}"   # worktree 根(ops/agent/ 上两级)
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
  local hits=""
  if (( ${#kws[@]} )); then
    hits="$(rg -i -l -g '*.md' -g '!_schema.md' \
      $(printf -- '-e %q ' "${kws[@]}") "$PRECEDENTS_DIR" 2>/dev/null | sort -u || true)"
  fi
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
verify_cited_precedents() {
  local pkg="$1"
  [[ -f "$pkg" ]] || { echo "verify_cited_precedents: 包不存在: $pkg" >&2; return 1; }
  local sec
  sec="$(awk '/^#+ .*注入判例/ { insec = 1; next } insec && /^#+ / { exit } insec { print }' "$pkg")"
  [[ -n "$sec" ]] || { echo "verify_cited_precedents: 包缺少「注入判例」节: $pkg" >&2; return 1; }
  local paths rc=0
  paths="$(printf '%s\n' "$sec" | awk '{
    line = $0; gsub(/`/, "", line)
    if (match(line, /[^ \t()\[\]'"'"',;。]+\.md/)) {
      tok = substr(line, RSTART, RLENGTH); gsub(/[),.;]$/, "", tok); print tok
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
