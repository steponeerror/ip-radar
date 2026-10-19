#!/usr/bin/env bash
# round.sh — 运营轮次 runner(T2 骨架 + T3 健康轮动作面;discover 归 T4;
# T3.5 pi 调用面修正:run_pi 统一 json/no-session/no-extensions,工具面按轮次收紧)
# 链:组用户消息(判例注入块+轮次输入,health 输入含确定性检查实测读数;系统提示
# 经 --append-system-prompt 文件传入)→ run_pi → 落裁决包草稿 → 台账(真用量)→
# 判例引用校验 → 沙箱断言。任一步失败即轮次失败非零退出(九裁决 6:短命 pi 进程,每轮记账)。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib.sh
. ops/agent/lib.sh

# T3:矩阵扫描用主 checkout venv + 数据面/资产(worktree 无 backend/data;
# IP_RADAR_DATA_DIR 判例 2026-10-18;--assets-dir 显式指主仓免符号链接,
# 不写 worktree backend/ 一字节)。只读测量,不落盘。
MS_EVAL_PY=/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python
MS_MAIN_DATA=/home/huxiao/dev/pi-ip-lookup-tool/backend/data

usage() {
  echo '用法: ops/agent/round.sh health|discover "<本轮输入摘要>" [追加判例检索词...]' >&2
  exit 2
}
(( $# >= 2 )) || usage
round="$1"; input="$2"; shift 2

# 模型映射(九裁决 9):健康轮 flash,discover 轮 pi 默认主力;检索词默认按轮次主题,T3/T4 再精化
case "$round" in
  health)
    sys_prompt=ops/agent/prompts/health-system.md
    # 工具面收紧(T3.5 问题④):健康轮纯摘要器,一切输入已在用户消息,
    # --no-tools --no-skills 全关(含扩展工具);flash 轻模型(九裁决 9)。
    pi_flags=(--model glm-5.3-flash --no-tools --no-skills)
    model_label="glm-5.3-flash"
    kws=(冻结 死键 不可达 违例)
    # ── T3 确定性检查:不经 LLM 先算,结果作为 INPUT 一部分喂 flash ──
    mapfile -t ff_urls < <(extract_feed_urls)
    (( ${#ff_urls[@]} > 0 )) || { echo "round: 源 URL 清单为空(extract_feed_urls 失败?)" >&2; exit 1; }
    ff_tsv="$(feed_freshness "${ff_urls[@]}")"
    ff_flags="$(freshness_flags <<<"$ff_tsv")"
    [[ -n "$ff_flags" ]] || ff_flags="(本轮无冻结/不可达异常)"
    ff_ms_json="$(mktemp)"
    if ( cd "$ROOT/backend" && IP_RADAR_DATA_DIR="$MS_MAIN_DATA" "$MS_EVAL_PY" \
         -m ipdb._eval --matrix-scan --json --assets-dir "$MS_MAIN_DATA/eval/assets" ) \
         > "$ff_ms_json" 2>/dev/null; then ff_ms_rc=0; else ff_ms_rc=$?; fi
    ff_ms_sum="$(${MS_EVAL_PY} ops/agent/matrix_summary.py "$ff_ms_json" 2>&1)"
    rm -f "$ff_ms_json"
    # matrix-scan rc 0/1/2 = 读数(干净/pending/violation)非轮次失败;失败信封
    # 由摘要行如实呈现(无证据≠清白)。已知限:需 token 的源 API 会落 UNREACHABLE
    # (摘要员措辞「不可达≠死键」);truth 层主仓无资产 → NO-LAYER 如实入读数。
    input+=$'\n\n'"$(cat <<EOF
## 确定性检查(本地实测,不经 LLM;T3 契约:摘要员只汇总不裁决)

### feed freshness(源 URL 提取自 backend/ipdb/_sources/*.py 只读扫描,共 ${#ff_urls[@]} 个;age_days 以 Last-Modified 计算,UNREACHABLE=不可达,NO-LM=缺头)
${ff_tsv}

### 异常标记(冻结门线 ${FROZEN_DAYS} 天)
${ff_flags}

### --matrix-scan 违例读数
命令: (cd backend && IP_RADAR_DATA_DIR=${MS_MAIN_DATA} ${MS_EVAL_PY} -m ipdb._eval --matrix-scan --json --assets-dir ${MS_MAIN_DATA}/eval/assets)
退出码: ${ff_ms_rc}(0 干净/1 pending/2 violation;其他或失败信封=测量故障,见下)
${ff_ms_sum}
EOF
)"
    ledger_note="urls=${#ff_urls[@]} flags=$(grep -c '建议复核' <<<"$ff_flags" || true) matrix_rc=${ff_ms_rc}"
    ;;
  discover)
    sys_prompt=ops/agent/prompts/discover-system.md
    # 工具面收紧(T3.5 问题④):-xt write,edit 留 read+bash 跑探针(gh/curl/ipdb
    # CLI);注意 bash 仍可写文件——沙箱保证仍是系统提示红线+轮末 sandbox_assert,
    # 工具收紧只减面不立界。
    pi_flags=(-xt write,edit)
    model_label="default(主力)"
    kws=(排他率 聚合器 许可 体量 冻结)
    ;;
  *) usage ;;
esac
kws+=("$@")

[[ -f "$sys_prompt" ]] || { echo "round: 缺系统提示文件 $sys_prompt" >&2; exit 1; }

# 1) 组用户消息 = 判例注入块(rg 词法,无嵌入)+ 本轮输入;系统提示(role/边界/
#    输出契约)经 --append-system-prompt 文件传入(实测读文件内容,2026-10-19 探针)
inject_block="$(inject_precedents "${kws[@]}")"
user_msg="$inject_block

# 本轮输入

$input"

# 2) pi 短命调用(T3.5 修正面:json 真用量/no-session/no-extensions/工具收紧;
#    失败面——stopReason=error/aborted、agent_settled.aborted、空文本——由 run_pi 自判)
if ! run_pi --append-system-prompt "$sys_prompt" ${pi_flags[@]+"${pi_flags[@]}"} <<<"$user_msg"; then
  echo "round: pi 调用失败,轮次失败" >&2; exit 1
fi

# 3) 裁决包草稿落 docs 仓(经符号链接;文件名带 HHMM——同日同轮重跑不覆盖,证据不灭失裁决 2026-10-19 评审 Minor-2)
pkg_dir="$DOCS_ROOT/ops/packages"; mkdir -p "$pkg_dir"
pkg="$pkg_dir/$(date +%F)-$round-$(date +%H%M).md"
printf '%s\n' "$PI_TEXT" > "$pkg"

# 4) 台账(用量=pi 实报真数,九裁决 9)→ 5) 判例引用校验 → 6) 沙箱断言(每轮末步强制,Review Focus 1)
ledger_append "$round" "$model_label" "$PI_USAGE" "${ledger_note:-}"
verify_cited_precedents "$pkg"
sandbox_assert
echo "round: $round 完成 → $pkg"
