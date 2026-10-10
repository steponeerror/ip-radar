from ipdb._sources.infra_services import InfraServicesSource


def test_infra_services_loads_and_routes(tmp_path):
    s = InfraServicesSource(data_dir=tmp_path)
    # 43 总行 = 22 既有行(2026-10-10 根 13 行迁出至 root_servers 源)+ 21 新行:
    # 中文公共 DNS 9 行(AliDNS/DNSPod/114DNS/百度)+ 既有 5 家 resolver 的
    # IPv6 对 10 行(OpenDNS v6 经 ARIN RDAP OPENDNS-V6-NET-1 核验;
    # ControlD IPv6 无可核背书,宁少算不入)+ AliDNS v6 2 行(含于中文 9 行)
    # + Yandex 基础对 2 行。31 v4 + 12 v6 = 43 总行
    # (双族计数,n4 口径,同 test_reportedip 惯例:IPv6 行入 v6 族)
    assert s.rebuild() == 31
    # DNS resolver — service slot + provider on _native_types (→ AssetStatement.native_type)
    r = s.query("8.8.8.8")[0]
    assert r["service"] == "dns"
    assert r["_native_types"] == {"service": "Google Public DNS"}
    # 中文公共 DNS(AliDNS 官网 2026-10-09 亲核:223.5.5.5/223.6.6.6 + 两个 v6)
    assert s.query("223.5.5.5")[0]["_native_types"] == {"service": "AliDNS"}
    assert s.query("119.29.29.29")[0]["_native_types"] == {"service": "DNSPod Public DNS"}
    assert s.query("114.114.114.114")[0]["_native_types"] == {"service": "114DNS"}
    assert s.query("180.76.76.76")[0]["_native_types"] == {"service": "Baidu Public DNS"}
    assert s.query("77.88.8.8")[0]["_native_types"] == {"service": "Yandex DNS"}
    # IPv6 对:同 provider 同 service,经 v6 族查询路径
    assert s.query("2400:3200::1")[0]["_native_types"] == {"service": "AliDNS"}
    assert s.query("2620:fe::fe")[0]["_native_types"] == {"service": "Quad9"}
    assert s.query("2620:119:35::35")[0]["_native_types"] == {"service": "Cisco OpenDNS"}
    # 根服务器 13 行已迁出(infra_services 不再收录,→ root_servers 源)
    assert s.query("198.41.0.4") == {}
    # NTP
    assert s.query("216.239.35.0")[0]["service"] == "ntp"
    # not in feed
    assert s.query("1.2.3.4") == {}
    # asset-only source: verdict="" 弃权拼写由 to_dict 特判保留(R17A-1),
    # 读回按 "" 处理不兑底 malicious(旧断言「verdict 键缺席」随之反转)
    assert r["verdict"] == ""


def test_infra_services_health_loaded_not_stale(tmp_path):
    s = InfraServicesSource(data_dir=tmp_path)
    s.rebuild()
    h = s.health()
    assert h.loaded is True
    assert h.record_count == 31     # 31 v4 + 12 v6 = 43 总行(双族计数,n4 口径)
    assert h.covered_ips == 31      # 31 个 /32 单址 → 31 covered IPs(v4 口径)
    assert h.covered_v6_nets == 12  # 12 个 /128 单址 → 12 covered v6 nets
    assert h.is_stale is False      # stale_days=36500 (curated static)
