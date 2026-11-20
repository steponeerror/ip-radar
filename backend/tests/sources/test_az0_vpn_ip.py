"""az0/vpn_ip — IpListSource (plain IPv4-per-line, inline '# provider' tags).

Publisher: github.com/az0/vpn_ip, GitHub Actions auto-updated (update-data.yml);
download face is the CDN mirror the README pins (az0-vpnip-public.oooninja.com),
no auth. First line is an internal `# <ISO8601>` freshness stamp, every data
line is `<ipv4> # <provider[,provider...]>` (no CIDR notation anywhere in the
2026-11-20 capture, 20634 lines). The '# provider' suffix is provenance
annotation only — it must not pollute the parsed key; rebuild's comment-stripping
already drops it, parse_raw normalizes the same way at download time.
Siblings: x4bnet_vpn (same VPN/asset archetype, authoritative witness),
danmeuk_tor (plain IP-per-line witness shape).
Fixtures below are verbatim lines from the 2026-11-20 capture.
"""
from pathlib import Path
import pytest
from ipdb._sources.az0_vpn_ip import Az0VpnIpSource


def test_az0_rebuild_and_query_hit_miss(tmp_path: Path):
    f = tmp_path / "az0_vpn_ip.txt"
    f.write_text(
        "# 2026-11-20T12:28:15Z\n"
        "1.220.90.178 # windscribe\n"
        "2.56.189.13 # nordvpn\n"
        "222.255.100.3 # pointtoserver.com\n"
        "not-an-ip # hola\n"
    )
    s = Az0VpnIpSource(data_dir=tmp_path)
    n = s.rebuild()
    assert n == 3                          # header + inline tags fine; bad line dropped
    assert s.health().record_count == 3
    rec = s.query("1.220.90.178")[0]
    assert rec["classification_type"] == "proxy"
    assert rec["is_vpn"] is True
    assert s.query("2.56.189.13")[0]["is_vpn"] is True
    assert s.query("192.0.2.1") == {}      # miss → {}


def test_az0_parse_raw_strips_inline_provider_tags():
    s = Az0VpnIpSource.__new__(Az0VpnIpSource)
    raw = (
        b"# 2026-11-20T12:28:15Z\n"
        b"1.220.90.178 # windscribe\n"
        b"2.56.189.13 # nordvpn\n"
        b"103.2.144.20 # c6gj-static.net,hola,su89-cdn.net,x-cdn-static.com,yg5sjx5kzy.com\n"
    )
    assert s.parse_raw(raw) == [
        "1.220.90.178", "2.56.189.13", "103.2.144.20",
    ]


def test_az0_get_insert_data_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    s = Az0VpnIpSource(data_dir=tmp_path)
    assert s.get_insert_data() == Evidence(
        classification_type="proxy", verdict="suspicious",
        reliability=s.reliability, is_vpn=True,
        native_types={"is_vpn": "VPN"},
    ).to_dict()


def test_az0_fresh_instance_load(tmp_path: Path):
    """Convention 7 — never load() on the instance that rebuilt."""
    (tmp_path / "az0_vpn_ip.txt").write_text("1.220.90.178 # windscribe\n")
    s = Az0VpnIpSource(data_dir=tmp_path)
    s.rebuild()
    if s._reader is not None:
        s._reader.close()
    if s._reader6 is not None:
        s._reader6.close()
    s2 = Az0VpnIpSource(data_dir=tmp_path)
    assert s2.load() == 1
    assert s2.query("1.220.90.178")[0]["is_vpn"] is True


def test_az0_metadata_declared():
    s = Az0VpnIpSource.__new__(Az0VpnIpSource)
    assert s.category == "asset"
    assert 0 < s.reliability <= 1
    assert "is_vpn" in s.fields


def test_az0_import_aliases():
    """PEP 562 spelling-family aliases import to the same class and stay out
    of dir() (registry auto-discovery must not double-register)."""
    import ipdb._sources.az0_vpn_ip as m
    assert m.Az0VpnIpSource is m.AZ0VpnIpSource
    assert m.Az0VpnIpSource is m.Az0VpnIPSource
    for alias in ("AZ0VpnIpSource", "Az0VpnIPSource"):
        assert alias not in dir(m)
