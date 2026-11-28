"""blocklist.net.ua 封禁清单 — Source 子类(mirage_feed 模式:DictReader +
行过滤 + REASON 关键词分类)。

``https://blocklist.net.ua/blocklist.csv`` — 乌克兰社区封禁服务第一方数据,
CSV 4 列 ``IP;BAN_DATE;UNBAN_DATE;"REASON"``(分号分隔,REASON 带引号俄/英
双语;实测 2026-11-22 全量 83,674 行,BAN/UNBAN 为 unix 秒,最新 BAN_DATE =
抓取当分钟,实时滚动)。

行过滤(本源独有语义,列表史上首个显式解封):UNBAN_DATE <= now 的行
跳过 = 出库——封禁到期即不再是指控。UNBAN 缺值/不可解析时防御性保留
(仅显式过去解封才出库,宁少算不错杀)。

分类:REASON 自由文本按 NETUA_MAP 关键词子串匹配(ddos/паразит HTTP
flood 族、сканирование scanner 族、брутфорс/подбор brute 族、спам spam
族),全 miss → 兜底 blacklist(活性封禁的基类分类,urlhaus 先例);
REASON 原文进 native_categories。first_seen = BAN_DATE(unix→ISO-Z,首见
语义;衰减轴时钟按「最近见到」优先,#523——本源只给 first_seen 时
实际用 first_seen)。

download 截断防护:上游 2022-08 才修过文件截断 bug——原子写前校验非空 +
首行是表头(截断半截数据拒收,旧文件字节级保留,insightflare 同款形状)。

无鉴权直下;许可未标注(社区公开清单页),礼貌 = 单文件单 GET。
"""
import csv
import logging
import time

from .._source_base import Source
from .._evidence import Evidence
from ._download import atomic_write_bytes, redact_url

logger = logging.getLogger(__name__)

_HEADER_PREFIX = "ip;ban_date"   # 首行表头前缀(容引号/大小写)


# blocklist.net.ua REASON 关键词 → IntelMQ(2026-11-22 三源批)。REASON 是
# 自由文本(俄/英双语全句,内嵌被攻击站点名,同一语义多种措辞),exact-key
# normalize() 不可用——blocklist_netua.harvest 按本表键做**子串匹配**,
# 插入序即优先序(ddos 族 → scanner → brute → spam),全 miss → 源内兜底
# blacklist(每行都是活性封禁指控,urlhaus 基类分类先例)。
# 谱系 = 2026-11-22 实抓全量 83,674 行闭集统计(8 语义族):паразит
# 32,939(上游自译「Паразитные HTTP запросы」= "HTTP flood requests",
# паразитный трафик/запросы 同族)/ddos 24,071/скан 23,851/brute 2,514
# (брутфорс+подбор)/нагрузка 114(含 укр. навантаження)/malicious 111
# (VNC 无差别指控,无净槽→兜底)/спам 39/截断尾 1。
NETUA_MAP = {
    # ddos 系(应用层洪水:HTTP flood/паразит/过载冲击)
    "ddos": "ddos",
    "паразит": "ddos",
    "нагрузка": "ddos",
    "навантаження": "ddos",
    # scanner 系(несанкционированное сканирование/Сканер сайтов)
    "сканиров": "scanner",
    "сканер": "scanner",
    "scanning": "scanner",
    # brute-force 系(брутфорс атака/подбор паролей/brute force)
    "брутфорс": "brute-force",
    "подбор": "brute-force",
    "brute force": "brute-force",
    # spam 系(рассылка email спама/send spam)
    "рассылка": "spam",
    "спам": "spam",
    "spam": "spam",
}


def _classify(reason: str) -> str:
    """REASON 关键词 → 受控词表(NETUA_MAP 子串匹配,插入序即优先序);
    全 miss → blacklist 兜底(每行都是活性封禁指控,urlhaus 基类先例)。"""
    rl = reason.lower()
    for kw, term in NETUA_MAP.items():
        if kw in rl:
            return term
    return "blacklist"


class BlocklistNetUaSource(Source):
    name = "blocklist_netua"
    category = "threat"
    url = "https://blocklist.net.ua/blocklist.csv"
    filename = "blocklist_netua.csv"
    fields = ("is_malicious",)
    classification_type = "blacklist"   # default; overridden per-row in harvest
    verdict = "malicious"
    stale_days = 1                       # 实时滚动(最新 BAN = 抓取当分钟)
    reliability = 0.70                   # 社区第一方基础设施封禁(自运营 WAF 面)
    authoritative_for = ()
    provenance_tier = "B"                # B=社区(S21;第三方自有封禁面非自采,sblam 同档)

    def download(self, token=None) -> None:
        """GET + 截断防护(表头校验)→ 原子写。失败/拒收时旧文件字节级
        保留(next rebuild 不清库)。``token`` 接受但忽略(Simple GET,
        Source.download 同款签名契约)。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = self._http_get(self.url)
        if not data.strip():
            raise RuntimeError(f"Empty response from {redact_url(self.url)}")
        first = data.decode(errors="replace").splitlines()[0].strip()
        if not first.replace('"', "").lower().startswith(_HEADER_PREFIX):
            raise RuntimeError(
                f"blocklist_netua: header line missing/truncated (got "
                f"{first[:40]!r}) — refusing to overwrite existing data "
                f"(upstream truncation guard, 2022-08 precedent)")
        atomic_write_bytes(self._path, data)

    def harvest(self):
        """逐行 yield:已解封行跳过、first_seen=BAN_DATE、REASON 原文进
        native_categories。裸 IPv4(/32 语义由双族 rebuild 归一)。"""
        with open(self._path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                ip = (row.get("IP") or "").strip()
                if not ip:
                    continue
                # 显式解封 = 出库:仅可解析且已到期的 UNBAN 才丢行
                unban_raw = (row.get("UNBAN_DATE") or "").strip()
                if unban_raw.isdigit() and int(unban_raw) <= time.time():
                    continue
                ban_raw = (row.get("BAN_DATE") or "").strip()
                first_seen = (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                  time.gmtime(int(ban_raw)))
                    if ban_raw.isdigit() else None)
                reason = (row.get("REASON") or "").strip()
                yield ip, Evidence(
                    classification_type=_classify(reason),
                    verdict=self.verdict,
                    reliability=self.reliability,
                    first_seen=first_seen,
                    native_categories=[reason] if reason else [],
                )
