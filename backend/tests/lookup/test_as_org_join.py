"""as_org 查询期 join(b/asorg-anycast 批,2026-10-10)。

caida_asorg 无 CIDR 面,无法走 per-IP 收集;lookup() 在 asn 胜者解出后经
org_for_asn() 钩子注入 as_org 值,再走 as_org 策略(NamingAuthority,单证人
conf=r 公理)。本文件钉三件事:join 生效、asn 缺席不出块、allowed_sources
照常过滤(per-key 白名单语义不因 join 旁路失效)。
"""
import pytest

from ipdb._types import SourceHealth


class FakeAsnSource:
    name = "ipinfo_lite"
    fields = ("country_code", "asn", "as_name", "ip_range")
    reliability = 0.95

    def __init__(self, asn=13335):
        self._data = {"country_code": "US", "asn": asn,
                      "as_name": "CLOUDFLARENET", "ip_range": "1.1.1.0/24"}

    def query(self, ip):
        return self._data

    def health(self):
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


class FakeAsorgSource:
    name = "caida_asorg"
    fields = ("as_org",)
    reliability = 0.8

    def query(self, ip):
        return None                               # 无 per-IP 面

    def org_for_asn(self, asn):
        return {13335: "Cloudflare, Inc."}.get(int(asn))

    def health(self):
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


def _patch(monkeypatch, sources):
    import ipdb._registry as reg
    monkeypatch.setattr(reg, "_sources", sources)


def test_join_populates_as_org_merged_field(monkeypatch):
    _patch(monkeypatch, [FakeAsnSource(), FakeAsorgSource()])
    from ipdb._registry import lookup
    r = lookup("1.1.1.1")
    assert r.as_org is not None
    assert r.as_org.value == "Cloudflare, Inc."
    assert r.as_org.algorithm == "authority"       # NamingAuthority 族
    assert r.as_org.confidence == 80               # 单源 conf = r(0.8)公理
    assert r.as_org.sources[0].source == "caida_asorg"


def test_no_asn_winner_leaves_as_org_none(monkeypatch):
    class NoAsnSource(FakeAsnSource):
        def query(self, ip):
            return {"country_code": "US"}          # asn 缺席

    _patch(monkeypatch, [NoAsnSource(), FakeAsorgSource()])
    from ipdb._registry import lookup
    r = lookup("1.1.1.1")
    assert r.as_org is None


def test_unknown_asn_leaves_as_org_none(monkeypatch):
    _patch(monkeypatch, [FakeAsnSource(asn=64512), FakeAsorgSource()])
    from ipdb._registry import lookup
    r = lookup("1.1.1.1")
    assert r.as_org is None


def test_allowed_sources_filters_join(monkeypatch):
    _patch(monkeypatch, [FakeAsnSource(), FakeAsorgSource()])
    from ipdb._registry import lookup
    r = lookup("1.1.1.1", allowed_sources=frozenset({"ipinfo_lite"}))
    assert r.as_org is None                        # 白名单不含 caida_asorg → join 不注入
