from datetime import datetime, timezone, timedelta
from ipdb._types import EvidenceObservation
from ipdb._merge import _assess_classification, to_observation


def _obs(source, reliability=0.5, first_seen=None, confidence=None,
         malware_name=None, verdict="malicious", extra=None):
    return EvidenceObservation(
        source=source, classification_type="c2-server", verdict=verdict,
        reliability=reliability, first_seen=first_seen, confidence=confidence,
        malware_name=malware_name, extra=extra or {})


def test_single_fresh_source_conf_equals_r():
    # 单源 r=0.85,无 first_seen:conf = 85(与旧 mean 连续,决策 1)
    a = _assess_classification([_obs("threatfox", reliability=0.85)])
    assert a.detected is True
    assert a.confidence == 85
    assert a.corroborated is False
    assert len(a.sources) == 1


def test_two_fresh_sources_compound():
    # 2×0.85 无 first_seen:Σ = 2×1.7346 = 3.469 → P = 0.970 → 97(旧 floor 80 死)
    grp = [_obs("threatfox", reliability=0.85), _obs("abuseipdb", reliability=0.85)]
    a = _assess_classification(grp)
    assert a.confidence == 97
    assert a.corroborated is True


def test_stale_evidence_decays_toward_neutral():
    # 单源 r=0.85,first_seen 240d 前(4 个半衰期):coeff = 1.7346×0.0625
    # = 0.1084 → P = 0.527 → 53(逐源衰减,不再锚定组内最新)
    stale = (datetime.now(timezone.utc) - timedelta(days=240)).isoformat()
    a = _assess_classification([_obs("threatfox", reliability=0.85, first_seen=stale)])
    assert a.confidence == 53


def test_corroborated_requires_deduped_sources():
    # firehol(derived)弱于非 derived 最强时被谱系去重剔除:去重后仅 1 源
    # → corroborated False(spec §3.3,决策 6)
    grp = [_obs("firehol", reliability=0.50), _obs("blocklist_de", reliability=0.70)]
    a = _assess_classification(grp)
    assert a.corroborated is False


def test_verdict_still_worst_first_and_conflict_flag():
    # benign × 指控 = 真对立,冲突照旧为 True(spec 2026-09-06 语义)
    a = _assess_classification([_obs("s1", verdict="benign"),
                                _obs("s2", verdict="malicious")])
    assert a.verdict == "malicious"
    assert a.verdict_conflict is True


def test_single_source_multiple_observations_not_corroborated():
    # Same source produces 2 observations (different malware_name, e.g.
    # threatfox lists one IP under both win.vidar and agenttesla). These
    # share a single source and must NOT count as independent corroboration,
    # and must NOT compound: per-source coefficients aggregate keeping the max
    # (spec §3.3 宁少算不多算 — 重复广播只计最强单条断言)。
    grp = [
        _obs("threatfox", reliability=0.85, malware_name="win.vidar"),
        _obs("threatfox", reliability=0.85, malware_name="agenttesla"),
    ]
    a = _assess_classification(grp)
    assert a.detected is True
    assert a.corroborated is False
    assert a.confidence == 85            # max(logit(0.85)), NOT 2×logit(0.85)=97
    assert len(a.sources) == 1


def test_two_independent_sources_corroborated_high_confidence():
    # threatfox 0.85 + abuseipdb 0.75:Σ = 1.7346+1.0986 = 2.833 → 94
    grp = [_obs("threatfox", reliability=0.85), _obs("abuseipdb", reliability=0.75)]
    a = _assess_classification(grp)
    assert a.detected is True
    assert a.corroborated is True
    assert a.confidence == 94


def test_reporter_total_sums():
    grp = [_obs("threatfox", reliability=0.85),
           EvidenceObservation(source="abuseipdb", classification_type="c2-server",
                               verdict="malicious", reliability=0.7, reporter_count=12)]
    a = _assess_classification(grp)
    assert a.reporter_total == 12


# ── 家族占位词 unknown(工单 #503)──
# abuse.ch ThreatFox 用 "unknown" 表示「未归到任何已命名家族」,查询期
# 整理时当作没有值;原始值仍在 extra.malware_printable,证据不丢。


def test_placeholder_unknown_dropped_but_real_family_kept():
    # 同组:threatfox 的 unknown 被滤掉,另一源的真实家族照旧收进来;
    # threatfox 明细没有 malware_name 键,extra.malware_printable 还在。
    grp = [
        _obs("threatfox", reliability=0.85, malware_name="unknown",
             extra={"malware_printable": "Unknown malware"}),
        _obs("abuseipdb", reliability=0.75, malware_name="win.vidar"),
    ]
    a = _assess_classification(grp)
    assert a.malware_names == ["win.vidar"]
    by_source = {d["source"]: d for d in a.details}
    assert "malware_name" not in by_source["threatfox"]
    assert by_source["threatfox"]["extra"]["malware_printable"] == "Unknown malware"
    assert by_source["abuseipdb"]["malware_name"] == "win.vidar"


def test_all_unknown_group_has_no_family():
    # 整组只有 unknown:malware_names 空,明细也不带 malware_name;
    # 该留的还在(源、verdict、extra)。
    a = _assess_classification([
        _obs("threatfox", reliability=0.85, malware_name="unknown",
             extra={"malware_printable": "Unknown malware"})])
    assert a.malware_names == []
    assert "malware_name" not in a.details[0]
    assert a.details[0]["source"] == "threatfox"
    assert a.details[0]["verdict"] == "malicious"
    assert a.details[0]["extra"]["malware_printable"] == "Unknown malware"


def test_placeholder_case_insensitive_with_whitespace():
    # "Unknown"(含首尾空白)去空白、不分大小写后同样当没有值;
    # 真实家族 win.vidar 照旧保留。
    grp = [
        _obs("threatfox", reliability=0.85, malware_name="  Unknown "),
        _obs("abuseipdb", reliability=0.75, malware_name="win.vidar"),
    ]
    a = _assess_classification(grp)
    assert a.malware_names == ["win.vidar"]
    by_source = {d["source"]: d for d in a.details}
    assert "malware_name" not in by_source["threatfox"]
    assert by_source["abuseipdb"]["malware_name"] == "win.vidar"


def test_raw_evidence_placeholder_unknown_dropped():
    # 原始证据 dict → to_observation 那条路同样生效(值会被转小写,
    # "unknown" → "unknown");真实家族保留。
    o = to_observation(
        "threatfox", {"malware_name": "unknown",
                      "extra": {"malware_printable": "Unknown malware"},
                      "confidence": 75},
        classification_type="c2-server", verdict="malicious", reliability=0.85)
    a = _assess_classification([o, _obs("abuseipdb", reliability=0.75,
                                        malware_name="win.vidar")])
    assert a.malware_names == ["win.vidar"]
    by_source = {d["source"]: d for d in a.details}
    assert "malware_name" not in by_source["threatfox"]
    assert by_source["threatfox"]["extra"]["malware_printable"] == "Unknown malware"
    assert by_source["abuseipdb"]["malware_name"] == "win.vidar"


def test_non_string_malware_name_kept_as_is():
    # 非字符串的 malware_name 照旧当有值、原样保留(#503 追加):
    # to_observation 对非字符串原样透传,master 上 123 会被保留,不能崩。
    a = _assess_classification([_obs("x", reliability=0.85, malware_name=123)])
    assert a.malware_names == [123]
    assert a.details[0]["malware_name"] == 123


def test_same_source_judged_per_observation_and_variants_kept():
    grp = [
        _obs("threatfox", reliability=0.85, malware_name="unknown", extra={"malware_printable": "Unknown malware"}),
        _obs("threatfox", reliability=0.85, malware_name="win.vidar"),
        _obs("threatfox", reliability=0.85, malware_name="unknown_rat"),
    ]
    a = _assess_classification(grp)
    assert a.malware_names == ["unknown_rat", "win.vidar"]
    assert ["malware_name" in d for d in a.details] == [False, True, True]
    assert a.details[0]["extra"]["malware_printable"] == "Unknown malware"


# ── 印证旗判式 #522(2026-11-28 丙口径):非派生且系数非零 ≥2 ──

def test_pure_derived_mutual_corroboration_no_flag():
    """#522 情形①:两聚合器互投不再亮旗(旧 grill Q2 2026-10-11 语义
    被取代)。变异③(判式回退只数源数)→ 本测试红。"""
    grp = [_obs("otx", reliability=0.55), _obs("otx_subscribed", reliability=0.55)]
    a = _assess_classification(grp)
    assert a.corroborated is False


def test_zero_coefficient_first_hands_no_flag():
    """#522 情形②:两个 r=0.5 的第一手源(系数恒 0)互相抬不起旗。
    变异②(去掉「系数非零」条件)→ 本测试红。"""
    grp = [_obs("threatfox", reliability=0.50), _obs("tweetfeed", reliability=0.50)]
    assert _assess_classification(grp).corroborated is False
    # 1 个非零第一手 + 1 个零系数第一手:同样不足两票
    grp2 = [_obs("threatfox", reliability=0.85), _obs("tweetfeed", reliability=0.50)]
    assert _assess_classification(grp2).corroborated is False


def test_first_hand_plus_stronger_derived_survivor_no_flag():
    """1 个第一手非零 + 更强派生(dedup 幸存)不足两票(读数①形)。"""
    grp = [_obs("abuseipdb", reliability=0.80), _obs("ziyadnz", reliability=0.90)]
    a = _assess_classification(grp)
    assert a.corroborated is False
