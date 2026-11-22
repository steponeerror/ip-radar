#!/usr/bin/env bash
# worktree-prep.sh — 给特性分支 worktree 补齐 gitignored 运行件(2026-11-15 retro 立)
# 用法: scripts/worktree-prep.sh [--overwrite] <worktree-dir>
# 背景:托管/手工 worktree 不带主检出的 untracked 运行件;漏拷会造成大片假红:
#   - ops/agent/node_modules 缺 → e2e spawn agent 崩、v2 测试引 v1 模块崩(2026-11-15 两踩)
#   - ops/agent-v2/node_modules 缺 → v2 套件自身崩
#   - frontend/node_modules 缺 → vitest/tsc 跑不了(#420 起纳入拷贝家族)
# backend/.venv 不拷(几 GB,拷不起);跑后端测试用主检出解释器+cwd 切 worktree backend/
# (见 AGENTS.md worktree 规则)。本脚本幂等:已存在则跳过。
# --overwrite(2026-11-17 #356 delta P2-③):已在件先删再拷=用主检出副本覆写。防候选
# node_modules 投毒:演化循环护栏在候选树内跑,而 node_modules 是 gitignored、
# diff 闸两腿看不见它——驱动器在护栏块前用 --overwrite 重跑本脚本把运行件打回主检出态。
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
wt=""
overwrite=0
for a in "$@"; do
  case "$a" in
    --overwrite) overwrite=1 ;;
    *) wt="$a" ;;
  esac
done
[ -n "$wt" ] || { echo "用法: scripts/worktree-prep.sh [--overwrite] <worktree-dir>" >&2; exit 2; }

[ -d "$wt" ] || { echo "worktree 目录不存在: $wt" >&2; exit 2; }

for rel in ops/agent/node_modules ops/agent-v2/node_modules frontend/node_modules; do
  src="$main_root/$rel"
  dst="$wt/$rel"
  if [ ! -d "$src" ]; then
    echo "SKIP(主检出也没有): $rel"
  elif [ "$overwrite" = 1 ] && [ -d "$dst" ]; then
    rm -rf "$dst"
    cp -r "$src" "$dst"
    echo "OVERWRITTEN: $rel -> $dst"
  elif [ -d "$dst" ]; then
    echo "OK(已在): $rel"
  else
    cp -r "$src" "$dst"
    echo "COPIED: $rel -> $dst"
  fi
done
echo "worktree 运行件就绪: $wt(主检出: $main_root)"
