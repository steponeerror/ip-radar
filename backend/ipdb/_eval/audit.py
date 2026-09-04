"""Lineage audit (B1): read persisted model-report history, judge copying
direction via containment + first-seen time priority (Dong principle: the
later lister of a shared assertion set is the copier). Advisory only —
production DERIVED_SOURCES stays a human-committed constant.
"""
import json
import re
from pathlib import Path

from .._logodds import DERIVED_SOURCES

_TS = re.compile(r"model-(\d{8}-\d{6})\.json$")
CONTAIN_BAR = 0.9      # mirror must be >=90% inside its upstream
TIME_BAR = 0.6         # upstream lists first on >=60% of dated shared pairs
MIN_SHARED = 10        # dated shared assertions needed for a time verdict
MIN_COPIERS = 2        # per FOUNTAIN_MIN_CONTAINEES precedent


def load_history(model_dir: Path) -> list[dict]:
    files = sorted((Path(model_dir)).glob("model-*.json"),
                   key=lambda p: _TS.search(p.name).group(1))
    out = []
    for f in files:
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if d.get("kind") == "model" and d.get("pairs"):
            out.append(d)
    return out


def _sets(pairs_by_src: dict) -> dict[str, set]:
    return {s: {(ip, c) for ip, c, _ in lst}
            for s, lst in pairs_by_src.items()}


def _dated(pairs_by_src: dict) -> dict[str, dict]:
    return {s: {(ip, c): fs for ip, c, fs in lst if fs}
            for s, lst in pairs_by_src.items()}


def lineage_audit(model_dir: Path) -> dict:
    runs = load_history(model_dir)
    # union across runs (history-aware: a pair listed in ANY run counts)
    union: dict[str, list] = {}
    dated: dict[str, dict] = {}
    for r in runs:
        for s, lst in r["pairs"].items():
            union.setdefault(s, [])
            seen = {(a, b) for a, b, _ in union[s]}
            union[s].extend(x for x in lst if (x[0], x[1]) not in seen)
    sets = _sets(union)
    for s, lst in union.items():
        m = {}
        for ip, c, fs in lst:
            if fs and (ip, c) not in m:
                m[(ip, c)] = fs
        dated[s] = m
    names = sorted(sets)
    relations: dict[str, list] = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sa, sb = sets.get(a, set()), sets.get(b, set())
            if len(sa) < MIN_SHARED or len(sb) < MIN_SHARED:
                continue
            inter = sa & sb
            if len(inter) < MIN_SHARED:
                continue
            frac_in_a = len(inter) / len(sa)   # share of a inside the pair
            frac_in_b = len(inter) / len(sb)
            da, db = dated.get(a, {}), dated.get(b, {})
            shared_dated = [p for p in inter if p in da and p in db]
            if shared_dated:
                a_first = sum(1 for p in shared_dated if da[p] <= db[p])
                b_first = len(shared_dated) - a_first
            else:
                a_first = b_first = 0
            # b is copier when b is highly contained in a AND a lists first
            if (frac_in_b >= CONTAIN_BAR and shared_dated
                    and a_first / len(shared_dated) >= TIME_BAR):
                relations.setdefault(b, []).append(
                    (a, frac_in_b, a_first, b_first))
            elif (frac_in_a >= CONTAIN_BAR and shared_dated
                    and b_first / len(shared_dated) >= TIME_BAR):
                relations.setdefault(a, []).append(
                    (b, frac_in_a, a_first, b_first))
    recommended = sorted(s for s, rels in relations.items()
                         if len(rels) >= MIN_COPIERS)
    false_acc = [s for s in recommended if s not in DERIVED_SOURCES]
    missing = sorted(DERIVED_SOURCES - set(recommended))
    c3 = {"pass": not false_acc, "false_accusations": false_acc,
          "missing_known": missing}
    return {"recommended_derived": recommended, "relations": relations,
            "c3": c3}
