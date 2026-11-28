"""Concurrency regression tests for the coordinated queue/lock-protocol redesign
(#1 cancel race, #2 enqueue_batch early-done, #3 FIFO head-block). Each test
deterministically reproduces the bug against the pre-redesign code and locks
the fixed invariant. See the 9-finding code review (2026-08-12)."""
import threading
import time

from ipdb import _task_state
from ipdb._tasks import UpdateManager


class _Src:
    """Minimal source matching the worker's contract:
    name, download_host, download(token), rebuild()."""
    def __init__(self, name, host="h", slow=0.0):
        self.name = name
        self.download_host = host
        self._slow = slow
        self.download_calls = 0
        self.rebuild_calls = 0
    def download(self, token=None):
        self.download_calls += 1
        time.sleep(self._slow)
    def rebuild(self):
        self.rebuild_calls += 1


def _mgr(sources, concurrency=3, valve=None):
    by_name = {s.name: s for s in sources}
    locks = {}
    m = UpdateManager(
        resolve_source=lambda n: by_name.get(n),
        lock_for=lambda n: locks.setdefault(n, threading.Lock()),
        concurrency=concurrency,
        valve=valve,
    )
    return m, by_name


def _wait(mgr, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ── #3 FIFO head-block ──────────────────────────────────────────────────────

class _AdmitSecondValve:
    """Valve that rejects the very first can_run check and admits everything
    after — deterministically puts the queue head into 'throttled'
    (head-of-line scenario)."""
    def __init__(self):
        self.active_rebuilds = 0
        self._blocked_once = False
    def can_run(self):
        if not self._blocked_once:
            self._blocked_once = True
            return False
        return True
    def on_start(self):
        self.active_rebuilds += 1
    def on_finish(self):
        self.active_rebuilds -= 1


def test_fifo_head_block_does_not_starve_next_task():
    """#3: a throttled task at queue[0] must NOT block tasks queued behind it.
    Pre-redesign, workers peek queue[0], see can_run=False, wait+cont without
    popping — so queue[1..N] tasks never reach any worker, defeating
    concurrency. After redesign (scan queue for an admissible task), the
    second task runs even while the head is throttled."""
    head = _Src("head")
    follower = _Src("follower", host="n")
    mgr, by_name = _mgr([head, follower], concurrency=2, valve=_AdmitSecondValve())
    mgr.enqueue_one("head")        # queue[0] = head (rejected on first check)
    mgr.enqueue_one("follower")    # queue[1] = follower (admissible)
    # The follower must run despite the head being throttled.
    ran = _wait(mgr, lambda: by_name["follower"].download_calls >= 1, timeout=3)
    # cleanup: nothing to drain (head never starts; follower is instant)
    assert ran, (
        "follower starved behind throttled head — FIFO head-block bug. "
        f"follower.download_calls={by_name['follower'].download_calls}"
    )


# ── #2 enqueue_batch early-done ─────────────────────────────────────────────

def test_enqueue_batch_no_task_orphaned_and_done_equals_total():
    """#2 invariant: every task created by enqueue_batch must carry the batch id
    and batch.done must equal batch.total. The bug (outside-lock enqueue loop +
    fast-first source nulling _active_batch mid-loop) orphans later tasks
    (batch_id=None) and leaves done < total. This locks the redesigned
    invariant. NOTE: the underlying race is timing-dependent; this test asserts
    the invariant the redesign guarantees rather than deterministically
    reproducing the race window (see #3 test for a deterministic RED)."""
    fast = _Src("fast", host="f1")
    followers = [_Src(f"s{i}", host=f"h{i}") for i in range(6)]
    mgr, by_name = _mgr([fast] + followers, concurrency=1)
    names = [s.name for s in [fast] + followers]
    bid = mgr.enqueue_batch(names)
    _wait(mgr, lambda: mgr._batches[bid].state == "done", timeout=5)
    b = mgr._batches[bid]
    orphans = [t for t in mgr._tasks.values()
               if t.source_name in set(names) and t.batch_id != bid]
    assert not orphans, f"{len(orphans)} tasks orphaned (batch_id != {bid}): {orphans}"
    assert b.done == b.total, f"done={b.done} < total={b.total}"


# ── #1 cancel race ──────────────────────────────────────────────────────────

def test_cancel_queued_task_does_not_run_and_does_not_overshoot_batch_done():
    """#1: cancel a task while it is still QUEUED (behind a worker-holding
    blocker, concurrency=1). This is the path finding #1 describes: cancel()'s
    _settle must not double-increment batch.done against _run_task's _settle if
    the worker races the cancel and runs the task anyway.

    Two invariants:
      (a) the cancelled queued task must NEVER run (download_calls == 0);
      (b) batch.done must never exceed batch.total (the double-settle symptom).

    Deterministic RED on pre-fix code: _settle had no idempotency guard, so
    cancel's settle + _run_task's settle both incremented b.done. The idempotent
    _settled flag (post-fix) closes it for every path."""
    release = threading.Event()
    blocker = _Src("blocker", host="hb")

    def hold(token=None):
        blocker.download_calls += 1
        release.wait(3)              # occupy the single worker
    blocker.download = hold
    victim = _Src("victim", host="hv")
    mgr, by_name = _mgr([blocker, victim], concurrency=1)
    bid = mgr.enqueue_batch(["blocker", "victim"])   # blocker runs, victim queued
    # let the blocker claim the worker
    _wait(mgr, lambda: by_name["blocker"].download_calls >= 1, timeout=2)
    victim_task = [t for t in mgr._tasks.values() if t.source_name == "victim"][0]
    assert victim_task.state == "queued", victim_task.state
    mgr.cancel(victim_task.id)       # cancel while QUEUED — the #1 path
    release.set()                    # let the blocker finish
    _wait(mgr, lambda: all(t.state in ("done", "failed", "cancelled")
                           for t in mgr._tasks.values()), timeout=3)
    b = mgr._batches[bid]
    assert by_name["victim"].download_calls == 0, "cancelled queued task ran anyway"
    assert b.done <= b.total, (
        f"batch.done={b.done} > total={b.total} — cancel/_run_task double-settled"
    )


# ── #488 cancel vs. start race (the wide window of #1) ─────────────────────

def _cancel_before_start_scenario():
    """搭起「victim 出队后卡在 _run_task 开头主机锁上时被取消」的场景并跑完
    (放行 blocker、两任务终态、两个 worker 都走出 _run_task),返回
    (mgr, by_name, victim_task, events)。严格/记录两模式的孪生用例共用。"""
    release = threading.Event()
    blocker = _Src("blocker", host="h488")

    def hold(token=None):
        blocker.download_calls += 1
        release.wait(3)              # 占住主机锁,把 victim 挡在起跑前
    blocker.download = hold
    victim = _Src("victim", host="h488")
    mgr, by_name = _mgr([blocker, victim], concurrency=2)
    victim_popped = threading.Event()
    locks: dict = {}

    def lock_for(n):
        # _run_task 取主机锁前调 lock_for(_enqueue_one 不调)——它在
        # victim 上被调 = victim 已出队、即将阻塞在主机锁上。
        if n == "victim":
            victim_popped.set()
        return locks.setdefault(n, threading.Lock())

    mgr._lock_for = lock_for
    events = []
    mgr._emit = events.append        # 从入队前起记录,拿全任务状态事件流
    mgr.enqueue_one("blocker")
    assert _wait(mgr, lambda: by_name["blocker"].download_calls >= 1, timeout=2), \
        "blocker 未进入 download(主机锁未被占住),前置条件不成立"
    mgr.enqueue_one("victim")
    assert victim_popped.wait(3), "victim 未出队(未进 _run_task)"
    victim_task = [t for t in mgr._tasks.values() if t.source_name == "victim"][0]
    assert victim_task.state == "queued", victim_task.state  # 卡在锁上,未翻相位
    mgr.cancel(victim_task.id)
    assert mgr.task_state(victim_task.id) == "cancelled"
    release.set()                    # 放行 blocker,让 victim 的 worker 拿到锁
    assert _wait(mgr, lambda: all(
        mgr.task_state(t.id) in ("done", "failed", "cancelled")
        for t in mgr._tasks.values()), timeout=3)
    # 同步点(#488 评审建议改 1,2026-11-28):上面的「全终态」在取消那一刻
    # 就只剩 blocker 没跑完,不保证 victim 的 worker 已从主机锁上醒来走完
    # _run_task——victim 取消时就已经是终态。两个 worker 都在 _run_task 的
    # finally 里才释放主机锁,测试线程此刻能拿到锁 = 两 worker 都走完,之后
    # 读事件流/断言不受调度时序影响(变异①的红由此钉在用例自己的断言上,
    # 记录模式孪生用例尤其依赖这一步,否则会偶发假绿)。
    hl = mgr._host_lock("h488")
    assert hl.acquire(timeout=3), "worker 未在 3s 内释放主机锁"
    hl.release()
    return mgr, by_name, victim_task, events


def _assert_victim_stays_cancelled(mgr, by_name, victim_task, events):
    """两条孪生用例共用的断言:事件流恰为 queued→cancelled(不得出现
    downloading/loading/failed),victim 没跑下载。"""
    victim_states = [e["task"]["state"] for e in events
                     if e.get("type") == "task" and e["task"]["id"] == victim_task.id]
    assert victim_states == ["queued", "cancelled"], \
        f"取消后状态被翻回在飞: {victim_states}"
    assert by_name["victim"].download_calls == 0, \
        "已取消的任务在起跑窗口之后照样跑了下载"


def test_cancel_of_task_blocked_before_start_never_flips_in_flight():
    """#488:取消一个「已出队、卡在 _run_task 开头主机锁上」的任务,状态必须
    停在 cancelled,事件流里不得出现过 downloading/loading/failed。

    确定性复现:两个源同 download_host → 共享主机锁;blocker 先起跑、在
    download 里阻塞事件;victim 出队(以 lock_for("victim") 被调为界——
    _run_task 在取主机锁前最后一站)后必阻塞在主机锁上,状态仍是 queued。
    此时取消,再放行 blocker:pre-fix worker 拿到锁照样翻 downloading(本
    用例红);post-fix 起跑前查 token 直接返回(finally 收尾幂等)。
    断言走任务状态事件流(转移序列),不只看终态;严格模式(测试缺省)。"""
    mgr, by_name, victim_task, events = _cancel_before_start_scenario()
    _assert_victim_stays_cancelled(mgr, by_name, victim_task, events)


def test_cancel_of_task_blocked_before_start_record_mode_never_flips(monkeypatch):
    """记录模式(生产形态)孪生用例(#488 评审建议改 1):全套件 autouse 的
    严格模式在这里翻回 False,验证生产形态下取消也不被翻回在飞。变异①
    (去掉 _run_task 起跑前的提前返回)在这条上红在用例自己的断言(取消后
    状态被翻回在飞 / 已取消的任务照样跑了下载),不靠线程异常夹具「碰上」。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    mgr, by_name, victim_task, events = _cancel_before_start_scenario()
    _assert_victim_stays_cancelled(mgr, by_name, victim_task, events)


# ── pause/abort without active batch (batchless single-source updates) ──────

def test_pause_without_active_batch_does_not_wedge_workers():
    """pause() 在无 active batch(batchless 单源更新在飞)时不得清 _go:
    否则 worker 全体 cv-wait,新任务永远 queued,且无任何 batch 事件可
    供前端渲染 Resume — 永久卡死,只能重启后端恢复。"""
    src = _Src("solo")
    mgr, by_name = _mgr([src], concurrency=1)
    mgr.pause()                                  # batchless 状态下 pause
    mgr.enqueue_one("solo")
    ran = _wait(mgr, lambda: by_name["solo"].rebuild_calls >= 1, timeout=3)
    assert ran, "pause() without an active batch must not block workers"


def test_cancel_batch_none_without_active_batch_cancels_batchless_task():
    """cancel_batch(None) 在无 active batch 时应清掉在飞的 batchless 任务
    (前端 Abort 按钮对单源更新是真实按钮,不是摆设)。"""
    src = _Src("slow", slow=2.0)
    mgr, by_name = _mgr([src], concurrency=1)
    task = mgr.enqueue_one("slow")
    started = _wait(mgr, lambda: by_name["slow"].download_calls >= 1, timeout=3)
    assert started
    mgr.cancel_batch(None)                       # 无 active batch 的 abort
    done = _wait(mgr, lambda: mgr.task_state(task.id) in
                 ("cancelled", "failed", "done"), timeout=3)
    assert done and mgr.task_state(task.id) != "done", \
        "batchless task must be cancelled, not run to completion"
