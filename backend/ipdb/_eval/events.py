"""Corroboration events under the lineage/OC independence predicate.

B2 red line: everything here measures CORROBORATION (co-assertion by a
lineage-independent, low-overlap source), never correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config
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


def independent(i: str, j: str, oc_table: dict) -> bool:
    """True iff i and j may corroborate each other (G3 hard exclusion)."""
    if _cluster(i) == _cluster(j):
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
