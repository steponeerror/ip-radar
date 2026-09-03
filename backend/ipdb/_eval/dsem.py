# backend/ipdb/_eval/dsem.py
"""DS-EM: one-sided Dawid-Skene with silence-as-negative (spike-validated
2026-09-02). Estimates per-source per-ctype latent-truth rates pi. ADVISORY
ONLY — never feeds SOURCE_RELIABILITY (red line, brief 5.6).
Semantics: pi = P(assertion true | source asserts in this ctype) — truth-rate,
NOT corroboration (theta stays the corroboration measure)."""
import math
import random
from collections import Counter, defaultdict

W_PI, W_PHI = 10.0, 20.0


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _lg(p):
    p = _clamp(p, 0.005, 0.995)
    return math.log(p / (1 - p))


def _sg(x):
    return 1.0 / (1.0 + math.exp(-x))


def _em_once(pi_data, declared_r, iters, seed, min_cover=2, tol=1e-5,
             solo_pairs=frozenset()):
    rng = random.Random(seed)
    ctype_of, asserters = {}, defaultdict(set)
    asserted = defaultdict(set)
    for s, lst in pi_data.items():
        for p, c in lst:
            ctype_of[p] = c
            asserters[p].add(s)
            asserted[(s, c)].add(p)
    universe = sorted(ctype_of)
    by_ctype = defaultdict(list)
    for p in universe:
        by_ctype[ctype_of[p]].append(p)
    covered = {(s, c): by_ctype[c] for (s, c), own in asserted.items()
               if len(own) >= min_cover}
    theta0 = 0.5
    w = {p: _clamp(0.5 + rng.uniform(-0.15, 0.15), 0.05, 0.95)
         for p in universe}
    pi = {(s, c): _clamp(declared_r.get(s, 0.5) + rng.uniform(-0.03, 0.03),
                         0.05, 0.97) for (s, c) in covered}
    phi = {(s, c): _clamp(0.05 + rng.uniform(-0.01, 0.01), 0.01, 0.2)
           for (s, c) in covered}
    for _ in range(iters):
        for p in universe:
            c = ctype_of[p]
            acc = _lg(theta0)
            for (s, cc) in covered:
                if cc != c:
                    continue
                if s in asserters[p]:
                    acc += _lg(pi[(s, c)]) - _lg(phi[(s, c)])
                else:
                    acc += _lg(1 - pi[(s, c)]) - _lg(1 - phi[(s, c)])
            w[p] = _sg(acc)
        delta = 0.0
        for (s, c), pairs in covered.items():
            mass_t = sum(w[p] for p in pairs)
            mass_f = sum(1 - w[p] for p in pairs)
            ev_t = sum(w[p] for p in asserted[(s, c)] if p not in solo_pairs)
            ev_f = sum(1 - w[p] for p in asserted[(s, c)]
                       if p not in solo_pairs)
            n_pi = W_PI + (mass_t - sum(w[p] for p in asserted[(s, c)]
                                        if p in solo_pairs))
            new_pi = _clamp((W_PI * declared_r.get(s, 0.5) + ev_t) / n_pi,
                            0.02, 0.98)
            new_phi = _clamp((1.0 + ev_f) / (W_PHI + mass_f), 0.005, 0.4)
            delta = max(delta, abs(new_pi - pi[(s, c)]),
                        abs(new_phi - phi[(s, c)]))
            pi[(s, c)], phi[(s, c)] = new_pi, new_phi
        theta0 = _clamp((1.0 + sum(w.values())) / (2.0 + len(universe)),
                        0.02, 0.98)
        if delta < tol:
            break
    return pi, theta0


def run_dsem(pair_sets, declared_r, restarts=8, iters=200,
             exclude_solo=False):
    pi_data = {s: sorted(ps) for s, ps in pair_sets.items()}
    asserters = defaultdict(set)
    for s, lst in pi_data.items():
        for p, _ in lst:
            asserters[p].add(s)
    solo = {p for p, ss in asserters.items() if len(ss) == 1}
    solo_pairs = solo if exclude_solo else frozenset()
    runs = [_em_once(pi_data, declared_r, iters, seed=100 + k,
                     solo_pairs=solo_pairs) for k in range(restarts)]
    keys = sorted({k for pi, _ in runs for k in pi})
    pi_hat = {k: sum(pi[k] for pi, _ in runs) / len(runs)
              for k in keys if all(k in pi for pi, _ in runs)}
    spread = {k: max(pi[k] for pi, _ in runs) - min(pi[k] for pi, _ in runs)
              for k in pi_hat}
    counts = Counter((s, c) for s, lst in pi_data.items() for (_, c) in lst)
    headline, solo_share = {}, {}
    for s in pi_data:
        tot = mass = 0.0
        n_solo = 0
        for p, c in pi_data[s]:
            n = counts[(s, c)]
            if (s, c) in pi_hat:
                tot += n
                mass += pi_hat[(s, c)] * n
            n_solo += 1 if p in solo else 0
        headline[s] = mass / tot if tot else None
        solo_share[s] = n_solo / len(pi_data[s]) if pi_data[s] else 0.0
    theta0 = sum(t for _, t in runs) / len(runs)
    return {"pi_hat": pi_hat, "spread": spread, "headline": headline,
            "solo_share": solo_share, "theta0": theta0}
