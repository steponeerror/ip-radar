#!/usr/bin/env bash
# 月轮全量评估(Eval Algorithm v2 Phase 1 收口;决策 #6:手动触发,
# 错峰可前置 nice/ionice,如 `nice -n 19 ionice -c3 bash scripts/monthly_eval.sh`)。
# 断史红线(2026-10-29 判例):temporal 腿需 ≥2 个 model 轮历史——必须在带
# backend/data/eval/monthly/ 累积历史的副本上跑(仓主 worktree 即有;干净
# worktree 会断供致 rc=2 insufficient rounds 且不落工件,报告族被拒)。
# 流程:① 守卫(须在 master 且工作区 clean)② rsync 生产 volume 镜像到本地
# ③ 镜像 manifest 守卫(S7: 塕缩即止, 先于读数)④ 十连 eval 命令
# (--model 先落盘本轮;--audit/--anchors 只读 model 历史但各落己件
# audit-*/anchors-*.json(Phase 2 T8,清偿 Phase 1 T14 缓议);--agg-share
# 印证对聚合器占比披露(#183/spec #180 Q4,只测量不持门 exit 恒 0,落
# model/agg-share-*.json);--sinkhole-probe 污染探针+#233 锚读数族
# 双读数(ADR 0013,只测量不持门,落 model/sinkhole-probe-*.json +
# anchor-fp-*.json + scanner-recall-*.json);--temporal 读
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

REPORT_ROOT="$REPO/backend/data/eval/monthly"
# ── 腿级 rc 分离(#193 C5,承 F4 anchors 判例推广到全腿):任一腿红
# 不中止后续腿(红态记录≠管线中止),工件照写留证;缺员即死不变
# (工件缺席=半途中止=死,不推心跳)。腿级状态落 leg-status-*.json
# (报告根,机器可读:render 前件 readout=null 供月报嵌「在飞」,结尾
# 定稿;_alerts 只认心跳 mtime,腿级红必须长在工件里,评审D P1-3)。
# 结尾退出码=腿序首个非零(红态外显不吞)。
# ── #233 T4(ADR 0013):锚读数族两腿入序。位置内聚度:sinkhole-probe
# 紧随 agg-share(同源 raw 采样面,复用 agg_share.probe_ips,只测量
# 不持门同律);anchor-readouts 承其后(锚/自报段 lookup 面,与
# --anchors 判定门腿同锚族但只测量,不插判定门与 advisory 腿之间);两
# 新腿均不读 model 历史 → 置于历史读者(audit/temporal)之前,readout
# 组装面殿后不变。两腿均不进判定门(只测量,exit 恒 0;红=崩溃即
# 工件缺席,报告族缺员即死把关)。
LEG_ORDER=(model all anchors dsem agg-share sinkhole-probe anchor-readouts audit temporal readout)
declare -A LEG_RC=()
for _leg in "${LEG_ORDER[@]}"; do LEG_RC[$_leg]=0; done
run_step model    --model    || LEG_RC[model]=$?      # 舰队模型+验收套件(model-*.json)
run_step all      --all      || LEG_RC[all]=$?        # 逐源 verdict 表
run_step anchors  --anchors  || LEG_RC[anchors]=$?    # 锚点回归(判定门:失败 rc=1 照写工件)
run_step dsem     --dsem     || LEG_RC[dsem]=$?       # DS-EM 公平对决(advisory)
run_step agg-share --agg-share || LEG_RC[agg-share]=$?  # 印证对聚合器占比披露(#183;只测量不持门,exit 恒 0)
run_step sinkhole-probe --sinkhole-probe || LEG_RC[sinkhole-probe]=$?  # 污染探针(#233 T2/ADR 0013;只测量不持门,exit 恒 0,落 model/sinkhole-probe-*.json)
# #233 T3 评审 P2#4 月轮首跑核对项:monthly 全源物化下 scanner-recall
# 工件的 n_self_echo 应>0(dev 库 0=数据条件非机制失效;机制由 T3 单测钉,
# 读数留痕 model/scanner-recall-*.json,首跑后人工核对该件)。
run_step anchor-readouts --anchor-readouts || LEG_RC[anchor-readouts]=$?  # 锚读数族双读数(#233 T3/ADR 0013;只测量不持门,一腿双工件 anchor-fp+scanner-recall;scanner_ranges CSV 缺失→missing 形状照写照绿=缺层≠0)
run_step audit    --audit    || LEG_RC[audit]=$?      # 谱系前向流审计(读 model 历史)
run_step temporal --temporal || LEG_RC[temporal]=$?   # λ_s 确认率(读 model 历史,须 ≥2 轮)

write_leg_status() {  # write_leg_status <readout_rc|null> — 腿级状态件(#193 C5)
  # 落报告根 leg-status-<ts>.json(ts 形制同族);all 腿校验须排除本件
  # (同形状不得顶替逐源 verdict 件,观测件永不触活族门)。
  [ "$DRY_RUN" = 1 ] && return 0
  local path="$REPORT_ROOT/leg-status-$(date -u +%Y%m%d-%H%M%S).json"
  local argv=("$path")
  local leg rc="readout=$1"  # readout 位由调用方显式给(null=在飞)
  for leg in "${LEG_ORDER[@]}"; do
    if [ "$leg" = readout ]; then argv+=("$leg" "$1"); else argv+=("$leg" "${LEG_RC[$leg]}"); fi
  done
  python3 - "${argv[@]}" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path = Path(sys.argv[1])
legs = {}
for i in range(2, len(sys.argv), 2):
    name, rc = sys.argv[i], sys.argv[i + 1]
    legs[name] = None if rc == "null" else int(rc)
doc = {
    "schema": "leg-status/1",
    "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "legs": legs,
    "red_legs": sorted(k for k, v in legs.items() if v not in (0, None)),
}
path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
PYEOF
  echo "==> 腿级状态件: $path"
}

# render 前件:readout 腿在飞(null)——月报 render_leg_status 读最新件嵌行
write_leg_status null
run_step readout  --readout   || LEG_RC[readout]=$?  # 月轮四层读数(§4.2/S26)月报+北星
write_leg_status "${LEG_RC[readout]}"  # 定稿件(机器可读面完整)

# 红态行(红腿逐个点名,输出面可见;证据在工件,此处外显不吞)
for _leg in "${LEG_ORDER[@]}"; do
  if [ "$DRY_RUN" != 1 ] && [ "${LEG_RC[$_leg]}" != 0 ]; then
    echo "!! $_leg 腿 rc=${LEG_RC[$_leg]}:红态记录(工件照写留证)——红态记录≠管线中止,腿级状态入 leg-status 工件,结尾外显此 rc"
  fi
done

# ── S5(裁决 A / spec §4.1):报告族齐全校验 → 心跳推送 ──
# 命令族齐全=活:逐腿写者均查本轮工件(mtime 晚于脚本启动)。audit/anchors
# json 落盘已清偿(Phase 2 T8,原 T14 缓议)→ 从退出码门升格报告族写者
# (anchors 失败仍 sys.exit(1) 双保险;audit advisory 按设计不拦退出码,
# 靠工件缺席即死把关)。agg-share 入族(#183 终审修单 F6):exit 恒 0
# 只测量不持门,但工件缺席即族缺员(写者身份≠门身份,同 northstar 反向
# 面的对称律:观测件不得触活族门,族员工件缺席仍是死)。
# sinkhole-probe/anchor-readouts 同律入族(#233 T4,ADR 0013 只测量不
# 持门;anchor-readouts 一腿双工件,anchor-fp 与 scanner-recall 两件
# 均须本轮在场)。
# 缺员即死(半途中止=死,不推心跳)。心跳落生产 volume,生产侧
# _alerts 只认文件 mtime(IP_RADAR_EVAL_HEARTBEAT,>35d 告警;时基
# 独立 S6,不信管线自报)。
HEARTBEAT_DST="/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data/eval-heartbeat"
check_family() {  # check_family <label> <subdir> <name-pattern> [排除pattern...]
  local label=$1 sub=$2 pat=$3; shift 3
  if [ "$DRY_RUN" = 1 ]; then
    echo "  [dry-run] 报告族: $label -> ${sub:+$sub/}$pat${*:+ 排除 $*}"
    return 0
  fi
  # #193: -maxdepth 1 —— find 默认递归会让 model/ 子目录同形状件(如
  # agg-share-<ts>.json)顶替根 all 腿校验;各腿工件只落自身层,
  # 限深=逐腿只在自身层验在场(腿级状态件同形状防顶替,观测件永不
  # 触活族门)。
  local args=("-maxdepth" "1" -name "$pat")
  local excl
  for excl in "$@"; do args+=(! -name "$excl"); done
  local f
  f=$(find "$REPORT_ROOT/${sub}" "${args[@]}" -newermt "@$START_S" \
        -print -quit 2>/dev/null)
  if [ -z "$f" ]; then
    echo "拒绝: 报告族不齐($label: $pat)" >&2
    exit 1
  fi
}
echo
# 报告族 10 写者(能力轨北星件 #185 与 monthly-*.md 同腿先写、只观测
# 不持门, 不另设族员):model/dsem/agg-share/sinkhole-probe/
# anchor-readouts/audit/anchors 落 model/ 子目录,
# all/temporal/readout 落报告根(monthly-*.md 缺月轮读数即缺员)。
echo "==> 报告族齐全校验(model/all/anchors/dsem/agg-share/sinkhole-probe/anchor-readouts/audit/temporal/readout)"
check_family model    model 'model-*.json'
# all 腿排除: temporal-*/northstar-* 同带 ts 后缀形状但不属逐源 verdict
# 件 —— northstar(#185 能力轨观测件)若不排除, 会顶替 all 腿满足校验
# → 回归族判定被观测件稀释(观测件永不持门, 亦不得反向触活报告族门)。
check_family all      ''     '*-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9].json' 'temporal-*' 'northstar-*' 'leg-status-*'
check_family anchors  model 'anchors-*.json'
check_family dsem     model 'dsem-*.json'
check_family agg-share model 'agg-share-*.json'
check_family sinkhole-probe model 'sinkhole-probe-*.json'
# anchor-readouts 一腿双工件:两件分别验在场(缺任一=族缺员)
check_family anchor-readouts model 'anchor-fp-*.json'
check_family anchor-readouts model 'scanner-recall-*.json'
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
# 结尾退出码(#193 C5):腿序首个非零外显(完成≠全绿;cron/操作员以
# 非零退出码感知腿级红;红腿明细在 leg-status 工件与月报腿级行)。
AGG_RC=0
for _leg in "${LEG_ORDER[@]}"; do
  if [ "${LEG_RC[$_leg]}" != 0 ]; then AGG_RC=${LEG_RC[$_leg]}; break; fi
done
exit "$AGG_RC"
