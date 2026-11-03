#!/usr/bin/env bash
# worktree-init.sh — 全新 worktree 一键接线本地开发环境(retro P1-3 固化,2026-11-03)。
# 为什么:git worktree 只带 tracked 文件,本地开发要的未跟踪件全缺。2026-11-03 在
# 草稿 worktree rb-b-scratch(基点 dc73766c)实测缺件清单:
#   - backend/.venv:缺(README「Tests」节正路 = python3 -m venv + pip install
#     -r requirements-dev.txt;实测 pip 缓存热 ~2.7s)
#   - frontend/node_modules:缺(npm ci,实测缓存热 ~14s)
#   - docs/:嵌套私有仓、仅主检出有。缺失时 backend/tests/test_precedent_schema.py
#     模块级跳过(其文件头 2026-10-19 T1 评审 Info-① 裁决原文:「无仓即跳过,
#     本地/worktree 符号链接下守真章」)→ 本脚本从主检出符号链接,链接建在
#     目标 worktree 内,判例库测试从跳过转为真跑
#   - assets/:不缺,无需接线。eval 测试全用 tmp_path 自造资产根
#     (tests/eval/test_eval_gate_cli.py:171 等,2026-11-03 rg 实证)
#   - .env:tests/conftest.py 无 load_dotenv,不需要
# 边界:脚本只写 TARGET 内路径;pip/npm 用户级缓存(~/.cache/pip、~/.npm)是包
# 管理器自身行为,不算越界。幂等:venv/node_modules 已存在即跳过;pip install
# 重复跑是 no-op(Requirement already satisfied)。
# 自验(2026-11-03):bash -n;rb-b-scratch 全新态跑通 + 双聚焦门绿;重复跑幂等跳过。
set -euo pipefail

usage() {
  cat <<'EOF'
用法: scripts/worktree-init.sh [TARGET_DIR] [--no-frontend] [--no-backend]
  TARGET_DIR     目标 worktree 根目录,默认当前目录。必须在 worktree 根上调用
                 (子目录会报错);脚本只写 TARGET_DIR 内的路径
  --no-frontend  跳过 frontend 接线(npm ci)
  --no-backend   跳过 backend 接线(venv + pip install)

步骤:
  1. backend:  python3 -m venv backend/.venv(已存在跳过)
               + pip install -r backend/requirements-dev.txt(重复跑 no-op)
  2. frontend: cd frontend && npm ci(node_modules 已存在跳过;
               强制重装:rm -rf frontend/node_modules 后再跑)
  3. docs:     主检出有嵌套 docs/ 而目标没有 → 符号链接 docs -> 主检出 docs
               (让 test_precedent_schema.py 真跑而非跳过)

跑完后的聚焦门(手动执行验证):
  cd <TARGET>/backend  && .venv/bin/python -m pytest tests/test_ops_config.py -q
  cd <TARGET>/frontend && npm test -- src/__tests__/api.test.ts
EOF
}

TARGET=
NO_FRONTEND=0
NO_BACKEND=0
for arg in "$@"; do
  case "$arg" in
    --no-frontend) NO_FRONTEND=1 ;;
    --no-backend)  NO_BACKEND=1 ;;
    -h|--help)     usage; exit 0 ;;
    *) if [ -n "$TARGET" ]; then usage >&2; exit 2; fi; TARGET=$arg ;;
  esac
done
[ -n "$TARGET" ] || TARGET=$PWD

die() { echo "worktree-init: 错误:$*" >&2; exit 1; }

# --- 目标校验:必须是 git worktree 的根目录 ---
git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "$TARGET 不是 git 工作树(先 git worktree add 再来)"
TOP=$(git -C "$TARGET" rev-parse --show-toplevel)
[ "$TOP" = "$TARGET" ] || die "请在 worktree 根目录调用(当前 toplevel:$TOP)"
echo "==> 目标 worktree:$TARGET"

if [ "$NO_BACKEND" -eq 0 ]; then
  echo "==> [backend] 接线 .venv + 依赖"
  if [ -x "$TARGET/backend/.venv/bin/python" ]; then
    echo "    backend/.venv 已存在,跳过创建(重建:rm -rf backend/.venv 后再跑)"
  else
    (cd "$TARGET/backend" && python3 -m venv .venv)
    echo "    已创建 backend/.venv"
  fi
  # 重复跑 no-op:依赖已满足时 pip 秒回,顺带保持与 requirements 漂移同步
  "$TARGET/backend/.venv/bin/pip" install -q -r "$TARGET/backend/requirements-dev.txt"
  echo "    pip install -r requirements-dev.txt 完成"
else
  echo "==> [backend] --no-backend,跳过"
fi

if [ "$NO_FRONTEND" -eq 0 ]; then
  echo "==> [frontend] 接线 node_modules"
  if [ -d "$TARGET/frontend/node_modules" ]; then
    echo "    frontend/node_modules 已存在,跳过 npm ci(强制重装:rm -rf 后再跑)"
  else
    (cd "$TARGET/frontend" && npm ci --no-audit --no-fund)
    echo "    npm ci 完成"
  fi
else
  echo "==> [frontend] --no-frontend,跳过"
fi

echo "==> [docs] 判例库符号链接(可选件)"
if [ -e "$TARGET/docs" ]; then
  echo "    目标已有 docs/,跳过"
else
  COMMON=$(git -C "$TARGET" rev-parse --git-common-dir)
  case "$COMMON" in /*) ;; *) COMMON="$TARGET/$COMMON" ;; esac
  MAIN=$(cd "$(dirname "$COMMON")" && pwd)
  if [ -d "$MAIN/docs" ]; then
    ln -s "$MAIN/docs" "$TARGET/docs"
    echo "    已链接 docs -> $MAIN/docs(test_precedent_schema.py 将真跑)"
  else
    echo "    主检出($MAIN)无 docs/,跳过(test_precedent_schema.py 将跳过)"
  fi
fi

echo "==> 完成。聚焦门验证(复制执行):"
echo "    cd $TARGET/backend  && .venv/bin/python -m pytest tests/test_ops_config.py -q"
echo "    cd $TARGET/frontend && npm test -- src/__tests__/api.test.ts"
