# backend/tests/auth/test_login.py — Task 2: fastapi-users 接线 + 登录路由 + fail-closed
"""POST /api/auth/jwt/login|logout、GET /api/users/me 契约 + admin 未配置 fail-closed。

- TestClient 不进 `with`:lifespan(重 load_db/调度器)不跑(仓库现有模式,
  见 tests/core/test_api_update.py);auth db 由 fixture 手动 init/bootstrap。
- cookie 生产默认 Secure;TestClient 用 https base_url,cookie jar 才会按
  secure 策略回发(等价于生产 TLS 下的浏览器行为)。
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import main  # noqa: F401  (import 触发 app 组装)


@pytest.fixture()
def auth_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_ADMIN_PASSWORD", "s3cret-pass-123")


@pytest.fixture()
def client(auth_env):
    from ipdb import _auth
    asyncio.run(_auth.init_auth_db())
    asyncio.run(_auth.bootstrap_admin())
    return TestClient(main.app, base_url="https://testserver")


def test_login_logout_me(client):
    r = client.post("/api/auth/jwt/login",
                    data={"username": "admin@ipradar.local",
                          "password": "s3cret-pass-123"})
    assert r.status_code == 204  # CookieTransport 契约:204 No Content
    assert "ipradar_admin" in r.cookies
    me = client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@ipradar.local"
    out = client.post("/api/auth/jwt/logout")
    assert out.status_code == 204
    assert client.get("/api/users/me").status_code == 401


def test_login_wrong_password_envelope(client):
    r = client.post("/api/auth/jwt/login",
                    data={"username": "admin@ipradar.local", "password": "nope"})
    assert r.status_code == 400
    assert r.json()["error"]["code"]  # 信封;具体码以实现为准


def test_admin_endpoints_503_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth2.db"))
    monkeypatch.delenv("IP_RADAR_ADMIN_PASSWORD", raising=False)
    from ipdb import _auth
    asyncio.run(_auth.init_auth_db())
    asyncio.run(_auth.bootstrap_admin())
    assert not _auth.admin_configured()
    c = TestClient(main.app)
    # Task 2 拥有的路由:/api/users/me 的 router 级 require_admin_configured
    # 先于 current_user 依赖 → 503 优先于 401(PATCH /api/sources 的 admin 门
    # 是 Task 3 的事,controller ruling 5 授权改打本任务路由)
    me = c.get("/api/users/me")
    assert me.status_code == 503
    assert me.json()["error"]["code"] == "admin_disabled"
    login = c.post("/api/auth/jwt/login",
                   data={"username": "a@b.c", "password": "x"})
    assert login.status_code == 503  # fail-closed:登录路由同样被门挡住
