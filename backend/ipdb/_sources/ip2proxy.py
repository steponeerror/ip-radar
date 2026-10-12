"""IP2Proxy PX2 LITE source — Source subclass with ZIP handling.

Range→CIDR expansion via ipaddress.summarize_address_range; one CSV row
yields one or more (cidr, Evidence) pairs. Asset labels (is_proxy /
is_hosting / is_tor) ride the Evidence slots; per-asset native labels
(used by the attributes channel) ride native_types → _native_types.

download() streams the ZIP atomically to a sibling .zip via the shared
`download_file` helper (token-aware, mid-stream cancel, long timeout for
the large PX2 LITE archive), then extracts the inner CSV onto `self._path`.
The URL is exposed as `_url` (not `url`) to avoid a property/str clash with
the base class's `url: str` class attribute.
"""
import csv
import ipaddress
import io
import logging
import os
import zipfile
from pathlib import Path

from .._source_base import Source
from .._evidence import Evidence
from ._download import download_file, CancelToken, atomic_write_bytes

logger = logging.getLogger(__name__)


class IP2ProxySource(Source):
    name = "ip2proxy"
    category = "asset"
    filename = "ip2proxy_px2.csv"  # post-extraction
    fields = ("is_proxy", "is_hosting")
    stale_days = 7
    reliability = 0.80
    single_evidence = True   # one evidence per CIDR → stream load() (OOM guard)
    authoritative_for = ("is_proxy",)
    # ADR 0001(2026-10-12, grill Q1):全量资产弃权 —— 类级不再声明
    # classification_type/verdict,对齐 cloud_ranges 全弃权样板(DCH 时代
    # 残留的 "proxy"/"suspicious" 随 VPN/PUB/TOR 一并弃)。指控语料枚举
    # (fusion_replay_gate)与 /api/sources 据此类属性判指控章,勿回填。

    def __init__(self, data_dir: Path):
        self._token = os.environ.get("IP2PROXY_TOKEN", "").strip()
        super().__init__(data_dir=data_dir)

    @property
    def _url(self) -> str:
        if not self._token:
            return ""
        return f"https://www.ip2location.com/download?token={self._token}&file=PX2LITECSV"

    @property
    def download_host(self) -> str | None:
        # Stable vendor host even before IP2PROXY_TOKEN is configured — used for
        # UX labeling, not as a readiness signal (_url="" still means "no fetch").
        return "www.ip2location.com"

    def download(self, token: CancelToken | None = None) -> None:
        if not self._url:
            logger.warning("IP2PROXY_TOKEN not set, skipping IP2Proxy download")
            return
        self._data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading IP2Proxy PX2 LITE...")
        # download_file streams atomically to zip_path (token-aware, mid-stream
        # cancel); then we extract the inner CSV onto _path so base load()'s
        # `_path.exists()` guard passes and harvest() reads plain CSV.
        zip_path = self._data_dir / "ip2proxy_px2.zip"
        try:
            download_file(self._url, zip_path, token=token, timeout=900,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            data = zip_path.read_bytes()
            if not data:
                raise RuntimeError("Empty response")
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                csv_names = [n for n in zf.namelist()
                             if n.lower().endswith(".csv") and "/" not in n and "\\" not in n]
                if not csv_names:
                    raise RuntimeError("no .csv inside IP2Proxy zip")
                payload = zf.read(csv_names[0])
            atomic_write_bytes(self._path, payload)
        finally:
            zip_path.unlink(missing_ok=True)

    def harvest(self):
        """Parse the CSV at _path → yield (cidr, Evidence) per CIDR. Range→CIDR
        expansion means one CSV row may yield several pairs."""
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            first = next(reader, None)
            # PX2 LITE 实际下发无表头:首列是范围端点即数据行,不能丢
            # (带表头变体的首列是 "ip_from" 之类的标签,自然落入跳过分支)
            if first is not None and _is_range_start(first[0] if first else ""):
                yield from self._row_to_cidrs(first)
            for row in reader:
                yield from self._row_to_cidrs(row)

    @staticmethod
    def _row_to_cidrs(row):
        if len(row) < 3:
            return
        raw_start, raw_end, proxy_type = (
            row[0].strip(), row[1].strip(), row[2].strip())
        country_code = row[3].strip() if len(row) > 3 else ""
        country_name = row[4].strip() if len(row) > 4 else ""
        start_ip = _int_to_ip(raw_start) or raw_start
        end_ip = _int_to_ip(raw_end) or raw_end
        try:
            sa = ipaddress.IPv4Address(start_ip)
            ea = ipaddress.IPv4Address(end_ip)
        except (ipaddress.AddressValueError, ValueError):
            return
        ev = _proxy_evidence(proxy_type)
        if ev is None:
            return
        if country_code:
            ev.country_code = country_code.upper()
        if country_name or proxy_type:
            ev.extra = dict(ev.extra or {})
            if country_name:
                ev.extra["country_name"] = country_name
            ev.extra["proxy_type"] = proxy_type
        for cidr in ipaddress.summarize_address_range(sa, ea):
            yield str(cidr), ev


def _is_range_start(tok: str) -> bool:
    """数据行首列是范围端点:十进制整数或点分 IPv4;表头("ip_from" 等)不是。"""
    t = tok.strip().strip('"').strip()
    if t.isdigit():
        return True
    try:
        ipaddress.IPv4Address(t)
        return True
    except ValueError:
        return False


def _int_to_ip(s: str) -> str | None:
    try:
        n = int(s)
        if n < 0 or n > 0xFFFFFFFF:
            return None
        return str(ipaddress.IPv4Address(n))
    except (ValueError, ipaddress.AddressValueError):
        return None


def _proxy_evidence(proxy_type: str) -> Evidence | None:
    """Map an IP2Proxy proxy_type to asset-only Evidence (or None to drop).

    ADR 0001 (2026-10-12, grill Q1): ip2proxy 全量资产弃权 —— VPN/PUB/TOR
    继 DCH (SM-F2) 之后同判:挂着代理/出口节点是基础设施属性,不是滥用
    指控;滥用由行为源立证,corroborated 自然涨分。四型统一镜像
    cloud_ranges 形状(classification_type 缺省 None、verdict="" 弃权):
    只走 attributes 通道,不产分类组、不计票、不产 STIX Indicator。
    is_proxy/is_tor 标签照常;数据摄取(fields/harvest)不动 —— 改的是
    指控计票资格,不是数据面。

    Drops SES/WEB/etc. Per-asset labels ride in native_types (→ _native_types).
    """
    pt = proxy_type.strip().upper()
    if pt not in ("VPN", "PUB", "DCH", "TOR"):
        return None
    if pt == "DCH":
        return Evidence(
            is_hosting=True,
            native_types={"is_hosting": "DCH"},
            verdict="",   # 弃权拼写:由 to_dict 特判保留,读回按 "" 处理不兑底
        )
    if pt == "TOR":
        return Evidence(
            is_tor=True,
            native_types={"is_tor": "TOR"},
            verdict="",
        )
    # VPN / PUB
    return Evidence(
        is_proxy=True,
        native_types={"is_proxy": pt},
        verdict="",
    )
