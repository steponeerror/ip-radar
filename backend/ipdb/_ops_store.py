"""ops 数据树存取(P1,票 #133;产品化裁④:ops 树落数据目录一个根)。

判例/裁决包/台账/待集成清单的可读写面,供 P2 轮次端点与 P3 读 API/人裁写回
消费。文件格式沿 T4 冻结件(docs/ops/ 现状为唯一形状真源,本文所写为占位
形状的正式落位):

- 台账 ledger.md 表头/行 = ops/agent/lib.sh ledger_append 逐字;
- 待集成清单 queue.md 表头/行/去重键(action+source)/谓词闭集 =
  ops/agent/tools.mjs queueAction 逐字(轮次信封 queue_writes 的 dedup 同键);
- 判例目录名 _schema.md 是 schema 说明非判例,检索/导入一律随目录携带但
  读取方须排除(既有 test_precedent_schema.py 同口径)。

设计裁记(出处):
- ops 根 = $IP_RADAR_DATA_DIR/ops,回落 <backend>/data/ops —— 与
  ipdb/_registry.py DATA_DIR 同一惯例;call-time 解析(env 覆盖照
  _eval/__main__.py 先例,测试免 reload)。
- 原子写 = 同目录临时文件 + fsync + os.replace(POSIX rename 原子),
  故障时临时文件清理、原文件原样 —— 中断不留半包。
- 种子导入幂等:目标已存在一律跳过,种子永不覆写库内判例(无界不删;
  库是活副本,人裁写回后不得被再导入冲掉)。
- rg 检索 rc≥2 = 基础设施故障,显式报错,绝不伪装成空结果(T2 Minor-3
  判例:无证据≠清白);rc=1 才是真零命中。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

_app_dir = Path(__file__).resolve().parent.parent
# 与 _registry.py 同惯例:CLI/API 进程都认 backend/.env(存在才生效,不覆盖已设值)
load_dotenv(_app_dir / ".env")

# T4 冻结闭集(tools.mjs queueAction parameters)
QUEUE_ACTIONS = ("ENQUEUE", "REJECT")
QUEUE_PREDICATES = ("sunset_frozen", "mirror_echo", "zero_asset")
_QUEUE_SOURCE_RE = re.compile(r"^[a-z0-9_]{1,32}$")

# T4 冻结表头(逐字;lib.sh ledger_append / tools.mjs queueAction 首建串)
LEDGER_HEADER = (
    "# 运营轮次台账\n\n"
    "| 日期 | 轮次 | model | 用量 | 备注 |\n"
    "|---|---|---|---|---|\n"
)
QUEUE_HEADER = (
    "# 源生命周期动作队列(queue_action 唯一写口;行由 host 模板渲染,rationale 只落工件)\n\n"
    "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n"
    "|---|---|---|---|---|---|---|\n"
)

_RG_TIMEOUT_S = 60  # ops/agent tools.mjs search_precedents 同值


def ops_root() -> Path:
    """ops 树根:$IP_RADAR_DATA_DIR/ops(回落 <backend>/data/ops)。

    call-time 解析(_eval/__main__.py 先例):测试 monkeypatch env 免 reload,
    进程内多次调用始终见最新值。
    """
    data_dir = os.environ.get("IP_RADAR_DATA_DIR", str(_app_dir / "data"))
    return Path(data_dir) / "ops"


def atomic_write_text(path: Path | str, text: str) -> Path:
    """原子写文本:同目录临时文件 + fsync + os.replace。

    rename 前任何故障 → 临时文件删除、目标原样(半包不留脏文件);
    rename 后目录项 fsync 尽力而为(平台不支持则静默,文件内容已 fsync)。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    try:  # 目录项落盘(尽力)
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    return path


def init_ops_tree() -> Path:
    """初始化 ops 树(precedents/packages/artifacts + 台账/清单表头)。

    幂等:目录与表头已存在即零改动,既有内容不重写、不校验(树内容归
    导入/追加/写回路径管,init 只保证形状存在)。
    """
    root = ops_root()
    for sub in ("precedents", "packages", "artifacts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for name, header in (("ledger.md", LEDGER_HEADER), ("queue.md", QUEUE_HEADER)):
        target = root / name
        if not target.exists():
            atomic_write_text(target, header)
    return root


def import_seeds(seed_dir: Path | str) -> dict:
    """种子判例一次性幂等导入 <ops_root>/precedents/。

    目录内全部 *.md(含 _schema.md,保持库自描述)逐文件复制:目标已存在
    一律跳过并计数 —— 重复执行零新增;缺种子目录/无 .md 文件显式报错,
    不静默零导入伪装「无事可做」(无证据≠清白)。复制走原子写,导入中断
    不留半文件。
    """
    seed_dir = Path(seed_dir)
    if not seed_dir.is_dir():
        raise FileNotFoundError(f"种子目录不存在: {seed_dir}")
    seeds = sorted(seed_dir.glob("*.md"))
    if not seeds:
        raise ValueError(f"种子目录无 .md 判例: {seed_dir}")
    target_dir = ops_root() / "precedents"
    target_dir.mkdir(parents=True, exist_ok=True)
    imported = skipped = 0
    for src in seeds:
        dst = target_dir / src.name
        if dst.exists():
            skipped += 1
            continue
        atomic_write_text(dst, src.read_text(encoding="utf-8"))
        imported += 1
    return {"imported": imported, "skipped": skipped, "target": str(target_dir)}


def _read_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _append_row_with_header(path: Path, header: str, row: str) -> None:
    """表头惰性首建 + 行原子追加(T4 lib.sh/tools.mjs 缺文件即建头口径)。"""
    existing = _read_if_exists(path)
    body = existing if existing else header
    if not body.endswith("\n"):
        body += "\n"
    atomic_write_text(path, body + row)


def append_queue(
    round_: str,
    action: str,
    source: str,
    predicate: str | None = None,
    evidence: Sequence[tuple[str, str, Any]] = (),
    *,
    today: date | None = None,
) -> dict:
    """待集成清单(queue.md)追加,幂等去重键 = action+source(T4 冻结)。

    行形状与 evidence 渲染(call_id:field=json 值,分号连接)逐字沿
    tools.mjs queueAction;vetoable 恒「是(否决=删除本行)」。闭集校验
    (action/predicate/source 形状)在写文件前拒绝;evidence 的语义验证
    (逐字对结构化返回)属 agent 侧写前门,不在此重复(P2 桥消费面)。
    """
    if action not in QUEUE_ACTIONS:
        raise ValueError(f"action 必须在闭集内: {'/'.join(QUEUE_ACTIONS)},实际 {action!r}")
    if predicate is not None and predicate not in QUEUE_PREDICATES:
        raise ValueError(
            f"predicate 必须在闭集内: {'/'.join(QUEUE_PREDICATES)},实际 {predicate!r}")
    if not _QUEUE_SOURCE_RE.match(source):
        raise ValueError(f"source 形状非法(^[a-z0-9_]{{1,32}}$): {source!r}")

    qpath = ops_root() / "queue.md"
    existing = _read_if_exists(qpath)
    # T4 去重判式逐字:任意日期/轮次的同 action+source 行已存在即去重
    dedup_re = re.compile(
        r"\| \d{4}-\d{2}-\d{2} \| [^|]+ \| " + re.escape(action)
        + r" \| " + re.escape(source) + r" \|")
    dedup = dedup_re.search(existing) is not None
    if not dedup:
        ev = ";".join(f"{c}:{f}={json.dumps(v, ensure_ascii=False)}"
                      for c, f, v in evidence)
        d = (today or date.today()).isoformat()
        row = (f"| {d} | {round_} | {action} | {source} | {predicate if predicate else '—'} "
               f"| {ev} | 是(否决=删除本行) |\n")
        _append_row_with_header(qpath, QUEUE_HEADER, row)
    return {"appended": not dedup, "dedup": dedup}


def append_ledger(
    round_: str,
    model: str,
    usage: str,
    note: str = "",
    *,
    today: date | None = None,
) -> Path:
    """台账(ledger.md)追加一行;文件不存在则建表头(T4 lib.sh ledger_append)。

    用量记 provider 实报不自行估算(九裁决 9),本函数只落串。
    """
    d = (today or date.today()).isoformat()
    row = f"| {d} | {round_} | {model} | {usage} | {note} |\n"
    lpath = ops_root() / "ledger.md"
    _append_row_with_header(lpath, LEDGER_HEADER, row)
    return lpath


def rg_search_precedents(keywords: Sequence[str] | str) -> list[str]:
    """判例库词法检索(rg 子进程,无嵌入;检索词 OR)。

    返回命中判例文件名排序去重列表;rc=1 = 真零命中(空列表);rc≥2 =
    目录缺失/非法检索词等基础设施故障 → RuntimeError,绝不伪装成空结果
    (T2 Minor-3 判例,无证据≠清白)。_schema.md 经 rg -g 排除。
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = list(keywords)
    if not keywords or any(not k for k in keywords):
        raise ValueError("至少一个非空检索词")
    precedents = ops_root() / "precedents"
    cmd = ["rg", "-i", "-l", "-g", "*.md", "-g", "!_schema.md"]
    for kw in keywords:
        cmd += ["-e", kw]
    cmd.append(str(precedents))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_RG_TIMEOUT_S)
    except FileNotFoundError as e:
        raise RuntimeError(f"rg 不可用(镜像须装 ripgrep,P5): {' '.join(cmd)}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"rg 超时(>{_RG_TIMEOUT_S}s): {' '.join(cmd)}") from e
    if proc.returncode >= 2:
        raise RuntimeError(
            f"rg rc={proc.returncode} 基础设施故障 ≠ 零命中(无证据≠清白,"
            f"T2 Minor-3): {proc.stderr.strip()[:300]}")
    if proc.returncode == 1:
        return []
    return sorted({Path(line).name for line in proc.stdout.splitlines() if line.strip()})


def main(argv: Sequence[str] | None = None) -> int:
    """CLI:python -m ipdb._ops_store --import-seeds <seed_dir>(幂等)。

    用法错 = 纯 stderr + exit 2(_rebuild_child 惯例);导入失败(目录缺/
    无种子)exit 1;成功 stdout 报 imported/skipped 计数与落位目录。
    """
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    usage = "usage: python -m ipdb._ops_store --import-seeds <seed_dir>"
    if len(argv) != 2 or argv[0] != "--import-seeds":
        print(usage, file=sys.stderr)
        return 2
    try:
        res = import_seeds(argv[1])
    except (FileNotFoundError, ValueError) as e:
        print(f"import-seeds 失败: {e}", file=sys.stderr)
        return 1
    print(f"imported {res['imported']}, skipped {res['skipped']} -> {res['target']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
