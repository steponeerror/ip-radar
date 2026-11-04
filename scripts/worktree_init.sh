#!/usr/bin/env bash
# worktree_init.sh — 全新 worktree 一键接线本地开发环境(retro P1-3 固化,2026-11-03)。
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
# 在用登记表(#299 清单锁,2026-11-04):接线成功后把 {path, branch, started_at,
# owner} 登记进主检出 .worktrees/registry.json(本地件,.gitignore 的 .worktrees/
# 兜底不入 git)。为什么:2026-10 起多次发生集成分支 worktree 被并行会话当草稿扫掉/
# 抢占(#299 判例)——先登记后用,把「我以为没人用」变成跨会话可查的事实;owner 非
# 本会话的既有登记在接线开始前即拒(--force 覆盖)。owner=$PI_SESSION_ID(有则),
# 否则 hostname:PID——后者每次运行必变,无 PI_SESSION_ID 的环境重跑会被自己的旧
# 登记拦下(--force 过;--release 可收尾)。
# 自验(2026-11-04):登记流 E2E 于临时 scratch worktree 实跑——全量接线登记/同会话
# 重入放行/外会话接线前拒/--force 翻 owner/无 PI_SESSION_ID 记 hostname:PID/坏表
# 拒盲写/--list/--release(含目标目录已删的按路径释放);跑后零残留(worktree+分支+表全清)。
set -euo pipefail

usage() {
  cat <<'EOF'
用法: scripts/worktree_init.sh [TARGET_DIR] [--no-frontend] [--no-backend] [--force]
       scripts/worktree_init.sh --list
       scripts/worktree_init.sh --release <path>
  TARGET_DIR     目标 worktree 根目录,默认当前目录。必须在 worktree 根上调用
                 (子目录会报错);脚本只写 TARGET_DIR 内的路径
  --no-frontend  跳过 frontend 接线(npm ci)
  --no-backend   跳过 backend 接线(venv + pip install)
  --force        目标已登记且 owner 非本会话时强制接线并改写登记
  --list         打印在用 worktree 登记表(主检出 .worktrees/registry.json)
  --release <path> 从登记表移除一条(收尾清理;path 用登记时的绝对路径,
                 目标目录已删也能按路径释放)

步骤:
  1. backend:  python3 -m venv backend/.venv(已存在跳过)
               + pip install -r backend/requirements-dev.txt(重复跑 no-op)
  2. frontend: cd frontend && npm ci(node_modules 已存在跳过;
               强制重装:rm -rf frontend/node_modules 后再跑)
  3. docs:     主检出有嵌套 docs/ 而目标没有 → 符号链接 docs -> 主检出 docs
               (让 test_precedent_schema.py 真跑而非跳过)
  4. registry: 接线全部成功后登记在用(主检出 .worktrees/registry.json,
               #299 清单锁);owner 非本会话的既有登记在接线开始前拒绝

跑完后的聚焦门(手动执行验证):
  cd <TARGET>/backend  && .venv/bin/python -m pytest tests/test_ops_config.py -q
  cd <TARGET>/frontend && npm test -- src/__tests__/api.test.ts
EOF
}

TARGET=
MODE=init
RELEASE_PATH=
NO_FRONTEND=0
NO_BACKEND=0
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-frontend) NO_FRONTEND=1; shift ;;
    --no-backend)  NO_BACKEND=1; shift ;;
    --force)       FORCE=1; shift ;;
    --list)        MODE=list; shift ;;
    --release)     MODE=release
                   [ $# -ge 2 ] || { echo "worktree_init: --release 需要一个路径参数" >&2; exit 2; }
                   RELEASE_PATH=$2; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *) if [ "$MODE" != init ] || [ -n "$TARGET" ]; then usage >&2; exit 2; fi
       TARGET=$1; shift ;;
  esac
done
[ -n "$TARGET" ] || TARGET=$PWD

die() { echo "worktree_init: 错误:$*" >&2; exit 1; }

# 主检出定位(供 docs 链接防自指 2026-11-03 事故判例 + 登记表落位;dir 须在 git 工作树内)
main_checkout_of() {
  local common
  common=$(git -C "$1" rev-parse --git-common-dir)
  case "$common" in /*) ;; *) common="$1/$common" ;; esac
  (cd "$(dirname "$common")" && pwd)
}

# 登记表读写(json 用 python3,先例 monthly_eval.sh write_leg_status):
#   check <target> <owner>          被外会话占用→stdout "owner|started_at" rc=1;
#                                   表损坏/结构不对 rc=2(拒绝盲写,证据不灭失)
#   set <target> <branch> <owner>   写登记(os.replace 原子替换,防并行会话撕裂读)
#   del <target>                     移除登记(不在表 rc=1);表空连文件删,不留空壳
#   list                             逐行 path/branch/owner/started_at(表空提示)
registry_ctl() {
  python3 - "$@" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

reg, op = Path(sys.argv[1]), sys.argv[2]

def load():
    if not reg.exists():
        return {"schema": "worktree-registry/1", "entries": {}}
    try:
        doc = json.loads(reg.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"登记表损坏,拒绝盲写({reg}):{exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), dict):
        print(f"登记表结构不对,拒绝盲写({reg})", file=sys.stderr)
        sys.exit(2)
    return doc

def save(doc):
    tmp = reg.with_name(reg.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, reg)

if op == "check":
    e = load()["entries"].get(sys.argv[3])
    if e and e.get("owner") != sys.argv[4]:
        print(f"{e.get('owner', '?')}|{e.get('started_at', '?')}")
        sys.exit(1)
elif op == "set":
    doc = load()
    doc["entries"][sys.argv[3]] = {
        "branch": sys.argv[4],
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "owner": sys.argv[5],
    }
    reg.parent.mkdir(parents=True, exist_ok=True)
    save(doc)
elif op == "del":
    doc = load()
    if sys.argv[3] not in doc["entries"]:
        print(f"不在登记表:{sys.argv[3]}", file=sys.stderr)
        sys.exit(1)
    del doc["entries"][sys.argv[3]]
    if doc["entries"]:
        save(doc)
    else:
        reg.unlink()  # 表空连文件删,不留空壳
elif op == "list":
    entries = load()["entries"]
    if not entries:
        print("(登记表空)")
    for path in sorted(entries):
        e = entries[path]
        print(f"{path}\t{e.get('branch', '?')}\t{e.get('owner', '?')}\t{e.get('started_at', '?')}")
else:
    print(f"未知子命令:{op}", file=sys.stderr)
    sys.exit(2)
PYEOF
}

# 本会话身份:PI_SESSION_ID 有则用之;否则 hostname:PID(跨次必变,见头注释)
if [ -n "${PI_SESSION_ID:-}" ]; then OWNER=$PI_SESSION_ID; else OWNER="$(hostname):$$"; fi

# --- --list / --release:不接线,只动登记表;在任何仓内目录可调用 ---
if [ "$MODE" != init ]; then
  git rev-parse --git-common-dir >/dev/null 2>&1 \
    || die "--list/--release 须在仓库内调用(靠 git 定位主检出)"
  REGISTRY=$(main_checkout_of "$PWD")/.worktrees/registry.json
  if [ "$MODE" = list ]; then
    registry_ctl "$REGISTRY" list
    exit 0
  fi
  # release:目标目录可能已被 git worktree remove 删掉 → 存在则 cd 归一,
  # 不存在则 realpath 归一,两种部与登记键同形(绝对物理路径)
  if [ -d "$RELEASE_PATH" ]; then RELEASE_PATH=$(cd "$RELEASE_PATH" && pwd); fi
  RELEASE_PATH=$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$RELEASE_PATH")
  registry_ctl "$REGISTRY" del "$RELEASE_PATH"
  echo "==> [registry] 已释放:$RELEASE_PATH"
  exit 0
fi

# --- 目标校验:必须是 git worktree 的根目录 ---
TARGET=$(cd "$TARGET" && pwd)   # 归一(尾斜杠/相对路径形态,评审 P2-1)
# 主检出定位(供 docs 链接防自指 2026-11-03 事故判例 + 登记表落位)
MAIN_CHECKOUT=$(main_checkout_of "$TARGET")
# 防自指(2026-11-03 事故判例):目标是主检出时,后续 docs 链接会指向自身,
# 把主检出的真 docs 嵌套仓变成自环链接 → 在任何接线动作之前拒绝
if [ "$TARGET" = "$MAIN_CHECKOUT" ]; then
  die "目标就是主检出,本脚本面向新建 worktree;主检出无需接线"
fi
git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "$TARGET 不是 git 工作树(先 git worktree add 再来)"
TOP=$(git -C "$TARGET" rev-parse --show-toplevel)
[ "$TOP" = "$TARGET" ] || die "请在 worktree 根目录调用(当前 toplevel:$TOP)"
echo "==> 目标 worktree:$TARGET"
REGISTRY=$MAIN_CHECKOUT/.worktrees/registry.json

# --- 在用检查(#299 清单锁):外会话占用在接线开始前就拒,省下 venv/npm 的几分钟 ---
if [ "$FORCE" -eq 0 ]; then
  check_rc=0; foreign=$(registry_ctl "$REGISTRY" check "$TARGET" "$OWNER") || check_rc=$?
  case "$check_rc" in
    0) ;;
    1) die "$TARGET 已被其他会话占用(owner=${foreign%%|*},登记于 ${foreign#*|})。确认对方已收尾后 --force 覆盖,或 scripts/worktree_init.sh --release $TARGET" ;;
    2) die "登记表异常,先人工核 $REGISTRY 再来" ;;
    *) die "登记表检查失败(rc=$check_rc)" ;;
  esac
fi

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
if [ -e "$TARGET/docs" ] || [ -L "$TARGET/docs" ]; then
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

# 接线全部成功才登记(#299 清单锁):中途失败 set -e 早退,不会留下假登记
BRANCH=$(git -C "$TARGET" rev-parse --abbrev-ref HEAD)
registry_ctl "$REGISTRY" set "$TARGET" "$BRANCH" "$OWNER"
echo "==> [registry] 已登记在用:owner=$OWNER,branch=$BRANCH"

echo "==> 完成。聚焦门验证(复制执行):"
echo "    cd $TARGET/backend  && .venv/bin/python -m pytest tests/test_ops_config.py -q"
echo "    cd $TARGET/frontend && npm test -- src/__tests__/api.test.ts"
echo "    收尾清理:scripts/worktree_init.sh --release $TARGET"
