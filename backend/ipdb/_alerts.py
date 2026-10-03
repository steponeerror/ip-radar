# backend/ipdb/_alerts.py — 源活性告警:存储层 + 节奏计算 + 判定状态机 + 推送出口(Task 1-4)
"""update_events 事件表、节奏推导与 evaluate 状态机(stdlib sqlite3 同步,每次操作新连接)。

事件历史恒开,与通知无关(约束 2):scheduler 每见内容更新就 record_event,
observed_interval_h 用近 90 天相邻间隔中位数回答"该源平时多久更一次"。
evaluate 消费 scheduler 每轮快照,per (source, condition) 推进 alert_state
(转入/24h 重发/恢复/静默清理)并组装合并消息(约束 4/6,中文硬编码)。
IP_RADAR_ALERTS_DB 可覆盖 db 路径(测试逐用例隔离);缺省落在 _registry
数据目录(_STATE_PATH.parent),与 auth.db 同级。连接工厂按解析出的路径
字符串缓存(循 _auth._engine 惯例但同步版):生产单路径单工厂,env 切
tmp 即新键,互不串台。时间统一 epoch 秒落库(at REAL),对外 API 一律小时。

push 是唯一出站出口(约束 5):apprise 多 URL 推送,env IP_RADAR_ALERT_URLS
空 = 完全不通知;apprise 惰性 import(env 空不 import),任何异常 warning
吞掉永不 raise——跑在 scheduler 守护线程里,推送失败不得杀死调度。
"""
import logging
import math
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Callable

from . import _registry

logger = logging.getLogger(__name__)

# 固定参数不设旋钮(约束 8):90d 滚动窗口/清理、min events=5、K=4、fail≥3、24h 重发
_WINDOW_S = 90 * 86400
_MIN_EVENTS = 5
_INTERVAL_FACTOR = 4
_FAIL_COUNT = 3
_RE_NOTIFY_S = 86400

# alert_state 的 condition 取值
_STALE = "stale"
_FAIL = "fail"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS update_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL, at REAL NOT NULL, record_count INTEGER);
CREATE INDEX IF NOT EXISTS ix_update_events_source_at ON update_events(source, at);
CREATE TABLE IF NOT EXISTS alert_state (
  source TEXT NOT NULL, condition TEXT NOT NULL,   -- 'stale' | 'fail'
  active_since REAL NOT NULL, last_notified REAL NOT NULL,
  PRIMARY KEY (source, condition));
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


def event_count(source: str) -> int:
    """该源 update_events 行数。scheduler 种子判定用:0 = 从未观测到
    此源的内容更新(prune 清空后回到 0,重扫时按当前 mtime 重种)。"""
    with closing(_connect()) as conn:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM update_events WHERE source = ?",
            (source,)).fetchone()
    return n


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


def _fmt_hours(hours: float) -> str:
    """时长两档(约束 6):<48h → 向上取整整数 + "h";≥48h → 一位小数 + "d"。"""
    if hours < 48:
        return f"{math.ceil(hours)}h"
    return f"{hours / 24:.1f}d"


def evaluate(snapshots: list[dict], now: float) -> dict | None:
    """消费 scheduler 每轮快照,推进 alert_state 并组装本轮合并消息。

    snapshot 每项:{"name", "stale_days", "content_age_h"(None=无文件→视为 ∞),
    "fail_count"(缺省 0)}。per (source, condition) 状态机(约束 4):
    转入坏 → INSERT active_since/last_notified=now 并计入;持续坏且
    now-last_notified ≥ 24h → 刷新 last_notified 并计入(重发);恢复 →
    DELETE,源名入恢复段;快照中消失的源(被禁用)→ 静默 DELETE。
    本轮无计入且无恢复 → None(不产生空消息);恢复-only 轮标题
    "ipradar: {k} 源已恢复"。状态只经 DB 传递,进程重启自然续跑。
    """
    inserts: list[tuple[str, str]] = []
    refires: list[tuple[str, str]] = []
    deletes: list[tuple[str, str]] = []
    stale_lines: list[tuple[str, str]] = []  # (源名, 行)——组内按源名排序
    fail_lines: list[tuple[str, str]] = []
    recovered: set[str] = set()

    with closing(_connect()) as conn:
        existing = {
            (source, cond): last_notified
            for source, cond, last_notified in conn.execute(
                "SELECT source, condition, last_notified FROM alert_state")
        }
        seen: set[str] = set()
        for snap in snapshots:
            name = snap["name"]
            if name in seen:  # 同名快照只取首个,防重复 INSERT 撞主键
                continue
            seen.add(name)
            stale_days = snap["stale_days"]
            age_h = snap.get("content_age_h")
            fail_count = snap.get("fail_count", 0)
            # observed 走独立只读连接:本连接此刻未开写事务,互不阻塞
            observed = observed_interval_h(name, now)
            thr = stall_threshold_h(stale_days, observed)

            counted = set()  # 本源本轮计入消息的条件
            for cond, bad in (
                (_STALE, age_h is None or age_h > thr),  # None = 无文件 → ∞ 必触发
                (_FAIL, fail_count >= _FAIL_COUNT),
            ):
                key = (name, cond)
                if bad:
                    if key not in existing:
                        inserts.append(key)
                        counted.add(cond)
                    elif now - existing[key] >= _RE_NOTIFY_S:
                        refires.append(key)
                        counted.add(cond)
                elif key in existing:
                    deletes.append(key)
                    recovered.add(name)

            if _STALE in counted:
                age_str = "从未" if age_h is None else _fmt_hours(age_h)
                if observed is not None and \
                        observed * _INTERVAL_FACTOR > stale_days * 24:
                    line = (f"{name}: 停更嫌疑({age_str} 未变,"
                            f"实测 {_fmt_hours(observed)}/次)")
                else:
                    line = (f"{name}: 过期(上次内容更新 {age_str},"
                            f"阈值 {_fmt_hours(thr)})")
                stale_lines.append((name, line))
            if _FAIL in counted:
                fail_lines.append((name, f"{name}: 连续失败 ×{fail_count}"))

        # 快照里消失的源(被禁用):静默清状态,不入恢复段
        deletes.extend(k for k in existing if k[0] not in seen)

        # 条件全部算完才落写:先读后写,一事务提交(约束 3:本操作单连接)
        with conn:
            for source, cond in inserts:
                conn.execute(
                    "INSERT INTO alert_state (source, condition, active_since,"
                    " last_notified) VALUES (?, ?, ?, ?)", (source, cond, now, now))
            for source, cond in refires:
                conn.execute(
                    "UPDATE alert_state SET last_notified = ?"
                    " WHERE source = ? AND condition = ?", (now, source, cond))
            for source, cond in deletes:
                conn.execute(
                    "DELETE FROM alert_state WHERE source = ? AND condition = ?",
                    (source, cond))

    bad_sources = {name for name, _ in stale_lines} | {name for name, _ in fail_lines}
    if not bad_sources and not recovered:
        return None
    lines = [line for _, line in sorted(stale_lines)] \
        + [line for _, line in sorted(fail_lines)]
    if recovered:
        lines.append("——已恢复: " + ", ".join(sorted(recovered)))
    if bad_sources:
        title = f"ipradar: {len(bad_sources)} 源异常"  # N=异常源数,双条件同源算 1
    else:
        title = f"ipradar: {len(recovered)} 源已恢复"
    return {"title": title, "body": "\n".join(lines)}


def push(title: str, body: str) -> bool:
    """apprise 推送出口(约束 5):notify 结果 bool() 化透传,任何异常 False 不抛。

    实测 apprise 2.0 的 notify() 返回 AppriseResult 对象,不是 bool;
    bool() 取其 __bool__(status==SUCCESS),与签名 -> bool 一致。

    IP_RADAR_ALERT_URLS 逗号/空白分隔多个 URL;空/未设 → False 且不 import
    apprise(历史照记,只是不通知)。单 URL add 失败仅 log.debug 跳过,
    notify 对其余 URL 照发。本函数会跑在 scheduler 守护线程里,故全路径
    吞异常(含 apprise 未安装的 ImportError),warning 后返回 False。
    """
    urls = [u for u in re.split(r",\s*|\s+", os.environ.get("IP_RADAR_ALERT_URLS", "")) if u]
    if not urls:
        return False
    try:
        import apprise  # 惰性:仅 env 非空才 import(约束 5)
        ap = apprise.Apprise()
        for url in urls:
            if not ap.add(url):
                logger.debug("apprise add 失败,跳过该 URL: %s", url)
        return bool(ap.notify(title=title, body=body))
    except Exception:
        logger.warning("apprise 推送失败(title=%r)", title, exc_info=True)
        return False
