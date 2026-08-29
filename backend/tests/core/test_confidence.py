"""Unit tests for confidence scoring functions — integer confidence (0–100)."""
import pytest
import ipdb._merge as _merge
from ipdb._types import SourceAttribution, MergedField
from ipdb._merge import (
    FactualVoting, NamingAuthority, RangeSpecificity, LogOddsVoting,
)


class TestFactualVoting:
    def test_no_sources_returns_default_zero(self):
        fv = FactualVoting(default="N/A")
        result = fv.merge({}, {})
        assert result == MergedField("N/A", 0, "voting", [])

    def test_single_source_confidence_50(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"src1": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        result = fv.merge({"src1": "CN"}, {})
        assert result.value == "CN"
        assert result.confidence == 50

    def test_all_agree_confidence_100(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.80, "s2": 0.80, "s3": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        result = fv.merge({"s1": "CN", "s2": "CN", "s3": "CN"}, {})
        assert result.value == "CN"
        assert result.confidence == 100

    def test_majority_confidence_67(self, monkeypatch):
        """2/3 equal rel → Σ1.6/Σ2.4 = 66.67 → half-up 67"""
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.80, "s2": 0.80, "s3": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        result = fv.merge({"s1": "CN", "s2": "CN", "s3": "US"}, {})
        assert result.value == "CN"
        assert result.confidence == 67

    def test_weighted_share_5_of_6_83(self, monkeypatch):
        """5×0.6 vs 1×0.6 → Σ3.0/Σ3.6 = 83.33 → 83"""
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {f"s{i}": 0.6 for i in range(1, 7)})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        values = {f"s{i}": "CN" for i in range(1, 6)}
        values["s6"] = "US"
        result = fv.merge(values, {})
        assert result.value == "CN"
        assert result.confidence == 83

    def test_filters_empty_string(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        result = fv.merge({"s1": "", "s2": "CN"}, {})
        assert result.value == "CN"
        assert result.confidence == 50

    def test_filters_na_string(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        result = fv.merge({"s1": "N/A", "s2": "CN"}, {})
        assert result.value == "CN"
        assert result.confidence == 50

    def test_all_invalid_returns_default_zero(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default="N/A")
        result = fv.merge({"s1": "", "s2": "N/A"}, {})
        assert result.value == "N/A"
        assert result.confidence == 0

    def test_asn_zero_filtered(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default=0)
        result = fv.merge({"s1": 0, "s2": 4134}, {})
        assert result.value == 4134
        assert result.confidence == 50

    def test_asn_all_agree_confidence_100(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        fv = FactualVoting(default=0)
        result = fv.merge({"s1": 4134, "s2": 4134}, {})
        assert result.value == 4134
        assert result.confidence == 100


class TestNamingAuthority:
    def test_no_sources(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        na = NamingAuthority()
        result = na.merge({}, {"country": {}, "ip": "1.2.3.4"})
        assert result.value == "N/A"
        assert result.confidence == 0
        assert result.algorithm == "authority"

    def test_single_source(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        na = NamingAuthority()
        result = na.merge({"s1": "China Telecom"}, {"country": {}, "ip": "1.2.3.4"})
        assert result.value == "China Telecom"
        assert result.confidence == 80          # conf = r×100(spec §4)

    def test_no_authoritative_falls_back(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"ipinfo_lite": 0.95, "iptoasn": 0.90})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        na = NamingAuthority()
        result = na.merge(
            {"ipinfo_lite": "China Telecom", "iptoasn": "CHINANET"},
            {"country": {}, "ip": "1.2.3.4"},
        )
        assert result.value == "China Telecom"  # 最高 r 胜(docstring 语义)
        assert result.confidence == 95


class TestLogOddsVoting:
    """country/ASN 融合(spec 2026-08-29 §3.2/§4)。

    conf = round(P(MAP)·100),P(v)=exp(Σ logit r)/(Σ exp + 1)(背景质量 1);
    标量字段无 first_seen → 不衰减。"""

    def _lv(self, default="N/A"):
        return LogOddsVoting(default=default)

    def test_single_source_conf_equals_r(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"src1": 0.70})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv().merge({"src1": "CN"}, {})
        assert result.value == "CN"
        assert result.confidence == 70          # 决策 1:单源 conf = r
        assert result.algorithm == "logodds"

    def test_all_agree_three_sources(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.70, "s2": 0.70, "s3": 0.70})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv().merge({"s1": "CN", "s2": "CN", "s3": "CN"}, {})
        assert result.value == "CN"
        assert result.confidence == 93          # σ(3×0.8473)=0.927

    def test_majority_two_of_three(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.60, "s2": 0.60, "s3": 0.60})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv().merge({"s1": "CN", "s2": "CN", "s3": "US"}, {})
        assert result.value == "CN"
        assert result.confidence == 47          # exp(0.811)/(exp(0.811)+exp(0.405)+1)

    def test_weighted_minority_high_r(self, monkeypatch):
        """2×0.9 vs 3×0.3:r=0.3 低于生产红线 0.5,仅测试用;其 logit 为负,
        投给某类别反而拉低该类别。"""
        rels = {"h1": 0.90, "h2": 0.90,
               "l1": 0.30, "l2": 0.30, "l3": 0.30}
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", rels)
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        values = {"h1": "HK", "h2": "HK", "l1": "MO", "l2": "MO", "l3": "MO"}
        result = self._lv().merge(values, {})
        assert result.value == "HK"
        assert result.confidence == 99          # exp(4.394)/(exp(4.394)+exp(−2.542)+1)

    def test_alternatives_present_and_sorted(self, monkeypatch):
        """2:2 等权:conf ≈ 44,alternatives 降序(等率时按值字典序)。"""
        rels = {"s1": 0.66, "s2": 0.66, "s3": 0.66, "s4": 0.66}
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", rels)
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        values = {"s1": "HK", "s2": "HK", "s3": "US", "s4": "US"}
        result = self._lv().merge(values, {})
        assert result.confidence == 44
        assert [a["value"] for a in result.alternatives] == ["HK", "US"]
        assert result.alternatives[0]["probability"] >= result.alternatives[1]["probability"]
        assert all(0 <= a["probability"] <= 100 for a in result.alternatives)

    def test_alternatives_single_value_still_listed(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"src1": 0.70})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv().merge({"src1": "CN"}, {})
        assert result.alternatives == [{"value": "CN", "probability": 70.0}]

    def test_no_valid_returns_default_zero(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv(default=0).merge({"s1": "", "s2": 0}, {})
        assert result.value == 0
        assert result.confidence == 0
        assert result.algorithm == "logodds"

    def test_derived_lineage_dropped_when_weaker(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"firehol": 0.55, "blocklist_de": 0.62})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv().merge(
            {"firehol": "CN", "blocklist_de": "CN"}, {})
        assert result.confidence == 62          # firehol 系数低于非 derived max → 剔

    def test_derived_lineage_kept_when_stronger(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"firehol": 0.90, "blocklist_de": 0.62})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        result = self._lv().merge(
            {"firehol": "CN", "blocklist_de": "CN"}, {})
        assert result.confidence == 94          # Σ = logit(.9)+logit(.62) = 2.687 → 0.936


class TestRangeSpecificity:
    def test_no_sources(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        rs = RangeSpecificity()
        result = rs.merge({}, {"ip": "1.2.3.4"})
        assert result.value == "N/A"
        assert result.confidence == 0

    def test_single_valid_confidence_50(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"s1": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        rs = RangeSpecificity()
        result = rs.merge({"s1": "1.2.3.0/24"}, {"ip": "1.2.3.4"})
        assert result.value == "1.2.3.0/24"
        assert result.confidence == 50

    def test_picks_most_specific_confidence_85(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        rs = RangeSpecificity()
        result = rs.merge(
            {"s1": "1.2.0.0/16", "s2": "1.2.3.0/24"},
            {"ip": "1.2.3.4"},
        )
        assert result.value == "1.2.3.0/24"
        assert result.confidence == 85

    def test_excludes_non_containing(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        rs = RangeSpecificity()
        result = rs.merge(
            {"s1": "10.0.0.0/8", "s2": "1.2.3.0/24"},
            {"ip": "1.2.3.4"},
        )
        assert result.value == "1.2.3.0/24"
        assert result.confidence == 50

    def test_invalid_cidr_filtered(self, monkeypatch):
        monkeypatch.setattr(_merge, "SOURCE_RELIABILITY",
                            {"s1": 0.80, "s2": 0.80})
        monkeypatch.setattr(_merge, "AUTHORITATIVE_SOURCES", {})
        rs = RangeSpecificity()
        result = rs.merge(
            {"s1": "not-a-cidr", "s2": "1.2.3.0/24"},
            {"ip": "1.2.3.4"},
        )
        assert result.value == "1.2.3.0/24"
        assert result.confidence == 50
