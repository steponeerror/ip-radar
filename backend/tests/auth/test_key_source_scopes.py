# backend/tests/auth/test_key_source_scopes.py — Task 1: _apikeys 数据层
"""api_key_meta.sources 列 + 幂等迁移 + demo web 种子行 + set_sources /
issue_key(sources=) 往返(brief Step 1 用例原样)。"""
import pytest

@pytest.mark.anyio
async def test_migrate_adds_column_to_legacy_db(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_API_JWT_SECRET", "x" * 40)
    from ipdb import _apikeys, _auth
    async with _auth._engine().begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE api_key_meta (sub VARCHAR(16) PRIMARY KEY,"
            " name VARCHAR(200) NOT NULL, created_at DATETIME,"
            " last_used_at DATETIME, disabled BOOLEAN)")
        await conn.exec_driver_sql(
            "INSERT INTO api_key_meta (sub, name, created_at, disabled)"
            " VALUES ('legacy0000000000', 'legacy', '2025-01-01 12:00:00', 0)")
    await _apikeys.migrate_sources_column()
    meta = await _apikeys.list_keys()
    assert meta[0]["sub"] == "legacy0000000000"
    assert meta[0]["sources"] is None and meta[0]["web"] is False
    assert meta[0]["created_at"] is not None   # 真实时间戳迁移后完好


def test_legacy_schema_route_roundtrip(client_as_admin, key_env):
    """spec §9 迁移锚点(路由级):legacy 表(无 sources 列)→ 迁移 →
    GET 可见 → PATCH sources 成功 → 读回反映;created_at IS NULL 的
    legacy 行 → GET 200 且 created_at: null(钉住 Optional 契约)。"""
    import asyncio
    from ipdb import _apikeys, _auth

    async def _seed_legacy_rows() -> None:
        async with _auth._engine().begin() as conn:
            await conn.exec_driver_sql("DROP TABLE IF EXISTS api_key_meta")
            await conn.exec_driver_sql(
                "CREATE TABLE api_key_meta (sub VARCHAR(16) PRIMARY KEY,"
                " name VARCHAR(200) NOT NULL, created_at DATETIME,"
                " last_used_at DATETIME, disabled BOOLEAN)")
            await conn.exec_driver_sql(
                "INSERT INTO api_key_meta (sub, name, created_at, disabled)"
                " VALUES ('legacy0000000000', 'legacy', '2025-01-01 12:00:00', 0)")
            await conn.exec_driver_sql(
                "INSERT INTO api_key_meta (sub, name, created_at, disabled)"
                " VALUES ('nullts000000000', 'null-ts', NULL, 0)")

    asyncio.run(_seed_legacy_rows())
    asyncio.run(_apikeys.migrate_sources_column())

    lst = client_as_admin.get("/api/admin/keys")
    assert lst.status_code == 200
    rows = {k["sub"]: k for k in lst.json()}
    assert set(rows) == {"legacy0000000000", "nullts000000000"}
    assert rows["legacy0000000000"]["created_at"].startswith("2025-01-01")
    assert rows["nullts000000000"]["created_at"] is None   # 钉 Optional

    r = client_as_admin.patch("/api/admin/keys/legacy0000000000",
                              json={"sources": ["dbip_city"]})
    assert r.status_code == 200 and r.json()["sources"] == ["dbip_city"]
    rows2 = {k["sub"]: k for k in client_as_admin.get("/api/admin/keys").json()}
    assert rows2["legacy0000000000"]["sources"] == ["dbip_city"]   # 读回反映


@pytest.mark.anyio
async def test_migrate_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_API_JWT_SECRET", "x" * 40)
    from ipdb import _apikeys, _auth
    async with _auth._engine().begin() as conn:
        await conn.run_sync(_auth.Base.metadata.create_all)
    await _apikeys.migrate_sources_column()
    await _apikeys.migrate_sources_column()   # 第二次不炸

@pytest.mark.anyio
async def test_ensure_demo_row_idempotent_and_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_API_JWT_SECRET", "x" * 40)
    from ipdb import _apikeys, _auth
    async with _auth._engine().begin() as conn:
        await conn.run_sync(_auth.Base.metadata.create_all)
    await _apikeys.ensure_demo_row()
    await _apikeys.ensure_demo_row()
    rows = [k for k in await _apikeys.list_keys() if k["web"]]
    assert len(rows) == 1 and rows[0]["sub"] == _apikeys.DEMO_SUB
    assert rows[0]["sources"] is None

@pytest.mark.anyio
async def test_ensure_demo_row_no_secret_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("IP_RADAR_API_JWT_SECRET", raising=False)
    from ipdb import _apikeys, _auth
    async with _auth._engine().begin() as conn:
        await conn.run_sync(_auth.Base.metadata.create_all)
    await _apikeys.ensure_demo_row()
    assert await _apikeys.list_keys() == []

@pytest.mark.anyio
async def test_issue_key_with_sources_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("IP_RADAR_API_JWT_SECRET", "x" * 40)
    from ipdb import _apikeys, _auth
    async with _auth._engine().begin() as conn:
        await conn.run_sync(_auth.Base.metadata.create_all)
    _, token = await _apikeys.issue_key("t", sources=["dbip", "dshield"])
    info = await _apikeys.verify_key(token)
    assert info["sources"] == ["dbip", "dshield"]
    await _apikeys.set_sources(info["sub"], None)
    assert (await _apikeys.verify_key(token))["sources"] is None
