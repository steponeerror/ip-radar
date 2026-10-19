"""USTC blackip campus self-protection blacklist (IpListSource) — shape assertions.

Covers: mixed sample (v4 bare IP + v4 CIDR + v6 CIDR — the feed's native
shape) → rebuild key count (v4 main store only; v6 rows live in the parallel
family) → query blacklist/malicious at r=0.55 → the CIDR hit-point property
(an in-net IP resolves the CIDR row, one step out-of-net resolves nothing)
→ v6 rows land in the v6 family. Sample lines verbatim from the live feed
(2026-10-19 fetch, dossier docs/research/2026-10-19-tails-discover.md §7).
"""
from pathlib import Path

from ipdb._sources.ustc_blackip import UstcBlackipSource

SAMPLE = (
    "1.28.44.177\n"
    "1.10.16.0/20\n"
    "2001:678:e4c::/48\n"
)


def test_ustc_blackip_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "ustc_blackip").write_text(SAMPLE)
    s = UstcBlackipSource(data_dir=tmp_path)
    assert s.rebuild() == 2     # v4 keys: 1 bare IP + 1 CIDR; the v6 row is not in this count
    from ipdb._evidence import Evidence
    rec = s.query("1.28.44.177")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.55,
    ).to_dict()


def test_ustc_blackip_cidr_hit_point(tmp_path: Path):
    """An in-net IP resolves the CIDR row (IpListSource CIDR semantics)."""
    (tmp_path / "ustc_blackip").write_text(SAMPLE)
    s = UstcBlackipSource(data_dir=tmp_path)
    s.rebuild()
    recs = s.query("1.10.31.200")       # 1.10.16.0/20 tail segment, inside the net
    assert recs and recs[0]["classification_type"] == "blacklist"
    assert not s.query("1.10.32.1")     # one step out of the net


def test_ustc_blackip_v6_rows_live_in_v6_family(tmp_path: Path):
    (tmp_path / "ustc_blackip").write_text(SAMPLE)
    s = UstcBlackipSource(data_dir=tmp_path)
    s.rebuild()
    assert s._count6 == 1               # v6 parallel-family sidecar count
    recs = s.query("2001:678:e4c::1")   # v6 query path; in-net address hits the v6 CIDR
    assert recs and recs[0]["verdict"] == "malicious"
