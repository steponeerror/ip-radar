#!/usr/bin/env bash
# bootstrap-rrsi.sh — RRSI 盲测演化接线引导(票 #325;#322 执行前置)。
# 干四件事(幂等;可重复跑,每次重同步当前代码):
#   1. clone/更新 dev/rrsi(github.com/google-research/rrsi,Apache 2.0;dev/ 不入 git);
#   2. venv + pip install -e ".[dev]";
#   3. 域接线:ops/agent-v2/bench/rrsi-domain/ → dev/rrsi/domains/ipradar/,
#      并 vendor 开放面 ops/agent + ops/agent-v2 → domains/ipradar/harness/ops/
#      (RRSI 候选=dev/rrsi 的 git worktree,harness 必须在仓内才随候选隔离;
#      harness_path="harness" 单目录=票面「仓根+PATTERNS 限定」的落点);
#   4. 门:RRSI 核心 pytest 绿 + `rrsi.py --domain ipradar smoke` 绿(faux,零网络零花费)。
#
# 注意:重跑会把域重置到当前代码(git 提交 + evolve/ipradar 重指)。若 runs/ipradar/
# 已有真实演化状态(frontier.json 在),拒绝执行,除非 FORCE=1——真实演化期间勿跑。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RRSI_DIR="${RRSI_DIR:-$REPO_ROOT/dev/rrsi}"
DOMAIN_DIR="$REPO_ROOT/ops/agent-v2/bench/rrsi-domain"
RRSI_REPO="${RRSI_REPO:-https://github.com/google-research/rrsi.git}"

log() { printf '[bootstrap-rrsi] %s\n' "$*"; }

# ── 1. clone/更新 ──
if [ ! -d "$RRSI_DIR/.git" ]; then
  log "clone $RRSI_REPO → $RRSI_DIR"
  git clone "$RRSI_REPO" "$RRSI_DIR"
else
  log "更新 $RRSI_DIR(本地提交如有,fetch 不动)"
  git -C "$RRSI_DIR" fetch origin --quiet || log "fetch 失败(离线?用现有检出继续)"
fi

# ── 2. venv + 依赖 ──
if [ ! -x "$RRSI_DIR/.venv/bin/python" ]; then
  log "建 venv"
  python3 -m venv "$RRSI_DIR/.venv"
fi
log "pip install -e .[dev]"
"$RRSI_DIR/.venv/bin/pip" install -q -e "$RRSI_DIR[dev]"
# litellm:四角色 GLM 面(RRSI_LLM_BACKEND=litellm-zai)的运行依赖,上游 [dev] 不含——#322 首跑踩坑补入
"$RRSI_DIR/.venv/bin/pip" install -q litellm

# ── 3. 域接线(vendored 拷贝;node_modules 不带,候选 worktree 各自 npm ci)──
log "同步域目录 + 开放面"
mkdir -p "$RRSI_DIR/domains/ipradar"
rsync -a --delete "$DOMAIN_DIR/" "$RRSI_DIR/domains/ipradar/"
mkdir -p "$RRSI_DIR/domains/ipradar/harness/ops"
# NEEDS.md 考题宇宙输入面同步(bench SCAN 真面读 <repoRoot>/NEEDS.md,tests/bench-round
# 真面例同读;候选禁改——adapter._guardrails 对 evolve/ipradar 做冻结 diff)
cp "$REPO_ROOT/NEEDS.md" "$RRSI_DIR/domains/ipradar/harness/NEEDS.md"
rsync -a --delete --exclude node_modules \
  "$REPO_ROOT/ops/agent/" "$RRSI_DIR/domains/ipradar/harness/ops/agent/"
rsync -a --delete --exclude node_modules \
  "$REPO_ROOT/ops/agent-v2/" "$RRSI_DIR/domains/ipradar/harness/ops/agent-v2/"

if [ -f "$RRSI_DIR/runs/ipradar/frontier.json" ] && [ "${FORCE:-0}" != "1" ]; then
  log "拒绝:runs/ipradar/ 已有真实演化状态(frontier.json)。重接线须 FORCE=1(会重置域到当前代码)。"
  exit 3
fi

log "提交域同步(本地提交,永不 push)"
git -C "$RRSI_DIR" add -A domains/ipradar
if git -C "$RRSI_DIR" diff --cached --quiet; then
  log "域内容无变化,复用 HEAD"
else
  git -C "$RRSI_DIR" -c user.email=rrsi@localhost -c user.name=rrsi \
    commit -q -m "bootstrap: sync ipradar domain + open face ($(date +%F))"
fi
git -C "$RRSI_DIR" worktree prune
# evolve/ipradar 重指到同步提交(分支不被任何 worktree 持有,branch -f 可行);
# 旧候选分支(r{t}{variant})留着,轮机会自行复用/清理。
if git -C "$RRSI_DIR" rev-parse --verify --quiet evolve/ipradar >/dev/null; then
  git -C "$RRSI_DIR" branch -f evolve/ipradar HEAD
else
  git -C "$RRSI_DIR" branch evolve/ipradar HEAD
fi

# ── 4. 门 ──
log "RRSI 核心 pytest"
( cd "$RRSI_DIR" && .venv/bin/python -m pytest tests -q )

log "rrsi.py --domain ipradar smoke(faux;首次含 worktree 内 npm ci,需数分钟)"
( cd "$RRSI_DIR" && .venv/bin/python rrsi.py --domain ipradar smoke )

log "全绿:接线完成。真实首跑见 #322(IPRADAR_BENCH_MODE=real 花钱面,总帽 ¥100)。"
