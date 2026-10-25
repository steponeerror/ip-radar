"""CriticalPathSecurity cps-collected-iocs.txt (IpListSource) — Evidence shape.

Covers: rebuild dedup key count (duplicate lines normalize to one LMDB key,
DQ-2 same-key-overwrite semantics; blank lines and comment lines dropped),
query round-trip blacklist/malicious at the r=0.50 aggregator floor,
Evidence-contract equality, and out-of-list IP resolves to nothing. Sample
lines verbatim from the live feed (2026-10-19 fetch: 47,405 lines, bare
IPv4, no header; 33% duplicates).
"""
from pathlib import Path

from ipdb._sources.cps_collected_iocs import CpsCollectedIocsSource

SAMPLE = (
    "# cps-collected-iocs\n"
    "\n"
    "3.135.207.58\n"
    "45.95.19.50\n"
    "51.15.17.89\n"
    "45.95.19.50\n"           # duplicate line — rebuild collapses to one key
    "172.93.107.67\n"
    "\n"                      # blank line — dropped, no key
    "199.247.7.82\n"
    "5.188.87.2\n"            # dossier exclusivity sample (2026-10-19)
    "5.188.87.2\n"            # duplicate line
)


def test_cps_collected_iocs_rebuild_dedupes_and_queries(tmp_path: Path):
    (tmp_path / "cps_collected_iocs.txt").write_text(SAMPLE)
    s = CpsCollectedIocsSource(data_dir=tmp_path)
    assert s.rebuild() == 6    # 8 payload lines − 2 duplicates = 6 distinct keys; blanks/comments dropped
    recs = s.query("45.95.19.50")
    assert recs, "query must return a record"
    rec = recs[0]
    assert rec["classification_type"] == "blacklist"
    assert "native_type" not in (rec.get("extra") or {})
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.50       # aggregator floor: no per-row attribution


def test_cps_collected_iocs_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    # 样本 IP 避开 curated infra 集(cps 载入面排 infra 噪声,issue #183)
    (tmp_path / "cps_collected_iocs.txt").write_text("45.148.65.28\n")
    s = CpsCollectedIocsSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("45.148.65.28")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.50,
    ).to_dict()


def test_cps_collected_iocs_non_present_ip_resolves_empty(tmp_path: Path):
    """An IP not in the feed resolves to nothing (rebuilt env, real miss)."""
    (tmp_path / "cps_collected_iocs.txt").write_text("1.2.3.4\n")
    s = CpsCollectedIocsSource(data_dir=tmp_path)
    s.rebuild()
    assert not s.query("203.0.113.42")       # TEST-NET-3, never in a blocklist
