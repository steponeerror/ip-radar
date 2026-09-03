# backend/ipdb/_eval/dsem_cli.py
"""--dsem runner: DS-EM over the live corpus snapshot + T-3 fair fight.

Advisory artifact only — pi_hat is a latent TRUTH-rate estimate
(silence-as-negative, declared-r anchored), while theta / T-3 measure
CORROBORATION against the ctype market; neither is accuracy and neither
ever feeds SOURCE_RELIABILITY (red line, brief 5.6). The fair fight
re-runs the suite's T-3 split-half predictive-coverage check under three
prior settings — market rho as-is, declared_r override, pi-hat headline
override — so the three priors compete on identical events. Adopting any
measured value requires a human-reviewed PR; this report only advises.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import replace
from pathlib import Path

from . import config
from .ablation import take_snapshot
from .dsem import run_dsem
from .events import extract_events
from .model import estimate
from .pairwise import pairwise_oc, source_pair_sets
from .suite import _movers, _t3

_T3_RATE = re.compile(r"coverage (\d+)/(\d+)")


def _t3_rate(detail: str) -> float | None:
    """Coverage rate as a float parsed from _t3's detail line (R7: the
    fair fight compares rates, not the human-readable strings). None on
    mismatch or 0/0 (no testable movers) — caller then reports beats=None."""
    m = _T3_RATE.search(detail)
    if not m:
        return None
    covered, tested = int(m.group(1)), int(m.group(2))
    return covered / tested if tested else None


def _json_safe_dsem(dsem: dict) -> dict:
    """Stringify (source, ctype) tuple keys: json.dumps rejects tuple keys
    and its default= hook is never consulted for keys."""
    return {**dsem,
            "pi_hat": {f"{s}|{c}": v for (s, c), v in dsem["pi_hat"].items()},
            "spread": {f"{s}|{c}": v for (s, c), v in dsem["spread"].items()}}


def run_dsem_report(lookup_fn, corpus, declared_r, out_dir=None) -> dict:
    """Snapshot -> events -> the three-prior T-3 fair fight + DS-EM run.

    Override rule (plan semantics): override value wins when present and
    non-None, else the mover's existing market rho stands.
    """
    snap = take_snapshot(lookup_fn, corpus.all_ips())
    pair_sets = source_pair_sets(snap)
    events = extract_events(snap, pairwise_oc(pair_sets))
    dsem = _json_safe_dsem(run_dsem(pair_sets, declared_r))
    movers = _movers(estimate(events, declared_r))
    market = _t3(events, movers, config.MODEL_W)
    decl = _t3(events, [replace(s, rho=declared_r.get(s.source) or s.rho)
                        for s in movers], config.MODEL_W)
    pihat = _t3(events, [replace(s, rho=dsem["headline"].get(s.source) or s.rho)
                         for s in movers], config.MODEL_W)
    pr, dr = _t3_rate(pihat["detail"]), _t3_rate(decl["detail"])
    beats = (pr >= dr) if pr is not None and dr is not None else None
    res = {"kind": "dsem", "dsem": dsem,
           "fair_fight": {"market_t3": market["detail"],
                          "declared_t3": decl["detail"],
                          "pihat_t3": pihat["detail"],
                          "pihat_beats_declared": beats}}
    if out_dir is not None:
        d = Path(out_dir) / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        (d / f"dsem-{ts}.json").write_text(
            json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res
