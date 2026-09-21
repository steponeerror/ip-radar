# backend/tests/auth/test_auth_db.py — Task 1: auth data layer (models/engine/bootstrap)
# anyio 标记沿用仓库现有 async 测试模式(test_version.py),不引 pytest-asyncio。
import pytest


@pytest.mark.anyio
async def test_bootstrap_creates_superuser_once(tmp_path, monkeypatch):
    db = tmp_path / "auth.db"
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(db))
    monkeypatch.setenv("IP_RADAR_ADMIN_PASSWORD", "s3cret-pass-123")
    from ipdb import _auth
    await _auth.init_auth_db()
    await _auth.bootstrap_admin()
    u1 = await _auth.get_superuser_count()
    await _auth.bootstrap_admin()          # 幂等:不重复建
    u2 = await _auth.get_superuser_count()
    assert u1 == 1 == u2
    assert db.exists()


@pytest.mark.anyio
async def test_no_env_no_superuser(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("IP_RADAR_ADMIN_PASSWORD", raising=False)
    from ipdb import _auth
    await _auth.init_auth_db()
    await _auth.bootstrap_admin()
    assert await _auth.get_superuser_count() == 0
    assert not _auth.admin_configured()
