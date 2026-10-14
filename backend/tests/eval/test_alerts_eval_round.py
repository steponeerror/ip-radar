# backend/tests/eval/test_alerts_eval_round.py — Task 14:S6 月轮心跳告警条件
"""evaluate(eval_heartbeat=...) 位等价红线 + eval_round 条件状态机。

时基独立(S6/裁决 A):告警只认生产侧心跳文件 mtime(eval_heartbeat_age_h),
不信月轮管线自报。路径 None = 不检查(新部署防误报),既有行为逐位不变
(位等价:两参调用与显式 None 同快照同库同输出)。阈值 35d;重发抑制
循既有 (source, condition) 24h 机制,source="monthly-eval"。
"""
import os
import sqlite3
from contextlib import closing

import pytest

T0 = 1_700_000_000.0
H = 3600.0


@pytest.fixture(autouse=True)
def _no_env_heartbeat(monkeypatch):
    """钉死 env:本文件只经显式参数启用心跳检查,ambient env 不得串台。"""
    monkeypatch.delenv("IP_RADAR_EVAL_HEARTBEAT", raising=False)


@pytest.fixture()
def alerts_db(tmp_path, monkeypatch):
    p = tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(p))
    return p


def _hb(tmp_path, age_h, now=T0):
    """造心跳文件并回拨 mtime 至 now-age_h(告警时基只看 mtime)。"""
    p = tmp_path / "eval-heartbeat"
    p.write_text("x")
    os.utime(p, (now - age_h * H, now - age_h * H))
    return p


def _state(db):
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute(
            "SELECT source, condition, active_since, last_notified"
            " FROM alert_state ORDER BY source, condition").fetchall()


def _snap(name, stale_days=1, age=1.0):
    return {"name": name, "stale_days": stale_days, "content_age_h": age,
            "fail_count": 0, "reader_error": False}


def test_heartbeat_36d_fires_line(alerts_db, tmp_path):
    from ipdb import _alerts
    hb = _hb(tmp_path, age_h=36 * 24)
    msg = _alerts.evaluate([], now=T0, eval_heartbeat=hb)
    assert msg is not None
    assert msg["title"] == "ipradar: 月轮心跳异常"
    assert "月轮过期" in msg["body"]
    assert "阈值 35.0d" in msg["body"]
    assert _state(alerts_db) == [("monthly-eval", "eval_round", T0, T0)]


def test_heartbeat_34d_silent(alerts_db, tmp_path):
    from ipdb import _alerts
    hb = _hb(tmp_path, age_h=34 * 24)
    assert _alerts.evaluate([], now=T0, eval_heartbeat=hb) is None
    assert _state(alerts_db) == []


def test_none_path_bit_identical(tmp_path, monkeypatch):
    """位等价红线:两参调用 vs 显式 None —— 即使心跳文件在场且过期。"""
    from ipdb import _alerts
    _hb(tmp_path, age_h=36 * 24)
    snaps = [_snap("stalesrc", stale_days=1, age=72.0), _snap("fresh", age=1.0)]
    db1, db2 = tmp_path / "a.db", tmp_path / "b.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(db1))
    msg_a = _alerts.evaluate(snaps, now=T0)
    state_a = _state(db1)
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(db2))
    msg_b = _alerts.evaluate(snaps, now=T0, eval_heartbeat=None)
    state_b = _state(db2)
    assert msg_a is not None          # 快照确有异常,消息非空才谈得上逐位同
    assert msg_a == msg_b
    assert state_a == state_b
    assert all(cond != "eval_round" for _, cond, _, _ in state_b)


def test_missing_file_alerts(alerts_db, tmp_path):
    from ipdb import _alerts
    msg = _alerts.evaluate(
        [], now=T0, eval_heartbeat=tmp_path / "nope-eval-heartbeat")
    assert msg is not None
    assert "月轮心跳缺失" in msg["body"]


def test_renotify_suppressed_within_24h(alerts_db, tmp_path):
    from ipdb import _alerts
    hb = _hb(tmp_path, age_h=36 * 24)
    first = _alerts.evaluate([], now=T0, eval_heartbeat=hb)
    assert first is not None and "月轮过期" in first["body"]
    # 24h 内第二轮:状态在场但未到期 → 不再计入(抑制),不重发
    assert _alerts.evaluate([], now=T0 + H, eval_heartbeat=hb) is None
    assert _state(alerts_db) == [("monthly-eval", "eval_round", T0, T0)]
    # ≥24h 后重发:last_notified 前推,active_since 不变
    again = _alerts.evaluate([], now=T0 + 25 * H, eval_heartbeat=hb)
    assert again is not None and "月轮过期" in again["body"]
    assert _state(alerts_db) == [
        ("monthly-eval", "eval_round", T0, T0 + 25 * H)]


def test_recovery_clears_state(alerts_db, tmp_path):
    from ipdb import _alerts
    hb = _hb(tmp_path, age_h=36 * 24)
    assert _alerts.evaluate([], now=T0, eval_heartbeat=hb) is not None
    os.utime(hb, (T0 + H, T0 + H))  # 心跳回来(mtime 新)
    msg = _alerts.evaluate([], now=T0 + H, eval_heartbeat=hb)
    assert msg is not None and "monthly-eval" in msg["body"]
    assert _state(alerts_db) == []
