"""Sblam! form-spam blacklist (IpListSource) — Evidence shape assertions.

Covers: rebuild key count with '#'-comment header filtered by the base
(zero parse hook — bare-IP list), query round-trip spam/malicious at r=0.55,
Evidence-contract equality, comment lines polluting nothing (a commented-out
IP stays unqueried), and an out-of-list IP resolves to nothing. Header lines
verbatim from the live feed (2026-10-19 fetch).
"""
from pathlib import Path

from ipdb._sources.sblam import SblamSource

SAMPLE = (
    "# HTTP spam sources identified by http://sblam.com.\n"
    "# Generated 2026-10-19 03:59:01\n"
    "# This is a list of HTML form (comment) spammers--not for blocking e-mail spam!\n"
    "# 203.0.113.99\n"
    "1.12.125.97\n"
    "2.27.4.166\n"
    "5.157.5.11\n"
)


def test_sblam_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "sblam").write_text(SAMPLE)
    s = SblamSource(data_dir=tmp_path)
    assert s.rebuild() == 3                     # 3 IPs; all '#' comment lines filtered
    recs = s.query("1.12.125.97")
    assert recs, "query must return a record"
    rec = recs[0]
    assert rec["classification_type"] == "spam"
    assert "native_type" not in (rec.get("extra") or {})
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.55


def test_sblam_comment_lines_pollute_nothing(tmp_path: Path):
    """A commented-out IP must never become evidence (zero parse, base skips '#')."""
    (tmp_path / "sblam").write_text(SAMPLE)
    s = SblamSource(data_dir=tmp_path)
    s.rebuild()
    assert not s.query("203.0.113.99")          # lives only in a '#' comment line


def test_sblam_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "sblam").write_text("9.9.9.9\n")
    s = SblamSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("9.9.9.9")[0]
    assert rec == Evidence(
        classification_type="spam", verdict="malicious", reliability=0.55,
    ).to_dict()


def test_sblam_non_present_ip_resolves_empty(tmp_path: Path):
    """An IP not in the feed resolves to nothing."""
    (tmp_path / "sblam").write_text("1.2.3.4\n")
    s = SblamSource(data_dir=tmp_path)
    s.load()
    assert not s.query("203.0.113.42")       # TEST-NET-3, never in a blocklist
