"""anycast_census:UT-Dallas LACeS 任播普查(b/asorg-anycast 批,2026-10-10)。

partial=True(混播前缀)排除——宁少算,grill Q4 裁定;is_anycast 走 asset 槽。
"""
from ipdb._sources.anycast_census import AnycastCensusSource

SAMPLE = (
    "prefix,AB_ICMPv4,AB_TCPv4,AB_DNSv4,GCD_ICMPv4,GCD_TCPv4,partial,"
    "locations,backing_prefix,ASN\n"
    '1.1.1.0/24,29,30,29,72,27,False,"[]",1.1.1.0/24,13335\n'
    '1.2.3.0/24,3,0,3,1,0,True,"[]",1.2.3.0/24,99999\n'
    '9.9.9.0/24,5,5,5,5,5,False,"[]",9.9.9.0/24,19281\n'
)


def _make(tmp_path):
    (tmp_path / "anycast_census.csv").write_text(SAMPLE, encoding="utf-8")
    return AnycastCensusSource(tmp_path)


def test_rebuild_drops_partial_rows(tmp_path):
    s = _make(tmp_path)
    n = s.rebuild()
    assert n == 2                                  # partial=True 的 1.2.3.0/24 被排除
    assert s.health().record_count == 2


def test_query_hits_emit_is_anycast_asset(tmp_path):
    s = _make(tmp_path)
    s.rebuild()
    hit = s.query("1.1.1.1")
    assert hit and hit[0].get("is_anycast") is True
    # 弃权拼写(R17A-1):资产位不指控,verdict="" 必须在存储面存活
    assert hit[0].get("verdict") == ""
    assert hit[0].get("_native_types", {}).get("is_anycast") == "LACeS anycast census"
    assert s.query("9.9.9.9")[0].get("is_anycast") is True


def test_query_partial_prefix_misses(tmp_path):
    s = _make(tmp_path)
    s.rebuild()
    assert not s.query("1.2.3.4")                  # 混播前缀整段不入库


def test_query_outside_prefixes_misses(tmp_path):
    s = _make(tmp_path)
    s.rebuild()
    assert not s.query("8.8.8.8")


def test_metadata_declared_in_file(tmp_path):
    s = _make(tmp_path)
    assert s.category == "asset"
    assert 0.0 < s.reliability <= 1.0
    assert "is_anycast" in s.authoritative_for
