#!/usr/bin/env bash
# round.sh — 运营轮次 runner(T2 骨架;health/discover 的具体动作面归 T3/T4 填充)
# 链:组上下文(模板+判例注入+输入)→ pi --print → 落裁决包草稿 → 台账 → 判例引用校验 → 沙箱断言。
# 任一步失败即轮次失败非零退出(九裁决 6:短命 pi 进程,每轮记账)。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib.sh
. ops/agent/lib.sh

usage() {
  echo '用法: ops/agent/round.sh health|discover "<本轮输入摘要>" [追加判例检索词...]' >&2
  exit 2
}
(( $# >= 2 )) || usage
round="$1"; input="$2"; shift 2

# 模型映射(九裁决 9):健康轮 flash,discover 轮 pi 默认主力;检索词默认按轮次主题,T3/T4 再精化
case "$round" in
  health)
    prompt_file=ops/agent/prompts/health.md
    model_args=(--model glm-5.3-flash)
    model_label="glm-5.3-flash"
    kws=(冻结 死键 不可达 违例)
    ;;
  discover)
    prompt_file=ops/agent/prompts/discover.md
    model_args=()
    model_label="default(主力)"
    kws=(排他率 聚合器 许可 体量 冻结)
    ;;
  *) usage ;;
esac
kws+=("$@")

[[ -f "$prompt_file" ]] || { echo "round: 缺提示词模板 $prompt_file" >&2; exit 1; }

# 1) 组上下文:模板 + 判例注入块(rg 词法,无嵌入)+ 本轮输入
inject_block="$(inject_precedents "${kws[@]}")"
prompt="$(<"$prompt_file")"
prompt="${prompt//'{{PRECEDENTS}}'/$inject_block}"
prompt="${prompt//'{{INPUT}}'/$input}"

# 2) pi 短命调用;非零退出或空输出 = 轮次失败
pi_err="$(mktemp)"
if ! pi_out="$(pi --print ${model_args[@]+"${model_args[@]}"} -- "$prompt" 2>"$pi_err")"; then
  echo "round: pi 调用失败(非零退出)" >&2; cat "$pi_err" >&2; rm -f "$pi_err"; exit 1
fi
rm -f "$pi_err"
[[ -n "$pi_out" ]] || { echo "round: pi 空输出,轮次失败" >&2; exit 1; }

# 3) 裁决包草稿落 docs 仓(经符号链接;文件名带 HHMM——同日同轮重跑不覆盖,证据不灭失裁决 2026-10-19 评审 Minor-2)
pkg_dir="$DOCS_ROOT/ops/packages"; mkdir -p "$pkg_dir"
pkg="$pkg_dir/$(date +%F)-$round-$(date +%H%M).md"
printf '%s\n' "$pi_out" > "$pkg"

# 4) 台账 → 5) 判例引用校验 → 6) 沙箱断言(每轮末步强制,Review Focus 1)
ledger_append "$round" "$model_label" "pi_rc=0 out_len=${#pi_out}"
verify_cited_precedents "$pkg"
sandbox_assert
echo "round: $round 完成 → $pkg"
