# backend/tests/lookup/test_benign_assertion.py — benign② 良性断言源语义(#188)
"""infra_services 升格为良性断言源后的全管线语义(真 registry lookup 面):

- 真对立:良性断言 type-agnostic 注入每个指控组 → verdict_conflict=True;
- 宁少算:良性证人不进投票池(组 conf/顶层重融合恒等)、不压制指控
  verdict(precedence 恒指控胜);
- 纯良性面:无指控组时良性断言以自身 ctype 成组(verdict=benign,
  conf≈r)——区别于 ① 无证据弃权(顶层恒 benign/0);
- 良性断言是判断面输入,不是指控 → 不产 STIX Indicator。
"""
import pytest

from ipdb._sources.infra_services import InfraServicesSource
from tests.lookup.test_lookup_pipeline import (
    FakeScalarSource, FakeThreatSource,
)

try:
    import stix2 as _stix2  # noqa: F401
    _HAS_STIX2 = True
except ImportError:
    _HAS_STIX2 = False


@pytest.fixture
def infra(tmp_path):
    s = InfraServicesSource(data_dir=tmp_path)
    s.rebuild()
    return s


def _lookup_with(monkeypatch, sources):
    import ipdb._registry as reg
    from ipdb._registry import lookup
    monkeypatch.setattr(reg, "_sources", sources)
    return lookup


# ── 真对立:任意指控类型 × 良性断言 ──

def test_benign_assertion_conflicts_any_accusation_type(monkeypatch, infra):
    """223.5.5.5 生产形状:tweetfeed 指控(other)× infra_services 良性断言
    (dns)——ctype 不同也对立(注入面,非仅同组 benign 混场)。"""
    lookup = _lookup_with(monkeypatch, [
        FakeScalarSource(),
        FakeThreatSource("tweetfeed", "other", verdict="malicious",
                         reliability=0.5),
        infra,
    ])
    r = lookup("223.5.5.5")
    ca = r.classifications["other"]
    assert ca.verdict_conflict is True          # 真对立出海
    assert ca.verdict == "malicious"            # 良性不压制指控(宁少算)
    assert ca.confidence == 50                  # 池=指控源,良性证人不计分
    assert any(s.source == "infra_services" for s in ca.sources)  # 断言源在场(展示面)
    d = next(d for d in ca.details if d["source"] == "infra_services")
    assert d["verdict"] == "benign"
    # 有指控组时良性断言只同场,不另立独立良性组(一处断言一处显示)
    assert set(r.classifications) == {"other"}
    # 顶层摘要同样不压制
    assert r.threat_summary()["verdict"] == "malicious"


def test_benign_assertion_injected_into_every_accusing_group(monkeypatch, infra):
    """多指控组各自同场对峙:两组都带 conflict 标记与良性 detail。"""
    lookup = _lookup_with(monkeypatch, [
        FakeScalarSource(),
        FakeThreatSource("src_a", "scanner", verdict="malicious",
                         reliability=0.8),
        FakeThreatSource("src_b", "blacklist", verdict="suspicious",
                         reliability=0.7),
        infra,
    ])
    r = lookup("8.8.8.8")
    assert set(r.classifications) == {"scanner", "blacklist"}
    for ca in r.classifications.values():
        assert ca.verdict_conflict is True
        assert any(d["source"] == "infra_services"
                   for d in ca.details)


# ── 宁少算:良性断言不改计分 ──

def test_benign_assertion_leaves_conf_bit_identical(monkeypatch, infra):
    """同源同指控,加/不加良性断言:组 conf 与顶层 conf 逐位相等。"""
    import ipdb._registry as reg
    from ipdb._registry import lookup

    scalar = FakeScalarSource()
    tf = FakeThreatSource("tweetfeed", "other", verdict="malicious",
                          reliability=0.5)
    monkeypatch.setattr(reg, "_sources", [scalar, tf])
    without = lookup("223.5.5.5")
    monkeypatch.setattr(reg, "_sources", [scalar, tf, infra])
    with_benign = lookup("223.5.5.5")

    ca0 = without.classifications["other"]
    ca1 = with_benign.classifications["other"]
    assert ca0.confidence == ca1.confidence          # 组后验恒等
    assert ca0.corroborated == ca1.corroborated is False
    assert without.threat_summary()["confidence"] == \
        with_benign.threat_summary()["confidence"]   # 顶层重融合恒等
    assert ca1.verdict_conflict is True and ca0.verdict_conflict is False


# ── 纯良性面:无指控时良性断言成组(② 判定面,非 ① 弃权)──

def test_pure_benign_infra_ip_standalone_group(monkeypatch, infra):
    lookup = _lookup_with(monkeypatch, [FakeScalarSource(), infra])
    r = lookup("8.8.8.8")
    assert set(r.classifications) == {"dns"}
    ca = r.classifications["dns"]
    assert ca.verdict == "benign"
    assert ca.verdict_conflict is False
    assert ca.detected is True
    assert ca.confidence == 95                      # 单源 r=0.95(无衰减)
    # 顶层 = ②良性判定 95,非 ① 无证据弃权的 benign/0
    t = r.threat_summary()
    assert t["verdict"] == "benign" and t["confidence"] == 95
    # service 资产槽照旧
    assert any(s.source == "infra_services" and s.value == "dns"
               for s in r.attributes["service"])
    # 序列化口径
    assert r.to_dict()["classifications"]["dns"]["verdict"] == "benign"


def test_pure_benign_infra_v6(monkeypatch, infra):
    lookup = _lookup_with(monkeypatch, [infra])
    r = lookup("2400:3200::1")
    assert set(r.classifications) == {"dns"}
    assert r.classifications["dns"].verdict == "benign"


@pytest.mark.skipif(not _HAS_STIX2, reason="stix2 not installed")
def test_pure_benign_group_produces_no_stix_indicator(monkeypatch, infra):
    """良性断言不产 STIX Indicator(Indicator 语义=恶性工件断言)。"""
    from ipdb._stix_export import to_stix_bundle
    lookup = _lookup_with(monkeypatch, [FakeScalarSource(), infra])
    bundle = to_stix_bundle(lookup("8.8.8.8"))
    assert bundle is not None
    assert not [o for o in bundle["objects"] if o["type"] == "indicator"]
