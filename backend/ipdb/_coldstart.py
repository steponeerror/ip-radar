"""#294 冷启动门(建库期间挡查询、到点放行的状态机)。

历史:这段状态机原住 backend/main.py 模块级全局变量(_BUILD_DEADLINE/
_coverage_episode/_build_window_sec + _coverage_building/_db_ready,
2026-11-03 前在 main.py:142-226)——规则散在 main 里不可单测。本模块把它
收成显式门:探针全部可注入(时钟 now、任务活跃探针、_db_loaded 探针、
_enabled_sources 探针、窗口秒计算),状态只有 deadline + episode 两件,
对外 db_ready()/blocking_reason()。

铁律:require_ready 与 db-status 的 warming_up 字段必须共用同一扇门实例
的单一真相(历史口径见 main.py require_ready 注释)。

reason 串字面值是跨栈契约(X-IPRadar-Reason 头 / 信封语义码 / 前端
LookupView 的 code 判定),前端以钉子测试机读本模块对拍,勿改字面。
"""
import math
import os

# X-IPRadar-Reason 头值;main._reason_code 再映到信封语义码
# ("warming"/"no_sources",连字符→下划线)。
REASON_WARMING = "warming"
REASON_NO_SOURCES = "no-sources"


def _cold_start_timeout(total_gb: float) -> int:
    """超时分档(B2)。env 覆盖。"""
    env_val = os.environ.get("IP_RADAR_COLD_START_TIMEOUT", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    if total_gb < 6:
        return 1800
    if total_gb < 12:
        return 1200
    return 900


class ColdStartGate:
    """显式冷启动门:输入=注入的探针(即时快照),输出=ready/reason。

    状态(仅两件,测试可直读直设以摆场景):
      deadline — 强制放行时刻;inf = 未臂(暖视景)
      episode  — 上次探测是否处于覆盖构建段(边沿探测用)
    """

    def __init__(self, *, now, tasks_active, db_loaded,
                 enabled_sources, compute_window_sec):
        self.now = now
        self.tasks_active = tasks_active
        self.db_loaded = db_loaded
        self.enabled_sources = enabled_sources
        self.compute_window_sec = compute_window_sec
        self.deadline = math.inf
        self.episode = False
        self._window_sec_cache: float | None = None

    def window_sec(self) -> float:
        """冷启窗口策略超时(内存分档,env 覆盖),惰性算一次缓存
        (历史 _build_window_sec 同律:进程生命期内内存档不变)。"""
        if self._window_sec_cache is None:
            self._window_sec_cache = self.compute_window_sec()
        return self._window_sec_cache

    def arm_from_now(self):
        """显式预臂:冷启动 _startup 在首批探测前先把窗锚到进程起点
        (慢启动的 build 也从进程起算,而非首探针时刻)。"""
        self.deadline = self.now() + self.window_sec()

    def coverage_building(self) -> bool:
        """有在飞离线任务、且其目标仍有未加载读器 → 覆盖构建中。
        已加载源的刷新/重建永不门控(安定部署例行刷新期间照常服务)。
        paused 批保活语义在 tasks_active 探针里(queued/downloading/
        loading/throttled/paused 口径,main 接 manager.has_active_offline_tasks)。"""
        if not self.tasks_active():
            return False
        loaded = {s.name for s in self.enabled_sources() if s.health().loaded}
        return self.tasks_active(lambda n: n not in loaded)

    def reset(self):
        """回暖视景:deadline=inf、无段(测试摆场/进程重启语义;
        窗口缓存保留 —— 内存档进程生命期内不变)。"""
        self.deadline = math.inf
        self.episode = False

    def blocking_reason(self):
        """查询被挡原因:"no-sources" / "warming" / None(放行)。

        零启用源不是 warming(诚实报错口径,require_ready 与 warming_up
        共用本判定);其余按 db_ready()。"""
        if not self.enabled_sources():
            return REASON_NO_SOURCES
        if not self.db_ready():
            return REASON_WARMING
        return None

    def db_ready(self):
        """积分门,按状态:(a) 零覆盖 → 持门(绝不放空库净白判定,
        窗过期也不放);(b) 覆盖构建中且在已臂的 deadline 内 → 持门 ——
        首个源的重建热换把 _db_loaded() 翻 True 也不算够,门中途不开
        (防段中放部分覆盖判定);deadline 已过 → 强制放行。

        deadline 生命周期(单点):新 build 段(暖启动 PATCH-enable /
        day-2 重建 / settle 后 Retry)在首次探测 fresh arm;continuing
        段保原 deadline —— 超时即放行不滑窗(暂停中的 build 也在原点
        到点放行;裁决 2026-08-18 #9 继承段时钟)。"""
        building = self.coverage_building()
        if building and not self.episode:
            self.deadline = self.now() + self.window_sec()
        self.episode = building
        if not self.db_loaded():
            return False  # 零覆盖:持门
        if building and self.now() < self.deadline:
            return False
        return True
