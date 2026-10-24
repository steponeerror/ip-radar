#!/usr/bin/env bash
# 月轮全量评估(Eval Algorithm v2 Phase 1 收口;决策 #6:手动触发,
# 错峰可前置 nice/ionice,如 `nice -n 19 ionice -c3 bash scripts/monthly_eval.sh`)。
# 流程:① 守卫(须在 master 且工作区 clean)② rsync 生产 volume 镜像到本地
# ③ 镜像 manifest 守卫(S7: 塕缩即止, 先于读数)④ 六连 eval 命令
# (--model 先落盘本轮;--audit/--anchors 只读 model 历史但各落己件
# audit-*/anchors-*.json(Phase 2 T8,清偿 Phase 1 T14 缓议);--temporal 读
# 历史落 temporal-*.json;--readout
# 组合四层读数管线出月报 monthly-*.md + action-block.json + northstar-*.json
# (#185 能力轨北星记录,只观测不持门))
# ⑤ 每命令打印尾行摘要 ⑥ 报告族齐全校验 → 生产 volume 心跳推送(S5)。
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
DATA_DIR="$(realpath -m "${EVAL_DATA_DIR:-$REPO/.eval-prod-data}")"  # 绝对化:防 run_step cd backend 后相对路径漂移
RSYNC_SRC="$PROD_HOST:/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data/"  # 尾斜杠=拷内容

echo "repo:   $REPO"
echo "branch: $BRANCH (dirty: $DIRTY)"
echo "host:   $PROD_HOST"
echo "data:   $DATA_DIR"
START_S=$(date +%s)  # S5:报告族"本轮"锚 —— 工件 mtime 须晚于此才算本轮产物

# 守卫:月轮在 master 基线上跑,树必须 clean(防把未提交代码的评估当月轮结论)
if [ "$DRY_RUN" != 1 ]; then
  if [ "$BRANCH" != "master" ]; then
    echo "拒绝:不在 master(当前 $BRANCH)" >&2; exit 1
  fi
  if [ "$DIRTY" = "yes" ]; then
    echo "拒绝:工作区未 clean" >&2; exit 1
  fi
fi

run_step() {  # run_step <label> <ipdb._eval args...> — 执行并打印尾行摘要;rc=命令退出码
  # 管线 rc 显式捕获后 return(不靠 set -e 在函数内炸出——调用方在 || 语境下调
  # 用时 set -e 全程失效,靠尾命令 echo 会吞 rc;终审修单 F4 判例)
  local label=$1; shift
  local log="/tmp/monthly_eval-$label.log"
  local rc=0
  echo
  echo "==> $label: IP_RADAR_EVAL_ENV=monthly python3 -m ipdb._eval $*"
  if [ "$DRY_RUN" = 1 ]; then return 0; fi
  # cwd 须在 backend/(模块路径 ipdb);报告目录用绝对路径防 cwd 歧义
  ( cd "$REPO/backend" && \
      IP_RADAR_DATA_DIR="$DATA_DIR" \
      IP_RADAR_EVAL_DIR="$REPO/backend/data/eval" \
      IP_RADAR_EVAL_ENV=monthly \
      python3 -m ipdb._eval "$@" ) 2>&1 | tee "$log" || rc=$?
  echo "-- [$label 尾行] $(tail -n 2 "$log" | tr '\n' ' ')"
  return "$rc"
}

echo
echo "==> rsync: $RSYNC_SRC -> $DATA_DIR/"
if [ "$DRY_RUN" != 1 ]; then
  mkdir -p "$DATA_DIR"
  # --delete-after 保持镜像(与既往手动月轮一致)
  # rc=24(源侧活文件消失)对活镜像良性:生产 scheduler 随时在重建 LMDB epoch,
  # 旧 epoch 家族中途消失属常态;其余非零仍致命(首月轮 2026-10-14 实测发现)。
  rsync -az --partial --delete-after --info=progress2 "$RSYNC_SRC" "$DATA_DIR/" && rc=0 || rc=$?
  if [ "$rc" != 0 ] && [ "$rc" != 24 ]; then
    echo "拒绝: rsync 失败 (rc=$rc)" >&2; exit 1
  fi
  [ "$rc" = 24 ] && echo "-- rsync rc=24(源侧活动文件消失,活镜像可容忍)"
fi

# 守卫序(S7): rsync 后、读数前校验 manifest(文件数+字节+epoch 指纹+抽样
# sha256);源塔缩(binarydefense 6347→382 式)或半截 rsync → 退出非零,
# set -e 在任何 eval 读数前中止。manifest 只在通过时落盘,失败保留旧档
# 可复现;epoch 指纹留档供新鲜度哨兵(S6)。
MIRROR_MANIFEST="$REPO/backend/data/eval/monthly/mirror-manifest.json"
echo
echo "==> mirror-check: python3 -m ipdb._eval.mirror_check \"$DATA_DIR\" \"$MIRROR_MANIFEST\""
if [ "$DRY_RUN" != 1 ]; then
  ( cd "$REPO/backend" && \
      IP_RADAR_DATA_DIR="$DATA_DIR" \
      IP_RADAR_EVAL_ENV=monthly \
      python3 -m ipdb._eval.mirror_check "$DATA_DIR" "$MIRROR_MANIFEST" )
fi

run_step model    --model    # 舰队模型 + 验收套件(落盘本轮 model-*.json)
run_step all      --all      # 逐源 verdict 表
# anchors 腿:失败不阻断后续腿(终审修单 F4)——回归红态记录≠管线中止:
# 锚点红时工件照写(anchors_report 失败也落盘 anchors-*.json,证据不灭),
# rc 捕获进运行日志红态行,readout/月报/北星与心跳照常,结尾以此 rc 退出
# (红态外显不吞);其余腿 set -e 语义不变(仍缺员即死不推心跳)。
# 守卫=tests/eval/test_monthly_eval_cascade.py(密闭 harness:桩腿红绿双态)。
ANCHORS_RC=0
run_step anchors  --anchors  || ANCHORS_RC=$?  # 锚点回归(判定门:失败 rc=1 照写工件)
if [ "$DRY_RUN" != 1 ] && [ "$ANCHORS_RC" != 0 ]; then
  echo "!! anchors 腿 rc=$ANCHORS_RC:回归红态(anchors-*.json 已照写留证)——红态记录≠管线中止,后续腿照跑,结尾外显此 rc"
fi
run_step dsem     --dsem     # DS-EM 公平对决(advisory)
run_step audit    --audit    # 谱系前向流审计(读 model 历史)
run_step temporal --temporal # λ_s 确认率(读 model 历史,须 ≥2 轮)
run_step readout  --readout  # 月轮四层读数(§4.2/S26: 资产+四层读数+行动区块+月报)

# ── S5(裁决 A / spec §4.1):报告族齐全校验 → 心跳推送 ──
# 七命令齐全=活:七写者均查本轮工件(mtime 晚于脚本启动)。audit/anchors
# json 落盘已清偿(Phase 2 T8,原 T14 缓议)→ 从退出码门升格报告族写者
# (anchors 失败仍 sys.exit(1) 双保险;audit advisory 按设计不拦退出码,
# 靠工件缺席即死把关)。
# 缺员即死(半途中止=死,不推心跳)。心跳落生产 volume,生产侧
# _alerts 只认文件 mtime(IP_RADAR_EVAL_HEARTBEAT,>35d 告警;时基
# 独立 S6,不信管线自报)。
REPORT_ROOT="$REPO/backend/data/eval/monthly"
HEARTBEAT_DST="/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data/eval-heartbeat"
check_family() {  # check_family <label> <subdir> <name-pattern> [排除pattern...]
  local label=$1 sub=$2 pat=$3; shift 3
  if [ "$DRY_RUN" = 1 ]; then
    echo "  [dry-run] 报告族: $label -> ${sub:+$sub/}$pat${*:+ 排除 $*}"
    return 0
  fi
  local args=(-name "$pat")
  local excl
  for excl in "$@"; do args+=(! -name "$excl"); done
  local f
  f=$(find "$REPORT_ROOT/${sub}" "${args[@]}" -newermt "@$START_S" \
        -print -quit 2>/dev/null)
  if [ -z "$f" ]; then
    echo "拒绝: 报告族不齐($label)" >&2
    exit 1
  fi
}
echo
# 报告族 7 写者(能力轨北星件 #185 与 monthly-*.md 同腿先写、只观测
# 不持门, 不另设族员):model/dsem/audit/anchors 落 model/ 子目录,
# all/temporal/readout 落报告根(monthly-*.md 缺月轮读数即缺员)。
echo "==> 报告族齐全校验(model/all/anchors/dsem/audit/temporal/readout)"
check_family model    model 'model-*.json'
# all 腿排除: temporal-*/northstar-* 同带 ts 后缀形状但不属逐源 verdict
# 件 —— northstar(#185 能力轨观测件)若不排除, 会顶替 all 腿满足校验
# → 回归族判定被观测件稀释(观测件永不持门, 亦不得反向触活报告族门)。
check_family all      ''     '*-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9].json' 'temporal-*' 'northstar-*'
check_family anchors  model 'anchors-*.json'
check_family dsem     model 'dsem-*.json'
check_family audit    model 'audit-*.json'
check_family temporal ''     'temporal-*.json'
check_family readout  ''     'monthly-*.md'

echo
echo "==> 心跳推送: $PROD_HOST:$HEARTBEAT_DST"
if [ "$DRY_RUN" = 1 ]; then
  echo "  [dry-run] 跳过 ssh(生产 volume 心跳写入)"
else
  ssh "$PROD_HOST" "printf '%s\n' $(date -u +%Y-%m-%dT%H:%M:%SZ) > $HEARTBEAT_DST"
fi

echo
echo "完成。报告目录: $REPORT_ROOT(model/ 逐轮累积)"
# 结尾退出码:anchors 红态外显(完成≠全绿;cron/操作员以非零退出码感知
# 回归轨红,详见 CHANGELOG「回归红态记录不等于管线中止」句)。
exit "$ANCHORS_RC"
