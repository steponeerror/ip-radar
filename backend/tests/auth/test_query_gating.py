# backend/tests/auth/test_query_gating.py — Task 6: 查询端点 api_key_dep 接线
"""四查询端点同规(Q1-B:GET lookup/stix 与 batch 同一依赖,无 GET 匿名分支):
同源(Origin/Referer 命中 Host/XFH/PUBLIC_ORIGIN)匿名放行,否则须合法
Bearer key。依赖顺序 api_key_dep → require_ready:401/403/503-admin 优先于
warming 503(与 Task 3 _ADMIN_DEPS 同原则)。

require_ready 需过 → client fixture 组合 tiny_db(conftest 最小 LMDB 库);
keyed 用例再叠 key_env(JWT secret ≥32B)。TestClient 默认无 Origin/Referer
= 跨源程序化请求 → 401,这正是被测语义。
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import main  # noqa: F401  (import 触发 app 组装)
from ipdb import _apikeys, _auth


@pytest.fixture()
def client(tiny_db):
    """匿名 TestClient(无 Origin/Referer)。tiny_db 打开 require_ready 门。"""
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _hermetic_gate(monkeypatch):
    """密闭门(同 test_stream_pool 先例):全量跑序里早期 lifespan 测试往
    单例 manager 塞真实重建任务,真 _coverage_building 会对本文件误报
    warming 503(时序 flake)。本文件测鉴权不测门。"""
    monkeypatch.setattr(main, "_coverage_building", lambda: False)


def _issue(name):
    """key_env 前提下签发一把 key:隔离 auth db 已由 key_env 建好。"""
    asyncio.run(_auth.init_auth_db())
    meta, token = asyncio.run(_apikeys.issue_key(name))
    return meta["sub"], token


def test_batch_no_origin_no_key_401(client):
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_batch_same_origin_passes(client):
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                    headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_batch_bearer_without_origin_passes(client, key_env):
    """Review Focus #1:桌面伴侣形态 —— 无 Origin 纯 Bearer 必须可用。"""
    _, token = _issue("no-origin")
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_batch_disabled_key_403(client, key_env):
    sub, token = _issue("then-disabled")
    asyncio.run(_apikeys.set_disabled(sub, True))
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_get_lookup_cross_origin_401(client):
    r = client.get("/api/lookup/1.1.1.1")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_get_lookup_bearer_passes(client, key_env):
    _, token = _issue("get-ok")
    r = client.get("/api/lookup/1.1.1.1",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_stix_same_rule_as_lookup(client):
    r = client.get("/api/lookup/1.1.1.1/stix")
    assert r.status_code == 401          # Q1-B: stix 不再豁免
    assert r.json()["error"]["code"] == "unauthorized"


def test_public_origin_env_override(client, monkeypatch):
    monkeypatch.setenv("IP_RADAR_PUBLIC_ORIGIN", "https://ipradar.example.com")
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                    headers={"Origin": "https://ipradar.example.com"})
    assert r.status_code == 200


def test_keys_disabled_with_auth_header_503(client, monkeypatch):
    """keys disabled + 带 Authorization → 503 admin_disabled(先于 warming,
    也先于 jwt.decode 摸缺失 secret)。tiny_db 下 require_ready 本可过,
    503 只可能来自鉴权层 —— 依赖顺序的独立证明。"""
    monkeypatch.delenv("IP_RADAR_API_JWT_SECRET", raising=False)
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                    headers={"Authorization": "Bearer anything"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "admin_disabled"
