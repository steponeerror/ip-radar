from ipdb._eval.pairwise import pairwise_oc, source_pair_sets


def _snap(rows):
    """rows: list of (ip, ctype, [source names]) -> minimal Snapshot."""
    snap = {}
    for ip, ctype, srcs in rows:
        ca = snap.setdefault(ip, {}).setdefault("classifications", {}).setdefault(ctype, {})
        ca["sources"] = [{"source": s, "value": True, "reliability": 0.5,
                          "authoritative": False} for s in srcs]
    return snap


def test_source_pair_sets_collects_per_source_pairs():
    snap = _snap([("1.1.1.1", "scanner", ["a", "b"]),
                  ("1.1.1.1", "spam", ["a"]),
                  ("2.2.2.2", "scanner", ["b"])])
    assert source_pair_sets(snap) == {
        "a": {("1.1.1.1", "scanner"), ("1.1.1.1", "spam")},
        "b": {("1.1.1.1", "scanner"), ("2.2.2.2", "scanner")},
    }


def test_pairwise_oc_symmetric_and_formula():
    ps = {"a": {("1", "t"), ("2", "t"), ("3", "t"), ("4", "t")},
          "b": {("1", "t"), ("2", "t"), ("5", "t")},
          "c": set()}
    oc = pairwise_oc(ps)
    assert oc[frozenset({"a", "b"})] == 2 / 3   # |∩|/min(|a|,|b|) = 2/3
    assert oc[frozenset({"a", "b"})] == oc[frozenset({"b", "a"})]
    assert frozenset({"a", "c"}) not in oc       # empty side -> no entry


def test_pairwise_oc_full_overlap_is_one():
    ps = {"a": {("1", "t")}, "b": {("1", "t")}}
    assert pairwise_oc(ps)[frozenset({"a", "b"})] == 1.0
