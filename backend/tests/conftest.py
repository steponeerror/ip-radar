"""Shared test fixtures/helpers for the ipdb test suite."""
from pathlib import Path

import pytest


def build_lmdb(records, base):
    """测试构库:rebuild 后立即关闭 env,避免同进程双开。"""
    from ipdb._sources._lmdb import rebuild_lmdb
    envs = []
    rebuild_lmdb(records, base, envs.append)
    envs[0].close()


@pytest.fixture
def tiny_db(tmp_path, monkeypatch):
    """最小可用库: tmp 下建 ipinfo_lite LMDB, 打开查询门。
    CI 干净检出没有仓库根 data/, 不建库则 lookup/流式接口全 503
    (Database not loaded / 冷启动门)。进程内 monkeypatch 换 _sources;
    spawn 子进程靠 IP_RADAR_DATA_DIR 环境继承 (monkeypatch 过不了进程边界)。
    load_db 钉死后测试内两处双载不再双开 LMDB。"""
    from ipdb import _registry
    from ipdb._sources._lmdb import rebuild_lmdb
    envs = []
    rebuild_lmdb([
        ("8.8.8.0/24", {"country_code": "US", "_net": "8.8.8.0/24", "has_asn": False}),
        ("1.1.1.0/24", {"country_code": "AU", "_net": "1.1.1.0/24", "has_asn": False}),
    ], tmp_path / "ipinfo_lite.csv.lmdb", envs.append)
    envs[0].close()  # py-lmdb 同路径双开禁止, rebuild 句柄先关
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_registry, "_sources", _registry._discover_sources(tmp_path))
    _registry.load_db()
    monkeypatch.setattr(_registry, "load_db", lambda: None)


@pytest.fixture
def tiny_db_v6(tmp_path, monkeypatch):
    """tiny_db 的双族版:v4 8.8.8.0/24(US) + v6 2a00:1450:4001::/48(DE)。

    v6 段必须全球可路由——文档段(2001:db8::/32)is_global=False 会走
    reserved 短路,当不了正常命中 fixture(T10 先例)。同测试函数内模块级
    autouse _tiny_db 先跑且已把 _registry.load_db 钉成 no-op,故这里用
    `from ipdb import load_db`(包 import 期绑定,不受 _registry 上 pin 影响)
    重新加载;tmp_path 函数级共享,v4 base 的二次 rebuild 是新 epoch 覆写,
    1.1.1.0/24 不再可见(本 fixture 的测试只用 8.8.8.8)。"""
    from ipdb import _registry, load_db
    from ipdb._sources._lmdb import rebuild_lmdb
    envs = []
    rebuild_lmdb([
        ("8.8.8.0/24", {"country_code": "US", "_net": "8.8.8.0/24",
                        "has_asn": False, "asn": "N/A"}),
    ], tmp_path / "ipinfo_lite.csv.lmdb", envs.append)
    rebuild_lmdb([
        ("2a00:1450:4001::/48", {"country_code": "DE",
                                 "_net": "2a00:1450:4001::/48",
                                 "has_asn": False, "asn": "N/A"}),
    ], tmp_path / "ipinfo_lite.csv.v6.lmdb", envs.append, ip_version=6)
    for e in envs:
        e.close()  # py-lmdb 同路径双开禁止, rebuild 句柄先关
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_registry, "_sources", _registry._discover_sources(tmp_path))
    load_db()  # 真实引用(绕开 _tiny_db 的 no-op pin)
    monkeypatch.setattr(_registry, "load_db", lambda: None)
