# backend/test_eval_independence.py
from ipdb._eval.independence import oc_suspicion_pairs

def test_oc_suspicion_flags_high_overlap_pairs():
    pair_oc = {
        ("abuseipdb", "threatfox"): 0.10,
        ("alpha", "beta"): 0.85,    # above 0.70 -> suspect
        ("gamma", "delta"): 0.70,   # exactly threshold -> NOT flagged (strict >)
    }
    flagged = oc_suspicion_pairs(pair_oc)
    assert flagged == [(("alpha", "beta"), 0.85)]

def test_oc_suspicion_accepts_frozenset_keys():
    # pairwise.py (D4) returns frozenset keys; the harness must accept them
    # and normalize to sorted tuples.
    pair_oc = {frozenset(("beta", "alpha")): 0.9}
    flagged = oc_suspicion_pairs(pair_oc)
    assert flagged == [(("alpha", "beta"), 0.9)]

def test_oc_suspicion_skips_declared_lineage_cluster():
    # firehol × ipsum share a declared LINEAGE_CLUSTERS cluster — their
    # overlap is expected shared upstream, not a suspicion finding.
    pair_oc = {frozenset(("firehol", "ipsum")): 0.95}
    assert oc_suspicion_pairs(pair_oc) == []

def test_oc_suspicion_flags_cross_cluster_high_overlap():
    # Undeclared pair with high overlap IS the alarm this exists for
    # (e.g. blocklist_de silently copying spamhaus).
    pair_oc = {frozenset(("blocklist_de", "spamhaus")): 0.80}
    assert oc_suspicion_pairs(pair_oc) == [(("blocklist_de", "spamhaus"), 0.80)]
