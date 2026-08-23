"""A 类源 harvest 放开 v6:yield 两族,generic rebuild 自动分区(T8)。

五个 Source 子类(geolite_city/iptoasn/dataplane/reportedip/cdn_edges)走
Task 4 的通用双族 rebuild——本任务只让各自 harvest()/_parse 不再丢弃 v6。
"""
import csv
import ipaddress
import json

import pytest


# ── geolite_city:monkeypatch maxminddb.open_database 边界 ──

def test_geolite_harvest_yields_v6(tmp_path, monkeypatch):
    """harvest 只用 str(network) 与 record 字段;删 version!=4 过滤后两族齐出。"""
    import maxminddb
    from ipdb._sources.geolite_city import GeoLiteCitySource

    rows = [
        (ipaddress.ip_network("8.8.4.0/24"),
         {"country": {"iso_code": "US"}, "city": {"names": {}}}),
        (ipaddress.ip_network("2600:1f18::/32"),
         {"country": {"iso_code": "US"},
          "city": {"names": {"en": "Ashburn"}}}),
    ]

    class _FakeReader:
        def __iter__(self):
            return iter(rows)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(maxminddb, "open_database", lambda _p: _FakeReader())
    src = GeoLiteCitySource(tmp_path)
    got = {str(cidr): ev for cidr, ev in src.harvest()}
    assert "2600:1f18::/32" in got
    assert got["2600:1f18::/32"].city == "Ashburn"
    assert got["2600:1f18::/32"].country_code == "US"
    assert "8.8.4.0/24" in got                      # v4 不回归


# ── iptoasn:真文件直测 ──

def test_iptoasn_v6_harvest(tmp_path):
    from ipdb._sources.iptoasn import IPtoASNSource
    src = IPtoASNSource(tmp_path)
    (tmp_path / "ip-to-asn.tsv").write_text(
        "1.0.0.0\t1.0.0.255\t13335\tAU\tCLOUDFLARENET\n"
        "2001:200::\t2001:200:ffff:ffff:ffff:ffff:ffff:ffff\t2500\tJP\tWIDE Internet\n")
    got = {c: ev for c, ev in src.harvest()}
    assert "2001:200::/32" in got
    assert got["2001:200::/32"].asn == 2500
    assert got["2001:200::/32"].as_name == "WIDE Internet"
    assert got["2001:200::/32"].country_code == "JP"
    assert got["2001:200::/32"].ip_range == "2001:200::/32"
    assert "1.0.0.0/24" in got                     # v4 不回归


def test_iptoasn_mixed_family_row_skipped(tmp_path):
    """start/end 跨族的畸形行按 brief 跳过,不 raise。"""
    from ipdb._sources.iptoasn import IPtoASNSource
    src = IPtoASNSource(tmp_path)
    (tmp_path / "ip-to-asn.tsv").write_text(
        "1.0.0.0\t2001:db8::ffff\t64512\tXX\tMIXED\n")
    assert list(src.harvest()) == []


# ── dataplane:pipe 格式真文件 ──

def test_dataplane_v6_harvest(tmp_path):
    from ipdb._sources.dataplane import DataplaneSource
    src = DataplaneSource(tmp_path)
    (tmp_path / "dataplane.txt").write_text(
        "12345 | Foo Telecom | 1.2.3.4 | 2026-08-23 00:00:00 | sshpwauth\n"
        "2500 | WIDE Internet | 2001:db8::1 | 2026-08-23 01:00:00 | dnsrd\n")
    got = {c: ev for c, ev in src.harvest()}
    assert "2001:db8::1/128" in got                # 裸 v6 → /128
    assert got["2001:db8::1/128"].asn == 2500
    assert got["2001:db8::1/128"].classification_type == "scanner"
    assert "1.2.3.4/32" in got                     # v4 不回归


# ── reportedip:CSV 真文件(yield 形态=裸 ip)──

def test_reportedip_v6_harvest(tmp_path):
    from ipdb._sources.reportedip import ReportedIPSource
    src = ReportedIPSource(tmp_path)
    (tmp_path / "reportedip.csv").write_text(
        "ip,confidence,categories,last_reported\n"
        "1.2.3.4,90,\"1;5\",2026-08-23 04:05:00\n"
        "2001:db8::dead,85,3,2026-08-23 04:05:00\n")
    got = {}
    for cidr, ev in src.harvest():
        got[cidr] = ev
    assert "2001:db8::dead" in got                 # 裸 v6 不再被 drop
    assert got["2001:db8::dead"].verdict == "malicious"
    assert got["2001:db8::dead"].last_seen == "2026-08-23T04:05:00"
    assert "1.2.3.4" in got                        # v4 不回归


# ── cdn_edges:_parse 单元 + harvest(合成 csv 中间产物)──

def test_cdn_parse_yields_v6():
    from ipdb._sources.cdn_edges import _parse
    aws = json.dumps({
        "prefixes": [{"ip_prefix": "1.2.3.0/24", "service": "CLOUDFRONT"}],
        "ipv6_prefixes": [{"ipv6_prefix": "2600:9000::/28",
                           "service": "CLOUDFRONT"}]})
    got = list(_parse(aws.encode(), "aws"))
    assert "2600:9000::/28" in got and "1.2.3.0/24" in got
    # 非 CLOUDFRONT 的 v6 前缀仍应被过滤(service 过滤对两族同构)
    aws2 = json.dumps({
        "prefixes": [],
        "ipv6_prefixes": [{"ipv6_prefix": "2600:9000::/28", "service": "EC2"}]})
    assert list(_parse(aws2.encode(), "aws")) == []
    fastly = json.dumps({"addresses": ["23.235.32.0/20", "2a04:4e40::/32"]})
    got = list(_parse(fastly.encode(), "fastly"))
    assert "2a04:4e40::/32" in got and "23.235.32.0/20" in got


def test_cdn_harvest_yields_v6(tmp_path):
    from ipdb._sources.cdn_edges import CdnEdgesSource
    src = CdnEdgesSource(tmp_path)
    (tmp_path / "cdn_edges.csv").write_text(
        "1.2.3.0/24,CloudFront\n"
        "2600:9000::/28,CloudFront\n")
    got = {c: ev for c, ev in src.harvest()}
    assert "2600:9000::/28" in got
    assert got["2600:9000::/28"].native_types == {"service": "CloudFront"}
    assert "1.2.3.0/24" in got                     # v4 不回归
