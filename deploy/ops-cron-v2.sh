#!/usr/bin/env bash
# v2 生产健康轮 cron(#364 切流转正;SHADOW-RUNBOOK §已切流)
# 影子期(2026-10-28 起)SAME 门槛全绿后,v2 run-health 接生产世界:DOCS_ROOT=ops 根
# 的父(生产 ops 树 /app/data/ops:台账/queue/轮目录/precedents 全生产面),替代
# v1 ops-cron.sh 的 API 触发形(POST /api/ops/rounds)。轮 id 取容器 UTC 墙钟
# (v1 pipeline.mjs mkCtx 同钟:容器本地=UTC),宿主 cron 0 4-23/8(04/12/20 本地
# 时=03/11/19 UTC)自然接续生产既有序列。SQLite --db 缺省随 DOCS_ROOT 落
# /app/data/ops/agent-v2.sqlite(ipradar-data 卷内,随卷持久)。
#
# 与影子形 deploy/ops-shadow-cron.sh 的关键差异(其余同形,含容器内 docker exec
# 织法/凭证预检/退出码透传/rc 透传判例):
# - 生产世界:无影子根自种段——生产 ops 树本就在位,v2 直写台账/queue/轮目录;
# - 影子零外发栈整体摘除:不设 OPS_SWEEP_DRY_RUN(finding 出口按生产语义真开:
#   gh issue + apprise webhook,#184);GH_TOKEN/IP_RADAR_ALERT_URLS 继承不摘——
#   出口契约员,v1 后端 C4 白名单 _SPAWN_ENV_EXACT 本就同面透传(#364 裁定
#   2026-11-20;shadow 形曾一并摘除属影子零外发纵深,生产语义下随 dry-run 摘除);
# - PI_CODING_AGENT_DIR 显式指生产 ops 根(v1 桥 _round_env 同键:pi-web-access
#   读 web-search.json 的 jina provider 路由面)。
#
# env 面逐键白名单(#364 裁定;「逐键白名单,不笼统同环境」判例):
#   设:DOCS_ROOT/OPS_AUTH/OPS_EVAL_PY/OPS_DATA_DIR/PI_CODING_AGENT_DIR/LANG
#       (+agent-config 在场的 OPS_MODEL_HEALTH/OPS_MODEL_DISCOVER);
#   unset:IP_RADAR_ADMIN_PASSWORD/IP_RADAR_API_JWT_SECRET(管理密钥,C4 判例);
#   继承不摘:GH_TOKEN/IP_RADAR_ALERT_URLS(出口契约员)+PATH/HOME 等运行必需面。
#
# 旧 ops-cron 的 409(eval_busy)/403(鉴权败)跳过语义在直跑形无 API 面对应物,
# 同精神面保留:缺件不硬跑,明确跳过留痕 exit 0,下窗自愈(内层凭证预检)。
#
# 退出码透传 v2 信封面(ENVELOPE.md):0=completed;1=failed/refused/parked;
# 2=用法错;3=运行期异常。cron 面不重试——下窗自然重来(同 ops-cron.sh 判例)。
set -u
CONTAINER="${OPS_V2_CONTAINER:-ip-lookup-tool-ipradar-1}"
OPS_ROOT="${OPS_V2_OPS_ROOT:-/app/data/ops}"   # 测试/运维 override;缺省生产 ops 树
APP_ROOT="${OPS_V2_APP_ROOT:-/app}"            # 同上;容器内仓根(run-health.mjs 的 cwd)
# 传值经 printf %q 转义后拼入内层 sh 源码(裸拼不手写引号;override 值带空格/引号
# /元字符时 %q 产出即合法 sh 字面量——shadow 脚本同款判例)
OPS_Q=$(printf '%q' "$OPS_ROOT")
APP_Q=$(printf '%q' "$APP_ROOT")

echo "[$(date -u -Is)] ops-cron-v2: 触发 v2 生产健康轮"
# rc 透传形:先跑后取 $?;`if ! docker exec;then rc=$?` 的取反分支里 $? 恒 0,
# 拿不到信封退出码(shadow 脚本评审轮 1 修正判例)
docker exec "$CONTAINER" sh -c '
  set -e
  OPS='"$OPS_Q"'
  APP='"$APP_Q"'
  # —— 凭证预检(旧 ops-cron 409 跳过判例的直跑形延续:缺件不硬跑,明确跳过
  #    exit 0,下窗自愈)——
  if [ ! -f "$OPS/auth.json" ]; then
    echo "[$(date -u -Is)] ops-cron-v2: 生产 auth.json 未物化,本轮跳过,下窗自愈"
    exit 0
  fi
  # 模型引用从生产 agent-config 现读(v1 桥 _round_env 同源;缺配置/缺件=回落
  # env/缺省链,不注入)
  MODEL_HEALTH=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_health\",\"\"))" 2>/dev/null || true)
  MODEL_DISCOVER=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_discover\",\"\"))" 2>/dev/null || true)
  cd "$APP"
  export DOCS_ROOT="$(dirname "$OPS")"   # v1 桥同律:str(root.parent)——ops 根的父
  export OPS_AUTH="$OPS/auth.json"       # 生产物化凭证件,只读消费
  # 桥 _round_env 同源两键:OPS_EVAL_PY/OPS_DATA_DIR 是 shared.mjs 模块加载期
  # 常量,缺省指开发机路径(venv/本地 data),容器内不物化必死 PROBE
  export OPS_EVAL_PY="$(command -v python3)" OPS_DATA_DIR=/app/data
  export PI_CODING_AGENT_DIR="$OPS"      # v1 桥同键:pi-web-access 读 web-search.json(jina 路由)
  export LANG=C.UTF-8                    # C4 判例:bash 面 locale 确定性(CJK %q)
  # 管理密钥摘除(C4 判例:docker exec 继承容器全量 env,管理密钥不带进模型进程)。
  # GH_TOKEN/IP_RADAR_ALERT_URLS 不摘——finding 出口契约员(#364 裁定,见头注)
  unset IP_RADAR_ADMIN_PASSWORD IP_RADAR_API_JWT_SECRET
  [ -n "$MODEL_HEALTH" ] && export OPS_MODEL_HEALTH="$MODEL_HEALTH"
  [ -n "$MODEL_DISCOVER" ] && export OPS_MODEL_DISCOVER="$MODEL_DISCOVER"
  exec node --max-old-space-size=256 ops/agent-v2/run-health.mjs "$(date -u +%Y-%m-%d-%H%M)-health"
'
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[$(date -u -Is)] ops-cron-v2: v2 健康轮退出码 $rc(信封语义见 ENVELOPE.md;1=failed/refused/parked 属业务面,留给观察面复盘)"
  exit "$rc"
fi
