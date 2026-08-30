"""Beta posterior estimator: corroboration contrast vs ctype market (G1').

Output semantics = corroboration probability relative to market — NEVER
correctness/accuracy (audit B2 red line). declared_r is a read-only
comparison column; nothing here feeds production fusion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import config
from .events import Events, market_rates


# ── stdlib incomplete beta (NR §6.4 continued fraction) ─────────

def _betacf(a: float, b: float, x: float, itmax: int = 200, eps: float = 3e-12) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1.0) < eps:
            break
    return h


def beta_cdf(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_ppf(a: float, b: float, q: float) -> float:
    """Inverse CDF by bisection (q in (0,1))."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if beta_cdf(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def beta_ci(a: float, b: float, level: float = 0.90) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    return beta_ppf(a, b, tail), beta_ppf(a, b, 1.0 - tail)


def _log_beta_binomial_pmf(k: int, n: int, a: float, b: float) -> float:
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + math.lgamma(a + k) + math.lgamma(b + n - k) - math.lgamma(a + b + n)
            - math.lgamma(a) - math.lgamma(b) + math.lgamma(a + b))


def beta_binomial_interval(n: int, a: float, b: float,
                           level: float = 0.90) -> tuple[int, int]:
    """Equal-tail posterior-predictive interval for k ~ BetaBinomial(n,a,b)."""
    tail = (1.0 - level) / 2.0
    logp = [_log_beta_binomial_pmf(k, n, a, b) for k in range(n + 1)]
    m = max(logp)
    w = [math.exp(lp - m) for lp in logp]
    total = sum(w)
    cum = 0.0
    lo = 0
    for k in range(n + 1):
        cum += w[k] / total
        if cum >= tail:
            lo = k
            break
    cum = 0.0
    hi = n
    for k in range(n, -1, -1):
        cum += w[k] / total
        if cum >= tail:
            hi = k
            break
    return lo, hi


# ── estimator ────────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceScore:
    source: str
    theta: float | None        # posterior mean; None = no-signal (monopoly)
    ci_lo: float | None
    ci_hi: float | None
    n: int
    k: int
    rho: float | None          # prior center (market mix)
    below_market: bool
    monopoly: bool
    declared_r: float | None


def _prior_center(se, rhos_full: dict[str, float], rhos_loo: dict[str, float]) -> float | None:
    """n-weighted mix of that source's LOO market rates (mean if n=0)."""
    if not se.by_ctype:
        return None
    n_tot = sum(n for n, _ in se.by_ctype.values())
    if n_tot == 0:
        vals = [rhos_full.get(c) for c in se.by_ctype]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None
    return sum(rhos_loo.get(c, rhos_full.get(c, 0.5)) * n
               for c, (n, _) in se.by_ctype.items()) / n_tot


def estimate(events: Events, declared_r: dict[str, float] | None = None,
             w: int | None = None) -> list[SourceScore]:
    w = w if w is not None else config.MODEL_W
    declared_r = declared_r or {}
    out: list[SourceScore] = []
    for src, se in sorted(events.per_source.items()):
        rhos_loo = market_rates(events, leave_out=src)
        rhos_full = market_rates(events)
        rho = _prior_center(se, rhos_full, rhos_loo)
        asserted = events.pair_sets.get(src) or set()
        monopoly = (se.n == 0 and se.k == 0 and bool(asserted)
                    and all(p[1] in events.monopoly_ctypes for p in asserted))
        if rho is None or se.n == 0:
            # monopoly -> no-signal; n=0 non-monopoly -> market-prior slot
            out.append(SourceScore(src, None, None, None, se.n, se.k, rho,
                                   False, monopoly, declared_r.get(src)))
            continue
        a = w * rho + se.k
        b = w * (1.0 - rho) + (se.n - se.k)
        theta = a / (a + b)
        lo, hi = beta_ci(a, b, level=0.90)
        out.append(SourceScore(src, theta, lo, hi, se.n, se.k, rho,
                               hi < rho, monopoly, declared_r.get(src)))
    return out
