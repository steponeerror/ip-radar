# backend/tests/auth/test_apikeys_core.py — Task 4: JWT-as-API-key 核心
"""issue/verify/元数据 CRUD + _same_origin + api_key_dep(Q1-B 修订:无 GET
匿名分支)。key_env(顶层 conftest 共享 fixture)提供隔离 auth db + 48B secret;
本文件以 autouse 桥接 brief 用例的隐式环境依赖。"""
import time

import jwt as pyjwt
import pytest
from starlette.requests import Request

SECRET = "x" * 48


@pytest.fixture(autouse=True)
def _env(key_env):
    """brief 用例按 autouse 环境书写;conftest 的 key_env 保持选入式共享。"""


def make_request(headers: dict) -> Request:
    """手工 scope 构造 Request:任意 header 组合,不受 TestClient 注入限制。"""
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode())
                    for k, v in headers.items()],
    }
    return Request(scope)


# ── brief Step 1 的 5 个用例(原样,补 anyio 标记)──

@pytest.mark.anyio
async def test_issue_and_verify_roundtrip():
    from ipdb import _apikeys, _auth
    await _auth.init_auth_db()
    meta, token = await _apikeys.issue_key("测试key")
    assert meta["name"] == "测试key" and token.count(".") == 2
    got = await _apikeys.verify_key(token)
    assert got["sub"] == meta["sub"]
    assert got["name"] == "测试key"


@pytest.mark.anyio
async def test_verify_garbage_token_401():
    from ipdb import _apikeys, _auth
    from ipdb._errors import ApiError
    await _auth.init_auth_db()
    for bad in ["garbage", "Bearer abc", "a.b.c"]:
        with pytest.raises(ApiError) as ei:
            await _apikeys.verify_key(bad)
        assert ei.value.status == 401


@pytest.mark.anyio
async def test_expired_key_401():
    from ipdb import _apikeys, _auth
    from ipdb._errors import ApiError
    await _auth.init_auth_db()
    _, token = await _apikeys.issue_key("e", expires_days=1)
    past = pyjwt.encode(  # 手造过期 token,同 secret
        {"sub": "deadbeef", "kname": "e", "iat": int(time.time()) - 999,
         "exp": int(time.time()) - 1}, SECRET, algorithm="HS256")
    with pytest.raises(ApiError) as ei:
        await _apikeys.verify_key(past)
    assert ei.value.status == 401


@pytest.mark.anyio
async def test_disabled_key_403_and_deleted_401():
    from ipdb import _apikeys, _auth
    from ipdb._errors import ApiError
    await _auth.init_auth_db()
    meta, token = await _apikeys.issue_key("d")
    await _apikeys.set_disabled(meta["sub"], True)
    with pytest.raises(ApiError) as ei:
        await _apikeys.verify_key(token)
    assert ei.value.status == 403
    await _apikeys.delete_key(meta["sub"])
    with pytest.raises(ApiError) as ei2:
        await _apikeys.verify_key(token)
    assert ei2.value.status == 401


@pytest.mark.anyio
async def test_wrong_secret_401():
    from ipdb import _apikeys, _auth
    from ipdb._errors import ApiError
    await _auth.init_auth_db()
    forged = pyjwt.encode({"sub": "abc", "exp": int(time.time()) + 100},
                          "attacker-secret" * 4, algorithm="HS256")
    with pytest.raises(ApiError):
        await _apikeys.verify_key(forged)


# ── keys_enabled 失效路径(spec §7.1:issue/verify 503 admin_disabled)──

@pytest.mark.anyio
async def test_issue_key_disabled_secret_503(monkeypatch):
    from ipdb import _apikeys
    from ipdb._errors import ApiError
    monkeypatch.delenv("IP_RADAR_API_JWT_SECRET", raising=False)
    assert not _apikeys.keys_enabled()
    with pytest.raises(ApiError) as ei:
        await _apikeys.issue_key("nope")
    assert ei.value.status == 503
    monkeypatch.setenv("IP_RADAR_API_JWT_SECRET", "x" * 31)  # <32B 同样失效
    assert not _apikeys.keys_enabled()
    with pytest.raises(ApiError) as ei2:
        await _apikeys.issue_key("nope")
    assert ei2.value.status == 503


# ── _touch_last_used 节流落盘(spec §7.3)──

@pytest.mark.anyio
async def test_verify_touches_last_used():
    from ipdb import _apikeys, _auth
    await _auth.init_auth_db()
    meta, token = await _apikeys.issue_key("t")
    _apikeys._last_flush = 0.0  # 强制下次 verify 触发批量 flush
    await _apikeys.verify_key(token)
    sm = _auth._session_maker()
    async with sm() as s:
        row = await s.get(_apikeys.ApiKeyMeta, meta["sub"])
    assert row.last_used_at is not None
    await _apikeys.verify_key(token)  # 节流窗口内:仅记缓存,不报错


# ── _same_origin(controller ruling 3:Host/XFH scheme-insensitive,
#    IP_RADAR_PUBLIC_ORIGIN scheme-sensitive,无头 Referer 前缀,皆无→False)──

def test_same_origin_host_match():
    from ipdb._apikeys import _same_origin
    assert _same_origin(make_request(
        {"origin": "https://example.com", "host": "example.com"}))
    # TLS 终结代理:Origin 的 scheme 与 Host 无关(Host 本就不带 scheme)
    assert _same_origin(make_request(
        {"origin": "http://example.com", "host": "example.com"}))


def test_same_origin_mismatch_false():
    from ipdb._apikeys import _same_origin
    assert not _same_origin(make_request(
        {"origin": "https://evil.example", "host": "example.com"}))
    assert not _same_origin(make_request({"origin": "null", "host": "x"}))


def test_same_origin_referer_prefix():
    from ipdb._apikeys import _same_origin
    assert _same_origin(make_request(
        {"referer": "https://example.com/some/page", "host": "example.com"}))
    assert not _same_origin(make_request(
        {"referer": "https://evil.example/example.com/x", "host": "example.com"}))


def test_same_origin_x_forwarded_host():
    from ipdb._apikeys import _same_origin
    assert _same_origin(make_request(
        {"origin": "https://pub.example.com", "host": "internal:8000",
         "x-forwarded-host": "pub.example.com"}))
    # 多值取首个
    assert _same_origin(make_request(
        {"origin": "https://a.com", "host": "internal",
         "x-forwarded-host": "a.com, b.com"}))


def test_same_origin_public_origin_exact(monkeypatch):
    from ipdb._apikeys import _same_origin
    monkeypatch.setenv("IP_RADAR_PUBLIC_ORIGIN", "https://radar.example.com")
    assert _same_origin(make_request(
        {"origin": "https://radar.example.com", "host": "whatever-else"}))
    # 对 PUBLIC_ORIGIN 比较 scheme 也必须一致
    assert not _same_origin(make_request(
        {"origin": "http://radar.example.com", "host": "whatever-else"}))


def test_same_origin_no_headers_false():
    from ipdb._apikeys import _same_origin
    assert not _same_origin(make_request({}))


# ── api_key_dep(Q1-B:无 GET 匿名分支;Bearer→verify,无 Bearer→同源/401)──

@pytest.mark.anyio
async def test_api_key_dep_disabled_503_before_decode(monkeypatch):
    # ruling 2:secret 失效时任何 Authorization 头先 503,绝不带着缺失
    # secret 走到 jwt.decode(KeyError → 500)
    from ipdb import _apikeys
    from ipdb._errors import ApiError
    monkeypatch.delenv("IP_RADAR_API_JWT_SECRET", raising=False)
    req = make_request({"authorization": "Bearer garbage", "host": "h.test"})
    with pytest.raises(ApiError) as ei:
        await _apikeys.api_key_dep(req)
    assert ei.value.status == 503


@pytest.mark.anyio
async def test_api_key_dep_same_origin_passes():
    from ipdb import _apikeys
    req = make_request({"origin": "https://h.test", "host": "h.test"})
    assert await _apikeys.api_key_dep(req) is None
    assert getattr(req.state, "api_key_sub", None) is None  # 未注入 sub


@pytest.mark.anyio
async def test_api_key_dep_no_auth_no_origin_401():
    from ipdb import _apikeys
    from ipdb._errors import ApiError
    with pytest.raises(ApiError) as ei:
        await _apikeys.api_key_dep(make_request({}))
    assert ei.value.status == 401


@pytest.mark.anyio
async def test_api_key_dep_bearer_sets_state():
    from ipdb import _apikeys, _auth
    await _auth.init_auth_db()
    meta, token = await _apikeys.issue_key("dep")
    req = make_request({"authorization": f"Bearer {token}", "host": "h.test"})
    assert await _apikeys.api_key_dep(req) is None
    assert req.state.api_key_sub == meta["sub"]
