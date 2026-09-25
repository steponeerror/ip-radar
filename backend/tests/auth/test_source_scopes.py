# backend/tests/auth/test_source_scopes.py — Task 1: _apikeys 数据层
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
            "INSERT INTO api_key_meta (sub, name, disabled)"
            " VALUES ('legacy0000000000', 'legacy', 0)")
    await _apikeys.migrate_sources_column()
    meta = await _apikeys.list_keys()
    assert meta[0]["sub"] == "legacy0000000000"
    assert meta[0]["sources"] is None and meta[0]["web"] is False

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
