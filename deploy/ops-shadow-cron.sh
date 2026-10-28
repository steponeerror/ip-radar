#!/usr/bin/env bash
# shadow v2 健康轮 cron(Pi Durable shadow 期;SHADOW-RUNBOOK §双轨)
# 置备 2026-10-28。旧管线照跑生产(ops-cron.sh POST /api/ops/rounds);本脚本
# 在生产容器内以影子世界跑 v2 run-health——零生产写面:DOCS_ROOT/SQLite 全落
# /app/data/ops-shadow(ipradar-data 卷内,随卷持久),auth.json 只读消费生产
# 物化件。错峰 +30min(旧 04/12/20 整点 → 本 30 分)。
#
# 首跑自种影子世界(RUNBOOK §影子世界置备,幂等):从生产 ops 树 cp 一份,
# 清 rounds/ledger/queue(影子从零起卷),保留 precedents/rules/items/
# breaker.json(跨轮输入面)/agent-config.json(模型引用面)。
#
# 退出码透传 v2 信封面(ENVELOPE.md):0=completed;1=failed/refused/parked;
# 2=用法错;3=运行期异常。cron 面不重试——下窗自然重来(同 ops-cron.sh 判例)。
set -u
CONTAINER="${OPS_SHADOW_CONTAINER:-ip-lookup-tool-ipradar-1}"
SHADOW_DIR="${OPS_SHADOW_DATA_DIR:-/app/data/ops-shadow}"

echo "[$(date -u -Is)] ops-shadow: 触发 v2 健康轮"
# 全段在容器内跑(roundId 时钟与生产同源=容器 UTC;env 白名单最小面)
if ! docker exec "$CONTAINER" sh -c '
  set -e
  OPS=/app/data/ops
  SH='"$SHADOW_DIR"'
  # —— 首跑自种(幂等:影子 docs/ops 已在即跳过)——
  if [ ! -d "$SH/docs/ops" ]; then
    mkdir -p "$SH/docs"
    cp -a "$OPS" "$SH/docs/ops"
    rm -rf "$SH/docs/ops/rounds" "$SH/docs/ops/ledger.md" "$SH/docs/ops/queue.md" "$SH/docs/ops/ledger.md.lock"
    echo "[$(date -u -Is)] ops-shadow: 影子世界已自种(precedents/rules/items/breaker 随卷)"
  fi
  # 模型引用从生产 agent-config 现读(桥 _round_env 同源;缺配置=回落 env/缺省链)
  MODEL_HEALTH=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_health\",\"\"))" 2>/dev/null || true)
  MODEL_DISCOVER=$(python3 -c "import json;print(json.load(open(\"$OPS/agent-config.json\")).get(\"model_discover\",\"\"))" 2>/dev/null || true)
  cd /app
  export DOCS_ROOT="$SH/docs"
  export OPS_AUTH="$OPS/auth.json"          # 生产物化凭证件,只读消费
  export LANG=C.UTF-8                        # C4 判例:bash 面 locale 确定性(CJK %q)
  [ -n "$MODEL_HEALTH" ] && export OPS_MODEL_HEALTH="$MODEL_HEALTH"
  [ -n "$MODEL_DISCOVER" ] && export OPS_MODEL_DISCOVER="$MODEL_DISCOVER"
  exec node --max-old-space-size=256 ops/agent-v2/run-health.mjs "$(date +%Y-%m-%d-%H%M)-health"
'; then
  rc=$?
  echo "[$(date -u -Is)] ops-shadow: v2 健康轮退出码 $rc(信封语义见 ENVELOPE.md;1=failed/refused/parked 属业务面,留给观察面复盘)"
  exit "$rc"
fi
