# backend/test_eval_metrics.py
from ipdb._eval.metrics import (Metric, pairs, mc, cg,
    conflict, oc, dead_slot_fill, _effective_votes)
from ipdb._eval.ablation import Snapshot

# baseline: only threatfox on c2-server for 1.1.1.1
BASELINE: Snapshot = {
    "1.1.1.1": {"classifications": {"c2-server": {
        "type": "c2-server", "verdict_conflict": False, "confidence": 50,
        "sources": [{"source": "threatfox"}],
        "details": [{"source": "threatfox", "reliability": 0.60,
                      "verdict": "malicious"}]}}},
    "2.2.2.2": {"classifications": {}},
}
# candidate run: cand ALSO now on c2-server for 1.1.1.1 (corroboration); new
# type phishing for 2.2.2.2 (dead-slot fill).
CANDIDATE: Snapshot = {
    "1.1.1.1": {"classifications": {"c2-server": {
        "type": "c2-server", "verdict_conflict": False, "confidence": 80,
        "sources": [{"source": "threatfox"}, {"source": "cand"}],
        "details": [{"source": "threatfox", "reliability": 0.60,
                      "verdict": "malicious"},
                     {"source": "cand", "reliability": 0.60,
                      "verdict": "malicious"}]}}},
    "2.2.2.2": {"classifications": {"phishing": {
        "type": "phishing", "verdict_conflict": False, "confidence": 50,
        "sources": [{"source": "cand"}],
        "details": [{"source": "cand", "reliability": 0.60,
                      "verdict": "malicious"}]}}},
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
        "details": [{"source": "spamhaus", "reliability": 0.70,
                      "verdict": "malicious"}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "firehol"}],
        "details": [{"source": "spamhaus", "reliability": 0.70,
                      "verdict": "malicious"},
                     {"source": "firehol", "reliability": 0.55,
                      "verdict": "malicious"}]}}}}
    m = cg(base, cand, "firehol")
    assert m.value == 0

def test_cg_zero_coeff_first_hand_plus_derived_echo_gains_nothing():
    # #522(2026-11-28 丙口径):第一手源 r=0.50 系数恒 0,不抬旗;
    # 更强的派生源(firehol 0.90,dedup_lineage 幸存)也不算票——旗仍
    # False,cg=0。旧判式(谱系去重后源数 1->2,本测试曾钉 cg=1)被
    # #522 取代。变异①(判式回退只数池大小 1->2)→ 本测试红;变异②③
    # 下两侧资格票都不足两票,本测试恒绿(红证见变异表)。
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}],
        "details": [{"source": "spamhaus", "reliability": 0.50,
                      "verdict": "malicious"}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "firehol"}],
        "details": [{"source": "spamhaus", "reliability": 0.50,
                      "verdict": "malicious"},
                     {"source": "firehol", "reliability": 0.90,
                      "verdict": "malicious"}]}}}}
    m = cg(base, cand, "firehol")
    assert m.value == 0                 # #522:零系数第一手 + 派生回声 ≠ 印证

def test_cg_no_gain_when_already_corroborated():
    # Pair already at 2 independent votes: a third vote adds no NEW
    # corroboration (crossing only, not raw vote delta).
    base = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "threatfox"}],
        "details": [{"source": "spamhaus", "reliability": 0.70,
                      "verdict": "malicious"},
                     {"source": "threatfox", "reliability": 0.60,
                      "verdict": "malicious"}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "spamhaus"}, {"source": "threatfox"},
                     {"source": "urlhaus"}],
        "details": [{"source": "spamhaus", "reliability": 0.70,
                      "verdict": "malicious"},
                     {"source": "threatfox", "reliability": 0.60,
                      "verdict": "malicious"},
                     {"source": "urlhaus", "reliability": 0.60,
                      "verdict": "malicious"}]}}}}
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
        "details": [{"source": "firehol", "reliability": 0.60,
                      "verdict": "malicious"}]}}}}
    cand = {"1.1.1.1": {"classifications": {"spam": {
        "sources": [{"source": "firehol"}, {"source": "ipsum"}],
        "details": [{"source": "firehol", "reliability": 0.60,
                      "verdict": "malicious"},
                     {"source": "ipsum", "reliability": 0.60,
                      "verdict": "malicious"}]}}}}
    m = cg(base, cand, "ipsum")
    assert m.value == 0                 # #522:纯 derived 互证不再亮旗


def test_eval_corroborated_flag_matches_production():
    """对拍钉子(#522 变异④返工版):走评测侧自己的闸函数 cg 本尊
    (_eval.metrics,与生产 _assess_classification 同一组证据),逐景断言
    「cg 的跨越结果 = 生产旗的 False→True 转变」;另对每组断言
    corroborated_after_dedup(_group_pool(…)) == 生产旗。变异:把
    metrics.cg 改回旧写法(有效票 1→≥2)→ 本测试在纯派生/零系数/
    第一手+派生三景红。"""
    from datetime import datetime, timezone, timedelta
    from ipdb._eval.metrics import _group_pool, cg
    from ipdb._logodds import corroborated_after_dedup
    from ipdb._merge import _assess_classification
    from ipdb._types import EvidenceObservation
    fs = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    def obs(src, r, verdict="malicious"):
        return EvidenceObservation(source=src, classification_type="spam",
                                   verdict=verdict, reliability=r,
                                   first_seen=fs, confidence=None,
                                   malware_name=None, extra={})

    def snap(grp, ip="1.1.1.1"):
        """生产 _assess_classification 结果 → lookup to_dict 形状快照。"""
        ca = _assess_classification(grp)
        return {ip: {"classifications": {"spam": {
            "type": "spam", "verdict": ca.verdict, "detected": True,
            "corroborated": ca.corroborated, "details": ca.details,
            "sources": [{"source": s.source} for s in ca.sources]}}}}

    # (名, 基线组, 候选组, 候选源):候选源 = 候选组新增的证人
    scenarios = [
        ("two_first_hand", [obs("threatfox", 0.85)],
         [obs("threatfox", 0.85), obs("abuseipdb", 0.75)], "abuseipdb"),
        ("pure_derived", [obs("otx", 0.55)],
         [obs("otx", 0.55), obs("otx_subscribed", 0.55)], "otx_subscribed"),
        ("zero_coeff_lift", [obs("threatfox", 0.50)],
         [obs("threatfox", 0.50), obs("tweetfeed", 0.50)], "tweetfeed"),
        ("first_hand_plus_derived", [obs("abuseipdb", 0.80)],
         [obs("abuseipdb", 0.80), obs("ziyadnz", 0.90)], "ziyadnz"),
        ("derived_no_dilute", [obs("abuseipdb", 0.80), obs("spamhaus", 0.70)],
         [obs("abuseipdb", 0.80), obs("spamhaus", 0.70), obs("ziyadnz", 0.90)],
         "ziyadnz"),
        ("accusing_plus_archive", [obs("threatfox", 0.85)],
         [obs("threatfox", 0.85), obs("stopforumspam", 0.70, "informational")],
         "stopforumspam"),
    ]
    for name, base_grp, cand_grp, cand_src in scenarios:
        base_ca = _assess_classification(base_grp)
        cand_ca = _assess_classification(cand_grp)
        base_snap, cand_snap = snap(base_grp), snap(cand_grp)
        # 旗本身:评测取池函数(cg 同款取池)算旗 vs 生产旗
        for snap_d, ca in ((base_snap, base_ca), (cand_snap, cand_ca)):
            assert corroborated_after_dedup(
                _group_pool(snap_d, "1.1.1.1", "spam")) == ca.corroborated, name
        # cg 的跨越 = 生产旗的 False→True 转变(评测闸与生产同判)
        expected = 1 if (not base_ca.corroborated
                         and cand_ca.corroborated) else 0
        m = cg(base_snap, cand_snap, cand_src)
        assert m.value == expected, (name, m.value, expected)


def test_cg_derived_pair_qualifying_zero_both_sides_still_zero():
    # greensnow+firehol 都是派生源:新判式下两侧资格票都是 0,cg 恒 0。
    # 本用例不再检验镜像对去重(那由 test_logodds.py::
    # test_dedup_lineage_pure_derived_mirror_pair 钉);留作「纯派生对
    # 永不亮旗、加票不涨 cg」的钉子(#522)。
    base = {"1.1.1.1": {"classifications": {"blacklist": {
        "sources": [{"source": "greensnow"}],
        "details": [{"source": "greensnow", "reliability": 0.60,
                      "verdict": "malicious"}]}}}}
    cand = {"1.1.1.1": {"classifications": {"blacklist": {
        "sources": [{"source": "greensnow"}, {"source": "firehol"}],
        "details": [{"source": "greensnow", "reliability": 0.60,
                      "verdict": "malicious"},
                     {"source": "firehol", "reliability": 0.50,
                      "verdict": "malicious"}]}}}}
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

def test_effective_votes_missing_verdict_key_not_counted():
    # #529 裁决 2026-11-28:detail 缺 verdict 键 = 不算指控(宁少算;
    # 旧口径兑底 malicious,九处收成 accusation.is_accusation 后统一)。
    snap = {"1.1.1.1": {"classifications": {"c2-server": {
        "sources": [{"source": "threatfox"}, {"source": "urlhaus"}],
        "details": [{"source": "threatfox", "reliability": 0.60},
                    {"source": "urlhaus", "reliability": 0.60}]}}}}
    assert _effective_votes(snap, "1.1.1.1", "c2-server") == 0
    # 混合组:显式 malicious 仍计,缺键的同组证人剔除后不拖累有效票
    mixed = {"1.1.1.1": {"classifications": {"c2-server": {
        "sources": [{"source": "threatfox"}, {"source": "urlhaus"}],
        "details": [{"source": "threatfox", "reliability": 0.60,
                      "verdict": "malicious"},
                    {"source": "urlhaus", "reliability": 0.60}]}}}}
    assert _effective_votes(mixed, "1.1.1.1", "c2-server") == 1

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
