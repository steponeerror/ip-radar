import math

import pytest

from ipdb._eval import config
from ipdb._eval.events import Events, SourceEvents
from ipdb._eval.model import (SourceScore, beta_binomial_interval, beta_cdf,
                              beta_ci, beta_ppf, estimate)


def test_beta_cdf_against_closed_form_beta22():
    # I_x(2,2) = 3x^2 - 2x^3 (closed form)
    for x in (0.1, 0.3, 0.5, 0.8):
        assert beta_cdf(2.0, 2.0, x) == pytest.approx(3 * x * x - 2 * x ** 3, abs=1e-9)


def test_beta_cdf_symmetry_and_edges():
    assert beta_cdf(5.0, 2.0, 0.0) == 0.0
    assert beta_cdf(5.0, 2.0, 1.0) == 1.0
    assert beta_cdf(5.0, 2.0, 0.4) == pytest.approx(1 - beta_cdf(2.0, 5.0, 0.6), abs=1e-9)


def test_beta_ppf_roundtrip():
    for a, b, q in ((2.0, 2.0, 0.05), (9.0, 3.0, 0.5), (0.5, 0.5, 0.95)):
        assert beta_cdf(a, b, beta_ppf(a, b, q)) == pytest.approx(q, abs=1e-6)


def test_beta_ci_equal_tail():
    lo, hi = beta_ci(2.0, 2.0, level=0.90)
    assert beta_cdf(2.0, 2.0, lo) == pytest.approx(0.05, abs=1e-6)
    assert beta_cdf(2.0, 2.0, hi) == pytest.approx(0.95, abs=1e-6)


def test_beta_binomial_interval_covers_mass():
    lo, hi = beta_binomial_interval(20, 6.0, 4.0, level=0.90)
    assert 0 <= lo < hi <= 20


def _make_events():
    return Events(
        pair_sets={"a": {("p1", "t")}, "b": {("p1", "t")},
                   "tor_exits": {("x", "tor")}},
        monopoly_ctypes={"tor"},
        per_source={
            "a": SourceEvents(n=20, k=10, by_ctype={"t": (20, 10)}),
            "b": SourceEvents(n=20, k=2, by_ctype={"t": (20, 2)}),
            "tor_exits": SourceEvents(n=0, k=0, by_ctype={}),
        },
    )


def test_estimate_contrast_direction_and_monopoly():
    ev = _make_events()
    scores = {s.source: s for s in estimate(ev, declared_r={"a": 0.9})}
    # market rate for t (LOO for a: only b contributes) = (2+0.5)/(20+1)
    rho_a = (2.5) / 21
    a = scores["a"]
    assert a.rho == pytest.approx(rho_a)
    assert a.theta > a.rho            # k/n = 0.5 >> market -> above
    assert a.declared_r == 0.9
    b = scores["b"]
    assert b.theta < b.rho            # k/n = 0.1 << market -> below
    assert b.below_market is True
    assert b.declared_r is None
    tor = scores["tor_exits"]
    assert tor.monopoly is True and tor.theta is None


def test_estimate_is_deterministic():
    ev = _make_events()
    assert estimate(ev) == estimate(ev)
