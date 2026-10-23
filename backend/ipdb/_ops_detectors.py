"""ops 确定性探测器(P1 §2,票 #154,spec #152 §2)。

零 LLM:两类确定性信号直接产待审条目(_ops_items.create_item),幂等与
复开链指复用 T1 条目库(dedup_key 语义键,同因在飞不双开),本模块不
重复实现。探测器本体不吞错(坏条目文件等显式报错沿 _ops_items 口径);
故障隔离在挂点的独立兜错(_tasks._settle 的 on_terminal try/except、
_scheduler.scan 的 on_scan try/except):探测面故障只 log,不反噬任务
状态机/调度行为。

- 下载失败探测器(make_download_fail_detector → manager.on_terminal):
  挂 UpdateManager 终态缝(_settle 收口)而非轮询——spec #152 验收要求
  「停用真源 → 失败条目即时出现」,事件驱动是唯一直达路径;轮询面
  (snapshot)的终态任务会被同源再入队清扫,且同一失败任务跨扫描重复
  计数。只读消费 to_dict() 快照,范围裁记:
  * 只认 error_code=="download"(下载相位失败):探测器名与可逆动作
    建议 retry_download 只对下载失败成立;rebuild/source_not_found 归
    既有告警面(_alerts 分报构建失败),宁少算勿多算(spec §2 名
    「下载失败探测器」);
  * source=="ops"(ops 轮伪源)跳过:ops 任务不经 _settle(驱动方是
    轮次线程),此为防御性守卫——伪源失败归轮次信封面,不产数据源条目;
  * 连续失败计数自持(任务对象无此状态):error_code=download 计入,
    done 清零,failed(rebuild)= 下载已落地亦清零,cancelled 无证据
    不动(无证据即无话)。进程内状态,重启归零——重启后首次失败重计 1,
    幂等由条目库兜(同因在飞不双开),不虚增;
  * severity:连续≥3 high / 其余 medium(票 #154;≥3 门线同 _alerts
    _FAIL_COUNT=3 判例口径)。在飞条目不升级改写(T1 无此 API,severity
    是产条时快照):升级沿复开链实现——人审处置终态后同因再犯,新条目
    按当次连败数定级,证据不灭失;
  * error_signature = 错误族(闭集,http_401/403 单列——与探测降噪刀一
    的「需令牌·正常」同口径;认不出归 error_code 兜底):同族失败同因
    去重,换族 = 新事实开新条目。

- 超龄探测器(run_staleness_detector → RefreshScheduler.on_scan):内容
  年龄 > 2× 刷新周期 → 产条(spec §2「45h/12h 实证案例」:日更源内容
  45h 旧,> 2×12h 应产条,而告警面阈值 max(stale_days×24, observed×4)
  = 48h 拦不住——探测器补此细粒度空档)。刷新周期 = _scheduler.
  _period_of(stale_days)(现成信号:日更源 12h 槽位,其余 stale_days×24h,
  同一拼写一处来源,不自造第二套周期语义);恰 2× 不产(严格大于)。
  挂 scheduler 扫描尾:扫描节律即探测节律,源清单就地取。无数据文件
  (mtime None)不产:无内容年龄证据,冷启动/首拉未成不是超龄(拉不到
  的因归下载失败探测器;无证据≠清白,但也无证据即无话)。
"""

import logging
import re
import threading
import time
from pathlib import Path

from . import _ops_items
from ._scheduler import _period_of

logger = logging.getLogger(__name__)

# severity 门线:连续失败 ≥3 → high(票 #154;_alerts._FAIL_COUNT=3 同口径)
DOWNLOAD_FAIL_HIGH_THRESHOLD = 3
# 超龄系数:内容年龄 > 2× 刷新周期(spec #152 §2)
STALENESS_FACTOR = 2
# 下载失败 error_signature 兜底族(= 任务失败分类码 error_code 本身)
_FALLBACK_FAMILY = "download"

_HTTP_STATUS_RE = re.compile(r"HTTP Error (\d{3})")


def _error_family(error_code, error_text) -> str:
    """错误文本 → 错误族闭集(宁少算勿多算:认不出的归 error_code 兜底)。

    urllib 形状:HTTPError "HTTP Error 403: Forbidden";超时 "timed out";
    URLError "<urlopen error ...>"(DNS/连接层)。401/403 单列——匿名撞
    鉴权墙与探测降噪刀一(TOKEN_REQUIRED)同口径:需令牌,非源死亡。
    """
    text = error_text or ""
    m = _HTTP_STATUS_RE.search(text)
    if m:
        status = int(m.group(1))
        if status in (401, 403):
            return f"http_{status}"
        if 400 <= status < 500:
            return "http_4xx"
        if 500 <= status < 600:
            return "http_5xx"
    low = text.lower()
    if "timed out" in low or "timeout" in low:
        return "timeout"
    if "urlopen error" in low or "connection" in low:
        return "network"
    return error_code if error_code else _FALLBACK_FAMILY


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_download_fail_detector():
    """下载失败探测器(线程安全可调用,挂 manager.on_terminal)。

    入参 = task.to_dict() 只读快照(state/source/error/error_code)。
    产条参数面见模块头裁记;连败计数是本闭包状态(每 manager 一实例,
    测试自建实例互不串)。
    """
    lock = threading.Lock()
    streaks: dict[str, int] = {}   # source → 连续下载失败数

    def on_task_terminal(task: dict) -> None:
        if not isinstance(task, dict):
            return
        source = task.get("source")
        state = task.get("state")
        if not isinstance(source, str) or not source:
            return
        if state == "done":
            with lock:
                streaks.pop(source, None)   # 成功清连败(_alerts 恢复判定同律)
            return
        if state != "failed":
            return                           # cancelled:无证据不动
        if source == "ops":
            return                           # ops 轮伪源(防御性,见模块头)
        error_code = task.get("error_code")
        if error_code != "download":
            with lock:
                streaks.pop(source, None)   # rebuild 等:下载已落地,连败断
            return
        with lock:
            streaks[source] = streaks.get(source, 0) + 1
            streak = streaks[source]
        error_text = str(task.get("error") or "")
        family = _error_family(error_code, error_text)
        _ops_items.create_item(
            source=source,
            probe_class="download",
            error_signature=family,
            action="retry_download",
            args={"source": source},
            evidence={
                "consecutive_failures": streak,
                "error_code": error_code,
                "error_family": family,
                "last_error": error_text[:300],
                "last_failed_at": _utc_now_iso(),
            },
            impact=f"{source} 数据停更,威胁覆盖面收缩",
            rollback="重新触发下载即可恢复;无不可逆变更",
            severity=("high" if streak >= DOWNLOAD_FAIL_HIGH_THRESHOLD
                      else "medium"),
            cause_group="download_failure",
            summary=(
                f"# 待审:源 {source} 下载失败(连续 {streak} 轮)\n\n"
                f"末次错误({error_code}/{family}):{error_text[:300] or '(无消息)'}\n"
                f"建议动作 retry_download(可逆);失败画像与时间戳见 evidence。\n"
            ),
        )

    return on_task_terminal


def run_staleness_detector(sources, now=None) -> None:
    """超龄探测器(挂 RefreshScheduler.on_scan;测试可独立驱动)。

    sources = enabled offline source 对象集(读 name/stale_days/_path,
    与 scheduler/_alerts 同信号面);无 _path/文件不存在 → 跳过(见模块
    头裁记)。幂等由条目库保证:同因在飞不双开,每轮扫描重复调用零害。
    """
    if now is None:
        now = time.time()
    for source in sources:
        name = getattr(source, "name", None)
        if not isinstance(name, str) or not name:
            continue
        path = getattr(source, "_path", None)
        if not isinstance(path, (str, Path)):
            continue
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            continue                       # 无文件 = 无内容年龄证据,不产
        stale_days = int(getattr(source, "stale_days", 7) or 7)
        period_s = _period_of(stale_days)
        age_s = now - mtime
        if age_s <= STALENESS_FACTOR * period_s:
            continue                       # 恰 2× 不产(严格大于)
        age_h = age_s / 3600.0
        period_h = period_s / 3600.0
        _ops_items.create_item(
            source=name,
            probe_class="staleness",
            error_signature="age_gt_2x_refresh",
            action="refresh_source",
            args={"source": name},
            evidence={
                "content_age_h": round(age_h, 2),
                "refresh_period_h": round(period_h, 2),
                "stale_days": stale_days,
                "observed_at": _utc_now_iso(),
            },
            impact=f"{name} 内容超龄,数据新鲜度与覆盖受损",
            rollback="刷新成功即自愈;无不可逆变更",
            severity="medium",
            cause_group="staleness",
            summary=(
                f"# 待审:源 {name} 内容超龄\n\n"
                f"内容年龄 {age_h:.1f}h > 2×刷新周期 {period_h:.1f}h"
                f"(stale_days={stale_days})。建议动作 refresh_source;"
                f"读数与观测时间见 evidence。\n"
            ),
        )
