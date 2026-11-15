#!/usr/bin/env bash
# worktree-prep.sh — 给特性分支 worktree 补齐 gitignored 运行件(2026-11-15 retro 立)
# 用法: scripts/worktree-prep.sh <worktree-dir>
# 背景:托管/手工 worktree 不带主检出的 untracked 运行件;漏拷会造成大片假红:
#   - ops/agent/node_modules 缺 → e2e spawn agent 崩、v2 测试引 v1 模块崩(2026-11-15 两踩)
#   - ops/agent-v2/node_modules 缺 → v2 套件自身崩
# backend/.venv 不拷(几 GB,拷不起);跑后端测试用主检出解释器+cwd 切 worktree backend/
# (见 AGENTS.md worktree 规则)。本脚本幂等:已存在则跳过。
set -euo pipefail

main_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo /home/huxiao/dev/pi-ip-lookup-tool)"
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
echo "worktree 运行件就绪: $wt"
