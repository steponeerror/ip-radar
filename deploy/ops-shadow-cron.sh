#!/usr/bin/env bash
# shadow v2 健康轮 cron(Pi Durable shadow 期;SHADOW-RUNBOOK §双轨)
# 置备 2026-10-28。旧管线照跑生产(ops-cron.sh POST /api/ops/rounds);本脚本
# 在生产容器内以影子世界跑 v2 run-health——零生产写面:DOCS_ROOT/SQLite 全落
# /app/data/ops-shadow(ipradar-data 卷内,随卷持久),auth.json 只读消费生产
# 物化件。错峰 +40min(旧 04/12/20 整点 → 本 40 分;旧轮墙钟帽 1800s 恰 30 分,
# +30 仍可能踩旧轮尾巴,退到 40)。
#
# 首跑自种影子世界(RUNBOOK §影子世界置备,幂等:终位 $SH/docs/ops 已在即
# 整段跳过):从生产 ops 树 cp 一份,清轮次状态与密钥面(rounds/ ledger.md
# ledger.md.lock queue.md auth.json web-search.json agent-config.json——影子
# 从零起卷且种子零密钥:凭证经 OPS_AUTH 只读消费生产件,模型引用每轮从生产
# agent-config 现读注入),保留 precedents/rules/items/breaker.json(跨轮输入
# 面)。种入 docs/ops.tmp 再 mv 终位(同卷 rename 原子,中断不留半树)。
#
# 影子轮零外发:OPS_SWEEP_DRY_RUN=1(finding-exit.mjs 出口开关,=1 只记
# cmd/payload)+ 摘除密钥 env(见 C4 判例注释)——模型进程拿不到出口凭证。
#
# 退出码透传 v2 信封面(ENVELOPE.md):0=completed;1=failed/refused/parked;
# 2=用法错;3=运行期异常。cron 面不重试——下窗自然重来(同 ops-cron.sh 判例)。
set -u
CONTAINER="${OPS_SHADOW_CONTAINER:-ip-lookup-tool-ipradar-1}"
SHADOW_DIR="${OPS_SHADOW_DATA_DIR:-/app/data/ops-shadow}"
# SH 传值经 printf %q 转义后拼入内层 sh 源码(裸拼,不再手写引号):override 值
# 带空格/引号/元字符时 %q 产出即合法 sh 字面量,不破内层脚本。
SHADOW_Q=$(printf '%q' "$SHADOW_DIR")

echo "[$(date -u -Is)] ops-shadow: 触发 v2 健康轮"
# rc 透传形:先跑后取 $?;`if ! docker exec;then rc=$?` 的取反分支里 $? 恒 0,
# 拿不到信封退出码(评审轮 1 修正)。
docker exec "$CONTAINER" sh -c '
  set -e
  OPS=/app/data/ops
  SH='"$SHADOW_Q"'
  # —— 凭证预检(旧 ops-cron 409 跳过判例:缺件不硬跑,明确跳过 exit 0,下窗自愈)——
  if [ ! -f "$OPS/auth.json" ]; then
    echo "[$(date -u -Is)] ops-shadow: 生产 auth.json 未物化,本轮跳过,下窗自愈"
    exit 0
  fi
  # —— 首跑自种(幂等:护栏只认终位 $SH/docs/ops;tmp 残留先清防 cp 嵌套)——
  if [ ! -d "$SH/docs/ops" ]; then
    mkdir -p "$SH/docs"
    rm -rf "$SH/docs/ops.tmp"
    cp -a "$OPS" "$SH/docs/ops.tmp"
    rm -rf "$SH/docs/ops.tmp/rounds" "$SH/docs/ops.tmp/ledger.md" \
           "$SH/docs/ops.tmp/ledger.md.lock" "$SH/docs/ops.tmp/queue.md" \
           "$SH/docs/ops.tmp/auth.json" "$SH/docs/ops.tmp/web-search.json" \
           "$SH/docs/ops.tmp/agent-config.json"
    mv "$SH/docs/ops.tmp" "$SH/docs/ops"
    echo "[$(date -u -Is)] ops-shadow: 影子世界已自种(precedents/rules/items/breaker 随卷,轮次状态与密钥面剔除)"
  fi
  # 模型引用从生产 agent-config 现读(桥 _round_env 同源;缺配置=回落 env/缺省链)
  MODEL_HEALTH=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_health\",\"\"))" 2>/dev/null || true)
  MODEL_DISCOVER=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_discover\",\"\"))" 2>/dev/null || true)
  cd /app
  export DOCS_ROOT="$SH/docs"
  export OPS_AUTH="$OPS/auth.json"          # 生产物化凭证件,只读消费
  # 桥 _round_env 同源两键:OPS_EVAL_PY/OPS_DATA_DIR 是 shared.mjs 模块加载期
  # 常量,缺省指开发机路径(venv/本地 data),容器内不物化必死 PROBE
  export OPS_EVAL_PY="$(command -v python3)" OPS_DATA_DIR=/app/data
  export OPS_SWEEP_DRY_RUN=1                # 影子轮零外发:=1 只记 cmd/payload 零真发
  export LANG=C.UTF-8                        # C4 判例:bash 面 locale 确定性(CJK %q)
  # 密钥摘除(C4 判例:docker exec 继承容器全量 env,管理密钥不带进模型进程;
  # GH_TOKEN 一并摘除=gh 出口双保险,与 OPS_SWEEP_DRY_RUN 成纵深两层)
  unset IP_RADAR_ADMIN_PASSWORD IP_RADAR_API_JWT_SECRET IP_RADAR_ALERT_URLS GH_TOKEN
  [ -n "$MODEL_HEALTH" ] && export OPS_MODEL_HEALTH="$MODEL_HEALTH"
  [ -n "$MODEL_DISCOVER" ] && export OPS_MODEL_DISCOVER="$MODEL_DISCOVER"
  exec node --max-old-space-size=256 ops/agent-v2/run-health.mjs "$(date +%Y-%m-%d-%H%M)-health"
'
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[$(date -u -Is)] ops-shadow: v2 健康轮退出码 $rc(信封语义见 ENVELOPE.md;1=failed/refused/parked 属业务面,留给观察面复盘)"
  exit "$rc"
fi
