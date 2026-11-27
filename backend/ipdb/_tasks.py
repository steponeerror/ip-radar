"""UpdateManager — unified trackable/abortable source-update task runner."""
import asyncio
import inspect
import logging
import os
import queue
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
from ._task_state import (
    BatchState, OPS_ROUND_SOURCE, TaskState, TerminalTaskState,
    TASK_STATES_IN_FLIGHT, TASK_STATES_TERMINAL, TASK_STATES_WAITING,
    enforce_batch_transition, enforce_task_transition,
)

logger = logging.getLogger(__name__)

# ops 轮 stderr 日志尾窗(2026-10-26 修):= 前端
# frontend/src/tasks/taskEvents.ts 的 LOG_KEEP_LINES 同值(#292 常数
# 已从 TaskProvider 迁出)——尾随快照出后前端同窗截留,两端窗口一致防
# 播种面反复增缩。进度面非存档,证据本体在包/台账(哲学 1)。
_OPS_LOG_KEEP = 200

# ── #478 子进程车道:停顿超时 + 随时可取消 ──
# stdout 读线程→队列,主循环 get 至多等 1 秒:静默期(写库前的收获阶段,
# 多证据源收完整个文件才开始写库,合法地数分钟无输出)取消标记每秒至少
# 被看一次。
_STDOUT_POLL_S = 1.0
# terminate 后留 30 秒宽限再 kill(对照评估子进程 _eval_manager 的
# communicate(timeout) 模式)。只用在「取消」「停顿」「读事故」三条
# 失败路上(返工裁决,#478 评审必须改 3):正常读到结束那条路,EOF 的
# 时刻就是子进程退出、内核在退出路径里关管道 fd 的时刻(print OK 之后
# 从不显式关 stdout;CPython 收尾在 exit 之前,那段静默归停顿线管),
# EOF 后的 wait 毫秒级返回,不存在「关了输出再慢慢退出」的窗口。
_TERM_GRACE_S = 30.0
# 停顿阈值缺省(分钟)。60 的理由:子进程有两段合法的长时间不出声
# ——①写库之前的收获阶段,多证据源收完整个文件才开始写库,小机上最
# 大的源光收文件就要好几分钟(_rebuild_child 模块头);②最后一条
# PROG 之后还有同步落盘、关 env、compact 拷贝(_lmdb.rebuild_lmdb 提交
# 段),打印 OK 之后还有解释器收尾,大源在小机上都要数分钟。60 分钟
# 留足余量,合法重建不会被误杀;真挂死最多白占一个 worker 线程 60 分钟。
_REBUILD_QUIET_MAX_MIN_DEFAULT = 60.0


def _rebuild_quiet_max_s() -> float | None:
    """停顿阈值:env `IP_RADAR_REBUILD_QUIET_MAX_MIN`(分钟,可小数)
    → 秒;返回 None = 关掉停顿检查(不设上限)。

    取值口径(2026-11-26 返工裁决;写法照兄弟函数 _lmdb._stall_budget_s:
    一次 `not val >= 0` 把负数和 NaN 一起判掉 —— 单式比较 NaN 两侧皆假,
    漏拦会静默落进 `nan*60` 的永假阈值):
    - 未设 → 缺省 60 分钟(理由见 _REBUILD_QUIET_MAX_MIN_DEFAULT 注)。
    - 「0」→ None,关掉检查(运维写 0 的自然意图是「别管」)。
    - 负数、非数字、NaN → 回退缺省 + 告警:打错的开关不该静默关掉挂死
      保护。
    分钟是运维口径;测试直接设小数(如 0.0005 分 ≈ 30ms)即得秒级阈值,
    不另开测试专用入口。
    """
    raw = os.environ.get("IP_RADAR_REBUILD_QUIET_MAX_MIN")
    if raw is None:
        return _REBUILD_QUIET_MAX_MIN_DEFAULT * 60.0
    try:
        val = float(raw)
    except ValueError:
        logger.warning("IP_RADAR_REBUILD_QUIET_MAX_MIN=%r not a number; "
                       "using default %.0f min",
                       raw, _REBUILD_QUIET_MAX_MIN_DEFAULT)
        return _REBUILD_QUIET_MAX_MIN_DEFAULT * 60.0
    if not val >= 0:   # 负/NaN 一并按非法(单式比较,NaN 两侧皆假)
        logger.warning("IP_RADAR_REBUILD_QUIET_MAX_MIN=%r negative/NaN; "
                       "using default %.0f min",
                       raw, _REBUILD_QUIET_MAX_MIN_DEFAULT)
        return _REBUILD_QUIET_MAX_MIN_DEFAULT * 60.0
    if val == 0:       # 0 = 关掉停顿检查(不设上限)
        return None
    return val * 60.0


@dataclass
class Task:
    id: str
    source_name: str
    host: Optional[str]
    # 状态闭集、在飞/终态集合与合法转移表都在 _task_state.py(#484);字段的
    # 唯一写入口是 UpdateManager._write_state。running = ops 轮相位(P2 票
    # #134;源任务不用——下载/构建沿既有相位,has_active_offline_tasks 四态
    # 不含 running → 轮次不阻查询门,冷启动验收 1)。
    state: TaskState = "queued"
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
    state: BatchState = "running"  # running|paused|done(转移表 _task_state.py #484)
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

        # P1 T2 确定性探测器旁挂(票 #154,spec #152 §2):终态回调,入参 =
        # task.to_dict() 只读快照。None = 无消费者(位等价:既有测试/未装配
        # 路径零行为变化);装配在 main.lifespan(_ops_detectors),本模块零
        # 存储依赖。回调在 _settle 收口处只读消费,异常全吞 + log——探测面
        # 故障不得反噬任务状态机/串行车道/查询门。
        self.on_terminal: Optional[Callable[[dict], None]] = None

        # ops 轮串行车道(P2 票 #134,裁①闸二):在飞 ops 轮 task_id;非 None
        # 时 worker 全局停摆(轮次与源更新互斥,964MB 小机 OOM 前科),
        # finish_ops_round 的 notify_all 放行。
        self._ops_active: Optional[str] = None

        # ops 轮 stderr 日志尾(2026-10-26 修,驾驶舱「展开全量日志」中途
        # 开页只见订阅后行的根因):task_log 即时流之外的有界留存,快照面
        # 携带(snapshot() "logs" 键,键=task_id)——中途开页/SSE 重连可
        # 播种订阅前已发行。窗=前端 TaskProvider LOG_KEEP_LINES 同值(200);
        # 证据本体在包/台账,这里只是即时进度面(哲学 1)。生命周期同
        # _tasks 的 ops 面:start 建、下一轮 start 清扫(终态后仍随快照出,
        # 供轮后开页播「上一轮」尾行)。
        self._ops_logs: dict[str, deque[str]] = {}

        self._queue: deque[str] = deque()
        self._queue_cv = threading.Condition()

        self._go = threading.Event(); self._go.set()  # cleared => paused
        self._lock = threading.RLock()

        # event bus
        self._subs: set = set()
        self._subs_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # #411 转移事件面:生命周期等待 cv(wait_for_state/wait_snapshot 的
        # 唤醒源)。锁序约束(终审 P1 补全):全局单向 _queue_cv → 
        # _lifecycle_cv → self._lock,禁反向嵌套——①notify 一律在 self._lock
        # 外取本 cv(等待面会 cv→self._lock 短临界区读态;反序 self._lock→cv
        # = 死锁对);②worker 的转移打戳在 _queue_cv 内、其 _notify_lifecycle
        # 随 _set_state 同点触发 = _queue_cv→cv 嵌套边(合法向);③旧
        # self._lock→_queue_cv 嵌套(_enqueue_one 持锁入队)已拆(见 
        # _enqueue_one 内注释),否则①②③闭成三锁死锁环。唤醒点 = 相位写点
        # _set_state(= 写入口 _write_state + 唤醒,#484)、终态记账 _settle、
        # ops 轮占道/收口与 cancel 的排队中分支(这两处只经写入口写字段、
        # 不唤醒:前者各自在锁段外通知,后者由紧随的 _settle 尾部通知)。
        self._lifecycle_cv = threading.Condition()

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
            if existing and self._tasks[existing].state in TASK_STATES_IN_FLIGHT:
                return self._tasks[existing]
            # Evict the source's prior TERMINAL tasks (and their progress state)
            # before installing the new one, so _tasks/_prog stay O(sources)
            # instead of growing one entry per run forever (#5). _settle clears
            # _by_source on termination, so terminal tasks linger in _tasks with
            # no back-reference — sweep by source_name. A terminal task was
            # retained until now so snapshot()/task_state() could report the last
            # phase; once the source moves on it's stale.
            stale = [tid for tid, t in self._tasks.items()
                     if t.source_name == name and t.state in TASK_STATES_TERMINAL]
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
            self._emit({"type": "task", "task": task.to_dict()})
        # 入队出锁序段(#411 终审 P1):旧序在此持 self._lock 嵌套取 _queue_cv,
        # 与 worker 的 _queue_cv→_lifecycle_cv(转移通知)及等待者的
        # _lifecycle_cv→self._lock(谓词读态)闭成三锁死锁环;外移后全局锁序
        # 无环:_queue_cv → _lifecycle_cv → self._lock。注册先于入队,worker
        # 持同一 _queue_cv 弹出后查 _tasks 必见(happens-before 经 cv)。
        self._enqueue(task.id)
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

    def task_error(self, task_id: str) -> Optional[str]:
        """失败任务的 error 文本(#371:源告警带失败原因)。task 存在且
        state=="failed" → 其 error(下载异常 str / 重建子进程 stderr 尾
        ~300 字,可含换行);否则 None(done/partial/cancelled 无失败
        文本)。循 task_failure_kind 惯例:锁内查,scheduler reconcile
        升退避时取当次失败原因。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and task.state == "failed":
                return task.error
            return None

    # --- #411 转移事件面:可等待的转移观察 ---
    def _notify_lifecycle(self) -> None:
        """唤醒生命周期等待者。锁序:调用点一律不持 self._lock(__init__
        _lifecycle_cv 注释);无等待者时本调用 ≈ 一次无争用锁 + 空唤
        醒(热路径预算:相位转移非查询车道,不碰每请求面)。"""
        with self._lifecycle_cv:
            self._lifecycle_cv.notify_all()

    def wait_for_state(self, task_id: str, states, timeout: float = 5.0) -> Optional[str]:
        """阻塞等 task_id 的相位进入 states;命中返回该相位,超时返回当下
        相位(供断言直读实际值,而非空泛超时错),task 未知/已被清扫返回 None。

        #411:替代 flake 家族的 bare time.sleep 等待——唤醒挂相位写点
        (_set_state + ops 轮占道/收口 + cancel 排队中分支随后的 _settle),
        真转移即时醒,门上下文调度延迟只吃 timeout 富余而非窗口上限。检查与
        wait 在 cv 内原子(写点先写态后通知,无丢唤醒)。"""
        states = set(states)
        deadline = time.monotonic() + timeout
        with self._lifecycle_cv:
            while True:
                with self._lock:
                    task = self._tasks.get(task_id)
                    state = None if task is None else task.state
                if state is None or state in states:
                    return state
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return state
                self._lifecycle_cv.wait(remaining)

    def wait_snapshot(self, predicate, timeout: float = 5.0) -> dict:
        """阻塞等快照满足 predicate(事件驱动谓词等待);满足即返,超时返
        回当下快照(断言直读)。与 wait_for_state 同唤醒源:相位转移、
        终态记账(_settle 的批计数/清槽)、ops 车道占道/收口均唤醒复查。
        快照在 cv 内取:谓词判定与 wait 原子,无丢唤醒。唤醒面不含
        「任务出现」本身——新任务的首个相位转移会唤醒;暂停档纯排队
        的快照变化无等待者(现有等待面都等转移,不等出现)。"""
        deadline = time.monotonic() + timeout
        with self._lifecycle_cv:
            while True:
                snap = self.snapshot()
                if predicate(snap):
                    return snap
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return snap
                self._lifecycle_cv.wait(remaining)

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
            # ops 日志尾随快照出(键=task_id;源任务无此面)——中途开页/
            # SSE 重连播种订阅前已发行(__init__ _ops_logs 注释)。
            logs = {tid: list(lines) for tid, lines in self._ops_logs.items()}
            return {"tasks": tasks, "batch": batch, "logs": logs}

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
                if t.state in TASK_STATES_IN_FLIGHT:
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
            self._write_batch_state(b, "done")
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
            self._write_batch_state(b, "paused")
            self._go.clear()

    def resume(self):
        with self._lock:
            if self._active_batch:
                b = self._batches[self._active_batch]
                if b.state == "paused":
                    self._write_batch_state(b, "running")
        self._go.set()
        with self._queue_cv:
            self._queue_cv.notify_all()

    def cancel(self, task_id):
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task.state in TASK_STATES_WAITING:
            # Defensive: a worker may have just read state='queued' under the cv
            # and be about to popleft+run it. Re-check under the cv (in _worker)
            # is the primary guard; cancelling the token covers the residual
            # window between that re-check and _run_task (#1 cancel race).
            task.token.cancel()
            # #484:终态经写入口落(判转移 + 写字段 + 发 task 事件)。token 先于
            # 状态写:外界看到 cancelled 时下载一定已被叫停。本分支「读态 →
            # 写 cancelled」不持 self._lock,与 worker 起跑之间没有互斥(#1
            # cancel race):worker 已过 _queue_cv 复查、卡在 _run_task 开头的
            # 主机锁/源锁上时,同主机源排队要等前一个源整个下载完——这一整段
            # 窗口里本分支会先落 cancelled,worker 拿到锁后照常翻相位,
            # cancelled 的登记出边由此而来(转移表 _task_state.py)。根因修复
            # (起跑前查 token,不加锁、不碰 #411 锁序)见 #488。
            self._write_state(task, "cancelled")
            with self._queue_cv:
                self._queue = deque(t for t in self._queue if t != task_id)
                self._queue_cv.notify_all()
            # #411:排队中分支落终态(_write_state 不唤醒)后的唤醒由紧随的
            # _settle 尾部通知承担(同线程同步到达,无丢唤醒窗口);此处不
            # 另发——避免任何 cancel 调用点未来被包进 self._lock 时引入
            # cv 反序嵌套。
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
                           if t.batch_id is None and t.state in TASK_STATES_IN_FLIGHT]
                    target = None
            else:
                if batch_id not in self._batches:
                    return
                target = batch_id
            if target is not None:
                ids = [tid for tid, t in self._tasks.items()
                       if t.batch_id == target and t.state in TASK_STATES_IN_FLIGHT]
        for tid in ids:
            self.cancel(tid)

    # --- ops 轮串行车道(P2,票 #134;裁①闸二:轮次与源更新互斥)---
    def start_ops_round(self, round_type: str):
        """占串行车道并登记 ops 轮任务;返回 (Task, None) 或 (None, busy_reason)。

        busy_reason="sources" = 任一源任务 queued/downloading/loading/throttled
        (queued 也算:worker pop 后未翻相位的任务 state 仍 queued,拒绝即无
        并发窗);"round" = ops 轮在飞(一轮一车道)。占道成功即建 running 态
        任务并发 task 事件;ops 任务不入 worker 队列/_by_source(驱动方是轮次
        线程,不走 _run_task/_settle)。清扫上一轮终态 ops 任务(镜像
        _enqueue_one 的 stale 清扫,快照不随轮次累积)。
        """
        with self._lock:
            if self._ops_active is not None:
                return None, "round"
            for t in self._tasks.values():
                if t.state in TASK_STATES_IN_FLIGHT:
                    return None, "sources"
            stale = [tid for tid, t in self._tasks.items()
                     if t.source_name == OPS_ROUND_SOURCE
                     and t.state in TASK_STATES_TERMINAL]
            for tid in stale:
                self._tasks.pop(tid, None)
                self._prog.pop(tid, None)
                self._ops_logs.pop(tid, None)
            task = Task(id=uuid.uuid4().hex[:12], source_name=OPS_ROUND_SOURCE, host=None)
            self._tasks[task.id] = task
            self._ops_logs[task.id] = deque(maxlen=_OPS_LOG_KEEP)
            self._ops_active = task.id
            # #484:ops 任务出生即 running——以缺省 queued 构造,在同一锁段内经
            # 写入口进 running(转移表的出生边 queued → running);task 事件
            # 由写入口发。写入口不唤醒,唤醒照旧在锁段外(_notify_lifecycle)。
            self._write_state(task, "running")
            result = (task, None)
        self._notify_lifecycle()  # ops 轮相位不经 _set_state:占道写点自通知(#411)
        return result

    def finish_ops_round(self, task_id: str, state: TerminalTaskState,
                         error: Optional[str] = None,
                         error_code: Optional[str] = None) -> None:
        """ops 轮收口:终态落任务(emit)+ 释放车道(notify_all 放行源 worker)。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                # #484:终态经写入口落(判转移 + 写字段 + 发 task 事件)。在
                # self._lock 内调用:写入口自身不取锁、不唤醒,锁序不变。
                self._write_state(task, state, error, error_code)
            if self._ops_active == task_id:
                self._ops_active = None
        self._notify_lifecycle()  # ops 轮收口写点(#411;同上不经 _set_state)
        with self._queue_cv:
            self._queue_cv.notify_all()

    def ops_lane_owner(self) -> Optional[str]:
        """当前占道的 ops 轮 task_id(None=车道空闲)。#411 结构性收口面:
        ops_lane_guard(_ops_rounds)退出时读它判定「轮体是否漏收口」;测试/
        观察面亦可直接看车道归属。锁内读(与 start/finish 同锁,无窗口)。"""
        with self._lock:
            return self._ops_active

    def ops_log(self, task_id: str, line: str) -> None:
        """轮次 stderr 进度行([turn]/[tool],spawn 契约面)→ 事件总线 → SSE;
        同步入有界日志尾(快照面,__init__ _ops_logs 注释)。未知 task_id
        (恢复轮替身等)只发事件不建尾——尾随 start_ops_round 生命周期。"""
        with self._lock:
            tail = self._ops_logs.get(task_id)
            if tail is not None:
                tail.append(line)
        self._emit({"type": "task_log", "task_id": task_id, "line": line})

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
                # ops 轮在飞 = 全局停摆(P2 裁①闸二:轮次与源更新串行);车道
                # 释放(finish_ops_round)的 notify_all 在此唤醒。
                while (not self._go.is_set()) or (not self._queue) \
                        or (self._ops_active is not None):
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
                    if task is None or task.state not in TASK_STATES_WAITING:
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
                            and self._tasks[t].state in TASK_STATES_WAITING)
                    self._queue_cv.wait()
                    continue
                task_id = self._queue[chosen_idx]
                task = self._tasks.get(task_id)
                # Re-check state under the cv RIGHT before popping: cancel() can
                # flip a queued task to 'cancelled' between the scan above and
                # here. Without this, a cancelled task runs and both cancel's
                # _settle and _run_task's _settle increment batch.done (#1).
                if task is None or task.state not in TASK_STATES_WAITING:
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

    def _write_state(self, task: Task, state: TaskState,
                     error: Optional[str] = None,
                     error_code: Optional[str] = None) -> None:
        """任务状态字段的唯一写入口(#484):判转移(含类别闸:运营轮任务只许
        running/终态,源任务不许 running)→ 写字段 → 发 task 事件。返回值无;
        守门返回 False(仅记录模式下从 done/failed 出发的非法写入)时不写字段
        不发事件——终态下游(_settle、on_terminal、调度器退避、告警)都按终态
        消费,覆盖会造出假 failed 告警;车道清理/唤醒等下游动作由调用点
        (finish_ops_round / cancel / _set_state)在本方法之后照走,任务线程
        不因这张表卡住。不取 self._lock(调用点自己决定持不持:cancel() 不持,
        ops 轮两处持),不唤醒(_set_state / 锁段外的 _notify_lifecycle /
        _settle 负责)。_tasks.py 里对 task.state 的直接赋值只许出现在这里
        (test_vocab_contract 的守卫用例盯着)。"""
        if not enforce_task_transition(task.id, task.source_name, task.state, state):
            return
        task.state = state
        task.error = error
        task.error_code = error_code
        self._emit({"type": "task", "task": task.to_dict()})

    def _write_batch_state(self, b: Batch, state: BatchState) -> None:
        """批次状态字段的唯一写入口(#484),同 _write_state:判转移 → 写 → 发
        batch 事件;记录模式下从终态 done 出发的非法写入拒写(表本来就没有
        done 出边,现行代码走不到)。三个调用点(pause / resume /
        _maybe_finish_batch)都持 self._lock。"""
        if not enforce_batch_transition(b.id, b.state, state):
            return
        b.state = state
        self._emit({"type": "batch", "batch": b.to_dict()})

    def _set_state(self, task: Task, state: TaskState, error: Optional[str] = None,
                   error_code: Optional[str] = None):
        """源任务的相位写点 = 写入口 + 唤醒。"""
        self._write_state(task, state, error, error_code)
        # #411 转移事件面:相位写后的唤醒(本方法是不持 self._lock 的写点;
        # notify 在 emit 后,等待者醒来读到的一定是已发事件的态)。
        self._notify_lifecycle()

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

    def _drop_child_staging(self, source, task: Task) -> None:
        """子进程车道失败终态(取消/停顿/读事故/管道异常)的定点暂存清扫
        (#478 返工裁决,评审建议 6 延伸):子进程被结束会留下
        <base>.<epoch>.new.<pid> 暂存,原先要等下次成功重建后的 load()
        或重启才清 —— 停顿反复发生时每次换一个 pid,大源会把 40G 小机盘
        占满。只清暂存不动纪元(SourceBase.drop_staging →
        _lmdb.drop_staging);清不动不反噬任务状态,只 log。成功与子进程
        自己报错退出两条路不清:前者 load() 里的 cleanup_stale 顺路清,
        后者属「下次载入或重启时清」的既有口径(评审建议 6)。
        """
        drop = getattr(source, "drop_staging", None)
        if drop is None:
            return
        try:
            n = drop()
        except Exception:
            logger.warning("drop staging failed for %s",
                           task.source_name, exc_info=True)
            return
        if n:
            logger.info("dropped %d staging dir(s) for %s",
                        n, task.source_name)

    def _rebuild_via_subprocess(self, task: Task, source) -> bool:
        """loading 相位的子进程重建(IP_RADAR_REBUILD_SUBPROCESS=1 车道,
        2026-10 小机 RSS 棘轮根修)。

        子进程 `python -m ipdb._rebuild_child <name>`(stdout 行协议 PROG/OK,
        见该模块头);数据目录经继承的 IP_RADAR_DATA_DIR 解析,与父进程
        一致。rc==0 后父进程 source.load() 把 reader/count 重同步到子进程
        提交的新 epoch(子进程不回写父进程对象状态);load 抛 → failed。
        rc!=0 → failed(stderr 尾部 ~300 字入 error,足够定位 traceback 末段
        又不把任务快照变日志倾倒场)。

        取消:主循环 get 至多等 1 秒(#478:stdout 挪进读线程 + 队列),
        取消标记在子进程安静时也每秒被看一次;命中即 terminate + 30 秒
        宽限 wait(不退再 kill)+ cancelled。取消不回滚(返工评审措辞
        修正):子进程车道里取消可以落在写库途中 —— 已换的 ptr 不动
        (父进程下次 load() 接上),没换的 ptr 仍指旧纪元、照常可查
        (grill Q8 2026-10-11 的「不回滚」不变量照旧,只是成因说准)。
        停顿超时(#478):「多久没读到子进程的任何一行输出」超过
        IP_RADAR_REBUILD_QUIET_MAX_MIN(分钟,缺省 60;0=关掉;负数/
        非数字/NaN 回退缺省并告警;两段合法静默期与 60 的理由见
        _REBUILD_QUIET_MAX_MIN_DEFAULT 注)判挂死:terminate → 30 秒
        不退 kill → failed,error_code 沿用 rebuild(2026-10-17 裁定
        车道全线构建码,「连续构建失败」告警接得上),错误说明带
        「重建停顿」。
        读事故(返工必须改 1):stdout 读线程里的任何异常经队列递回主
        循环,立刻按失败收口(异常文本进 error),不等停顿阈值 —— 否则
        这类事故最长等满阈值,且可能把 rc=0 的成功重建报成「重建停顿」
        (老主线程读版本则是当场 failed 带异常文本)。
        被杀不留半截:子进程提交是「先写 <base>.<epoch>.new.<pid> 暂存、
        最后换 ptr」(_lmdb.rebuild_lmdb 提交顺序不变量),ptr 仍指旧完整
        epoch,上一可用版本照常可查;取消/停顿/读事故/管道异常四个失败
        终态在确认子进程结束后顺手清暂存(_drop_child_staging →
        SourceBase.drop_staging → _lmdb.drop_staging,只清暂存不动
        纪元),成功与子进程自己报错退出两条路仍由 cleanup_stale 在下次
        成功重建后的 load() 或重启时清(原口径)。
        返回 True 仅当 rc==0 且 load() 成功 —— 取消/停顿/读事故/失败都
        在此内置终态并返回 False,由 _run_task 的 finally 走 _settle。Popen/管道
        层异常同样映射 failed:炸出 _run_task 会杀死 worker 线程,任务
        永久卡 loading、batch 永不完成。
        """
        stderr_buf: list[str] = []
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "ipdb._rebuild_child",
                 task.source_name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace")
                # encoding/errors 对齐 _ops_rounds(返工必须改 1 顺手项):
                # traceback 带源名/URL 的非 UTF-8 字节不再炸解码;stdout
                # 与 stderr 同一 Popen,一并兜住。
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
        # stdout 同样挪进读线程 + 队列(#478):原实现主循环
        # `for line in proc.stdout` 阻塞在读上,取消只在每行末尾被看一次
        # —— 子进程安静时取消不可达、挂死无人管。改后主循环 get 至多等
        # _STDOUT_POLL_S 秒,静默期每秒看一次取消、核一次停顿线。
        stdout_q: queue.Queue = queue.Queue()

        def _drain_stdout():
            ended = False

            def _end(item) -> None:
                nonlocal ended
                if not ended:
                    ended = True
                    stdout_q.put(item)

            try:
                for ln in proc.stdout:
                    stdout_q.put(ln)
            except Exception as e:
                _end(e)         # 读事故随队列递回主循环:快速失败,不伪装停顿
            finally:
                _end(None)      # 结束信号必达(try/finally,返工必须改 1)

        stdout_reader = threading.Thread(target=_drain_stdout, daemon=True)
        stdout_reader.start()
        cancelled = False
        stalled = False
        reader_error: BaseException | None = None  # 读线程递回的异常(必须改 1)
        quiet_max_s = _rebuild_quiet_max_s()
        last_output = time.monotonic()      # 停顿线基线 = 车道起点
        try:
            try:
                while True:
                    try:
                        line = stdout_q.get(timeout=_STDOUT_POLL_S)
                    except queue.Empty:
                        # 静默期:取消每秒至少可见(#478);停顿线 = 距
                        # 最近一行输出超过阈值即判挂死(两段合法静默期
                        # 可达数分钟以上,阈值不能定短,理由见缺省值注;
                        # None = 运维写 0,关掉检查)。
                        if task.token.is_cancelled():
                            cancelled = True
                            break
                        if (quiet_max_s is not None and
                                time.monotonic() - last_output >= quiet_max_s):
                            stalled = True
                            break
                        continue
                    if isinstance(line, BaseException):
                        # 读事故(必须改 1):读线程的异常随队列递回,当场
                        # 失败,不等停顿线,也不把 rc==0 的成功重建误报成
                        # 「重建停顿」。
                        reader_error = line
                        break
                    if line is None:
                        break               # stdout EOF:子进程退出中
                    last_output = time.monotonic()
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
                failed_lane = cancelled or stalled or reader_error is not None
                if failed_lane:
                    proc.terminate()
                # wait 上限按路选(返工必须改 3):取消/停顿/读事故给
                # _TERM_GRACE_S 宽限(不退 kill)。正常 EOF 那条路:EOF 的
                # 时刻就是子进程退出、内核在退出路径里关 fd 的时刻,wait
                # 本应毫秒级返回;上限设成停顿线(None=不设上限)而不设
                # 30 秒硬帽,防极端慢的退出收尾把 rc==0 的重建错杀成
                # failed(主会话实测:读到结束只在子进程退出时发生,
                # print OK 之后并不关 stdout)。
                wait_cap = _TERM_GRACE_S if failed_lane else quiet_max_s
                try:
                    rc = proc.wait(timeout=wait_cap)
                except subprocess.TimeoutExpired:
                    # terminate 不退(拦截 SIGTERM/卡在不可中断态)→ kill
                    # 兜底:原实现 wait 无限等,挂死进程永久占住车道。
                    proc.kill()
                    rc = proc.wait()
            finally:
                # 收尾顺序(返工必须改 4):先兜底 terminate —— 进程若还
                # 活着,reader 线程就还卡在读上,先 join 会白等满超时;
                # 再 join 两个读线程(子进程已退出 ⇒ 两管道必至 EOF ⇒
                # 线程必退出),最后才关两根管道。
                if proc.returncode is None:     # 异常路径兜底:不留僵尸
                    proc.terminate()
                    proc.wait()
                stdout_reader.join(timeout=5)
                stderr_reader.join(timeout=5)
                proc.stdout.close()
                proc.stderr.close()
        except Exception as e:
            logger.warning("rebuild subprocess pipe failed for %s: %s",
                           task.source_name, e)
            # 走到这已过 finally(子进程确认结束):按四个失败终态之一清暂存。
            self._set_state(task, "failed", str(e), error_code="rebuild")
            self._drop_child_staging(source, task)
            return False
        if cancelled:
            self._set_state(task, "cancelled")
            self._drop_child_staging(source, task)
            return False
        if reader_error is not None:
            # 读事故终态(必须改 1):异常文本进 error,快速失败。
            logger.warning("rebuild stdout reader crashed for %s: %s",
                           task.source_name, reader_error)
            self._set_state(task, "failed", str(reader_error),
                            error_code="rebuild")
            self._drop_child_staging(source, task)
            return False
        if stalled:
            quiet = time.monotonic() - last_output
            error = (f"重建停顿:最后一条输出在 {quiet:.0f} 秒前"
                     if quiet < 60.0 else
                     f"重建停顿:最后一条输出在 {quiet / 60.0:.0f} 分钟前")
            logger.warning("rebuild subprocess stalled for %s: %s",
                           task.source_name, error)
            self._set_state(task, "failed", error, error_code="rebuild")
            self._drop_child_staging(source, task)
            return False
        if rc == 0:
            # 成功路径也留痕子进程 stderr 人类可读行(如载入期 infra 排除
            # 计数,issue #183):原先只在失败尾摘 300 字,成功即丢 ——
            # 排除日志在生产容器将不可见。正常子进程 stderr 为空,零噪音。
            for ln in stderr_buf:
                if ln.strip():
                    logger.info("rebuild child %s: %s",
                                task.source_name, ln.rstrip())
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
        terminal `task` event — every terminal path has already emitted via the
        write entry `_write_state` (`_set_state`, or `cancel()`'s queued
        branch), so emitting here would double-broadcast. Only the batch-progress
        event (done-counter increment) and `_maybe_finish_batch` are owned here.

        Idempotent: a terminal task can reach _settle twice when cancel()
        races dispatch (cancel's _settle + _run_task's finally _settle). The
        _settled flag ensures batch.done increments exactly once (#1)."""
        with self._lock:
            if task._settled:
                return
            terminal = task.state in TASK_STATES_TERMINAL
            if self._by_source.get(task.source_name) == task.id and terminal:
                del self._by_source[task.source_name]
            if task.batch_id and task.batch_id in self._batches and terminal:
                b = self._batches[task.batch_id]
                b.done += 1
                self._emit({"type": "batch", "batch": b.to_dict()})
            if terminal:
                task._settled = True
        self._maybe_finish_batch()
        # P1 T2 终态旁挂(票 #154):_settled 幂等保证恰好一次;快照只读
        # (dict 拷贝,不传活 task 对象),回调异常吞掉只留警告日志。
        hook = self.on_terminal
        if hook is not None and task.state in TASK_STATES_TERMINAL:
            try:
                hook(task.to_dict())
            except Exception:
                logger.warning("on_terminal hook raised for %s(%s/%s)",
                               task.id, task.source_name, task.state,
                               exc_info=True)
        # #411:终态记账(b.done 递增 / _maybe_finish_batch 清槽)也唤醒
        # 谓词等待者——「全终态」为真后批释放断言不再靠时序窗口。此刻
        # 不持任何锁(_maybe_finish_batch/hook 均已返回)。
        self._notify_lifecycle()

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
