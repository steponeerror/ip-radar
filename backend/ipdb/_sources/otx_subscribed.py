"""AlienVault OTX subscribed-stream source — curated pulse library via REST.

2026-10-07 立项(方案 B),与 otx.py(activity 全网自动扫描流)同发布者不同流:

- 抓取面 = 账号订阅库(/api/v1/pulses/subscribed),数据 = 用户策展的作者群
  (蜜罐运营方/威胁研究团队),demo 账号实测 83 pulses/4 authors/16,929 唯一 IPv4,
  对比 activity 流同窗口仅数百条。
- 取数正解 = limit=1 逐页(每页单 pulse、指标全量内联,~0.5s/页;大页(≥5)必
  504——OTX 60s 网关闸,序列化整页全部 indicators 撞闸,2026-10-07 实测)。
  枚举页被巨型 pulse 挡住(504 重试一次仍败)则跳过该 pulse 记账继续,
  下轮 12h 槽位再补——流是滚动的,单轮缺页可容忍。
- 分类 = 双路:indicator 自带 role 字段优先(bruteforce→brute-force,逐 IP
  精确),pulse 名关键词兜底(Botnet List→c2-server 等,规则来自 2026-10-07
  实测 pulse 名分布),都miss→blacklist(通用策展榜)。
- 同 IP 多行 = 同一蜜罐内重复观测(45,330 行→5,867 唯一,87% 重复):去重保
  created 最新行,first_seen 落观测时间(provenance 三时间戳中的观测侧)。
- 谱系:derived=True(聚合平台,与 otx/firehol/ipsum 同层)。dedup_lineage
  在存在更强非派生源时剔除本源(spec 2026-08-29 §3.3);残余回声 = activity
  流与订阅流对同一 pulse 双计(仅当无任何非派生源覆盖该 IP 时),与 firehol/
  ipsum 重叠镜像同口径的保守近似,接受。
- 镜像卷谱系注:CyberHunterAutoFeed 的 URLHaus/Twitter 卷是公开 feed 搬运,
  与 urlhaus 源存在观测重叠——derived 标记 + 谱系去重兜底,不单独剔除
  (Botnet List 卷为 malware-traffic-analysis 谱系,非重复数据,保留)。

WAF 注(2026-10-07 实测):OTX 拦 Python-urllib 指纹(403),带 ip-lookup-tool/1.0
UA 的 urllib 请求在 per-pulse indicators 端点被拦;subscribed 端点同 UA 可过。
若线上 403 频发,备选 = 换 UA 复测(风险栏,未启用)。
"""
import csv
import json
import logging
import os
import time

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize, OTX_SUBSCRIBED_ROLE_MAP
from ._download import CancelToken, CancelledError

logger = logging.getLogger(__name__)

_SUBSCRIBED_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"
_DEFAULT_BUDGET_SECONDS = 900
_MAX_PAGES = 100
_TIMEOUT = 90

# pulse 名关键词 → IntelMQ 分类,首中即停(顺序=优先级)。规则来源:2026-10-07
# 对 demo 账号 83 个订阅 pulse 名的实测分布;"(s3" 捕捉非端口型 S3# 行为
# 脉冲(HTTP Range/敏感文件探测等均为扫描行为)。
_NAME_RULES: list[tuple[str, str]] = [
    ("botnet", "c2-server"),
    ("malware delivery", "malware-distribution"),
    ("urlhaus", "malware-distribution"),
    ("phishing", "phishing"),
    ("brute force", "brute-force"),
    ("bruteforce", "brute-force"),
    ("ics targeting", "scanner"),
    ("scan port", "scanner"),
    ("(s3", "scanner"),
]


def _classify_row(role: str, pulse_name: str) -> tuple[str, str]:
    """role → pulse 名关键词 → blacklist。返回 (classification_type, native_tag)。

    role 是 indicator 记录自带的逐 IP 角色标签(蜜罐源常用,如 bruteforce);
    native_tag 进 native_categories(前端 chip),取实际命中词保持可追溯。
    """
    if role:
        mapped = normalize(role, OTX_SUBSCRIBED_ROLE_MAP)
        if mapped != "other":
            return mapped, role
    name = (pulse_name or "").lower()
    for kw, ctype in _NAME_RULES:
        if kw in name:
            return ctype, kw
    return "blacklist", ""


class OtxSubscribedSource(Source):
    """Subscribed pulse library (curated) — Source subclass, CSV transport.

    download() 全量重写 CSV(滚动窗口语义,与 otx activity 同型):
    [indicator, ctype, tag, author, pulse, created, description]
    """

    name = "otx_subscribed"
    category = "threat"
    fields = ("is_malicious",)
    classification_type = "blacklist"   # class-level default; harvest sets per-row
    verdict = "malicious"
    url = _SUBSCRIBED_URL
    filename = "otx_subscribed.csv"
    stale_days = 1          # 12h 槽位网格;Live 蜜罐 pulse 时更、CyberHunter 日更
    reliability = 0.6       # 策展库主体为原创蜜罐观测,略高于 activity 流的 0.55
    derived = True          # 聚合平台:谱系去重用(spec 2026-08-29 §3.3)
    authoritative_for = ()

    @property
    def download_host(self) -> str | None:
        from urllib.parse import urlparse
        return urlparse(_SUBSCRIBED_URL).hostname

    def _fetch(self, url: str, headers: dict, retries: int = 2) -> bytes:
        """GET with retries(otx.py 同型;urllib UA 见文件头 WAF 注)。"""
        import urllib.request
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    return resp.read()
            except Exception as e:
                if attempt == retries:
                    raise
                wait = 2 ** attempt
                logger.info(
                    f"{self.name}: request failed (attempt {attempt}), "
                    f"retrying in {wait}s: {type(e).__name__}")
                time.sleep(wait)
        raise RuntimeError(  # pragma: no cover
            f"{self.name}: fetch failed after {retries} retries")

    def _fetch_json_page(self, page: int, headers: dict) -> dict | None:
        """取第 page 页(limit=1);失败(含 504 HTML)返回 None。"""
        url = f"{_SUBSCRIBED_URL}?limit=1&page={page}"
        try:
            return json.loads(self._fetch(url, headers))
        except Exception:
            return None

    def download(self, token: CancelToken | None = None) -> None:
        key = os.environ.get("OTX_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                f"{self.name}: OTX_API_KEY not set — cannot poll subscribed stream")
        headers = {
            "X-OTX-API-KEY": key,
            "Accept": "application/json",
            "User-Agent": "ip-lookup-tool/1.0",
        }
        budget = int(os.environ.get(
            "OTX_SUBSCRIBED_BUDGET_SECONDS", _DEFAULT_BUDGET_SECONDS))
        t0 = time.time()

        # ip -> [ctype, tag, author, pulse, created, description]
        collected: dict[str, list] = {}
        page, empty_streak, blocked, pulses_seen = 1, 0, 0, 0

        logger.info(f"Downloading {self.name} (REST /pulses/subscribed, limit=1 pages)")

        while page <= _MAX_PAGES:
            if token is not None and token.is_cancelled():
                raise CancelledError(f"{self.name} download cancelled")
            if time.time() - t0 > budget:
                logger.info(
                    f"{self.name}: reached {budget}s budget at page {page}, "
                    f"stopping early")
                break

            data = self._fetch_json_page(page, headers)
            if data is None or "results" not in data:
                # 504/瞬时错误:重试一次(8s),仍败则记账跳过(巨型 pulse 挡页)
                time.sleep(8)
                data = self._fetch_json_page(page, headers)
                if data is None or "results" not in data:
                    blocked += 1
                    empty_streak = 0
                    page += 1
                    continue

            pulses = data.get("results") or []
            if not pulses:
                empty_streak += 1
                if empty_streak >= 2:
                    break            # 订阅库尽头(两连空确认)
                page += 1
                continue
            empty_streak = 0
            pulses_seen += 1

            pulse = pulses[0]
            author = str(pulse.get("author_name") or "")
            pname = str(pulse.get("name") or "")

            for ind in (pulse.get("indicators") or []):
                itype = ind.get("type")
                if itype not in ("IPv4", "IPv6", "CIDR", "IPv4CIDR"):
                    continue        # domain/URL/FileHash 不入键空间(架构红线)
                value = ind.get("indicator", "").strip()
                if not value:
                    continue
                created = str(ind.get("created") or "")
                prev = collected.get(value)
                if prev is not None and prev[4] >= created:
                    continue        # 同 IP 重复观测,保最新 created 行
                ctype, tag = _classify_row(
                    str(ind.get("role") or ""), pname)
                collected[value] = [ctype, tag, author, pname, created,
                                    str(ind.get("description") or "")]

            page += 1

        if blocked:
            logger.warning(
                f"{self.name}: {blocked} page(s) blocked by 504 "
                f"(mega-pulse serialization); those pulses skipped this round")
        if not collected:
            raise RuntimeError(f"{self.name}: no IP indicators harvested")

        # 全量重写 CSV(滚动窗口,harvest() 的唯一消费源)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for indicator in sorted(collected):
                writer.writerow([indicator] + collected[indicator])

        elapsed = time.time() - t0
        logger.info(
            f"Downloaded {self.name} "
            f"({len(collected)} unique IPs, {pulses_seen} pulses, "
            f"{blocked} blocked pages, {elapsed:.0f}s)")

    # ── CSV parser(single source of truth)──

    def harvest(self):
        """Yield (ip_or_cidr, Evidence) per CSV row download() wrote.

        列 = [indicator, ctype, tag, author, pulse, created, description];
        created → first_seen(观测时间,接时间衰减),tag → native_categories,
        author/pulse/description → extra(无损)。reliability 留 None 走类级 0.6。
        """
        with open(self._path, "r", newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                ip_or_cidr = row[0].strip()
                ctype = row[1].strip()
                if not ip_or_cidr or not ctype:
                    continue
                tag = row[2].strip() if len(row) > 2 else ""
                author = row[3].strip() if len(row) > 3 else ""
                pulse = row[4].strip() if len(row) > 4 else ""
                created = row[5].strip() if len(row) > 5 else ""
                description = row[6].strip() if len(row) > 6 else ""
                extra = {}
                if author:
                    extra["author"] = author
                if pulse:
                    extra["pulse"] = pulse
                if description:
                    extra["description"] = description
                yield ip_or_cidr, Evidence(
                    classification_type=ctype,
                    verdict="malicious",
                    first_seen=created or None,
                    native_categories=[tag] if tag else [],
                    extra=extra or None,
                )
