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

P3 人裁写回(票 #135,写回四律 = 计划书 Global Constraints + 原 T5 史档规格):
- 幂等键 = (包, 建议, verdict, 修正案) 的语义比较(非文件名):同裁重复
  (含跨日)零副作用;新条目文件名内容寻址(sha1 前 10 位)→ 同日改回原裁
  复用同名文件,链保持单向一致不繁殖;
- superseded_by = 唯一许可的就地变更(仅改链指位,decision 内容原样;
  「就地改历史一律禁止」指裁决内容,链指位是 _schema.md 定义的取代机制);
  写序 = 先新条目后旧链指 → 任一瞬间链目标都存在(验收:指向存在的文件);
- hard_gates 不复制包内硬门数字,只携 package/round 指针(宁少算勿多算:
  数字在包里,复制 = 双源漂移);
- 裁⑦清单维护:agreed + 建议动词 ∈ T4 队列闭集(ENQUEUE/REJECT)→ 经
  append_queue 入队(action+source 去重幂等);其余 verdict/动词零队列写
  (不发明闭集外动词);幂等路径也调 append_queue —— 去重下真零写,且自愈
  「判例已落、队列中途失或多」的崩殘态;
- 竞态窗口:queue.md 写口持跨进程 flock(_queue_lock,与 node 侧
  tools/queue-lock.mjs 的 flock(1) 同锁域互认,#139 挂账②双边闭环);旧判
  「多进程部署下窗口残留」已由双边锁关闭;
- P1 §3 审阅四键(票 #155):write_ruling 增 item_id 来源(与 package 互斥),
  四律同构复用:lineage/hard_gates 指针 = ops/items/<id>.md(证据在条目里
  不复制),幂等键首槽 = item:<id>(与包名空间隔离),队列行轮次列 =
  "review"(审阅动作非轮次产物);包来源路径字节零变化。
"""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import yaml
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

# #139 挂账②:queue.md 跨进程互斥锁文件名(= queue.md 同名 + .lock)。对称契约:
# node 侧 ops/agent/tools/queue-lock.mjs QUEUE_LOCK_SUFFIX=".lock" 从其 queueFile
# 落位(DOCS_ROOT/ops/queue.md)同式推导;生产形态 P2 桥 _ops_rounds._round_env
# 注入 DOCS_ROOT=ops_root().parent 使两侧落位同址同文件。路径漂移防线 =
# selftest-contract.mjs「锁路径对拍」哨(抽本文件 QUEUE_LOCK_NAME 字面量与
# node queueLockPath 实跑值对拍,形制同 selftest.sh §14)。
QUEUE_LOCK_NAME = "queue.md.lock"

# 台账锁(#199 交付A A3):ledger.md 双写面(python append_ledger × bash lib.sh
# ledger_append,node 轮次经 spawn 调)互斥锁名;形制同 QUEUE_LOCK_NAME——同目录
# 同名+.lock,与 node 侧 budget.mjs readLedgerTextLocked(flock(1) 读面)/lib.sh
# flock(1) 写面同一 flock(2) 锁域互认互斥。对拍哨 = selftest-contract.mjs
# 「锁路径对拍:python LEDGER_LOCK_NAME」(形制同 queue 哨)。
LEDGER_LOCK_NAME = "ledger.md.lock"


def queue_lock_path() -> Path:
    """queue.md 跨进程互斥锁文件路径(与 queue.md 同目录)。"""
    return ops_root() / QUEUE_LOCK_NAME


def ledger_lock_path() -> Path:
    """ledger.md 跨进程互斥锁文件路径(与 ledger.md 同目录;#199 交付A A3)。"""
    return ops_root() / LEDGER_LOCK_NAME


@contextmanager
def _ledger_lock():
    """ledger.md 跨进程排它锁(fcntl.flock(2),LOCK_EX;#199 交付A A3)。

    为什么锁:append_ledger 是读(缺文件建头)-写两段,与 node 轮次侧 lib.sh
    ledger_append(bash)同构,同容器两进程并发互窗后写覆盖前写(修前实证 2×40
    并发丢行近半,期望 80 实际 40——同 #139 queue 判形);月度准入读面
    (budget.mjs readLedgerTextLocked)同锁域读,读不交错写。锁形制同
    _queue_lock:O_CREAT 常驻不删,flock 挂 open file description 进程死即释。
    """
    lock = ledger_lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


@contextmanager
def _queue_lock():
    """queue.md 跨进程排它锁(fcntl.flock(2),LOCK_EX)。

    为什么锁:append_queue 是读-判重-写三段,node agent 的 queue_action(轮次中)
    是同构读-改-写,同容器两进程(uvicorn × node 轮次)并发时互窗存在——旧模块锁
    只关进程内窗(#139 挂账②原判「单边修是假修」,现双边闭环:node 侧 spawn
    util-linux flock(1),与本侧 fcntl.flock 同一 flock(2) 锁域,互认互斥)。
    为什么这窗口:锁必须覆盖 读 existing → 去重判 → 原子写 全段,缺任何一段都
    留窗(读后写前的判重结果会被他方写失效)。
    为什么 flock 不用 O_EXCL 判龄:锁挂在 open file description 上由内核管理,
    进程死锁即自动释放,无 stale 判龄协议的「>30s 强接误杀活锁」竞态;锁文件
    不存在则 O_CREAT 创建,close 即释放,不删除(空文件常驻无害)。
    fcntl 面向 POSIX:容器 Linux 限定(#139 语境=单容器生产形态),可接受。
    锁序:write_ruling 先持 threading._ruling_lock 再进本锁(恒 threading→flock,
    本锁内不再取其他锁,无倒置死锁面)。
    """
    lock = queue_lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # close 即释放 flock,不删锁文件

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
    """初始化 ops 树(precedents/packages/artifacts/items + 台账/清单表头)。

    幂等:目录与表头已存在即零改动,既有内容不重写、不校验(树内容归
    导入/追加/写回路径管,init 只保证形状存在)。items/ = P1 待审条目库
    (票 #153,spec #152 §1,一条一文件;旧树无此目录 = 首次调用补建,
    既有文件零触碰)。
    """
    root = ops_root()
    for sub in ("precedents", "packages", "artifacts", "items"):
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
    # #139 挂账②:读-判重-写全段持跨进程锁(窗口论证见 _queue_lock;幂等去重
    # 逻辑不动,只包锁)——无锁窗口 = 他方写使本方判重结果失效,丢行/重行。
    with _queue_lock():
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
    with _ledger_lock():  # #199 A3:读-建头-写全段入锁(双写面互斥;形制同 append_queue)
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
    cmd = ["rg", "-i", "-l", "-g", "*.md", "-g", "!_*"]
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


# ── P3 人裁写回(票 #135;写回四律语义见模块头)────────────────────

# T1 冻结 frontmatter 九字段(_schema.md 字段表,与 test_precedent_schema.py
# 同源不互导——两处都是 schema 真源的独立抄录)
_PRECEDENT_FIELDS = (
    "id", "date", "subject", "context", "recommendation",
    "human_ruling", "reward", "lineage", "superseded_by",
)
_PRECEDENT_REWARD_KEYS = {"hard_gates", "ruling_agreement", "production_delta"}
_PRECEDENT_AGREEMENTS = ("agreed", "overruled", "amended", "pending")
# 人裁三动作(T1 ruling_agreement 闭集去 pending:人裁不可能悬置)
RULING_VERDICTS = ("agreed", "overruled", "amended")
# verdict 固定形人裁留痕(P3 落判语义;修正案 = 固定头 + 原文一字不改)
_RULING_HUMAN = {
    "agreed": "人裁同意:建议照准。",
    "overruled": "人裁否决:建议不成立。",
}
_RULING_AMENDED_HEAD = "人裁修正,修正案逐字:\n"
_RULING_ZH = {"agreed": "同意", "overruled": "否决", "amended": "修正"}
# ops 文件名(包/判例)纯文件名约束:拒路径分隔/点前缀(../ 逃逸、.tmp 残留物)
_OPS_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# 裁⑦队列动词映射:建议首词 = T4 冻结队列闭集动词 + 源名 → 同意后入队
_SUGGESTION_QUEUE_RE = re.compile(
    r"^\s*(ENQUEUE|REJECT)\s+([a-z0-9_]{1,32})\b", re.IGNORECASE)
# 先查后写的竞态窗口锁(进程内;跨进程窗口见模块头说明)
_ruling_lock = threading.Lock()


def validate_ops_filename(name: str) -> None:
    """ops 文件名(包/判例)只认纯文件名:字母数字开头,限 [A-Za-z0-9._-]。

    路由层与写入口共用;路径分隔/点前缀一律拒。"""
    if not isinstance(name, str) or not _OPS_FILENAME_RE.match(name):
        raise ValueError(
            f"ops 文件名形状非法(纯文件名,^[A-Za-z0-9][A-Za-z0-9._-]*$): {name!r}")


def validate_precedent_entry(fm: dict) -> None:
    """T1 判例 schema 校验(写回四律之「schema 校验」的强制点)。

    九字段齐全 / reward 恰三列且非标量 / hard_gates 非空映射 /
    ruling_agreement 闭集 / production_delta 恒 null / superseded_by 指向
    存在文件 —— 写入口生成内容过此校验才落盘(库内种子同口径由
    test_precedent_schema.py 守)。"""
    if not isinstance(fm, dict):
        raise ValueError("判例 frontmatter 必须是映射")
    for field in _PRECEDENT_FIELDS:
        if field not in fm:
            raise ValueError(f"判例缺必填字段 {field}")
    reward = fm["reward"]
    if not isinstance(reward, dict):
        raise ValueError("reward 必须是映射(复合三列,永不坍缩成标量)")
    if set(reward) != _PRECEDENT_REWARD_KEYS:
        raise ValueError(f"reward 恰含三键,实际 {sorted(reward)}")
    hard_gates = reward["hard_gates"]
    if not isinstance(hard_gates, dict) or not hard_gates:
        raise ValueError("reward.hard_gates 必须是非空映射(硬门数字必带)")
    if reward["ruling_agreement"] not in _PRECEDENT_AGREEMENTS:
        raise ValueError(
            f"ruling_agreement 闭集外: {reward['ruling_agreement']!r}")
    if reward["production_delta"] is not None:
        raise ValueError(
            "production_delta 一律 null(30 天写回是独立后续批,未结案不补)")
    sb = fm["superseded_by"]
    if sb is not None and not (ops_root() / "precedents" / str(sb)).is_file():
        raise ValueError(f"superseded_by 指向不存在文件: {sb}")
    # P1 判例扩展(票 #153,spec #152 §1):item_id = 本判例来源的待审条目
    # id(T3 审阅四键落判时携带)。可选缺省 —— 旧判例文件零改动照常通过,
    # 写回四律/write_ruling 语义零改动;有则须非空字符串(条目 id 形状
    # 校验归 _ops_items,此处不跨模块 import 防环)。
    item_id = fm.get("item_id")
    if item_id is not None and (not isinstance(item_id, str) or not item_id.strip()):
        raise ValueError("item_id 若有必须是非空字符串(来源待审条目 id)")


def _frontmatter_text(text: str) -> str:
    """提取 leading `---` 围栏内的 frontmatter 原文(yaml 段)。"""
    if not text.startswith("---\n"):
        raise ValueError("缺 frontmatter 起始围栏")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("frontmatter 未闭合")
    return text[4:end]


def _parse_precedent(path: Path) -> dict:
    """解析判例 frontmatter;形状坏 = 显式报错(含包引用却非判例形状 →
    疑似本库文件损坏,绝不静默跳过伪装无事)。"""
    text = path.read_text(encoding="utf-8")
    try:
        fm = yaml.safe_load(_frontmatter_text(text))
    except yaml.YAMLError as e:
        raise ValueError(f"{path.name}: frontmatter 解析失败: {e}") from e
    if not isinstance(fm, dict):
        raise ValueError(f"{path.name}: frontmatter 非映射")
    return fm


def _round_from_package(package: str) -> str:
    """包名 YYYY-MM-DD-<round>-HHMM.md → 轮次段;异形回落 'ruling'(不猜)。"""
    stem = package[:-3] if package.endswith(".md") else package
    parts = stem.split("-")
    return parts[3] if len(parts) >= 5 else "ruling"


def _render_precedent(fm: dict, body: str) -> str:
    """判例全文 = --- 围栏 yaml frontmatter + 叙事正文。

    width 拉满 → 不折行(逐字留痕肉眼可核);sort_keys=False → 字段序 =
    _schema.md 字段表序。yaml 串行化保证多行/引号/冒号原文往返无损。"""
    fm_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False, width=10**6)
    return f"---\n{fm_text}---\n\n{body}"


def _find_current_ruling(origin: str, suggestion: str):
    """找目标(来源+建议)的 current 判例:未被取代且 recommendation 逐字相等
    且 lineage 含该来源。来源 = ops/packages/<包> 或 ops/items/<条目>.md
    (T3 审阅四键同律复用)。返回 (path, fm) 或 None;廉价预滤 = 全文不含
    来源引用的判例零解析。"""
    needle = origin
    pdir = ops_root() / "precedents"
    for path in sorted(pdir.glob("*.md")):
        if path.name.startswith("_"):
            continue
        if needle not in path.read_text(encoding="utf-8"):
            continue
        fm = _parse_precedent(path)
        lineage = fm.get("lineage")
        if fm.get("recommendation") != suggestion:
            continue
        if not isinstance(lineage, list) or needle not in [str(x) for x in lineage]:
            continue
        if fm.get("superseded_by") is not None:
            continue  # 已被取代 → 链历史,非 current
        return path, fm
    return None


def _same_ruling(fm: dict, verdict: str, amendment: str | None) -> bool:
    """current 条目与本裁语义相等(幂等判定):verdict 相同且人裁留痕相同
    (修正案原文一字不差)。"""
    reward = fm.get("reward")
    if not isinstance(reward, dict) or reward.get("ruling_agreement") != verdict:
        return False
    human = fm.get("human_ruling")
    if verdict == "amended":
        return human == _RULING_AMENDED_HEAD + amendment
    return human == _RULING_HUMAN[verdict]


def _link_superseded(path: Path, new_name: str) -> None:
    """旧条目 superseded_by 链指到新条目(唯一许可的就地变更)。

    仅在 frontmatter 范围内替换字面 'superseded_by: null' 行;找不到 =
    拒绝猜测改链(宁报错不碰历史)。"""
    lines = path.read_text(encoding="utf-8").split("\n")
    try:
        close = lines[1:].index("---") + 1
    except ValueError:
        raise ValueError(f"{path.name}: frontmatter 未闭合,拒绝改链") from None
    idx = next((i for i in range(1, close) if lines[i] == "superseded_by: null"), None)
    if idx is None:
        raise ValueError(f"{path.name}: 无 'superseded_by: null' 行,拒绝改链")
    lines[idx] = f"superseded_by: {new_name}"
    atomic_write_text(path, "\n".join(lines))


def _maybe_queue(suggestion: str, verdict: str, today: date, *,
                 round_: str | None, origin_field: tuple[str, str]) -> bool:
    """裁⑦清单维护:agreed 且建议首词 = T4 队列闭集动词(ENQUEUE/REJECT)
    + 合法源名 → append_queue(去重幂等);否则零队列写(不发明闭集外
    动词;ACCEPT/FLAG/人裁类建议以判例为唯一产物)。round_ = None 时由
    包名推导(P3 包来源旧径);条目来源传 "review"(审阅动作非轮次产物,
    不伪造轮次名)。origin_field = 溯源对(("package", 包名) 或
    ("item", 条目 id))。返回是否新入行。"""
    if verdict != "agreed":
        return False
    m = _SUGGESTION_QUEUE_RE.match(suggestion)
    if not m:
        return False
    res = append_queue(
        round_=round_ or _round_from_package(origin_field[1]),
        action=m.group(1).upper(),
        source=m.group(2), predicate=None,
        evidence=[("ruling", "verdict", "agreed"),
                  ("ruling", *origin_field)],
        today=today)
    return res["appended"]


def write_ruling(package: str | None, suggestion: str, verdict: str,
                 amendment: str | None = None, *, today: date | None = None,
                 item_id: str | None = None) -> dict:
    """人裁三动作落判例(POST /api/ops/ruling 的存储层本体;P1 §3 审阅
    四键(票 #155)经 item_id 来源同律复用)。

    来源互斥二选一:package(P3 裁决包,须存在)或 item_id(P1 待审条目,
    须存在;判例 item_id 字段 = T1 预留扩展位)。四律对两来源同构:
    幂等(键 =(来源,建议,verdict,修正案)语义比较,同裁重复含跨日零
    副作用)/ superseded_by(改裁 = 新条目 + 旧条目链指,原条目永不删)/
    人裁逐字留痕 / schema 校验;production_delta 恒 null。条目来源的
    hard_gates/lineage 指针 = ops/items/<id>.md(证据在条目里,不复制,
    防双源漂移)。返回 {created, precedent, superseded, queue_appended}。
    """
    if verdict not in RULING_VERDICTS:
        raise ValueError(
            f"verdict 必须在闭集内: {'/'.join(RULING_VERDICTS)},实际 {verdict!r}")
    if not isinstance(suggestion, str) or not suggestion.strip():
        raise ValueError("suggestion 必须是非空字符串(建议原文逐字)")
    # 空白仅当缺失;非空修正案逐字保留(含首尾空白,一字不改)
    amendment = amendment if (isinstance(amendment, str) and amendment.strip()) else None
    if verdict == "amended":
        if amendment is None:
            raise ValueError("amended 必须带非空修正案(逐字留痕载体)")
    elif amendment is not None:
        raise ValueError("修正案只随 amended(同意/否决无修正案)")
    if item_id is not None and package is not None:
        raise ValueError("package 与 item_id 互斥(判例来源唯一)")
    if item_id is not None:
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("item_id 必须是非空字符串(来源待审条目 id)")
        # 存在性:hard_gates/lineage 指针不得悬空(superseded_by 同律);
        # 不 import _ops_items 防环(_ops_items → _ops_store),按树形状直查
        if not (ops_root() / "items" / f"{item_id}.md").is_file():
            raise FileNotFoundError(f"待审条目不存在: {item_id}")
        origin = f"ops/items/{item_id}.md"
        digest_source = f"item:{item_id}"   # 与包名空间隔离(幂等键首槽)
        round_label = "review"              # 审阅动作非轮次产物(见 _maybe_queue)
        origin_field = ("item", item_id)
    else:
        validate_ops_filename(package)
        origin = f"ops/packages/{package}"
        digest_source = package
        round_label = None
        origin_field = ("package", package)
    init_ops_tree()
    if item_id is None:
        pkg_path = ops_root() / "packages" / package
        if not pkg_path.is_file():
            raise FileNotFoundError(f"裁决包不存在: {package}")
    d = today or date.today()
    with _ruling_lock:
        current = _find_current_ruling(origin, suggestion)
        if current is not None and _same_ruling(current[1], verdict, amendment):
            # 幂等零副作用;append_queue 去重 = 真零写,兼自愈队列崩殘态
            return {"created": False, "precedent": current[0].name,
                    "superseded": None,
                    "queue_appended": _maybe_queue(
                        suggestion, verdict, d, round_=round_label,
                        origin_field=origin_field)}
        digest = hashlib.sha1("\x00".join(
            (digest_source, suggestion, verdict, amendment or "")).encode("utf-8")
        ).hexdigest()[:10]
        new_name = f"{d:%Y-%m-%d}-ruling-{digest}.md"
        human = (_RULING_AMENDED_HEAD + amendment if verdict == "amended"
                 else _RULING_HUMAN[verdict])
        if item_id is None:
            subject = f"运营建议人裁 — {_RULING_ZH[verdict]}({package})"
            context = (
                f"裁决包 ops/packages/{package} 的建议(见 recommendation 逐字)经 "
                "admin 人裁三动作落判例;决策时事实面与硬门实测数字以该包为准,"
                "本条不复制(宁少算勿多算,防双源漂移)。")
            hard_gates = {"package": f"ops/packages/{package}",
                          "round": _round_from_package(package)}
            lineage = [f"ops/packages/{package}"]
            body = (
                f"# 判例:人裁{_RULING_ZH[verdict]} — {package}\n\n"
                f"裁决包 `ops/packages/{package}` 的建议经人裁{_RULING_ZH[verdict]}。"
                "事实面/硬门数字/trace 以该包为准,本条不复制(防双源漂移);"
                f"回报三列:ruling_agreement={verdict},production_delta=null"
                "(30 天生产增量写回是独立后续批,未结案不补)。\n"
            )
        else:
            subject = f"待审条目人裁 — {_RULING_ZH[verdict]}({item_id})"
            context = (
                f"待审条目 ops/items/{item_id}.md 的动作建议(见 recommendation 逐字)经 "
                "admin 四键审阅落判例;决策时事实面与证据以该条目为准,"
                "本条不复制(宁少算勿多算,防双源漂移)。")
            hard_gates = {"item": f"ops/items/{item_id}.md"}
            lineage = [f"ops/items/{item_id}.md"]
            body = (
                f"# 判例:待审条目人裁{_RULING_ZH[verdict]} — {item_id}\n\n"
                f"待审条目 `ops/items/{item_id}.md` 的动作建议经人裁{_RULING_ZH[verdict]}。"
                "事实面/证据/evidence 以该条目为准,本条不复制(防双源漂移);"
                f"回报三列:ruling_agreement={verdict},production_delta=null"
                "(30 天生产增量写回是独立后续批,未结案不补)。\n"
            )
        fm = {
            "id": new_name[:-3],
            "date": d,
            "subject": subject,
            "context": context,
            "recommendation": suggestion,
            "human_ruling": human,
            "reward": {
                # 指针非数字:硬门数字/证据在包或条目里,复制 = 双源漂移
                # (模块头裁记;条目来源 hard_gates 只携 item 指针)
                "hard_gates": hard_gates,
                "ruling_agreement": verdict,
                "production_delta": None,
            },
            "lineage": lineage,
            "superseded_by": None,
        }
        if item_id is not None:
            fm["item_id"] = item_id  # T1 预留扩展位(validate 可选字段)
        text = _render_precedent(fm, body)
        # 四律之 schema 校验:序列化文本往返解析后过校验(写什么校什么)
        validate_precedent_entry(yaml.safe_load(_frontmatter_text(text)))
        atomic_write_text(ops_root() / "precedents" / new_name, text)
        superseded = None
        if current is not None:
            # 先新条目后链指 → 任一瞬间 superseded_by 目标都存在
            _link_superseded(current[0], new_name)
            superseded = current[0].name
        return {"created": True, "precedent": new_name, "superseded": superseded,
                "queue_appended": _maybe_queue(
                    suggestion, verdict, d, round_=round_label,
                    origin_field=origin_field)}


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
