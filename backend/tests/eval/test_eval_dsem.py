# backend/tests/eval/test_eval_dsem.py
import math
import random
from collections import Counter

from ipdb._eval.dsem import run_dsem


def _plant(seed=7, n_src=15, n_ctype=4, n_true=60, n_false=20):
    rng = random.Random(seed)
    srcs = [f"synth{i}" for i in range(n_src)]
    r_true = {s: rng.uniform(0.55, 0.95) for s in srcs}
    declared = {s: min(0.95, max(0.5, r_true[s] + rng.gauss(0, 0.07)))
                for s in srcs}
    pi_true, data = {}, {s: set() for s in srcs}
    for c in range(n_ctype):
        ct = str(c)
        tp = {(f"i{c}t{j}", ct) for j in range(n_true)}
        fp = {(f"i{c}f{j}", ct) for j in range(n_false)}
        for s in srcs:
            pi_true[(s, ct)] = min(0.98, max(0.3,
                                     r_true[s] + rng.gauss(0, 0.05)))
            for p in tp:
                if rng.random() < pi_true[(s, ct)]:
                    data[s].add(p)
            for p in fp:
                if rng.random() < 0.05:
                    data[s].add(p)
    return data, pi_true, declared


def test_planted_recovery_at_n_scaled_tolerance():
    data, pi_true, declared = _plant()
    res = run_dsem(data, declared, restarts=4)
    counts = Counter((s, c) for s, ps in data.items() for (_, c) in ps)
    ok = 0
    for k, truth in pi_true.items():
        est = res["pi_hat"][k]
        tol = max(0.05, 2.0 * math.sqrt(est * (1 - est) / counts[k]))
        ok += abs(est - truth) <= tol
    assert ok / len(pi_true) >= 0.9      # C-4 gate (amended tolerance)


def test_headline_and_diagnostics_shape():
    data, _, declared = _plant()
    res = run_dsem(data, declared, restarts=2)
    assert 0.0 <= res["theta0"] <= 1.0
    for s in declared:
        assert res["headline"][s] is None or 0.0 <= res["headline"][s] <= 1.0
        assert 0.0 <= res["solo_share"][s] <= 1.0
        assert all(v >= 0 for v in res["spread"].values())


def test_exclude_solo_shrinks_evidence_for_biased_source():
    # Solo assertions must live in a ctype no other covered source witnesses:
    # that is the self-sampling-bias case exclude_solo exists for (spec 7 F4).
    # If solo pairs share a ctype with corroborated pairs, silence-as-negative
    # from the good sources already deflates them, leaving only second-order
    # terms and the exclusion contract unexercised.
    data = {"good": {("ip1", "a"), ("ip2", "a")},
            "g2": {("ip1", "a"), ("ip2", "a")},
            "junk": {("ip1", "a"), ("ip2", "a"), ("j1", "b"), ("j2", "b")}}
    # junk's (j1, b) / (j2, b) have no other asserter: including them lets
    # junk self-corroborate (pi inflated above its declared 0.8); excluding
    # them deflates pi back toward the declared anchor. good corroborated by
    # g2 in ctype "a" either way.
    declared = {"good": 0.8, "g2": 0.8, "junk": 0.8}
    with_solo = run_dsem(data, declared, restarts=2, exclude_solo=False)
    without = run_dsem(data, declared, restarts=2, exclude_solo=True)
    assert without["headline"]["junk"] <= with_solo["headline"]["junk"]
