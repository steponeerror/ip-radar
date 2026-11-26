"""Corroboration events under the lineage/OC independence predicate.

B2 red line: everything here measures CORROBORATION (co-assertion by a
lineage-independent, low-overlap source), never correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .. import _logodds
from .pairwise import source_pair_sets


@dataclass
class SourceEvents:
    n: int = 0                                   # asserted pairs, non-monopoly ctypes
    k: int = 0                                   # corroborated among them
    by_ctype: dict[str, tuple[int, int]] = field(default_factory=dict)  # ctype -> (n, k)


@dataclass
class Events:
    pair_sets: dict[str, set] = field(default_factory=dict)
    monopoly_ctypes: set[str] = field(default_factory=set)
    per_source: dict[str, SourceEvents] = field(default_factory=dict)


def _cluster(s: str) -> str:
    return config.LINEAGE_CLUSTERS.get(s, s)


def _republishes_parent() -> dict[str, str]:
    """转载链并查集父表(卡2上半,#464):边 = LINEAGE_ANCHORS(registry
    按 republishes 类属性灌装——计分与评测读同一份声明;无 registry 时
    读兜底种子)。仅声明边入集(现存 ~6 条),每次调用重建不缓存——
    registry fill-in-place 只改内容不改对象身份,身份键缓存会脏读。"""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]   # 路径减半
            x = parent[x]
        return x

    for target, anchors in _logodds.LINEAGE_ANCHORS.items():
        for a in anchors:
            rt, ra = find(target), find(a)
            if rt != ra:
                parent[rt] = ra
    return parent


def same_republish_chain(i: str, j: str) -> bool:
    """i、j 是否经转载声明相连(含传递:转载链传递闭包,#464 卡2上半)。
    评测判独立(independent / oc_suspicion_pairs)与生产计分
    (LINEAGE_ANCHORS)读同一份声明;链外源(未入任何声明)恒独立。
    评测闭包 ⊇ 生产表由 test_eval_config 钉(两边漂移即红)。"""
    if i == j:
        return False
    parent = _republishes_parent()
    if i not in parent or j not in parent:
        return False

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    return find(i) == find(j)


def independent(i: str, j: str, oc_table: dict) -> bool:
    """True iff i and j may corroborate each other (G3 hard exclusion)."""
    if _cluster(i) == _cluster(j):
        return False
    if same_republish_chain(i, j):
        # 转载链上互不独立(#464):同场共现的转载者与原创互为回声,
        # 不算印证(哲学 3);声明清单见各源类 republishes 旁注
        # (#469 评审 B8:此处不抄清单,抄一份漂移一份)。
        return False
    return oc_table.get(frozenset((i, j)), 0.0) <= config.OC_EXCLUSION


def extract_events(snap: dict, oc_table: dict) -> Events:
    pair_sets = source_pair_sets(snap)

    # asserters per ctype (over all pairs observed with that ctype)
    ctype_asserters: dict[str, set[str]] = {}
    pair_asserters: dict[tuple[str, str], set[str]] = {}
    for src, pairs in pair_sets.items():
        for p in pairs:
            pair_asserters.setdefault(p, set()).add(src)
            ctype_asserters.setdefault(p[1], set()).add(src)
    monopoly = {c for c, a in ctype_asserters.items() if len(a) <= 1}

    ev = Events(pair_sets=pair_sets, monopoly_ctypes=monopoly)
    for src, pairs in pair_sets.items():
        se = SourceEvents()
        for p in pairs:
            if p[1] in monopoly:
                continue
            ctype_n, ctype_k = se.by_ctype.get(p[1], (0, 0))
            se.n += 1
            ctype_n += 1
            others = pair_asserters.get(p, set()) - {src}
            if any(independent(src, o, oc_table) for o in others):
                se.k += 1
                ctype_k += 1
            se.by_ctype[p[1]] = (ctype_n, ctype_k)
        ev.per_source[src] = se
    return ev


def market_rates(events: Events, leave_out: str | None = None) -> dict[str, float]:
    """Per-ctype fleet corroboration rate, Jeffreys-smoothed (K+0.5)/(N+1).

    leave_out excludes one source's (n, k) — used as that source's G1′ prior
    center so a source never props up its own market.
    """
    tot: dict[str, list[int]] = {}               # ctype -> [N, K]
    for src, se in events.per_source.items():
        if leave_out is not None and src == leave_out:
            continue
        for ctype, (n, k) in se.by_ctype.items():
            acc = tot.setdefault(ctype, [0, 0])
            acc[0] += n
            acc[1] += k
    return {c: (k + 0.5) / (n + 1) for c, (n, k) in tot.items()}
