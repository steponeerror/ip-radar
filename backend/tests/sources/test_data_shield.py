"""duggytuxy/Data-Shield_IPv4_Blocklist (IpListSource) — Evidence shape assertions.

Covers: rebuild key count (comment/blank-line noise filtered), query round-trip
blacklist/malicious at the r=0.50 aggregator floor, Evidence-contract equality,
and out-of-list IP resolves to nothing. Sample lines verbatim from the live
prod feed (2026-10-19 fetch; bare IPv4, no header).
"""
from pathlib import Path

from ipdb._sources.data_shield import DataShieldSource

SAMPLE = (
    "# prod_data-shield_ipv4_blocklist\n"
    "\n"
    "1.0.164.165\n"
    "1.6.29.197\n"
    "1.7.51.205\n"
)


def test_data_shield_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "data_shield.txt").write_text(SAMPLE)
    s = DataShieldSource(data_dir=tmp_path)
    assert s.rebuild() == 3                     # 3 IPs; comment + blank lines filtered as noise
    recs = s.query("1.0.164.165")
    assert recs, "query must return a record"
    rec = recs[0]
    assert rec["classification_type"] == "blacklist"
    assert "native_type" not in (rec.get("extra") or {})
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.50           # aggregator floor: no per-row attribution


def test_data_shield_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "data_shield.txt").write_text("9.9.9.9\n")
    s = DataShieldSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("9.9.9.9")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.50,
    ).to_dict()


def test_data_shield_non_present_ip_resolves_empty(tmp_path: Path):
    """An IP not in the feed resolves to nothing."""
    (tmp_path / "data_shield.txt").write_text("1.2.3.4\n")
    s = DataShieldSource(data_dir=tmp_path)
    s.load()
    assert not s.query("203.0.113.42")       # TEST-NET-3, never in a blocklist
