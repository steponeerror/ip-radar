"""Lineage audit (B1/W3 v2): read persisted model-report history and judge
copying direction by FORWARD FLOW asymmetry — a pair asserted by a in round
t, absent from b in round t, and picked up by b in t+1..T flows a→b; the net
outflowing side is the source. Replaces the naive first-seen Dong clock:
the §7 spike showed aggregators keep history while originals churn, so
observed first-seen inverts direction (the spamhaus counterexample).
Containment survives as a display column only. Advisory — production
DERIVED_SOURCES stays a human-committed constant.
"""
import json
import re
from pathlib import Path

from .._logodds import DERIVED_SOURCES

_TS = re.compile(r"model-(\d{8}-\d{6})\.json$")
MIN_SHARED = 10        # union-shared assertions needed to judge a pair
MIN_ROUNDS = 3         # <3 rounds → no confirmed verdicts (2 rounds = not-yet)
FLOW_MIN = 3           # forward-flow pairs needed for a direction verdict
FLOW_ASYM = 1.5        # asymmetry bar: fab >= FLOW_ASYM * fba (and vice versa)
MIN_COPIERS = 2        # confirmed in-edges needed to recommend a DERIVED
RECALL_BAR = 0.8       # C-3: recall >= 4/5 of known DERIVED_SOURCES


def load_history(model_dir: Path) -> list[dict]:
    """Chronological round list from model-*.json reports. Same-date
    reports collapse to the lexicographic-last filename (round-parsing
    convention shared with temporal.rounds_from_history)."""
    by_date: dict[str, dict] = {}
    for f in sorted(Path(model_dir).glob("model-*.json")):
        m = _TS.search(f.name)
        if not m:
            continue
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if d.get("kind") == "model" and d.get("pairs"):
            by_date[m.group(1)[:8]] = d
    return [by_date[k] for k in sorted(by_date)]


def forward_flow(pairs_by_round, a: str, b: str) -> tuple[int, int]:
    """前向流计数:抄袭方向由“谁先断言、谁滞后捡起”的不对称决定,
    同一 pair 只在其首个合格轮计一次(去重),后续复断/丢弃不重计。

    (a→b, b→a) forward-flow counts over per-round pair sets
    ({source: {(ip, ctype), ...}} per round). A pair flows a→b when a
    asserts it in round t, b does not, and b picks it up in t+1..T —
    counted once, at its first qualifying round. Symmetric for b→a."""
    n = len(pairs_by_round)

    def one(src: str, dst: str) -> int:
        counted: set = set()
        for t in range(n):
            fresh = (pairs_by_round[t].get(src, set())
                     - pairs_by_round[t].get(dst, set()) - counted)
            for pr in fresh:
                if any(pr in pairs_by_round[u].get(dst, set())
                       for u in range(t + 1, n)):
                    counted.add(pr)
        return len(counted)

    return one(a, b), one(b, a)


def lineage_audit(model_dir: Path) -> dict:
    """谱系审计:读 model 历史报告,对每对源做前向流三态判定
    (confirmed / not-yet / no-relation),并跑 C-3 双向检查(0 误伤 ∧
    recall ≥ 4/5);advisory,生产 DERIVED_SOURCES 仍为人工提交常量。

    Reads persisted model-*.json rounds via load_history, judges each
    source pair by forward_flow asymmetry (FLOW_MIN / FLOW_ASYM, only
    with >= MIN_ROUNDS rounds and >= MIN_SHARED shared assertions), and
    recommends DERIVED candidates holding >= MIN_COPIERS confirmed
    in-edges. Containment is a display column only."""
    runs = load_history(model_dir)
    n = len(runs)
    rounds = [{s: {(ip, c) for ip, c, *_ in lst}
               for s, lst in r["pairs"].items()} for r in runs]
    union: dict[str, set] = {}
    for ps in rounds:
        for s, pairs in ps.items():
            union.setdefault(s, set()).update(pairs)
    names = sorted(union)
    relations: dict[str, list] = {}
    pairs_out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = len(union[a] & union[b])
            row = {"a": a, "b": b, "shared": shared,
                   "contain_a": shared / len(union[a]) if union[a] else 0.0,
                   "contain_b": shared / len(union[b]) if union[b] else 0.0}
            if shared < MIN_SHARED:
                row["state"] = "no-relation"
            else:
                fab, fba = forward_flow(rounds, a, b)
                row["fab"], row["fba"] = fab, fba
                copier = None
                if n >= MIN_ROUNDS:
                    if fab >= FLOW_MIN and fab >= FLOW_ASYM * fba:
                        copier = b
                    elif fba >= FLOW_MIN and fba >= FLOW_ASYM * fab:
                        copier = a
                if copier is None:
                    row["state"] = "not-yet"
                else:
                    row["state"] = "confirmed"
                    row["copier"] = copier
                    upstream = b if copier == a else a
                    contain = row["contain_b"] if copier == b else row["contain_a"]
                    f_in = fab if copier == b else fba   # upstream → copier
                    f_out = fba if copier == b else fab
                    relations.setdefault(copier, []).append(
                        (upstream, f_in, f_out, contain))
            pairs_out.append(row)
    recommended = sorted(s for s, rels in relations.items()
                         if len(rels) >= MIN_COPIERS)
    false_acc = [s for s in recommended if s not in DERIVED_SOURCES]
    hits = [s for s in recommended if s in DERIVED_SOURCES]
    recall = len(hits) / len(DERIVED_SOURCES) if DERIVED_SOURCES else 0.0
    c3 = {"pass": not false_acc and recall >= RECALL_BAR,
          "false_accusations": false_acc,
          "missing_known": sorted(DERIVED_SOURCES - set(recommended)),
          "recall": recall}
    return {"kind": "lineage-audit", "n_rounds": n,
            "recommended_derived": recommended, "relations": relations,
            "pairs": pairs_out, "c3": c3}
