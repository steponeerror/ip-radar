"""myip.ms htaccess blacklist (IpListSource + deny-from parse_raw) — assertions.

Covers: parse_raw strips the `deny from ` prefix and drops header comments,
blank lines, prefix-less lines and non-IP payloads (v6 kept); the normalized
on-disk form (parse_raw output — download() installs exactly this) rebuilds to
the expected key counts (v4 master + v6 side family) and queries
blacklist/malicious at r=0.55; a commented-out or unprefixed IP never becomes
evidence. Header lines verbatim from the live feed (2026-10-19 fetch).
"""
from pathlib import Path

from ipdb._sources.myip_ms import MyipMsSource

SAMPLE = (
    "# on Mon, 19 Oct 2026 05:32:41 +0000 Last 10days Blacklist IPs\n"
    "###############################################################################\n"
    "# LIVE BLACKLIST IPv4/IPv6 ADDRESSES DATABASE\n"
    "# URL: https://myip.ms/browse/blacklist\n"
    "# Copyright 2026, Myip.ms\n"
    "# File Format: deny from ..IPAddress.. (compatible with .htaccess)\n"
    "###############################################################################\n"
    "#  Myip.ms Blacklist IPs in this List: 1,621 ip (09 October 2026 - 19 October 2026)\n"
    "\n"
    "deny from 34.178.198.175\n"
    "deny from 157.157.221.34\n"
    "deny from 45.148.65.28\n"
    "deny from 2600:1f28:365:80b0:a6e5:c50a:613e:28ed\n"
    "# deny from 203.0.113.99\n"
    "216.73.216.190\n"
    "deny from not_an_ip\n"
)


def _normalized() -> str:
    """parse_raw output — the on-disk format download() installs (wire → disk)."""
    entries = MyipMsSource.__new__(MyipMsSource).parse_raw(SAMPLE.encode())
    return "\n".join(entries) + "\n"


def test_myip_ms_parse_raw_strips_prefix_and_drops_noise():
    entries = MyipMsSource.__new__(MyipMsSource).parse_raw(SAMPLE.encode())
    assert entries == [
        "34.178.198.175", "157.157.221.34", "45.148.65.28",
        "2600:1f28:365:80b0:a6e5:c50a:613e:28ed",
    ]   # comments/blank/prefix-less/non-IP dropped; v6 kept (version-agnostic)


def test_myip_ms_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "myip_ms").write_text(_normalized())
    s = MyipMsSource(data_dir=tmp_path)
    assert s.rebuild() == 3                     # 3 v4 keys; v6 line lives in the side family
    assert s._count6 == 1
    recs = s.query("34.178.198.175")
    assert recs, "query must return a record"
    rec = recs[0]
    assert rec["classification_type"] == "blacklist"
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.55


def test_myip_ms_noise_lines_pollute_nothing(tmp_path: Path):
    """A commented-out or prefix-less IP must never become evidence."""
    (tmp_path / "myip_ms").write_text(_normalized())
    s = MyipMsSource(data_dir=tmp_path)
    s.rebuild()
    assert not s.query("203.0.113.99")          # lives only in a '#' comment line
    assert not s.query("216.73.216.190")        # bare IP line, no 'deny from' prefix


def test_myip_ms_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "myip_ms").write_text(_normalized())
    s = MyipMsSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("157.157.221.34")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.55,
    ).to_dict()
