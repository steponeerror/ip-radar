"""任务/批次状态机:合法转移表与唯一写入口(#484,第四轮架构评审第 21 张卡)。

四个面:
1. 表逐对测:TASK_TRANSITIONS / BATCH_TRANSITIONS 对词表全积参数化——
   表内合法对经写入口照写;表外对严格模式(conftest 的 task_state_strict
   全套件 autouse 打开)当场抛 ValueError、字段不被污染。期望合法性从
   模块表本身取:这对测试钉的是「写入口与表不脱钩」;「表漏登记真路径」
   由整套件开着严格模式跑一遍兜住——任何代码路径写进未登记转移即抛。
2. 三个入口各自走写入口:_set_state、finish_ops_round 用严格模式下的
   非法转移证明(绕开写入口就不会抛);cancel() 排队中分支的转移恒合法
   (queued/throttled → cancelled 都在表内,无从构造非法对),用实例级
   spy 钉「必经写入口」。
3. 记录模式(生产缺省,用例内把开关翻回 False):不抛、计数 +1、错误日志
   带固定前缀 ILLEGAL_TRANSITION_LOG_PREFIX、状态照写。
4. 表的自洽:键 = 词表全集、值 ⊆ 词表、在飞/终态/running 划分不重不漏。
"""
import logging
import threading

import pytest

from ipdb import _task_state
from ipdb._task_state import (
    BATCH_STATES, BATCH_TRANSITIONS,
    ILLEGAL_TRANSITION_LOG_PREFIX, NO_WRITE_FROM, OPS_ROUND_ONLY_STATES,
    OPS_ROUND_SOURCE, TASK_STATES, TASK_STATES_IN_FLIGHT,
    TASK_STATES_TERMINAL, TASK_STATES_WAITING, TASK_TRANSITIONS,
    illegal_transition_count,
)
from ipdb._tasks import Batch, Task, UpdateManager


def _make_manager(sources=(), concurrency=1):
    by_name = {s.name: s for s in sources}
    return UpdateManager(resolve_source=lambda n: by_name.get(n),
                         lock_for=lambda n: threading.Lock(),
                         concurrency=concurrency), by_name


class _BlockSrc:
    """最小源桩(批次行为用例用):download 阻在 Event 上,rebuild 即返。
    形状对齐 _run_task 的消费面:download(token=None)、rebuild(progress=None)。"""

    def __init__(self, name, gate):
        self.name = name
        self.download_host = None
        self._gate = gate

    def download(self, token=None):
        if not self._gate.wait(30):
            raise RuntimeError("test gate never released")
        if token is not None and token.is_cancelled():
            from ipdb._sources._download import CancelledError
            raise CancelledError()

    def rebuild(self, progress=None):
        pass


@pytest.fixture(scope="module")
def mgr():
    """词表/转移用例共用一个空 manager:_emit 无订阅者时是 no-op,worker
    空转;状态写不持锁,用例间无共享可变任务。"""
    m, _ = _make_manager(concurrency=1)
    yield m


def _pairs(table, vocab, legal):
    out = []
    for old in vocab:
        for new in vocab:
            if (new in table[old]) == legal:
                out.append((old, new))
    return out


def _ids(pairs):
    return [f"{o}->{n}" for o, n in pairs]


# --- 1. 表逐对测:任务 --------------------------------------------------------

@pytest.mark.parametrize("old,new", _pairs(TASK_TRANSITIONS, TASK_STATES, legal=True),
                         ids=_ids(_pairs(TASK_TRANSITIONS, TASK_STATES, legal=True)))
def test_task_legal_pair_writes_through_entry(mgr, old, new):
    """表内每一对合法转移:写入口照写(判转移放行 + 字段落 + 事件面)。
    new = running 的对用运营轮任务跑——类别闸(#484 返工评审第 4 条)只许
    运营轮任务进 running,源任务走这条对子会在类别闸被拦。"""
    src = OPS_ROUND_SOURCE if new == "running" else "a"
    t = Task(id=f"p_{old}_{src}", source_name=src, host=None, state=old)
    mgr._tasks[t.id] = t
    mgr._write_state(t, new)
    assert t.state == new
    assert t.error is None and t.error_code is None  # 无错转移不携带脏错误


@pytest.mark.parametrize("old,new", _pairs(TASK_TRANSITIONS, TASK_STATES, legal=False),
                         ids=_ids(_pairs(TASK_TRANSITIONS, TASK_STATES, legal=False)))
def test_task_illegal_pair_rejected_strict(mgr, old, new):
    """表外每一对:严格模式(conftest autouse)抛 ValueError,字段不被污染。"""
    t = Task(id=f"x_{old}", source_name="a", host=None, state=old)
    mgr._tasks[t.id] = t
    with pytest.raises(ValueError, match="is not legal"):
        mgr._write_state(t, new)
    assert t.state == old


@pytest.mark.parametrize("old,new", _pairs(TASK_TRANSITIONS, TASK_STATES, legal=False),
                         ids=_ids(_pairs(TASK_TRANSITIONS, TASK_STATES, legal=False)))
def test_task_illegal_pair_record_mode(mgr, monkeypatch, caplog, old, new):
    """表外每一对 × 记录模式:不抛、计数 +1、错误日志带固定前缀;写不写按
    出发态分(返工评审第 2 条):从 done/failed 出发拒写(终态下游都按终态
    消费,覆盖会造假告警),其余照写(非终态不写可能被留在在飞态卡住查询
    门和批次)。cancelled 有登记的竞态出边,不在拒写之列。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    t = Task(id=f"r_{old}", source_name="a", host=None, state=old)
    mgr._tasks[t.id] = t
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_state(t, new)
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text
    if old in NO_WRITE_FROM:
        assert t.state == old, f"{old} 出发的写入应拒写,却被写成了 {t.state}"
    else:
        assert t.state == new, f"非终态出发的写入应照写,状态仍是 {t.state}"


def test_task_out_of_vocab_states_rejected(mgr):
    """词表外的值同样拦:新值不在词表 / 旧值不在词表,错误说明都能直接进日志。"""
    t = Task(id="ov1", source_name="a", host=None, state="queued")
    with pytest.raises(ValueError, match="new state"):
        mgr._write_state(t, "bogus")
    t2 = Task(id="ov2", source_name="a", host=None, state="bogus")
    with pytest.raises(ValueError, match="old state"):
        mgr._write_state(t2, "done")


# --- 1b. 表逐对测:批次 --------------------------------------------------------

@pytest.mark.parametrize("old,new", _pairs(BATCH_TRANSITIONS, BATCH_STATES, legal=True),
                         ids=_ids(_pairs(BATCH_TRANSITIONS, BATCH_STATES, legal=True)))
def test_batch_legal_pair_writes_through_entry(mgr, old, new):
    b = Batch(id=f"bp_{old}", state=old)
    mgr._write_batch_state(b, new)
    assert b.state == new


@pytest.mark.parametrize("old,new", _pairs(BATCH_TRANSITIONS, BATCH_STATES, legal=False),
                         ids=_ids(_pairs(BATCH_TRANSITIONS, BATCH_STATES, legal=False)))
def test_batch_illegal_pair_record_mode(mgr, monkeypatch, caplog, old, new):
    """批次同规则:记录模式不抛、计数 +1、前缀日志;终态 done 出发拒写。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    b = Batch(id=f"br_{old}", state=old)
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_batch_state(b, new)
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text
    if old in NO_WRITE_FROM:
        assert b.state == old
    else:
        assert b.state == new


# --- 2. 三个入口都走写入口 ----------------------------------------------------

def test_set_state_routes_through_write_entry(mgr):
    """_set_state = 写入口 + 唤醒:done → failed 非法,严格模式在写字段前抛。"""
    t = Task(id="s1", source_name="a", host=None, state="done")
    mgr._tasks[t.id] = t
    with pytest.raises(ValueError, match="is not legal"):
        mgr._set_state(t, "failed")
    assert t.state == "done"


def test_finish_ops_round_routes_through_write_entry(mgr):
    """任务书原例:已 done 的运营轮任务再收口 failed——绕开写入口的旧写法
    (finish_ops_round 直写 task.state)不会抛;现在必抛。"""
    t = Task(id="ops1", source_name="ops", host=None, state="done")
    mgr._tasks[t.id] = t
    with pytest.raises(ValueError, match="is not legal"):
        mgr.finish_ops_round(t.id, "failed", "late fuse", "infra")
    assert t.state == "done"


def test_cancel_queued_branch_routes_through_write_entry(mgr, monkeypatch):
    """cancel() 排队中分支:queued → cancelled 恒合法,构造不出非法对,改用
    实例级 spy 钉「必经写入口」——直写字段的旧写法不会经过它。spy 挂在
    monkeypatch 上,不留在模块级共享的 manager 上(返工评审第 6 条)。"""
    t = Task(id="c1", source_name="a", host=None)  # 出生态 queued
    mgr._tasks[t.id] = t
    seen = []
    real = mgr._write_state

    def spy(task, state, *a, **kw):
        seen.append((task.id, state))
        return real(task, state, *a, **kw)

    monkeypatch.setattr(mgr, "_write_state", spy)
    mgr.cancel(t.id)
    assert seen == [("c1", "cancelled")]
    assert t.state == "cancelled"
    assert t.token.is_cancelled()  # token 先于状态写(外界见 cancelled 即已叫停)


def test_strict_mode_does_not_count(mgr):
    """严格模式抛错不进计数(计数是记录模式的账,两模式不重复记账)。"""
    before = illegal_transition_count()
    t = Task(id="sc1", source_name="a", host=None, state="done")
    mgr._tasks[t.id] = t
    with pytest.raises(ValueError):
        mgr._write_state(t, "failed")
    assert illegal_transition_count() == before


# --- 3. 记录模式(生产缺省)----------------------------------------------------

def test_record_mode_no_raise_writes_and_counts(monkeypatch, caplog, mgr):
    """非终态出发的非法写入,记录模式照写不卡人(用 queued → done 举例:
    若拒写,任务会被留在排队态卡住批次计数)。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    t = Task(id="r1", source_name="a", host=None)
    mgr._tasks[t.id] = t
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_state(t, "done")
    assert t.state == "done"
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text
    assert "task=r1" in caplog.text and "source=a" in caplog.text
    assert "'queued' -> 'done'" in caplog.text


def test_record_mode_refuses_terminal_departure(monkeypatch, caplog, mgr):
    """返工评审第 2 条:记录模式下从 done 出发的写入拒写——记日志 + 计数,
    字段不被覆盖(终态下游:_settle 已记账、on_terminal 已旁挂、调度器按
    failed 升退避、告警按 state == failed 读,覆盖 done → failed 会造出一条
    假告警)。只拒 done/failed;cancelled 有登记的竞态出边,照写。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    t = Task(id="rr1", source_name="a", host=None, state="done", error="old")
    mgr._tasks[t.id] = t
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_state(t, "failed", "late fuse", "infra")
    assert t.state == "done" and t.error == "old" and t.error_code is None
    t2 = Task(id="rr2", source_name="a", host=None, state="failed")
    mgr._tasks[t2.id] = t2
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_state(t2, "cancelled")
    assert t2.state == "failed"
    assert illegal_transition_count() == before + 2
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text


def test_record_mode_terminal_refusal_keeps_downstream(monkeypatch, caplog, mgr):
    """拒写只拦「写字段 + 发事件」:批次收口/清车道/唤醒照走(评审第 2 条
    的配套——任务线程不能被这张表卡住,下游账务不能因此断)。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    t = Task(id="rr3", source_name=OPS_ROUND_SOURCE, host=None, state="done")
    mgr._tasks[t.id] = t
    mgr._ops_active = t.id
    wakes = []
    real_notify = mgr._notify_lifecycle

    def notify_spy():
        wakes.append(1)
        real_notify()

    monkeypatch.setattr(mgr, "_notify_lifecycle", notify_spy)
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr.finish_ops_round(t.id, "failed", "late fuse", "infra")
    assert t.state == "done" and t.error is None      # 字段未被覆盖
    assert mgr.ops_lane_owner() is None                # 车道照清
    assert wakes == [1]                                # 唤醒照走
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text


def test_record_mode_batch_no_raise_counts(monkeypatch, caplog, mgr):
    """批次记录模式:终态 done 出发的非法写入拒写(同任务规则),非终态出发
    (running → running,重复完成竞态形状)照写。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    b = Batch(id="rb1", state="done")
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_batch_state(b, "paused")
    assert b.state == "done"
    b2 = Batch(id="rb2", state="running")
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_batch_state(b2, "running")
    assert b2.state == "running"
    assert illegal_transition_count() == before + 2
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text
    assert "batch=rb1" in caplog.text


# --- 3b. 类别闸(返工评审第 4 条)-----------------------------------------------

def test_source_task_cannot_enter_running_strict(mgr):
    """源任务 → running:表里 queued → running 是合法边(运营轮出生边),类别
    闸在此拦住源任务——进了 running 就退出在飞集合,查询门放行、轮次互斥
    失效。"""
    t = Task(id="cat1", source_name="a", host=None)
    mgr._tasks[t.id] = t
    with pytest.raises(ValueError, match="source task cannot enter"):
        mgr._write_state(t, "running")
    assert t.state == "queued"


def test_source_task_running_record_mode_writes(monkeypatch, caplog, mgr):
    """类别违规按非法转移处置:源任务进 running 非终态出发 → 记录模式照写
    + 日志(拒写会把任务留在在飞态)。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    t = Task(id="cat2", source_name="a", host=None)
    mgr._tasks[t.id] = t
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_state(t, "running")
    assert t.state == "running"
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text


def test_ops_task_cannot_enter_source_phase_strict(mgr):
    """运营轮任务只许 running + 终态:queued → throttled 表里合法(源任务
    的阀门边),对 ops 任务由类别闸拦住。"""
    t = Task(id="cat3", source_name=OPS_ROUND_SOURCE, host=None)  # 出生态 queued
    mgr._tasks[t.id] = t
    with pytest.raises(ValueError, match="ops-round task cannot enter"):
        mgr._write_state(t, "throttled")
    assert t.state == "queued"


# --- 4. 表的自洽 --------------------------------------------------------------

# 评审版逐对写死的对照(返工评审第 6 条/评审附录 A):表的内容有一个不依赖
# 模块自身取值的独立锚——改表(加边/删边)必须同步改这里,改表的人会看到
# 这份清单,想清楚每条边是不是真路径。
_REVIEWED_TASK_EDGES = {  # 21 对;2026-11-27 评审逐边对过发生点
    ("queued", "throttled"), ("queued", "downloading"), ("queued", "loading"), ("queued", "failed"),
    ("queued", "cancelled"), ("queued", "running"), ("throttled", "queued"), ("throttled", "cancelled"),
    ("downloading", "loading"), ("downloading", "failed"), ("downloading", "cancelled"),
    ("loading", "done"), ("loading", "failed"), ("loading", "cancelled"),
    ("running", "done"), ("running", "failed"), ("running", "cancelled"),
    ("cancelled", "downloading"), ("cancelled", "loading"), ("cancelled", "failed"), ("cancelled", "cancelled"),
}


def test_table_matches_reviewed_edges():
    assert {(o, n) for o, ts in TASK_TRANSITIONS.items() for n in ts} == _REVIEWED_TASK_EDGES, (
        "任务转移表与评审版逐对清单不一致——改表 = 改 _REVIEWED_TASK_EDGES,"
        "每条边都要在 _tasks.py/_ops_rounds.py 里指得出发生点"
    )


def test_tables_are_well_formed():
    """键 = 词表全集(漏键 = 该状态写出界外);值 ⊆ 词表;在飞/终态/running
    不重不漏盖满八态(查询门语义:在飞不含 running);排队两态是在飞子集;
    终态无出边、每个非终态至少一条出边(状态机没有死角)。"""
    assert set(TASK_TRANSITIONS) == set(TASK_STATES)
    for old, targets in TASK_TRANSITIONS.items():
        assert targets <= set(TASK_STATES), f"{old} 的出边越界: {targets}"
    assert set(BATCH_TRANSITIONS) == set(BATCH_STATES)
    for old, targets in BATCH_TRANSITIONS.items():
        assert targets <= set(BATCH_STATES), f"batch {old} 的出边越界: {targets}"
    assert not (TASK_STATES_IN_FLIGHT & TASK_STATES_TERMINAL)
    assert not (TASK_STATES_IN_FLIGHT & OPS_ROUND_ONLY_STATES)
    assert (TASK_STATES_IN_FLIGHT | TASK_STATES_TERMINAL
            | OPS_ROUND_ONLY_STATES) == set(TASK_STATES)
    assert TASK_STATES_WAITING <= TASK_STATES_IN_FLIGHT
    for terminal in ("done", "failed"):
        assert TASK_TRANSITIONS[terminal] == frozenset(), f"{terminal} 不该有出边"
    for s in set(TASK_STATES) - TASK_STATES_TERMINAL:
        assert TASK_TRANSITIONS[s], f"非终态 {s} 一条出边都没有——状态机死角"
    assert BATCH_TRANSITIONS["done"] == frozenset()
    assert BATCH_TRANSITIONS["running"] and BATCH_TRANSITIONS["paused"]


# --- 4b. 批次两条登记边的行为用例(返工评审第 1 条:注释声称「用测试钉住」)---

def test_paused_batch_completes_when_inflight_tasks_finish():
    """paused → done:暂停只停派发,在飞任务跑完、计数到齐,批次照收 done
    (BATCH_TRANSITIONS['paused'] 的 done 边)。"""
    gate = threading.Event()
    m, _ = _make_manager([_BlockSrc("a", gate), _BlockSrc("b", gate)], concurrency=2)
    m.enqueue_batch(["a", "b"])
    assert m.wait_snapshot(
        lambda s: sum(t["state"] == "downloading" for t in s["tasks"]) == 2,
        timeout=10)
    m.pause()
    assert m.snapshot()["batch"]["state"] == "paused"
    gate.set()
    assert m.wait_snapshot(lambda s: s["batch"] is None, timeout=10)
    done = [b for b in m._batches.values() if b.state == "done"]
    assert len(done) == 1 and done[0].done == done[0].total == 2


def test_pause_twice_stays_paused(monkeypatch):
    """paused → paused:重复点暂停重写状态、batch 事件重发一次(BATCH_TRANSITIONS
    ['paused'] 的自环边;pause() 无幂等守卫是现行行为,登记现状)。"""
    gate = threading.Event()
    m, _ = _make_manager([_BlockSrc("a", gate)], concurrency=1)
    m.enqueue_batch(["a"])
    assert m.wait_snapshot(lambda s: s["tasks"][0]["state"] == "downloading",
                           timeout=10)
    events = []
    monkeypatch.setattr(m, "_emit", events.append)
    try:
        m.pause()
        m.pause()
        assert m.snapshot()["batch"]["state"] == "paused"
        assert sum(1 for e in events if e.get("type") == "batch") == 2
    finally:
        gate.set()  # 放行在飞任务,worker 落终态,不留挂着的线程


def test_ops_round_birth_emits_single_running_event(monkeypatch):
    """运营轮任务出生只发一条 running 的 task 事件(旧实现构造直写 state 时
    也只发一条;改成经写入口的出生边 queued → running 后,不得多发 queued)。"""
    m, _ = _make_manager(concurrency=1)
    events = []
    monkeypatch.setattr(m, "_emit", events.append)
    task, reason = m.start_ops_round("health")
    try:
        assert reason is None
        assert [(e["type"], e["task"]["id"], e["task"]["state"])
                for e in events] == [("task", task.id, "running")]
    finally:
        monkeypatch.undo()  # 恢复 _emit,收口走真实事件面
        if task is not None:
            m.finish_ops_round(task.id, "done")
