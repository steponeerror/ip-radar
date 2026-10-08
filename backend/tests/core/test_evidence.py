# backend/test_evidence.py
from ipdb._evidence import (Evidence, ALL_KNOWN, CANONICAL_SLOTS, CORE_FIELDS,
                            route_record)


def test_evidence_to_dict_drops_none_keeps_extra():
    e = Evidence(classification_type="c2-server", verdict="malicious",
                 malware_name="win.vidar", extra={"port": 80})
    d = e.to_dict()
    assert d["classification_type"] == "c2-server"
    assert d["malware_name"] == "win.vidar"
    assert d["extra"] == {"port": 80}
    # None-valued canonical slots are NOT serialized
    assert "country_code" not in d
    assert "comment" not in d


def test_route_record_keeps_known_folds_unknown_into_extra():
    raw = {"classification_type": "scanner", "country_code": "US",
           "asn": 123, "port": 22, "protocol": "ssh", "extra": {"native_type": "ssh"}}
    out = route_record(raw)
    # known keys kept at top level
    assert out["classification_type"] == "scanner"
    assert out["country_code"] == "US"
    assert out["asn"] == 123
    # unknown keys folded into extra (alongside existing extra)
    assert out["extra"]["port"] == 22
    assert out["extra"]["protocol"] == "ssh"
    assert out["extra"]["native_type"] == "ssh"
    # unknown keys removed from top level
    assert "port" not in out
    assert "protocol" not in out


def test_schema_tiers_disjoint_and_complete():
    assert CORE_FIELDS.isdisjoint(CANONICAL_SLOTS)
    assert CANONICAL_SLOTS == (frozenset({"country_code","asn","as_name","ip_range","city",
        "native_categories","comment","tags","reporter_count","last_seen",
        "is_proxy","is_hosting","is_tor","is_vpn","carrier","service","as_domain"}))
    assert ALL_KNOWN == CORE_FIELDS | CANONICAL_SLOTS


def test_evidence_native_types_serialized_as_internal_key():
    e = Evidence(classification_type="proxy", is_proxy=True,
                 native_types={"is_proxy": "VPN"})
    d = e.to_dict()
    assert d["_native_types"] == {"is_proxy": "VPN"}
    assert d["is_proxy"] is True
    assert "native_types" not in d          # field name not leaked


def test_evidence_reliability_default_not_serialized():
    e = Evidence(classification_type="proxy")   # no reliability set
    d = e.to_dict()
    assert "reliability" not in d               # None → omitted, lookup falls back to source attr
    e2 = Evidence(classification_type="proxy", reliability=0.8)
    assert e2.to_dict()["reliability"] == 0.8   # explicit reliability IS serialized


def test_route_record_keeps_is_isp_at_top_level():
    # is_isp is a lookup-path scalar (cn_isp sets it); it must stay top-level
    # so lookup's SCALAR_SLOTS | {"is_isp"} collection finds it (regression guard).
    raw = {"country_code": "CN", "is_isp": True, "ip_range": "1.0.0.0/24"}
    out = route_record(raw)
    assert out["is_isp"] is True                       # kept at top level
    assert "is_isp" not in (out.get("extra") or {})    # NOT folded into extra


def test_evidence_native_categories_serialized():
    e = Evidence(classification_type="exploit", native_categories=["15", "16"])
    d = e.to_dict()
    assert d["native_categories"] == ["15", "16"]


def test_verdict_empty_abstention_survives_roundtrip():
    """R17A-1:verdict="" 是弃权拼写,不得被丢空检查吃掉 —— 否则读路径
    _registry.lookup 的 item.get("verdict","malicious") 会把缺键兑底成
    恶意(弃权变指控,语义反转)。写入边 → route_record → to_observation
    读路径逐级保持 ""。"""
    from ipdb._merge import to_observation
    e = Evidence(classification_type="other", verdict="")
    d = e.to_dict()
    assert d["verdict"] == ""                      # 特判保留(先于丢空检查)
    routed = route_record(d)                       # 查询路径路由:verdict ∈ ALL_KNOWN 顶层
    assert routed["verdict"] == ""
    # 模拟 _registry.lookup 的读侧调用形状(_registry.py 兑底行同构)
    obs = to_observation("cloud_ranges", routed,
                         classification_type=routed["classification_type"],
                         verdict=routed.get("verdict", "malicious"),
                         reliability=0.95)
    assert obs.verdict == ""                       # 弃权,非 "malicious"
    # 反例:正常 verdict 照常保留;缺键(旧快照)仍兑底 malicious(兼容不动)
    assert Evidence(classification_type="proxy",
                    verdict="suspicious").to_dict()["verdict"] == "suspicious"
    legacy = route_record({"classification_type": "other"})
    obs2 = to_observation("old_snapshot", legacy,
                          classification_type="other",
                          verdict=legacy.get("verdict", "malicious"),
                          reliability=0.5)
    assert obs2.verdict == "malicious"


def test_evidence_native_categories_empty_not_serialized():
    e = Evidence(classification_type="exploit")   # no native_categories set
    d = e.to_dict()
    assert "native_categories" not in d           # empty list → omitted


def test_route_record_keeps_native_categories_top_level():
    raw = {"classification_type": "other", "native_categories": ["31", "55"]}
    out = route_record(raw)
    assert out["native_categories"] == ["31", "55"]          # stays top level
    assert "native_categories" not in (out.get("extra") or {})  # NOT folded into extra
