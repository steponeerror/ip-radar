# backend/tests/alerts/test_storage.py — Task 1:_alerts 存储层(建表/事件/节奏/阈值/清理)
"""update_events 落库与近 90 天节奏计算。IP_RADAR_ALERTS_DB 指向 tmp 隔离
(循 IP_RADAR_AUTH_DB 惯例),不触真 data 目录。时间一律 epoch 秒,断言小时。
"""
import sqlite3
from contextlib import closing

import pytest


@pytest.fixture()
def alerts_db(tmp_path, monkeypatch):
    """逐用例独立 db 文件;路径缓存按 resolved path,换 tmp 即换工厂。"""
    p = tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(p))
    return p


def _rows(db):
    """直读 sqlite 验证落库(绕开被测 API,断言才独立)。"""
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute(
            "SELECT source, at, record_count FROM update_events"
            " ORDER BY source, at, id").fetchall()


def test_import_alone_creates_no_file(alerts_db):
    # 惰性:建表发生在首次操作,不在模块导入期
    from ipdb import _alerts
    assert not alerts_db.exists()
    assert _alerts.stall_threshold_h(1, None) == pytest.approx(24.0)
    assert not alerts_db.exists()  # 纯函数也不落盘


def test_record_creates_schema_idempotently(alerts_db):
    from ipdb import _alerts
    _alerts.record_event("otx", at=100.0)
    _alerts.record_event("otx", at=200.0)  # 二次操作:CREATE IF NOT EXISTS 幂等
    assert alerts_db.exists()
    assert _rows(alerts_db) == [("otx", 100.0, None), ("otx", 200.0, None)]


def test_default_path_next_to_state(tmp_path, monkeypatch):
    # 无 env 时落 _STATE_PATH.parent(与 auth.db 同目录惯例)
    from ipdb import _alerts, _registry
    monkeypatch.delenv("IP_RADAR_ALERTS_DB", raising=False)
    monkeypatch.setattr(_registry, "_STATE_PATH", tmp_path / "source_state.json")
    _alerts.record_event("otx", at=1.0)
    assert (tmp_path / "alerts.db").exists()


def test_empty_db_observed_none_idempotent(alerts_db):
    from ipdb import _alerts
    assert _alerts.observed_interval_h("otx", now=1_000_000.0) is None
    assert _alerts.observed_interval_h("otx", now=2_000_000.0) is None  # 空库可重复读
    _alerts.prune(now=1_000_000.0)  # 空库 prune 不炸
    assert _rows(alerts_db) == []


def test_fewer_than_five_events_none(alerts_db):
    from ipdb import _alerts
    for h in (0, 3, 7, 12):  # 4 事件 → 观测侧不参与
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h("otx", now=12 * 3600) is None


def test_median_odd_interval_count(alerts_db):
    # 6 事件 → 5 个间隔 [2,4,6,8,10]h → 中位 6h
    from ipdb import _alerts
    for h in (0, 2, 6, 12, 20, 30):
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h("otx", now=30 * 3600) == pytest.approx(6.0)


def test_median_even_interval_count(alerts_db):
    # 5 事件 → 4 个间隔 [2,4,6,8]h → 中位 (4+6)/2 = 5h
    from ipdb import _alerts
    for h in (0, 2, 6, 12, 20):
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h("otx", now=20 * 3600) == pytest.approx(5.0)


def test_window_trims_events_older_than_90d(alerts_db):
    # 近 5 个 24h 事件 + 两个 90d 外旧事件:误入会把中位拉爆
    from ipdb import _alerts
    D = 86400.0
    now = 100 * D
    for h in (0, 24, 48, 72, 96):
        _alerts.record_event("s", at=now - h * 3600)
    _alerts.record_event("s", at=now - 91 * D)
    _alerts.record_event("s", at=now - 95 * D)
    assert _alerts.observed_interval_h("s", now) == pytest.approx(24.0)


def test_window_boundary_inclusive(alerts_db):
    # 首事件恰在 now-90d:窗口含入(at >= 下界,与 prune 的 < 互补)
    from ipdb import _alerts
    D = 86400.0
    now = 200 * D
    cutoff = now - 90 * D
    for h in (0, 10, 20, 30, 40):
        _alerts.record_event("s", at=cutoff + h * 3600)
    # 排除则仅 4 事件 → None;含入 → 间隔全 10h
    assert _alerts.observed_interval_h("s", now) == pytest.approx(10.0)


def test_events_isolated_per_source(alerts_db):
    from ipdb import _alerts
    for h in (0, 24, 48, 72, 96):
        _alerts.record_event("otx", at=float(h) * 3600)
    for h in (0, 1):  # 别的源的事件不串台
        _alerts.record_event("dshield", at=float(h) * 3600)
    assert _alerts.observed_interval_h("otx", now=96 * 3600) == pytest.approx(24.0)
    assert _alerts.observed_interval_h("dshield", now=96 * 3600) is None


def test_prune_deletes_only_older_than_90d(alerts_db):
    from ipdb import _alerts
    D = 86400.0
    now = 300 * D
    _alerts.record_event("old", at=now - 91 * D)
    _alerts.record_event("edge", at=now - 90 * D)  # 边界保留(开区间删)
    _alerts.record_event("new", at=now - 3600)
    _alerts.prune(now)
    assert [r[0] for r in _rows(alerts_db)] == ["edge", "new"]
    _alerts.prune(now)  # 幂等
    assert len(_rows(alerts_db)) == 2


def test_stall_threshold_observed_none():
    from ipdb import _alerts
    assert _alerts.stall_threshold_h(2, None) == pytest.approx(48.0)


def test_stall_threshold_stale_days_wins():
    from ipdb import _alerts
    # stale_days=1 → 24h;observed 2h×4=8h < 24h
    assert _alerts.stall_threshold_h(1, 2.0) == pytest.approx(24.0)


def test_stall_threshold_observed_wins():
    from ipdb import _alerts
    # observed 10h×4=40h > 24h
    assert _alerts.stall_threshold_h(1, 10.0) == pytest.approx(40.0)


def test_record_count_persisted(alerts_db):
    from ipdb import _alerts
    _alerts.record_event("otx", at=100.0, record_count=123)
    _alerts.record_event("otx", at=200.0)  # 缺省落 NULL
    assert _rows(alerts_db) == [
        ("otx", 100.0, 123), ("otx", 200.0, None)]
