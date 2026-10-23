"""ops 待审条目库(P1 §1,票 #153;spec #152 运营审阅条目化)。

结构化待审条目一条一文件(markdown + frontmatter,判例同构),是四键审阅
(同意/修改/忽略/稍后,T3)与确定性产条(T2 探测器)的存储底座;本模块
只做 T1 范围:存储/幂等/复开链指/状态机,零审阅动作、零 LLM、零队列写。

设计裁记(出处):
- 十字段冻结(spec #152 §1):id / action / args / evidence / impact /
  rollback / dedup_key / severity / cause_group / status —— 前端四键后果
  文案(impact/rollback)与排序面(severity/cause_group)全从这十个字段出,
  扩字段须过 spec 变更,不在此私自加;supersedes 是复开链指可选字段,不
  计入冻结十(仅复开条目携带);
- status ∈ active|snoozed|done|dismissed(spec #152 §1)。done/dismissed
  终态:复开 = 新条目 supersedes 链指旧条(原条目永不删,判例 superseded_by
  同思想,spec #152 §1「同因重开不双开,复开链指旧条」),不是改旧条回
  active —— 就地复活会抹掉「已处置过」的人裁史;
- 状态变更只改 frontmatter 的 status 行,正文永不改(哲学①证据不灭失,
  spec #152 §1);实现沿 _ops_store._link_superseded 的字面行替换法:
  找不到字面行 = 疑似手改损坏 → 拒绝猜测(宁报错不碰历史);
- 幂等:dedup_key = (source, probe_class, error_signature) 语义键(spec
  #152 §1)。同 key 在飞(active/snoozed)→ 零写返回既有条目,不双开;
  同 key 终态 → 复开新条目链指。文件名内容寻址(sha1 前 10 位,含
  supersedes 目标 → 同日连环复开不撞名),沿 write_ruling 判例;
- severity 闭集 high|medium|low(列表序 = high 先见;闭集真源 = T2 探测器
  产条粒度);cause_group 不设闭集(根因组词表归 T2 冻结,存储层只保证
  非空,宁少算勿多算);
- 写操作原子(_ops_store.atomic_write_text 同件复用);先查后写窗口 =
  模块锁(_ops_store._ruling_lock 同思想,单 worker 部署下足够);
- 坏文件(解析失败/闭集外/缺字段)= 显式报错,绝不静默跳过伪装无事
  (无证据≠清白,_ops_store._parse_precedent 同口径)—— 列表与产条扫描
  全量过 validate_item_entry,一个坏文件即拦下待修,不让幂等判读跑在
  不可信数据上。
"""

import hashlib
import json
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from . import _ops_store

# status 闭集(spec #152 §1;active = 待审,snoozed = 稍后(到期回 active 归
# T3 审阅 API),done/dismissed = 终态,复开走新条目链指)
ITEM_STATUSES = ("active", "snoozed", "done", "dismissed")
# severity 闭集:排序序 = 元组序(high 最先见);闭集真源 = T2 探测器产条粒度
ITEM_SEVERITIES = ("high", "medium", "low")
# 十字段冻结(spec #152 §1;supersedes 为复开链指可选字段,不计入冻结十)
ITEM_FIELDS = (
    "id", "action", "args", "evidence", "impact",
    "rollback", "dedup_key", "severity", "cause_group", "status",
)
_DEDUP_KEY_FIELDS = ("source", "probe_class", "error_signature")
# 合法状态迁移闭集:active/snoozed ↔ 审阅四键目标态;done/dismissed 终态
# (复开 = 新条目链指,非就地迁移)
_ITEM_TRANSITIONS = {
    "active": frozenset({"snoozed", "done", "dismissed"}),
    "snoozed": frozenset({"active", "done", "dismissed"}),
    "done": frozenset(),
    "dismissed": frozenset(),
}
_STATUS_RANK = {s: i for i, s in enumerate(ITEM_STATUSES)}
_SEVERITY_RANK = {s: i for i, s in enumerate(ITEM_SEVERITIES)}
# 条目文件名 = 判例同款日期前缀 + item + 内容寻址摘要(见模块头幂等裁记)
_ITEM_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-item-[0-9a-f]{10}\.md$")
# 源名形状 = T4 冻结队列源形状(_ops_store._QUEUE_SOURCE_RE)独立抄录,
# 同一拼写一处来源;probe_class/error_signature 不设形状闭集(归 T2)
_SOURCE_RE = re.compile(r"^[a-z0-9_]{1,32}$")
# 先查后写竞态窗口锁(进程内;跨进程窗口见 _ops_store 模块头同款说明)
_items_lock = threading.Lock()


def _items_dir() -> Path:
    return _ops_store.ops_root() / "items"


def validate_item_entry(fm: dict) -> None:
    """条目 schema 校验(写入口生成内容过此校验才落盘,写什么校什么 ——
    判例 validate_precedent_entry 同律)。十字段齐全 + 类型/闭集校验;
    supersedes 可选(仅复开条目携带)。"""
    if not isinstance(fm, dict):
        raise ValueError("条目 frontmatter 必须是映射")
    for field in ITEM_FIELDS:
        if field not in fm:
            raise ValueError(f"条目缺必填字段 {field}")
    if not isinstance(fm["id"], str) or not fm["id"]:
        raise ValueError("id 必须是非空字符串(文件名 stem)")
    if not isinstance(fm["action"], str) or not fm["action"].strip():
        raise ValueError("action 必须是非空字符串")
    if not isinstance(fm["args"], dict):
        raise ValueError("args 必须是映射(动作参数)")
    if not isinstance(fm["evidence"], dict) or not fm["evidence"]:
        raise ValueError("evidence 必须是非空映射(无证据即无话)")
    for field in ("impact", "rollback"):
        v = fm[field]
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{field} 必须是非空字符串(四键后果文案面)")
    dk = fm["dedup_key"]
    if not isinstance(dk, dict) or set(dk) != set(_DEDUP_KEY_FIELDS):
        raise ValueError(
            f"dedup_key 恰含三键 {_DEDUP_KEY_FIELDS},实际 "
            f"{sorted(dk) if isinstance(dk, dict) else dk!r}")
    for k in _DEDUP_KEY_FIELDS:
        v = dk[k]
        if not isinstance(v, str) or not v:
            raise ValueError(f"dedup_key.{k} 必须是非空字符串")
    if not _SOURCE_RE.match(dk["source"]):
        raise ValueError(
            f"dedup_key.source 形状非法(^[a-z0-9_]{{1,32}}$): {dk['source']!r}")
    if fm["severity"] not in ITEM_SEVERITIES:
        raise ValueError(
            f"severity 必须在闭集内: {'/'.join(ITEM_SEVERITIES)},"
            f"实际 {fm['severity']!r}")
    if not isinstance(fm["cause_group"], str) or not fm["cause_group"].strip():
        raise ValueError("cause_group 必须是非空字符串")
    if fm["status"] not in ITEM_STATUSES:
        raise ValueError(
            f"status 必须在闭集内: {'/'.join(ITEM_STATUSES)},实际 {fm['status']!r}")
    sup = fm.get("supersedes")
    if sup is not None and (not isinstance(sup, str) or not sup):
        raise ValueError("supersedes 若有必须是非空字符串(复开链指旧条目 id)")


def _frontmatter_text(text: str) -> str:
    """leading `---` 围栏内 frontmatter 原文(_ops_store 同款独立抄录)。"""
    if not text.startswith("---\n"):
        raise ValueError("缺 frontmatter 起始围栏")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("frontmatter 未闭合")
    return text[4:end]


def _parse_item(path: Path) -> dict:
    """解析条目 frontmatter 并过 schema 校验。形状坏 = 显式报错
    (_ops_store._parse_precedent 同口径:绝不静默跳过伪装无事)。"""
    try:
        fm = yaml.safe_load(_frontmatter_text(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as e:
        raise ValueError(f"{path.name}: frontmatter 解析失败: {e}") from e
    if not isinstance(fm, dict):
        raise ValueError(f"{path.name}: frontmatter 非映射")
    try:
        validate_item_entry(fm)
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}") from None
    return fm


def _render_item(fm: dict, body: str) -> str:
    """条目全文 = --- 围栏 yaml frontmatter + 人读摘要正文(_render_precedent
    同款:width 拉满不折行、sort_keys=False 字段序 = 冻结序)。"""
    fm_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False, width=10**6)
    return f"---\n{fm_text}---\n\n{body}"


def _same_dedup_key(fm: dict, source: str, probe_class: str,
                    error_signature: str) -> bool:
    dk = fm.get("dedup_key")
    return (isinstance(dk, dict)
            and dk.get("source") == source
            and dk.get("probe_class") == probe_class
            and dk.get("error_signature") == error_signature)


def create_item(*, source: str, probe_class: str, error_signature: str,
                action: str, args: dict, evidence: dict, impact: str,
                rollback: str, severity: str, cause_group: str, summary: str,
                today: date | None = None) -> dict:
    """产条(确定性,零 LLM):十字段 frontmatter + 人读摘要正文一条一文件。

    幂等(语义键非文件名):同 dedup_key 在飞(active/snoozed)→ 零写返回
    既有条目 created=False;同 key 终态 → 复开新条目,supersedes 链指最近
    旧条(原条目永不删)。返回 {created, item, supersedes}。校验全在写前
    (write_ruling 同律),失败 = 树零变化。
    """
    if not (isinstance(source, str) and _SOURCE_RE.match(source)):
        raise ValueError(f"source 形状非法(^[a-z0-9_]{{1,32}}$): {source!r}")
    for name, v in (("probe_class", probe_class),
                    ("error_signature", error_signature),
                    ("action", action), ("impact", impact),
                    ("rollback", rollback), ("cause_group", cause_group)):
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{name} 必须是非空字符串")
    if not isinstance(args, dict):
        raise ValueError("args 必须是映射(动作参数)")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("evidence 必须是非空映射(无证据即无话)")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary 必须是非空字符串(人读摘要正文)")
    d = today or date.today()
    _ops_store.init_ops_tree()  # 幂等建形状(items/ 目录,裁④同判例)
    with _items_lock:
        open_item = None    # 同 key 在飞条目(不双开)
        same_key = []       # 同 key 文件集(倒序扫描仅为确定性遍历,不作新旈权威)
        for path in sorted(_items_dir().glob("*.md"), reverse=True):
            fm = _parse_item(path)  # 坏文件显式报错(模块头裁记)
            if not _same_dedup_key(fm, source, probe_class, error_signature):
                continue
            same_key.append(path)
            if fm.get("status") in ("active", "snoozed"):
                open_item = path.stem
                break
        if open_item is not None:
            return {"created": False, "item": open_item, "supersedes": None}
        # latest = 同 key 中 mtime 最大者(review Finding 1):同日文件名倒序
        # 退化为摘要 hex 序,与创建先后无关,曾致第三次同日事件链指错跳并
        # 撞名静默覆写终态字节。创建与 set_status 都是原子重写(临时文件 +
        # rename 换新 mtime),终态文件此后不被触碰 → mtime 新者即链头。
        latest = (max(same_key, key=lambda p: p.stat().st_mtime).stem
                  if same_key else None)
        # 文件名内容寻址含 supersedes 目标 → 同日连环复开各得新名不撞车
        digest = hashlib.sha1("\x00".join((
            source, probe_class, error_signature, action,
            json.dumps(args, sort_keys=True, ensure_ascii=False),
            latest or "")).encode("utf-8")).hexdigest()[:10]
        stem = f"{d:%Y-%m-%d}-item-{digest}"
        fm = {
            "id": stem,
            "action": action,
            "args": args,
            "evidence": evidence,
            "impact": impact,
            "rollback": rollback,
            "dedup_key": {
                "source": source, "probe_class": probe_class,
                "error_signature": error_signature,
            },
            "severity": severity,
            "cause_group": cause_group,
            "status": "active",
        }
        if latest is not None:  # 复开条目才携带链指(冻结十字段保持十)
            fm["supersedes"] = latest
        text = _render_item(fm, summary)
        # schema 校验律:序列化文本往返解析后过校验才落盘(写什么校什么)
        validate_item_entry(yaml.safe_load(_frontmatter_text(text)))
        # 写前防呆(review Finding 1):撞名宁响亮失败不静默覆写(哲学①)
        if (_items_dir() / f"{stem}.md").is_file():
            raise ValueError(f"条目文件已存在,拒绝覆写: {stem}.md")
        _ops_store.atomic_write_text(_items_dir() / f"{stem}.md", text)
        return {"created": True, "item": stem, "supersedes": latest}


def _resolve_item(item_id: str) -> Path:
    _ops_store.validate_ops_filename(item_id)
    return _items_dir() / f"{item_id}.md"


def set_status(item_id: str, new_status: str) -> dict:
    """状态迁移:只改 frontmatter 的 status 字面行,正文一字不动(哲学①)。

    合法迁移闭集见 _ITEM_TRANSITIONS;终态外迁拒绝(复开 = 新条目链指,
    非就地迁移);同态重置 = 幂等零写。字面行找不到 = 疑似手改损坏 →
    拒绝猜测改写(宁报错不碰历史)。
    """
    # 与 create_item 同锁纪律(review Finding 2):读-改-写全程持锁,
    # 防并发丢更新与查在飞/落终态的 TOCTOU 窗口(_ops_store._ruling_lock
    # 包 _link_superseded 同思想)。
    with _items_lock:
        if new_status not in ITEM_STATUSES:
            raise ValueError(
                f"status 必须在闭集内: {'/'.join(ITEM_STATUSES)},实际 {new_status!r}")
        path = _resolve_item(item_id)
        if not path.is_file():
            raise FileNotFoundError(f"条目不存在: {item_id}")
        text = path.read_text(encoding="utf-8")
        fm = _parse_item(path)
        old = fm["status"]
        if new_status == old:
            return {"item": item_id, "from": old, "to": new_status, "changed": False}
        if new_status not in _ITEM_TRANSITIONS[old]:
            raise ValueError(
                f"非法迁移 {old} → {new_status}(终态复开 = 新条目链指,"
                f"非就地迁移;合法目标: {'/'.join(sorted(_ITEM_TRANSITIONS[old])) or '无'})")
        # 字面行替换(仅 frontmatter 范围;正文按构造不动)
        lines = text.split("\n")
        try:
            close = lines[1:].index("---") + 1
        except ValueError:
            raise ValueError(f"{path.name}: frontmatter 未闭合,拒绝改状态") from None
        target = f"status: {old}"
        idx = next((i for i in range(1, close) if lines[i] == target), None)
        if idx is None:
            raise ValueError(
                f"{path.name}: 无字面行 {target!r},疑似手改损坏,拒绝改状态")
        lines[idx] = f"status: {new_status}"
        _ops_store.atomic_write_text(path, "\n".join(lines))
        return {"item": item_id, "from": old, "to": new_status, "changed": True}


def list_items() -> list[dict]:
    """条目列表(frontmatter 全字段 + mtime):active 先见,severity 降序,
    cause_group 升序,同组新条目先见(日期前缀名倒序,包/判例同惯例)。
    坏文件显式报错不静默跳过(无证据≠清白)。"""
    _ops_store.init_ops_tree()
    out = []
    for path in sorted(_items_dir().glob("*.md"), reverse=True):
        fm = _parse_item(path)  # 含 schema 校验(坏文件显式报错)
        it = dict(fm)
        it["modified"] = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc).isoformat()
        out.append(it)
    # 稳定双趟:先 id 倒序(新先见),再 (status, severity, cause_group)
    out.sort(key=lambda it: str(it["id"]), reverse=True)
    out.sort(key=lambda it: (_STATUS_RANK[it["status"]],
                             _SEVERITY_RANK[it["severity"]],
                             str(it["cause_group"])))
    return out


def read_item(item_id: str) -> str:
    """条目全文逐字;不存在/名字形状非法显式报错(不伪装空)。"""
    path = _resolve_item(item_id)
    if not path.is_file():
        raise FileNotFoundError(f"条目不存在: {item_id}")
    return path.read_text(encoding="utf-8")
