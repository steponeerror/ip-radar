"""公共 demo 模式中间件测试 — spec: docs/superpowers/specs/2026-08-23-public-demo-mode-design.md

三态:写/内部接口 404(当作不存在);查询读接口无 header 403;
STIX/OPTIONS/回环/version 豁免。env 需动态读(monkeypatch 可切换)。
"""
import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

HEADER = {"x-ipradar-client": "web"}


@contextmanager
def _client(env_value: str | None):
    """TestClient with ``_startup`` patched out (no cold-start downloads)."""
    import main
    with patch.object(main, "_startup"):
        if env_value is None:
            import os
            os.environ.pop("IP_RADAR_PUBLIC_DEMO", None)
        else:
            import os
            os.environ["IP_RADAR_PUBLIC_DEMO"] = env_value
        with TestClient(main.app) as c:
            yield c


@pytest.fixture(autouse=True)
def _restore_env():
    import os
    yield
    os.environ.pop("IP_RADAR_PUBLIC_DEMO", None)


def test_demo_hidden_endpoints_404():
    with _client("1") as c:
        cases = [
            ("post", "/api/update-db"),
            ("post", "/api/update-db/cancel"),
            ("post", "/api/update-db/pause"),
            ("post", "/api/update-db/resume"),
            ("get", "/api/sources"),
            ("get", "/api/scheduler/status"),
            ("get", "/api/tasks"),
            ("get", "/api/events"),
            ("get", "/api/update/status"),
            ("post", "/api/update"),
            ("get", "/api/perf/layout"),
        ]
        for method, path in cases:
            res = getattr(c, method)(path)
            assert res.status_code == 404, f"{method} {path} -> {res.status_code}"


def test_demo_read_endpoints_need_header():
    with _client("1") as c:
        assert c.get("/api/db-status").status_code == 403
        res = c.get("/api/db-status", headers=HEADER)
        assert res.status_code == 200


def test_demo_stix_exempt_from_header():
    # window.open 发不了自定义 header;无库时非 403 即证明未拦
    with _client("1") as c:
        res = c.get("/api/lookup/1.1.1.1/stix")
        assert res.status_code != 403


def test_demo_options_passthrough():
    # CORS 预检不带业务 header,必须直通(中间件在 CORS 外层)
    with _client("1") as c:
        res = c.options(
            "/api/db-status",
            headers={"Origin": "http://localhost:5173",
                     "Access-Control-Request-Method": "GET"},
        )
        assert res.status_code != 403


def test_demo_loopback_exempt():
    # compose healthcheck 无 header 直击 db-status;httpx.ASGITransport
    # 默认 client=("127.0.0.1", 123),恰好模拟回环来源
    import main
    with _client("1"):
        async def run():
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://t"
            ) as ac:
                return await ac.get("/api/db-status")
        res = asyncio.run(run())
    assert res.status_code != 403


def test_normal_mode_unaffected():
    with _client(None) as c:
        assert c.get("/api/db-status").status_code == 200  # 无 header 也放行
        assert c.get("/api/perf/layout").status_code == 200  # 隐藏组照常可达


def test_version_reports_demo_flag():
    import main
    for env, expected in [("1", True), (None, False)]:
        with _client(env) as c:
            monkey_target = main._ipdb_version
            with patch.object(
                monkey_target, "fetch_latest", AsyncMock(return_value=None)
            ):
                res = c.get("/api/version")
            assert res.status_code == 200
            assert res.json()["public_demo"] is expected
