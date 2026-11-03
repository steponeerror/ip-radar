"""#294 冷启动门单元测试:门状态机搬进 ipdb._coldstart 后的生命周期规则。

门的历史形态 = backend/main.py 模块级全局变量(_BUILD_DEADLINE/
_coverage_episode,2026-11-03 前住 main.py:142-226),本文件把那些规则的
行为钉在新模块的公开接口上(探针全注入,fake 时钟):

  - blocking_reason() 的三值域:warming / no-sources / None
  - deadline 生命周期:新 build 段 fresh arm(False→True 边沿) /
    continuing 段保原 deadline / 超时强制放行
  - 零覆盖恒持门(即使窗已过,也绝不放空库净白判定)
  - 窗口秒惰性算一次缓存
  - 显式预臂(冷启动 _startup 用)
"""
import math
from types import SimpleNamespace

from ipdb import _coldstart


class FakeClock:
    """可拨动的假时钟:门只信注入的 now()。"""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Src:
    """最小 registry source 形状:name + health().loaded。"""

    def __init__(self, name, loaded):
        self.name = name
        self._loaded = loaded

    def health(self):
        return SimpleNamespace(loaded=self._loaded)


def make_gate(*, now=None, tasks_active=None, db_loaded=False,
              sources=(), window=600):
    """全注入假探针构造一扇新门(暖视景:deadline=inf,无段)。"""
    return _coldstart.ColdStartGate(
        now=now or FakeClock(),
        tasks_active=tasks_active or (lambda source_filter=None: False),
        db_loaded=lambda: db_loaded,
        enabled_sources=lambda: list(sources),
        compute_window_sec=lambda: window,
    )


def test_reason_constants_are_the_wire_contract():
    """reason 串是跨栈契约(X-IPRadar-Reason 头 + 前端钉子对拍源),
    字面值以已知好值为准(测试既有 header 断言与 spec)。"""
    assert _coldstart.REASON_WARMING == "warming"
    assert _coldstart.REASON_NO_SOURCES == "no-sources"


def test_zero_enabled_sources_reasons_no_sources_even_while_building():
    """零启用源不是 warming(require_ready 的诚实报错语义):无论覆盖
    构建/加载状态如何,reason 恒 no-sources。"""
    gate = make_gate(sources=[], db_loaded=False,
                     tasks_active=lambda source_filter=None: True)
    assert gate.blocking_reason() is _coldstart.REASON_NO_SOURCES


def test_zero_coverage_holds_forever_even_past_deadline():
    """零覆盖恒持门:_db_loaded() False 时永不放行(绝不放空库净白
    判定)——窗过期也不放(超时即放行只救已加载库上的构建楔死)。"""
    gate = make_gate(sources=[Src("a", True)], db_loaded=False)
    gate.deadline = gate.now.t - 1  # 窗早已过
    assert gate.db_ready() is False
    assert gate.blocking_reason() is _coldstart.REASON_WARMING


def test_loaded_and_idle_reasons_none():
    """库已载且无覆盖构建:放行,reason None。"""
    gate = make_gate(sources=[Src("a", True)], db_loaded=True)
    assert gate.db_ready() is True
    assert gate.blocking_reason() is None


def test_new_build_episode_arms_fresh_window_on_false_to_true_edge():
    """新 build 段 fresh arm:首次探测见 building(=覆盖构建中)且
    episode 仍 False → 重臂 deadline = now + window;之后段内探测不重臂。
    (暖启动 PATCH-enable / day-2 重建 / Retry —— 任何入口,门是状态驱动的。)"""
    clock = FakeClock(1000.0)
    gate = make_gate(now=clock, sources=[Src("a", False)], db_loaded=True,
                     tasks_active=lambda source_filter=None: True, window=600)
    assert gate.db_ready() is False            # held
    assert gate.deadline == 1000.0 + 600       # fresh arm at first probe
    assert gate.episode is True
    # 段内时钟推进、再探测:保持原 deadline(不重臂)
    clock.t = 1005.0
    assert gate.db_ready() is False
    assert gate.deadline == 1600.0


def test_continuing_episode_keeps_original_deadline_no_rearm():
    """continuing 段保原 deadline:段时钟属「连续构建期」而非单源
    (裁决 2026-08-18,#9 继承段时钟)——按源/按 enqueue 重臂会复活
    toggle 滑窗楔死(disable/re-enable 循环无限推迟放行)。"""
    clock = FakeClock(1000.0)
    gate = make_gate(now=clock, sources=[Src("a", False)], db_loaded=True,
                     tasks_active=lambda source_filter=None: True, window=600)
    gate.episode = True                        # continuing 段(探测从未见 False→True)
    gate.deadline = 1300.0                     # 原段时钟(还在窗内)
    gate.db_ready()
    assert gate.deadline == 1300.0             # 不重臂


def test_deadline_elapsed_forces_release_even_while_building():
    """超时即放行:段在、窗已过 → 放行(楔死/暂停的 build 不得扣服务器
    为人质;暂停批保活的 queued 任务也拦不住到点放行)。"""
    clock = FakeClock(2000.0)
    gate = make_gate(now=clock, sources=[Src("a", False)], db_loaded=True,
                     tasks_active=lambda source_filter=None: True, window=600)
    gate.episode = True
    gate.deadline = 1999.0                     # 已过
    assert gate.db_ready() is True
    assert gate.blocking_reason() is None


def test_window_sec_computed_once_and_cached():
    """窗口秒惰性算一次缓存:多次臂窗/探测只即一次环境读取(内存档
    进程生命期内不变,历史 _build_window_sec 同律)。"""
    calls = []

    def compute():
        calls.append(1)
        return 600

    clock = FakeClock(1000.0)
    gate = _coldstart.ColdStartGate(
        now=clock, tasks_active=lambda source_filter=None: False,
        db_loaded=lambda: True, enabled_sources=lambda: [Src("a", True)],
        compute_window_sec=compute)
    gate.arm_from_now()
    gate.arm_from_now()
    clock.t = 9999.0
    gate.db_ready()
    gate.db_ready()
    assert calls == [1]
    assert gate.deadline == 1000.0 + 600       # arm 时刻锚定,不受后续时钟影响


def test_arm_from_now_anchors_window_at_process_start():
    """显式预臂(冷启动 _startup 用):窗从进程起点起算,而非首个
    探针时刻 —— 慢启动的 build 也被同一窗口兜底。"""
    clock = FakeClock(100.0)
    gate = make_gate(now=clock, window=1800)
    gate.arm_from_now()
    assert gate.deadline == 100.0 + 1800


def test_coverage_building_false_when_no_tasks():
    """无在飞任务 → 不在覆盖构建(安定态)。"""
    gate = make_gate(sources=[Src("a", False)], db_loaded=True,
                     tasks_active=lambda source_filter=None: False)
    assert gate.coverage_building() is False


def test_coverage_building_false_when_all_targets_loaded():
    """例行刷新永不门:在飞任务的目标全部已有加载读器 → 不是覆盖
    构建;且已加载集合滤器真的被口询过(不是被短路跳过)。"""
    calls = []

    def fake_active(source_filter=None):
        calls.append(source_filter)
        if source_filter is None:
            return True                        # 任务在跑
        return False                           # 但全落已加载集

    gate = make_gate(sources=[Src("a", True), Src("b", True)],
                     db_loaded=True, tasks_active=fake_active)
    assert gate.coverage_building() is False
    assert calls[-1] is not None               # 滤器被真口询


def test_coverage_building_true_when_unloaded_target_in_flight():
    """在飞任务落在未加载读器的源上 → 覆盖构建中(首个重建热换
    _db_loaded=True 之前/之中,门都持着)。"""
    gate = make_gate(sources=[Src("a", True), Src("b", False)], db_loaded=True,
                     tasks_active=lambda source_filter=None:
                         source_filter is None or source_filter("b"))
    assert gate.coverage_building() is True


def test_reset_restores_warm_view():
    """reset 回暖视景(deadline=inf,无段)——测试摆场与进程重启语义。"""
    gate = make_gate(sources=[Src("a", False)], db_loaded=True,
                     tasks_active=lambda source_filter=None: True)
    gate.db_ready()
    assert gate.deadline != math.inf and gate.episode is True
    gate.reset()
    assert gate.deadline == math.inf and gate.episode is False
