# backend/ipdb/_alerts.py — 源活性告警:存储层 + 节奏计算(Task 1)
"""update_events 事件表(stdlib sqlite3 同步,每次操作新连接)与节奏推导。

事件历史恒开,与通知无关(约束 2):scheduler 每见内容更新就 record_event,
observed_interval_h 用近 90 天相邻间隔中位数回答"该源平时多久更一次"。
IP_RADAR_ALERTS_DB 可覆盖 db 路径(测试逐用例隔离);缺省落在 _registry
数据目录(_STATE_PATH.parent),与 auth.db 同级。连接工厂按解析出的路径
字符串缓存(循 _auth._engine 惯例但同步版):生产单路径单工厂,env 切
tmp 即新键,互不串台。时间统一 epoch 秒落库(at REAL),对外 API 一律小时。
"""
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Callable

from . import _registry

# 固定参数不设旋钮(约束 8):90d 滚动窗口/清理、min events=5、K=4
_WINDOW_S = 90 * 86400
_MIN_EVENTS = 5
_INTERVAL_FACTOR = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS update_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL, at REAL NOT NULL, record_count INTEGER);
CREATE INDEX IF NOT EXISTS ix_update_events_source_at ON update_events(source, at);
"""


def _db_path() -> Path:
    env = os.environ.get("IP_RADAR_ALERTS_DB")
    if env:
        return Path(env)
    return _registry._STATE_PATH.parent / "alerts.db"


# 按路径字符串缓存连接工厂(不是连接本身):约束 3 要求每次操作新建
# sqlite3 连接,避免跨线程复用;scheduler 线程与 API 线程互不共享句柄。
_factories: dict[str, Callable[[], sqlite3.Connection]] = {}


def _make_factory(path: Path) -> Callable[[], sqlite3.Connection]:
    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(path))
        # 惰性建表:首次使用即建,IF NOT EXISTS 幂等(空库/存量库同路径)
        conn.executescript(_SCHEMA)
        return conn

    return factory


def _connect() -> sqlite3.Connection:
    path = _db_path()
    key = str(path)
    factory = _factories.get(key)
    if factory is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        factory = _make_factory(path)
        _factories[key] = factory
    return factory()


def record_event(source: str, at: float, record_count: int | None = None) -> None:
    """记一次源内容更新;record_count 缺省 NULL(种子事件无计数)。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO update_events (source, at, record_count)"
            " VALUES (?, ?, ?)",
            (source, at, record_count),
        )


def observed_interval_h(source: str, now: float) -> float | None:
    """近 90 天窗口内相邻事件间隔中位数(小时);事件 <5 → None。

    窗口下界 at >= now-90d 与 prune 的 at < now-90d 互补:事件不会一边
    计入节奏一边被清掉。
    """
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT at FROM update_events WHERE source = ? AND at >= ?"
            " ORDER BY at",
            (source, now - _WINDOW_S),
        ).fetchall()
    ats = [r[0] for r in rows]
    if len(ats) < _MIN_EVENTS:
        return None
    gaps = sorted(b - a for a, b in zip(ats, ats[1:]))
    n = len(gaps)
    mid = n // 2
    median_s = gaps[mid] if n % 2 else (gaps[mid - 1] + gaps[mid]) / 2
    return median_s / 3600.0


def stall_threshold_h(stale_days: int, observed_h: float | None) -> float:
    """max(stale_days×24, observed×4);observed=None → 纯 stale_days(约束 1)。"""
    observed_side = observed_h * _INTERVAL_FACTOR if observed_h is not None else 0.0
    return float(max(stale_days * 24, observed_side))


def prune(now: float) -> None:
    """90 天滚动清理(约束 2);删 at < now-90d,与窗口同界互补。"""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM update_events WHERE at < ?", (now - _WINDOW_S,))
