"""RefreshScheduler + detached-enqueue/task_state unit tests.

Real UpdateManager for the manager-method tests; a FakeManager for the
scheduler-logic tests (added in Task 3) so task_state can be controlled
deterministically without threads.
"""
import threading
import time

from ipdb._tasks import UpdateManager


class FakeSource:
    """Minimal source for manager-level tests (mirrors test_tasks.FakeSource)."""

    def __init__(self, name, host="h", slow=0.0):
        self.name = name
        self.download_host = host
        self._slow = slow
        self._lock = threading.Lock()

    def download(self, token=None):
        time.sleep(self._slow)

    def load(self):
        pass

    def rebuild(self):
        pass


def _make_manager(sources, concurrency=3):
    by_name = {s.name: s for s in sources}
    locks = {}

    def lock_for(n):
        locks.setdefault(n, threading.Lock())
        return locks[n]

    return UpdateManager(
        resolve_source=lambda n: by_name.get(n),
        lock_for=lock_for, concurrency=concurrency), by_name


def test_enqueue_one_detached_forces_none_batch_id():
    """C1 fix: detached tasks get batch_id=None even with an active batch."""
    mgr, _ = _make_manager([FakeSource("a", slow=5.0), FakeSource("b", slow=5.0)])
    # Plant an active batch with a different source to keep _active_batch set
    # without creating an in-flight task for "a"
    mgr.enqueue_batch(["b"])
    assert mgr._active_batch is not None

    # enqueue_one_detached should create a task with batch_id=None,
    # even though there's an active batch (and no in-flight task for "a")
    task = mgr.enqueue_one_detached("a")
    assert task.batch_id is None, "detached task must never carry a batch_id"

    # The task's batch_id is reflected in to_dict (what SSE/clients see).
    snap = mgr.snapshot()
    a_task = [t for t in snap["tasks"] if t["source"] == "a"][0]
    assert a_task["batch_id"] is None

    # cleanup: cancel the in-flight detached task so the worker exits
    mgr.cancel(task.id)


def test_task_state_returns_state_or_none():
    """task_state is a lock-guarded lookup; None for unknown ids."""
    mgr, _ = _make_manager([FakeSource("a", slow=5.0)])
    task = mgr.enqueue_one("a")  # queued or running shortly
    # task_id is known while the task exists in _tasks
    assert mgr.task_state(task.id) in (
        "queued", "downloading", "loading", "throttled", "done", "failed", "cancelled")
    # unknown id -> None, never raises
    assert mgr.task_state("does-not-exist") is None
    mgr.cancel(task.id)


def test_enabled_offline_sources_returns_objects_not_names(tmp_path):
    """enabled_offline_sources returns Source objects (offline+enabled), not names."""
    from ipdb._registry import enabled_offline_sources
    srcs = enabled_offline_sources()
    # Every returned object is a Source instance with a .name and an _path attr
    # (offline sources set _path in __init__). We assert on shape, not specific
    # sources, since the discovered set is environment-dependent.
    for s in srcs:
        assert isinstance(s.name, str) and s.name
        assert hasattr(s, "_path"), f"{s.name} has no _path (not offline-shaped)"


def test_needs_rebuild_of_detects_stale_mmdb(tmp_path):
    """_needs_rebuild_of is True when MMDB is missing or older than raw."""
    from pathlib import Path
    from ipdb._registry import _needs_rebuild_of
    import time

    class _FakeOffline:
        def __init__(self, p):
            self._path = p
            self._lmdb_base = Path(str(p) + ".lmdb")   # C2/ADR 0009:族契约属性

    raw = tmp_path / "raw.txt"
    from ipdb._sources._lmdb import HARVEST_REV, ptr_path, rev_path
    base = Path(str(raw) + ".lmdb")

    # raw exists, 族 ptr 缺失 -> needs rebuild
    raw.write_text("x")
    f = _FakeOffline(raw)
    assert _needs_rebuild_of(f) is True

    # ptr 新于 raw + .rev 戳匹配 -> does not need rebuild
    ptr_path(base).write_text("1")
    rev_path(base).write_text(str(HARVEST_REV))
    fut = time.time() + 100
    import os
    os.utime(ptr_path(base), (fut, fut))
    assert _needs_rebuild_of(f) is False

    # raw newer than ptr -> needs rebuild(mtime 腿)
    os.utime(raw, (fut + 200, fut + 200))
    assert _needs_rebuild_of(f) is True

    # .rev 戳漂移(代码代演进,mtime 收敛)-> needs rev-leg rebuild
    os.utime(ptr_path(base), (fut + 400, fut + 400))
    rev_path(base).write_text(str(HARVEST_REV - 1))
    assert _needs_rebuild_of(f) is True


# ── Scheduler-logic tests (no threads; scan() called directly) ──

class SchedFakeSource:
    """Source object for scheduler tests: has .name, .health(), _path, _mmdb_path.

    Backed by a REAL temp file so _read_mtime's Path(_path).stat().st_mtime
    works identically to production. Use set_mtime() to control the file's
    mtime between scans.
    """

    def __init__(self, name, path, is_stale=False, mtime=None, mmdb_path=None,
                 stale_days=1):
        self.name = name
        self._is_stale = is_stale
        self.stale_days = stale_days
        from pathlib import Path
        self._path = Path(path)
        self._mmdb_path = mmdb_path or Path(str(path) + ".mmdb")
        self._lmdb_base = Path(str(path) + ".lmdb")  # C2:族契约(needs_convert 对象)
        if mtime is not None:
            self.set_mtime(mtime)

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=True, record_count=0,
                            last_updated=None, is_stale=self._is_stale, covered_ips=0)

    def set_mtime(self, ts):
        """Set the file's mtime (and atime) to ts via os.utime."""
        import os
        os.utime(str(self._path), (ts, ts))


class FakeManager:
    """Stand-in UpdateManager: records detached enqueues, returns scripted states."""

    def __init__(self):
        self.enqueued = []        # list of source names enqueue_one_detached was called with
        self.lanes = []           # parallel to enqueued: rebuild_only flag per call
        self._states = {}         # task_id -> state (scripted)
        self._rebuild_only = {}   # task_id -> rebuild_only flag
        self._kinds = {}          # task_id -> failure kind (scripted, failed 态才读)
        self._next_task_id = 0

    def enqueue_one_detached(self, name, rebuild_only=False):
        tid = f"t{self._next_task_id}"
        self._next_task_id += 1
        self.enqueued.append(name)
        self.lanes.append(rebuild_only)
        self._states.setdefault(tid, "queued")  # default queued unless overwritten
        self._rebuild_only[tid] = rebuild_only
        from ipdb._tasks import Task
        return Task(id=tid, source_name=name, host=None, batch_id=None,
                    _rebuild_only=rebuild_only)

    def task_state(self, task_id):
        return self._states.get(task_id)

    def task_rebuild_only(self, task_id):
        return self._rebuild_only.get(task_id, False)

    def task_failure_kind(self, task_id):
        # 镜像 UpdateManager.task_failure_kind 语义:仅 failed 态返回分类码
        if self._states.get(task_id) != "failed":
            return None
        return self._kinds.get(task_id)


def _make_scheduler(sources, manager=None, needs_rebuild=lambda s: False, interval=1800):
    from ipdb._scheduler import RefreshScheduler
    mgr = manager or FakeManager()
    sch = RefreshScheduler(
        manager=mgr,
        enabled_offline_sources=lambda: list(sources),
        needs_rebuild_of=needs_rebuild,
        interval=interval)
    return sch, mgr


def _make_src(name, tmp_path, is_stale=False, mtime=None):
    """Create a SchedFakeSource backed by a real temp file in tmp_path."""
    p = tmp_path / f"fake_{name}"
    p.write_text("x")
    return SchedFakeSource(name, path=p, is_stale=is_stale, mtime=mtime)


NOW = 1_000_000.0   # slot-era tests share an epoch-scale time base
OLD = NOW - 86400   # a day-old mtime: daily tier is guaranteed due at NOW


def test_scan_slot_due_enqueues_only_due(tmp_path):
    """Slot-era predicate: enqueues only sources past their due slot."""
    due = _make_src("due_src", tmp_path, mtime=OLD)
    fresh = _make_src("fresh_src", tmp_path, mtime=NOW - 60)
    sch, mgr = _make_scheduler([due, fresh])
    sch.scan(now=NOW)
    assert mgr.enqueued == ["due_src"]


def test_scan_mtime_none_enqueues(tmp_path):
    """Download-failure residue (file deleted → mtime None) is immediately due."""
    src = _make_src("gone", tmp_path, mtime=NOW)
    src._path.unlink()
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    assert mgr.enqueued == ["gone"]


def test_scan_needs_rebuild_ignores_slot(tmp_path):
    """needs_rebuild fires immediately even when mtime is fresh."""
    src = _make_src("rb", tmp_path, mtime=NOW)     # fresh: not slot-due
    sch, mgr = _make_scheduler([src], needs_rebuild=lambda s: True)
    sch.scan(now=NOW)
    assert mgr.enqueued == ["rb"]


def test_scan_needs_rebuild_inclusion(tmp_path):
    """A fresh-mtime source with needs_rebuild=True is still enqueued."""
    sch, mgr = _make_scheduler(
        [_make_src("rebuild_only", tmp_path, is_stale=False)],
        needs_rebuild=lambda s: s.name == "rebuild_only")
    sch.scan(now=1000.0)
    assert mgr.enqueued == ["rebuild_only"]


def test_scan_backoff_skip(tmp_path):
    """A slot-due source in active backoff (now < next_attempt) is NOT enqueued
    — the backoff guard alone suppresses it (regression pin: deleting the
    guard must fail this test)."""
    src = _make_src("x", tmp_path, mtime=OLD)      # slot-due at NOW
    sch, mgr = _make_scheduler([src])
    from ipdb._scheduler import _Backoff
    # Plant a backoff entry: next_attempt well past NOW(真 _Backoff:轮末
    # 快照要读 kind/kind_count,假对象会触发告警侧异常兑错路径)
    sch._backoff["x"] = _Backoff(
        fail_count=1, next_attempt=NOW + 99999.0)
    sch.scan(now=NOW)
    assert mgr.enqueued == []
    # and without the guard the source WOULD be due (guards the pin itself)
    sch2, mgr2 = _make_scheduler([_make_src("x", tmp_path, mtime=OLD)])
    sch2.scan(now=NOW)
    assert mgr2.enqueued == ["x"]


def test_reconcile_success_clears_fail_count(tmp_path):
    """mtime changed between scans -> fail_count reset to 0, backoff cleared."""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    assert "x" in sch._last_task
    from ipdb._scheduler import _Backoff
    sch._backoff["x"] = _Backoff(fail_count=2, next_attempt=0.0)
    src.set_mtime(NOW + 100.0)          # success: file rewritten
    sch.scan(now=NOW + 1000.0)
    assert "x" not in sch._backoff
    assert "x" not in sch._last_task


def test_reconcile_mtime_advanced_but_unrebuilt_escalates(tmp_path, monkeypatch):
    """2026-10-14 demo 五源自增强环刹车:mtime 前进(下载成功)但
    needs_rebuild 仍 True(rebuild 被 memory valve 卡住/ptr 纪元冻结)
    → 升退避而非清退避(归成功会失去唯一刹车 → 每 30min 全量重抓);
    record_event 照记(内容真实落地)。ptr 推进后走 else 清退避(见
    test_reconcile_success_clears_fail_count 钉住)。"""
    src = _make_src("freeze", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src], needs_rebuild=lambda s: True)
    sch.scan(now=NOW)                           # enqueues t0
    mgr._states[sch._last_task["freeze"]] = "done"
    src.set_mtime(NOW + 100.0)                  # 下载落地,mtime 前进
    recorded = []
    from ipdb import _alerts
    monkeypatch.setattr(
        _alerts, "record_event",
        lambda name, at=None, **k: recorded.append((name, at)))
    sch.scan(now=NOW + 1000.0)                  # reconcile: mtime 前进但 ptr 冻结
    b = sch._backoff["freeze"]
    assert b.fail_count == 1
    assert b.next_attempt == NOW + 1000.0 + 3600    # 首级 1h
    # 事件不丢:内容变化被确认(record_count 取当前 health)
    assert ("freeze", NOW + 1000.0) in recorded
    # backoff 未到期:needs_rebuild 立即路径也被压着,不重拉
    sch.scan(now=NOW + 2000.0)
    assert mgr.enqueued == ["freeze"]


def test_scan_needs_rebuild_lane_is_rebuild_only(tmp_path):
    """T3(2026-10-14 收敛批):needs_rebuild 车道 enqueue 传 rebuild_only=
    True(已下载的不重复下载);partial_failure 车道(死 feed 要重抓)与
    slot 车道(新内容要抓)不传。三车道同扫对照。"""
    rb = _make_src("rb", tmp_path, mtime=NOW)          # fresh:仅 needs_rebuild 触发
    slot = _make_src("slot_src", tmp_path, mtime=OLD)  # slot 到期,无 needs_rebuild
    pf = _make_partial_src("pf", tmp_path)
    pf.last_partial_failure = ["dead_feed"]
    sch, mgr = _make_scheduler(
        [rb, slot, pf], needs_rebuild=lambda s: s.name == "rb")
    sch.scan(now=NOW)
    assert mgr.enqueued == ["rb", "slot_src", "pf"]    # 三车道全触发
    assert dict(zip(mgr.enqueued, mgr.lanes)) == {
        "rb": True, "slot_src": False, "pf": False}


def test_rebuild_only_task_skips_download_when_raw_exists(tmp_path):
    """T3:rebuild-only 任务 raw 在 → download 不被调用,rebuild 照跑至 done
    (状态直达 loading);raw 缺失 → 回退全量(download 照调)。"""
    class RawBackedSource:
        def __init__(self, name, path, exists=True):
            self.name = name
            self.download_host = None
            self._path = path
            self.download_calls = 0
            self.rebuild_calls = 0
            if exists:
                path.write_text("x")

        def download(self, token=None):
            self.download_calls += 1

        def rebuild(self):
            self.rebuild_calls += 1

    def _wait_terminal(mgr, task):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline \
                and mgr.task_state(task.id) not in ("done", "failed", "cancelled"):
            time.sleep(0.02)
        return mgr.task_state(task.id)

    src = RawBackedSource("geo", tmp_path / "geo.csv")
    mgr, _ = _make_manager([src])
    task = mgr.enqueue_one_detached("geo", rebuild_only=True)
    assert _wait_terminal(mgr, task) == "done"
    assert src.download_calls == 0          # 车道核心:没下载
    assert src.rebuild_calls == 1

    src2 = RawBackedSource("geo2", tmp_path / "geo2.csv", exists=False)
    mgr2, _ = _make_manager([src2])
    task2 = mgr2.enqueue_one_detached("geo2", rebuild_only=True)
    assert _wait_terminal(mgr2, task2) == "done"
    assert src2.download_calls == 1         # raw 缺失回退全量
    assert src2.rebuild_calls == 1


def test_reconcile_rebuild_only_done_converged_clears_backoff(
        tmp_path, monkeypatch):
    """T3:rebuild-only done + mtime 不变(预期,没下载)+ needs_rebuild 翻
    False → 成功处理:清退避清任务,不记内容事件(事件在下载轮已记)。"""
    from ipdb import _alerts
    monkeypatch.setattr(_alerts, "event_count", lambda name: 1)  # 抑制种子事件
    recorded = []
    monkeypatch.setattr(_alerts, "record_event",
                        lambda name, at=None, **k: recorded.append((name, at)))
    needs = {"flag": True}
    src = _make_src("rb2", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src], needs_rebuild=lambda s: needs["flag"])
    sch.scan(now=NOW)                            # needs_rebuild 车道 → rebuild_only
    assert mgr.lanes == [True]
    mgr._states[sch._last_task["rb2"]] = "done"  # 重建完成,mtime 不变
    needs["flag"] = False                         # ptr 已推进 → 收敛
    sch.scan(now=NOW + 1000.0)
    assert "rb2" not in sch._backoff              # 成功:退避清
    assert "rb2" not in sch._last_task
    assert recorded == []                         # 不记内容事件


def test_reconcile_rebuild_only_done_still_stale_escalates(tmp_path, caplog):
    """T3:rebuild-only done 但 needs_rebuild 仍 True(另一族被 valve 卡住
    仍冻)→ 升退避梯(与 mtime-advanced 分支同刹车),且不再触发
    "theoretically unreachable"告警分支。"""
    import logging
    src = _make_src("rb3", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src], needs_rebuild=lambda s: True)
    sch.scan(now=NOW)
    mgr._states[sch._last_task["rb3"]] = "done"
    with caplog.at_level(logging.WARNING):
        sch.scan(now=NOW + 1000.0)
    b = sch._backoff["rb3"]
    assert b.fail_count == 1
    assert b.next_attempt == NOW + 1000.0 + 3600   # 首级 1h
    assert not any("unreachable" in r.message.lower() for r in caplog.records)



def test_scan_lmdb_backed_false_exempt_from_rebuild(tmp_path):
    """2026-10-14 幻影环修:设计上无 LMDB 的源(lmdb_backed=False,如
    caida_asorg)ptr 永不存在 ≠ 需重建 → fresh raw + ptr 缺失不 enqueue;
    同形源未标(默认 True)仍走 needs_rebuild 立即路径(对照组)。"""
    from ipdb._registry import _needs_rebuild_of
    src = _make_src("phantom", tmp_path, mtime=NOW)   # fresh raw, ptr 缺失
    assert not src._mmdb_path.exists()
    sch, mgr = _make_scheduler([src], needs_rebuild=_needs_rebuild_of)
    sch.scan(now=NOW)
    assert mgr.enqueued == ["phantom"]                # 对照:默认豁免前必抓
    src2 = _make_src("caida_phantom", tmp_path, mtime=NOW)
    src2.lmdb_backed = False
    assert _needs_rebuild_of(src2) is False
    sch2, mgr2 = _make_scheduler([src2], needs_rebuild=_needs_rebuild_of)
    sch2.scan(now=NOW)
    assert mgr2.enqueued == []                        # 豁免:不再幻影重抓


def test_caida_asorg_exempt_from_phantom_rebuild(tmp_path):
    """生产钉子:真实 caida_asorg(rebuild=load,文件即持久层)必须豁免
    needs_rebuild —— raw 在而 ptr 缺失(基类无条件设 _mmdb_path 的默认)
    不得触发重建入队。"""
    from ipdb._registry import _needs_rebuild_of
    from ipdb._sources.caida_asorg import CaidaAsorgSource
    src = CaidaAsorgSource(tmp_path)
    (tmp_path / src.filename).write_text("x")   # raw 存在(ptr 家族永不存在)
    assert src.lmdb_backed is False
    assert _needs_rebuild_of(src) is False


class PartialFeedSource(SchedFakeSource):
    """cloud_ranges 形源:download 部分容忍,失败家记在
    last_partial_failure(scheduler 的 done-但-部分失败信号,spec §2.3)。"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.last_partial_failure: list = []


def _make_partial_src(name, tmp_path, mtime=None):
    p = tmp_path / f"fake_{name}"
    p.write_text("x")
    # stale_days=7(周级,cloud_ranges 同款):默认 mtime = 8 天前 → 已过
    # 周级 deadline,首扫即 due(与日级用例的 OLD=1 天前同理)。
    if mtime is None:
        mtime = NOW - 8 * 86400
    return PartialFeedSource(name, path=p, stale_days=7, mtime=mtime)


def test_reconcile_partial_failure_backoff_not_stale_days(tmp_path):
    """终审 Important#1:部分容忍下 download 整体 done、目录 mtime 前进
    (四家成一家挂),旧槽位判定只看新鲜 mtime → 下次重试 = +stale_days
    (+7d),坏死家永不自愈。修复:done-但-部分失败(last_partial_failure
    非空)→ 走 _BACKOFF_SECONDS 封顶 backoff(≤12h),自愈前持续重试。"""
    src = _make_partial_src("cloud_ranges", tmp_path)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                          # enqueues t0
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    src.set_mtime(NOW + 100.0)                 # 成功落地的四家推进目录 mtime
    src.last_partial_failure = ["Azure"]       # …但 Azure 挂了
    sch.scan(now=NOW + 1000.0)                 # reconcile: done + mtime 前进
    b = sch._backoff["cloud_ranges"]
    assert b.fail_count == 1
    assert b.next_attempt == NOW + 1000.0 + 3600    # 首级 1h
    # 核心断言:下次重试间隔 ≤ backoff 封顶(12h),而非 stale_days 的 7 天
    assert b.next_attempt - (NOW + 1000.0) <= 43200 < 7 * 86400
    # backoff 未到期:mtime 全新也压着不重试(防 30 分钟全源重拉风暴)
    sch.scan(now=NOW + 2000.0)
    assert mgr.enqueued == ["cloud_ranges"]
    # 到期即重试:部分失败信号短路槽位判定,不等 mtime + 7d
    sch.scan(now=NOW + 4601.0)
    assert mgr.enqueued == ["cloud_ranges", "cloud_ranges"]
    # 再次部分失败 → 逐级爬梯 2h
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    src.set_mtime(NOW + 4700.0)
    sch.scan(now=NOW + 4800.0)
    assert sch._backoff["cloud_ranges"].fail_count == 2
    assert sch._backoff["cloud_ranges"].next_attempt == NOW + 4800.0 + 7200


def test_partial_failure_backoff_caps_at_12h(tmp_path):
    """持续部分失败的重试间隔封顶 _BACKOFF_SECONDS 末位 12h:既不无限
    放大,也不退化成每扫描周期的全源重拉。"""
    src = _make_partial_src("cloud_ranges", tmp_path)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    src.set_mtime(NOW + 100.0)
    src.last_partial_failure = ["Azure"]
    from ipdb._scheduler import _Backoff
    sch._backoff["cloud_ranges"] = _Backoff(
        fail_count=5, next_attempt=0.0, kind="download")  # 已在梯子末级(同 kind)
    sch.scan(now=NOW + 1000.0)
    b = sch._backoff["cloud_ranges"]
    assert b.fail_count == 6
    assert b.next_attempt == NOW + 1000.0 + 43200   # 封顶 12h


def test_partial_failure_healed_resumes_stale_days_rhythm(tmp_path):
    """全绿自愈:Azure 恢复(last_partial_failure 清空)→ backoff 消除,
    新 mtime 重新按槽位节奏(stale_days 内不再重试,正常节奏不变)。"""
    src = _make_partial_src("cloud_ranges", tmp_path)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                          # 首次入队
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    src.set_mtime(NOW + 100.0)
    src.last_partial_failure = ["Azure"]
    sch.scan(now=NOW + 1000.0)
    assert "cloud_ranges" in sch._backoff        # 部分失败被记入梯子
    # backoff 到期后的重试:此刻 last_partial_failure 仍是上一轮的
    # ["Azure"](它只在下一轮 download 结束时被覆写)→ 部分失败信号仍短路
    # 槽位判定,重试得以入队
    sch.scan(now=NOW + 4601.0)
    assert mgr.enqueued == ["cloud_ranges", "cloud_ranges"]
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    src.set_mtime(NOW + 5000.0)                 # 五家全落地
    src.last_partial_failure = []               # 本轮 download 结束时落账:全绿
    sch.scan(now=NOW + 5200.0)
    assert "cloud_ranges" not in sch._backoff    # 梯子清空 = 自愈完成
    assert "cloud_ranges" not in sch._last_task
    # 正常节奏恢复:mtime 全新、无部分失败 → stale_days 内不再入队
    for t in (NOW + 5200.0 + 43200, NOW + 5200.0 + 3 * 86400):
        sch.scan(now=t)
    assert mgr.enqueued == ["cloud_ranges", "cloud_ranges"]


def test_reconcile_real_failure_increments_backoff(tmp_path):
    """mtime unchanged + task_state 'failed' -> fail_count++, next_attempt set."""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                   # enqueues t0
    mgr._states[sch._last_task["x"]] = "failed"
    sch.scan(now=NOW + 1000.0)          # reconcile t0 as failed
    assert sch._backoff["x"].fail_count == 1
    assert sch._backoff["x"].next_attempt == NOW + 1000.0 + 3600
    sch.scan(now=NOW + 2000.0)          # still backing off -> no re-enqueue
    assert mgr.enqueued == ["x"]
    sch.scan(now=NOW + 5000.0)          # past next_attempt -> re-enqueue
    assert mgr.enqueued == ["x", "x"]
    mgr._states[sch._last_task["x"]] = "failed"
    sch.scan(now=NOW + 6000.0)          # second failure -> 2h backoff
    assert sch._backoff["x"].fail_count == 2
    assert sch._backoff["x"].next_attempt == NOW + 6000.0 + 7200
    assert sch._backoff["x"].kind_count == 2     # 同 kind(""):逐 kind 计数照爬


# ── 失败分类计梯(2026-10-17 用户裁定:告警分报下载/构建失败)──

def test_reconcile_kind_partial_feeds_are_download(tmp_path):
    """kind 传递:partial feed 失败(下载相位挂了部分家)→ kind=download。
    mtime 前进 + partial 与 done + partial(mtime 不变)两分支同 kind。"""
    src = _make_partial_src("cloud_ranges", tmp_path)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                          # enqueues t0
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    src.set_mtime(NOW + 100.0)                 # 四家落地推进目录 mtime
    src.last_partial_failure = ["Azure"]       # …但 Azure 挂了
    sch.scan(now=NOW + 1000.0)                 # reconcile: mtime 前进 + partial
    assert sch._backoff["cloud_ranges"].kind == "download"
    # 下一轮 done + partial(mtime 不变):同 kind 续爬 2h
    sch.scan(now=NOW + 4601.0)                 # 过 1h 重试入队
    mgr._states[sch._last_task["cloud_ranges"]] = "done"
    sch.scan(now=NOW + 4800.0)
    b = sch._backoff["cloud_ranges"]
    assert b.kind == "download"
    assert b.fail_count == 2
    assert b.kind_count == 2                     # 同 kind:双计数同步爬
    assert b.next_attempt == NOW + 4800.0 + 7200


def test_reconcile_kind_ptr_frozen_is_rebuild(tmp_path, monkeypatch):
    """kind 传递:ptr 冻结(mtime 前进但 needs_rebuild 仍 True,构建未成)
    → kind=rebuild;rebuild-only 车道 done 仍冻同 kind。"""
    from ipdb import _alerts
    monkeypatch.setattr(_alerts, "record_event", lambda *a, **k: None)
    src = _make_src("freeze", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src], needs_rebuild=lambda s: True)
    sch.scan(now=NOW)
    mgr._states[sch._last_task["freeze"]] = "done"
    src.set_mtime(NOW + 100.0)                 # 下载落地,ptr 冻结
    sch.scan(now=NOW + 1000.0)
    assert sch._backoff["freeze"].kind == "rebuild"

    rb = _make_src("rb3", tmp_path, mtime=OLD)  # rebuild-only 车道对照
    sch2, mgr2 = _make_scheduler([rb], needs_rebuild=lambda s: True)
    sch2.scan(now=NOW)
    assert mgr2.lanes == [True]                # needs_rebuild 立即车道
    mgr2._states[sch2._last_task["rb3"]] = "done"   # mtime 不变是预期
    sch2.scan(now=NOW + 1000.0)
    assert sch2._backoff["rb3"].kind == "rebuild"


def test_reconcile_kind_failed_task_takes_manager_value(tmp_path):
    """kind 传递:state==failed → kind 取 manager.task_failure_kind 的
    返回值(真任务的 error_code 分类码)。"""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    tid = sch._last_task["x"]
    mgr._states[tid] = "failed"
    mgr._kinds[tid] = "download"
    sch.scan(now=NOW + 1000.0)
    assert sch._backoff["x"].kind == "download"


def test_kind_switch_dual_counters(tmp_path):
    """双计数(2026-10-17 裁定修):kind 切换 → fail_count(任意类连败总数)
    **不**重置——≥3 告警/恢复判定/退避计时梯全由总数驱动(kind 中途切换
    ≠ 成功,不得下假「已恢复」);kind_count 重归 1,只驱动文案 ×N。"""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)                           # 第 1 次 download 失败
    mgr._states[sch._last_task["x"]] = "failed"
    mgr._kinds[sch._last_task["x"]] = "download"
    sch.scan(now=NOW + 1000.0)
    b = sch._backoff["x"]
    assert (b.fail_count, b.kind, b.kind_count) == (1, "download", 1)
    sch.scan(now=NOW + 5000.0)                  # 过 1h 重试
    mgr._states[sch._last_task["x"]] = "failed"
    mgr._kinds[sch._last_task["x"]] = "download"
    sch.scan(now=NOW + 6000.0)                  # 同 kind 续爬 2h
    b = sch._backoff["x"]
    assert (b.fail_count, b.kind_count) == (2, 2)
    assert b.next_attempt == NOW + 6000.0 + 7200
    sch.scan(now=NOW + 20000.0)                 # 过 2h 重试
    mgr._states[sch._last_task["x"]] = "failed"
    mgr._kinds[sch._last_task["x"]] = "rebuild"  # 第 3 次换 kind
    sch.scan(now=NOW + 21000.0)
    b = sch._backoff["x"]
    assert b.fail_count == 3                    # 总数不重置(切换 ≠ 成功)
    assert b.kind == "rebuild"
    assert b.kind_count == 1                    # 逐 kind 计数重归 1
    # 计时梯跟总数走:第 3 级 4h(若误按 kind_count 落梯会回首级 1h)
    assert b.next_attempt == NOW + 21000.0 + 14400


def test_reconcile_throttled_not_a_failure(tmp_path):
    """H1 fix: non-terminal task_state (throttled) -> no fail_count increment."""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    mgr._states[sch._last_task["x"]] = "throttled"
    sch.scan(now=NOW + 1000.0)
    assert sch._backoff.get("x") is None
    assert "x" in sch._last_task       # retained for next reconcile


def test_reconcile_cancelled_not_a_failure(tmp_path):
    """cancelled task_state -> fail_count untouched, last_task cleared."""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    mgr._states[sch._last_task["x"]] = "cancelled"
    sch.scan(now=NOW + 1000.0)
    assert "x" not in sch._backoff
    assert "x" not in sch._last_task


def test_reconcile_done_unreachable_warns_and_clears(tmp_path, caplog):
    """done + mtime unchanged (unreachable) -> warn, clear last_task, no backoff."""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    mgr._states[sch._last_task["x"]] = "done"
    import logging
    with caplog.at_level(logging.WARNING):
        sch.scan(now=NOW + 1000.0)
    assert "x" not in sch._backoff
    assert "x" not in sch._last_task
    assert any("unreachable" in r.message.lower() or "done" in r.message.lower()
               for r in caplog.records)


def test_reconcile_unknown_task_id_no_failure(tmp_path):
    """task_state None (evicted) -> fail_count untouched, last_task cleared."""
    src = _make_src("x", tmp_path, mtime=OLD)
    sch, mgr = _make_scheduler([src])
    sch.scan(now=NOW)
    del mgr._states[sch._last_task["x"]]   # simulate eviction
    sch.scan(now=NOW + 1000.0)
    assert "x" not in sch._backoff
    assert "x" not in sch._last_task


def test_scan_exception_isolation(tmp_path, caplog):
    """A source whose stale_days read raises does not stop other sources."""
    class BadSource(SchedFakeSource):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            del self.stale_days      # scan's read raises AttributeError

    bad = BadSource("bad", path=tmp_path / "fake_bad")
    (tmp_path / "fake_bad").write_text("x")
    sch, mgr = _make_scheduler([
        bad,
        _make_src("good", tmp_path, mtime=OLD),
    ])
    import logging
    with caplog.at_level(logging.ERROR):
        sch.scan(now=NOW)            # must not raise
    assert mgr.enqueued == ["good"]


def test_shutdown_stops_thread(tmp_path):
    """start() returns shortly after stop_event.set(), using a tiny interval."""
    import threading
    sch, mgr = _make_scheduler([_make_src("x", tmp_path, is_stale=False)], interval=0.05)
    stop = threading.Event()
    t = threading.Thread(target=sch.start, args=(stop,))
    t.start()
    stop.set()
    t.join(timeout=5.0)
    assert not t.is_alive(), "scheduler thread did not shut down"


def test_slot_of_deterministic_and_in_range():
    from ipdb._scheduler import _slot_of
    assert _slot_of("abuseipdb") == _slot_of("abuseipdb")
    for n in ("abuseipdb", "firehol", "geolite_city", "x"):
        s = _slot_of(n)
        assert isinstance(s, int) and 0 <= s < 43200


def test_slot_spread_across_real_sources():
    """Real source names hash to (near-)distinct slots spread over the grid."""
    from ipdb._scheduler import _slot_of
    names = ["abuseipdb", "firehol", "spamhaus", "threatfox", "tor_exits",
             "greensnow", "binarydefense", "tweetfeed", "blocklist_de",
             "emerging_threats", "stopforumspam", "f3csystems", "reportedip",
             "geolite_city", "ipinfo_lite", "infra_services"]
    slots = [_slot_of(n) for n in names]
    assert len(set(slots)) >= len(names) - 2      # collisions rare, tolerate 2
    assert max(slots) - min(slots) > 43200 // 2   # not crammed into one tail


def test_period_of_tiers():
    from ipdb._scheduler import _period_of
    assert _period_of(1) == 43200        # daily tier → 12h (twice a day)
    assert _period_of(7) == 604800       # weekly tier → 7d


def test_due_at_daily_rhythm_stable():
    """F1 regression: guard keeps consecutive fires exactly 12h apart."""
    from ipdb._scheduler import _due_at, _slot_of, SLOT_GRID
    name = "abuseipdb"
    slot = _slot_of(name)
    fire1 = 10 * SLOT_GRID + slot          # a slot boundary firing
    delta = 1800.0                         # scan+download lag < guard
    fire2 = _due_at(name, fire1 + delta, 1)
    assert fire2 - fire1 == SLOT_GRID      # same slot point, +12h
    fire3 = _due_at(name, fire2 + delta, 1)
    assert fire3 - fire2 == SLOT_GRID      # no drift on cycle 2


def test_due_at_weekly_rhythm_stable():
    """F1 regression: weekly fires exactly 7d apart, not 7.5d."""
    from ipdb._scheduler import _due_at, _slot_of, SLOT_GRID
    name = "geolite_city"
    slot = _slot_of(name)
    fire1 = 10 * SLOT_GRID + slot
    fire2 = _due_at(name, fire1 + 1800.0, 7)
    assert fire2 - fire1 == 604800
    fire3 = _due_at(name, fire2 + 1800.0, 7)
    assert fire3 - fire2 == 604800


def test_due_at_slow_download_skips_then_recovers():
    """Lag > guard misses the next slot (that day: 1 refresh), then recovers."""
    from ipdb._scheduler import _due_at, _slot_of, SLOT_GRID
    name = "abuseipdb"
    slot = _slot_of(name)
    fire1 = 10 * SLOT_GRID + slot
    fire2 = _due_at(name, fire1 + 5000.0, 1)   # 5000s lag > 3600s guard
    assert fire2 - fire1 == 2 * SLOT_GRID      # skipped one slot
    fire3 = _due_at(name, fire2 + 1800.0, 1)
    assert fire3 - fire2 == SLOT_GRID          # recovered


def test_due_at_lands_on_own_slot_after_deadline():
    from ipdb._scheduler import _due_at, _slot_of, SLOT_GRID, REFRESH_GUARD
    name = "spamhaus"
    slot = _slot_of(name)
    mtime = 10 * SLOT_GRID                      # just after a slot point
    due = _due_at(name, mtime, 1)
    deadline = mtime + SLOT_GRID - REFRESH_GUARD
    assert due > deadline and due <= deadline + SLOT_GRID
    assert (due - 10 * SLOT_GRID) % SLOT_GRID == slot   # lands on its own slot


def test_dbip_refresh_period_cannot_skip_monthly_edition():
    """2026-09 事故:dbip 上游按月出版版本化 URL,刷新周期(stale_days)≥ 28 天时,
    月末边界触发的刷新会把上个月文件再锁一整个周期,下一期月版被整期跳过
    (9 月版从未入库)。不变量:周期 < 最短月长 28 天 ⇒ 相邻两次刷新必然
    横跨任何一期的存活窗口,任何月版都不会被跳过。"""
    from ipdb._scheduler import _period_of
    from ipdb._sources.dbip_city import DbIpCitySource
    assert _period_of(DbIpCitySource.stale_days) < 28 * 86400

