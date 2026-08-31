import pytest

from ipdb._eval.events import Events, SourceEvents
from ipdb._eval.model import (beta_binomial_interval, beta_cdf,
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


def test_estimate_evidence_flag():
    ev = Events(
        pair_sets={"a": {("p1", "t")}, "c": {("p9", "t")}},
        monopoly_ctypes=set(),
        per_source={
            "a": SourceEvents(n=20, k=10, by_ctype={"t": (20, 10)}),
            "c": SourceEvents(n=5, k=0, by_ctype={"t": (5, 0)}),
            "tor_exits": SourceEvents(n=0, k=0, by_ctype={}),
        },
    )
    scores = {s.source: s for s in estimate(ev)}
    assert scores["a"].evidence is True       # k=10 >= 1 -> independently corroborated
    assert scores["c"].evidence is False      # k=0 -> evidence-starved, not tested-weak
    assert scores["tor_exits"].evidence is False  # no-signal slot


# ── fountain_suspect flag (spec 2026-09-01 Part 2) ───────────────

from ipdb._eval.events import Events, SourceEvents
from ipdb._eval.model import estimate


def _events_from_pair_sets(pair_sets):
    ev = Events(pair_sets=pair_sets, monopoly_ctypes=set(), per_source={})
    for src, ps in pair_sets.items():
        se = SourceEvents()
        for ip, ctype in ps:
            n, k = se.by_ctype.get(ctype, (0, 0))
            se.by_ctype[ctype] = (n + 1, k)
            se.n += 1
        ev.per_source[src] = se
    return ev


def test_fountain_suspect_needs_two_qualifying_containees():
    ips = [("10.0.0.%d" % i, "spam") for i in range(12)]
    ps = {
        "fount": set(ips),
        "m1": set(ips[:10]),            # ⊆ fount, |m1| = 10 ≥ floor
        "m2": set(ips[2:12]),           # ⊆ fount, |m2| = 10 ≥ floor
        "m3": set(ips[:9]),             # ⊆ fount but |m3| = 9 < floor
        "ind": {("10.9.9.9", "spam")},  # unique pair
    }
    sc = {s.source: s for s in estimate(_events_from_pair_sets(ps))}
    assert sc["fount"].fountain_suspect is True      # m1 + m2 qualify
    assert sc["m1"].fountain_suspect is False
    assert sc["ind"].fountain_suspect is False


def test_fountain_suspect_single_containee_is_not_enough():
    ips = [("10.0.0.%d" % i, "spam") for i in range(12)]
    ps = {"fount": set(ips), "m1": set(ips[:10])}
    sc = {s.source: s for s in estimate(_events_from_pair_sets(ps))}
    assert sc["fount"].fountain_suspect is False


def test_fountain_suspect_partial_overlap_below_bar():
    ips = [("10.0.0.%d" % i, "spam") for i in range(12)]
    ps = {
        "fount": set(ips),
        "m1": set(ips[:10]) | {("10.9.9.9", "spam")},   # 10/11 inside ≈ 0.91 → ok
        "m2": set(ips[:8]) | {("10.9.9.8", "spam"),
                              ("10.9.9.7", "spam"),
                              ("10.9.9.6", "spam")},    # 8/11 ≈ 0.73 < 0.9
    }
    sc = {s.source: s for s in estimate(_events_from_pair_sets(ps))}
    assert sc["fount"].fountain_suspect is False      # only m1 qualifies


# ── unique_share (spec 2026-09-01 Q4-B1) ─────────────────────────

def test_unique_share_counts_solo_pairs_only():
    ips = [("10.0.0.%d" % i, "spam") for i in range(4)]
    ps = {
        "a": set(ips) | {("10.9.9.9", "spam")},   # 4 shared + 1 unique
        "b": set(ips),
    }
    sc = {s.source: s for s in estimate(_events_from_pair_sets(ps))}
    assert sc["a"].unique_share == 0.2
    assert sc["b"].unique_share == 0.0


def test_unique_share_none_when_all_pairs_monopoly():
    ps = {"solo": {("1.2.3.4", "tor")}}
    ev = _events_from_pair_sets(ps)
    ev.monopoly_ctypes = {"tor"}                  # sole asserter ctype
    ev.per_source["solo"] = SourceEvents()        # n=k=0 → all-monopoly
    sc = {s.source: s for s in estimate(ev)}
    assert sc["solo"].unique_share is None
