"""Knock-Knock honeypot blocklist (IpListSource) — Evidence shape assertions.

Covers: rebuild/query round-trip on verbatim sample lines (2026-10-10 fetch),
Evidence-contract equality, undifferentiated honeypot attackers → ``blacklist``
(binarydefense twin precedent, Convention 2: no force-fit), out-of-list empty.
"""
from pathlib import Path

from ipdb._sources.knock_knock import KnockKnockSource

SAMPLE = (
    "109.160.32.134\n"
    "179.254.176.47\n"
    "211.195.202.210\n"
    "103.68.69.14\n"
)


def test_knock_knock_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "knock_knock.txt").write_text(SAMPLE)
    s = KnockKnockSource(data_dir=tmp_path)
    assert s.rebuild() == 4
    rec = s.query("109.160.32.134")[0]
    assert rec["classification_type"] == "blacklist"
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.70
    assert "native_type" not in (rec.get("extra") or {})


def test_knock_knock_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "knock_knock.txt").write_text("9.9.9.9\n")
    s = KnockKnockSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("9.9.9.9")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.70,
    ).to_dict()


def test_knock_knock_non_present_ip_resolves_empty(tmp_path: Path):
    (tmp_path / "knock_knock.txt").write_text("1.2.3.4\n")
    s = KnockKnockSource(data_dir=tmp_path)
    s.load()
    assert not s.query("203.0.113.42")
