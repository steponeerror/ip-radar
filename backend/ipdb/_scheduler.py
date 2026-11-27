"""Background auto-refresh scheduler.

A single daemon thread that scans enabled offline sources every `interval`
seconds and enqueues each at its deterministic 12h-grid slot when due
(`_due_at`; daily tier twice a day; periods beyond the 12h grid lead
their target slot by one full grid — #398) — or
immediately, behind the backoff gate, for partial-tolerant multi-feed
sources with a standing feed failure (spec 2026-10-02 §2.3) — via
enqueue_one_detached (batch_id=None, so scheduler tasks never pollute an
in-flight manual batch).
Backoff is inferred on the NEXT scan: a float-mtime diff plus one task_state
lookup distinguishes "didn't run yet" (valve-throttled) from "ran and failed".

Started/stopped from main.lifespan, mirroring _ensure_valve_sampler.
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import _alerts
from ._task_state import TASK_STATES_IN_FLIGHT

logger = logging.getLogger(__name__)

# Backoff seconds for fail_count 1..5: 1h, 2h, 4h, 8h, 12h (cap).
_BACKOFF_SECONDS = [3600, 7200, 14400, 28800, 43200]

SLOT_GRID = 43200  # 12h slot grid — per-source deterministic refresh anchors
# ponytail: guard covers slot-fire→file-mtime lag (scan ≤1800s + download);
# downloads >1h skip one slot that day and self-recover next cycle
REFRESH_GUARD = 3600


def _slot_of(name: str) -> int:
    """Deterministic per-source offset within the 12h grid (0..SLOT_GRID-1)."""
    return int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % SLOT_GRID


def _period_of(stale_days: int) -> int:
    """Tier period: daily (stale_days<=1) → 12h (twice a day); else stale_days days."""
    return SLOT_GRID if stale_days <= 1 else stale_days * 86400


def _due_at(name: str, mtime: float, stale_days: int) -> float:
    """First slot strictly after (mtime + period - guard [- lead]).

    The guard absorbs slot-fire→mtime lag. Without it, mtime always trails the
    slot point, so each cycle's first_slot lands one grid further out: daily
    sources drift to 24h/cycle and weekly to 7.5d with +12h wall-clock drift.
    #398 (2026-11-22): the drift alone already pushes real weekly cycles past
    the stale alert line (stale_days×24h, _alerts.stall_threshold_h floor) —
    queue+download lag beyond the guard (964MB-box valve queues, commonly >1h)
    made every cycle cross it, flapping a stale alert + auto-recovery weekly.
    Fix: periods longer than the grid lead by one full slot (deadline −
    SLOT_GRID). Margin map (#398 review hand-calc): lag ≤ guard → ≈6.5d
    cycles, ≈11h under the line; lag > guard → cycle pinned at exactly
    stale_days×24 and still never fires, because scan age is strictly
    < cycle and the alert predicate is strictly age > stale_days×24;
    residual = lag rising between rounds (Δlag > 30-min scan step) → an
    occasional one-off alert, accepted for observation. Daily tier
    (period == grid) keeps the legacy formula bit-for-bit: a lead there
    leaves every scan overdue (refresh storm).
    """
    slot = _slot_of(name)
    period = _period_of(stale_days)
    # #398(2026-11-22 判例):周期>12h 档目标槽位提前一整格——槽位网格+排队下载延迟
    # (964MB 小机内存阀门排队,实测常见>1h)使实际周期滑到 7.5d,越过 7.0d stale
    # 告警线,每周期必抖一轮告警+恢复。提前一格:延迟≤guard 档周期≈6.5d(余量≈11h);
    # 延迟>guard 档周期钉在恰 stale_days×24——扫描年龄恒严格小于周期、告警谓词是
    # 严格 age>线,最坏相位仍不触发(#398 评审手算);残余=轮间延迟上升(增量>30min
    # 扫描步长)偶发单轮告警,已裁接受,观察窗盯 1-3h 延迟带。
    # 日更档(period=12h=网格)不适用:提前一格=恒到期刷新风暴。
    lead = SLOT_GRID if period > SLOT_GRID else 0
    deadline = mtime + period - lead - REFRESH_GUARD
    first_slot = (deadline // SLOT_GRID) * SLOT_GRID + slot
    if first_slot <= deadline:
        first_slot += SLOT_GRID
    return first_slot


@dataclass
class _Backoff:
    fail_count: int
    next_attempt: float
    # 失败模式分类(2026-10-17 用户裁定:告警分报下载/构建失败):"download"
    # /"rebuild"/""(缺省 = 旧通用文案,兼容存量路径)。
    kind: str = ""
    # 双计数(2026-10-17 裁定修):逐 kind 连败数——kind 切换重归 1,同 kind
    # +1;只驱动告警文案 ×N。fail_count 是任意类连败总数,kind 切换不
    # 重置(≥2 告警/恢复判定/退避计时梯全由总数驱动)。
    kind_count: int = 1
    # 当次失败原因(#371:告警带失败原因):当次失败 task 的 error 尾摘
    # (空白折叠、截 ~200 字);成功路径 pop 整个退避项即随之清空。
    error: str = ""


class RefreshScheduler:
    def __init__(self, manager, enabled_offline_sources: Callable[[], list],
                 needs_rebuild_of: Callable[[object], bool], interval: int = 1800,
                 on_scan: Optional[Callable[[list, float], None]] = None):
        self._manager = manager
        self._enabled_offline_sources = enabled_offline_sources
        self._needs_rebuild_of = needs_rebuild_of
        self._interval = interval
        # P1 T2 超龄探测器旁挂(票 #154,spec #152 §2):每轮扫描尾回调
        # (enabled_sources, now) 只读消费;None = 位等价(既有测试零变化)。
        # 装配在 main.lifespan(_ops_detectors.run_staleness_detector),
        # 本模块零存储依赖;回调异常独立吞掉(仿告警周期兑错律)。
        self._on_scan = on_scan
        self._last_task: dict[str, str] = {}
        self._last_attempt: dict[str, float] = {}
        self._baseline_mtime: dict[str, Optional[float]] = {}
        self._backoff: dict[str, _Backoff] = {}
        self._last_scan_at: Optional[float] = None
        # #478:跑扫描循环的线程(start() 装入,循环退出即清)——
        # auto_refresh_status() 的 running 依据;直接调 scan() 的测试路径
        # 不经过 start(),running 恒 False。
        self._thread: Optional[threading.Thread] = None

    # --- public ---
    def start(self, stop_event: threading.Event) -> None:
        """Run the scan loop until stop_event is set. Blocks the caller."""
        # #478:记下本线程供 auto_refresh_status() 查 running;收到 stop
        # 循环退出即清(调度器被停后状态口如实报不在跑)。
        self._thread = threading.current_thread()
        try:
            while not stop_event.wait(timeout=self._interval):
                try:
                    self.scan()
                except Exception:
                    logger.exception("scheduler scan raised; continuing")
        finally:
            self._thread = None

    def auto_refresh_status(self, now: Optional[float] = None) -> dict:
        """「服务会不会自动刷新」公开查询面(#478:/api/db-status 的
        auto_refresh 段由此出,调用方不得拿 _last_scan_at 等私有名)。

        enabled 恒 True:本对象被构造即配置上已开 —— 装配门在 main
        ._ensure_refresh_scheduler(IPRADAR_AUTO_REFRESH=0 时根本不构造),
        关停态的四项(False/False/None/None)由调用方给字面。running =
        扫描线程在不在跑;last_scan_age_s 还没扫过 → null,否则距上次
        扫描的秒数 —— 口径是扫描「开始」时刻(scan() 一进来就记
        _last_scan_at,不等扫完;返工评审建议 11),不是扫完时刻。"""
        if now is None:
            now = time.time()
        t = self._thread
        return {
            "enabled": True,
            "running": t is not None and t.is_alive(),
            "interval_s": self._interval,
            "last_scan_age_s": None if self._last_scan_at is None
            else max(0.0, now - self._last_scan_at),
        }

    def scan(self, now: Optional[float] = None) -> None:
        """One scan pass. Public so tests can drive it deterministically."""
        if now is None:
            now = time.time()
        self._last_scan_at = now
        for source in self._enabled_offline_sources():
            name = source.name
            try:
                # ── 内容更新事件记账(#455,原种子块与 reconcile 记账并入
                # 这一处):每轮对每个启用源比一次数据文件 mtime,比账本
                # 水位(source_watermark 表,重启不丢)新才记一条,at 用
                # 文件自己的修改时间。谁触发的落盘都算——调度器任务、页面
                # 手动/批量、冷启动建库、脚本一视同仁;mtime None(无文件)
                # 跳过。放在 _reconcile 之前:记账只认文件事实,与调度任务
                # 的内存状态无关。record_count 尽力取 health()(读不到如
                # epoch 损坏 → 事件照记,计数留空)。独立兜错:告警侧故障
                # 不碰下方调度逻辑。
                try:
                    obs_mtime = self._read_mtime(source)
                    if obs_mtime is not None:
                        try:
                            rc = source.health().record_count
                        except Exception:
                            rc = None
                        # #467:指纹经 content_hash_of 延迟传入——记不记由
                        # observe_update 内部比水位决定,只在要落新事件时才
                        # 调到(平时扫描不算指纹,见 observe_update 注)。
                        _alerts.observe_update(
                            name, obs_mtime, record_count=rc,
                            content_hash_of=lambda: self._content_fingerprint_of(source))
                except Exception:
                    logger.exception(
                        "scheduler: update observation failed for %s; continuing",
                        name)
                had_task = name in self._last_task
                self._reconcile(name, source, now)
                if had_task:
                    continue  # just resolved (or still tracking); re-eligible next scan
                b = self._backoff.get(name)
                if b is not None and now < b.next_attempt:
                    continue  # still backing off
                partial = self._partial_failure_of(source)
                rebuild_only = False
                if partial is None and not self._needs_rebuild_of(source):
                    # needs_rebuild is immediate (local integrity, no quota).
                    # Otherwise: slot-based due. mtime None (download-failure
                    # residue) is immediately due; backoff throttles retries.
                    # A standing partial failure (partial-tolerant multi-feed
                    # source: overall done, some feeds failed) is likewise due
                    # now — the slot check keys on the dir mtime, which any
                    # landed feed advances, hiding the dead one (spec
                    # 2026-10-02 §2.3); the backoff gate above paces it.
                    mtime = self._read_mtime(source)
                    if mtime is not None and now < _due_at(
                            name, mtime, source.stale_days):
                        continue
                elif partial is None:
                    # needs_rebuild 立即车道(2026-10-14 收敛批):raw 已最新
                    # 只欠重建,重抓是纯浪费 → rebuild-only 跳下载。partial
                    # 车道相反(死 feed 要重抓)、slot 车道有新内容要抓,
                    # 均不传。needs_rebuild=True 蕴含 raw 在,故 _run_task
                    # 的 raw 缺失回退分支在此仅是防御。
                    rebuild_only = True
                task = self._manager.enqueue_one_detached(
                    name, rebuild_only=rebuild_only)
                self._last_task[name] = task.id
                self._last_attempt[name] = now
                self._baseline_mtime[name] = self._read_mtime(source)
            except Exception:
                logger.exception("scheduler: error processing source %s; skipping", name)

        # ── 告警周期(Task 4):快照 → evaluate → push → prune ──
        # 独立 try/except:告警侧任何异常只 log,scheduler 永不因告警死
        # (约束 5 同精神,把评估/存储/推送一并兑住)。快照必须是 enabled
        # 源全集——缺失的源会被 evaluate 静默清状态。
        try:
            snapshots = []
            for source in self._enabled_offline_sources():
                mtime = self._read_mtime(source)
                b = self._backoff.get(source.name)
                ptr = getattr(source, "_mmdb_path", None)   # ptr 文件(registry/scheduler 契约名)
                snapshots.append({
                    "name": source.name,
                    "stale_days": source.stale_days,
                    # mtime None(无文件)→ content_age_h None = 视为 ∞ 必触发
                    "content_age_h": None if mtime is None
                    else (now - mtime) / 3600.0,
                    "fail_count": b.fail_count if b is not None else 0,
                    # 2026-10-17 裁定:失败分类随快照交给告警渲染(缺省 ""
                    # = 旧「连续 N 次更新失败」通用文案);×N 口径 = 逐 kind 连败
                    # 数 fail_kind_count(裁定修:kind 切换重归 1,只动文案)
                    "fail_kind": b.kind if b is not None else "",
                    "fail_kind_count": b.kind_count if b is not None else 0,
                    # #371:当次失败原因随快照交给告警渲染(缺省 "" = 旧行
                    # 无原因段,位等价);只加键,既有键名不动。
                    "fail_error": b.error if b is not None else "",
                    # OL-4:epoch 损坏不得静默缺席——ptr 在(库已建成)而
                    # reader None(load 抛)即降级告警;不触发自动 rebuild(人裁)
                    "reader_error": ptr is not None and ptr.exists()
                    and not source.health().loaded,
                })
            # S6:env 给心跳路径才查月轮心跳过期(未设 None = 旧有行为不变);
            # 时基独立 —— 生产侧只看文件 mtime,不采信管线自报时间。
            msg = _alerts.evaluate(
                snapshots, now, eval_heartbeat=_alerts._heartbeat_path())
            if msg is not None:
                _alerts.push(msg["title"], msg["body"])
            _alerts.prune(now)
        except Exception:
            logger.exception("scheduler: alert cycle raised; continuing")

        # ── P1 T2 超龄探测器旁挂(票 #154):扫描尾只读回调,独立兑错 ──
        # (探测面故障只 log,调度行为零影响;默认 None = 位等价)。
        if self._on_scan is not None:
            try:
                self._on_scan(self._enabled_offline_sources(), now)
            except Exception:
                logger.exception("scheduler: on_scan hook raised; continuing")

    def _reconcile(self, name: str, source, now: float) -> None:
        """Infer the previous cycle's outcome. No-op if name not in _last_task."""
        task_id = self._last_task.get(name)
        if task_id is None:
            return
        current = self._read_mtime(source)
        baseline = self._baseline_mtime.get(name)
        if current != baseline:
            # file was rewritten -> download landed; integrity still to check
            if self._partial_failure_of(source) is not None:
                # done-but-partial: the overall download succeeded and mtime
                # advanced, but some feeds failed — escalate backoff instead
                # of clearing it, so the dead feeds keep the 1h..12h retry
                # pacing instead of waiting out the full stale period (spec
                # 2026-10-02 §2.3 self-heal; final-review Important #1).
                self._escalate_backoff(name, now, kind="download",
                                       error=self._task_error_tail(task_id))
            elif self._needs_rebuild_of(source):
                # 2026-10-14 demo 五源自增强环:mtime 前进(下载成功)但 ptr
                # 未推进(rebuild 被 memory valve 卡住/纪元冻结)= 完整性未
                # 恢复;归成功清退避会失去唯一刹车 → 每 30min scan 全量重抓
                # (ipinfo 330MB/轮)。升退避 1h→12h 梯;ptr 推进后自动回
                # else 清退避,正常槽位节奏不受影响。ptr 冻结 = 构建未成
                # → kind=rebuild(2026-10-17 裁定)。
                self._escalate_backoff(name, now, kind="rebuild",
                                       error=self._task_error_tail(task_id))
            else:
                self._backoff.pop(name, None)
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            # 内容变化的事件记账已上收进 scan() 开头的 observe_update(#455):
            # 本分支只管调度状态收敛(退避/任务跟踪),不再记账。
            return
        # mtime unchanged -> classify by terminal state
        state = self._manager.task_state(task_id)
        # 在飞四态引用词表(#484,原手抄元组 _NON_TERMINAL)。调度器只跟踪自己
        # enqueue 的源任务 id,ops 轮的 running 不会出现在这里。
        if state in TASK_STATES_IN_FLIGHT or state is None:
            # didn't run yet (throttled) or task evicted -> leave _last_task to retry reconcile
            if state is None:
                self._last_task.pop(name, None)
                self._baseline_mtime.pop(name, None)
            return
        if state == "failed":
            # 失败分类(2026-10-17 裁定):取任务自己的 error_code——下载
            # 异常 download/构建异常 rebuild;其余码(source_not_found 等
            # 非下载/构建失败)原样透传为非空 kind,告警侧未知 kind 走
            # else 通用文案(可观测行为同 "",机制是透传非重写);旧任务
            # 无 error_code → ""。
            self._escalate_backoff(
                name, now, kind=self._manager.task_failure_kind(task_id) or "",
                error=self._task_error_tail(task_id))
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            return
        if state == "cancelled":
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            return
        if state == "done":
            if self._partial_failure_of(source) is not None:
                # Normal path since F-4 (A1/Task 3): spamhaus/x4bnet_vpn's
                # v6-sibling failure records the flag and returns done
                # WITHOUT rewriting the join file, so mtime is unchanged —
                # escalate so the dead sibling keeps the 1h..12h retry
                # pacing instead of per-scan retries (30-min re-pull storm
                # guard). Dir-shaped multi-feed sources (cloud_ranges) with
                # any landed feed take the mtime-advanced branch above.
                # 部分挂 = 下载相位失败 → kind=download(2026-10-17 裁定)。
                self._escalate_backoff(name, now, kind="download",
                                       error=self._task_error_tail(task_id))
            elif self._manager.task_rebuild_only(task_id):
                # rebuild-only 车道(2026-10-14 收敛批):mtime 不变是预期
                # (没下载)。收敛(needs_rebuild 翻 False)→ 清退避 —— 内容
                # 事件不记,事件在下载轮已记,重建轮零新证据(哲学 3);
                # 仍 needs_rebuild(另一族被 valve 卡住仍冻)→ 升梯,
                # ptr 推进前不重抓(与 mtime-advanced 分支同刹车);ptr 冻
                # = 构建未成 → kind=rebuild(2026-10-17 裁定)。
                if self._needs_rebuild_of(source):
                    self._escalate_backoff(name, now, kind="rebuild",
                                           error=self._task_error_tail(task_id))
                else:
                    self._backoff.pop(name, None)
            else:
                logger.warning(
                    "scheduler: source %s task %s is 'done' but mtime unchanged "
                    "(theoretically unreachable); needs_rebuild will catch a stale MMDB",
                    name, task_id)
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            return

    def _escalate_backoff(self, name: str, now: float, kind: str = "",
                          error: str = "") -> None:
        """Bump the failure ladder: 1h, 2h, 4h, 8h, 12h (cap). Shared by the
        real-failure path and the done-but-partial path (spec §2.3).

        kind(2026-10-17 用户裁定:告警分报下载/构建失败)+ 双计数(裁定修):
        fail_count = 任意类连败总数,kind 切换**不**重置——≥2 告警条件、
        恢复判定(只有真成功才清,与改前逐位同)与退避计时梯全由总数驱动
        (kind 中途切换 ≠ 成功,不得下假「已恢复」);kind_count = 逐 kind
        连败数,切换重归 1——只驱动告警文案 ×N(报什么就像什么,×N 逐
        kind 真实)。next_attempt 落梯公式不变(按总数)。

        error(#371:源告警带失败原因):当次失败 task 的 error 尾摘,
        随梯子存入 _Backoff.error 供快照/告警渲染;每次升级覆盖为当次
        原因,成功路径 pop 整项即清空。"""
        b = self._backoff.get(name)
        same_kind = b is not None and b.kind == kind
        fail_count = (b.fail_count + 1) if b is not None else 1
        kind_count = (b.kind_count + 1) if same_kind else 1
        idx = min(fail_count, len(_BACKOFF_SECONDS)) - 1
        self._backoff[name] = _Backoff(
            fail_count=fail_count, next_attempt=now + _BACKOFF_SECONDS[idx],
            kind=kind, kind_count=kind_count, error=error)

    def _task_error_tail(self, task_id: str) -> str:
        """当次失败 task 的 error 尾摘(#371):空白折叠成单空格(stderr 尾
        含换行,告警体按行 join 不得炸行)+ 截 200 字;task 无/非 failed
        (成功/partial/取消路径)→ ""。取数走 manager 既有按 id 查询面
        (task_error),不新起进程不翻日志。"""
        err = self._manager.task_error(task_id) or ""
        return " ".join(err.split())[:200]

    @staticmethod
    def _partial_failure_of(source) -> Optional[list]:
        """Partial-tolerance signal (cloud_ranges): download() records the
        feeds that failed in `last_partial_failure`. Non-empty → the source
        is not healthy despite a fresh dir mtime. Sources without the attr
        (legacy/custom sources) report None — scheduling unchanged."""
        return getattr(source, "last_partial_failure", None) or None

    @staticmethod
    def _data_files_or_legacy(source) -> list:
        """内容输入集(#501 起指纹用,#509 起修改时间同走这份):有
        _data_files() 钩子的源返回钩子声明的清单;无钩子的自定义源/
        测试桩退回旧口径——_path 是文件 → [文件],是目录 → 目录内全部
        普通文件(暂存件照吃,旧行为原样);_path 缺失或列目录失败 →
        [](两个消费面算空集同为「算不出」:newest_mtime → None、
        content_fingerprint → None)。_data_files() 抛异常 → 记 warning
        (带源名与异常类型)后退回旧口径,输入集不因钩子故障硬丢。
        清单里出现目录(目录型 _path 不覆写钩子时,基类默认返回的就是
        目录自己)→ 记 warning(带源名与目录项)后退回旧口径:「有钩子」
        ≠「清单可信」,拿目录自身 mtime 当内容新鲜度会回到 #465 卡16
        的「46 天误报」(#509 评审记一笔 8)。
        """
        from pathlib import Path
        data_files = getattr(source, "_data_files", None)
        if data_files is not None:
            try:
                declared = list(data_files())
                dir_items = [str(f) for f in declared if Path(f).is_dir()]
                if not dir_items:
                    return declared
                logger.warning(
                    "scheduler: _data_files() for %s lists directory "
                    "item(s) [%s]; falling back to legacy path listing",
                    getattr(source, "name", "?"), ", ".join(dir_items))
            except Exception as e:      # 钩子故障不丢记账:退回旧口径
                logger.warning(
                    "scheduler: _data_files() failed for %s (%s); "
                    "falling back to legacy path listing",
                    getattr(source, "name", "?"), type(e).__name__)
        p = getattr(source, "_path", None)
        if p is None:
            return []
        path = Path(p)
        try:
            if path.is_dir():
                return [c for c in path.iterdir() if c.is_file()]
            return [path]
        except OSError:
            return []

    @staticmethod
    def _content_fingerprint_of(source) -> Optional[str]:
        """#467:源数据文件字节指纹;经 observe_update 的 content_hash_of 延迟
        调用,只在落新事件时进本函数(平时扫描不算指纹,零开销)。

        输入集 = _data_files_or_legacy(#501,还 #465 卡16 的挂账;#509
        起 _read_mtime 同走这份输入集):有 _data_files() 钩子的源走
        钩子返回的声明清单——与 health()、/api/sources 的 content_age_h
        同一输入集,下载暂存件(.dl、.dl.tmp、cn_isp 的 .tmp)不再混进
        指纹。#455 评审 R-2 的窗口两半都已关(对有 _data_files() 覆写
        的源;钩子抛异常退回旧口径时,对那一个源重新打开,有 warning):
        「暂存件进指纹」这一半 #501 关了;「扫描落在下载途中多记一条」
        那一半 #509 关了(_read_mtime 不再看暂存件,那条假事件不再产生;
        存量库历史区间的读数仍按 _alerts.py 头注的读数注意②剔除)。无钩子的自定义
        源/测试桩退回旧口径:_path 是文件 → 单文件;是目录 → 目录内
        文件列表(排序由 _alerts.content_fingerprint 内部做,这里不排)。
        _path 缺失、列目录失败、目录空 → None(指纹列落 NULL,事件照记)。

        缺席裁决(#501 主会话定):声明清单里任一文件不存在 → 整次指纹
        None——None 在读数时按「不可比」剔除,永远不会被算成「没变」
        (宁少算,哲学 2:算不出可比指纹就不硬造);缺席经
        _alerts.content_fingerprint 的 OSError 规则落 None(任一文件读
        不了/列表为空同为 None),不在此处另立一份缺席判定。

        _data_files() 调用抛异常 → 退回旧口径并记 warning(带源名与
        异常类型),指纹不因钩子故障硬丢。
        """
        return _alerts.content_fingerprint(
            RefreshScheduler._data_files_or_legacy(source))

    @staticmethod
    def _read_mtime(source) -> Optional[float]:
        """内容修改时间:更新账本水位(#455)、slot 到期(scan)、告警
        content_age_h、超龄探测器(ops_detectors)的共同信号源。

        #509:目录分支的输入集与 _content_fingerprint_of 同走
        _data_files_or_legacy——有 _data_files() 钩子的源取声明清单的
        最新 mtime,下载暂存件(.dl、.dl.tmp、cn_isp 的 .tmp)不再被
        当成「源刚更新过」。清单里的文件全都不存在 → 返回 None:和
        「下载失败的残缺」同一处理(None = 立即到期,见 scan() 的 slot
        注释)——声明文件全缺席 = 完整性未恢复,宁可立即重抓,也不拿
        暂存件的「刚写入」冒充内容新鲜度(暂存件一出现就算更新过、被
        改名或清掉 mtime 又变回去,_reconcile 会把这种波动误判成下载
        落地,即 #455 评审 R-2 窗口的成因)。无钩子源退回旧口径(目录
        内全部普通文件取最新);_path 是文件的源完全不变(直接 stat
        的 mtime,与指纹的 [_path] 输入集天然一致)。
        """
        from pathlib import Path
        import stat as _stat
        p = getattr(source, "_path", None)
        if p is None:
            return None
        try:
            st = Path(p).stat()
            if _stat.S_ISDIR(st.st_mode):
                # 目录型源(cn_isp isp/、cloud_ranges/):内容 mtime = 数据
                # 文件清单里最新的。重写文件不改目录 mtime(线上实证:isp/
                # 目录停在首建日 08-18,文件当天 10-03 刚刷新),只看目录
                # 会把新鲜多 feed 源误判 46 天过期。#465 卡16:取最大收
                # _freshness 单源点;#509:输入集改走声明清单(暂存件
                # 不参与;清单全缺席 → None,裁决见 docstring)。
                from ._sources import _freshness
                return _freshness.newest_mtime(
                    RefreshScheduler._data_files_or_legacy(source))
            return st.st_mtime
        except OSError:
            return None


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
