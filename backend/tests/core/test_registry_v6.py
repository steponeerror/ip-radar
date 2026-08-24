"""registry.lookup v6:版本感知解析 + reserved 语义(纯 stdlib is_global,spec §4.2)。

先例:tests/lookup/test_lookup_reserved.py(v4 probe 短路模式)与
tests/conftest.py tiny_db(双族 env fixture house pattern)。
"""
import ipaddress

import pytest

import ipdb._registry as reg
from ipdb._types import LookupResult, SourceHealth


class _ProbeSource:
    """reserved IP 绝不能到达 source.query(v4 先例同款)。health.loaded=True
    使 _db_loaded() 通过,无需真实数据目录。"""
    name = "probe"
    fields = ("is_malicious",)
    reliability = 0.5
    authoritative_for = []

    def query(self, ip):
        raise AssertionError(
            f"source.query must not be called for reserved IP {ip}")

    def health(self):
        return SourceHealth(name="probe", loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


@pytest.fixture
def v6_db(tmp_path, monkeypatch):
    """tiny_db 同式:ipinfo_lite 双族 env(v4 8.8.8.0/24 US;v6 两段——
    2a00:1450:4001::/48 全球可路由 DE 供正常命中,2001:db8::/32 文档段
    (is_global=False)供 reserved 优先于数据命中的证明),换 _sources 后 load_db()。"""
    from ipdb import _registry
    from ipdb._sources._lmdb import rebuild_lmdb
    envs = []
    rebuild_lmdb([("8.8.8.0/24", {"country_code": "US", "_net": "8.8.8.0/24",
                                  "has_asn": False, "asn": "N/A"})],
                 tmp_path / "ipinfo_lite.csv.lmdb", envs.append)
    rebuild_lmdb([("2a00:1450:4001::/48", {"country_code": "DE",
                                          "_net": "2a00:1450:4001::/48",
                                          "has_asn": False, "asn": "N/A"}),
                  ("2001:db8::/32", {"country_code": "XX", "_net": "2001:db8::/32",
                                     "has_asn": False, "asn": "N/A"})],
                 tmp_path / "ipinfo_lite.csv.v6.lmdb", envs.append, ip_version=6)
    for e in envs:
        e.close()
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_registry, "_sources", _registry._discover_sources(tmp_path))
    _registry.load_db()
    monkeypatch.setattr(_registry, "load_db", lambda: None)


def test_v6_normal_hits_v6_env(v6_db):
    """正常 v6(全球可路由段):走完整查询路径,country 从 v6 env 合并
    (FactualVoting 直投票值)。"""
    r = reg.lookup("2a00:1450:4001::42")
    assert isinstance(r, LookupResult)
    assert r.error is None
    assert r.is_reserved is False
    assert r.country.value == "DE"


def test_v6_miss_returns_clean(v6_db):
    """无证据 v6:clean 路径,threat_summary 融合裁决 benign。"""
    r = reg.lookup("2600:dead:beef::1")
    assert r.error is None
    assert r.is_reserved is False
    assert r.country.value == "N/A"
    assert r.threat_summary()["verdict"] == "benign"


def test_v4_path_unchanged(v6_db):
    """回归钉:v4 查询行为不变(同一 fixture 内)。"""
    r = reg.lookup("8.8.8.1")
    assert r.error is None
    assert r.country.value == "US"


@pytest.mark.parametrize("bad", ["::1", "fc00::1", "fe80::1", "2001:db8::1",
                                 "2002:c000:204::1", "ff02::1"])
def test_v6_reserved_short_circuits(bad, monkeypatch):
    """v6 bogon 纯 stdlib:is_global=False 或 multicast → reserved,源不触达。
    2001:db8::1(文档段)与 2002:c000:204::1(6to4)是 spec A4 钉死的 quirk。"""
    monkeypatch.setattr(reg, "_sources", [_ProbeSource()])
    r = reg.lookup(bad)
    assert r.is_reserved is True
    assert r.error is None
    assert r.classifications == {}
    assert r.to_dict()["is_reserved"] is True


def test_v6_reserved_takes_priority_over_data_hit(v6_db):
    """reserved 判定优先于数据命中:2001:db8::1 落在 fixture 的文档段 /32 内
    (env 里有数据),仍必须 short-circuit(N/A 而非 XX)。"""
    r = reg.lookup("2001:db8::1")
    assert r.is_reserved is True
    assert r.country.value == "N/A"


def test_v6_quirk_v4_mapped_goes_normal_path(v6_db):
    """spec A4 quirk:::ffff:8.8.8.8 is_global=True → 当公网 v6 走正常查询
    (不翻译成内嵌 v4),各源 miss → clean;绝不能是 reserved。"""
    r = reg.lookup("::ffff:8.8.8.8")
    assert ipaddress.IPv6Address("::ffff:8.8.8.8").is_global is True
    assert r.is_reserved is False
    assert r.error is None
    assert r.threat_summary()["verdict"] == "benign"


def test_v6_quirk_6to4_is_reserved():
    """spec A4 quirk:6to4(2002::/16)is_global=False → reserved。stdlib 钉死。"""
    assert ipaddress.IPv6Address("2002:c000:204::1").is_global is False


def test_v6_invalid_format_is_error(monkeypatch):
    """畸形 v6 串走 error 分支(与 v4 同构),非 crash。"""
    monkeypatch.setattr(reg, "_sources", [_ProbeSource()])
    r = reg.lookup("2001:db8::zz")
    assert r.error == "invalid IP format"
    assert r.is_reserved is False


def test_needs_rebuild_triggers_on_missing_v6_ptr(tmp_path):
    """Q3:v6 ptr 缺失 ⇒ 需要重建(即使 v4 ptr 新鲜)。"""
    import os
    import shutil

    from ipdb._source_base import Source
    from ipdb._evidence import Evidence

    class _S(Source):
        name = "q3"; fields = ("country_code",); filename = "q.csv"
        single_evidence = True
        def harvest(self):
            yield "10.0.0.0/24", Evidence(country_code="XX")

    src = _S(tmp_path)
    (tmp_path / "q.csv").write_text("x\n")
    src.rebuild()
    # 删 v6 sidecar 模拟旧目录升级
    for p in tmp_path.glob("q.csv.v6.lmdb*"):
        (shutil.rmtree if p.is_dir() else os.unlink)(p)
    # 模拟重启:关句柄 + load(v6 ptr 缺失 → _reader6=None)。
    # 不关则 py-lmdb 同进程双开同路径 env(epoch 回卷到 1)拒绝;
    # 生产升级流(重启→load→触发)无此双开。brief 测试压缩两步为一步的缺陷。
    src._reader.close()
    src._reader = None
    src.load()
    assert src._reader6 is None                 # 重启后无 v6 侧
    assert reg._needs_rebuild_of(src) is True
    src.rebuild()                                   # 重建后 v6 ptr 回来
    assert reg._needs_rebuild_of(src) is False


def test_sources_needing_rebuild_plural_ignites_on_missing_v6_ptr(
        tmp_path, monkeypatch):
    """final-review I1:复数版必须同样纳入 v6 ptr 检查(温启动升级点燃)。

    v4 ptr 新鲜 + v6 sidecar 缺失(旧目录原地升级)⇒ sources_needing_rebuild()
    必须返回该源——否则 v6 只能等 scheduler 首扫(默认 1800s 后)或
    IPRADAR_AUTO_REFRESH=0 时永不点燃(spec §8 当天点亮)。"""
    import os
    import shutil

    from ipdb._source_base import Source
    from ipdb._evidence import Evidence

    class _S(Source):
        name = "q3p"; fields = ("country_code",); filename = "q3p.csv"
        single_evidence = True
        def harvest(self):
            yield "10.0.0.0/24", Evidence(country_code="XX")

    src = _S(tmp_path)
    (tmp_path / "q3p.csv").write_text("x\n")
    src.rebuild()
    for p in tmp_path.glob("q3p.csv.v6.lmdb*"):
        (shutil.rmtree if p.is_dir() else os.unlink)(p)
    # 模拟重启(同 :146 注:避免同进程双开)
    src._reader.close()
    src._reader = None
    src.load()
    monkeypatch.setattr(reg, "_sources", [src])
    assert reg.sources_needing_rebuild() == ["q3p"]   # I1:复数版点燃
    src.rebuild()
    assert reg.sources_needing_rebuild() == []        # 重建后安静
