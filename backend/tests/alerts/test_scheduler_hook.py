# backend/tests/alerts/test_scheduler_hook.py — Task 4:scheduler 挂钩
"""RefreshScheduler ↔ _alerts 接通:种子事件、内容变化事件、快照/评估/推送。

循 tests/core/test_scheduler.py 的 fake manager + 真实 tmp 文件源模式
(scan() 直调,无线程)。db 经 IP_RADAR_ALERTS_DB 指 tmp(顶层 conftest
的 autouse 已兜底;本文件 alerts_db 再显式钉同一路径),直读 sqlite 断言
update_events 落库形状(种子 record_count NULL、reconcile 带 health 计数)。
消息字面以 Task 2 报告裁决为准(None-age → 「从未」)。
"""
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

NOW = 2_000_000.0   # 挂钩不关心 due 与否;只求与 mtime 差值可预期
OLD = NOW - 86400   # 日级源一天前的 mtime:首扫即 slot-due(会入队)


class HookSource:
    """scheduler 挂钩测试用源:.name/.stale_days/.health()/_path 齐全,
    真实 tmp 文件支撑 _read_mtime;set_mtime 控制内容变化,record_count
    可变(reconcile 落事件时读 health())。"""

    def __init__(self, name, path, stale_days=1, record_count=0, mtime=None):
        self.name = name
        self.stale_days = stale_days
        self._record_count = record_count
        self._path = Path(path)
        self._path.write_text("x")
        if mtime is not None:
            self.set_mtime(mtime)

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=True,
                            record_count=self._record_count, last_updated=None,
                            is_stale=False, covered_ips=0)

    def set_mtime(self, ts):
        os.utime(str(self._path), (ts, ts))


class FakeManager:
    """Stand-in UpdateManager:记录 detached enqueue,task_state 可脚本化。"""

    def __init__(self):
        self.enqueued = []
        self._states = {}
        self._next = 0

    def enqueue_one_detached(self, name):
        tid = f"t{self._next}"
        self._next += 1
        self.enqueued.append(name)
        self._states.setdefault(tid, "queued")
        from ipdb._tasks import Task
        return Task(id=tid, source_name=name, host=None, batch_id=None)

    def task_state(self, task_id):
        return self._states.get(task_id)


def _make_scheduler(sources, needs_rebuild=lambda s: False):
    from ipdb._scheduler import RefreshScheduler
    mgr = FakeManager()
    sch = RefreshScheduler(
        manager=mgr,
        enabled_offline_sources=lambda: list(sources),
        needs_rebuild_of=needs_rebuild,
        interval=1800)
    return sch, mgr


def _make_src(name, tmp_path, mtime=None, stale_days=1, record_count=0):
    return HookSource(name, tmp_path / f"fake_{name}", stale_days=stale_days,
                      record_count=record_count, mtime=mtime)


@pytest.fixture()
def alerts_db(tmp_path, monkeypatch):
    """逐用例独立 db 文件(与 conftest autouse 同值,显式可读)。"""
    p = tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(p))
    return p


def _events(db):
    """直读 sqlite 验证 update_events(绕开被测 API,断言才独立)。"""
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute(
            "SELECT source, at, record_count FROM update_events"
            " ORDER BY at, id").fetchall()


# ── 种子事件 ──

def test_seed_event_first_scan_and_no_duplicate(alerts_db, tmp_path):
    """种子:源有 mtime 且事件表零行 → 落 (name, mtime, NULL)
    (=首次观测到此内容);再扫 mtime 未变、事件非零 → 不重复种。"""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    assert _events(alerts_db) == [("x", OLD, None)]
    sch.scan(now=NOW + 60.0)
    assert _events(alerts_db) == [("x", OLD, None)]
    assert mgr.enqueued == ["x"]      # 调度行为照常


def test_seed_skipped_when_no_mtime(alerts_db, tmp_path):
    """无文件(mtime None)不种事件——没有可观测的内容。"""
    src = _make_src("gone", tmp_path, mtime=NOW)
    src._path.unlink()
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    assert _events(alerts_db) == []


def test_seed_failure_does_not_block_scheduling(
        alerts_db, tmp_path, monkeypatch, caplog):
    """record_event 抛异常 → 独立兜错只 log,该源本轮调度照常入队。"""
    from ipdb import _alerts
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])

    def boom(source, at, record_count=None):
        raise RuntimeError("seed boom")

    monkeypatch.setattr(_alerts, "record_event", boom)
    with caplog.at_level(logging.ERROR):
        sch.scan(now=NOW)             # must not raise
    assert mgr.enqueued == ["x"]


# ── 内容变化事件(reconcile mtime 前进分支)──

def test_content_change_records_event_with_record_count(alerts_db, tmp_path):
    """mtime 前进(内容变化被 reconcile 确认)→ record_event(at=now,
    record_count=health().record_count);首轮种子保留为第一条,不双记。"""
    src = _make_src("x", tmp_path, mtime=OLD, record_count=4242)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                 # 种子 + 入队 t0
    src.set_mtime(NOW + 100.0)        # download 落地:文件被改写
    sch.scan(now=NOW + 1000.0)        # reconcile:mtime 前进 → 落事件
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", NOW + 1000.0, 4242)]


# ── 轮末告警周期:快照 / evaluate / push / prune ──

def test_snapshots_passed_to_evaluate(alerts_db, tmp_path, monkeypatch):
    """轮末快照 = enabled 源全集,逐源含 name/stale_days/content_age_h
    (now-mtime,无文件 None)/fail_count(_backoff 缺省 0);evaluate
    返回 None → push 不调。"""
    from ipdb import _alerts
    from ipdb._scheduler import _Backoff
    a = _make_src("a", tmp_path, mtime=OLD, stale_days=3)
    b = _make_src("b", tmp_path, mtime=NOW)
    b._path.unlink()                  # 无文件 → content_age_h None
    sch, mgr = _make_scheduler([a, b])
    sch._backoff["a"] = _Backoff(fail_count=2, next_attempt=0.0)
    seen, pushes = [], []

    def fake_evaluate(snapshots, now):
        seen.append((snapshots, now))
        return None

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "evaluate", fake_evaluate)
    monkeypatch.setattr(_alerts, "push", fake_push)
    sch.scan(now=NOW)
    assert seen == [([
        {"name": "a", "stale_days": 3, "content_age_h": 24.0, "fail_count": 2},
        {"name": "b", "stale_days": 1, "content_age_h": None, "fail_count": 0},
    ], NOW)]
    assert pushes == []


def test_evaluate_exception_does_not_kill_scan(
        alerts_db, tmp_path, monkeypatch, caplog):
    """evaluate 抛异常 → 独立 try/except 吞掉(logger.exception),
    scan 照常完成且调度不受影响(scheduler 永不因告警死)。"""
    from ipdb import _alerts
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])

    def boom(snapshots, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(_alerts, "evaluate", boom)
    with caplog.at_level(logging.ERROR):
        sch.scan(now=NOW)             # must not raise
    assert mgr.enqueued == ["x"]
    assert any("alert" in r.getMessage().lower() for r in caplog.records)


def test_push_called_with_evaluate_msg_shape(alerts_db, tmp_path, monkeypatch):
    """真实 evaluate 产消息(无文件 → ∞ 必触发)→ push(title, body) 恰一
    次,参数与 Task 2 钉死字面一致(标题 ipradar 前缀、None-age=从未)。"""
    from ipdb import _alerts
    src = _make_src("gone", tmp_path, mtime=NOW)
    src._path.unlink()
    sch, mgr = _make_scheduler([src])
    pushes = []

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "push", fake_push)
    sch.scan(now=NOW)
    assert pushes == [("ipradar: 1 源异常",
                       "gone: 过期(上次内容更新 从未,阈值 24h)")]


def test_push_not_called_when_evaluate_returns_none(
        alerts_db, tmp_path, monkeypatch):
    """一切正常(新鲜 mtime、零失败)→ evaluate None → push 不调。"""
    from ipdb import _alerts
    src = _make_src("fresh", tmp_path, mtime=NOW)
    sch, mgr = _make_scheduler([src])
    pushes = []

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "push", fake_push)
    sch.scan(now=NOW)
    assert pushes == []


def test_prune_runs_each_scan(alerts_db, tmp_path):
    """同轮 prune:90d 窗口外的旧事件被清(种子因事件非零不触发)。"""
    from ipdb import _alerts
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    _alerts.record_event("x", at=NOW - 91 * 86400)   # 窗口外旧事件
    sch.scan(now=NOW)
    assert _events(alerts_db) == []
