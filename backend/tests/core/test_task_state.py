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
    ILLEGAL_TRANSITION_LOG_PREFIX, TASK_STATES, TASK_STATES_IN_FLIGHT,
    TASK_STATES_TERMINAL, TASK_STATES_WAITING, TASK_TRANSITIONS,
    illegal_transition_count,
)
from ipdb._tasks import Batch, Task, UpdateManager


def _make_manager(sources=(), concurrency=1):
    by_name = {s.name: s for s in sources}
    return UpdateManager(resolve_source=lambda n: by_name.get(n),
                         lock_for=lambda n: threading.Lock(),
                         concurrency=concurrency), by_name


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
    """表内每一对合法转移:写入口照写(判转移放行 + 字段落 + 事件面)。"""
    t = Task(id=f"p_{old}", source_name="a", host=None, state=old)
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
def test_batch_illegal_pair_rejected_strict(mgr, old, new):
    b = Batch(id=f"bx_{old}", state=old)
    with pytest.raises(ValueError, match="is not legal"):
        mgr._write_batch_state(b, new)
    assert b.state == old


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


def test_cancel_queued_branch_routes_through_write_entry(mgr):
    """cancel() 排队中分支:queued → cancelled 恒合法,构造不出非法对,改用
    实例级 spy 钉「必经写入口」——直写字段的旧写法不会经过它。"""
    t = Task(id="c1", source_name="a", host=None)  # 出生态 queued
    mgr._tasks[t.id] = t
    seen = []
    real = mgr._write_state

    def spy(task, state, *a, **kw):
        seen.append((task.id, state))
        return real(task, state, *a, **kw)

    mgr._write_state = spy
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
    """不抛、计数 +1、错误日志带固定前缀与任务号/源名、状态照写——生产里
    任务线程不因这张表被卡住。"""
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    t = Task(id="r1", source_name="a", host=None, state="done")
    mgr._tasks[t.id] = t
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_state(t, "failed")
    assert t.state == "failed"
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text
    assert "task=r1" in caplog.text and "source=a" in caplog.text
    assert "'done' -> 'failed'" in caplog.text


def test_record_mode_batch_no_raise_writes_and_counts(monkeypatch, caplog, mgr):
    monkeypatch.setattr(_task_state, "_strict", False)
    before = illegal_transition_count()
    b = Batch(id="rb1", state="done")
    with caplog.at_level(logging.ERROR, logger="ipdb._task_state"):
        mgr._write_batch_state(b, "paused")
    assert b.state == "paused"
    assert illegal_transition_count() == before + 1
    assert ILLEGAL_TRANSITION_LOG_PREFIX in caplog.text
    assert "batch=rb1" in caplog.text


# --- 4. 表的自洽 --------------------------------------------------------------

def test_tables_are_well_formed():
    """键 = 词表全集(漏键 = 该状态写出界外);值 ⊆ 词表;在飞/终态/running
    不重不漏盖满八态(查询门语义:在飞不含 running);排队两态是在飞子集。"""
    assert set(TASK_TRANSITIONS) == set(TASK_STATES)
    for old, targets in TASK_TRANSITIONS.items():
        assert targets <= set(TASK_STATES), f"{old} 的出边越界: {targets}"
    assert set(BATCH_TRANSITIONS) == set(BATCH_STATES)
    for old, targets in BATCH_TRANSITIONS.items():
        assert targets <= set(BATCH_STATES), f"batch {old} 的出边越界: {targets}"
    assert not (TASK_STATES_IN_FLIGHT & TASK_STATES_TERMINAL)
    assert (TASK_STATES_IN_FLIGHT | TASK_STATES_TERMINAL
            | _task_state.OPS_ROUND_ONLY_STATES) == set(TASK_STATES)
    assert TASK_STATES_WAITING <= TASK_STATES_IN_FLIGHT
