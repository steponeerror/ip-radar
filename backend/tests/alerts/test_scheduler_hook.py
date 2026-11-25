# backend/tests/alerts/test_scheduler_hook.py — Task 4:scheduler 挂钩
"""RefreshScheduler ↔ _alerts 接通:内容更新事件记账(#455 observe_update)、快照/评估/推送。

循 tests/core/test_scheduler.py 的 fake manager + 真实 tmp 文件源模式
(scan() 直调,无线程)。db 经 IP_RADAR_ALERTS_DB 指 tmp(顶层 conftest
的 autouse 已兜底;本文件 alerts_db 再显式钉同一路径),直读 sqlite 断言
update_events 落库形状(种子 record_count NULL、前进事件 at=文件 mtime 带
health 计数)。#455 起记账收到 scan() 开头的 observe_update(水位落库):
谁触发的落盘都算、at 用文件修改时间、重启不丢不重记、mtime 回退不记。
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


class UnloadedSource(HookSource):
    """OL-4 测试源:reader 未加载(epoch 损坏后 load_db 的残留形态)。"""

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=False, record_count=0,
                            last_updated=None, is_stale=False, covered_ips=0)


class FakeManager:
    """Stand-in UpdateManager:记录 detached enqueue,task_state 可脚本化。"""

    def __init__(self):
        self.enqueued = []
        self._states = {}
        self._kinds = {}       # task_id -> failure kind(镜像真 manager,仅 failed 态读)
        self._errors = {}      # task_id -> failure error text(#371,仅 failed 态读)
        self._next = 0

    def enqueue_one_detached(self, name, rebuild_only=False):
        # rebuild_only:收敛批(2026-10-14)调度器以 kwarg 调用;fake 只记账
        tid = f"t{self._next}"
        self._next += 1
        self.enqueued.append(name)
        self._states.setdefault(tid, "queued")
        from ipdb._tasks import Task
        return Task(id=tid, source_name=name, host=None, batch_id=None)

    def task_state(self, task_id):
        return self._states.get(task_id)

    def task_failure_kind(self, task_id):
        # 镜像 UpdateManager.task_failure_kind 语义:仅 failed 态返回分类码
        if self._states.get(task_id) != "failed":
            return None
        return self._kinds.get(task_id)

    def task_error(self, task_id):
        # 镜像 UpdateManager.task_error 语义(#371):仅 failed 态返回失败文本
        if self._states.get(task_id) != "failed":
            return None
        return self._errors.get(task_id)


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


def _alert_state(db):
    """直读 sqlite 验证 alert_state(OL-4:reader 条件经 scheduler 落行)。"""
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute(
            "SELECT source, condition FROM alert_state"
            " ORDER BY source, condition").fetchall()


# ── 种子事件(#455:并入 observe_update,零水位+零事件 → 按 mtime 种)──

def test_seed_event_first_scan_and_no_duplicate(alerts_db, tmp_path):
    """种子:源有 mtime 且事件表零行 → 落 (name, mtime, NULL)
    (=首次观测到此内容);再扫 mtime 未变、水位同值 → 不重复种。"""
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
    """observe_update 抛异常 → 独立兜错只 log,该源本轮调度照常入队。"""
    from ipdb import _alerts
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])

    def boom(source, mtime, record_count=None):
        raise RuntimeError("observe boom")

    monkeypatch.setattr(_alerts, "observe_update", boom)
    with caplog.at_level(logging.ERROR):
        sch.scan(now=NOW)             # must not raise
    assert mgr.enqueued == ["x"]


# ── 内容变化事件(#455:记账只认文件事实,谁触发的落盘都算)──

def test_content_change_records_event_with_record_count(alerts_db, tmp_path):
    """mtime 前进(调度器自己的任务落地)→ 下轮扫描 observe_update 记一条,
    at=文件修改时间(不是扫描时刻),record_count 取 health()。"""
    src = _make_src("x", tmp_path, mtime=OLD, record_count=4242)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                 # 种子 + 入队 t0
    src.set_mtime(NOW + 100.0)        # download 落地:文件被改写
    sch.scan(now=NOW + 1000.0)        # 观察:mtime > 水位 → 落事件
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", NOW + 100.0, 4242)]


def test_external_rewrite_recorded_next_scan_at_file_mtime(
        alerts_db, tmp_path):
    """#455 验收:文件在调度器之外被重写(无任务在途;页面手动/脚本触发
    同形)→ 下一轮扫描后 update_events 多一条,at 等于文件 mtime。"""
    src = _make_src("x", tmp_path, mtime=OLD, record_count=7)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    assert _events(alerts_db) == [("x", OLD, None)]
    src._path.write_text("y")         # 外部落盘(mtime 随之前进,再钉准)
    src.set_mtime(NOW + 500.0)
    sch.scan(now=NOW + 600.0)         # 无任务在途,纯扫描观察
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", NOW + 500.0, 7)]


def test_restart_same_db_no_rerecord_and_catches_up(
        alerts_db, tmp_path):
    """#455 验收:重启不丢、不重记——新建调度器实例指向同一 alerts.db,
    同一 mtime 不再记;停机期间落下的新文件在第一轮扫描补记一条。"""
    src = _make_src("x", tmp_path, mtime=OLD, record_count=3)
    sch1, _ = _make_scheduler([src])
    sch1.scan(now=NOW)                # 种子 (x, OLD)
    src.set_mtime(NOW + 100.0)        # 停机期间文件被重写
    src._record_count = 99            # 新内容计数(health() 取新值)
    sch2, _ = _make_scheduler([src])  # 「重启」:全新实例,同一 alerts.db
    sch2.scan(now=NOW + 200.0)
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", NOW + 100.0, 99)]   # 恰补一条,at=文件 mtime
    sch2.scan(now=NOW + 300.0)        # 同一 mtime 不重记
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", NOW + 100.0, 99)]


def test_mtime_regress_ignored_watermark_never_moves_back(
        alerts_db, tmp_path):
    """#455 验收:mtime 往回退不记、水位不下调;回退后再前进到仍低于旧
    水位 → 不记;超过旧水位 → 记。"""
    src = _make_src("x", tmp_path, mtime=OLD, record_count=1)
    sch, _ = _make_scheduler([src])
    sch.scan(now=NOW)                          # 水位=种子=OLD
    src.set_mtime(OLD - 100.0)                 # 往回退(旧文件搬回/时钟回拨)
    sch.scan(now=NOW + 60.0)
    assert _events(alerts_db) == [("x", OLD, None)]
    src.set_mtime(OLD - 50.0)                  # 仍低于旧水位:不记
    sch.scan(now=NOW + 120.0)
    assert _events(alerts_db) == [("x", OLD, None)]
    src.set_mtime(OLD + 100.0)                 # 超过旧水位:记
    sch.scan(now=NOW + 180.0)
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", OLD + 100.0, 1)]


def test_health_failure_still_records_event_without_count(
        alerts_db, tmp_path):
    """record_count 尽力取:health() 抛异常(如 epoch 损坏)→ 事件照记,
    计数留空(None),记账不因 health 失败而丢。"""
    src = _make_src("x", tmp_path, mtime=OLD)
    src._record_count = 5
    sch, _ = _make_scheduler([src])
    sch.scan(now=NOW)                 # 种子(record_count NULL,不看 health)
    src._path.write_text("y")
    src.set_mtime(NOW + 100.0)

    def broken_health():
        raise RuntimeError("epoch corrupt")

    src.health = broken_health
    sch.scan(now=NOW + 200.0)
    assert _events(alerts_db) == [
        ("x", OLD, None), ("x", NOW + 100.0, None)]


# ── 轮末告警周期:快照 / evaluate / push / prune ──

def test_snapshots_passed_to_evaluate(alerts_db, tmp_path, monkeypatch):
    """轮末快照 = enabled 源全集,逐源含 name/stale_days/content_age_h
    (now-mtime,无文件 None)/fail_count(_backoff 缺省 0);evaluate
    返回 None → push 不调。eval_heartbeat(S6):env 未设 → None;
    env 给路径则透传(scheduler 每轮解析)。"""
    from ipdb import _alerts
    from ipdb._scheduler import _Backoff
    monkeypatch.delenv("IP_RADAR_EVAL_HEARTBEAT", raising=False)
    a = _make_src("a", tmp_path, mtime=OLD, stale_days=3)
    b = _make_src("b", tmp_path, mtime=NOW)
    b._path.unlink()                  # 无文件 → content_age_h None
    sch, mgr = _make_scheduler([a, b])
    # kind=download 随梯子入快照(2026-10-17 裁定:告警分报;×N 口径 =
    # 逐 kind 计数 fail_kind_count);当次失败原因随梯子入快照(#371:
    # fail_error,空白折叠单空格);无梯子 → ""/0/""
    sch._backoff["a"] = _Backoff(fail_count=2, next_attempt=0.0,
                                 kind="download", kind_count=2,
                                 error="HTTP 503 service unavailable")
    seen, pushes = [], []

    def fake_evaluate(snapshots, now, eval_heartbeat=None):
        seen.append((snapshots, now, eval_heartbeat))
        return None

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "evaluate", fake_evaluate)
    monkeypatch.setattr(_alerts, "push", fake_push)
    sch.scan(now=NOW)
    assert seen == [([
        {"name": "a", "stale_days": 3, "content_age_h": 24.0, "fail_count": 2,
         "fail_kind": "download", "fail_kind_count": 2,
         "fail_error": "HTTP 503 service unavailable", "reader_error": False},
        {"name": "b", "stale_days": 1, "content_age_h": None, "fail_count": 0,
         "fail_kind": "", "fail_kind_count": 0, "fail_error": "",
         "reader_error": False},
    ], NOW, None)]
    assert pushes == []
    # S6 接线:env 给路径则透传给 evaluate(未设已验 None)
    seen.clear()
    hb = tmp_path / "eval-heartbeat"
    monkeypatch.setenv("IP_RADAR_EVAL_HEARTBEAT", str(hb))
    sch.scan(now=NOW)
    assert seen[0][2] == hb


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
                       "gone: 内容太久没更新——上次内容更新 从未,告警线 24h。下一步:服务不会自动修,先看上游是否还在发布,再由人决定这个源留还是撤。")]


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


def test_kind_switch_mid_failure_no_false_recovery(
        alerts_db, tmp_path, monkeypatch):
    """双计数走查(2026-10-17 裁定修;#371 阈值 3→2):download 连败到
    total 2 → 告警「连续 2 次下载失败(原因)」(#383 大白话行);total 3 同行 24h 内不重发;
    随后下载成功但构建挂(kind 切换,total 4/kind_count 1)→ 行仍活、
    24h 内无任何消息(不下假「已恢复」——恢复只认真成功);24h 到点
    重发渲染「连续 1 次构建失败」(done 任务无 error → 无原因段)。计时梯
    跟总数走(第 4 级 8h)。"""
    from ipdb import _alerts
    monkeypatch.delenv("IP_RADAR_EVAL_HEARTBEAT", raising=False)
    # partial 车道:last_partial_failure 常立 → 每轮退避到期即重试不等
    # slot(mtime 可全程保持新鲜,stale 不掺和本走查)
    src = _make_src("x", tmp_path, mtime=NOW - 3600.0)
    src.last_partial_failure = ["dead"]
    needs = {"flag": False}
    sch, mgr = _make_scheduler([src], needs_rebuild=lambda s: needs["flag"])
    pushes = []

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "push", fake_push)

    def _fail(kind, error=None):
        mgr._states[sch._last_task["x"]] = "failed"
        mgr._kinds[sch._last_task["x"]] = kind
        if error is not None:
            mgr._errors[sch._last_task["x"]] = error

    # ── 第 1-3 轮:download 连败(退避到期 → partial 车道重试)──
    sch.scan(now=NOW)                  # 入队 t0;轮末 fail_count 0 无消息
    _fail("download", "connection reset by peer")
    sch.scan(now=NOW + 4000.0)         # reconcile:total 1 / kind 1(1h 梯)<2 不告
    sch.scan(now=NOW + 8000.0)         # 过 1h:重试入队
    _fail("download", "connection reset by peer")
    sch.scan(now=NOW + 12000.0)        # total 2 ≥2(#371)→ 落行 + push 带原因
    assert pushes == [("ipradar: 1 源异常",
                       "x: 连续 2 次下载失败(数据拉不下来)(connection reset by peer)。下一步:不用动手,服务会自动重试;持续失败的话这条告警每 24h 重发一次。")]
    assert _alert_state(alerts_db) == [("x", "fail")]
    sch.scan(now=NOW + 20000.0)        # 过 2h:重试入队
    _fail("download", "connection reset by peer")
    sch.scan(now=NOW + 24000.0)        # total 3:行活、24h 内不重发
    assert pushes == [("ipradar: 1 源异常",
                       "x: 连续 2 次下载失败(数据拉不下来)(connection reset by peer)。下一步:不用动手,服务会自动重试;持续失败的话这条告警每 24h 重发一次。")]
    assert _alert_state(alerts_db) == [("x", "fail")]

    # ── 第 4 轮:下载成功但构建挂(kind 切换)──
    sch.scan(now=NOW + 40000.0)        # 过 4h 梯:重试入队 t3
    src.set_mtime(NOW + 40100.0)       # 下载落地(mtime 前进)
    src.last_partial_failure = []      # 家家都成了
    needs["flag"] = True               # …但 ptr 冻结(构建未成)
    mgr._states[sch._last_task["x"]] = "done"
    sch.scan(now=NOW + 41000.0)        # reconcile:mtime 前进 + ptr 冻 → rebuild
    b = sch._backoff["x"]
    assert (b.fail_count, b.kind, b.kind_count) == (4, "rebuild", 1)
    assert b.error == ""              # done 任务无失败文本 → 原因段清空
    # 计时梯跟总数走:第 4 级 8h(若误按 kind_count 落梯会回首级 1h)
    assert b.next_attempt == NOW + 41000.0 + 28800
    # 24h 内:行仍活、无任何消息(尤其无「已恢复」——kind 切换 ≠ 成功)
    assert pushes == [("ipradar: 1 源异常",
                       "x: 连续 2 次下载失败(数据拉不下来)(connection reset by peer)。下一步:不用动手,服务会自动重试;持续失败的话这条告警每 24h 重发一次。")]
    assert _alert_state(alerts_db) == [("x", "fail")]

    # ── 24h 到点重发:文案按当前 kind 渲染 ×1 ──
    sch.scan(now=NOW + 24000.0 + 86401.0)
    assert pushes[1:] == [("ipradar: 1 源异常", "x: 连续 1 次构建失败(数据拉下来了,装进本地库这一步挂了)。下一步:原因段没带出来——人工核对构建日志与上游数据形状,交代理分诊。")]
    assert _alert_state(alerts_db) == [("x", "fail")]   # 行未清,恢复只认真成功
    assert not any("已恢复" in body for _, body in pushes)


def test_scan_fail_alert_carries_reason_with_drift_label(
        alerts_db, tmp_path, monkeypatch):
    """#371 端到端:重建失败文本(#369 判例 "zero records parsed but
    previous count was 41867")经 manager.task_error → _Backoff.error →
    快照 fail_error → 告警行追加原因段,格式漂移关键词命中 →「疑似
    上游格式变动」标签;阈值 2 = 两连败即告。stderr 尾带换行 → 折叠
    单空格不炸行。"""
    from ipdb import _alerts
    monkeypatch.delenv("IP_RADAR_EVAL_HEARTBEAT", raising=False)
    # partial 车道常立(退避到期即重试,不等 slot;mtime 全程新鲜,
    # stale 不掺和本走查)
    src = _make_src("anycast_census", tmp_path, mtime=NOW - 3600.0)
    src.last_partial_failure = ["dead"]
    sch, mgr = _make_scheduler([src])
    pushes = []

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "push", fake_push)

    err = ("Traceback (most recent call last):\n"
           "ValueError: zero records parsed but previous count was 41867\n")

    def _fail_rebuild():
        tid = sch._last_task["anycast_census"]
        mgr._states[tid] = "failed"
        mgr._kinds[tid] = "rebuild"
        mgr._errors[tid] = err

    sch.scan(now=NOW)                  # 入队 t0
    _fail_rebuild()
    sch.scan(now=NOW + 4000.0)         # total 1 <2 不告
    assert pushes == []
    sch.scan(now=NOW + 8000.0)         # 过 1h 梯:重试入队
    _fail_rebuild()
    sch.scan(now=NOW + 12000.0)        # total 2 ≥2 → 告警带原因+标签
    assert pushes == [("ipradar: 1 源异常",
        "anycast_census: 连续 2 次构建失败(数据拉下来了,装进本地库这一步挂了)(疑似上游格式变动: "
        "Traceback (most recent call last): ValueError: zero records"
        " parsed but previous count was 41867)。下一步:括号里标了「疑似上游格式变动」的,多半是上游改了数据格式,人工核对格式;其余按括号里的原因判断。")]
    assert _alert_state(alerts_db) == [("anycast_census", "fail")]
    # 快照面独立验证:fail_error 已折叠单空格入 _Backoff.error
    assert sch._backoff["anycast_census"].error == (
        "Traceback (most recent call last): ValueError: zero records"
        " parsed but previous count was 41867")


def test_prune_runs_each_scan(alerts_db, tmp_path):
    """同轮 prune:90d 窗口外的旧事件被清(种子因事件非零不触发)。"""
    from ipdb import _alerts
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    _alerts.record_event("x", at=NOW - 91 * 86400)   # 窗口外旧事件
    sch.scan(now=NOW)
    assert _events(alerts_db) == []


# ── OL-4:epoch 损坏不再静默(轮末告警查 loaded 态)──

def test_scan_alerts_reader_error_for_corrupt_epoch(
        alerts_db, tmp_path, monkeypatch):
    """ptr 在(库已建成)而 health().loaded=False(load 抛/epoch 损坏)
    → 轮末快照记 reader_error → alert_state 落 reader 行 + push 消息含
    降级行;调度面不自动 rebuild(宁少算,rebuild 人裁)——mtime 新鲜
    且 needs_rebuild=False 时不得入队。"""
    from ipdb import _alerts
    src = UnloadedSource("dbip", tmp_path / "fake_dbip", mtime=NOW)
    ptr = tmp_path / "fake_dbip.lmdb.ptr"
    ptr.write_text("42\n")                    # 库已建成(ptr 在)
    src._mmdb_path = ptr
    sch, mgr = _make_scheduler([src])
    pushes = []

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "push", fake_push)
    sch.scan(now=NOW)
    assert mgr.enqueued == []                 # 不自动 rebuild(人裁不变)
    assert _alert_state(alerts_db) == [("dbip", "reader")]
    assert len(pushes) == 1
    assert pushes[0][0] == "ipradar: 1 源异常"
    assert "dbip: 数据库文件在,但查询端没能加载它" in pushes[0][1]  # #383 大白话行
    # 人裁 rebuild 完成 reader 回来(loaded=True)→ 下一轮恢复,状态自清
    fixed = _make_src("dbip", tmp_path, mtime=NOW)   # HookSource: loaded=True
    fixed._mmdb_path = ptr
    sch2, _ = _make_scheduler([fixed])
    sch2.scan(now=NOW + 60.0)
    assert _alert_state(alerts_db) == []


def test_scan_no_reader_alert_when_never_built(
        alerts_db, tmp_path, monkeypatch):
    """ptr 缺失(库从未建成/冷启动未建)→ reader_error False,不告
    reader——只有「库已建成却加载不上」才算降级。"""
    from ipdb import _alerts
    src = UnloadedSource("fresh", tmp_path / "fake_fresh", mtime=NOW)
    src._mmdb_path = tmp_path / "fake_fresh.lmdb.ptr"   # 不存在
    sch, mgr = _make_scheduler([src])
    pushes = []

    def fake_push(title, body):
        pushes.append((title, body))
        return True

    monkeypatch.setattr(_alerts, "push", fake_push)
    sch.scan(now=NOW)
    assert mgr.enqueued == []                 # mtime 新鲜,非 slot 到期
    assert _alert_state(alerts_db) == []
    assert pushes == []
