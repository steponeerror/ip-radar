#!/usr/bin/env bash
# 月轮全量评估(Eval Algorithm v2 Phase 1 收口;决策 #6:手动触发,
# 错峰可前置 nice/ionice,如 `nice -n 19 ionice -c3 bash scripts/monthly_eval.sh`)。
# 流程:① 守卫(须在 master 且工作区 clean)② rsync 生产 volume 镜像到本地
# ③ 五连 eval 命令(--model 先落盘本轮,--audit/--temporal 只读 model 历史)
# ④ 每命令打印尾行摘要。
# 自验:`bash -n scripts/monthly_eval.sh`(语法);`bash scripts/monthly_eval.sh
# --dry-run`(只打印将执行的命令不执行;dry-run 下守卫仅提示不拦截,便于预演)。
# 数据目录默认 <repo>/.eval-prod-data(已 gitignore,防误提交 ~55GB),
# 环境变量 EVAL_DATA_DIR 可覆盖。
# 设计:docs/superpowers/specs/2026-09-28-eval-algorithm-optimization-brief.md
set -euo pipefail

usage() {
  echo "用法: scripts/monthly_eval.sh [prod-host] [--dry-run]"
  echo "  prod-host  默认 root@203.88.124.85"
  echo "  --dry-run  只打印将执行的命令,不执行"
}

PROD_HOST="root@203.88.124.85"
DRY_RUN=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) PROD_HOST="$a" ;;
  esac
done

REPO=$(git rev-parse --show-toplevel)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ -n "$(git status --porcelain)" ]; then DIRTY=yes; else DIRTY=no; fi
DATA_DIR="${EVAL_DATA_DIR:-$REPO/.eval-prod-data}"
RSYNC_SRC="$PROD_HOST:/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data/"  # 尾斜杠=拷内容

echo "repo:   $REPO"
echo "branch: $BRANCH (dirty: $DIRTY)"
echo "host:   $PROD_HOST"
echo "data:   $DATA_DIR"

# 守卫:月轮在 master 基线上跑,树必须 clean(防把未提交代码的评估当月轮结论)
if [ "$DRY_RUN" != 1 ]; then
  if [ "$BRANCH" != "master" ]; then
    echo "拒绝:不在 master(当前 $BRANCH)" >&2; exit 1
  fi
  if [ "$DIRTY" = "yes" ]; then
    echo "拒绝:工作区未 clean" >&2; exit 1
  fi
fi

run_step() {  # run_step <label> <ipdb._eval args...> — 执行并打印尾行摘要
  local label=$1; shift
  local log="/tmp/monthly_eval-$label.log"
  echo
  echo "==> $label: python3 -m ipdb._eval $*"
  if [ "$DRY_RUN" = 1 ]; then return 0; fi
  # cwd 须在 backend/(模块路径 ipdb);报告目录用绝对路径防 cwd 歧义
  ( cd "$REPO/backend" && \
      IP_RADAR_DATA_DIR="$DATA_DIR" \
      IP_RADAR_EVAL_DIR="$REPO/backend/data/eval" \
      python3 -m ipdb._eval "$@" ) 2>&1 | tee "$log"
  echo "-- [$label 尾行] $(tail -n 2 "$log" | tr '\n' ' ')"
}

echo
echo "==> rsync: $RSYNC_SRC -> $DATA_DIR/"
if [ "$DRY_RUN" != 1 ]; then
  mkdir -p "$DATA_DIR"
  # --delete-after 保持镜像(与既往手动月轮一致)
  rsync -az --partial --delete-after --info=progress2 "$RSYNC_SRC" "$DATA_DIR/"
fi

run_step model    --model    # 舰队模型 + 验收套件(落盘本轮 model-*.json)
run_step all      --all      # 逐源 verdict 表
run_step anchors  --anchors  # 锚点回归
run_step dsem     --dsem     # DS-EM 公平对决(advisory)
run_step audit    --audit    # 谱系前向流审计(读 model 历史)
run_step temporal --temporal # λ_s 确认率(读 model 历史,须 ≥2 轮)

echo
echo "完成。报告目录: $REPO/backend/data/eval(model/ 逐轮累积)"
