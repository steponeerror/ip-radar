import ipdb._sources.infra_services as infra_mod
from ipdb._sources.infra_services import InfraServicesSource
from ipdb._sources._lmdb import needs_convert


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
    # benign② 良性断言(#188,2026-10-24):verdict="benign" + 断言域
    # ctype=服务角色(dns/ntp);弃权拼写 "" 期已随升格作废
    # (R17A-1 特判保留历史仅适用于其他 asset-only 源)
    assert r["verdict"] == "benign"
    assert r["classification_type"] == "dns"
    assert s.query("216.239.35.0")[0]["classification_type"] == "ntp"


def test_infra_services_health_loaded_not_stale(tmp_path):
    s = InfraServicesSource(data_dir=tmp_path)
    s.rebuild()
    h = s.health()
    assert h.loaded is True
    assert h.record_count == 31     # 31 v4 + 12 v6 = 43 总行(双族计数,n4 口径)
    assert h.covered_ips == 31      # 31 个 /32 单址 → 31 covered IPs(v4 口径)
    assert h.covered_v6_nets == 12  # 12 个 /128 单址 → 12 covered v6 nets
    assert h.is_stale is False      # stale_days=36500 (curated static)


# ── 投影语义(grill Q6,2026-10-11):_DATA 唯一真相源,data/ csv 是物化投影 ──


def test_projection_rematerializes_on_content_drift(tmp_path, monkeypatch):
    """生产挂账形态(2026-10-10):csv 是旧 _DATA 的投影、mtime 老、ptr 新
    → 代码演进 _DATA 后 needs_convert 恒 False、旧纪元永不重建;
    投影语义下 load() 重物化 + mtime 前进 → needs_convert 翻 True。"""
    s = InfraServicesSource(data_dir=tmp_path)
    csv_path = tmp_path / "infra_services.csv"
    monkeypatch.setattr(infra_mod, "_DATA", "8.8.8.8,dns,Old Projection\n")
    s.download()
    assert s.rebuild() == 1           # 活纪元建于旧 _DATA
    new_data = "8.8.8.8,dns,Google Public DNS\n203.0.113.9,dns,New Row\n"
    monkeypatch.setattr(infra_mod, "_DATA", new_data)   # 模拟新版代码
    assert not needs_convert(csv_path, s._mmdb_path)    # 死锁态:csv 老 ptr 新
    m0 = csv_path.stat().st_mtime_ns
    assert s.load() == 1              # 旧 epoch 照常 mmap(重建交给调度器)
    assert csv_path.read_text() == new_data             # 投影已追平真相
    assert csv_path.stat().st_mtime_ns > m0   # mtime bump = rebuild 入队信号
    assert needs_convert(csv_path, s._mmdb_path)   # → 一次 rebuild 在队


def test_projection_no_rewrite_when_content_matches(tmp_path):
    """同内容零写(数字零变化契约):内容一致时 load 不碰 csv——
    不写、不换 inode、mtime 不动,无 rebuild 循环。"""
    s = InfraServicesSource(data_dir=tmp_path)
    s.download()
    csv_path = tmp_path / "infra_services.csv"
    m0 = csv_path.stat().st_mtime_ns
    s.load()
    assert csv_path.read_text() == infra_mod._DATA
    assert csv_path.stat().st_mtime_ns == m0


def test_projection_repeat_load_idempotent_no_half_write(tmp_path, monkeypatch):
    """漂移态下连续两次 load 幂等:csv 恒 == _DATA(原子换入,无半写),
    第二次零写(mtime 冻结),无 .tmp 残留。"""
    s = InfraServicesSource(data_dir=tmp_path)
    s.download()
    csv_path = tmp_path / "infra_services.csv"
    monkeypatch.setattr(infra_mod, "_DATA", infra_mod._DATA + "203.0.113.9,dns,Test\n")
    s.load()
    first = csv_path.read_text()
    m1 = csv_path.stat().st_mtime_ns
    s.load()
    assert csv_path.read_text() == first == infra_mod._DATA
    assert csv_path.stat().st_mtime_ns == m1
    assert list(tmp_path.glob("*.tmp")) == []


def test_projection_converges_after_one_rebuild(tmp_path, monkeypatch):
    """全程收敛:_DATA 演进 → load 重物化(mtime bump → needs_convert
    True)→ rebuild 采新 csv → needs_convert False,再 load 零写。"""
    from ipdb._sources.infra_services import _DATA
    s = InfraServicesSource(data_dir=tmp_path)
    s.rebuild()                     # 旧 _DATA 建纪元
    assert s.query("203.0.113.9") == {}
    monkeypatch.setattr(infra_mod, "_DATA", _DATA + "203.0.113.9,dns,Test\n")
    s.load()
    csv_path = tmp_path / "infra_services.csv"
    assert csv_path.read_text() == infra_mod._DATA
    # 重建路径同样同步投影(未经 load 直入 rebuild 也不采到旧 csv)
    assert s.rebuild() == 32
    assert s.query("203.0.113.9")[0]["service"] == "dns"
    assert not needs_convert(csv_path, s._mmdb_path)   # ptr 已新 → 收敛
    m1 = csv_path.stat().st_mtime_ns
    s.load()                        # 收敛后零写,无循环
    assert csv_path.stat().st_mtime_ns == m1
    assert not needs_convert(csv_path, s._mmdb_path)
