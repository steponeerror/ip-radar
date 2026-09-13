# backend/tests/core/test_archive_abstention.py
"""存档章弃权语义(spec 2026-09-06 §2.2/§4)。

不变式:confidence 仅由指控章(malicious/suspicious)源决定;
存档观测增删不改变数字;纯存档组退回旧公式(乙,平滑淡出)。
"""
from ipdb._merge import _assess_classification
from ipdb._types import EvidenceObservation
from ipdb import _logodds as _lo


def obs(source, verdict, r=0.7, first_seen=None):
    return EvidenceObservation(
        source=source, classification_type="spam", verdict=verdict,
        reliability=r, first_seen=first_seen)


FS = "2026-09-01T00:00:00+00:00"    # 新鲜
OLD = "2026-06-30T00:00:00+00:00"   # 68 天前


def test_archive_observation_does_not_change_confidence():
    """核心不变式:加入存档观测,数字逐位不变(71 病理 → 保持 63)。"""
    accusers = [obs("reportedip", "malicious", 0.65, FS)]
    mixed = accusers + [obs("stopforumspam", "informational", 0.70, OLD)]
    assert _assess_classification(mixed).confidence \
        == _assess_classification(accusers).confidence


def test_same_source_archive_never_contributes_even_when_stronger():
    """同源 max 域:同源的存档观测即使更强(0.90 > 0.65)也不进投票池、
    不抬数字 —— informational 整条排除,而非被同源 max 吸收。"""
    mixed = [obs("reportedip", "malicious", 0.65, FS),
             obs("reportedip", "informational", 0.90, FS)]
    solo = [obs("reportedip", "malicious", 0.65, FS)]
    ca = _assess_classification(mixed)
    assert ca.confidence == _assess_classification(solo).confidence
    assert ca.has_archive is True


def test_pure_archive_group_keeps_legacy_posterior():
    """纯存档组退回全量 Σ(决策 5/乙):与旧算法逐值一致。"""
    group = [obs("stopforumspam", "informational", 0.70, OLD),
             obs("greensnow", "informational", 0.60, None)]
    ca = _assess_classification(group)
    by_src: dict[str, float] = {}
    for o in group:
        c = _lo.coefficient(o.reliability, o.first_seen, "spam")
        by_src[o.source] = max(by_src.get(o.source, c), c)
    deduped = _lo.dedup_lineage(list(by_src.items()))
    assert ca.confidence == _lo.assertion_confidence([c for _, c in deduped])
    assert ca.corroborated is False   # 纯存档组无指控源,不亮已印证(决策 8)


def test_suspicious_votes_like_malicious():
    """可疑章与恶意同权(决策 4)。"""
    both = [obs("a", "malicious", 0.65, FS), obs("b", "suspicious", 0.70, FS)]
    same = [obs("a", "malicious", 0.65, FS), obs("b", "malicious", 0.70, FS)]
    assert _assess_classification(both).confidence \
        == _assess_classification(same).confidence
    assert _assess_classification(both).corroborated is True


def test_corroborated_counts_accusing_sources_only():
    """已印证只数指控源(决策 8):恶意+存档 不亮,恶意+可疑 亮。"""
    ca = _assess_classification(
        [obs("reportedip", "malicious", 0.65, FS),
         obs("stopforumspam", "informational", 0.70, OLD)])
    assert ca.corroborated is False
    assert _assess_classification(
        [obs("reportedip", "malicious", 0.65, FS),
         obs("stopforumspam", "suspicious", 0.70, OLD)]).corroborated is True


def test_has_archive_flag():
    ca = _assess_classification(
        [obs("reportedip", "malicious", 0.65, FS),
         obs("stopforumspam", "informational", 0.70, OLD)])
    assert ca.has_archive is True
    assert _assess_classification([obs("a", "malicious", 0.65, FS)]).has_archive is False


def test_verdict_conflict_requires_benign_opposition():
    """冲突 = 真对立(benign × 指控);定级分歧不再触发(决策 6/7)。"""
    assert _assess_classification(
        [obs("a", "malicious", 0.65, FS),
         obs("b", "informational", 0.70, OLD)]).verdict_conflict is False
    assert _assess_classification(
        [obs("a", "malicious", 0.65, FS),
         obs("b", "benign", 0.90, FS)]).verdict_conflict is True


def test_details_carry_verdict():
    ca = _assess_classification(
        [obs("reportedip", "malicious", 0.65, FS),
         obs("stopforumspam", "informational", 0.70, OLD)])
    by_src = {d["source"]: d["verdict"] for d in ca.details}
    assert by_src == {"reportedip": "malicious",
                      "stopforumspam": "informational"}


def test_unknown_verdict_abstains_but_shows():
    """未知 verdict 不投票(同存档但 has_archive=False);标签 worst-first 不变。"""
    ca = _assess_classification(
        [obs("a", "malicious", 0.65, FS), obs("b", "weird", 0.9, FS)])
    solo = _assess_classification([obs("a", "malicious", 0.65, FS)])
    assert ca.confidence == solo.confidence
    assert ca.verdict == "malicious"
    assert ca.has_archive is False
    assert ca.corroborated is False   # 唯一 voter 是 a,单源不足 2 不亮(决策 8)
