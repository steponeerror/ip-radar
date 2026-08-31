# backend/test_eval_metrics.py
from ipdb._eval.metrics import (Metric, pairs, asserting_sources, mc, cg,
    conflict, oc, dead_slot_fill)
from ipdb._eval.ablation import Snapshot

# baseline: only threatfox on c2-server for 1.1.1.1
BASELINE: Snapshot = {
    "1.1.1.1": {"classifications": {"c2-server": {
        "type": "c2-server", "verdict_conflict": False, "confidence": 50,
        "sources": [{"source": "threatfox"}],
        "details": [{"source": "threatfox", "reliability": 0.60}]}}},
    "2.2.2.2": {"classifications": {}},
}
# candidate run: cand ALSO now on c2-server for 1.1.1.1 (corroboration); new
# type phishing for 2.2.2.2 (dead-slot fill).
CANDIDATE: Snapshot = {
    "1.1.1.1": {"classifications": {"c2-server": {
        "type": "c2-server", "verdict_conflict": False, "confidence": 80,
        "sources": [{"source": "threatfox"}, {"source": "cand"}],
        "details": [{"source": "threatfox", "reliability": 0.60},
                     {"source": "cand", "reliability": 0.60}]}}},
    "2.2.2.2": {"classifications": {"phishing": {
        "type": "phishing", "verdict_conflict": False, "confidence": 50,
        "sources": [{"source": "cand"}],
        "details": [{"source": "cand", "reliability": 0.60}]}}},
}

def test_pairs_extracts_ip_type():
    p = pairs(CANDIDATE)
    assert ("1.1.1.1", "c2-server") in p
    assert ("2.2.2.2", "phishing") in p

def test_asserting_sources_reads_sources_list():
    assert asserting_sources(CANDIDATE, "1.1.1.1", "c2-server") == {"threatfox", "cand"}

def test_mc_counts_pairs_in_candidate_not_baseline():
    # candidate adds (2.2.2.2, phishing) which baseline lacks -> MC=1 pair.
    m = mc(BASELINE, CANDIDATE, "cand", total_corpus_pairs=2)
    assert m.value == 0.5        # 1 of 2 corpus pairs
    assert m.n == 2

def test_cg_counts_one_to_many_independent_upgrades():
    # (1.1.1.1, c2-server): baseline 1 source (threatfox), candidate 2 (threatfox+cand)
    # -> effective votes 1 -> 2. CG=1.
    m = cg(BASELINE, CANDIDATE, "cand")
    assert m.value == 1 and m.n == 1

def test_cg_shadowed_derived_candidate_gains_nothing():
    # firehol (derived) joins a pair already covered by a stronger non-derived
    # source: dedup_lineage drops it -> effective votes stay 1 -> no gain.
    # The static-group counter would have counted 1 -> 2 (the bug D5 fixes).
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}],
        "details": [{"source": "spamhaus", "reliability": 0.70}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "firehol"}],
        "details": [{"source": "spamhaus", "reliability": 0.70},
                     {"source": "firehol", "reliability": 0.55}]}}}}
    m = cg(base, cand, "firehol")
    assert m.value == 0

def test_cg_stronger_derived_candidate_survives_dedup():
    # Production semantics: a derived source strictly stronger than the best
    # non-derived survives dedup_lineage and DOES corroborate.
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}],
        "details": [{"source": "spamhaus", "reliability": 0.50}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "firehol"}],
        "details": [{"source": "spamhaus", "reliability": 0.50},
                     {"source": "firehol", "reliability": 0.90}]}}}}
    m = cg(base, cand, "firehol")
    assert m.value == 1

def test_cg_no_gain_when_already_corroborated():
    # Pair already at 2 independent votes: a third vote adds no NEW
    # corroboration (crossing only, not raw vote delta).
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "threatfox"}],
        "details": [{"source": "spamhaus", "reliability": 0.70},
                     {"source": "threatfox", "reliability": 0.60}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "threatfox"},
                     {"source": "urlhaus"}],
        "details": [{"source": "spamhaus", "reliability": 0.70},
                     {"source": "threatfox", "reliability": 0.60},
                     {"source": "urlhaus", "reliability": 0.60}]}}}}
    m = cg(base, cand, "urlhaus")
    assert m.value == 0

def test_cg_two_derived_alone_corroborate():
    # All-derived pair: dedup_lineage keeps everything -> firehol + ipsum
    # alone still count as 2 effective votes (matches production
    # `corroborated` semantics for all-derived groups).
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "firehol"}],
        "details": [{"source": "firehol", "reliability": 0.60}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "firehol"}, {"source": "ipsum"}],
        "details": [{"source": "firehol", "reliability": 0.60},
                     {"source": "ipsum", "reliability": 0.60}]}}}}
    m = cg(base, cand, "ipsum")
    assert m.value == 1

def test_dead_slot_fill_detects_new_type():
    # baseline had no phishing anywhere; candidate adds it.
    m = dead_slot_fill(BASELINE, CANDIDATE)
    assert m.value == 1          # 1 new type filled
    assert "phishing" in m.detail

def test_conflict_counts_newly_conflicted_pairs():
    base = {"1.1.1.1": {"classifications": {"x": {"verdict_conflict": False, "sources": []}}}}
    cand = {"1.1.1.1": {"classifications": {"x": {"verdict_conflict": True,  "sources": []}}}}
    m = conflict(base, cand)
    assert m.value == 1 and m.n == 1
