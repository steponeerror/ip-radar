"""caida_asorg:ASN 键查询期 join 源(b/asorg-anycast 批,2026-10-10)。

生命周期合同差异:全仓唯一无 LMDB 的源——数据是 ASN→组织名(无 CIDR 可
入库),load()/rebuild() 把文件解析为内存 dict,query(ip) 恒 None,
org_for_asn() 是 lookup 的 join 钩子(端到端见 test_as_org_join.py)。
"""
from ipdb._sources.caida_asorg import CaidaAsorgSource

# 真实格式样本(202610 快照原文节选 + aut-4134 的 org 记录)
SAMPLE = """\
# name: AS Org
# date: 202610
# program start time: 2026-10-07 01:12:38
13335|20170217|CLOUDFLARENET|CLOUD14-ARIN|28408e4f0567_ARIN|ARIN
4134|20210615|CHINANET-BACKBONE|@aut-4134-APNIC|A914EAE4_APNIC|APNIC
CLOUD14-ARIN|20170217|Cloudflare, Inc.|US|ARIN
@aut-4134-APNIC|20210615|CHINANET|CN|APNIC
"""


def _make(tmp_path):
    (tmp_path / "as-org2info.txt").write_text(SAMPLE, encoding="utf-8")
    return CaidaAsorgSource(tmp_path)


def test_rebuild_parses_aut_org_join(tmp_path):
    s = _make(tmp_path)
    n = s.rebuild()
    assert n == 2                                  # 两个 aut 行均 join 上 org
    assert s.org_for_asn(13335) == "Cloudflare, Inc."
    assert s.org_for_asn(4134) == "CHINANET"
    assert s.org_for_asn(999) is None


def test_query_is_none_never_per_ip(tmp_path):
    s = _make(tmp_path)
    s.rebuild()
    assert s.query("1.1.1.1") is None              # 无 CIDR 面,恒不答


def test_health_loaded_and_count(tmp_path):
    s = _make(tmp_path)
    s.load()
    h = s.health()
    assert h.loaded is True
    assert h.record_count == 2
    assert h.is_stale is False                     # 刚写的新文件


def test_load_without_file_returns_zero(tmp_path):
    s = CaidaAsorgSource(tmp_path)
    assert s.load() == 0
    assert s.health().loaded is False


def test_fresh_instance_reopens_same_dict(tmp_path):
    _make(tmp_path).rebuild()
    s2 = CaidaAsorgSource(tmp_path)
    assert s2.load() == 2
    assert s2.org_for_asn(13335) == "Cloudflare, Inc."


def test_metadata_declared_in_file(tmp_path):
    s = _make(tmp_path)
    assert s.category == "geo_asn"
    assert 0.0 < s.reliability <= 1.0
    assert "as_org" in s.authoritative_for
