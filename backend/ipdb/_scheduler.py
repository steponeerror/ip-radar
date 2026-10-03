"""Background auto-refresh scheduler.

A single daemon thread that scans enabled offline sources every `interval`
seconds and enqueues each at its deterministic 12h-grid slot when due
(`_due_at`; daily tier twice a day, weekly tier once per stale_days) — or
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

logger = logging.getLogger(__name__)

# Backoff seconds for fail_count 1..5: 1h, 2h, 4h, 8h, 12h (cap).
_BACKOFF_SECONDS = [3600, 7200, 14400, 28800, 43200]
_NON_TERMINAL = ("queued", "downloading", "loading", "throttled")

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
    """First slot strictly after (mtime + period - guard).

    The guard absorbs slot-fire→mtime lag. Without it, mtime always trails the
    slot point, so each cycle's first_slot lands one grid further out: daily
    sources drift to 24h/cycle and weekly to 7.5d with +12h wall-clock drift.
    """
    slot = _slot_of(name)
    deadline = mtime + _period_of(stale_days) - REFRESH_GUARD
    first_slot = (deadline // SLOT_GRID) * SLOT_GRID + slot
    if first_slot <= deadline:
        first_slot += SLOT_GRID
    return first_slot


@dataclass
class _Backoff:
    fail_count: int
    next_attempt: float


class RefreshScheduler:
    def __init__(self, manager, enabled_offline_sources: Callable[[], list],
                 needs_rebuild_of: Callable[[object], bool], interval: int = 1800):
        self._manager = manager
        self._enabled_offline_sources = enabled_offline_sources
        self._needs_rebuild_of = needs_rebuild_of
        self._interval = interval
        self._last_task: dict[str, str] = {}
        self._last_attempt: dict[str, float] = {}
        self._baseline_mtime: dict[str, Optional[float]] = {}
        self._backoff: dict[str, _Backoff] = {}
        self._last_scan_at: Optional[float] = None

    # --- public ---
    def start(self, stop_event: threading.Event) -> None:
        """Run the scan loop until stop_event is set. Blocks the caller."""
        while not stop_event.wait(timeout=self._interval):
            try:
                self.scan()
            except Exception:
                logger.exception("scheduler scan raised; continuing")

    def scan(self, now: Optional[float] = None) -> None:
        """One scan pass. Public so tests can drive it deterministically."""
        if now is None:
            now = time.time()
        self._last_scan_at = now
        for source in self._enabled_offline_sources():
            name = source.name
            try:
                had_task = name in self._last_task
                self._reconcile(name, source, now)
                # 种子事件(Task 4):存量内容冷启动加速——源有 mtime 且
                # 事件表零行 → 以 mtime 落一条“首次观测到此内容”
                # (record_count 缺省 None)。放在 reconcile 之后:同轮
                # mtime 前进已落过事件则这里事件非零,不双记。独立兜错:
                # 告警侧故障不碰下方调度逻辑。
                try:
                    seed_mtime = self._read_mtime(source)
                    if seed_mtime is not None \
                            and _alerts.event_count(name) == 0:
                        _alerts.record_event(name, at=seed_mtime)
                except Exception:
                    logger.exception(
                        "scheduler: seed event failed for %s; continuing", name)
                if had_task:
                    continue  # just resolved (or still tracking); re-eligible next scan
                b = self._backoff.get(name)
                if b is not None and now < b.next_attempt:
                    continue  # still backing off
                if (self._partial_failure_of(source) is None
                        and not self._needs_rebuild_of(source)):
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
                task = self._manager.enqueue_one_detached(name)
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
                snapshots.append({
                    "name": source.name,
                    "stale_days": source.stale_days,
                    # mtime None(无文件)→ content_age_h None = 视为 ∞ 必触发
                    "content_age_h": None if mtime is None
                    else (now - mtime) / 3600.0,
                    "fail_count": b.fail_count if b is not None else 0,
                })
            msg = _alerts.evaluate(snapshots, now)
            if msg is not None:
                _alerts.push(msg["title"], msg["body"])
            _alerts.prune(now)
        except Exception:
            logger.exception("scheduler: alert cycle raised; continuing")

    def _reconcile(self, name: str, source, now: float) -> None:
        """Infer the previous cycle's outcome. No-op if name not in _last_task."""
        task_id = self._last_task.get(name)
        if task_id is None:
            return
        current = self._read_mtime(source)
        baseline = self._baseline_mtime.get(name)
        if current != baseline:
            # file was rewritten -> success
            if self._partial_failure_of(source) is not None:
                # done-but-partial: the overall download succeeded and mtime
                # advanced, but some feeds failed — escalate backoff instead
                # of clearing it, so the dead feeds keep the 1h..12h retry
                # pacing instead of waiting out the full stale period (spec
                # 2026-10-02 §2.3 self-heal; final-review Important #1).
                self._escalate_backoff(name, now)
            else:
                self._backoff.pop(name, None)
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            # 内容变化被确认(Task 4):落一条真实更新事件,record_count 取
            # 当前 health。独立兜错(仿种子块,T4-P2-1):告警侧故障只丢
            # 本轮事件,上方已完成的调度状态收敛不受影响。
            try:
                _alerts.record_event(name, at=now,
                                     record_count=source.health().record_count)
            except Exception:
                logger.warning(
                    "alerts: record_event failed for %s; event lost this round",
                    name)
            return
        # mtime unchanged -> classify by terminal state
        state = self._manager.task_state(task_id)
        if state in _NON_TERMINAL or state is None:
            # didn't run yet (throttled) or task evicted -> leave _last_task to retry reconcile
            if state is None:
                self._last_task.pop(name, None)
                self._baseline_mtime.pop(name, None)
            return
        if state == "failed":
            self._escalate_backoff(name, now)
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            return
        if state == "cancelled":
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            return
        if state == "done":
            if self._partial_failure_of(source) is not None:
                # Unreachable for the one partial-tolerant source (any landed
                # feed advances the dir mtime), but escalate anyway so a
                # standing partial failure can never degrade to per-scan
                # retries (30-min full re-pull storm guard).
                self._escalate_backoff(name, now)
            else:
                logger.warning(
                    "scheduler: source %s task %s is 'done' but mtime unchanged "
                    "(theoretically unreachable); needs_rebuild will catch a stale MMDB",
                    name, task_id)
            self._last_task.pop(name, None)
            self._baseline_mtime.pop(name, None)
            return

    def _escalate_backoff(self, name: str, now: float) -> None:
        """Bump the failure ladder: 1h, 2h, 4h, 8h, 12h (cap). Shared by the
        real-failure path and the done-but-partial path (spec §2.3)."""
        b = self._backoff.get(name)
        fail_count = (b.fail_count + 1) if b else 1
        idx = min(fail_count, len(_BACKOFF_SECONDS)) - 1
        self._backoff[name] = _Backoff(
            fail_count=fail_count, next_attempt=now + _BACKOFF_SECONDS[idx])

    @staticmethod
    def _partial_failure_of(source) -> Optional[list]:
        """Partial-tolerance signal (cloud_ranges): download() records the
        feeds that failed in `last_partial_failure`. Non-empty → the source
        is not healthy despite a fresh dir mtime. Sources without the attr
        (i.e. everything else) report None — scheduling unchanged."""
        return getattr(source, "last_partial_failure", None) or None

    @staticmethod
    def _read_mtime(source) -> Optional[float]:
        from pathlib import Path
        import stat as _stat
        p = getattr(source, "_path", None)
        if p is None:
            return None
        try:
            st = Path(p).stat()
            if _stat.S_ISDIR(st.st_mode):
                # 目录型源(cn_isp isp/、cloud_ranges/):内容 mtime = 目录内
                # 最新文件。重写文件不改目录 mtime(线上实证:isp/ 目录停在
                # 首建日 08-18,文件当天 10-03 刚刷新),只看目录会把新鲜
                # 多 feed 源误判 46 天过期。
                mtimes = [c.stat().st_mtime
                          for c in Path(p).iterdir() if c.is_file()]
                return max(mtimes) if mtimes else None
            return st.st_mtime
        except OSError:
            return None


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
