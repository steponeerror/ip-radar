import json

from ipdb._sources.cdn_edges import CdnEdgesSource, _FEEDS, _parse

# Combined-intermediate fixture (cidr,provider) — exactly what download() writes.
_FIXTURE = """\
13.32.0.0/15,CloudFront
52.84.0.0/15,CloudFront
173.245.48.0/20,Cloudflare
103.21.244.0/22,Cloudflare
151.101.0.0/16,Fastly
"""


def test_cdn_edges_loads_and_routes(tmp_path):
    (tmp_path / "cdn_edges.csv").write_text(_FIXTURE)
    s = CdnEdgesSource(data_dir=tmp_path)
    assert s.rebuild() == 5
    # CloudFront edge range
    r = s.query("13.32.10.20")[0]
    assert r["service"] == "cdn"
    assert r["_native_types"] == {"service": "CloudFront"}
    # Cloudflare
    assert s.query("173.245.48.5")[0]["_native_types"] == {"service": "Cloudflare"}
    # Fastly
    assert s.query("151.101.5.5")[0]["_native_types"] == {"service": "Fastly"}
    # not in feed
    assert s.query("8.8.8.8") == {}
    # asset-only source: the "malicious" default verdict must NOT leak
    assert "verdict" not in r


def test_cdn_edges_health_loaded_not_stale(tmp_path):
    (tmp_path / "cdn_edges.csv").write_text(_FIXTURE)
    s = CdnEdgesSource(data_dir=tmp_path)
    s.rebuild()
    h = s.health()
    assert h.loaded is True
    assert h.record_count == 5
    assert h.is_stale is False      # stale_days=7; fixture just written


def test_parse_aws_cloudfront_only():
    data = json.dumps({
        "prefixes": [
            {"ip_prefix": "13.32.0.0/15", "service": "CLOUDFRONT"},
            {"ip_prefix": "52.94.0.0/20", "service": "EC2"},   # not CloudFront → drop
        ],
        "ipv6_prefixes": [
            {"ipv6_prefix": "2600:1f18:4000::/40", "service": "CLOUDFRONT"},  # v6 CLOUDFRONT → kept
            {"ipv6_prefix": "2600:9000:100::/40", "service": "EC2"},  # not CloudFront → drop
        ],
    }).encode()
    assert list(_parse(data, "aws")) == ["13.32.0.0/15", "2600:1f18:4000::/40"]


def test_parse_cloudflare_strips_blanks_and_garbage():
    data = b"173.245.48.0/20\n103.21.244.0/22\n\n<html>oops\n"
    assert list(_parse(data, "cloudflare")) == ["173.245.48.0/20", "103.21.244.0/22"]


def test_parse_fastly_reads_both_arrays():
    """实测 feed 形态(2026-08-23 curl):v4 在 addresses,v6 在独立 ipv6_addresses。"""
    data = json.dumps({
        "addresses": ["151.101.0.0/16", "199.232.0.0/16"],
        "ipv6_addresses": ["2a04:4e40::/32", "2a04:4e42::/32"],
    }).encode()
    assert list(_parse(data, "fastly")) == [
        "151.101.0.0/16", "199.232.0.0/16",
        "2a04:4e40::/32", "2a04:4e42::/32",
    ]


def test_parse_fastly_missing_ipv6_array_ok():
    # ipv6_addresses 缺席或空:纯 v4,不炸不漏
    data = json.dumps({"addresses": ["151.101.0.0/16"]}).encode()
    assert list(_parse(data, "fastly")) == ["151.101.0.0/16"]


def test_parse_cloudflare_accepts_v6():
    raw = b"1.2.3.0/24\n2400:cb00::/32\n2606:4700::/32\n"
    got = list(_parse(raw, "cloudflare"))
    assert got == ["1.2.3.0/24", "2400:cb00::/32", "2606:4700::/32"]


def test_feeds_include_cloudflare_v6():
    urls = [u for _, u, _ in _FEEDS]
    assert "https://www.cloudflare.com/ips-v4" in urls
    assert "https://www.cloudflare.com/ips-v6" in urls

