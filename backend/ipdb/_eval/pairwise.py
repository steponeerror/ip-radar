"""All-source pairwise OC table (audit D4/B4 first deliverable).

One full-fleet corpus snapshot -> per-source asserted (ip, ctype) pair sets
-> pairwise overlap coefficients. Pure; consumed by the event layer
(events.py) and available to oc_suspicion_pairs as the real baseline
(replacing the v1 `{}` placeholder).
"""
from __future__ import annotations


def source_pair_sets(snap: dict) -> dict[str, set[tuple[str, str]]]:
    """{source: {(ip, ctype), ...}} over all classification hits in snap."""
    out: dict[str, set[tuple[str, str]]] = {}
    for ip, res in snap.items():
        for ctype, ca in (res.get("classifications") or {}).items():
            for s in ca.get("sources") or []:
                name = s.get("source")
                if name:
                    out.setdefault(name, set()).add((ip, ctype))
    return out


def pairwise_oc(pair_sets: dict[str, set]) -> dict[frozenset[str], float]:
    """OC = |A∩B| / min(|A|,|B|) for every pair with both sides non-empty."""
    names = sorted(pair_sets)
    out: dict[frozenset[str], float] = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sa, sb = pair_sets[a], pair_sets[b]
            if not sa or not sb:
                continue
            inter = len(sa & sb)
            if inter:
                out[frozenset((a, b))] = inter / min(len(sa), len(sb))
            else:
                out[frozenset((a, b))] = 0.0
    return out


def containment(pair_sets: dict[str, set]) -> dict[frozenset[str], tuple[float, float]]:
    """Directed containment per source pair (spec 2026-09-01 Part 2).

    {frozenset({a,b}): (|A∩B|/|A|, |A∩B|/|B|)} with a < b lexicographically —
    tuple order is deterministic despite the unordered key. (0.3, 1.0) on
    (a, b) means b is fully contained in a. Pairs with an empty side are
    omitted. Unlike pairwise_oc this is asymmetric: it carries direction.
    """
    names = sorted(pair_sets)
    out: dict[frozenset[str], tuple[float, float]] = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sa, sb = pair_sets[a], pair_sets[b]
            if not sa or not sb:
                continue
            inter = len(sa & sb)
            out[frozenset((a, b))] = (inter / len(sa), inter / len(sb))
    return out
