"""ReportedIP blacklist — Source subclass (CSV, per-row multi-code classification).

`reportedip/reportedip-blacklist` (ReportedIP / Patrick Schlesinger, reportedip.de)
is a community-reputation feed backed by a first-party honeypot (WordPress /
Drupal / Joomla emulation, 36 threat analyzers) plus WordPress security plugins
and community reports. Only IPs with confidence >= 75% are listed; known-legit
CDN/search IPs are whitelisted; a 48-hour publication delay reduces false positives.

CSV columns: ``ip, confidence, categories, last_reported`` where ``categories``
is a ``;``-separated list of numeric codes. All 58 codes are officially
documented (per reportedip.com v2/categories API): 1-30 general attacks,
31-58 WordPress attack sub-categories. Each code maps via ``REPORTEDIP_MAP`` to
an IntelMQ ``classification.type``; ``REPORTEDIP_CODE_THEMATIC`` carries the
official per-code NAME for display. Codes are GROUPED by derived canonical type:
one ``Evidence`` per distinct type, each carrying ``native_categories`` = the
official names of its codes (deduped). Future codes absent from the tables
(59+) fall back to their raw numeric string. The canonical type is a derived
tag. IPv6 rows are harvested too (bare address, dual-family storage,
spec 2026-08-23).

License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Attribution
to ReportedIP (reportedip.com) is required.
"""
import csv
import logging

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize


# reportedip (reportedip.de) — CSV `categories` 字段是 ;-分隔数字码。1-58 全码
# 均为官方公开分类(per https://reportedip.com/wp-json/reportedip/v2/categories):
# 1-30 通用攻击,31-58 WordPress 攻击细分。code→IntelMQ 映射基于官方分类名语义。
# 一个 IP 多码 → N evidence(按 canonical 分组);未在表内的未来新增码(59+)→ other 兜底。
# code 9 Open Proxy→proxy、code 29 Zero-Day→exploit 为语义修正(映射语义要对,非数据驱动)。
REPORTEDIP_MAP = {
    # 1-30 通用
    "1": "scanner", "2": "scanner", "14": "scanner",       # DNS compromise/poisoning, port scan
    "3": "phishing", "7": "phishing", "8": "phishing", "17": "phishing",  # fraud/phishing/spoofing
    "4": "ddos", "6": "ddos",
    "5": "brute-force", "18": "brute-force", "22": "brute-force",  # FTP/credential/SSH brute-force
    "9": "proxy",                                          # open proxy
    "10": "spam", "11": "spam", "12": "spam",               # web/email/blog spam
    "15": "exploit", "16": "exploit", "19": "exploit", "21": "exploit",  # hacking/SQLi/bad-bot/web-app
    "20": "malware", "24": "malware", "25": "malware", "26": "malware", "27": "malware",  # exploited/mining/C2/trojan
    "23": "infected-system",                               # IoT targeted(drone 宿主)
    "28": "other", "29": "exploit", "30": "c2-server",     # supply chain(无净 IntelMQ 槽)/zero-day/nation-state
    "13": "proxy",                                         # VPN IP → proxy(低威胁,归 proxy)
    # 31-58 WordPress 攻击细分
    "31": "brute-force", "32": "brute-force", "33": "brute-force", "34": "brute-force",  # WP login/admin/XML-RPC/REST 爆破
    "35": "exploit", "36": "exploit", "37": "exploit", "38": "exploit",  # WP plugin/theme/core/0-day 漏洞
    "39": "spam", "40": "spam", "41": "spam", "42": "spam", "47": "spam", "49": "spam",  # WP comment/contact/reg/trackback/SEO spam
    "43": "malware", "44": "malware", "45": "malware", "46": "malware",  # WP file-upload/code-inj/DB-inj/backdoor
    "48": "scanner", "55": "scanner", "56": "scanner", "57": "scanner", "58": "scanner",  # WP content-scraping/user-enum/version/plugin scan/config exposure
    "50": "exploit",                                       # WP redirect hijacking
    "51": "ddos",                                          # WP resource exhaustion
    "52": "other", "53": "other", "54": "other",           # WP media/search/cron abuse(无净 IntelMQ 槽)
}

# reportedip code → 官方分类名(per reportedip.com v2/categories API, 2026-08-11)。
# 每码一名;harvest 按组去重。未来新增码(59+)或缺失 → harvest 回退原始码字符串。
REPORTEDIP_CODE_THEMATIC = {
    "1": "DNS Compromise", "2": "DNS Poisoning", "3": "Fraud Orders",
    "4": "DDoS Attack", "5": "FTP Brute-Force", "6": "Ping of Death",
    "7": "Phishing", "8": "Fraud VoIP", "9": "Open Proxy",
    "10": "Web Spam", "11": "Email Spam", "12": "Blog Spam",
    "13": "VPN IP", "14": "Port Scan", "15": "Hacking",
    "16": "SQL Injection", "17": "Spoofing", "18": "Brute-Force",
    "19": "Bad Web Bot", "20": "Exploited Host", "21": "Web App Attack",
    "22": "SSH", "23": "IoT Targeted", "24": "Cryptocurrency Mining",
    "25": "Ransomware C&C", "26": "Banking Trojan", "27": "Mobile Malware",
    "28": "Supply Chain Attack", "29": "Zero-Day Exploit", "30": "Nation State",
    "31": "WP Login Brute Force", "32": "WP Admin Brute Force",
    "33": "WP XML-RPC Brute Force", "34": "WP REST API Abuse",
    "35": "WP Plugin Exploit", "36": "WP Theme Exploit",
    "37": "WP Core Exploit", "38": "WP Zero-Day Exploit",
    "39": "WP Comment Spam", "40": "WP Contact Form Spam",
    "41": "WP Registration Spam", "42": "WP Trackback Spam",
    "43": "WP File Upload Malware", "44": "WP Code Injection",
    "45": "WP Database Injection", "46": "WP Backdoor Installation",
    "47": "WP SEO Spam", "48": "WP Content Scraping", "49": "WP Fake SEO Bot",
    "50": "WP Redirect Hijacking", "51": "WP Resource Exhaustion",
    "52": "WP Media Library Abuse", "53": "WP Search Abuse", "54": "WP Cron Abuse",
    "55": "WP User Enumeration", "56": "WP Version Scanning",
    "57": "WP Plugin Scanning", "58": "WP Config Exposure",
}


def _resolve_thematic(codes: list[str]) -> list[str]:
    """Resolve a canonical group's codes to their official reportedip category
    names (per REPORTEDIP_CODE_THEMATIC), deduped, preserving first-seen order.
    Codes absent from the table (future 59+) fall back to their raw string."""
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        label = REPORTEDIP_CODE_THEMATIC.get(c, c)
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


logger = logging.getLogger(__name__)


class ReportedIPSource(Source):
    name = "reportedip"
    category = "threat"
    url = "https://raw.githubusercontent.com/reportedip/reportedip-blacklist/main/blacklist-all.csv"
    filename = "reportedip.csv"
    fields = ("is_malicious",)
    classification_type = "other"   # default; overridden per-row in harvest
    verdict = "malicious"
    stale_days = 1                  # daily auto-commit at ~04:05 UTC
    reliability = 0.65              # honeypot + community reports (cf. binarydefense, blocklist_de)
    authoritative_for = ()
    # 载入期排除 infra_services curated 单址集(issue #347 / #183 同族 /
    # ADR 0008;2026-11-15 人裁按误报处理:生产 8.8.8.8(Google Public DNS,
    # curated 基础设施)被 reportedip 单源单时刻指控为恶意(verdict=
    # malicious conf=65,原生行 conf=77、codes "15;21" = Hacking/Web App
    # Attack,2026-11-13T16:15:58 单时刻单源无印证,同场 infra_services
    # 良性断言 conflict=true;上游行仍活)。实测本地快照 .eval-prod-data/
    # reportedip.csv(2026-10-29,17672 行)全量 curated 56 员命中 = 0
    # (零存量面;事故行为 2026-11-13 新增)。数据文件零改写,关
    # IP_RADAR_INFRA_NOISE_FILTER 重建即复原)。
    infra_noise_filter = True

    def harvest(self):
        """Yield (ip, Evidence) per IPv4 row, one Evidence per distinct canonical
        type. Codes are grouped by ``normalize(c, REPORTEDIP_MAP)``; codes absent
        from REPORTEDIP_MAP (future 59+) map to ``other`` and are preserved as
        their own group's ``native_categories``. ``confidence`` →
        ``Evidence.confidence`` (kept as ``native_confidence`` by fusion);
        ``last_reported`` → ``first_seen``/``last_seen`` (same value; first_seen
        drives decay). IPv6 rows are harvested too (bare address yields
        naturally as /128 under dual-family rebuild, spec 2026-08-23).
        """
        with open(self._path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ip = (row.get("ip") or "").strip()
                if not ip:
                    continue
                raw_cats = (row.get("categories") or "").strip()
                groups: dict[str, list[str]] = {}
                for c in raw_cats.split(";"):
                    c = c.strip()
                    if not c:
                        continue
                    t = normalize(c, REPORTEDIP_MAP)   # known → canonical; absent → "other"
                    groups.setdefault(t, []).append(c)
                if not groups:                         # empty categories → preserve IP signal as "other"
                    groups = {"other": []}
                conf_raw = (row.get("confidence") or "").strip()
                confidence = int(conf_raw) if conf_raw.isdigit() else None
                last_rep = (row.get("last_reported") or "").strip()
                first_seen = last_rep.replace(" ", "T") if last_rep else None
                for t, codes in groups.items():
                    yield ip, Evidence(
                        classification_type=t,
                        verdict="malicious",
                        confidence=confidence,
                        first_seen=first_seen,
                        last_seen=first_seen,
                        native_categories=_resolve_thematic(codes),
                    )
