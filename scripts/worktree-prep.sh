#!/usr/bin/env bash
# worktree-prep.sh — 给特性分支 worktree 补齐 gitignored 运行件(2026-11-15 retro 立)
# 用法: scripts/worktree-prep.sh <worktree-dir>
# 背景:托管/手工 worktree 不带主检出的 untracked 运行件;漏拷会造成大片假红:
#   - ops/agent/node_modules 缺 → e2e spawn agent 崩、v2 测试引 v1 模块崩(2026-11-15 两踩)
#   - ops/agent-v2/node_modules 缺 → v2 套件自身崩
# backend/.venv 不拷(几 GB,拷不起);跑后端测试用主检出解释器+cwd 切 worktree backend/
# (见 AGENTS.md worktree 规则)。本脚本幂等:已存在则跳过。
#
# 主检出定位:用 --git-common-dir(worktree 里它指向主检出 .git,主检出里等于 --git-dir)
# 上溯主检出根——**不能**用 --show-toplevel:脚本随仓提交,worktree 里也有一份,
# 从 worktree 自调时 show-toplevel 解析成 worktree 自身,主检出件全被误判 SKIP
# (2026-11-15 setup-dedup worker 实锤:两处 node_modules 打 SKIP → e2e 假红)。
set -euo pipefail

self_dir="$(cd "$(dirname "$0")" && pwd)"
common_dir="$(git -C "$self_dir" rev-parse --git-common-dir 2>/dev/null || true)"
case "$common_dir" in
  /*) : ;;
  *) common_dir="$self_dir/$common_dir" ;;  # 相对路径(主检出里 .git 即字面量)
esac
main_root="$(cd "$(dirname "$common_dir")" && pwd)"
wt="${1:?用法: scripts/worktree-prep.sh <worktree-dir>}"

[ -d "$wt" ] || { echo "worktree 目录不存在: $wt" >&2; exit 2; }

for rel in ops/agent/node_modules ops/agent-v2/node_modules; do
  src="$main_root/$rel"
  dst="$wt/$rel"
  if [ ! -d "$src" ]; then
    echo "SKIP(主检出也没有): $rel"
  elif [ -d "$dst" ]; then
    echo "OK(已在): $rel"
  else
    cp -r "$src" "$dst"
    echo "COPIED: $rel -> $dst"
  fi
done
echo "worktree 运行件就绪: $wt(主检出: $main_root)"
