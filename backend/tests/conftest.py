"""Shared test fixtures/helpers for the ipdb test suite."""
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# admin 认证 fixture 常量(Task 3):bootstrap_admin 的默认邮箱 + 测试密码。
ADMIN_EMAIL = "admin@ipradar.local"
ADMIN_PASSWORD = "s3cret-pass-123"

# API key JWT secret(Task 4):conftest fixture 与用例内伪造 token 共用同值。
KEY_JWT_SECRET = "x" * 48


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


# ── admin 认证 fixtures(顶层共享:tests/auth 之外的核心路由测试也用)──
# controller ruling:目录级 conftest 不可见 → 单一定义点放顶层。
@pytest.fixture()
def auth_env(tmp_path, monkeypatch):
    """隔离的 auth db + 已配置 admin 密码。只被 auth_client/client_as_admin
    依赖(惰性),不用 auth 的测试看不到任何 env 变化。"""
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_ADMIN_PASSWORD", ADMIN_PASSWORD)


@pytest.fixture()
def auth_client(auth_env):
    """未登录 TestClient。auth db 已 init+bootstrap(Task 2 模式:不进
    `with` — lifespan 重活不跑;https base_url 让 Secure cookie 可回发)。"""
    import main  # noqa: F401  (import 触发 app 组装;惰性 — 非 auth 测试不受影响)
    from ipdb import _auth
    asyncio.run(_auth.init_auth_db())
    asyncio.run(_auth.bootstrap_admin())
    return TestClient(main.app, base_url="https://testserver")


@pytest.fixture()
def client_as_admin(auth_client):
    """登录超管后的同一 client(管理端点 Task 3 起全部要求超管 cookie)。"""
    r = auth_client.post("/api/auth/jwt/login",
                         data={"username": ADMIN_EMAIL,
                               "password": ADMIN_PASSWORD})
    assert r.status_code == 204  # CookieTransport 契约:204 No Content
    return auth_client


# ── API key fixtures(Task 4):_apikeys 全链路;后续密钥管理端点任务复用 ──
@pytest.fixture()
def key_env(tmp_path, monkeypatch):
    """隔离 auth db + 已配置 JWT secret(≥32B)——issue/verify/dep 可用。"""
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_API_JWT_SECRET", KEY_JWT_SECRET)
