#!/usr/bin/env bash
# v2 生产发现轮 cron(#367 定频;SHADOW-RUNBOOK §已切流;2026-11-20 用户裁 Q3 每日一跑)。
# #364 切流律同款(ops-cron-v2.sh 同律,docker exec 容器直跑 v2 面接生产世界:
# DOCS_ROOT=ops 根的父=生产 ops 树 /app/data/ops 的父,台账/queue/轮目录/precedents
# 全生产写;轮 id 取容器 UTC 墙钟;SQLite --db 缺省随 DOCS_ROOT 落
# /app/data/ops/agent-v2.sqlite)。与健康轮件的关键差异:
# - real 面显式 --model:run-discover 无缺省 resolve(用法错 exit 2,不带病跑),
#   模型引用从生产 agent-config.json model_discover 现读注入 OPS_MODEL_DISCOVER +
#   --model 双面;缺配置=明确跳过留痕 exit 0 下窗自愈(同 auth.json 缺件判例——
#   修复属部署动作:PUT /api/ops/agent-config 配 model_discover)。
# - 月帽独立:发现轮月帽键 OPS_DISCOVER_MONTHLY_CAP_CNY(缺省 ¥20,#367 票面;
#   ≠健康轮共享 OPS_PIPELINE_MONTHLY_CAP_CNY ¥30)。超帽拒启在 run-discover 准入面
#   (admitRound→信封 budget_monthly exit 1+台账拒跑留痕行),cron 面透传不重裁;
#   容器 env(compose override)可覆写该键(docker exec 继承容器 env,白名单不摘它)。
# - 错峰:服务器本地每日 06:00(健康轮窗=04/12/20 起约 35 分钟禁并发,#365 评审
#   P2-2;06:00 距最近健康窗(04:00+35min)窗尾 ≥85 分钟,零并发面)。
#
# env 面逐键白名单(#364 裁定同判例;「逐键白名单,不笼统同环境」):
#   设:DOCS_ROOT/OPS_AUTH/OPS_EVAL_PY/OPS_DATA_DIR/PI_CODING_AGENT_DIR/LANG
#       /OPS_MODEL_DISCOVER(agent-config 现读;发现轮面不注 OPS_MODEL_HEALTH);
#   unset:IP_RADAR_ADMIN_PASSWORD/IP_RADAR_API_JWT_SECRET(管理密钥,C4 判例);
#   继承不摘:GH_TOKEN/IP_RADAR_ALERT_URLS(出口契约员)+PATH/HOME 等运行必需面;
#   不设:OPS_SWEEP_DRY_RUN(finding 出口生产语义真开,#184)。
#
# 退出码透传 v2 信封面(ENVELOPE.md):0=completed;1=failed/refused/parked(月帽拒启
# budget_monthly 同码,属业务面留给观察面复盘);2=用法错;3=运行期异常。cron 面不
# 重试——次日窗自然重来(同 ops-cron.sh 判例)。
set -u
CONTAINER="${OPS_V2_CONTAINER:-ip-lookup-tool-ipradar-1}"
OPS_ROOT="${OPS_V2_OPS_ROOT:-/app/data/ops}"   # 测试/运维 override;缺省生产 ops 树
APP_ROOT="${OPS_V2_APP_ROOT:-/app}"            # 同上;容器内仓根(run-discover.mjs 的 cwd)
# 传值经 printf %q 转义后拼入内层 sh 源码(裸拼不手写引号;ops-cron-v2.sh 同款判例)
OPS_Q=$(printf '%q' "$OPS_ROOT")
APP_Q=$(printf '%q' "$APP_ROOT")

echo "[$(date -u -Is)] ops-cron-v2: 触发 v2 生产发现轮"
# rc 透传形:先跑后取 $?(ops-cron-v2.sh 同款;`if ! docker exec` 取反分支里 $? 恒 0)
docker exec "$CONTAINER" sh -c '
  set -e
  OPS='"$OPS_Q"'
  APP='"$APP_Q"'
  # —— 凭证预检(缺件不硬跑,明确跳过留痕 exit 0,下窗自愈;旧 ops-cron 409 判例直跑形)——
  if [ ! -f "$OPS/auth.json" ]; then
    echo "[$(date -u -Is)] ops-cron-v2: 生产 auth.json 未物化,本轮跳过,下窗自愈"
    exit 0
  fi
  # 模型引用从生产 agent-config 现读(v1 桥 _round_env 同源;发现轮 real 面须显式
  # --model,缺配置=不带病跑(裸跑落用法错 exit 2),明确跳过留痕 exit 0 下窗自愈)
  MODEL_DISCOVER=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_discover\",\"\"))" 2>/dev/null || true)
  if [ -z "$MODEL_DISCOVER" ]; then
    echo "[$(date -u -Is)] ops-cron-v2: agent-config 缺 model_discover,发现轮明确跳过,下窗自愈"
    exit 0
  fi
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
  export OPS_MODEL_DISCOVER="$MODEL_DISCOVER"
  exec node --max-old-space-size=256 ops/agent-v2/run-discover.mjs "$(date -u +%Y-%m-%d-%H%M)-discover" --model "$MODEL_DISCOVER"
'
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[$(date -u -Is)] ops-cron-v2: v2 发现轮退出码 $rc(信封语义见 ENVELOPE.md;1=failed/refused/parked 属业务面——月帽拒启 budget_monthly 亦此码,留给观察面复盘)"
  exit "$rc"
fi
