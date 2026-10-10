import pytest

from ipdb._sources.threatfox import ThreatFoxSource
from ipdb._sources.spamhaus import SpamhausSource
from ipdb._sources.emerging_threats import EmergingThreatsSource
from ipdb._sources.blocklist_de import BlocklistDeSource
from ipdb._sources.ip2proxy import IP2ProxySource
from ipdb._sources.tor_exits import TorExitSource
from ipdb._sources.x4bnet_vpn import X4BNetVPNSource
from ipdb._sources.otx import OtxSource
from ipdb._sources.firehol import FireholBlocklistSource
from ipdb._sources.ipsum import IPsumSource


# (source_cls, expected_type, expected_verdict, min_reliability)
DECLS = [
    (ThreatFoxSource, "c2-server", "malicious", 0.85),
    (OtxSource, "scanner", "malicious", 0.55),
    (SpamhausSource, "blacklist", "malicious", 0.90),
    (EmergingThreatsSource, "blacklist", "malicious", 0.85),
    (BlocklistDeSource, "blacklist", "malicious", 0.65),
    (IP2ProxySource, "proxy", "suspicious", 0.80),
    (TorExitSource, "tor", "suspicious", 0.95),
    (X4BNetVPNSource, "proxy", "suspicious", 0.70),
    (FireholBlocklistSource, "blacklist", "malicious", 0.50),
    (IPsumSource, "blacklist", "malicious", 0.55),
]


@pytest.mark.parametrize("cls,ctype,verdict,rel", DECLS)
def test_source_declarations(cls, ctype, verdict, rel):
    assert cls.classification_type == ctype, cls.__name__
    assert cls.verdict == verdict, cls.__name__
    assert cls.reliability >= rel, cls.__name__


from ipdb._sources.ip2proxy import _proxy_evidence
from pathlib import Path


def test_ip2proxy_proxy_evidence_vpn_emits_asset_keys():
    e = _proxy_evidence("VPN").to_dict()
    assert e["is_proxy"] is True
    assert e["_native_types"] == {"is_proxy": "VPN"}
    # extra.native_type retired (Plan B Task 3): identity is in _native_types
    assert "native_type" not in (e.get("extra") or {})


def test_ip2proxy_proxy_evidence_pub_emits_asset_keys():
    e = _proxy_evidence("PUB").to_dict()
    assert e["is_proxy"] is True
    assert e["_native_types"] == {"is_proxy": "PUB"}


def test_ip2proxy_proxy_evidence_dch_emits_hosting():
    e = _proxy_evidence("DCH").to_dict()
    assert e["is_hosting"] is True
    assert e["_native_types"] == {"is_hosting": "DCH"}


def test_ip2proxy_proxy_evidence_tor_emits_is_tor():
    e = _proxy_evidence("TOR").to_dict()
    assert e["is_tor"] is True
    assert e["_native_types"] == {"is_tor": "TOR"}


def test_ip2proxy_proxy_evidence_drops_unknown():
    assert _proxy_evidence("SES") is None


def test_tor_exits_get_insert_data_has_is_tor():
    src = TorExitSource(data_dir=Path("/tmp"))
    d = src.get_insert_data()
    assert d["is_tor"] is True
    assert d["_native_types"] == {"is_tor": "TOR"}


def test_x4bnet_vpn_get_insert_data_has_is_vpn():
    src = X4BNetVPNSource(data_dir=Path("/tmp"))
    d = src.get_insert_data()
    assert d["is_vpn"] is True
    assert d["_native_types"] == {"is_vpn": "VPN"}


def test_authority_axes_declared_by_real_producers(tmp_path):
    """SM-F1 权威矩阵删幻影:AUTORITATIVE_SOURCES 每轴的声明者必须是
    真正产出该键的源——四轴全部带真产出断言(修环 1 补齐 tor/service
    轴,与 ip2proxy/x4bnet 两对同强度)。幻影轴(is_malicious——无证据
    键生产者;is_hosting/is_mobile——ipinfo_lite 只产 geo/asn 槽)已删;
    is_hosting 真生产者 ip2proxy(DCH)/cloud_ranges 有意不扩面声明
    (裁决只删不补)。"""
    import ipdb._merge as m
    got = {k: sorted(v) for k, v in m.AUTHORITATIVE_SOURCES.items()}
    assert got == {
        "is_proxy": ["ip2proxy"],
        "is_tor": ["tor_exits"],
        "is_vpn": ["x4bnet_vpn"],
        "service": ["cdn_edges", "infra_services", "root_servers"],
    }
    # 声明者与产出者一致:每轴钉一个真产出断言(ip2proxy 产 is_proxy,
    # tor_exits 产 is_tor,x4bnet_vpn 产 is_vpn;service 轴两声明者都走
    # harvest 真形状——文件行 → service Evidence)。
    from ipdb._sources.ip2proxy import _proxy_evidence
    assert _proxy_evidence("VPN").is_proxy is True
    from ipdb._sources.tor_exits import TorExitSource
    assert TorExitSource(data_dir=tmp_path).get_insert_data()["is_tor"] is True
    from ipdb._sources.x4bnet_vpn import X4BNetVPNSource
    assert "is_vpn" in X4BNetVPNSource.get_insert_data(X4BNetVPNSource(data_dir=Path("/tmp")))
    from ipdb._sources.cdn_edges import CdnEdgesSource
    (tmp_path / "cdn_edges.csv").write_text("1.2.3.0/24,CloudFront\n")
    _, ev = next(CdnEdgesSource(data_dir=tmp_path).harvest())
    assert ev.service == "cdn" and ev.native_types == {"service": "CloudFront"}
    from ipdb._sources.infra_services import InfraServicesSource
    (tmp_path / "infra_services.csv").write_text("8.8.8.8,dns,Google Public DNS\n")
    _, ev = next(InfraServicesSource(data_dir=tmp_path).harvest())
    assert ev.service == "dns" and ev.native_types == {"service": "Google Public DNS"}
    from ipdb._sources.root_servers import RootServersSource
    (tmp_path / "root_servers.cache").write_text(
        "A.ROOT-SERVERS.NET.      3600000      A     198.41.0.4\n")
    _, ev = next(RootServersSource(data_dir=tmp_path).harvest())
    assert ev.service == "dns" and ev.native_types == {"service": "a root server"}


def test_reliability_floor_and_derived_flags():
    """spec 2026-08-29 §3.4:r ≥ 0.5 红线;聚合器源带 derived 标记。
    R1-F1:_logodds.DERIVED_SOURCES 由该 attr 集合灌装(registry
    fill-in-place),此处钉镜像——attr 面与集合面不得再漂移。"""
    import ipdb._registry as reg
    import ipdb._logodds as lo
    from ipdb._sources.greensnow import GreensnowSource
    for s in reg._sources:
        assert getattr(s, "reliability", 0.5) >= 0.5, f"{s.name} below r floor"
    assert GreensnowSource.derived is True  # R1-F1:补齐 attr 面漂移
    derived = {s.name for s in reg._sources if getattr(s, "derived", False)}
    assert derived == set(lo.DERIVED_SOURCES)


def test_derived_sources_registry_fill_sync(monkeypatch):
    """R1-F1:registry 灌装机制——源 attr 变动后重灌 → DERIVED_SOURCES
    原位同步(对象身份不变,clear+update;重绑定会切断 _eval/audit.py
    的值绑定,严禁)。"""
    import ipdb._registry as reg
    import ipdb._logodds as lo
    seed = {"firehol", "ipsum", "otx", "otx_subscribed", "greensnow", "drb_ra"}
    assert set(lo.DERIVED_SOURCES) == seed  # 导入时已灌装 = attr 全集
    src = next(s for s in reg._sources if s.name == "blocklist_de")
    try:
        monkeypatch.setattr(src, "derived", True, raising=False)
        reg._apply_derived_sources()
        assert "blocklist_de" in lo.DERIVED_SOURCES
        assert set(lo.DERIVED_SOURCES) == seed | {"blocklist_de"}
    finally:
        monkeypatch.undo()
        reg._apply_derived_sources()  # 状态复位不依赖断言路径
    assert set(lo.DERIVED_SOURCES) == seed
