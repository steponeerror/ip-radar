"""dan.me.uk Tor node list — IpListSource (plain IP-per-line, no timestamps).

Second independent witness for is_tor / classification `tor`
(tor_exits = official check.torproject.org exits; this list covers the
full relay set — observed ~10.7k rows at the /torlist/ URL, 2026-09-28).
"""
from pathlib import Path

from ipdb._sources.danmeuk_tor import DanMeUkTorSource


def test_danmeuk_rebuild_and_query_hit_miss(tmp_path: Path):
    f = tmp_path / "danmeuk_tor.txt"
    f.write_text("# comment\n203.0.113.7\n198.51.100.9\nnot-an-ip\n")
    s = DanMeUkTorSource(data_dir=tmp_path)
    n = s.rebuild()
    assert n == 2                                  # invalid line dropped
    assert s.health().record_count == 2
    rec = s.query("203.0.113.7")[0]                # hit → list of evidence
    assert rec["classification_type"] == "tor"
    assert rec["is_tor"] is True
    assert s.query("192.0.2.1") == {}              # miss → {}


def test_danmeuk_get_insert_data_is_evidence_contract(tmp_path: Path):
    """get_insert_data() must construct via Evidence so the declared
    reliability (0.85) reaches the record and _native_types stays in
    lockstep with Evidence.to_dict()."""
    from ipdb._evidence import Evidence
    s = DanMeUkTorSource(data_dir=tmp_path)
    assert s.get_insert_data() == Evidence(
        classification_type="tor", verdict="suspicious", reliability=0.85,
        is_tor=True, native_types={"is_tor": "RELAY"},
    ).to_dict()


def test_danmeuk_fresh_instance_load(tmp_path: Path):
    """Fresh instance on the same data_dir re-opens the env (convention 7 —
    never load() on the instance that rebuilt)."""
    (tmp_path / "danmeuk_tor.txt").write_text("203.0.113.7\n")
    s = DanMeUkTorSource(data_dir=tmp_path)
    s.rebuild()
    s2 = DanMeUkTorSource(data_dir=tmp_path)
    assert s2.load() == 1
    assert s2.query("203.0.113.7")[0]["is_tor"] is True


def test_danmeuk_metadata_declared():
    """Phase 3 step 6 contract: in-file metadata, no central dict edits."""
    s = DanMeUkTorSource.__new__(DanMeUkTorSource)
    assert s.category == "asset"
    assert 0 < s.reliability <= 1
    assert s.authoritative_for == ()               # witness, not veto (official stays authority)
    assert s.stale_days == 1
