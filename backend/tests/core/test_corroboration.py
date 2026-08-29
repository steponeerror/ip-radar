from datetime import datetime, timezone, timedelta
from ipdb._types import EvidenceObservation
from ipdb._merge import _assess_classification


def _obs(source, reliability=0.5, first_seen=None, confidence=None,
         malware_name=None, verdict="malicious"):
    return EvidenceObservation(
        source=source, classification_type="c2-server", verdict=verdict,
        reliability=reliability, first_seen=first_seen, confidence=confidence,
        malware_name=malware_name)


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
    # verdict 优先级逻辑不变(verdict_conflict 照旧)
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
