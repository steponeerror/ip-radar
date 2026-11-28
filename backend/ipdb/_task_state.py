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
3. 处置:enforce_task_transition / enforce_batch_transition——返回「写不写」
   (True=照写)。合法返回 True;非法时按模块开关(_strict,tests/conftest.py
   全套件 setattr 打开)二选一:
     - 严格模式(测试套件):抛 ValueError;
     - 记录模式(缺省,生产):记一条错误日志(固定前缀
       ILLEGAL_TRANSITION_LOG_PREFIX,日后接告警的锚)+ 计数。写不写分两种
       (#484 返工,评审第 2 条;#488 评审建议改 2 把 cancelled 并入,2026-11-28):
       从终态 done/failed/cancelled 出发的写入**拒写**——终态的下游(_settle
       记账、on_terminal、调度器按 failed 升退避、告警渲染)都按终态消费,
       覆盖会造出一条假 failed 告警;从 cancelled 出发还会把已取消任务翻回
       在飞(重新压住查询门)。其余非法写入**照写**——非终态任务若不写
       可能被留在在飞态,查询门和批次都会卡住。
4. 类别闸(返工评审第 4 条):写入口再按任务类别限一道——运营轮任务
   (source_name == OPS_ROUND_SOURCE)的新状态只许 running 或终态;源任务
   的新状态不许是 running(否则退出在飞集合,查询门放行、轮次互斥失效)。
   违反同样按非法转移处置(两种模式同上;源任务进 running 是非终态出发
   的非法写入,记录模式下照写 + 日志)。
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
# throttled = 被内存阀门压住)。worker 的扫描/复查/清队和 cancel() 的排队中
# 分支(经写入口落 cancelled)共用——它是「在飞」的真子集,不是另一个概念
# 的三次手抄。
TASK_STATES_WAITING: frozenset[str] = frozenset({"queued", "throttled"})

# 运营轮任务的 source_name(原 _tasks.py 里的魔法字符串,#484 返工评审第 4 条
# 提成常量:类别闸和出生/清扫两处判定共用一个拼写出处)。
OPS_ROUND_SOURCE = "ops"

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
    # cancelled 终态,无出边(#488 修后「终态出不去」在此状态重新成立):
    # _run_task 起跑前查取消标记直接返回(宽窗口根修),各写 cancelled 的
    # 位置已 cancelled 就不再写(窄窗口防重写)。2026-11-27 评审曾登记四条
    # 竞态出边(downloading / loading / failed / cancelled):取消排队中
    # 任务与 worker 起跑之间没有互斥,worker 卡在 _run_task 开头的主机锁/
    # 源锁上时 cancel 先落 cancelled,worker 拿到锁后把状态翻回在飞,随后
    # 靠已取消的 token 落回 cancelled——窗口分析与成因见 #484 评审、#488
    # 工单。根修后这四条都不再发生——再现即新竞态形状,修代码,不是
    # 回填登记。记录模式下从本状态出发的写入一律拒写(NO_WRITE_FROM,
    # #488 评审建议改 2):拒写不会卡住任务(已 settle),放写才会翻回在飞。
    "cancelled": frozenset(),
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


# ── 处置 ───────────────────────────────────────────────────────────────────

# 非法转移错误日志的固定前缀(日后接告警按它 grep / 过滤)。
ILLEGAL_TRANSITION_LOG_PREFIX = "illegal-state-transition"

# 记录模式下「拒写」的出发态 = 终态三态(done/failed/cancelled;#484 返工
# 评审第 2 条,#488 评审建议改 2 把 cancelled 并入,主会话采纳 2026-11-28)。
# 理由与 done/failed 一字不差:出发态已是终态,_settle/批次计数/on_terminal
# 都已做完,拒写不会把任务留在在飞态(没有卡死面);而放写的代价是状态
# 能离开终态——本票清边后,从 cancelled 出发的写入只可能来自残余竞态
# (写点条件是正门,非原子先读后写的窗口见 #488 评审记一笔 2),放写会
# 把已取消任务翻回在飞(cancelled → downloading 重新压住查询门,下载再抛
# 普通异常还会落假 failed 升退避)。非终态出发的非法写入照写,否则任务
# 可能被留在在飞态卡住查询门和批次。
NO_WRITE_FROM: frozenset[str] = frozenset({"done", "failed", "cancelled"})

# 类别闸的允许新状态集(返工评审第 4 条):源任务不可进 running(退出在飞
# 集合 = 查询门放行、start_ops_round 查不到它、轮次与源更新互斥失效);
# 运营轮任务只许相位词表(running + 终态)。两个常量也把 SOURCE_ONLY /
# OPS_ROUND_ONLY 两组词表之差用到了实处。
SOURCE_TASK_ALLOWED_NEW: frozenset[str] = SOURCE_ONLY_TASK_STATES | TASK_STATES_TERMINAL
OPS_TASK_ALLOWED_NEW: frozenset[str] = OPS_ROUND_ONLY_STATES | TASK_STATES_TERMINAL

_strict: bool = False            # 缺省 = 记录模式(生产);测试套件经 conftest setattr 打开
_illegal_count: int = 0          # 记录模式下记下的非法转移次数(进程级)
_count_lock = threading.Lock()


def illegal_transition_count() -> int:
    """记录模式下记下的非法转移累计次数(严格模式抛错的不计)。"""
    with _count_lock:
        return _illegal_count


def _enforce(kind: str, table: dict[str, frozenset[str]], vocab: tuple[str, ...],
             subject: str, old: str, new: str,
             _reason: Optional[str] = None) -> bool:
    """守门本体:合法(或放行)返回 True = 照写;返回 False = 拒写(仅记录
    模式下从 NO_WRITE_FROM 终态出发的非法写入;严格模式照旧抛错)。
    _reason = 调用方已算好的违规说明(类别闸等表外规则),缺省自己判表。"""
    global _illegal_count
    if _reason is None:
        _reason = _transition_error(kind, table, vocab, old, new)
    if _reason is None:
        return True
    if _strict:
        raise ValueError(f"{_reason} [{subject}] (strict mode)")
    with _count_lock:
        _illegal_count += 1
    logger.error("%s: %s [%s]", ILLEGAL_TRANSITION_LOG_PREFIX, _reason, subject)
    return old not in NO_WRITE_FROM


def enforce_task_transition(task_id: str, source_name: str, old: str, new: str) -> bool:
    """任务状态写入口的守门:表判转移(登记边)+ 类别闸(返工评审第 4 条),
    合法或放行返回 True;非法按模式抛错或记日志 + 计数(终态出发再拒写,
    见 NO_WRITE_FROM)。带任务号与源名——两者都要进错误信息和日志。"""
    reason = _transition_error("task", TASK_TRANSITIONS, TASK_STATES, old, new)
    if reason is None:
        # 类别闸:表不看任务类别(queued → running 对运营轮是出生边,对源
        # 任务是禁入),这里按 source_name 再限一道。
        if source_name == OPS_ROUND_SOURCE:
            if new not in OPS_TASK_ALLOWED_NEW:
                reason = (f"ops-round task cannot enter state {new!r}: allowed "
                          f"targets for this task kind: {sorted(OPS_TASK_ALLOWED_NEW)}")
        elif new not in SOURCE_TASK_ALLOWED_NEW:
            reason = (f"source task cannot enter state {new!r}: allowed targets "
                      f"for this task kind: {sorted(SOURCE_TASK_ALLOWED_NEW)}")
    if reason is None:
        return True
    return _enforce("task", TASK_TRANSITIONS, TASK_STATES,
                    f"task={task_id} source={source_name}", old, new,
                    _reason=reason)


def enforce_batch_transition(batch_id: str, old: str, new: str) -> bool:
    """批次状态写入口的守门,同 enforce_task_transition(无类别闸;批次终态
    done 出发的写入同样按 NO_WRITE_FROM 拒写)。"""
    return _enforce("batch", BATCH_TRANSITIONS, BATCH_STATES,
                    f"batch={batch_id}", old, new)
