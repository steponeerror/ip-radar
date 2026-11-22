"""_update 状态机 + 启动对账(spec F2/F5)。

状态文件路径经 _paths.update_state_path 惰性解析(#406 折并):
monkeypatch env 即换路径,不再 patch 模块属性。
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ipdb import _update


def _write_state(tmp_path, payload):
    (tmp_path / "update_state.json").write_text(json.dumps(payload))


def test_reconcile_version_changed_to_idle(tmp_path, monkeypatch):
    # 旧容器死于 updating;新容器版本已变 → 上次成功
    _write_state(tmp_path, {"state": "updating", "from_version": "v1.0.0",
                            "at": datetime.now(timezone.utc).isoformat()})
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    with patch.object(_update, "_version_now", lambda: "v1.2.0"):
        _update.reconcile_on_startup()
    assert _update.state()["state"] == "idle"


def test_reconcile_slow_build_version_changed_beats_stale(tmp_path, monkeypatch):
    # OL-2 顺序钉:慢机构建(>15min stale 窗)但版本已前进 = 成功更新,
    # 不得先落 stale 判定被误标 failed(状态与事实相反)
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    _write_state(tmp_path, {"state": "updating", "from_version": "v1.0.0", "at": old})
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    with patch.object(_update, "_version_now", lambda: "v1.2.0"):
        _update.reconcile_on_startup()
    assert _update.state()["state"] == "idle"


def test_reconcile_version_same_to_failed(tmp_path, monkeypatch):
    _write_state(tmp_path, {"state": "updating", "from_version": "v1.2.0",
                            "at": datetime.now(timezone.utc).isoformat()})
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    with patch.object(_update, "_version_now", lambda: "v1.2.0"):
        _update.reconcile_on_startup()
    assert _update.state()["state"] == "failed"


def test_reconcile_stale_updating_expires(tmp_path, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    _write_state(tmp_path, {"state": "updating", "from_version": "v1.2.0", "at": old})
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    with patch.object(_update, "_version_now", lambda: "v1.2.0"):
        _update.reconcile_on_startup()
    s = _update.state()
    assert s["state"] == "failed"
    assert "超时" in s["error"]


def test_reconcile_clean_disk_stays_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    _update.reconcile_on_startup()
    assert _update.state()["state"] == "idle"


def test_mark_failed_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    _update.mark_updating()
    _update.mark_failed("git pull: not fast-forward")
    s = _update.state()
    assert s["state"] == "failed"
    assert "fast-forward" in s["error"]
    assert json.loads((tmp_path / "update_state.json").read_text())["state"] == "failed"


def test_reset_from_failed(tmp_path, monkeypatch):
    # 重试路径:failed → 新 POST 直接 mark_updating 覆盖
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "update_state.json"))
    _update.mark_failed("boom")
    _update.mark_updating()
    assert _update.state()["state"] == "updating"
