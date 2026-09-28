"""λ_s prequential confirmation-rate instrument (W1).

λ_s = share of source s's round-t UNIQUE assertions (pairs only s
asserted in round t) that any lineage-independent source re-asserts in
a later round t+1..T. Corroboration under the B2 red line: it measures
co-assertion by independent fleets, never correctness.

Consumes persisted model-*.json history directly (no runtime DB): the
`pairs` payload {source: [[ip, ctype, first_seen], ...]}, T3's
`source_health` (absent in pre-T3 rounds → treated as healthy), and the
round's `scores` for the preregistration θ̂ split.

Preregistration hygiene: sources are grouped by their ASSERTING round's
θ̂ (median split; θ̂ None / unscored sources enter no group), confirmation
events are pooled across windows, and one two-sided Fisher exact test
(stdlib hypergeometric sum, no scipy) compares the groups — decided
before looking at any λ.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import statistics
from pathlib import Path

from .events import independent
from .pairwise import pairwise_oc

_Z95 = 1.96


def rounds_from_history(model_dir) -> list[dict]:
    """Chronological round list from persisted model-*.json reports.

    Same-date reports collapse to the lexicographic-last filename
    (convention shared with _rc_history / the §7 spike). Each round:
    {"date", "pairs", "source_health" ({} when the round predates T3),
    "scores"}. Files that are not model reports or lack pairs are skipped.
    """
    by_date: dict[str, tuple[str, dict]] = {}
    for f in sorted(Path(model_dir).glob("model-*.json")):
        try:
            r = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(r, dict) or r.get("kind") != "model" or not r.get("pairs"):
            continue
        date = str(r.get("generated_at") or "")
        if date not in by_date or f.stem > by_date[date][0]:
            by_date[date] = (f.stem, r)
    return [{"date": d,
             "pairs": by_date[d][1]["pairs"],
             "source_health": by_date[d][1].get("source_health") or {},
             "scores": by_date[d][1].get("scores")}
            for d in sorted(by_date)]


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (stdlib, math.comb).

    Sum of hypergeometric point probabilities no smaller than the
    observed table's, over the support only — the classic convention.
    Exact integer arithmetic; float only at the final division.
    """
    r1, c1, c2 = a + b, a + c, b + d
    n = r1 + c + d
    denom = math.comb(n, r1)
    pv = lambda x: math.comb(c1, x) * math.comb(c2, r1 - x)
    obs = pv(a)
    lo, hi = max(0, r1 - c2), min(r1, c1)
    num = sum(pv(x) for x in range(lo, hi + 1) if pv(x) <= obs)
    return num / denom


def _wilson(k: int, n: int) -> tuple[float | None, float | None]:
    """Wilson 95% interval for k/n; (None, None) when n == 0."""
    if n <= 0:
        return None, None
    z2 = _Z95 * _Z95
    p = k / n
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (_Z95 / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


def _pair_sets(pairs_by_src: dict) -> dict[str, set[tuple[str, str]]]:
    return {s: {(ip, ctype) for ip, ctype, *_ in lst}
            for s, lst in pairs_by_src.items()}


def _thetas(scores) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for s in scores or []:
        if isinstance(s, dict) and s.get("source"):
            out[s["source"]] = s.get("theta")
    return out


def _confirmed(uniq: set, s: str, later, oc_by_round: list[dict]) -> int:
    """Count unique pairs re-asserted in a later round by a source that is
    lineage-independent of s per THAT round's OC table (corroboration
    event lives in the confirming round; missing OC entry → 0 overlap)."""
    k = 0
    for pr in uniq:
        if any(independent(s, o, oc_by_round[u]) for u, o in later.get(pr, [])):
            k += 1
    return k


def _group(n: int, k: int) -> dict:
    lo, hi = _wilson(k, n)
    return {"n_uniq": n, "n_conf": k, "lam": (k / n) if n else None,
            "ci_lo": lo, "ci_hi": hi}


def compute_temporal(rounds: list[dict]) -> dict:
    """Pure λ_s computation over rounds from rounds_from_history."""
    n = len(rounds)
    meta = []
    for r in rounds:
        ps = _pair_sets(r["pairs"])
        meta.append({"date": r["date"], "pair_sets": ps,
                     "oc": pairwise_oc(ps),
                     "health": r.get("source_health") or {},
                     "theta": _thetas(r.get("scores"))})
    oc_by_round = [m["oc"] for m in meta]

    windows = []
    for t in range(n - 1):
        asserters: dict[tuple, set] = {}
        for s, ps in meta[t]["pair_sets"].items():
            for pr in ps:
                asserters.setdefault(pr, set()).add(s)
        uniques: dict[str, set] = {}
        for pr, srcs in asserters.items():
            if len(srcs) == 1:
                uniques.setdefault(next(iter(srcs)), set()).add(pr)
        later: dict[tuple, list[tuple[int, str]]] = {}
        for u in range(t + 1, n):
            for s, ps in meta[u]["pair_sets"].items():
                for pr in ps:
                    later.setdefault(pr, []).append((u, s))

        per_source, skipped = {}, []
        for s in sorted(meta[t]["pair_sets"]):
            # 轮次健康规则:断言轮 rc==0 → 该源该窗口跳过(skipped 记名);
            # 无 source_health 的旧轮视为健康(历史轮无仪器不追责)。
            h = meta[t]["health"].get(s)
            if isinstance(h, dict) and h.get("rc") == 0:
                skipped.append(s)
                continue
            uniq = uniques.get(s, set())
            per_source[s] = _group(len(uniq), _confirmed(uniq, s, later, oc_by_round))
        windows.append({"from": meta[t]["date"], "to": meta[n - 1]["date"],
                        "per_source": per_source, "skipped": skipped})

    # preregistration: pool confirmation events by asserting-round θ̂ split
    above = [0, 0]
    below = [0, 0]
    for t, w in enumerate(windows):
        ths = sorted(v for v in meta[t]["theta"].values() if v is not None)
        if not ths:
            continue
        med = statistics.median(ths)
        for s, st in w["per_source"].items():
            v = meta[t]["theta"].get(s)
            if v is None:
                continue
            acc = above if v >= med else below
            acc[0] += st["n_uniq"]
            acc[1] += st["n_conf"]
    la = (above[1] / above[0]) if above[0] else None
    lb = (below[1] / below[0]) if below[0] else None
    if la is None or lb is None:
        direction = None
    elif la > lb:
        direction = "above>below"
    elif lb > la:
        direction = "below>above"
    else:
        direction = "equal"
    return {
        "kind": "temporal",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).date().isoformat(),
        "n_rounds": n,
        "rounds": [m["date"] for m in meta],
        "windows": windows,
        "preregistration": {
            "above": _group(*above),
            "below": _group(*below),
            "fisher_p": fisher_exact(above[1], above[0] - above[1],
                                     below[1], below[0] - below[1]),
            "direction": direction,
        },
    }


def temporal_report(model_dir, out_dir=None) -> dict:
    """Compute the λ_s report over persisted history; when out_dir is given
    (and rounds suffice) also persist it as <out_dir>/temporal-<ts>.json."""
    rep = compute_temporal(rounds_from_history(model_dir))
    if out_dir is not None and rep["n_rounds"] >= 2:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        p = d / f"temporal-{ts}.json"
        p.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        rep["report_path"] = str(p)
    return rep
