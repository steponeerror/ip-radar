# backend/ipdb/_eval/suite.py
"""Pre-registered acceptance suite (brief §1 v3.1) + fleet model report.

Checks T-1/T-2/T-3/C-1/C-2; every string says corroboration (B2 red line).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import random
from pathlib import Path

from . import config
from .ablation import take_snapshot
from .corpus import Corpus, stable_seed
from .events import extract_events, independent
from .model import SourceScore, beta_binomial_interval, estimate
from .pairwise import assertion_records, pairwise_oc, source_pair_sets

VERDICT_AUTHORITIES = ("spamhaus", "emerging_threats", "threatfox")
ASSET_AUTHORITIES = ("tor_exits", "ip2proxy", "x4bnet_vpn")
SPECIALISTS = ("urlhaus", "otx", "tweetfeed", "x4bnet_vpn")


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for t in range(i, j + 1):
            ranks[order[t]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys) -> float:
    if not xs or not ys:
        return 0.0
    rx, ry = _ranks(list(xs)), _ranks(list(ys))
    if len(set(rx)) == 1 or len(set(ry)) == 1:
        return 0.0
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def _movers(scores):
    return [s for s in scores
            if s.theta is not None and s.n >= config.MODEL_N_FLOOR]


def _t1(events, declared_r, movers):
    names = [s.source for s in movers]
    base = {s.source: s.theta for s in movers}
    worst = 1.0
    for w in (5, 20):
        alt = {s.source: s.theta for s in estimate(events, declared_r, w=w)
               if s.source in base}
        sp = spearman([base[n] for n in names], [alt[n] for n in names])
        worst = min(worst, sp)
    ok = worst >= 0.9
    return {"pass": ok, "detail": f"min pairwise Spearman vs w=10: {worst:.3f} (>=0.9)"}


def _t2(lookup_fn, corpus, declared_r, events, movers, w):
    ips = corpus.all_ips()
    names = [s.source for s in movers]
    base = {s.source: s.theta for s in movers}
    oc_table = pairwise_oc(events.pair_sets)          # frozen from full run
    vals = []
    for f in range(5):
        rng = random.Random(stable_seed(f"jk{f}"))
        drop = set(rng.sample(ips, max(1, len(ips) // 5)))
        keep = [ip for ip in ips if ip not in drop]
        snap = take_snapshot(lookup_fn, keep)
        ev = extract_events(snap, oc_table)           # oc_table frozen
        alt = {s.source: s.theta for s in estimate(ev, declared_r, w=w)
               if s.source in base}
        if len(alt) == len(base):
            vals.append(spearman([base[n] for n in names], [alt[n] for n in names]))
    mean = sum(vals) / len(vals) if vals else 0.0
    return {"pass": mean >= 0.8, "detail": f"mean jackknife Spearman {mean:.3f} over {len(vals)} folds (>=0.8)"}


def _t3(events, movers, w):
    covered = 0
    tested = 0
    oc_table = pairwise_oc(events.pair_sets)
    for s in movers:
        rho = s.rho or 0.5
        pairs = sorted(events.pair_sets[s.source])
        if len(pairs) < 4:
            continue
        rng = random.Random(stable_seed(f"t3:{s.source}"))
        rng.shuffle(pairs)
        half = len(pairs) // 2
        a_pairs, b_pairs = set(pairs[:half]), set(pairs[half:])
        # count events restricted to each half (same predicate, same oc table)
        def _count(sel):
            n = k = 0
            for p in sel:
                if p[1] in events.monopoly_ctypes:
                    continue
                n += 1
                others = set()
                for src, ps in events.pair_sets.items():
                    if src != s.source and p in ps:
                        others.add(src)
                if any(independent(s.source, o, oc_table) for o in others):
                    k += 1
            return n, k
        nA, kA = _count(a_pairs)
        nB, kB = _count(b_pairs)
        if nB < 1:
            continue
        tested += 1
        a = w * rho + kA
        b = w * (1 - rho) + (nA - kA)
        lo, hi = beta_binomial_interval(nB, a, b, level=0.90)
        if lo <= kB <= hi:
            covered += 1
    rate = covered / tested if tested else 0.0
    return {"pass": rate >= 0.8,
            "detail": f"split-half predictive coverage {covered}/{tested} = {rate:.0%} (>=80%)"}


def _c1(scores):
    scored = [s for s in scores if s.theta is not None]
    scored.sort(key=lambda s: -s.theta)
    rank = {s.source: i + 1 for i, s in enumerate(scored)}
    half = (len(scored) + 1) // 2
    fails = []
    exemptions = []
    present = {x.source for x in scores}
    for s in VERDICT_AUTHORITIES:
        if s not in present:
            # C-1 v1.1 (user-ratified 2026-08-31): zero corpus assertions =
            # no evidence, exempt like the asset tier — not a ranking failure.
            exemptions.append(f"{s}: exempt (absent on corpus)")
            continue
        r = rank.get(s)
        if r is None:
            fails.append(f"{s}: unscored")
        elif r > half:
            fails.append(f"{s}: rank {r}/{len(scored)} > {half}")
    for s in ASSET_AUTHORITIES:
        sc = next((x for x in scores if x.source == s), None)
        if sc is None:
            continue
        if sc.monopoly:
            continue
        r = rank.get(s)
        if r is not None and r < 15:
            fails.append(f"{s}: rank {r} < 15/23")
    parts = fails + exemptions
    return {"pass": not fails, "detail": "; ".join(parts) or
            f"verdict tier in top {half}, asset tier ok (ranked of {len(scored)})"}


def _c2(scores):
    fails = []
    for s in SPECIALISTS:
        sc = next((x for x in scores if x.source == s), None)
        if sc is None:
            continue
        if sc.monopoly:
            continue
        if sc.theta is None or not (0.0 < sc.theta < 1.0):
            fails.append(f"{s}: theta {sc.theta}")
    bm = [s for s in scores if s.below_market and s.theta is not None]
    return {"pass": not fails, "detail": "; ".join(fails) or
            f"specialists finite; {len(bm)} below-market flagged (not zeroed)"}


def run_suite(lookup_fn, corpus: Corpus, declared_r=None, w=None) -> dict:
    w = w if w is not None else config.MODEL_W
    ips = corpus.all_ips()
    corpus_fp = {"n_ips": len(ips),
                 "sha8": hashlib.sha256("\n".join(sorted(ips)).encode()).hexdigest()[:8]}
    snap = take_snapshot(lookup_fn, ips)
    pair_sets = source_pair_sets(snap)
    assertion_hist = assertion_records(snap)
    oc_table = pairwise_oc(pair_sets)
    events = extract_events(snap, oc_table)
    scores = estimate(events, declared_r, w=w)
    movers = _movers(scores)
    pinned = [s.source for s in scores
              if s.theta is None or s.n < config.MODEL_N_FLOOR]
    checks = {
        "T1": _t1(events, declared_r, movers),
        "T2": _t2(lookup_fn, corpus, declared_r, events, movers, w),
        "T3": _t3(events, movers, w),
        "C1": _c1(scores),
        "C2": _c2(scores),
    }
    return {"kind": "model", "w": w, "scores": scores, "checks": checks,
            "corpus": corpus_fp, "pairs": assertion_hist,
            "movers": [s.source for s in movers], "pinned": pinned,
            "monopoly_ctypes": sorted(events.monopoly_ctypes)}


def write_model_report(result: dict, out_dir: Path) -> tuple[Path, Path]:
    d = Path(out_dir) / "model"
    d.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    def _score_dict(s: SourceScore):
        return {"source": s.source, "theta": s.theta, "ci_lo": s.ci_lo,
                "ci_hi": s.ci_hi, "n": s.n, "k": s.k, "rho": s.rho,
                "evidence": s.evidence,
                "fountain_suspect": s.fountain_suspect,
                "unique_share": s.unique_share,
                "below_market": s.below_market, "monopoly": s.monopoly,
                "declared_r": s.declared_r}
    payload = {
        "kind": "model",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).date().isoformat(),
        "w": result["w"],
        "corpus": result["corpus"],
        "pairs": result["pairs"],
        "checks": result["checks"],
        "movers": result["movers"],
        "pinned": result["pinned"],
        "monopoly_ctypes": result["monopoly_ctypes"],
        "scores": [_score_dict(s) for s in result["scores"]],
    }
    md = d / f"model-{ts}.md"
    js = d / f"model-{ts}.json"
    lines = ["# Source corroboration-contrast model (advisory)", "",
             f"corpus: {result['corpus']['n_ips']} ips @ {result['corpus']['sha8']}", "",
             "| source | theta | 90% CI | n | k | rho | evidence | below-mkt | mono | fountain | unique | declared_r |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in result["scores"]:
        if s.theta is not None:
            cells = [s.source, f"{s.theta:.3f}",
                     f"[{s.ci_lo:.3f}, {s.ci_hi:.3f}]"]
        else:
            cells = [s.source, "—", "—"]
        cells += [str(s.n), str(s.k),
                  f"{s.rho:.3f}" if s.rho is not None else "—",
                  "present" if s.evidence else "none",
                  str(s.below_market), str(s.monopoly),
                  "suspect" if s.fountain_suspect else "—",
                  "—" if s.unique_share is None else f"{s.unique_share:.2f}",
                  "—" if s.declared_r is None else f"{s.declared_r:.2f}"]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Checks", ""]
    for name, chk in result["checks"].items():
        lines.append(f"- **{name}: {'PASS' if chk['pass'] else 'FAIL'}** — {chk['detail']}")
    lines += ["",
              "_High unique share with no evidence = specialist / uncovered niche, "
              "not necessarily weak (coverage is orthogonal to corroboration)._",
              "_Monopoly types are information-theoretically uncorroboratable; "
              "asserters are unscored by design and route through the authority "
              "tier in any future D2 loop._"]
    lines += ["", "_Corroboration semantics (audit B2): never read theta as accuracy; "
               "advisory only — declared_r stays authoritative until Q4 graduation._"]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    js.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return md, js
