#!/usr/bin/env bash
# 月轮全量评估(Eval Algorithm v2 Phase 1 收口;决策 #6:手动触发,
# 错峰可前置 nice/ionice,如 `nice -n 19 ionice -c3 bash scripts/monthly_eval.sh`)。
# 断史红线(2026-10-29 判例):temporal 腿需 ≥2 个 model 轮历史——必须在带
# backend/data/eval/monthly/ 累积历史的副本上跑(仓主 worktree 即有;干净
# worktree 会断供致 rc=2 insufficient rounds 且不落工件,报告族被拒)。
# 流程:① 守卫(须在 master 且工作区 clean)② rsync 生产 volume 镜像到本地
# (+truth-v2 周快照面拉取, ADR 0017 T0 采集器/#262 T3 接线;+honyport
# 日 CSV 面拉取, ADR 0017 §2 第二组件/issue #265)
# ③ 镜像 manifest 守卫(S7: 塕缩即止, 先于读数)④ 十二连 eval 命令
# (--model 先落盘本轮;--audit/--anchors 只读 model 历史但各落己件
# audit-*/anchors-*.json(Phase 2 T8,清偿 Phase 1 T14 缓议);--agg-share
# 印证对聚合器占比披露(#183/spec #180 Q4,只测量不持门 exit 恒 0,落
# model/agg-share-*.json);--sinkhole-probe 污染探针+#233 锚读数族
# 双读数(ADR 0013,只测量不持门,落 model/sinkhole-probe-*.json +
# anchor-fp-*.json + scanner-recall-*.json);--truth-v2 真值语料 v2
# 构建腿(ADR 0017/#262 T3 接线,周快照→滚动窗→组件闸→版本化双 pin,
# published/哨兵两态均落 model/truth-v2-build-*.json);--truth-v2-readout
# v2 读数腿一腿三工件(#261 T2 附录读数 + #262 T3 并排对照 + 换卷触发
# 判定,均只观测不持门,落 model/truth-v2-{readout,parallel,swap}-*.json);
# --temporal 读
# 历史落 temporal-*.json;--readout
# 组合四层读数管线出月报 monthly-*.md + action-block.json + northstar-*.json
# (#185 能力轨北星记录,只观测不持门))
# ④′ scan-equiv(#500,#444 §5 验收工具件 scan_equiv_check.py 的节拍化):
# 全库扫描↔查询对拍两步(collect+compare,同一 asof、同一 PYTHONHASHSEED=0;
# 样本落系统临时目录带轮次时间戳,比完即删;两步各留一行 JSON 到 scan-equiv/;
# rc 持门同 anchors:1=判定不一致或进程异常退出(collect 的正常出口只有
# 0,collect 的 1 必是崩溃),2=样本作废或用法错;rc=2 日志有人话「重跑
# 这一轮」);
# 位置在 readout(出月报)前。不在 LEG_ORDER:那个数组的每一项都对应一条
# `python3 -m ipdb._eval <旗标>` 腿,本腿跑的是独立工具件;rc 经
# LEG_RC[scan-equiv] 单列接线(红态行+结尾 AGG_RC,见对应注释)。抽样密度
# 缺省与实测依据见 run_scan_equiv 内注释。
# ⑤ 每命令打印尾行摘要(腿日志全文落 monthly/logs/,#468) ⑥ 报告族齐全校验 → 评估报告推送(#453:rsync
# 本轮逐源 verdict 件+model/model-*.json 到生产卷 eval/monthly/,推失败
# 记红态心跳照写结尾非零)→ 生产 volume 心跳推送(S5)。
# 自验:`bash -n scripts/monthly_eval.sh`(语法);`bash scripts/monthly_eval.sh
# --dry-run`(只打印将执行的命令不执行;dry-run 下守卫仅提示不拦截,便于预演)。
# #489 起干跑也要 python3 能导入 ipdb._eval(mirror-sync 单源入口,三面
# 回显都出自它);PATH 须带后端依赖的解释器(同实跑各腿)。
# 数据目录默认 <repo>/.eval-prod-data(已 gitignore,防误提交 ~55GB),
# 环境变量 EVAL_DATA_DIR 可覆盖。
# 设计:docs/superpowers/specs/2026-09-28-eval-algorithm-optimization-brief.md
set -euo pipefail

usage() {
  echo "用法: scripts/monthly_eval.sh [prod-host] [--dry-run]"
  echo "  prod-host  默认 $PROD_HOST"
  echo "  --dry-run  只打印将执行的命令,不执行"
}

PROD_HOST="root@203.88.124.85"
DRY_RUN=0
DRY_FLAG=""    # mirror-sync 单源入口的干跑旗标(#489;空=实跑)
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1; DRY_FLAG="--dry-run" ;;
    -h|--help) usage; exit 0 ;;
    *) PROD_HOST="$a" ;;
  esac
done

REPO=$(git rev-parse --show-toplevel)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ -n "$(git status --porcelain)" ]; then DIRTY=yes; else DIRTY=no; fi
DATA_DIR="$(realpath -m "${EVAL_DATA_DIR:-$REPO/.eval-prod-data}")"  # 绝对化:防 run_step cd backend 后相对路径漂移
# #489:拉取面源路径/旗标/rc 容忍收口到 backend/ipdb/_eval/gate_mirror.py
# 的 SYNC_FACES 契约(原 RSYNC_SRC/RSYNC_TV2_SRC/RSYNC_HP_SRC 三份字面量
# 已删),三面统一经 `python -m ipdb._eval mirror-sync` 单源入口调用。
mirror_sync() {  # mirror_sync <face> <本地目标目录> — 回显/建目录/容忍/留痕都在入口
  ( cd "$REPO/backend" && \
      python3 -m ipdb._eval mirror-sync --host "$PROD_HOST" --face "$1" \
        --dst "$2" $DRY_FLAG )
}

echo "repo:   $REPO"
echo "branch: $BRANCH (dirty: $DIRTY)"
echo "host:   $PROD_HOST"
echo "data:   $DATA_DIR"
START_S=$(date +%s)  # S5:报告族"本轮"锚 —— 工件 mtime 须晚于此才算本轮产物
ROUND_TS=$(date -u +%Y%m%dT%H%M%SZ)  # #468:一轮一个 UTC 时间戳(脚本开头取一次),全部腿日志文件名共用;一轮一个时间戳,不覆盖上一轮

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
  # #468:腿日志改落报告目录树($LOG_DIR,定义在 REPORT_ROOT 旁),不再写
  # /tmp/monthly_eval-<腿名>.log —— 旧文件名写死、不分轮次,后一次运行就覆盖
  # 前一次(2026-11-25 回看:固定路径上只剩空文件;每跑一遍级联测试也会把
  # 十二个文件清空,桩不产生输出);/tmp 另有重启即丢。文件名带 ROUND_TS,
  # 一轮一个时间戳,不覆盖上一轮。
  local log="$LOG_DIR/$label-$ROUND_TS.log"
  local rc=0
  echo
  echo "==> $label: IP_RADAR_EVAL_ENV=monthly python3 -m ipdb._eval $*"
  if [ "$DRY_RUN" = 1 ]; then return 0; fi  # 干跑不建目录不写文件(#468)
  mkdir -p "$LOG_DIR"
  # cwd 须在 backend/(模块路径 ipdb);报告目录用绝对路径防 cwd 歧义
  ( cd "$REPO/backend" && \
      IP_RADAR_DATA_DIR="$DATA_DIR" \
      IP_RADAR_EVAL_DIR="$REPO/backend/data/eval" \
      IP_RADAR_EVAL_ENV=monthly \
      python3 -m ipdb._eval "$@" ) 2>&1 | tee "$log" || rc=$?
  echo "-- [$label 尾行] $(tail -n 2 "$log" | tr '\n' ' ')"
  return "$rc"
}

run_scan_equiv() {  # #500 全库扫描↔查询对拍腿:scan_equiv_check.py 两步跑
  # 不进 LEG_ORDER:那个数组的每一项都对应一条 `python3 -m ipdb._eval <旗标>`
  # 腿(还供 leg-status/红态行/AGG_RC 迭代共用,语义=eval 旗标腿清单);
  # 本腿跑独立工具件,rc 进 LEG_RC[scan-equiv],接线三处照 anchors 持门腿:
  # 红态行、腿级状态件(write_leg_status)、结尾 AGG_RC(腿序位=执行序:
  # temporal 后、readout 前)。
  # 数据目录与其他腿同源:同一 IP_RADAR_DATA_DIR="$DATA_DIR"(本地镜像)。
  # 两步必须同一 asof、同一 PYTHONHASHSEED=0(脚本 docstring 的对拍前提;
  # 扫描器开着时同进程不能 load_db,故分 collect/compare 两个进程)。
  local label=scan-equiv
  local log="$LOG_DIR/$label-$ROUND_TS.log"
  local json_dir="$REPORT_ROOT/scan-equiv"
  local sample="${TMPDIR:-/tmp}/scan-equiv-$ROUND_TS.jsonl.gz"
  local rc=0
  local asof; asof=$(date +%s)   # 一次取定,两步共用(compare 复核同锚刻)
  echo
  echo "==> $label: PYTHONHASHSEED=0 python3 backend/scripts/scan_equiv_check.py collect --asof $asof --single-every $SINGLE_EVERY --out $sample"
  echo "==> $label: PYTHONHASHSEED=0 python3 backend/scripts/scan_equiv_check.py compare --asof $asof --sample $sample"
  if [ "$DRY_RUN" = 1 ]; then return 0; fi  # 干跑只打印两条命令,不执行不建目录(#500)
  mkdir -p "$LOG_DIR" "$json_dir"
  ( cd "$REPO/backend" && \
      IP_RADAR_DATA_DIR="$DATA_DIR" \
      PYTHONHASHSEED=0 \
      python3 "$REPO/backend/scripts/scan_equiv_check.py" collect \
      --asof "$asof" --single-every "$SINGLE_EVERY" --out "$sample" ) \
      2>&1 | tee "$log" || rc=$?
  # 两步各自打印的那行 JSON 是留下的证据件(#500):样本体很大(全收档原始
  # JSON 数 GB、gz 后实测 158 MB),留临时目录比完即删;JSON 行从腿日志摘取
  # 落 scan-equiv/(空文件=该步没吐 JSON,本身即异常信号,不以 grep 失败
  # 持门——步骤 rc 已持门)。
  grep -m1 '^{"mode": "collect"' "$log" > "$json_dir/collect-$ROUND_TS.json" || :
  if [ "$rc" = 0 ]; then
    local compare_rc=0
    ( cd "$REPO/backend" && \
        IP_RADAR_DATA_DIR="$DATA_DIR" \
        PYTHONHASHSEED=0 \
        python3 "$REPO/backend/scripts/scan_equiv_check.py" compare \
        --asof "$asof" --sample "$sample" ) \
        2>&1 | tee -a "$log" || compare_rc=$?
    grep -m1 '^{"mode": "compare"' "$log" > "$json_dir/compare-$ROUND_TS.json" || :
    rc=$compare_rc
    # compare 的 1 且 JSON 没落盘 = mismatches 行没吐,多半是崩溃不是判定
    # 不一致——日志多指一句路(评审返工 5)。
    if [ "$rc" = 1 ] && [ ! -s "$json_dir/compare-$ROUND_TS.json" ]; then
      echo "-- [$label] rc=1 且 compare 没吐 JSON:多半是崩溃,看腿日志" | tee -a "$log"
    fi
  fi
  rm -f "$sample" "$sample.head.json"  # 样本体+纪元旁证:判定已落 JSON 与腿日志,比完即删(#500)
  if [ "$rc" = 2 ]; then
    # rc=2=样本作废或用法错(纪元换了/asof 对不上/样本名不对):人话指引进日志与运行输出(#500)
    echo "-- [$label] rc=2:样本作废或用法错(纪元换了/asof 对不上/样本名不对),两步都要重跑——重跑这一轮" | tee -a "$log"
  fi
  echo "-- [$label 尾行] $(tail -n 2 "$log" | tr '\n' ' ')"
  return "$rc"
}

echo
# #489:主卷镜像拉取收口单源入口。旗标、容忍集、留痕文案见
# gate_mirror.SYNC_FACES;回显行在入口内逐字同改前;实跑前自建目录。
mirror_sync main "$DATA_DIR"

# ── truth-v2 周快照面拉取(ADR 0017 T0 采集器 / #262 T3 接线):小机
# auth.log 周快照在服务器 /opt/ip-truth-capture/(卷外, 周日 04:17 cron),
# 单独拉到本地镜像供 --truth-v2 构建腿消费;rc 容忍与卷镜像同律
# (rc=24 源侧活文件消失良性)。采集断供 → 构建腿 rc=2 坏输入族
# fail-loud(不静默跳过: 真值层断供是采集健康事故, 须人见)。
TRUTH_V2_CAPTURE_DIR="$(realpath -m "${TRUTH_V2_CAPTURE_DIR:-$DATA_DIR/truth-v2-capture}")"
echo
mirror_sync truth-v2 "$TRUTH_V2_CAPTURE_DIR"

# ── honyport 日 CSV 面拉取(issue #265, ADR 0017 §2 第二组件):服务器
# /opt/honyport/out/ 蜜罐舰队日 CSV(表头 ip,service,protocol,events,
# first_seen,last_seen, 文件名 honeypot_attackers-<YYYY-MM-DD>.csv)。与
# 快照面的差异: 远端目录缺席 = 合法态(数据未到/舰队未上线), 跳过拉取
# 且不传 honyport 组件参数 —— 组件闸哨兵吸收起步个位数 IP(#265 验收线
# 「缺目录=哨兵不持死」);目录在场则 rsync 容忍规则与快照面同律(rc=24
# 良性), 其余非零照 fail-loud。探测用 ssh test -d: rc=255(ssh 自身连
# 接/认证失败)与目录缺席(rc=1)分开 —— 网络断不得伪装成哨兵态静默
# 跳过(静默缩水)。
HONYPORT_CSV_DIR="$(realpath -m "${TRUTH_V2_HONYPORT_DIR:-$DATA_DIR/truth-v2-honyport}")"
HP_COMPONENT_ARG=()   # 远端目录在场才填充;空 = truth-v2 腿只跑 smallbox
                      # (展开处用 ${A[@]+"${A[@]}"} 形: bash<4.4 set -u 下空
                      #  数组裸展开报 unbound variable, 评审环条目 5a)
if [ "$DRY_RUN" = 1 ]; then
  echo
  mirror_sync honyport "$HONYPORT_CSV_DIR"
  echo "  [dry-run] 实跑时先 ssh 探测远端 /opt/honyport/out:在场→rsync+传"
  echo "  honyport 组件参数;缺席→只跑 smallbox(哨兵态不持死,#265)"
else
  hp_probe_rc=0
  ssh "$PROD_HOST" test -d /opt/honyport/out 2>/dev/null || hp_probe_rc=$?
  if [ "$hp_probe_rc" = 255 ]; then
    echo "拒绝: honyport 面探测 ssh 失败(rc=255, 连接/认证)" >&2; exit 1
  elif [ "$hp_probe_rc" != 0 ]; then
    echo
    echo "==> honyport 面: 远端 /opt/honyport/out 缺席, 不接 honyport 组件"
    echo "    (合法哨兵态不持死: 数据未到, 组件闸哨兵吸收;#265/ADR 0017 §2)"
  else
    echo
    mirror_sync honyport "$HONYPORT_CSV_DIR"
    HP_COMPONENT_ARG=(--truth-v2-component "honyport=$HONYPORT_CSV_DIR")
  fi
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
LOG_DIR="$REPORT_ROOT/logs"  # #468:每条腿日志目录(报告目录树下 monthly/logs/,与月轮工件同树);run_step 在此之后才首次调用,call-time 取值安全
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
# ── #262 T3(ADR 0017):truth-v2 构建/读数两腿入序。位置:构建腿在
# 读数腿前(其产物 = 读数腿输入);读数腿在 anchors 判定门后(换卷
# 触发判定读逐轮 anchors-*.json 工件, 须见本轮件)、历史读者
# (audit/temporal)前(#233 T4 同律: 不读 model 历史的新观测腿前置)。
# 零持门不变:两腿 rc 恒 0 语义照旧(缺件/哨兵态工件照写);红=崩溃
# 即工件缺席,报告族缺员即死把关(与 sinkhole-probe/anchor-readouts
# 同语义)。入族的真实成本 = LEG_ORDER 与写者计数/文档同步(#261 评审
# P2-2 措辞照准确机制: 观测腿在合法缺数据态也落件,不存在「缺件持
# 死」;只有崩溃(如采集面断供)才缺件即死——那正是要人见的事)。
# honyport 日 CSV 面已接线(#265): 远端 /opt/honyport/out 在场才传
# --truth-v2-component honyport=<dir>(上文 rsync 面填充 HP_COMPONENT_ARG);
# 缺席 = 只跑 smallbox, 组件闸哨兵吸收不持死(ADR 0017 §2;§7: 永不入池)。
# ── #550 quality-contract 腿入序(变异自检+事故回放的唯一载体接节拍):位置
# 在 temporal 后、readout 前(不读 model 历史不产出月报输入,放测量腿尾段)。
# 本腿挡轮(#550 评审返工必须改2,推翻首版「不挡轮」——那个前提写错了):
# CLI rc 语义 = 0 报告产出 / 2 契约表不合法(_eval/contract.py:214-217 契约表
# 三态校验、:341-343 仅 ContractError 上抛);oracle=none 的行状态是 no-reading
# 不是失败,腿不会「一上来就红」。rc 只反映「报告有没有产出」——契约表不合法
# 或进程崩溃(rc 非零)经结尾 AGG_RC 让整轮失败(挡轮点=结尾循环,无硬编码
# 排除);行级失败(单腿判定不过)收在报告 failures 面、不改 rc(contract.py
# :254-257),由本壳读本轮 quality-report 把腿级状态记红(QUALITY_CONTRACT_FAIL_N
# >0 → 腿状态 1),红态行打印失败条数 —— 行级红可见但不挡轮。本腿不入报告族
# check_family:rc 非零已覆盖「崩溃=缺件」的把关,无需缺员即死双重把关。
LEG_ORDER=(model all anchors dsem agg-share sinkhole-probe anchor-readouts truth-v2 truth-v2-readout audit temporal quality-contract readout)
declare -A LEG_RC=()
for _leg in "${LEG_ORDER[@]}"; do LEG_RC[$_leg]=0; done
LEG_RC[scan-equiv]=0  # #500:非 LEG_ORDER 腿的 rc 槽(接线见红态行、write_leg_status 与 AGG_RC 处)
# #500 scan-equiv 抽样密度(--single-every 缺省)。2026-11-27 生产镜像实测
# (dev 机 .eval-prod-data 只读,PYTHONHASHSEED=0,/usr/bin/time -v;读数全文
# 在 docs/reports/2026-11-26-arch-r4-landing/14-月轮加扫描查询对拍腿/
# impl-report-2.md):全收(=1,553 万单元)collect 19.6 分/峰值 689 MB/
# 样本 gz 158 MB,compare 峰值随样本条数线性(records=list(sample) 全驻
# 内存;纯 v4 单地址切片:10 万条 77 秒/796 MB,26.5 万条 3:09/1.92 GB,
# 50 万条 5:45/3.57 GB → ≈7.3 KB/条+≈83 MB 底)→ 全收外推 ≈40 GB,
# ≫6 GB 红线,不取。缺省 20 两步原样实测:collect 13:56/峰值 689 MB/
# 样本 gz 13.4 MB;compare 5:48/峰值 4.13 GB;mismatches=0(样本 444,689
# 条 = 单地址按 20 取一 267,451 + 网段全收 177,238),整腿 ≈19.7 分
# (≪45 分预算)、峰值 ≪6 GB 红线。IP_RADAR_SCAN_EQUIV_SINGLE_EVERY 可覆盖
# (要全收自担内存/时长)。
SINGLE_EVERY="${IP_RADAR_SCAN_EQUIV_SINGLE_EVERY:-20}"
[[ "$SINGLE_EVERY" =~ ^[1-9][0-9]*$ ]] || {
  echo "拒绝: IP_RADAR_SCAN_EQUIV_SINGLE_EVERY 须为正整数(实得 '$SINGLE_EVERY')" >&2
  exit 1
}
LEG_STATUS_TS=""  # 渲染前件 ts 锚(write_leg_status 单调钉用,#377)
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
# 快照面默认 = 本地镜像内 truth-v2-capture/(上文 rsync 拉取);
# rir/scanner 缺省 <data_dir>/ 镜像内既有件(与三闸 ops 面同源);
# honyport 组件(#265): 远端目录在场才传(HP_COMPONENT_ARG, 上文填充)。
run_step truth-v2 --truth-v2 \
  --truth-v2-component "smallbox=$TRUTH_V2_CAPTURE_DIR/snapshots" \
  ${HP_COMPONENT_ARG[@]+"${HP_COMPONENT_ARG[@]}"} \
  --ops-allowlist "$TRUTH_V2_CAPTURE_DIR/ops_allowlist.txt" \
  || LEG_RC[truth-v2]=$?  # 真值语料 v2 构建腿(ADR 0017/#260 T1;published/哨兵两态均落 model/truth-v2-build-*.json + report_dir/truth-v2/<version>/)
run_step truth-v2-readout --truth-v2-readout || LEG_RC[truth-v2-readout]=$?  # v2 读数腿一腿三工件(#261 T2 附录 + #262 T3 并排对照/换卷触发;只观测不持门)
run_step audit    --audit    || LEG_RC[audit]=$?      # 谱系前向流审计(读 model 历史)
run_step temporal --temporal || LEG_RC[temporal]=$?   # λ_s 确认率(读 model 历史,须 ≥2 轮)
run_scan_equiv || LEG_RC[scan-equiv]=$?  # #500 全库扫描↔查询对拍(持门同 anchors;两步见 run_scan_equiv)

write_leg_status() {  # write_leg_status <readout_rc|null> — 腿级状态件(#193 C5)
  # 落报告根 leg-status-<ts>.json(ts 形制同族);all 腿校验须排除本件
  # (同形状不得顶替逐源 verdict 件,观测件永不触活族门)。
  # ts 单调钉(#377):定稿件 ts 下限 = 首次(渲染前件)ts —— 宿主机时钟
  # 步进回跳时复用前件 ts 即同路径覆写,「文件名序取最新」的消费方
  # (monthly.py _load_latest_json / 级联测试 _latest_leg_status)任意时钟
  # 状态下读到的恒为定稿件;时钟健康时双件共存行为不变(同秒本就同路径覆写)。
  [ "$DRY_RUN" = 1 ] && return 0
  local ts; ts=$(date -u +%Y%m%d-%H%M%S)
  if [ -z "$LEG_STATUS_TS" ]; then LEG_STATUS_TS="$ts"; fi
  if [[ "$ts" < "$LEG_STATUS_TS" ]]; then ts="$LEG_STATUS_TS"; fi
  local path="$REPORT_ROOT/leg-status-$ts.json"
  local argv=("$path")
  local leg rc="readout=$1"  # readout 位由调用方显式给(null=在飞)
  for leg in "${LEG_ORDER[@]}"; do
    if [ "$leg" = readout ]; then argv+=("$leg" "$1")
    elif [ "$leg" = quality-contract ] && [ "${LEG_RC[$leg]}" = 0 ] \
         && [ "${QUALITY_CONTRACT_FAIL_N:-0}" -gt 0 ]; then
      # #550 评审必须改2:行级失败记红 —— CLI rc=0(报告照产出)但报告
      # failures 面非空,腿状态记 1(红);退出码不折算,挡轮只认 rc2/崩溃
      argv+=("$leg" 1)
    else argv+=("$leg" "${LEG_RC[$leg]}"); fi
  done
  argv+=("scan-equiv" "${LEG_RC[scan-equiv]}")  # #500:非旗标腿也进腿级状态(评审返工 8;渲染按 legs 字典通用)
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

# #550 quality-contract 腿:变异自检+事故回放(#349 runner,承 #351 事故回放、
# #352 变异自检)。rc 接住记 LEG_RC(0=报告产出;2=契约表不合法,经结尾 AGG_RC
# 挡轮);随后读本轮 quality-report 的 failures 条数(QUALITY_CONTRACT_FAIL_N;
# 只认 mtime 晚于 START_S 的件,崩溃轮不喂旧件),>0 时 write_leg_status 把
# 本腿腿状态记红(见该函数 argv 特例)——本腿在渲染前件之前跑完,前件/定稿
# 两份腿级状态件都含本腿终态。
run_step quality-contract --quality-contract || LEG_RC[quality-contract]=$?
QUALITY_CONTRACT_FAIL_N=0
if [ "$DRY_RUN" != 1 ]; then
  QUALITY_CONTRACT_FAIL_N="$(python3 - "$REPORT_ROOT/model" "$START_S" quality-fail-n <<'PYEOF'
import json
import sys
from pathlib import Path

model, start_s = Path(sys.argv[1]), float(sys.argv[2])
latest = None
for p in sorted(model.glob("quality-report-*.json")):
    try:
        if p.stat().st_mtime > start_s:
            latest = p
    except OSError:
        continue
if latest is None:
    print(0)
    raise SystemExit
try:
    d = json.loads(latest.read_text(encoding="utf-8"))
except (json.JSONDecodeError, OSError, ValueError):
    print(0)
    raise SystemExit
fails = d.get("failures") if isinstance(d, dict) else None
print(len(fails) if isinstance(fails, list) else 0)
PYEOF
)" || QUALITY_CONTRACT_FAIL_N=0
fi

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
# #500 scan-equiv 腿红态行(不在 LEG_ORDER,单列外显;工件=scan-equiv/ 两行 JSON+腿日志)
if [ "$DRY_RUN" != 1 ] && [ "${LEG_RC[scan-equiv]}" != 0 ]; then
  echo "!! scan-equiv 腿 rc=${LEG_RC[scan-equiv]}:红态记录(工件照写留证)——红态记录≠管线中止,腿级状态入 leg-status 工件,结尾外显此 rc"
fi
# #550 评审必须改2:行级失败红态行(rc=0 报告照产出,红在 failures 面;不进
# AGG_RC,整轮不受影响 —— 与 rc2/崩溃的挡轮分开显形;腿级状态件里记 1)
if [ "$DRY_RUN" != 1 ] && [ "${QUALITY_CONTRACT_FAIL_N:-0}" -gt 0 ]; then
  echo "!! quality-contract 行级失败 ${QUALITY_CONTRACT_FAIL_N} 条(报告 failures 面;rc=0 报告照产出,腿级状态记红)"
fi

# ── S5(裁决 A / spec §4.1):报告族齐全校验 → 心跳推送 ──
# 命令族齐全=活:逐腿写者均查本轮工件(mtime 晚于脚本启动)。audit/anchors
# json 落盘已清偿(Phase 2 T8,原 T14 缓议)→ 从退出码门升格报告族写者
# (anchors 失败仍 sys.exit(1) 双保险;audit advisory 按设计不拦退出码,
# 靠工件缺席即死把关)。agg-share 入族(#183 终审修单 F6):exit 恒 0
# 只测量不持门,但工件缺席即族缺员(写者身份≠门身份,同 northstar 反向
# 面的对称律:观测件不得触活族门,族员工件缺席仍是死)。
# sinkhole-probe/anchor-readouts 同律入族(#233 T4,ADR 0013 只测量不
# 持门;anchor-readouts 一腿双工件,anchor-fp 与 scanner-recall 两件
# 均须本轮在场)。truth-v2 构建腿与 v2 读数腿同律入族(#262 T3,ADR
# 0017 只测量不持门: 构建腿 published/哨兵两态均落 truth-v2-build 件;
# 读数腿一腿三工件 readout/parallel/swap 均恒落——观测腿在合法缺
# 数据态也落件,不存在「缺件持死」,缺员即死只辖崩溃事故)。
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
# 报告族 12 写者(能力轨北星件 #185 与 monthly-*.md 同腿先写、只观测
# 不持门, 不另设族员):model/dsem/agg-share/sinkhole-probe/
# anchor-readouts/truth-v2/truth-v2-readout/audit/anchors 落 model/
# 子目录,all/temporal/readout 落报告根(monthly-*.md 缺月轮读数即缺员)。
echo "==> 报告族齐全校验(model/all/anchors/dsem/agg-share/sinkhole-probe/anchor-readouts/truth-v2/truth-v2-readout/audit/temporal/readout)"
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
# truth-v2 构建腿: 摘要件恒在(published/哨兵两态均落;崩溃=缺员即死)
check_family truth-v2 model 'truth-v2-build-*.json'
# v2 读数腿一腿三工件: 三件分别验在场(缺任一=族缺员)
check_family truth-v2-readout model 'truth-v2-readout-*.json'
check_family truth-v2-readout model 'truth-v2-parallel-*.json'
check_family truth-v2-readout model 'truth-v2-swap-*.json'
check_family audit    model 'audit-*.json'
check_family temporal ''     'temporal-*.json'
check_family readout  ''     'monthly-*.md'

# ── #453:评估报告推送(报告族齐全校验之后、心跳之前)──
# 把本轮报告根下形状匹配的逐源 verdict 件 + model/model-*.json 推到生产
# 卷 eval/monthly/(rsync over ssh;只推 mtime 晚于脚本启动的本轮新件,
# START_S 同报告族校验;不带 --delete)。排除集与读侧 _eval_reader 今天
# 等价(读侧是内容闸「source 键是字符串」,这里是名单闸):
# northstar-*/temporal-*/leg-status-*/action-block/
# mirror-manifest 观测件不推(逐源形状排除名单与 check_family all 腿
# 同款;northstar-*/temporal-* 撞形状但无 source 键,不当报告)。
# 推失败 = 一条红态:红行外显 + 记入 PUSH_RC;心跳照写(报告族在本机
# 是齐的,生产读不到报告不该连心跳健康一起谎报),结尾退出码经 AGG_RC
# 同一出口取非零。rsync/ssh rc 显式捕获(set -e 与调用方 || 语境的坑,
# run_step F4 判例)。目标目录缺席先建(ssh mkdir -p);--dry-run 只打印。
EVAL_PUSH_DST="/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data/eval/monthly"
PUSH_RC=0
echo
echo "==> 评估报告推送: $REPORT_ROOT -> $PROD_HOST:$EVAL_PUSH_DST"
if [ "$DRY_RUN" = 1 ]; then
  echo "  [dry-run] ssh $PROD_HOST \"mkdir -p $EVAL_PUSH_DST\""
  echo "  [dry-run] rsync -az -R --files-from=<本轮工件清单> \"$REPORT_ROOT\" \"$PROD_HOST:$EVAL_PUSH_DST\""
else
  PUSH_LIST="$(mktemp "${TMPDIR:-/tmp}/monthly_eval_push.XXXXXX")"
  {
    # 逐源 verdict 件:all 腿族形状 + 观测件排除名单(见上),限报告根一层;
    # find 失败(如 model/ 缺席)不炸管道(pipefail),空清单 = 无可推
    find "$REPORT_ROOT" -maxdepth 1 \
      -name '*-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9].json' \
      ! -name 'temporal-*' ! -name 'northstar-*' ! -name 'leg-status-*' \
      -newermt "@$START_S" -printf '%P\n' 2>/dev/null || :
    find "$REPORT_ROOT/model" -maxdepth 1 \
      \( -name 'model-*.json' -o -name 'quality-report-*.json' \) \
      -newermt "@$START_S" -printf 'model/%f\n' 2>/dev/null || :
    # ↑ #550 评审必须改5:质量报告进推送清单 —— 服务器健康轮
    # (ops/agent-v2/tasks/health-round.mjs)读生产卷 model/quality-report-*.json
    # 判 mutation_check_due,不推则提醒永远「未见上次运行——首跑即到期」
  } | sort > "$PUSH_LIST"
  if [ ! -s "$PUSH_LIST" ]; then
    echo "  (本轮没有可推的报告文件,跳过推送)"
  fi
  if [ -s "$PUSH_LIST" ]; then
    ssh "$PROD_HOST" "mkdir -p $EVAL_PUSH_DST" || PUSH_RC=$?
    if [ "$PUSH_RC" = 0 ]; then
      # rc 显式捕获:调用方 || 语境下 set -e 失效,靠尾命令会吞 rc(F4 判例)
      rsync -az -R --files-from="$PUSH_LIST" "$REPORT_ROOT" \
        "$PROD_HOST:$EVAL_PUSH_DST" || PUSH_RC=$?
    fi
  fi
  rm -f "$PUSH_LIST"
  if [ "$PUSH_RC" != 0 ]; then
    echo "!! eval-报告推送 rc=$PUSH_RC:红态(心跳照写,报告族在本机齐;结尾退出码外显)" >&2
  fi
fi

echo
echo "==> 心跳推送: $PROD_HOST:$HEARTBEAT_DST"
if [ "$DRY_RUN" = 1 ]; then
  echo "  [dry-run] 跳过 ssh(生产 volume 心跳写入)"
else
  ssh "$PROD_HOST" "printf '%s\n' $(date -u +%Y-%m-%dT%H:%M:%SZ) > $HEARTBEAT_DST"
fi

echo

echo "完成。报告目录: $REPORT_ROOT(model/ 逐轮累积;腿日志 logs/<腿名>-<时间戳>.log;scan-equiv/ 全库对拍两行 JSON,#500)"
# 结尾退出码(#193 C5):腿序首个非零外显(完成≠全绿;cron/操作员以
# 非零退出码感知腿级红;红腿明细在 leg-status 工件与月报腿级行)。
AGG_RC=0
for _leg in "${LEG_ORDER[@]}"; do
  # #550 评审必须改2:quality-contract 挡轮(契约表不合法/崩溃的 rc 非零
  # 照进聚合退出码;行级失败不折算退出码,见上面行级红态行)
  if [ "${LEG_RC[$_leg]}" != 0 ]; then AGG_RC=${LEG_RC[$_leg]}; break; fi
done
# #500 scan-equiv 腿入终态(持门同 anchors;不在 LEG_ORDER 故单列一查):
# LEG_ORDER 各腿全绿才轮到它——任一 eval 旗标腿红(含执行序在它后面的
# readout)都优先于 scan-equiv 红,按 LEG_ORDER 序、不按执行序
if [ "$AGG_RC" = 0 ] && [ "${LEG_RC[scan-equiv]}" != 0 ]; then AGG_RC=${LEG_RC[scan-equiv]}; fi
# #453:推送红态经同一出口外显(腿级红优先;腿全绿时结尾取推送 rc)
if [ "$AGG_RC" = 0 ] && [ "$PUSH_RC" != 0 ]; then AGG_RC="$PUSH_RC"; fi
exit "$AGG_RC"
