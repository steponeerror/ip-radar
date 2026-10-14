#!/usr/bin/env bash
# 新源物化编排(Q18,spec 2026-10-12-eval-loop-hardening-design.md §3.2):
# fetch → rebuild → 生效性哨兵 20/20 →(提示)跑 --gate → epoch 清理/回滚指引。
# 只编排既有命令,不发明新数据通路,引擎零改动:
#   - fetch/rebuild:离线驱动源自身 download()+rebuild()(_tasks._run_task
#     同款两条调用;rebuild 是唯一写路径,UpdateManager 队列是进程内机制,
#     离线物化在独立进程走同一通路 —— monthly_eval.sh 驱动 python 同款形态)。
#   - 哨兵:python -m ipdb._eval --sentinel <source>(T2 sentinel.py 的 CLI
#     接线,同分支 Task 9 落地;本脚本只引用,验证范围按计划=语法+dry-run)。
#   - gate 只提示不代跑(测量建言,人裁终局);epoch 清理/回滚只出指引行,
#     本脚本不自动删除任何文件(旧物化产物保留至 gate 过后再清)。
# 自验:bash -n(语法)+ --dry-run(打印将执行的命令不执行,monthly_eval.sh
# 同款);命令序列可用 stub PATH(假 python3 恒 0/定向失败)非 dry-run 走查。
# 同批多候选:逐个串行跑本脚本(后者舰队含先放行者,spec §3.2)。
set -euo pipefail

usage() {
  echo "用法: scripts/materialize_source.sh <source> [--dry-run]"
  echo "  <source>   源名(backend/ipdb/_sources/ 注册名)"
  echo "  --dry-run  只打印将执行的命令,不执行"
  echo "  数据目录默认 <repo>/backend/data(_registry.DATA_DIR 同缺省),"
  echo "  环境变量 IP_RADAR_DATA_DIR 可覆盖;解释器默认 python3,"
  echo "  IP_RADAR_PYTHON 可覆盖(worktree 内用主仓 venv 绝对路径)"
}

DRY_RUN=0
SOURCE=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "未知参数: $a" >&2; usage >&2; exit 2 ;;
    *)
      if [ -n "$SOURCE" ]; then
        echo "只需一个 <source>(当前已给 $SOURCE 与 $a)" >&2; exit 2
      fi
      SOURCE="$a" ;;
  esac
done
if [ -z "$SOURCE" ]; then
  usage >&2; exit 2
fi

REPO=$(git rev-parse --show-toplevel)
PY="${IP_RADAR_PYTHON:-python3}"
# 绝对化:注册表缺省 = <repo>/backend/data(_registry.py DATA_DIR),显式导出
# 使 driver 与哨兵两个子进程看到同一存储(epoch/ptr 跨进程即存储契约)。
DATA_DIR="$(realpath -m "${IP_RADAR_DATA_DIR:-$REPO/backend/data}")"

echo "repo:   $REPO"
echo "source: $SOURCE"
echo "data:   $DATA_DIR"
echo "python: $PY (dry-run: $DRY_RUN)"

# 并发守卫(提示级,无跨进程锁可查):DATA_DIR 正被运行中服务使用时,离线
# rebuild 与服务侧同源 rebuild 会竞态 —— next_epoch 扫描分同号 epoch,提交
# 后 prune 旧 epoch 互删对方目录(_sources/_lmdb.py)→ 此时改走服务入口。
echo
echo "注意: 若 $DATA_DIR 正被运行中服务使用,改走服务入口(经 UpdateManager"
echo "      队列串行):POST /api/sources/$SOURCE/update,勿与本脚本并发。"

# ── 1/3 fetch + rebuild(离线驱动,唯一写路径)──
# driver 内联 -c:未知源具名列出全部注册名防 typo;download 原子发布原始
# 文件,rebuild 新 epoch + ptr swap(与 _tasks._run_task 的两次调用逐字同源)。
DRIVER='
import sys
from ipdb import _registry as reg
name = sys.argv[1]
src = next((x for x in reg._sources if x.name == name), None)
if src is None:
    sys.exit("unknown source: " + name + " (known: "
             + ", ".join(sorted(x.name for x in reg._sources)) + ")")
print("source: " + name
      + " category=" + str(getattr(src, "category", "?"))
      + " raw=" + str(src._path))
src.download()
print("fetched: " + str(src._path))
n = src.rebuild()
print("rebuild returned: " + str(n) + " (语义随基类而异, 见 add-intel-source skill Phase 4)")
'
echo
echo "==> 1/3 fetch+rebuild: $PY -c <driver> $SOURCE   # download()+rebuild() 经 ipdb._registry"
if [ "$DRY_RUN" != 1 ]; then
  ( cd "$REPO/backend" && IP_RADAR_DATA_DIR="$DATA_DIR" "$PY" -c "$DRIVER" "$SOURCE" )
fi

# ── 2/3 生效性哨兵(spec §3.2「哨兵 20/20」;T9 CLI,geo_asn 标量轴=N/A,
# 键集口径 coverage_check 由 CLI 分派)。失败不进 set -e 直杀 —— 回滚指引
# 必须先于退出码给出,人裁才有抓手。
SENTINEL_RC=0
echo
echo "==> 2/3 sentinel: $PY -m ipdb._eval --sentinel $SOURCE   # 期望 20/20 pass=True"
if [ "$DRY_RUN" = 1 ]; then
  echo "  [dry-run] cd backend && IP_RADAR_DATA_DIR=$DATA_DIR \\"
  echo "            $PY -m ipdb._eval --sentinel $SOURCE"
else
  ( cd "$REPO/backend" && IP_RADAR_DATA_DIR="$DATA_DIR" \
      "$PY" -m ipdb._eval --sentinel "$SOURCE" ) || SENTINEL_RC=$?
fi

# ── 3/3 gate 提示 + epoch 清理/回滚指引(只提示;不代跑,不自动删除)──
echo
if [ "$DRY_RUN" = 1 ]; then
  echo "==> 3/3 gate 提示 + epoch 清理/回滚指引"
  echo "  [dry-run] 哨兵通过分支: 提示 cd backend && IP_RADAR_EVAL_ENV=gate \\"
  echo "            $PY -m ipdb._eval --gate $SOURCE(不代跑)"
  echo "  [dry-run] 指引块: 清理(保留至 gate 过;rebuild 自 prune)/"
  echo "            回滚(停用 PATCH enabled=false 或 IP_RADAR_PRIVATE_SOURCES / 摘除 rm)"
  echo "  [dry-run] 哨兵未过分支: 不进 gate,打印回滚指引后以哨兵 rc 退出"
  echo
  echo "完成(dry-run)。"
  exit 0
fi

if [ "$SENTINEL_RC" != 0 ]; then
  echo "==> 3/3 哨兵未过(rc=$SENTINEL_RC): 不进 gate"
  echo "    fail-closed 语义见哨兵输出:not-accused=引擎全静默 /"
  echo "    accused-by-others[...]=他源回声、本源缺席 / NO-MEMBERS / NO-ASSET-AXIS"
else
  echo "==> 3/3 哨兵通过: 提示跑接入关(人裁终局,本脚本不代跑)"
  echo "    cd backend && IP_RADAR_EVAL_ENV=gate $PY -m ipdb._eval --gate $SOURCE"
  echo "    (--gate 先对齐生产镜像(S7)再出双口径报告;报告 gate-$SOURCE-<ts>.md 附 PR)"
fi

cat <<EOF

── epoch 清理/回滚指引(旧物化产物保留至 gate 过后再清;本脚本不自动删除任何文件)──
  清理(gate 过后): 正常无需手动 —— rebuild 提交后自动 prune 旧 epoch 目录
    (_sources/_lmdb.py rebuild_lmdb 尾部 best-effort prune);崩溃残留
    .new.<pid> staging 由下次进程启动 cleanup_stale 回收。
  回滚(gate 未过,人裁后手动执行):
    停用(保留数据,舰队查询即刻剔除):
      PATCH /api/sources/$SOURCE   body {"enabled": false}
      (set_source_enabled 持久化 source_state.json)
      或遮蔽不入舰队查询: IP_RADAR_PRIVATE_SOURCES=$SOURCE
    摘除(确认弃用;filename 以源模块为准,house style filename==name):
      rm -rf "$DATA_DIR/$SOURCE".lmdb.* "$DATA_DIR/$SOURCE".v6.lmdb.* "$DATA_DIR/$SOURCE"
    未合入的候选: 移除 backend/ipdb/_sources/$SOURCE.py 即回滚。
  修复/迭代后重跑本脚本即可(rebuild 自 prune 上一轮 epoch)。
  当前物化产物(只读列出):
EOF
find "$DATA_DIR" -maxdepth 1 \( -name "$SOURCE.lmdb.*" -o -name "$SOURCE.v6.lmdb.*" -o -name "$SOURCE" \) 2>/dev/null | sort | sed 's/^/    /' || true
PTR="$DATA_DIR/$SOURCE.lmdb.ptr"
if [ -f "$PTR" ]; then
  echo "    ptr(v4)=$(cat "$PTR")   ptr(v6)=$(cat "$DATA_DIR/$SOURCE.v6.lmdb.ptr" 2>/dev/null || echo -)"
fi

echo
if [ "$SENTINEL_RC" != 0 ]; then
  echo "中止: 哨兵未过,物化产物保留待人裁(回滚见上)。"
  exit "$SENTINEL_RC"
fi
echo "完成。gate 报告过审后源即收录;同批多候选逐个串行跑本流程(spec §3.2)。"
