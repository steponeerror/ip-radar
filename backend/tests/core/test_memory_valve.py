"""MemoryValve: can_run 判定 + throttled 语义。用 monkeypatch psutil。"""
import threading
import time
from ipdb._memory_valve import MemoryValve, initial_capacity


def _wait_until(predicate, timeout, msg):
    """#378:采样线程只暴露 target 值、无完成钩子——固定 sleep 窗口在门上下文
    (node+pytest 并行)线程调度延迟下偶红;改带 deadline 轮询:20ms 步进,
    deadline 取原窗口 10 倍,真值到达即返回,超时才以 msg 失败。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    assert predicate(), msg


def _set_mem(monkeypatch, available_gb, total_gb=8.0):
    class _VM:
        def __init__(self, avail): self.available = avail; self.total = total_gb * 1e9
    monkeypatch.setattr("ipdb._memory_valve.psutil.virtual_memory",
                        lambda: _VM(available_gb * 1e9))


def test_can_run_within_capacity(monkeypatch):
    """未达容量,可跑。"""
    _set_mem(monkeypatch, available_gb=6.0)
    v = MemoryValve(ceiling=3)
    assert v.can_run() is True


def test_can_run_blocked_at_capacity(monkeypatch):
    """活跃数达 target_capacity,不可跑。"""
    _set_mem(monkeypatch, available_gb=6.0)
    v = MemoryValve(ceiling=3)
    v.target_capacity = 1
    v.on_start()
    assert v.can_run() is False   # active=1 == cap
    v.on_finish()
    assert v.can_run() is True


def test_target_capacity_capped_at_ceiling(monkeypatch):
    """target_capacity 永不超过 ceiling。"""
    v = MemoryValve(ceiling=1)                          # 6GB 机 ceiling=1
    v.target_capacity = 1
    # 即使内存很宽裕,update 也不能升超 ceiling
    _set_mem(monkeypatch, available_gb=7.0, total_gb=8.0)
    v.update_from_sample()                              # ratio=87% 但 ceiling=1
    assert v.target_capacity == 1


def test_initial_capacity_tiers():
    """initial_capacity 分档:<6G→1 / <12G→2 / ≥12G→3。"""
    assert initial_capacity(4.0) == 1
    assert initial_capacity(5.999) == 1
    assert initial_capacity(6.0) == 2
    assert initial_capacity(11.999) == 2
    assert initial_capacity(12.0) == 3
    assert initial_capacity(32.0) == 3


def test_sampler_throttles_on_low_memory(monkeypatch):
    """内存跌破 25%,采样线程把 target 调到 1。"""
    _set_mem(monkeypatch, available_gb=1.5, total_gb=8.0)   # 18.75% < 25%
    v = MemoryValve(ceiling=3)
    v.target_capacity = 3
    cv = threading.Condition()
    stop = threading.Event()
    v.start_sampler(cv, stop, interval=0.05)
    _wait_until(lambda: v.target_capacity == 1, timeout=2.0,
                msg=f"sampler did not throttle to 1 (target={v.target_capacity})")
    stop.set()
    assert v.target_capacity == 1


def test_sampler_relaxes_on_high_memory(monkeypatch):
    """内存 ≥40% 连续2次,target 升一档(不超 ceiling)。"""
    _set_mem(monkeypatch, available_gb=7.0, total_gb=8.0)   # 87.5% ≥ 40%
    v = MemoryValve(ceiling=2)   # ceiling=2 cap, so 1→2 holds despite 6 samples
    v.target_capacity = 1
    cv = threading.Condition()
    stop = threading.Event()
    v.start_sampler(cv, stop, interval=0.05)
    _wait_until(lambda: v.target_capacity == 2, timeout=3.0,
                msg=f"sampler did not relax to 2 (target={v.target_capacity})")
    stop.set()
    assert v.target_capacity == 2


def test_sampler_critical_halt(monkeypatch):
    """内存 <12%,target=0。"""
    _set_mem(monkeypatch, available_gb=0.5, total_gb=8.0)   # 6.25% < 12%
    v = MemoryValve(ceiling=3)
    cv = threading.Condition()
    stop = threading.Event()
    v.start_sampler(cv, stop, interval=0.05)
    _wait_until(lambda: v.target_capacity == 0, timeout=2.0,
                msg=f"sampler did not halt to 0 (target={v.target_capacity})")
    stop.set()
    assert v.target_capacity == 0


def test_hold_band_recovers_from_zero(monkeypatch):
    """target=0 (CRITICAL) 后内存恢复到 25-40% hold band,target 应恢复到 ≥1。

    没有 floor 时,target 卡在 0 直到内存降到 <25%(→1)或升到 ≥40%(→slow +1)，
    导致 30% 可用内存时 rebuild 全部停摆。
    """
    _set_mem(monkeypatch, available_gb=2.8, total_gb=8.0)   # 35% — hold band
    v = MemoryValve(ceiling=3)
    v.target_capacity = 0   # 模拟刚从 CRITICAL 恢复
    v.update_from_sample()
    assert v.target_capacity >= 1, \
        f"hold band should recover target from 0, got {v.target_capacity}"


def test_critical_requires_two_consecutive_samples(monkeypatch):
    """单次 <12% 毛刺不归零(滞回);连续两次才 0——2026-10-11 demo 机
    avail 11.9↔12.1% 抖动致 0↔1 每两秒横跳(容器日志实测)。"""
    v = MemoryValve(ceiling=1)
    v.target_capacity = 1
    _set_mem(monkeypatch, available_gb=0.9, total_gb=8.0)   # 11.25% < 12%
    v.update_from_sample()
    assert v.target_capacity == 1, "single sub-critical blip must not zero"
    v.update_from_sample()
    assert v.target_capacity == 0, "two consecutive must zero"


def test_critical_counter_resets_on_recovery(monkeypatch):
    """毛刺后回到 ≥12%,计数清零;再单次低压仍不归零。"""
    v = MemoryValve(ceiling=1)
    v.target_capacity = 1
    _set_mem(monkeypatch, available_gb=0.9, total_gb=8.0)   # 11.25%
    v.update_from_sample()                                   # count=1
    _set_mem(monkeypatch, available_gb=1.5, total_gb=8.0)   # 18.75%(THROTTLE 清零)
    v.update_from_sample()
    _set_mem(monkeypatch, available_gb=0.9, total_gb=8.0)
    v.update_from_sample()                                   # count=1 重新起算
    assert v.target_capacity == 1


def test_alternating_blips_stay_throttled(monkeypatch):
    """11.25%↔12.5% 交替(实测形状)→ 恒 1,永不 0。"""
    v = MemoryValve(ceiling=1)
    v.target_capacity = 1
    for _ in range(6):
        _set_mem(monkeypatch, available_gb=0.9, total_gb=8.0)
        v.update_from_sample()
        _set_mem(monkeypatch, available_gb=1.0, total_gb=8.0)   # 12.5%
        v.update_from_sample()
    assert v.target_capacity == 1


def test_sampler_survives_psutil_exception(monkeypatch):
    """psutil.virtual_memory() 抛异常时,采样线程不应死亡。

    无 try/except 时,一次异常 = 线程退出 = valve 永久冻结在最后 target 值。
    """
    import time
    call_count = [0]

    def _flaky_virtual_memory():
        call_count[0] += 1
        raise PermissionError("simulated /proc failure")

    monkeypatch.setattr("ipdb._memory_valve.psutil.virtual_memory",
                        _flaky_virtual_memory)
    v = MemoryValve(ceiling=2)
    v.target_capacity = 1   # 初始值
    cv = threading.Condition()
    stop = threading.Event()
    v.start_sampler(cv, stop, interval=0.05)
    _wait_until(lambda: call_count[0] >= 3, timeout=3.0,
                msg=f"sampler made only {call_count[0]} calls")
    stop.set()
    assert call_count[0] >= 3, \
        f"sampler thread died after first exception (only {call_count[0]} calls)"
    assert v.target_capacity == 1, \
        f"target should stay at last value, got {v.target_capacity}"
