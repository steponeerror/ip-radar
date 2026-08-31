import pytest

from ipdb._eval import config
from ipdb._eval.events import extract_events, independent, market_rates
from ipdb._eval.pairwise import pairwise_oc, source_pair_sets


def _snap(rows):
    snap = {}
    for ip, ctype, srcs in rows:
        ca = snap.setdefault(ip, {}).setdefault(
            "classifications", {}).setdefault(ctype, {})
        ca["sources"] = [{"source": s, "value": True, "reliability": 0.5,
                          "authoritative": False} for s in srcs]
    return snap


def test_independent_respects_lineage_cluster():
    oc = {}   # no OC overlap at all
    assert independent("spamhaus", "ciarm", oc)
    assert not independent("firehol", "ipsum", oc)     # same cluster
    assert independent("firehol", "ciarm", oc)


def test_independent_respects_oc_bar():
    oc = {frozenset({"a", "b"}): config.OC_EXCLUSION,
          frozenset({"a", "c"}): config.OC_EXCLUSION + 1e-9}
    assert independent("a", "b", oc)          # at bar -> independent (<=)
    assert not independent("a", "c", oc)      # above bar -> dependent


def test_monopoly_ctype_excluded_from_counts():
    # tor asserted only by tor_exits -> monopoly. scanner: a and b each
    # assert 5 pairs sharing exactly 1 -> OC(a,b)=1/5=0.2 <= 0.30.
    # (NB: pair sets smaller than 4 can never clear the OC bar — shared>=1
    # forces OC >= 1/min — so every fixture here keeps min side >= 4.)
    rows = [("1.1.1.1", "tor", ["tor_exits"]),
            ("2.2.2.2", "tor", ["tor_exits"]),
            ("10.0.0.1", "scanner", ["a", "b"])]
    rows += [(f"10.0.1.{i}", "scanner", ["a"]) for i in range(4)]
    rows += [(f"10.0.2.{i}", "scanner", ["b"]) for i in range(4)]
    snap = _snap(rows)
    ev = extract_events(snap, pairwise_oc(source_pair_sets(snap)))
    assert ev.monopoly_ctypes == {"tor"}
    tor = ev.per_source["tor_exits"]
    assert (tor.n, tor.k) == (0, 0)           # monopoly -> no signal
    a = ev.per_source["a"]
    assert (a.n, a.k) == (5, 1)               # 5 scanner pairs, 1 corroborated


def test_dependent_only_overlap_counts_n_not_k():
    # f1's only co-asserter is ipsum (same lineage cluster -> not eligible);
    # f5's co-asserter ciarm has 4 pairs sharing 1 -> OC 0.25 <= 0.30.
    snap = _snap([("f1.example", "blacklist", ["firehol", "ipsum"]),
                  ("f2.example", "blacklist", ["firehol"]),
                  ("f3.example", "blacklist", ["firehol"]),
                  ("f4.example", "blacklist", ["firehol"]),
                  ("f5.example", "blacklist", ["firehol", "ciarm"]),
                  ("c2.example", "blacklist", ["ciarm"]),
                  ("c3.example", "blacklist", ["ciarm"]),
                  ("c4.example", "blacklist", ["ciarm"])])
    ev = extract_events(snap, pairwise_oc(source_pair_sets(snap)))
    fh = ev.per_source["firehol"]
    # f1 corroborated only by ipsum (same cluster) -> n yes k no;
    # f2-f4 solo -> n yes k no; f5 corroborated by ciarm -> k yes
    assert (fh.n, fh.k) == (5, 1)


def test_market_rates_leave_one_out_and_smoothing():
    # x: 5 pairs (s1 + 4 solo), y: 4 pairs, z: 5 pairs; x-y share s1,
    # y-z share s6; OC(x,y)=1/4=0.25, OC(y,z)=1/4=0.25 -> both eligible.
    rows = [("s1", "t", ["x", "y"]), ("s6", "t", ["y", "z"]),
            ("y1", "t", ["y"]), ("y2", "t", ["y"])]
    rows += [(f"x{i}", "t", ["x"]) for i in range(4)]
    rows += [(f"z{i}", "t", ["z"]) for i in range(4)]
    snap = _snap(rows)
    ev = extract_events(snap, pairwise_oc(source_pair_sets(snap)))
    full = market_rates(ev)
    # x n=5 k=1; y n=4 k=2; z n=5 k=1 -> N=14 K=4
    assert full["t"] == pytest.approx((4 + 0.5) / (14 + 1))
    loo_x = market_rates(ev, leave_out="x")
    # without x: N=9 (y 4 + z 5), K=3
    assert loo_x["t"] == pytest.approx((3 + 0.5) / (9 + 1))
