"""Tests for typed internal model dataclasses and serialization."""
from ipdb import _logodds as _lo
from ipdb._types import (
    AssetStatement, SourceAttribution, MergedField, ClassificationAssessment,
    LookupResult, _attribution_to_dict, _field_to_dict,
)


class TestSourceAttribution:
    def test_equality(self):
        a = SourceAttribution("ip2proxy", True, 0.80, True)
        b = SourceAttribution("ip2proxy", True, 0.80, True)
        assert a == b

    def test_defaults(self):
        a = SourceAttribution("ipsum", False)
        assert a.reliability == 0.0
        assert a.authoritative is False


class TestMergedField:
    def test_empty(self):
        mf = MergedField("N/A", 0, "voting", [])
        assert mf.value == "N/A"
        assert mf.confidence == 0
        assert mf.algorithm == "voting"
        assert mf.sources == []

    def test_with_attributions(self):
        attrs = [SourceAttribution("s1", "CN", 0.95, False)]
        mf = MergedField("CN", 85, "voting", attrs)
        assert len(mf.sources) == 1


class TestClassificationAssessment:
    def test_construction(self):
        attrs = [SourceAttribution("threatfox", True, 0.85, False)]
        ca = ClassificationAssessment(
            type="c2-server", verdict="malicious", detected=True,
            confidence=85, algorithm="corroboration", sources=attrs,
            corroborated=False, reporter_total=0)
        assert ca.detected is True
        assert ca.confidence == 85
        assert ca.corroborated is False


class TestLookupResultToDict:
    def test_full_result(self):
        country_mf = MergedField("CN", 85, "voting", [
            SourceAttribution("ipinfo_lite", "CN", 0.95, False),
        ])
        asn_mf = MergedField(4134, 85, "voting", [
            SourceAttribution("iptoasn", 4134, 0.90, False),
        ])
        as_name_mf = MergedField("China Telecom", 90, "authority", [
            SourceAttribution("cn_isp", "中国电信", 0.85, False),
        ])
        range_mf = MergedField("1.2.3.0/24", 50, "specificity", [
            SourceAttribution("ipinfo_lite", "1.2.3.0/24", 0.95, False),
        ])
        c2_ca = ClassificationAssessment(
            "c2-server", "malicious", True, 85, "corroboration",
            [SourceAttribution("threatfox", True, 0.85, False)],
            corroborated=False)

        r = LookupResult(
            ip="1.2.3.4",
            country=country_mf,
            city=_mf("N/A"),
            asn=asn_mf,
            as_name=as_name_mf,
            ip_range=range_mf,
            is_isp=False,
            classifications={"c2-server": c2_ca},
        )

        d = r.to_dict()

        assert d["ip"] == "1.2.3.4"
        assert d["country"]["value"] == "CN"
        assert d["country"]["confidence"] == 85
        assert d["country"]["sources"][0]["source"] == "ipinfo_lite"
        assert d["classifications"]["c2-server"]["detected"] is True
        assert d["classifications"]["c2-server"]["confidence"] == 85
        assert d["classifications"]["c2-server"]["verdict"] == "malicious"
        assert d["classifications"]["c2-server"]["has_archive"] is c2_ca.has_archive
        assert d["is_isp"] is False
        assert "error" not in d

    def test_threat_summary_confidence_is_group_max(self):
        """证据级重融合后,无 details 的旧载荷(指控组在但明细池空)仍走选角
        逻辑:worst-first 组内 max。回归:66.132.186.179 桌面 threat 65 vs
        网页 threatSummary 94 —— min() 取字典序第一成员是任意值;空池回退
        分支必须与网页 threatDisplay.threatSummary 的组内 max 对齐。"""
        def ca(name, conf):
            return ClassificationAssessment(
                name, "malicious", True, conf, "corroboration", [],
                corroborated=True)

        r = LookupResult(
            ip="66.132.186.179",
            country=MergedField("US", 85, "voting", []),
            city=MergedField("N/A", 0, "voting", []),
            asn=MergedField(0, 0, "voting", []),
            as_name=MergedField("N/A", 0, "voting", []),
            ip_range=MergedField("N/A", 0, "voting", []),
            is_isp=False,
            classifications={
                "abuse-reports": ca("abuse-reports", 65),
                "scanner": ca("scanner", 94),
            },
        )
        assert r.threat_summary()["confidence"] == 94

    def test_error_result(self):
        r = LookupResult(
            ip="bad",
            country=MergedField("N/A", 0, "voting", []),
            city=MergedField("N/A", 0, "voting", []),
            asn=MergedField(0, 0, "voting", []),
            as_name=MergedField("N/A", 0, "voting", []),
            ip_range=MergedField("N/A", 0, "voting", []),
            is_isp=False,
            classifications={},
            error="invalid IP format",
        )
        d = r.to_dict()
        assert d["error"] == "invalid IP format"
        assert d["country"]["confidence"] == 0
        assert d["classifications"] == {}


# ── AssetStatement + LookupResult.attributes ──


def _mf(v):
    return MergedField(v, 0, "voting", [])


def test_asset_statement_construction():
    s = AssetStatement(source="ip2proxy", value=True, native_type="VPN")
    assert s.source == "ip2proxy"
    assert s.value is True
    assert s.native_type == "VPN"


def test_asset_statement_native_type_defaults_none():
    s = AssetStatement(source="cn_isp", value="中国电信")
    assert s.native_type is None


def test_lookup_result_attributes_defaults_empty():
    r = LookupResult(
        ip="1.2.3.4", country=_mf("N/A"), city=_mf("N/A"), asn=_mf(0), as_name=_mf("N/A"),
        ip_range=_mf("N/A"), is_isp=False, classifications={})
    assert r.attributes == {}


def test_to_dict_serializes_attributes():
    r = LookupResult(
        ip="1.2.3.4", country=_mf("US"), city=_mf("N/A"), asn=_mf(13335), as_name=_mf("Cloudflare"),
        ip_range=_mf("1.2.3.0/24"), is_isp=False, classifications={},
        attributes={
            "is_proxy": [AssetStatement(source="ip2proxy", value=True, native_type="VPN")],
            "carrier": [AssetStatement(source="cn_isp", value="中国电信")],
        })
    d = r.to_dict()
    assert d["attributes"] == {
        "is_proxy": [{"source": "ip2proxy", "value": True, "native_type": "VPN"}],
        "carrier": [{"source": "cn_isp", "value": "中国电信", "native_type": None}],
    }


def test_to_dict_attributes_empty_when_unset():
    r = LookupResult(
        ip="1.2.3.4", country=_mf("US"), city=_mf("N/A"), asn=_mf(0), as_name=_mf("N/A"),
        ip_range=_mf("N/A"), is_isp=False, classifications={})
    assert r.to_dict()["attributes"] == {}


def test_lookup_result_to_dict_contains_city():
    from ipdb._types import LookupResult, MergedField
    r = LookupResult(
        ip="1.2.3.4",
        country=MergedField("US", 80, "voting", []),
        city=MergedField("Milan", 50, "voting", []),
        asn=MergedField(13335, 80, "voting", []),
        as_name=MergedField("Cloudflare", 80, "voting", []),
        ip_range=MergedField("1.0.0.0/24", 50, "voting", []),
        is_isp=False,
        classifications={},
    )
    d = r.to_dict()
    assert d["city"]["value"] == "Milan"


# ── threat_summary 证据级重融合(共识 2026-10-04)──

def _ca(ctype, verdict, conf, details, detected=True):
    return ClassificationAssessment(
        ctype, verdict, detected, conf, "logodds", [],
        corroborated=len(details) >= 2, details=details)


def _lr(classifications, attributes=None):
    return LookupResult(
        ip="1.2.3.4",
        country=_mf("US"), city=_mf("N/A"), asn=_mf(0), as_name=_mf("N/A"),
        ip_range=_mf("N/A"), is_isp=False,
        classifications=classifications, attributes=attributes or {})


class TestThreatSummaryFusion:
    """顶层 confidence 改证据级重融合:池化全部指控组证人明细后重算后验。
    本组测试一律省略 first_seen = 不衰减(coefficient 全强度),
    期望数字全部手算钉死,不随时钟漂移。"""

    def test_disjoint_sources_fuse_above_group_max(self):
        """C1(新语义,修前必红):两组不相交独立源 → 融合分 > max(两组组内分)。
        σ(2×logit(0.9)) = 99;旧选角只会给 90。"""
        g1 = _ca("scanner", "malicious", 90, [
            {"source": "threatfox", "verdict": "malicious", "reliability": 0.9}])
        g2 = _ca("abuse-reports", "malicious", 90, [
            {"source": "abuseipdb", "verdict": "malicious", "reliability": 0.9}])
        t = _lr({"scanner": g1, "abuse-reports": g2}).threat_summary()
        assert t["confidence"] > max(g1.confidence, g2.confidence)
        assert t["confidence"] == 99

    def test_single_group_degenerate_identity(self):
        """C2 专门测试:单指控组退化恒等——融合分必须恰好等于该组 confidence
        (数字相等,不是近似),因为两者走同一条 coefficient→dedup→σ 流水线。"""
        details = [
            {"source": "threatfox", "verdict": "malicious", "reliability": 0.85},
            {"source": "cisco_umbrella", "verdict": "malicious", "reliability": 0.75},
            {"source": "urlhaus", "verdict": "informational", "reliability": 0.9},
        ]
        expected = _lo.assertion_confidence(
            [c for _, c in _lo.dedup_lineage([
                ("threatfox", _lo.coefficient(0.85, None, "c2-server")),
                ("cisco_umbrella", _lo.coefficient(0.75, None, "c2-server")),
            ])])
        g = _ca("c2-server", "malicious", expected, details)
        t = _lr({"c2-server": g}).threat_summary()
        assert t["confidence"] == g.confidence
        assert t["confidence"] == 94   # σ(logit(0.85)+logit(0.75)) 手算钉死

    def test_shared_source_not_double_counted(self):
        """同源跨组不双计:融合分 == 该源单组结果 σ(logit(0.9)) = 90;
        朴素拼接会得 σ(2×logit(0.9)) = 99。"""
        g1 = _ca("scanner", "malicious", 90, [
            {"source": "abuseipdb", "verdict": "malicious", "reliability": 0.9}])
        g2 = _ca("abuse-reports", "malicious", 90, [
            {"source": "abuseipdb", "verdict": "malicious", "reliability": 0.9}])
        t = _lr({"scanner": g1, "abuse-reports": g2}).threat_summary()
        assert t["confidence"] == 90

    def test_pure_archive_groups_keep_selection_logic(self):
        """detected 非空但无指控组(全 informational/存档)→ 沿用现行选角
        (worst-first 组内 max,informational 组参与);绝不让空池 σ(0)=50 泄漏。"""
        g1 = _ca("vpn-proxy", "informational", 40, [
            {"source": "ip2location", "verdict": "informational", "reliability": 0.8}])
        g2 = _ca("datacenter", "informational", 70, [
            {"source": "ipinfo_lite", "verdict": "informational", "reliability": 0.9}])
        t = _lr({"vpn-proxy": g1, "datacenter": g2}).threat_summary()
        assert t["verdict"] == "informational"
        assert t["confidence"] == 70

    def test_suspicious_group_enters_pool(self):
        """指控章 = {malicious, suspicious}:suspicious 组证人也进后验。
        σ(2×logit(0.75)) = 90;suspicious 不入池则只会是 75。(新语义,修前必红)"""
        gm = _ca("scanner", "malicious", 75, [
            {"source": "abuseipdb", "verdict": "malicious", "reliability": 0.75}])
        gs = _ca("recon", "suspicious", 75, [
            {"source": "greynoise", "verdict": "suspicious", "reliability": 0.75}])
        t = _lr({"scanner": gm, "recon": gs}).threat_summary()
        assert t["verdict"] == "malicious"
        assert t["confidence"] == 90

    def test_verdict_types_is_cdn_keys_regression(self):
        """verdict(worst-first)、types(sorted detected)、is_cdn 三者原样保留。"""
        gm = _ca("scanner", "malicious", 90, [
            {"source": "threatfox", "verdict": "malicious", "reliability": 0.9}])
        ga = _ca("vpn-proxy", "informational", 60, [
            {"source": "ip2location", "verdict": "informational", "reliability": 0.8}])
        r = _lr({"scanner": gm, "vpn-proxy": ga},
                attributes={"is_cdn": [AssetStatement(source="ipinfo_lite", value=True)]})
        t = r.threat_summary()
        assert t["verdict"] == "malicious"
        assert t["types"] == ["scanner", "vpn-proxy"]
        assert t["is_cdn"] is True

    def test_no_detected_groups_still_benign_zero(self):
        """detected 为空 → 维持现行早退(benign/0);未 detected 组的指控 detail 不泄漏。"""
        g = _ca("scanner", "malicious", 90,
                [{"source": "threatfox", "verdict": "malicious", "reliability": 0.9}],
                detected=False)
        t = _lr({"scanner": g}).threat_summary()
        assert t == {"verdict": "benign", "confidence": 0, "types": [], "is_cdn": False}
