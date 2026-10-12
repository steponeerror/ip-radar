"""End-to-end: real source evidence shapes → load dedup → lookup → attributes."""
import pytest
from pathlib import Path

from ipdb._sources._base import CsvSource
from ipdb._merge import FactualVoting, RangeSpecificity
from ipdb._registry import lookup
from ipdb._types import SourceHealth


class _Ip2ProxyFixture(CsvSource):
    """CsvSource feeding ip2proxy-shaped rows for a single CIDR."""
    name = "ip2proxy"
    filename = "ip2proxy.csv"
    fields = ("is_proxy",)

    def parse_row(self, row):
        from ipdb._sources.ip2proxy import _proxy_evidence
        # row = [ip_or_range, proxy_type]
        ev = _proxy_evidence(row[1])
        if ev is None:
            return None
        d = ev.to_dict()
        d["_ip"] = row[0].strip()
        return d


class _TorFixture(CsvSource):
    name = "tor_exits"
    filename = "tor.csv"
    fields = ("is_tor",)

    def parse_row(self, row):
        return {"_ip": row[0].strip(), "classification_type": "tor",
                "verdict": "suspicious", "extra": {"native_type": "tor"},
                "is_tor": True, "_native_types": {"is_tor": "TOR"}}


class _ScalarFixture:
    name = "ipinfo_lite"
    fields = ("country_code", "asn", "as_name", "ip_range")

    def query(self, ip):
        return {"country_code": "US", "asn": 13335, "as_name": "Cloudflare",
                "ip_range": "1.2.3.0/24"}

    def health(self):
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


def test_lookup_aggregates_attributes_from_multiple_sources(tmp_path, monkeypatch):
    import ipdb._registry as reg

    # ip2proxy: two rows, VPN + DCH (different native_type, both kept)
    ip2p = _Ip2ProxyFixture(data_dir=tmp_path)
    ip2p._path = tmp_path / "ip2proxy.csv"
    ip2p._path.write_text("1.2.3.0/24,VPN\n1.2.3.0/24,DCH\n")
    ip2p.rebuild()

    # tor: single exit
    tor = _TorFixture(data_dir=tmp_path)
    tor._path = tmp_path / "tor.csv"
    tor._path.write_text("1.2.3.4\n")
    tor.rebuild()

    scalar = _ScalarFixture()
    monkeypatch.setattr(reg, "_sources", [ip2p, tor, scalar])
    monkeypatch.setattr(reg, "_strategies", {
        "country_code": FactualVoting(default="N/A"),
        "city": FactualVoting(default="N/A"),
        "asn": FactualVoting(default=0),
        "as_name": FactualVoting(default="N/A"),
        "ip_range": RangeSpecificity(),
    })

    r = lookup("1.2.3.4")
    # is_proxy from VPN row
    assert "is_proxy" in r.attributes
    assert any(s.native_type == "VPN" for s in r.attributes["is_proxy"])
    # is_hosting from DCH row
    assert "is_hosting" in r.attributes
    assert r.attributes["is_hosting"][0].native_type == "DCH"
    # is_tor from tor fixture
    assert "is_tor" in r.attributes
    assert r.attributes["is_tor"][0].source == "tor_exits"
    # Threat channel:tor_exits 仍产 tor 指控组;ip2proxy VPN 已全量弃权
    # (ADR 0001)——proxy 组不再由 ip2proxy 产生
    assert "proxy" not in r.classifications
    assert "tor" in r.classifications


def _lookup_ip2proxy_only(rows: str, ip: str, tmp_path, monkeypatch):
    """lookup 舱:只挂 ip2proxy fixture(真 harvest→LMDB→query 链),
    策略表照既有测试同口径 monkeypatch。ADR 0001 红测共用。"""
    import ipdb._registry as reg

    ip2p = _Ip2ProxyFixture(data_dir=tmp_path)
    ip2p._path = tmp_path / "ip2proxy.csv"
    ip2p._path.write_text(rows)
    ip2p.rebuild()

    monkeypatch.setattr(reg, "_sources", [ip2p])
    monkeypatch.setattr(reg, "_strategies", {
        "country_code": FactualVoting(default="N/A"),
        "city": FactualVoting(default="N/A"),
        "asn": FactualVoting(default=0),
        "as_name": FactualVoting(default="N/A"),
        "ip_range": RangeSpecificity(),
    })
    return lookup(ip)


def test_lookup_ip2proxy_vpn_abstains_no_proxy_group(tmp_path, monkeypatch):
    """ADR 0001(grill Q1)红测①:VPN 段 IP —— classifications 无 proxy
    指控组,attributes 有 is_proxy=True(标签照常呈现)。"""
    r = _lookup_ip2proxy_only("1.2.3.0/24,VPN\n", "1.2.3.4", tmp_path, monkeypatch)
    assert "proxy" not in r.classifications
    assert r.classifications == {}
    assert r.attributes["is_proxy"][0].value is True
    assert r.attributes["is_proxy"][0].native_type == "VPN"


def test_lookup_ip2proxy_tor_abstains_no_tor_group(tmp_path, monkeypatch):
    """ADR 0001 红测②:TOR 同构 —— 无 tor 指控组,is_tor 标签照常。"""
    r = _lookup_ip2proxy_only("1.2.3.0/24,TOR\n", "1.2.3.4", tmp_path, monkeypatch)
    assert "tor" not in r.classifications
    assert r.classifications == {}
    assert r.attributes["is_tor"][0].value is True
    assert r.attributes["is_tor"][0].native_type == "TOR"


def test_lookup_ip2proxy_single_source_80_gone(tmp_path, monkeypatch):
    """ADR 0001 红测③:单源 80 分消失 —— 只喂 ip2proxy(旧:r=0.80 单源
    恰 80 分 suspicious,benign 语料 C3 崩塌主因;新:无指控证人 →
    benign/0,conf < 70)。"""
    r = _lookup_ip2proxy_only("1.2.3.0/24,VPN\n", "1.2.3.4", tmp_path, monkeypatch)
    threat = r.threat_summary()
    assert threat["confidence"] < 70
    assert threat["verdict"] == "benign"
    assert threat["types"] == []
