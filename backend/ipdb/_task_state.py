"""任务/批次状态机的词表、合法转移表与处置(#484,第四轮架构评审第 21 张卡)。

独立成模块而不并入 _tasks.py:_scheduler.py / _api_models.py 只要词表,不该
为此 import UpdateManager(会连带拉起 worker 线程等 import 副作用,且
_tasks.py ↔ _scheduler.py 互相引用成环)。本模块只依赖标准库。

三样东西:
1. 词表(闭集):TaskState / BatchState 两个 Literal 是唯一的拼写出处;
   全集、在飞、终态、待派发等集合只在这里定义一次,_tasks.py /
   _scheduler.py / 词表对拍测试一律引用,不再手抄元组。
2. 合法转移表 TASK_TRANSITIONS / BATCH_TRANSITIONS:从代码里的实际发生点
   推出来(每条边注明出处)——表描述的是现行代码,不是设计意图。
3. 处置:enforce_task_transition / enforce_batch_transition——合法静默;
   非法时按模块开关(set_strict)二选一:
     - 严格模式(测试套件,tests/conftest.py 全套件打开):抛 ValueError;
     - 记录模式(缺省,生产):记一条错误日志(固定前缀
       ILLEGAL_TRANSITION_LOG_PREFIX,日后接告警的锚)+ 计数,状态照写
       ——任务线程不因这张表卡住。
"""
import logging
import threading
from typing import Literal, Optional, get_args

logger = logging.getLogger(__name__)

# ── 词表 ──────────────────────────────────────────────────────────────────

# 任务状态全集(八态)。序 = 生命周期序;OpenAPI 枚举(TaskOut.state)同序。
TaskState = Literal[
    "queued", "downloading", "loading", "throttled",   # 源任务在飞四态
    "running",                                          # 运营轮相位(P2 票 #134)
    "done", "failed", "cancelled",                      # 终态
]
# 终态子集的类型(运营轮收口 finish_ops_round 的实参域)。
TerminalTaskState = Literal["done", "failed", "cancelled"]

TASK_STATES: tuple[str, ...] = get_args(TaskState)

# 在飞四态:查询门 has_active_offline_tasks、同源去重 _enqueue_one、ops 车道
# 占道判定 start_ops_round、整批取消 cancel_batch、scheduler reconcile 共用。
# 刻意不含 running:轮次不阻查询门(冷启动验收 1)。
TASK_STATES_IN_FLIGHT: frozenset[str] = frozenset(
    {"queued", "downloading", "loading", "throttled"})
# 终态三态:源任务与运营轮共用。
TASK_STATES_TERMINAL: frozenset[str] = frozenset({"done", "failed", "cancelled"})

# 两类任务各自的词表之差(交集即终态):
SOURCE_ONLY_TASK_STATES: frozenset[str] = TASK_STATES_IN_FLIGHT   # 只属于源任务
OPS_ROUND_ONLY_STATES: frozenset[str] = frozenset({"running"})    # 只属于运营轮

# 排队待派发两态:任务还在 worker 队列里、_run_task 未起跑(queued = 可派发,
# throttled = 被内存阀门压住)。worker 的扫描/复查/清队和 cancel() 的直写
# 终态分支共用——它是「在飞」的真子集,不是另一个概念的三次手抄。
TASK_STATES_WAITING: frozenset[str] = frozenset({"queued", "throttled"})

# 批次状态全集(三态)。
BatchState = Literal["running", "paused", "done"]
BATCH_STATES: tuple[str, ...] = get_args(BatchState)


# ── 合法转移表 ─────────────────────────────────────────────────────────────
# 键 = 旧状态,值 = 允许写进去的新状态;不在表里的转移 = 非法(处置见上)。
# 每条边注明发生点(函数名;行号会漂,函数名不会)。

TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    # 出生态(构造缺省)。
    #   → throttled  _worker 扫描到阀门不放行(can_run=False)
    #   → downloading / loading
    #                _run_task 起跑(loading = rebuild-only 车道跳过下载)
    #   → failed     _run_task 开头 source disappeared(防御分支:_resolve 查的
    #                是静态注册表,现行装配下不可达,但代码里真有这个写点)
    #   → cancelled  cancel() 的排队中分支
    #   → running    运营轮出生边:ops 任务以缺省 queued 构造,start_ops_round
    #                在占道锁段内立刻经写入口进 running(源任务不走这条边)
    "queued": frozenset(
        {"throttled", "downloading", "loading", "failed", "cancelled", "running"}),
    #   → queued     _worker 阀门放行后、起跑前翻回
    #   → cancelled  cancel() 的排队中分支
    "throttled": frozenset({"queued", "cancelled"}),
    #   → loading    下载完成
    #   → failed     下载异常(error_code=download)
    #   → cancelled  CancelledError / 下载结束后 token 已取消
    "downloading": frozenset({"loading", "failed", "cancelled"}),
    #   → done       重建完成
    #   → failed     重建异常(子进程车道同码,error_code=rebuild)
    #   → cancelled  子进程车道逐行查 token / 重建返回后 token 已取消
    "loading": frozenset({"done", "failed", "cancelled"}),
    #   运营轮收口 finish_ops_round 的实参(_ops_rounds.py:run_round /
    #   _run_recovery_round / _settle_crash / ops_lane_guard 保险丝)
    "running": frozenset({"done", "failed", "cancelled"}),
    "done": frozenset(),
    "failed": frozenset(),
    # cancelled 的出边全部是取消竞态的现行路径——登记 = 记录现状,不是设计
    # 意图。根因:cancel() 的排队中分支「读态 → 写 cancelled」不持 self._lock
    # (#411 锁序:该路径不得碰 cv),与 worker 起跑之间没有互斥(#1 cancel race
    # 的残余窗口):
    #   → downloading / loading / failed
    #       worker 已过 _queue_cv 内的复查、卡在 _run_task 开头的主机锁/源锁
    #       上(状态仍是 queued,用户看到的就是排队中)时 cancel 落了
    #       cancelled;worker 拿到锁后照常翻相位,随后靠已取消的 token 落回
    #       cancelled(下载抛 CancelledError / 重建返回后查 token)。主机锁
    #       争用时这条窗口不窄,是普通「取消排队中任务」的真实路径。
    #   → cancelled
    #       cancel 读到 queued 之后、写之前,worker 已翻 downloading 并进入
    #       下载;cancel 落 cancelled 并取消 token,下载抛 CancelledError 再
    #       落一次 cancelled(终态重入:事件重发一次,_settle 幂等)。窗口只有
    #       几条字节码,偶发。
    # 不登记的后果:生产对普通的取消记错误日志(误报),严格模式下测试偶发
    # 红。修根因(让取消与起跑互斥)另票,不在本卡范围。
    "cancelled": frozenset({"downloading", "loading", "failed", "cancelled"}),
}

BATCH_TRANSITIONS: dict[str, frozenset[str]] = {
    # 出生态(构造缺省)。
    #   → paused  pause()
    #   → done    _maybe_finish_batch(计数式完成:done ≥ total)
    "running": frozenset({"paused", "done"}),
    #   → running  resume()
    #   → paused   重复点暂停:pause() 没有幂等守卫(接口可重复调),状态重写、
    #              batch 事件重发一次、_go 再清一次
    #   → done     暂停期间在飞任务跑完、计数到齐——_maybe_finish_batch 不看
    #              paused(暂停只停派发,不停已在跑的任务)
    # 后两条 #484 任务书没列,是从代码推出来并用测试钉住的。
    "paused": frozenset({"running", "paused", "done"}),
    "done": frozenset(),
}


# ── 判断 ───────────────────────────────────────────────────────────────────

def _transition_error(kind: str, table: dict[str, frozenset[str]],
                      vocab: tuple[str, ...], old: str, new: str) -> Optional[str]:
    allowed = table.get(old)
    if allowed is not None and new in allowed:
        return None
    if old not in table:
        detail = f"old state {old!r} is not in the vocabulary"
    elif new not in vocab:
        detail = f"new state {new!r} is not in the vocabulary"
    else:
        detail = f"allowed targets: {', '.join(sorted(allowed)) or 'none (terminal)'}"
    return f"{kind} state transition {old!r} -> {new!r} is not legal: {detail}"


def task_transition_error(old: str, new: str) -> Optional[str]:
    """任务状态转移 old → new:合法返回 None,不合法返回一句可直接进日志的说明。"""
    return _transition_error("task", TASK_TRANSITIONS, TASK_STATES, old, new)


def batch_transition_error(old: str, new: str) -> Optional[str]:
    """批次状态转移 old → new:合法返回 None,不合法返回一句可直接进日志的说明。"""
    return _transition_error("batch", BATCH_TRANSITIONS, BATCH_STATES, old, new)


# ── 处置 ───────────────────────────────────────────────────────────────────

# 非法转移错误日志的固定前缀(日后接告警按它 grep / 过滤)。
ILLEGAL_TRANSITION_LOG_PREFIX = "illegal-state-transition"

_strict: bool = False            # 缺省 = 记录模式(生产);测试套件经 conftest 打开
_illegal_count: int = 0          # 记录模式下记下的非法转移次数(进程级)
_count_lock = threading.Lock()


def set_strict(enabled: bool) -> None:
    """切换严格模式(True = 非法转移抛 ValueError)。返回 None;调用方要恢复旧值
    就自己先问 is_strict()(tests/conftest.py 用 monkeypatch 自动还原)。"""
    global _strict
    _strict = enabled


def is_strict() -> bool:
    return _strict


def illegal_transition_count() -> int:
    """记录模式下记下的非法转移累计次数(严格模式抛错的不计)。"""
    with _count_lock:
        return _illegal_count


def _enforce(kind: str, table: dict[str, frozenset[str]], vocab: tuple[str, ...],
             subject: str, old: str, new: str) -> None:
    global _illegal_count
    reason = _transition_error(kind, table, vocab, old, new)
    if reason is None:
        return
    if _strict:
        raise ValueError(f"{reason} [{subject}] (strict mode)")
    with _count_lock:
        _illegal_count += 1
    logger.error("%s: %s [%s]", ILLEGAL_TRANSITION_LOG_PREFIX, reason, subject)


def enforce_task_transition(task_id: str, source_name: str, old: str, new: str) -> None:
    """任务状态写入口的守门:合法静默;非法按模式抛错或记日志 + 计数。
    带任务号与源名——两者都要进错误信息和日志。"""
    _enforce("task", TASK_TRANSITIONS, TASK_STATES,
             f"task={task_id} source={source_name}", old, new)


def enforce_batch_transition(batch_id: str, old: str, new: str) -> None:
    """批次状态写入口的守门,同 enforce_task_transition。"""
    _enforce("batch", BATCH_TRANSITIONS, BATCH_STATES, f"batch={batch_id}", old, new)
