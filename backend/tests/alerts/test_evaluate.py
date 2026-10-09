# backend/tests/alerts/test_evaluate.py — Task 2:evaluate 状态机 + 合并消息组装
"""per-(source, condition) 状态机(转入/24h 重发/恢复/静默清理)与逐字消息。

IP_RADAR_ALERTS_DB 指向 tmp 逐用例隔离;直读 sqlite 断言 alert_state,
证明状态经 DB 持久推进而非内存。时间一律 epoch 秒。消息字面来自
plan 约束 6(ASCII 标点、× 为 U+00D7、恢复段前缀 —— 为两个 U+2014)。
"""
import sqlite3
from contextlib import closing

import pytest

T0 = 1_700_000_000.0
H = 3600.0


@pytest.fixture()
def alerts_db(tmp_path, monkeypatch):
    """逐用例独立 db 文件;路径缓存按 resolved path,换 tmp 即换工厂。"""
    p = tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(p))
    return p


def _snap(name, stale_days=1, age=1.0, fail=0, reader=False):
    return {"name": name, "stale_days": stale_days,
            "content_age_h": age, "fail_count": fail,
            "reader_error": reader}


def _seed_observed(source, gap_h, now, events=6):
    """等间隔事件 → 观测间隔中位数 = gap_h(≥5 事件观测侧才参与)。"""
    from ipdb import _alerts
    for k in range(events - 1, -1, -1):
        _alerts.record_event(source, at=now - k * gap_h * H)


def _state(db):
    """直读 sqlite 验证 alert_state(绕开被测 API,断言才独立)。"""
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute(
            "SELECT source, condition, active_since, last_notified"
            " FROM alert_state ORDER BY source, condition").fetchall()


def _set_last_notified(db, source, cond, value):
    with closing(sqlite3.connect(str(db))) as conn, conn:
        conn.execute(
            "UPDATE alert_state SET last_notified = ?"
            " WHERE source = ? AND condition = ?", (value, source, cond))


def test_empty_round_returns_none(alerts_db):
    from ipdb import _alerts
    assert _alerts.evaluate([], now=T0) is None
    assert _state(alerts_db) == []


def test_transition_sends_then_silences_within_24h(alerts_db):
    from ipdb import _alerts
    snap = [_snap("spamhaus", age=26.0)]  # 无事件 → 阈值 = stale_days×24 = 24h
    msg = _alerts.evaluate(snap, now=T0)
    assert msg == {"title": "ipradar: 1 源异常",
                   "body": "spamhaus: 过期(上次内容更新 26h,阈值 24h)"}
    assert _state(alerts_db) == [("spamhaus", "stale", T0, T0)]
    # 持续坏未满 24h:不入消息,last_notified 不动
    assert _alerts.evaluate(snap, now=T0 + H) is None
    assert _state(alerts_db) == [("spamhaus", "stale", T0, T0)]


def test_refire_boundary_86399_vs_86401(alerts_db):
    from ipdb import _alerts
    snap = [_snap("spamhaus", age=26.0)]
    _alerts.evaluate(snap, now=T0)
    assert _alerts.evaluate(snap, now=T0 + 86399) is None  # 差 1s 不重发
    msg = _alerts.evaluate(snap, now=T0 + 86401)
    assert msg["title"] == "ipradar: 1 源异常"  # 过 1s 重发计入
    # 重发只刷新 last_notified,active_since 保持转入时刻
    assert _state(alerts_db) == [("spamhaus", "stale", T0, T0 + 86401)]


def test_recovery_round_message_and_state_delete(alerts_db):
    from ipdb import _alerts
    _alerts.evaluate([_snap("dshield", age=26.0)], now=T0)
    # 恢复-only 轮:标题 {k} 源已恢复,body 仅恢复段一行
    msg = _alerts.evaluate([_snap("dshield", age=1.0)], now=T0 + H)
    assert msg == {"title": "ipradar: 1 源已恢复",
                   "body": "——已恢复: dshield"}
    assert _state(alerts_db) == []
    assert _alerts.evaluate([_snap("dshield", age=1.0)],
                            now=T0 + 2 * H) is None


def test_multi_source_recovery_same_round(alerts_db):
    from ipdb import _alerts
    # 两源同轮恢复(T2-P2-1):恢复段源名逗号+空格连接、字母序——
    # 快照故意逆序传入,锁定输出按 sorted() 排序而非入参顺序
    _alerts.evaluate([_snap("otx", age=26.0), _snap("dshield", age=26.0)],
                     now=T0)
    msg = _alerts.evaluate([_snap("otx", age=1.0), _snap("dshield", age=1.0)],
                           now=T0 + H)
    assert msg == {"title": "ipradar: 2 源已恢复",
                   "body": "——已恢复: dshield, otx"}
    assert _state(alerts_db) == []


def test_fail_condition_and_its_recovery(alerts_db):
    from ipdb import _alerts
    msg = _alerts.evaluate([_snap("otx", age=1.0, fail=3)], now=T0)
    assert msg == {"title": "ipradar: 1 源异常",
                   "body": "otx: 连续失败 ×3"}
    assert _state(alerts_db) == [("otx", "fail", T0, T0)]
    # fail_count 降回 <3 = 条件解除 → 恢复段
    msg = _alerts.evaluate([_snap("otx", age=1.0, fail=1)], now=T0 + H)
    assert msg == {"title": "ipradar: 1 源已恢复", "body": "——已恢复: otx"}


def test_fail_count_defaults_to_zero(alerts_db):
    from ipdb import _alerts
    snap = [{"name": "otx", "stale_days": 1, "content_age_h": 1.0}]  # 缺 fail_count
    assert _alerts.evaluate(snap, now=T0) is None
    assert _state(alerts_db) == []


def test_reader_error_condition_and_recovery(alerts_db):
    """OL-4:库已建成(ptr 在)但 reader 未加载(load 抛/epoch 损坏)→
    reader 条件转入,逐字消息行 + alert_state 落行;恢复(人裁 rebuild
    完成 reader 回来)→ 恢复段。"""
    from ipdb import _alerts
    msg = _alerts.evaluate([_snap("dbip", age=1.0, reader=True)], now=T0)
    assert msg == {"title": "ipradar: 1 源异常",
                   "body": "dbip: 数据库未加载(疑 epoch 损坏),查询端静默缺席"}
    assert _state(alerts_db) == [("dbip", "reader", T0, T0)]
    # reader_error 回 False = 条件解除 → 恢复段
    msg = _alerts.evaluate([_snap("dbip", age=1.0)], now=T0 + H)
    assert msg == {"title": "ipradar: 1 源已恢复", "body": "——已恢复: dbip"}


def test_reader_error_key_absent_defaults_false(alerts_db):
    """旧快照形状(无 reader_error 键)不触发 reader 条件(向后兼容)。"""
    from ipdb import _alerts
    snap = [{"name": "otx", "stale_days": 1, "content_age_h": 1.0,
             "fail_count": 0}]
    assert _alerts.evaluate(snap, now=T0) is None
    assert _state(alerts_db) == []


def test_reader_error_counts_source_once_with_stale(alerts_db):
    """reader + stale 同源同轮双条件:标题 N = 异常源数(双条件算 1),
    消息行 stale 在前 reader 在后(组装序)。"""
    from ipdb import _alerts
    msg = _alerts.evaluate([_snap("dbip", age=26.0, reader=True)], now=T0)
    assert msg == {
        "title": "ipradar: 1 源异常",
        "body": "dbip: 过期(上次内容更新 26h,阈值 24h)\n"
                "dbip: 数据库未加载(疑 epoch 损坏),查询端静默缺席"}
    assert [r[:2] for r in _state(alerts_db)] == [("dbip", "reader"), ("dbip", "stale")]


def test_none_age_always_triggers(alerts_db):
    from ipdb import _alerts
    msg = _alerts.evaluate(
        [{"name": "greensnow", "stale_days": 1, "content_age_h": None,
          "fail_count": 0}], now=T0)
    # 无文件 → age 视为 ∞ 必触发;age 字面渲染「从未」,阈值照常数值
    assert msg == {"title": "ipradar: 1 源异常",
                   "body": "greensnow: 过期(上次内容更新 从未,阈值 24h)"}


def test_label_dichotomy_stale_vs_stall(alerts_db):
    from ipdb import _alerts
    _seed_observed("fast", gap_h=5.0, now=T0)   # 5×4=20 < 24 → 过期
    _seed_observed("even", gap_h=6.0, now=T0)   # 6×4=24 == 24 → 过期(非严格大)
    _seed_observed("slow", gap_h=7.2, now=T0)   # 7.2×4=28.8 > 24 → 停更嫌疑
    _seed_observed("daily", gap_h=48.0, now=T0)  # 48×4=192 > 24 → 停更嫌疑(d 档)
    snaps = [
        _snap("slow", age=30.0),    # thr 28.8h
        _snap("even", age=25.5),    # thr 24h;25.5h 向上取整 → 26h
        _snap("fast", age=26.0),    # thr 24h
        _snap("daily", age=200.0),  # thr 192h;200h/48h 均落 d 档
    ]
    msg = _alerts.evaluate(snaps, now=T0)
    assert msg["title"] == "ipradar: 4 源异常"
    # 过期/停更同组,组内按源名字母序
    assert msg["body"].splitlines() == [
        "daily: 停更嫌疑(8.3d 未变,实测 2.0d/次)",
        "even: 过期(上次内容更新 26h,阈值 24h)",
        "fast: 过期(上次内容更新 26h,阈值 24h)",
        "slow: 停更嫌疑(30h 未变,实测 8h/次)",
    ]


def test_dual_condition_same_source_counts_once(alerts_db):
    from ipdb import _alerts
    msg = _alerts.evaluate([_snap("otx", age=26.0, fail=5)], now=T0)
    assert msg["title"] == "ipradar: 1 源异常"  # 两条件都坏,异常源数算 1
    assert msg["body"].splitlines() == [
        "otx: 过期(上次内容更新 26h,阈值 24h)",  # 过期/停更行在前
        "otx: 连续失败 ×5",                        # 失败行在后
    ]
    assert _state(alerts_db) == [
        ("otx", "fail", T0, T0), ("otx", "stale", T0, T0)]
    # 两条件同轮解除 → 状态全删,恢复段源名只出现一次
    msg = _alerts.evaluate([_snap("otx", age=1.0)], now=T0 + H)
    assert msg == {"title": "ipradar: 1 源已恢复", "body": "——已恢复: otx"}
    assert _state(alerts_db) == []


def test_merged_round_literal(alerts_db):
    from ipdb import _alerts
    # t0:dshield 转坏(待恢复)、feodo 转坏(待重发)
    _alerts.evaluate([_snap("dshield", age=26.0),
                      _snap("feodo", age=1.0, fail=3)], now=T0)
    t1 = T0 + 86401
    _seed_observed("greensnow", gap_h=48.0, now=t1)
    # t1:到点重发 + 恢复 + 新转入合并为一条;标题 N = 异常源数
    msg = _alerts.evaluate(
        [_snap("dshield", age=1.0),          # 恢复
         _snap("greensnow", age=200.0),      # 新转入(停更嫌疑,d 档)
         _snap("feodo", age=1.0, fail=4)],   # 到点重发(×4)
        now=t1)
    assert msg == {
        "title": "ipradar: 2 源异常",
        "body": "greensnow: 停更嫌疑(8.3d 未变,实测 2.0d/次)\n"
                "feodo: 连续失败 ×4\n"
                "——已恢复: dshield",
    }


def test_disappeared_source_silently_cleaned(alerts_db):
    from ipdb import _alerts
    _alerts.evaluate([_snap("spamhaus", age=26.0),
                      _snap("otx", age=1.0, fail=3)], now=T0)
    # otx 从快照消失(被禁用):静默清状态,不入恢复段;spamhaus 未到 24h
    msg = _alerts.evaluate([_snap("spamhaus", age=26.0)], now=T0 + H)
    assert msg is None
    assert [r[:2] for r in _state(alerts_db)] == [("spamhaus", "stale")]


def test_state_machine_driven_by_db_not_memory(alerts_db):
    from ipdb import _alerts
    snap = [_snap("otx", age=26.0)]
    _alerts.evaluate(snap, now=T0)
    # 直改 DB 回拨 last_notified(等价重启/他进程视角)→ 立即视为到点重发
    _set_last_notified(alerts_db, "otx", "stale", T0 - 86401)
    assert _alerts.evaluate(snap, now=T0)["title"] == "ipradar: 1 源异常"
    # 直插一条状态 → 本轮条件不成立即恢复:读的是 DB,非内存缓存
    with closing(sqlite3.connect(str(alerts_db))) as conn, conn:
        conn.execute(
            "INSERT INTO alert_state (source, condition, active_since,"
            " last_notified) VALUES ('dshield', 'stale', 0, 0)")
    msg = _alerts.evaluate([_snap("otx", age=26.0), _snap("dshield", age=1.0)],
                           now=T0 + H)
    assert msg == {"title": "ipradar: 1 源已恢复", "body": "——已恢复: dshield"}
