# backend/ipdb/_scan.py
"""按键序扫描(#444,规格 docs/research/2026-11-24-blocklist-scan-export-spec.md §4.2)。

黑名单导出的输入侧:不再逐地址调 lookup()(60+ 源 × 全键空间是 O(键)×O(源)
的随机读灾难),而是把每个(源,族)的 LMDB 库按键序(=地址数值序)顺游标走
一遍,heapq.merge 多路归并,同一起点凑组;一个单元的证据选法与查询接口
_lmdb.lookup 完全同构(先单地址、无则覆盖网段),喂给 #444 拆出的
_registry.fuse_items(),扫描结果与查询接口逐字段相同是构造出来的、不用另证。

内存纪律(规格 §4.2 规则 6):任何时刻不在内存里攒记录——网段记录原文落
临时 sqlite,内存只留起点/终点两个整数数组(游标序=起点升序,直接 append)。

纪元一致性(规格 §4.2 规则 10):开句柄时经 read_ptr() 记下纪元,整个扫描
期间只读这个纪元目录;rebuild 侧提交新纪元不影响进行中的扫描。
"""
from __future__ import annotations

import bisect
import heapq
import itertools
import logging
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import ipaddress
import lmdb

from ipdb._registry import LookupResult, fuse_items
from ipdb._sources._lmdb import (
    PAYLOADS_NAME,
    _PAYLOAD_DB_CACHE,
    _end_int,
    _payloads_db,
    decode_value,
    env_dir,
    read_disjoint_flag,
    read_ptr,
    resolve_evidence,
)

logger = logging.getLogger(__name__)

# 临时 sqlite 表:网段记录原文的落盘 scratch。主键 (source, family, start_hex)
# ——任务书 §2.2 写「索引 (source, start)」,实现必须加 family:v4/v6 两族
# 同表,起点整数数值空间重叠(v4 的小整数撞 v6 小整数),缺 family 会串族
# (#444 偏差,交付件 §2 记明)。start_hex 定宽十六进制文本,字典序=数值序。
_SPILL_DDL = """
CREATE TABLE cidr (
    source    TEXT    NOT NULL,
    family    INTEGER NOT NULL,
    start_hex TEXT    NOT NULL,
    end_hex   TEXT    NOT NULL,
    raw       BLOB    NOT NULL,
    PRIMARY KEY (source, family, start_hex)
)
"""


@dataclass
class ScannedUnit:
    """一个扫描单元:单地址=地址文本;网段=CIDR 文本。result 在单元地址
    (网段=网络地址)上经 fuse_items 算出,与查询接口同形状。"""

    ip: str
    is_v6: bool
    is_cidr: bool
    first_seen: str | None
    last_seen: str | None
    result: LookupResult


class _FamilyState:
    """一个(源,族)的扫描期状态:只读 env、钉死的纪元、起点/终点数组。

    starts/ends 是规格 §4.2 规则 6 唯一允许常驻内存的东西(整数数组,
    游标序=起点升序,append 即有序);网段原文在 sqlite,不驻内存。
    """

    __slots__ = ("env", "epoch", "disjoint", "bits", "starts", "ends",
                 "max_end", "plens")

    def __init__(self, env, epoch: int, disjoint: bool, bits: int):
        self.env = env
        self.epoch = epoch
        self.disjoint = disjoint
        self.bits = bits
        self.starts: list[int] = []
        self.ends: list[int] = []
        self.max_end = -1
        # 嵌套库才需要:库内出现过的前缀长集合(长到短探测用)。每条记录
        # 自身的前缀长必在此集合内 ⇒「限库内前缀长」与查询路径的逐全前缀
        # 探测命中同一记录(记录之外的前缀长探测必 miss,跳过只省探测次数)。
        self.plens: set[int] = set()

    def find_covering(self, addr: int) -> int | None:
        """返回覆盖 addr 的网段记录下标,无则 None。与 _lmdb.lookup 两分支
        同构:不相交库取「起点≤addr 的最后一条」且终点≥addr;嵌套库按库内
        前缀长从长到短找「对齐起点在数组中且终点≥addr」的第一条。"""
        if not self.starts or addr < self.starts[0] or addr > self.max_end:
            return None                     # 规格规则 6 快速排除
        if self.disjoint:
            i = bisect.bisect_right(self.starts, addr) - 1
            if i >= 0 and self.ends[i] >= addr:
                return i
            return None
        mask_full = (1 << self.bits) - 1
        for plen in sorted(self.plens, reverse=True):
            mask = mask_full >> plen        # 低 (bits-plen) 位为 1
            aligned = (addr | mask) ^ mask  # = addr & ~mask(对齐起点)
            i = bisect.bisect_left(self.starts, aligned)
            if i < len(self.starts) and self.starts[i] == aligned \
                    and self.ends[i] >= addr:
                return i
        return None


def _is_threat_source(s) -> bool:
    """与导出器 scripts/universe_walk.py 的 _is_threat_source 同一判据:
    声明了分类、category=="threat"、非 internal。只有威胁类源产生单元。"""
    return (getattr(s, "classification_type", None) is not None
            and getattr(s, "category", None) == "threat"
            and not getattr(s, "internal", False))


def _seen_bounds(evidence) -> tuple[list[str], list[str]]:
    """证据里的 (first_seen 列表, last_seen 列表)。只认字符串、文本序
    比较(与导出器 universe_walk 同款:时间格式不一,数值化会错序)。"""
    firsts: list[str] = []
    lasts: list[str] = []
    entries = evidence if isinstance(evidence, list) else [evidence]
    for e in entries:
        if not isinstance(e, dict):
            continue
        v = e.get("first_seen")
        if isinstance(v, str):
            firsts.append(v)
        v = e.get("last_seen")
        if isinstance(v, str):
            lasts.append(v)
    return firsts, lasts


class UnitScanner:
    """按键序扫描器。用法:``with open_unit_scanner(...) as sc:`` 然后迭代。

    读集=声明 classification_type 的源(威胁类+资产类都读——资产类证据
    要留给威胁单元融合用,规格 §4.2 规则 5);只有威胁类源产生单元。
    sources=None → _enabled_sources() 减 _PRIVATE;测试传显式实例列表。
    """

    def __init__(self, *, sources=None, asof=None, spill_dir=None):
        if sources is None:
            from ipdb import _registry
            sources = [s for s in _registry._enabled_sources()
                       if s.name not in _registry._PRIVATE]
        self._sources = list(sources)
        self._asof = asof
        self._classified = [s for s in self._sources
                            if getattr(s, "classification_type", None)
                            is not None]
        self._threat = {s.name for s in self._classified
                        if _is_threat_source(s)}
        self._fam: dict[tuple[str, int], _FamilyState] = {}
        self.epochs: dict[str, tuple[int | None, int | None]] = {}
        self.stats: dict = {
            "records": {},          # 各源单地址记录数
            "cidr_records": {},     # 各源网段记录数
            "skipped_anomalies": 0, # 不恰为一个 CIDR 的网段范围
            "units": {"v4_single": 0, "v4_cidr": 0,
                      "v6_single": 0, "v6_cidr": 0},
            "timings": {},
        }
        self._closed = False
        self._own_spill = spill_dir is None
        self._spill_path = Path(spill_dir or tempfile.mkdtemp(
            prefix="ipradar-scan-spill-")) / "cidr.sqlite3"
        self._spill_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._spill_path))
        self._db.execute(_SPILL_DDL)
        self._db.commit()
        self._pending = 0           # 攒批计数:到批就 commit,不攒内存
        self._probe_txns: dict[tuple[str, int], object] = {}
        self._open_envs()

    # ── 句柄 ──────────────────────────────────────────────────

    def _open_envs(self) -> None:
        """每个(源,族)自开只读句柄(规格 §4.2 规则 1/2/10):readahead=True
        (顺序扫描吃预读;查询侧 open_env_read 关预读是对随机读的取舍,不适用);
        纪元经 read_ptr 钉死,整个扫描期读同一纪元目录。"""
        for s in self._classified:
            fams = ((s._lmdb_base, 4, 32), (s._lmdb6_base, 6, 128))
            e4 = e6 = None
            for base, fam, bits in fams:
                epoch = read_ptr(base)
                if fam == 4:
                    e4 = epoch
                else:
                    e6 = epoch
                if epoch is None:
                    continue        # 规格规则 1:没有纪元就跳过这一族
                disjoint = read_disjoint_flag(base, epoch)
                target = env_dir(base, epoch)
                env = lmdb.open(str(target), readonly=True, lock=False,
                                subdir=True, readahead=True, max_dbs=2)
                # _PAYLOAD_DB_CACHE 按路径缓存,查询侧可能已为同一路径缓存了
                # 它自己 env 的句柄;本类句柄是另一个 env 对象,串了句柄会把
                # 字典引用解到错误 dbi 上 → 先 pop 强制按本 env 重开(#444,
                # close 时同样 pop,防把已关 env 的句柄留给查询侧)。
                _PAYLOAD_DB_CACHE.pop(env.path(), None)
                self._fam[(s.name, fam)] = _FamilyState(env, epoch,
                                                        disjoint, bits)
            self.epochs[s.name] = (e4, e6)

    # ── 迭代 ──────────────────────────────────────────────────

    def __iter__(self):
        """v4 一套、v6 一套,各走两遍(规格 §4.2 规则 7):先单地址遍
        (归并全部声明分类的源,威胁单地址凑单元),后网段遍(威胁源网段
        记录按 (起点,终点) 凑组)。"""
        for fam in (4, 6):
            t0 = time.perf_counter()
            yield from self._phase_single(fam)
            self.stats["timings"][f"phase_single_v{fam}_s"] = round(
                time.perf_counter() - t0, 3)
            self._db.commit()       # 网段遍要 SELECT,先落盘
            t0 = time.perf_counter()
            yield from self._phase_cidr(fam)
            self.stats["timings"][f"phase_cidr_v{fam}_s"] = round(
                time.perf_counter() - t0, 3)
            for key, txn in list(self._probe_txns.items()):
                if key[1] == fam:
                    txn.abort()
                    del self._probe_txns[key]

    def _probe_txn(self, name: str, fam: int):
        """(源,族)的常驻读事务:覆盖网段探测与网段遍的单地址探针共用。
        归并生成器自己的事务随游标耗尽而关,不能拿来做探测(生成器耗尽后
        事务已关);探测器事务存活整个族相位。"""
        key = (name, fam)
        txn = self._probe_txns.get(key)
        if txn is None:
            st = self._fam[key]
            txn = st.env.begin()
            self._probe_txns[key] = txn
        return txn

    def _phase_single(self, fam: int):
        gens = []
        for s in self._classified:
            st = self._fam.get((s.name, fam))
            if st is None:
                continue
            gens.append(self._iter_family(s, fam, st))
        if not gens:
            return
        merged = heapq.merge(*gens, key=lambda t: t[0])
        for start, grp in itertools.groupby(merged, key=lambda t: t[0]):
            items4 = list(grp)
            singles = [t for t in items4 if t[1] == t[0]]
            # 规格规则 5:一组里没有威胁类源的单地址记录就不产生单元
            if not any(t[2].name in self._threat for t in singles):
                continue
            ip_text = self._addr_text(start, fam)
            evidence_items = self._gather_items(start, fam, singles, None)
            firsts: list[str] = []
            lasts: list[str] = []
            for _, _, src, raw in singles:
                if src.name not in self._threat:
                    continue        # 规格规则 8:时间只从威胁类源取
                ev = self._decode(src, fam, raw)
                f, l = _seen_bounds(ev)
                firsts += f
                lasts += l
            result = fuse_items(ip_text, evidence_items, asof=self._asof)
            self.stats["units"][f"v{fam}_single"] += 1
            yield ScannedUnit(
                ip=ip_text, is_v6=(fam == 6), is_cidr=False,
                first_seen=min(firsts) if firsts else None,
                last_seen=max(lasts) if lasts else None,
                result=result)

    def _phase_cidr(self, fam: int):
        gens = []
        for s in self._classified:
            if s.name not in self._threat:
                continue            # 网段单元只由威胁类源凑组(规格规则 7)
            st = self._fam.get((s.name, fam))
            if st is None or not st.starts:
                continue
            gens.append(self._iter_spilled(s, fam, st))
        if not gens:
            return
        merged = heapq.merge(*gens, key=lambda t: (t[0], t[1]))
        for (start, end), grp in itertools.groupby(
                merged, key=lambda t: (t[0], t[1])):
            items4 = list(grp)
            lo = ipaddress.IPv4Address(start) if fam == 4 \
                else ipaddress.IPv6Address(start)
            hi = ipaddress.IPv4Address(end) if fam == 4 \
                else ipaddress.IPv6Address(end)
            nets = list(ipaddress.summarize_address_range(lo, hi))
            if len(nets) != 1:
                # 与导出器 universe_walk 同款:不恰为一个 CIDR 的范围跳过
                # 并计数(证据不丢——库里记录还在,只是不产单元)
                self.stats["skipped_anomalies"] += 1
                continue
            cidr_text = str(nets[0])
            evidence_items = self._gather_items(start, fam, None, items4)
            firsts: list[str] = []
            lasts: list[str] = []
            for _, _, src, raw in items4:
                ev = self._decode(src, fam, raw)
                f, l = _seen_bounds(ev)
                firsts += f
                lasts += l
            # 判定在网络地址上算(规格规则 4:网段单元用网络地址去算),
            # 与 lookup(网络地址) 同形;单元 ip 字段仍是 CIDR 文本
            result = fuse_items(str(nets[0].network_address),
                                evidence_items, asof=self._asof)
            self.stats["units"][f"v{fam}_cidr"] += 1
            yield ScannedUnit(
                ip=cidr_text, is_v6=(fam == 6), is_cidr=True,
                first_seen=min(firsts) if firsts else None,
                last_seen=max(lasts) if lasts else None,
                result=result)

    # ── 取数件 ────────────────────────────────────────────────

    def _iter_family(self, src, fam: int, st: _FamilyState):
        """(源,族)库的键序惰性游标:单地址记录原样吐出;网段记录落
        sqlite + 记进数组(规格规则 5/6)。跳过 payloads 命名库描述符键
        (LMDB 把 sub-db 注册项落在主库键空间,非数据记录)。"""
        txn = st.env.begin()
        try:
            cur = txn.cursor()
            n_single = 0
            n_cidr = 0
            ok = cur.first()
            while ok:
                if cur.key() == PAYLOADS_NAME:
                    ok = cur.next()
                    continue
                start = int.from_bytes(cur.key(), "big")
                raw = cur.value()
                end = _end_int(raw)
                if not st.disjoint:
                    # 嵌套库:记录自身前缀长必进探测集合(单地址=/32,
                    # size=1 → (0).bit_length()=0 → plen=bits)。查询路径
                    # 的 /32 记录是靠 plen=bits 探测命中的,漏了它覆盖
                    # 探测就假漏(等价性论证见类注释与交付件 §2)。
                    size = end - start + 1
                    st.plens.add(st.bits - (size - 1).bit_length())
                if start == end:
                    n_single += 1
                    yield start, end, src, raw
                else:
                    n_cidr += 1
                    self._spill_cidr(src.name, fam, start, end, raw)
                    st.starts.append(start)
                    st.ends.append(end)
                    if end > st.max_end:
                        st.max_end = end
                ok = cur.next()
            self.stats["records"][src.name] = \
                self.stats["records"].get(src.name, 0) + n_single
            self.stats["cidr_records"][src.name] = \
                self.stats["cidr_records"].get(src.name, 0) + n_cidr
        finally:
            txn.abort()

    def _iter_spilled(self, src, fam: int, st: _FamilyState):
        """网段遍:从 sqlite 按起点序取回该(源,族)的网段记录。
        start_hex 定宽十六进制,ORDER BY 字典序=数值序。"""
        cur = self._db.execute(
            "SELECT start_hex, end_hex, raw FROM cidr "
            "WHERE source=? AND family=? ORDER BY start_hex",
            (src.name, fam))
        for start_hex, end_hex, raw in cur:
            yield int(start_hex, 16), int(end_hex, 16), src, raw

    def _gather_items(self, start: int, fam: int, singles, cidr_group):
        """一个单元地址上的证据齐备(规格规则 4,与查询接口同构):每个
        声明分类的源至多一条——先该地址的单地址记录,没有才覆盖网段记录。
        singles=单地址遍的组内记录(该地址自身);cidr_group=网段遍的组
        (该网段记录本身,即本源对此网络地址的覆盖记录)。items 顺序=
        sources 传入顺序(测试钉);无记录的源不出现在 items 里。"""
        items = []
        by_src_single = {t[2].name: t for t in singles or []}
        by_src_cidr = {t[2].name: t for t in cidr_group or []}
        for s in self._sources:
            if getattr(s, "classification_type", None) is None:
                continue
            st = self._fam.get((s.name, fam))
            if st is None:
                continue
            hit = by_src_single.get(s.name)
            raw = hit[3] if hit is not None else None
            if raw is None:
                # 单地址遍里,本源组内无单地址记录 → 覆盖网段探测;网段遍
                # 里,组内记录优先(它就是网络地址键上的那条记录,等价于
                # 探测结果),非组源走探测
                if cidr_group is not None and s.name in by_src_cidr:
                    raw = by_src_cidr[s.name][3]
                else:
                    idx = st.find_covering(start)
                    if idx is None:
                        continue
                    raw = self._fetch_spilled(s.name, fam, st.starts[idx])
                    if raw is None:
                        continue
            evidence = self._decode(s, fam, raw)
            items.append((s, evidence))
        return items

    def _spill_cidr(self, name: str, fam: int, start: int, end: int,
                    raw: bytes) -> None:
        width = 32 if fam == 6 else 8
        self._db.execute(
            "INSERT OR REPLACE INTO cidr VALUES (?,?,?,?,?)",
            (name, fam, format(start, f"0{width}x"),
             format(end, f"0{width}x"), raw))
        self._pending += 1
        if self._pending >= 5000:
            self._db.commit()
            self._pending = 0

    def _fetch_spilled(self, name: str, fam: int, start: int) -> bytes | None:
        width = 32 if fam == 6 else 8
        row = self._db.execute(
            "SELECT raw FROM cidr WHERE source=? AND family=? AND start_hex=?",
            (name, fam, format(start, f"0{width}x"))).fetchone()
        return row[0] if row is not None else None

    def _decode(self, src, fam: int, raw: bytes):
        """值解码 + 字典引用解引用,事务用探测器事务(存活整个族相位,
        生成器事务已随游标关闭)。ev 是 int = payloads 字典引用,须先解
        引用(decode_value 契约:int 不得直接当证据)。"""
        st = self._fam[(src.name, fam)]
        txn = self._probe_txn(src.name, fam)
        _, ev = decode_value(raw)
        if isinstance(ev, int):
            ev = resolve_evidence(txn, ev, _payloads_db(st.env, txn))
        return ev

    @staticmethod
    def _addr_text(start: int, fam: int) -> str:
        if fam == 4:
            return str(ipaddress.IPv4Address(start))
        return str(ipaddress.IPv6Address(start))

    # ── 收尾 ──────────────────────────────────────────────────

    def close(self) -> None:
        """关全部句柄、删临时 sqlite(规格规则 9)。关完同进程 load_db()
        才能重开这些库(py-lmdb 同进程同路径禁双开);探测事务先于 env 关。"""
        if self._closed:
            return
        self._closed = True
        for txn in self._probe_txns.values():
            try:
                txn.abort()
            except Exception:       # 读事务 abort 失败不吞 close 的其余清理
                logger.warning("scan probe txn abort failed", exc_info=True)
        self._probe_txns.clear()
        for st in self._fam.values():
            _PAYLOAD_DB_CACHE.pop(st.env.path(), None)
            st.env.close()
        self._fam.clear()
        try:
            self._db.commit()
            self._db.close()
        finally:
            try:
                self._spill_path.unlink()
            except FileNotFoundError:
                pass
            if self._own_spill:
                try:
                    self._spill_path.parent.rmdir()
                except OSError:
                    pass

    def __enter__(self) -> "UnitScanner":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_unit_scanner(*, sources=None, asof=None,
                      spill_dir=None) -> UnitScanner:
    """打开按键序扫描器(#444,规格 §4.2)。参数见 UnitScanner.__init__。"""
    return UnitScanner(sources=sources, asof=asof, spill_dir=spill_dir)
