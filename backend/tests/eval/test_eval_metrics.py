# backend/test_eval_metrics.py
from ipdb._eval.metrics import (Metric, pairs, mc, cg,
    conflict, oc, dead_slot_fill, _effective_votes)
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

def test_cg_zero_coeff_first_hand_plus_derived_echo_gains_nothing():
    # #522(2026-11-28 丙口径):第一手源 r=0.50 系数恒 0,不抬旗;
    # 更强的派生源(firehol 0.90,dedup_lineage 幸存)也不算票——旗仍
    # False,cg=0。旧判式(谱系去重后源数 1->2,本测试曾钉 cg=1)被
    # #522 取代。变异②(去掉「系数非零」条件)或③(去掉「非派生」
    # 条件)任一 → 本测试红。
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}],
        "details": [{"source": "spamhaus", "reliability": 0.50}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "firehol"}],
        "details": [{"source": "spamhaus", "reliability": 0.50},
                     {"source": "firehol", "reliability": 0.90}]}}}}
    m = cg(base, cand, "firehol")
    assert m.value == 0                 # #522:零系数第一手 + 派生回声 ≠ 印证

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

def test_cg_two_derived_alone_not_corroborated():
    # All-derived pair WITHOUT an anchor: 旧语义(grill Q2 2026-10-11
    # 「纯 derived 组互证仍算 corroborated」,本测试曾钉 cg=1)被 #522
    # (2026-11-28 丙口径)取代——两个聚合器抄同一批上游,不是两票;
    # 生产旗判式 = _logodds.corroborated_after_dedup。变异③(去掉
    # 「非派生」条件)→ 本测试红。
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "firehol"}],
        "details": [{"source": "firehol", "reliability": 0.60}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "firehol"}, {"source": "ipsum"}],
        "details": [{"source": "firehol", "reliability": 0.60},
                     {"source": "ipsum", "reliability": 0.60}]}}}}
    m = cg(base, cand, "ipsum")
    assert m.value == 0                 # #522:纯 derived 互证不再亮旗


def test_eval_corroborated_flag_matches_production():
    """对拍钉子(#522 变异④):评测侧 cg 的旗判式 = 生产 _assess_
    classification 的 corroborated,评测与生产不许各算各的。四景:
    两第一手 / 纯派生互证 / 零系数抬旗 / 第一手+派生回声。"""
    from datetime import datetime, timezone, timedelta
    from ipdb._logodds import accuser_pool, corroborated_after_dedup
    from ipdb._merge import _assess_classification
    from ipdb._types import EvidenceObservation
    fs = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    def obs(src, r):
        return EvidenceObservation(source=src, classification_type="spam",
                                   verdict="malicious", reliability=r,
                                   first_seen=fs, confidence=None,
                                   malware_name=None, extra={})

    scenarios = {
        "two_first_hand": [obs("threatfox", 0.85), obs("abuseipdb", 0.75)],
        "pure_derived": [obs("otx", 0.55), obs("otx_subscribed", 0.55)],
        "zero_coeff_lift": [obs("threatfox", 0.50), obs("tweetfeed", 0.50)],
        "first_hand_plus_derived": [obs("abuseipdb", 0.80), obs("ziyadnz", 0.90)],
    }
    for name, grp in scenarios.items():
        ca = _assess_classification(grp)
        pool = accuser_pool(((o.source, o.reliability, o.first_seen)
                             for o in grp), "spam")
        assert corroborated_after_dedup(pool) == ca.corroborated, name


def test_cg_mirror_pair_no_corroboration():
    # grill Q2 翻案(2026-10-11):firehol+greensnow 镜像对(OC=1.0,
    # 包含度 ≥0.9)=同一出版方——firehol(r=.5,系数恒 0)不再是第二票:
    # 加它不涨旗,cg=0(旗判式 = corroborated_after_dedup,#522)。
    base = {"1.1.1.1": {"classifications": {"blacklist": {
        "sources": [{"source": "greensnow"}],
        "details": [{"source": "greensnow", "reliability": 0.60}]}}}}
    cand = {"1.1.1.1": {"classifications": {"blacklist": {
        "sources": [{"source": "greensnow"}, {"source": "firehol"}],
        "details": [{"source": "greensnow", "reliability": 0.60},
                     {"source": "firehol", "reliability": 0.50}]}}}}
    m = cg(base, cand, "firehol")
    assert m.value == 0

def test_effective_votes_informational_detail_not_counted():
    # EV-F1:存档票只展示不计分——2 details 其中 1 条 informational
    # -> 有效票 1 而非 2(镜像生产 corroboration,spec 2026-09-06 决策 8)。
    snap = {"1.1.1.1": {"classifications": {"c2-server": {
        "sources": [{"source": "threatfox"}, {"source": "urlhaus"}],
        "details": [{"source": "threatfox", "reliability": 0.60,
                      "verdict": "malicious"},
                    {"source": "urlhaus", "reliability": 0.60,
                     "verdict": "informational"}]}}}}
    assert _effective_votes(snap, "1.1.1.1", "c2-server") == 1

def test_effective_votes_missing_verdict_key_counts_as_malicious():
    # 旧快照兼容:detail 缺 verdict 键 -> 兑底 malicious 仍计票
    # (生产读路径 _registry.to_observation 同口径)。
    snap = {"1.1.1.1": {"classifications": {"c2-server": {
        "sources": [{"source": "threatfox"}, {"source": "urlhaus"}],
        "details": [{"source": "threatfox", "reliability": 0.60},
                    {"source": "urlhaus", "reliability": 0.60}]}}}}
    assert _effective_votes(snap, "1.1.1.1", "c2-server") == 2

def test_cg_pure_archive_cooccurrence_gains_nothing():
    # EV-F1:纯存档↔存档共现——有效票 0 -> 0,cg 无 gain;无过滤时
    # 会是 1 -> 2,经 CG 闸门误挣 POSITIVE-VERIFIED(verdict.verified = cg_hi)。
    base = {"1.1.1.1": {"classifications": {"c2-server": {
        "sources": [{"source": "threatfox"}],
        "details": [{"source": "threatfox", "reliability": 0.60,
                      "verdict": "informational"}]}}}}
    cand = {"1.1.1.1": {"classifications": {"c2-server": {
        "sources": [{"source": "threatfox"}, {"source": "urlhaus"}],
        "details": [{"source": "threatfox", "reliability": 0.60,
                      "verdict": "informational"},
                    {"source": "urlhaus", "reliability": 0.60,
                     "verdict": "informational"}]}}}}
    m = cg(base, cand, "urlhaus")
    assert m.value == 0

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


class _DirFakeSource:
    """目录源最小桩:_path=目录(§3c),query 走内存表——钉 compute_other_distribution
    的目录面(2026-11-22 评审 P1:此前 is_file() 守卫对目录源恒返 {})。"""
    def __init__(self, d, table):
        self._path = d
        self._table = table
    def query(self, ip):
        return self._table.get(ip)


def test_other_distribution_directory_source(tmp_path):
    from ipdb._eval.metrics import compute_other_distribution
    import random as _random
    d = tmp_path / "dirsrc"
    d.mkdir()
    (d / "a.txt").write_text("1.1.1.1\n2.2.2.2\n")
    (d / "b.txt").write_text("3.3.3.3\n4.4.4.4\n")
    table = {ip: [{"classification_type": "scanner"}] for ip in
             ("1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4")}
    counts = compute_other_distribution(_DirFakeSource(d, table),
                                        rng=_random.Random(7))
    assert counts == {"scanner": 4}


def test_other_distribution_missing_source_empty():
    from ipdb._eval.metrics import compute_other_distribution
    assert compute_other_distribution(None) == {}
    class _Bare:
        pass
    assert compute_other_distribution(_Bare()) == {}
