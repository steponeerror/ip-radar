"""三个更新端点契约(spec API Contract)。

GET /api/version — 当前版本 + 最新版(惰性缓存);POST /api/update — token 校验
+ 409 + 触发即忘 202;GET /api/update/status — 三态状态机。
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main  # noqa: F401  (import 触发 app 组装)


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_version_shape(client):
    with patch.object(main._ipdb_version, "VERSION", "v1.1.0"), \
         patch.object(main._ipdb_version, "fetch_latest",
                      AsyncMock(return_value={"tag": "v1.2.0", "summary": "新特性", "url": "http://r"})):
        r = client.get("/api/version")
    assert r.status_code == 200
    d = r.json()
    assert d["current"] == "v1.1.0"
    assert d["latest"] == "v1.2.0"
    assert d["update_available"] is True
    assert d["summary"] == "新特性"
    assert d["self_update_enabled"] is False


def test_version_latest_null(client):
    with patch.object(main._ipdb_version, "fetch_latest", AsyncMock(return_value=None)):
        r = client.get("/api/version")
    assert r.json()["latest"] is None
    assert r.json()["update_available"] is False


def test_update_requires_token(client):
    import os
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("IP_RADAR_UPDATE_TOKEN", None)
        r = client.post("/api/update")
    assert r.status_code == 403


def test_update_rejects_wrong_token(client):
    import os
    with patch.dict(os.environ, {"IP_RADAR_UPDATE_TOKEN": "sekrit"}):
        r = client.post("/api/update", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 403


def test_update_non_ascii_token_rejects_not_500(client):
    # H1: 双 str compare_digest 遇非 ASCII 抛 TypeError→500;bytes 版须稳回 403
    # httpx 客户端拒绝非 ASCII str 头,但原始客户端(curl/netcat)可发任意字节,uvicorn 以 latin-1 解码可达端点
    import os
    with patch.dict(os.environ, {"IP_RADAR_UPDATE_TOKEN": "sekrit"}):
        r = client.post("/api/update", headers={"Authorization": b"Bearer \xf1\xe9"})
    assert r.status_code == 403


def test_update_conflict_when_updating(client):
    import os
    with patch.dict(os.environ, {"IP_RADAR_UPDATE_TOKEN": "sekrit"}), \
         patch.object(main._ipdb_update, "self_update_enabled", lambda: True), \
         patch.object(main._ipdb_update, "state", lambda: {"state": "updating"}):
        r = client.post("/api/update", headers={"Authorization": "Bearer sekrit"})
    assert r.status_code == 409


def test_update_accepted_fires_and_forgets(client):
    import os
    started = []

    def fake_spawn():
        started.append(True)

    with patch.dict(os.environ, {"IP_RADAR_UPDATE_TOKEN": "sekrit"}), \
         patch.object(main._ipdb_update, "self_update_enabled", lambda: True), \
         patch.object(main._ipdb_update, "state", lambda: {"state": "idle"}), \
         patch.object(main._ipdb_update, "mark_updating", lambda: None), \
         patch.object(main, "_spawn_update", fake_spawn):
        r = client.post("/api/update", headers={"Authorization": "Bearer sekrit"})
    assert r.status_code == 202
    assert started == [True]


def test_update_status_shape(client):
    with patch.object(main._ipdb_update, "state",
                      lambda: {"state": "failed", "error": "boom", "at": "T"}):
        r = client.get("/api/update/status")
    assert r.json() == {"state": "failed", "error": "boom", "at": "T"}


def test_version_refresh_param_forces_source(client):
    seen = {}

    async def fl(force=False):
        seen["force"] = force
        return {"tag": "v1.2.0", "summary": None, "url": "u"}

    with patch.object(main._ipdb_version, "fetch_latest", fl):
        client.get("/api/version?refresh=1")
    assert seen["force"] is True
