"""RTBH.com.tr national RTBH list (IpListSource) — Evidence shape assertions.

Covers: rebuild/query round-trip on verbatim sample lines (2026-10-10 fetch),
Evidence-contract equality, blackholed DDoS-class sources → dedicated ``ddos``
slot (first dedicated ddos witness), out-of-list empty.
"""
from pathlib import Path

from ipdb._sources.rtbh import RtbhSource

SAMPLE = (
    "1.0.164.165\n"
    "1.0.211.250\n"
    "1.1.140.232\n"
)


def test_rtbh_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "rtbh.txt").write_text(SAMPLE)
    s = RtbhSource(data_dir=tmp_path)
    assert s.rebuild() == 3
    rec = s.query("1.0.164.165")[0]
    assert rec["classification_type"] == "ddos"
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.70
    assert "native_type" not in (rec.get("extra") or {})


def test_rtbh_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "rtbh.txt").write_text("9.9.9.9\n")
    s = RtbhSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("9.9.9.9")[0]
    assert rec == Evidence(
        classification_type="ddos", verdict="malicious", reliability=0.70,
    ).to_dict()


def test_rtbh_non_present_ip_resolves_empty(tmp_path: Path):
    (tmp_path / "rtbh.txt").write_text("1.2.3.4\n")
    s = RtbhSource(data_dir=tmp_path)
    s.load()
    assert not s.query("203.0.113.42")
