"""UpdateManager — unified trackable/abortable source-update task runner."""
import asyncio
import inspect
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ._sources._download import CancelledError, CancelToken

logger = logging.getLogger(__name__)


@dataclass
class Task:
    id: str
    source_name: str
    host: Optional[str]
    state: str = "queued"  # queued|downloading|loading|throttled|done|failed|cancelled
    error: Optional[str] = None
    # 失败终态的语义码:值域 = _errors ErrorCode 值 + 任务相位码
    # download/rebuild(2026-10-17 裁定);None=未失败。SSE/快照消费。
    error_code: Optional[str] = None
    batch_id: Optional[str] = None
    # 阶段内进度计数(事件/快照展示用):downloading=字节,loading=记录数。
    # 阶段切换由 _run_task 在 _set_state 之前清零(事件不得携带上一相位计数)。
    received: int = 0
    total: int = 0
    token: CancelToken = field(default_factory=CancelToken)
    # rebuild-only 车道(2026-10-14 收敛批):scheduler needs_rebuild 触发、
    # raw 已最新时跳过 download 直进 loading。刻意不入 to_dict:前端照旧
    # 显示 loading,无新契约。
    _rebuild_only: bool = False
    # Idempotency guard for _settle: a terminal task can be settled from two
    # places (cancel()'s _settle and _run_task's finally _settle) when cancel
    # races dispatch. Without this flag, both calls increment batch.done (#1).
    _settled: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source_name, "host": self.host,
                "state": self.state, "error": self.error,
                "error_code": self.error_code, "batch_id": self.batch_id,
                "received": self.received, "total": self.total}


@dataclass
class Batch:
    id: str
    state: str = "running"  # running|paused|done
    done: int = 0
    total: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "state": self.state, "done": self.done, "total": self.total}


class UpdateManager:
    def __init__(self, resolve_source: Callable, lock_for: Callable,
                 concurrency: int = 3,
                 queue_cap: int = 256, valve=None):
        self._resolve = resolve_source
        self._lock_for = lock_for
        self._concurrency = concurrency
        self._queue_cap = queue_cap
        self._valve = valve

        self._tasks: dict[str, Task] = {}
        self._by_source: dict[str, str] = {}      # source_name -> active task_id
        self._batches: dict[str, Batch] = {}
        self._active_batch: Optional[str] = None
        # Set while enqueue_batch is still populating the queue. Blocks
        # _maybe_finish_batch from nulling _active_batch mid-enqueue: without
        # it, a fast-first source can finish (via _settle) before the rest are
        # enqueued, orphaning later tasks (batch_id=None) and leaving the batch
        # done with done < total (#2 enqueue_batch early-done race).
        self._populating_batch: bool = False
        # Per-task download-progress throttle state: task_id -> (last_ts, last_pct).
        # Reset whenever a task (re-)enters the downloading phase.
        self._prog: dict[str, tuple[float, int]] = {}

        self._host_locks: dict[str, threading.Lock] = {}
        self._host_guard = threading.Lock()

        self._queue: deque[str] = deque()
        self._queue_cv = threading.Condition()

        self._go = threading.Event(); self._go.set()  # cleared => paused
        self._lock = threading.RLock()

        # event bus
        self._subs: set = set()
        self._subs_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        for _ in range(concurrency):
            threading.Thread(target=self._worker, daemon=True).start()

    # --- public ---
    def enqueue_one(self, name: str) -> Task:
        # _active_batch 必须在锁内读:锁外求值拿到 stale batch_id 会把任务
        # 挂上已完成 batch,后续 _settle 把 done 推过 total(3/2 · 150%)。
        with self._lock:
            return self._enqueue_one(name, self._active_batch)

    def enqueue_one_detached(self, name: str, rebuild_only: bool = False) -> Task:
        """Enqueue a task with batch_id=None, so scheduler-triggered refreshes
        are never absorbed into an in-flight manual batch (which would corrupt
        that batch's done/total via _settle). Shares dedup with enqueue_one:
        if the source already has an in-flight task, that task is returned
        unchanged — no new task, no new pollution.

        rebuild_only=True:needs_rebuild 车道专用(raw 已最新)——_run_task
        跳过 download 直进 loading;raw 缺失时 _run_task 自动回退全量。"""
        return self._enqueue_one(name, None, rebuild_only=rebuild_only)

    def _enqueue_one(self, name: str, batch_id: Optional[str],
                     rebuild_only: bool = False) -> Task:
        source = self._resolve(name)
        if source is None:
            raise ValueError(f"unknown source: {name}")
        with self._lock:
            existing = self._by_source.get(name)
            if existing and self._tasks[existing].state in ("queued", "downloading", "loading", "throttled"):
                return self._tasks[existing]
            # Evict the source's prior TERMINAL tasks (and their progress state)
            # before installing the new one, so _tasks/_prog stay O(sources)
            # instead of growing one entry per run forever (#5). _settle clears
            # _by_source on termination, so terminal tasks linger in _tasks with
            # no back-reference — sweep by source_name. A terminal task was
            # retained until now so snapshot()/task_state() could report the last
            # phase; once the source moves on it's stale.
            stale = [tid for tid, t in self._tasks.items()
                     if t.source_name == name and t.state in ("done", "failed", "cancelled")]
            for tid in stale:
                self._tasks.pop(tid, None)
                self._prog.pop(tid, None)
            task = Task(id=uuid.uuid4().hex[:12], source_name=name,
                        host=getattr(source, "download_host", None),
                        batch_id=batch_id, _rebuild_only=rebuild_only)
            self._tasks[task.id] = task
            self._by_source[name] = task.id
            # A task attaching to the active batch AFTER populate (re-enable
            # path: set_source_enabled → enqueue_one) must grow that batch's
            # total, or its later _settle increment pushes done past total and
            # can complete the batch while the straggler is still in flight.
            # During populate the post-loop re-stamp counts every attachment,
            # so skip to avoid double-counting.
            if (batch_id is not None and batch_id == self._active_batch
                    and not self._populating_batch):
                self._batches[batch_id].total += 1
            self._enqueue(task.id)
            self._emit({"type": "task", "task": task.to_dict()})
            return task

    def task_state(self, task_id: str) -> Optional[str]:
        """Lock-guarded lookup of a task's state. Returns None if task_id is
        unknown (evicted/garbage). The scheduler uses this during backoff
        reconciliation to distinguish terminal from non-terminal tasks."""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.state if task is not None else None

    def task_rebuild_only(self, task_id: str) -> bool:
        """Whether the task runs the rebuild-only lane (skip download). The
        scheduler's reconcile uses this: done-but-mtime-unchanged is EXPECTED
        for this lane (no download ran), not the "unreachable" warning case."""
        with self._lock:
            task = self._tasks.get(task_id)
            return task._rebuild_only if task is not None else False

    def task_failure_kind(self, task_id: str) -> Optional[str]:
        """失败任务的 error_code(2026-10-17 用户裁定:源监控告警须说清
        挂的是哪一环——下载失败就报下载失败,构建失败就报构建失败)。
        task 存在且 state=="failed" → 其 error_code("download"/"rebuild"
        等分类码;source_not_found 非下载/构建失败原样透传);否则 None。
        循 task_state/task_rebuild_only 惯例:锁内查,供 scheduler
        reconcile 分类计梯。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and task.state == "failed":
                return task.error_code
            return None

    def snapshot(self) -> dict:
        with self._lock:
            # _tasks accumulates terminal tasks across batches; iteration order
            # is insertion (oldest→newest), so the last task seen per source is
            # the current one. Collapse to one-per-source so a stale terminal
            # task can't mask a re-enqueued source's live phase.
            by_source: dict[str, "Task"] = {}
            for t in self._tasks.values():
                by_source[t.source_name] = t
            tasks = [t.to_dict() for t in by_source.values()]
            batch = self._batches[self._active_batch].to_dict() if self._active_batch else None
            return {"tasks": tasks, "batch": batch}

    # --- batch control (Task 4) / pause / cancel / bus: added in later tasks ---
    def enqueue_batch(self, source_names: list[str]) -> str:
        with self._lock:
            # Reject overlap: reuse the active batch if one is still running.
            if self._active_batch:
                return self._active_batch
            # Bounded retention: evict terminal batches beyond the 10 most recent.
            done = [bid for bid, b in self._batches.items() if b.state == "done"]
            for bid in done[:-10]:
                del self._batches[bid]
            batch = Batch(id=uuid.uuid4().hex[:12])
            self._batches[batch.id] = batch
            self._active_batch = batch.id
            names = [n for n in source_names
                     if self._resolve(n) is not None]
            batch.total = len(names)
            # Hold the populate guard across the enqueue loop so a fast-first
            # source finishing mid-loop cannot null _active_batch (via
            # _settle→_maybe_finish_batch) before later tasks are enqueued —
            # otherwise they'd read batch_id=None and orphan (#2).
            self._populating_batch = True
            self._emit({"type": "batch", "batch": batch.to_dict()})
        try:
            for n in names:
                try:
                    self.enqueue_one(n)
                except ValueError:
                    pass
        finally:
            # Always clear the guard — if it stayed True on an exception,
            # _maybe_finish_batch would early-return forever, stalling every
            # future batch as perpetually "running".
            with self._lock:
                self._populating_batch = False
                # Counter-based completion (see _maybe_finish_batch) needs
                # total == number of tasks that will actually settle into this
                # batch. A batchless in-flight task (scheduler-detached refresh)
                # absorbs its source's slot via dedup — no task is created for
                # this batch — so re-stamp total to the attached count.
                b = self._batches[batch.id]
                if b.state != "done":
                    b.total = sum(1 for t in self._tasks.values()
                                  if t.batch_id == b.id)
        self._maybe_finish_batch()
        return batch.id

    def enqueue_stale(self, stale_names: list[str]) -> str | None:
        if not stale_names:
            return None
        return self.enqueue_batch(stale_names)

    def has_active_offline_tasks(self, source_filter=None) -> bool:
        """True while any offline-source task is queued/downloading/
        loading/throttled. The cold-start gate holds the integral window on
        this: a paused batch keeps its tasks in these states (so pausing
        holds the gate until the deadline releases it), and a rebuild
        batch's tasks re-arm the window for the whole rebuild.
        `source_filter(name)` further restricts which sources count — the
        gate passes a "source not yet loaded" filter so refresh of
        already-loaded sources never holds queries."""
        with self._lock:
            for t in self._tasks.values():
                if t.state in ("queued", "downloading", "loading", "throttled"):
                    src = self._resolve(t.source_name)
                    if src is not None \
                            and (source_filter is None or source_filter(t.source_name)):
                        return True
            return False

    def _maybe_finish_batch(self):
        with self._lock:
            if not self._active_batch:
                return
            # Don't finish while enqueue_batch is still populating — a fast-first
            # source can otherwise null _active_batch before later tasks land (#2).
            if self._populating_batch:
                return
            b = self._batches[self._active_batch]
            if b.state == "done":
                return
            # Counter-based completion, NOT a state scan: a task flips terminal
            # via _set_state at the end of _run_task, but its b.done increment
            # lands later in _settle — a state scan can see "all terminal" while
            # the last 1..N increments are still in flight and emit the terminal
            # done event with done < total (#6). b.done only moves under this
            # lock, so the check is atomic with the increments.
            if b.done < b.total:
                return
            b.state = "done"
            self._emit({"type": "batch", "batch": b.to_dict()})
            self._emit({"type": "done", "batch": b.to_dict()})
            # Release the active slot so a terminal batch stops being
            # reported as active. Without this, _active_batch leaks and
            # later single-source updates (enqueue_one) silently attach to
            # the finished batch, accruing its done/total counter (e.g.
            # 3/2 · 150%) and showing stale batch context.
            self._active_batch = None

    # --- pause / resume / cancel (Task 5) ---
    def pause(self):
        with self._lock:
            if not self._active_batch:
                # batchless(单源更新)时 no-op:清 _go 会永久卡死 worker
                # 队列且无 batch 事件可供前端渲染 Resume,只能重启恢复。
                return
            b = self._batches[self._active_batch]
            # 状态写与 _go.clear 都在锁内:只保状态写的话,_maybe_finish_batch
            # 可在锁释放后、clear 前置 done 并清 active —— 清完的 batch 无 Resume
            # 入口,_go 已清 = 同一个永久卡死窗口。
            b.state = "paused"
            self._emit({"type": "batch", "batch": b.to_dict()})
            self._go.clear()

    def resume(self):
        with self._lock:
            if self._active_batch:
                b = self._batches[self._active_batch]
                if b.state == "paused":
                    b.state = "running"
                    self._emit({"type": "batch", "batch": b.to_dict()})
        self._go.set()
        with self._queue_cv:
            self._queue_cv.notify_all()

    def cancel(self, task_id):
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task.state in ("queued", "throttled"):
            task.state = "cancelled"
            # Defensive: a worker may have just read state='queued' under the cv
            # and be about to popleft+run it. Re-check under the cv (in _worker)
            # is the primary guard; cancelling the token covers the residual
            # window between that re-check and _run_task (#1 cancel race).
            task.token.cancel()
            self._emit({"type": "task", "task": task.to_dict()})
            with self._queue_cv:
                self._queue = deque(t for t in self._queue if t != task_id)
                self._queue_cv.notify_all()
            self._settle(task)
        else:
            task.token.cancel()

    def cancel_batch(self, batch_id: str | None = None):
        with self._lock:
            if batch_id is None:
                if self._active_batch:
                    target = self._active_batch
                else:
                    # 无 active batch 的 abort:清所有在飞的 batchless 任务
                    # (单源更新路径 — 前端 Abort 对它们同样是真实按钮)。
                    ids = [tid for tid, t in self._tasks.items()
                           if t.batch_id is None
                           and t.state in ("queued", "downloading", "loading",
                                           "throttled")]
                    target = None
            else:
                if batch_id not in self._batches:
                    return
                target = batch_id
            if target is not None:
                ids = [tid for tid, t in self._tasks.items()
                       if t.batch_id == target
                       and t.state in ("queued", "downloading", "loading", "throttled")]
        for tid in ids:
            self.cancel(tid)

    # --- internals ---
    def _host_lock(self, host):
        if host is None:
            return None
        with self._host_guard:
            if host not in self._host_locks:
                self._host_locks[host] = threading.Lock()
            return self._host_locks[host]

    def _enqueue(self, task_id):
        with self._queue_cv:
            self._queue.append(task_id)
            self._queue_cv.notify()

    def _worker(self):
        while True:
            with self._queue_cv:
                while (not self._go.is_set()) or (not self._queue):
                    self._queue_cv.wait()
                # Scan the queue for the first ADMISSIBLE task instead of only
                # peeking queue[0]. A throttled (valve-blocked) task at the
                # head must not starve tasks queued behind it — pre-fix,
                # workers peeked queue[0], saw can_run=False, wait+cont without
                # popping, so queue[1..N] never reached any worker (#3 FIFO
                # head-block).
                chosen_idx = None
                skipped_admit = False
                for i, tid in enumerate(self._queue):
                    task = self._tasks.get(tid)
                    if task is None or task.state not in ("queued", "throttled"):
                        continue
                    if self._valve is not None:
                        if not self._valve.can_run():
                            if task.state == "queued":
                                self._set_state(task, "throttled")
                            skipped_admit = True
                            continue
                    chosen_idx = i
                    break
                if chosen_idx is None:
                    # Either every runnable task is throttled, or the queue is
                    # all cancelled/garbage. Purge dead entries, then wait for a
                    # notify (valve target rising, a cancel, or a new enqueue).
                    if not skipped_admit:
                        self._queue = deque(
                            t for t in self._queue
                            if self._tasks.get(t) is not None
                            and self._tasks[t].state in ("queued", "throttled"))
                    self._queue_cv.wait()
                    continue
                task_id = self._queue[chosen_idx]
                task = self._tasks.get(task_id)
                # Re-check state under the cv RIGHT before popping: cancel() can
                # flip a queued task to 'cancelled' between the scan above and
                # here. Without this, a cancelled task runs and both cancel's
                # _settle and _run_task's _settle increment batch.done (#1).
                if task is None or task.state not in ("queued", "throttled"):
                    del self._queue[chosen_idx]
                    continue
                if self._valve is not None:
                    if task.state == "throttled":
                        self._set_state(task, "queued")
                    self._valve.on_start()
                del self._queue[chosen_idx]
            try:
                self._run_task(task)
            finally:
                if self._valve is not None:
                    self._valve.on_finish()
                    with self._queue_cv:
                        self._queue_cv.notify_all()

    def _set_state(self, task: Task, state: str, error: str | None = None,
                   error_code: str | None = None):
        task.state = state
        task.error = error
        task.error_code = error_code
        self._emit({"type": "task", "task": task.to_dict()})

    def _emit_progress(self, task: Task, received: int, total: int) -> None:
        """Throttled phase-progress event (downloading=bytes, loading=records).
        Emits at most every 0.15s or on a >=3 percentage-point change, plus the
        final 100% — so a large download yields a smooth bar without flooding
        SSE. 计数无条件落 Task(to_dict/快照读它),仅事件本身节流。"""
        task.received = received
        task.total = total
        now = time.time()
        pct = int(received * 100 / total) if total > 0 else 0
        last_ts, last_pct = self._prog.get(task.id, (0.0, -1))
        finished = total > 0 and received >= total
        if finished or (now - last_ts) >= 0.15 or abs(pct - last_pct) >= 3:
            self._prog[task.id] = (now, pct)
            self._emit({"type": "task_progress", "task_id": task.id,
                        "received": received, "total": total})

    def _rebuild_via_subprocess(self, task: Task, source) -> bool:
        """loading 相位的子进程重建(IP_RADAR_REBUILD_SUBPROCESS=1 车道,
        2026-10 小机 RSS 棘轮根修)。

        子进程 `python -m ipdb._rebuild_child <name>`(stdout 行协议 PROG/OK,
        见该模块头);数据目录经继承的 IP_RADAR_DATA_DIR 解析,与父进程
        一致。rc==0 后父进程 source.load() 把 reader/count 重同步到子进程
        提交的新 epoch(子进程不回写父进程对象状态);load 抛 → failed。
        rc!=0 → failed(stderr 尾部 ~300 字入 error,足够定位 traceback 末段
        又不把任务快照变日志倾倒场)。

        取消:逐行检查 token,命中即 terminate + wait + cancelled(记账
        语义与现行取消一致:epoch 已换新不回滚,grill Q8 2026-10-11)。
        返回 True 仅当 rc==0 且 load() 成功 —— 取消/失败都在此内置终态并
        返回 False,由 _run_task 的 finally 走 _settle。Popen/管道层异常同样
        映射 failed:炸出 _run_task 会杀死 worker 线程,任务永久卡 loading、
        batch 永不完成。
        """
        stderr_buf: list[str] = []
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "ipdb._rebuild_child",
                 task.source_name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception as e:
            logger.warning("rebuild subprocess spawn failed for %s: %s",
                           task.source_name, e)
            # 子进程车道全线 rebuild 码:构建失败就报构建失败(2026-10-17
            # 用户裁定,失败分类告警)。
            self._set_state(task, "failed", str(e), error_code="rebuild")
            return False
        # stderr 独立 reader 线程:子进程把 64KB stderr 管道缓冲写满而父
        # 进程只逐行读 stdout 时,子进程阻塞在 stderr 写上,OK 永远到不了
        # —— 经典双管道死锁。

        def _drain_stderr():
            for ln in proc.stderr:
                stderr_buf.append(ln)

        stderr_reader = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_reader.start()
        cancelled = False
        try:
            try:
                for line in proc.stdout:
                    parts = line.split()
                    if len(parts) == 3 and parts[0] == "PROG":
                        try:
                            r, t = int(parts[1]), int(parts[2])
                        except ValueError:
                            pass
                        else:
                            self._emit_progress(task, r, t)
                    if task.token.is_cancelled():
                        cancelled = True
                        break
                if cancelled:
                    proc.terminate()
                rc = proc.wait()
            finally:
                proc.stdout.close()
                # 子进程已退出(wait 返回)⇒ 两管道必至 EOF ⇒ reader 线程
                # 必退出;join 后再 close stderr,避免与阻塞中的 read 竞争。
                stderr_reader.join(timeout=5)
                proc.stderr.close()
                if proc.returncode is None:     # 异常路径兜底:不留僵尸
                    proc.terminate()
                    proc.wait()
        except Exception as e:
            logger.warning("rebuild subprocess pipe failed for %s: %s",
                           task.source_name, e)
            self._set_state(task, "failed", str(e), error_code="rebuild")
            return False
        if cancelled:
            self._set_state(task, "cancelled")
            return False
        if rc == 0:
            try:
                source.load()
            except Exception as e:
                logger.warning("post-subprocess load failed for %s: %s",
                               task.source_name, e)
                self._set_state(task, "failed", str(e), error_code="rebuild")
                return False
            return True
        tail = "".join(stderr_buf).strip()[-300:]
        logger.warning("rebuild subprocess failed for %s: %s",
                       task.source_name, tail)
        self._set_state(task, "failed", tail or f"rc={rc}",
                        error_code="rebuild")
        return False

    def _run_task(self, task: Task):
        source = self._resolve(task.source_name)
        if source is None:
            self._set_state(task, "failed", "source disappeared",
                            error_code="source_not_found"); self._settle(task); return
        host_lock = self._host_lock(task.host)
        src_lock = self._lock_for(task.source_name)
        if host_lock:
            host_lock.acquire()
        src_lock.acquire()
        try:
            # rebuild-only 车道(2026-10-14 收敛批):needs_rebuild 触发的任务
            # raw 已最新,重抓是纯浪费 —— 跳过 download 直进 loading(状态机
            # 少一个相位,进度语义不变);raw 缺失回退正常全量,旗标不制造
            # 假失败(手动 enqueue/降级路径不受影响)。
            p = getattr(source, "_path", None)
            if not (task._rebuild_only and p is not None and Path(p).exists()):
                task.received = task.total = 0
                self._set_state(task, "downloading")
                self._prog[task.id] = (0.0, -1)
                task.token.on_progress = lambda r, t: self._emit_progress(task, r, t)
                try:
                    source.download(token=task.token)
                except CancelledError:
                    self._set_state(task, "cancelled"); return
                except Exception as e:
                    # 静默失败清偿(2026-10 小机事故诊断痛点):失败必须留痕。
                    logger.warning("download failed for %s: %s",
                                   task.source_name, e)
                    # 失败分类(2026-10-17 用户裁定):下载相位异常记
                    # download——scheduler 按此分梯,告警渲染「下载连续失败」。
                    self._set_state(task, "failed", str(e),
                                    error_code="download"); return
                finally:
                    task.token.on_progress = None
                if task.token.is_cancelled():
                    self._set_state(task, "cancelled"); return
            task.received = task.total = 0
            self._set_state(task, "loading")
            self._prog[task.id] = (0.0, -1)
            if os.environ.get("IP_RADAR_REBUILD_SUBPROCESS") == "1":
                # 子进程车道(2026-10 小机 RSS 棘轮根修):rebuild 在一次性
                # 子进程执行,退出即归还堆高水位(动因见 _rebuild_child
                # 模块头)。默认关:不设开关时下方原路径逐位不动(位等价)。
                if not self._rebuild_via_subprocess(task, source):
                    return
            else:
                task.token.on_progress = lambda d, t: self._emit_progress(task, d, t)
                try:
                    # 预检而非 try/except TypeError 回退:后者会吞 rebuild 内部
                    # 真实 TypeError 并重复执行整个重建。
                    if "progress" in inspect.signature(source.rebuild).parameters:
                        source.rebuild(progress=task.token.on_progress)
                    else:
                        source.rebuild()
                except Exception as e:
                    # 静默失败清偿(2026-10 小机事故诊断痛点):失败必须留痕。
                    logger.warning("in-process rebuild failed for %s: %s",
                                   task.source_name, e)
                    # 失败分类(2026-10-17 用户裁定):构建相位异常记
                    # rebuild——告警渲染「构建连续失败」(子进程车道同码,
                    # 见 _rebuild_via_subprocess)。
                    self._set_state(task, "failed", str(e),
                                    error_code="rebuild"); return
                finally:
                    task.token.on_progress = None
            # 与 download→loading 边界检查对称:loading 期间点的取消在
            # rebuild 返回后生效(按钮在 loading 态是启用的,无视会误导)。
            # 取消只影响记账:epoch 已安全换新(rebuild 返回即 ptr 已切换,
            # 数据不回滚;grill Q8 2026-10-11)。
            if task.token.is_cancelled():
                self._set_state(task, "cancelled"); return
            self._set_state(task, "done")
        finally:
            src_lock.release()
            if host_lock:
                host_lock.release()
            self._settle(task)

    def _settle(self, task: Task):
        """Bookkeeping after a task leaves the active set. Does NOT emit a
        terminal `task` event — every terminal path has already emitted via
        `_set_state` (or `cancel()`'s explicit emit for the queued case), so
        emitting here would double-broadcast. Only the batch-progress event
        (done-counter increment) and `_maybe_finish_batch` are owned here.

        Idempotent: a terminal task can reach _settle twice when cancel()
        races dispatch (cancel's _settle + _run_task's finally _settle). The
        _settled flag ensures batch.done increments exactly once (#1)."""
        with self._lock:
            if task._settled:
                return
            terminal = task.state in ("done", "failed", "cancelled")
            if self._by_source.get(task.source_name) == task.id and terminal:
                del self._by_source[task.source_name]
            if task.batch_id and task.batch_id in self._batches and terminal:
                b = self._batches[task.batch_id]
                b.done += 1
                self._emit({"type": "batch", "batch": b.to_dict()})
            if terminal:
                task._settled = True
        self._maybe_finish_batch()

    # --- event bus (Task 6) ---
    def subscribe(self, loop: asyncio.AbstractEventLoop) -> "asyncio.Queue[dict]":
        """Register a bounded subscriber queue. `loop` is the asyncio loop the
        SSE endpoint runs in; `_emit` schedules puts onto it via
        `call_soon_threadsafe`. Caller owns the queue's lifetime and must call
        `unsubscribe(q)` on disconnect to avoid leaking entries in `_subs`."""
        self._loop = loop
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_cap)
        with self._subs_lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q) -> None:
        with self._subs_lock:
            self._subs.discard(q)

    def _emit(self, event: dict):
        with self._subs_lock:
            subs = list(self._subs)
        loop = self._loop
        if not subs or loop is None:
            return

        def _deliver(q: "asyncio.Queue[dict]", evt: dict) -> None:
            # Runs inside the subscriber loop via call_soon_threadsafe, so
            # QueueFull is raised (and caught) here — not in the worker thread
            # that called _emit. On overflow: drop oldest, retry once.
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()  # drop oldest
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(evt)
                except asyncio.QueueFull:
                    pass  # still full after drop (concurrent producer): give up

        for q in subs:
            try:
                loop.call_soon_threadsafe(_deliver, q, event)
            except RuntimeError:  # loop closed mid-flight
                pass
