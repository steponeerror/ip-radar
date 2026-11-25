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
    # 无 env 时落 source_state 同目录(与 auth.db 同目录惯例;#406 起
    # 经 _paths 解析,monkeypatch env 免 attr-patch)
    from ipdb import _alerts
    monkeypatch.delenv("IP_RADAR_ALERTS_DB", raising=False)
    monkeypatch.setenv("SOURCE_STATE_PATH", str(tmp_path / "source_state.json"))
    _alerts.record_event("otx", at=1.0)
    assert (tmp_path / "alerts.db").exists()


def test_db_path_env_override(tmp_path, monkeypatch):
    # #258 折并钉子:env 覆写直读(纯路径解析,不落盘)
    from ipdb import _alerts
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(tmp_path / "overridden.db"))
    assert _alerts._db_path() == tmp_path / "overridden.db"


def test_db_path_default_and_empty_env_fall_back(tmp_path, monkeypatch):
    # #258 折并钉子(#406 起解析单源在 _paths):缺省回退 source_state
    # 同目录;空串 env 视同未设(负例:钉 `if env:` 真值语义而非
    # is not None,折并前后零变化)
    from ipdb import _alerts
    monkeypatch.setenv("SOURCE_STATE_PATH", str(tmp_path / "source_state.json"))
    monkeypatch.delenv("IP_RADAR_ALERTS_DB", raising=False)
    assert _alerts._db_path() == tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", "")
    assert _alerts._db_path() == tmp_path / "alerts.db"


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


# ── observe_update:#455 内容更新记账唯一入口(source_watermark 水位落库)──

def _watermark(db, source):
    """直读 sqlite 验证水位(绕开被测 API,断言才独立)。"""
    with closing(sqlite3.connect(str(db))) as conn:
        row = conn.execute(
            "SELECT mtime FROM source_watermark WHERE source = ?",
            (source,)).fetchone()
    return row[0] if row else None


def test_observe_first_seen_seeds_and_writes_watermark(alerts_db):
    # 零水位 + 零事件 → 按 mtime 种一条(record_count NULL,原种子逻辑)+ 写水位
    from ipdb import _alerts
    assert _alerts.observe_update("otx", 100.0) is True
    assert _rows(alerts_db) == [("otx", 100.0, None)]
    assert _watermark(alerts_db, "otx") == 100.0


def test_observe_existing_history_no_reseed_writes_watermark(alerts_db):
    # 存量库迁移:update_events 有行、水位表刚建 → 只写水位不补种
    from ipdb import _alerts
    _alerts.record_event("otx", at=10.0)
    assert _alerts.observe_update("otx", 100.0) is False
    assert _rows(alerts_db) == [("otx", 10.0, None)]
    assert _watermark(alerts_db, "otx") == 100.0


def test_observe_advance_records_at_mtime_with_count(alerts_db):
    # mtime > 水位 → 记一条 at=文件 mtime(不是扫描时刻),计数随入,水位推进
    from ipdb import _alerts
    assert _alerts.observe_update("otx", 100.0) is True          # 种子
    assert _alerts.observe_update("otx", 200.0, record_count=123) is True
    assert _rows(alerts_db) == [
        ("otx", 100.0, None), ("otx", 200.0, 123)]
    assert _watermark(alerts_db, "otx") == 200.0


def test_observe_same_mtime_noop(alerts_db):
    from ipdb import _alerts
    _alerts.observe_update("otx", 100.0)
    assert _alerts.observe_update("otx", 100.0, record_count=5) is False
    assert _rows(alerts_db) == [("otx", 100.0, None)]


def test_observe_regress_ignored_watermark_never_moves_back(alerts_db):
    # 回退不记、水位不下调;仍低于旧水位的「前进」也不记;超过旧水位才记
    from ipdb import _alerts
    _alerts.observe_update("otx", 100.0)
    assert _alerts.observe_update("otx", 50.0) is False
    assert _alerts.observe_update("otx", 99.9) is False
    assert _rows(alerts_db) == [("otx", 100.0, None)]
    assert _watermark(alerts_db, "otx") == 100.0
    assert _alerts.observe_update("otx", 101.0, record_count=7) is True
    assert _rows(alerts_db) == [
        ("otx", 100.0, None), ("otx", 101.0, 7)]


# ── observed_interval_h 最小间隔下限(#455:中位数不计风暴短间隔)──

def test_median_filter_ignores_short_intervals(alerts_db):
    # 10 事件:gaps [1,1,1,1,6,10,10,10,10]h——无下限中位 6h;
    # 下限 6h 过滤后 [6,10,10,10,10] → 中位 10h
    from ipdb import _alerts
    for h in (0, 1, 2, 3, 4, 10, 20, 30, 40, 50):
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h("otx", now=50 * 3600) == pytest.approx(6.0)
    assert _alerts.observed_interval_h(
        "otx", now=50 * 3600, min_interval_s=6 * 3600) == pytest.approx(10.0)


def test_median_all_intervals_below_floor_none(alerts_db):
    # 全部短于下限 → None(回退声明线),即便不过滤时中位数算得出来
    from ipdb import _alerts
    for h in (0, 1, 2, 3, 4, 5):
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h("otx", now=5 * 3600) == pytest.approx(1.0)
    assert _alerts.observed_interval_h(
        "otx", now=5 * 3600, min_interval_s=6 * 3600) is None


def test_median_filtered_below_four_gaps_none(alerts_db):
    # 过滤后不足 4 个间隔(= 不足 5 个事件)→ None(即便无过滤时事件数够、
    # 中位数能算)
    from ipdb import _alerts
    for h in (0, 1, 2, 3, 24, 48, 72):
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h(
        "otx", now=72 * 3600, min_interval_s=6 * 3600) is None


def test_median_filtered_four_surviving_gaps_still_read(alerts_db):
    # 回归钉(2026-11-26 评审前自查):恰好 5 个事件、间隔全部过得了下限 →
    # 读数保留(4 个间隔与「事件 ≥5」同一把尺)。首版把门槛误写成「5 个
    # 间隔」,生产账本里 protonvpn/nordvpn/cdn_edges/rir_abuse 四个周更源
    # 会从约 168h 变成 None、告警线从约 672h 缩到 168h。
    from ipdb import _alerts
    for h in (0, 168, 336, 504, 972):
        _alerts.record_event("otx", at=float(h) * 3600)
    assert _alerts.observed_interval_h(
        "otx", now=972 * 3600, min_interval_s=42 * 3600) == pytest.approx(168.0)
    # 带下限与不带下限读数相同:没有风暴的源不受影响
    assert _alerts.observed_interval_h("otx", now=972 * 3600) == pytest.approx(168.0)
