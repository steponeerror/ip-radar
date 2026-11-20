"""metowolf/iplist china CIDR list — Source subclass (A-family harvest).
Data: plain per-line IPv4 CIDR list, no header, no comments, no timestamps
(raw.githubusercontent.com/metowolf/iplist master data/special/china.txt,
5569 lines at 2026-11-20 fetch; verbatim head below). Every member of the
list is a China-mainnet CIDR → scalar geo Evidence (country_code=CN,
ip_range), no fusion-core accusation (iptoasn archetype).
"""
from pathlib import Path
import pytest
from ipdb._sources.metowolf_iplist import MetowolfIplistSource
# verbatim from real fetch (head of data/special/china.txt)
SAMPLE = (
    "1.0.1.0/24\n"
    "1.0.2.0/23\n"
    "1.0.8.0/21\n"
    "1.0.32.0/19\n"
    "1.1.0.0/24\n"
)
def _src(tmp_path: Path, text: str) -> MetowolfIplistSource:
    (tmp_path / "metowolf_iplist_china.txt").write_text(text)
    return MetowolfIplistSource(data_dir=tmp_path)
def test_harvest_yields_scalar_geo_evidence_per_cidr(tmp_path: Path):
    s = _src(tmp_path, SAMPLE)
    rows = list(s.harvest())
    assert len(rows) == 5
    cidr, ev = rows[0]
    assert cidr == "1.0.1.0/24"
    assert ev.country_code == "CN"
    assert ev.ip_range == "1.0.1.0/24"
    assert ev.classification_type is None     # geo source accuses nothing
def test_rebuild_query_round_trip(tmp_path: Path):
    s = _src(tmp_path, SAMPLE)
    assert s.rebuild() == 5
    recs = s.query("1.0.2.7")                 # inside 1.0.2.0/23
    assert isinstance(recs, list) and len(recs) == 1
    rec = recs[0]
    assert rec["country_code"] == "CN"
    assert rec["ip_range"] == "1.0.2.0/23"
    assert "classification_type" not in rec and "asn" not in rec
    # fresh instance serves identical answers (rebuild→load roundtrip)
    s._reader.close()
    s2 = MetowolfIplistSource(data_dir=tmp_path)
    assert s2.load() == 5
    assert s2.query("1.0.2.7") == recs
def test_non_china_ip_resolves_empty(tmp_path: Path):
    s = _src(tmp_path, SAMPLE)
    s.rebuild()
    assert not s.query("8.8.8.8")             # Google DNS, never a CN mainnet CIDR
def test_noise_and_bad_key_lines_dropped(tmp_path: Path):
    """Comment/blank noise + key-column-garbage rows never enter the key count.
    (Real file has zero dirty lines; noise rows here exercise the shared
    list-parsing convention, not upstream data.)"""
    s = _src(tmp_path, "# comment\n\n" + SAMPLE + "not-an-ip\n999.1.2.3/40\n")
    assert s.rebuild() == 5                   # only the 5 real CIDRs
    assert not s.query("1.2.3.4")
def test_module_aliases_importable():
    from ipdb._sources import metowolf_iplist as m
    assert m.MetowolfIPListSource is MetowolfIplistSource
    assert m.MetowolfIpListSource is MetowolfIplistSource
    # aliases must not enter dir() (registry double-registration guard)
    assert "MetowolfIPListSource" not in dir(m)
    assert "MetowolfIpListSource" not in dir(m)
