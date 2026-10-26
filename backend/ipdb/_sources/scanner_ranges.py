"""scanner_ranges (扫描器厂商自报段) — Source subclass, cdn_edges 同构.

67 路单源:66 个 MISP warninglists `*-scanning` 家族(CC0, CIRCL;URL 走
raw.githubusercontent 一跳镜像)+ Xpanse 官方页直读(cortex-docs
scanning-activity)。实测 2026-10-26 普查(docs/research/2026-10-26-scanner-ranges-census.md):
66 列表 29,070 CIDR(5,919 v6,22 裸 IP);污染探针 80.2% 已被本地池标恶意
(N=400, seed 42)→ 立项裁定 = eval 真值层剔除成员(SR-T2),本源只作指控票。

证据形态(2026-10-26 用户裁定, ADR 0011 / GLOSSARY「自报段」「公开研究扫描」;
同日 spec 补定 native_categories 路线, #212 评论):
Evidence(classification="scanner", verdict="malicious",
native_categories=["研究扫描 · <厂商/机构>(自报段)"])——标签载体用 native_categories
(f3csystems.py:53 先例 → _merge.py:306-331 detail dict → _api_models.py:56
透传 → 前端 SourceDetailRow.tsx 内联 chip),不用 native_types(它只喂
ASSET_SLOTS AssetStatement, scanner 无槽,证人行渲染不出来)。非 service 资产槽
(cloudzy 判例),非良性断言(拒 benign②);verdict=malicious 是行为类型断言
("aggressive scanning" 词表),与 sw_scanners 等行为源构成独立两票,
corroborated +1 合法。

r=0.90 统一:自报段=厂商官方声明(高可信),但 MISP 是一跳镜像(对比
cdn_edges 出版商直连 0.95 折档);Xpanse 虽官方直读,同源单值统一 0.90,
防同源双权谱系噪声。stale_days=7(慢变段表,cf. cdn_edges)。
provenance_tier="B"(MISP 一跳镜像主导;Xpanse 官方页同源单值不拆档——
threat 类必声明, test_eval_source_meta 硬规);OpenFilters 镜像不接(56 列表
上游同源,只接一路防回声)、-nt- 22 列表不接(CIRCL 观测提取非自报)、GreyNoise
API-only 红线拒(spec 定案)。

download() 拉全部 67 路并写合并中间件 `scanner_ranges.csv` (cidr,vendor)
(与 cdn_edges (cidr,provider) 同构);harvest() 映射为 Evidence。厂商名从
列表自身 MISP 元数据(name 字段)折短;双族由 rebuild_dual_family 写入侧
自动分派(list 数组 v4/v6 混排,裸 IP 收作 /32)。
"""
import ipaddress
import json
import re

from ._download import atomic_write_bytes
from .._source_base import Source
from .._evidence import Evidence

_MISP_URL_TMPL = ("https://raw.githubusercontent.com/MISP/misp-warninglists/"
                  "main/lists/{name}/list.json")
_XPANSE_URL = ("https://cortex-docs.paloaltonetworks.com/cortex-xpanse/"
               "reference/scanning-activity")

# (list name, 厂商/机构) — 厂商名折短自各列表 list.json 自身的 name 元数据
# (/tmp/misl_*.json 缓存, 2026-10-26 实测; 全 66 条, 勿遗漏)。
_MISP_LISTS = (
    ("a10networks-scanning", "A10 Networks"),
    ("academyforinternetresearch-scanning", "Academy for Internet Research"),
    ("adscore-scanning", "Adscore"),
    ("alphastrike-scanning", "Alpha Strike Labs"),
    ("binaryedge-scanning", "BinaryEdge"),
    ("bitsight-scanning", "BitSight"),
    ("bufferoverrun-scanning", "BufferOver.run"),
    ("censys-scanning", "Censys"),
    ("circl-security-scanning", "CIRCL"),
    ("circl-ssh-scanning", "CIRCL"),
    ("criminalip-scanning", "Criminal IP"),
    ("crowdstrikefalconsurface-scanning", "CrowdStrike Falcon Surface"),
    ("cybcube-scanning", "CyberCube"),
    ("cybergreen-scanning", "CyberGreen Institute"),
    ("cyberok-scanning", "CyberOK"),
    ("cyberresilience-scanning", "CyberResilience"),
    ("cypex-scanning", "Cypex"),
    ("dataplane-scanning", "Dataplane"),
    ("deepfield-scanning", "Nokia Deepfield"),
    ("detectify-scanning", "Detectify"),
    ("edgewatch-scanning", "Edgewatch"),
    ("eset-scanning", "ESET"),
    ("fofa-scanning", "FOFA"),
    ("groupib-scanning", "Group-IB"),
    ("hackertarget-scanning", "Hacker Target"),
    ("hadrian-scanning", "Hadrian"),
    ("hunter-scanning", "Hunter"),
    ("infrawatch-scanning", "Infrawatch"),
    ("internetcleanup-scanner", "Internet Cleanup Foundation"),
    ("internetmeasurementresearch-scanning", "Internet Measurement Research"),
    ("internetmetrics-scanning", "Internet Metrics"),
    ("internetresearchproject-scanning", "Internet Research Project"),
    ("internettl-scanning", "InterneTTL"),
    ("intrinsec-scanning", "Intrinsec"),
    ("intruder-scanning", "Intruder"),
    ("ipinfo-scanning", "IPinfo"),
    ("ipip-scanning", "IPIP"),
    ("ki3-scanning", "KI3"),
    ("knoq-scanning", "Knoq"),
    ("leakix-scanning", "LeakIX"),
    ("mandiantasm-scanning", "Mandiant ASM"),
    ("modat-scanner", "Modat"),
    ("netlas-scanning", "Netlas"),
    ("netscout-scanning", "NETSCOUT"),
    ("netsecscan-scanning", "NetSecScan"),
    ("odin-scanning", "Cyble ODIN"),
    ("onlyscans-scanning", "ONLYSCANS"),
    ("onyphe-scanner", "Onyphe"),
    ("pocnroll-scanning", "pocnroll"),
    ("probethenet-scanning", "ProbeTheNet"),
    ("quake-scanning", "360 Quake"),
    ("rapid7-scanning", "Rapid7"),
    ("recordedfuture-scanning", "Recorded Future"),
    ("recyber-scanning", "Recyber"),
    ("researchscanner-scanning", "Research Scanner"),
    ("rootevidence-scanning", "Root Evidence"),
    ("securityresearch-scanning", "securityresearch.net"),
    ("shadowforce-scanning", "Shadowforce"),
    ("shodan-scanning", "Shodan"),
    ("stretchoid-scanning", "Stretchoid"),
    ("tenableasm-scanning", "Tenable ASM"),
    ("university-scanning", "University scanners"),
    ("visionheight-scanning", "VisionHeight"),
    ("xmco-scanning", "XMCO"),
    ("zern-scanning", "ZERN"),
    ("zoomeye-scanning", "ZoomEye"),
)

# (name, url, vendor, fmt) — cdn_edges (provider,url,fmt) 同构 +fmt:
# MISP 66 路共享一个 URL 模板(list.json),Xpanse 走 HTML 直读。
_FEEDS = tuple(
    (name, _MISP_URL_TMPL.format(name=name), vendor, "misp")
    for name, vendor in _MISP_LISTS
) + (("xpanse", _XPANSE_URL, "Palo Alto Xpanse", "xpanse"),)

# HTML 直读用:最宽形态护栏(IPv4/IPv6 字符集 + 前缀长),候选再经
# ip_network 语义闸过滤(HTML 噪声进不来;坏前缀长 ValueError 弃)。
_CIDR_TOKEN_RE = re.compile(r"[0-9A-Fa-f:.]+/\d{1,3}")


class ScannerRangesSource(Source):
    name = "scanner_ranges"
    category = "threat"
    filename = "scanner_ranges.csv"    # combined intermediate written by download()
    fields = ("is_malicious",)
    classification_type = "scanner"
    verdict = "malicious"
    stale_days = 7                      # 慢变段表(cf. cdn_edges)
    reliability = 0.90                  # 自报段官方声明 × 一跳镜像折档(spec 定案)
    provenance_tier = "B"               # MISP 一跳镜像主导(threat 类必声明,test_eval_source_meta)
    authoritative_for = ()              # corroboration only (SM-F1, sw_scanners 同款)

    def download(self, token=None) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for _name, url, vendor, fmt in _FEEDS:
            data = self._http_get(url)
            rows.extend((cidr, vendor) for cidr in _parse(data, fmt))
        atomic_write_bytes(self._path,
                           "".join(f"{c},{v}\n" for c, v in rows).encode("utf-8"))

    def harvest(self):
        for line in self._path.read_text().splitlines():
            if not line.strip():
                continue
            cidr, vendor = line.split(",", 1)
            yield cidr, Evidence(
                classification_type=self.classification_type,
                verdict=self.verdict,
                reliability=self.reliability,
                # 标签走 native_categories(f3csystems 先例,spec 补定):
                # native_types 只喂 ASSET_SLOTS,scanner 无槽渲染不出。
                native_categories=[f"研究扫描 · {vendor}(自报段)"],
            )


def _norm_cidr(entry: str) -> str | None:
    """归一为规范 CIDR 字符串;裸 IP 收作 /32(或 v6 /128),坏条目 → None。"""
    try:
        return str(ipaddress.ip_network(entry.strip(), strict=False))
    except ValueError:
        return None


def _parse(data: bytes, fmt: str):
    """Yield CIDR strings from one feed's raw bytes (both families).

    misp: list.json {"list": [...]} — v4/v6 混排(实测 5,919 v6),非字符串
    与坏条目弃;裸 IP 经 _norm_cidr 收作 /32。
    xpanse: 官方页 HTML — _CIDR_TOKEN_RE 提候选(文档表格内的 9 CIDR),
    ip_network 语义闸过滤页面噪声。
    """
    if fmt == "misp":
        d = json.loads(data)
        for entry in d.get("list") or []:
            if not isinstance(entry, str):
                continue
            cidr = _norm_cidr(entry)
            if cidr:
                yield cidr
    elif fmt == "xpanse":
        text = data.decode("utf-8", errors="ignore")
        for token in _CIDR_TOKEN_RE.findall(text):
            cidr = _norm_cidr(token)
            if cidr:
                yield cidr
