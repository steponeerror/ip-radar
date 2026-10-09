"""Cloud provider public ranges — five publishers fused into one source.

The five former per-provider sources (aws_ranges / gcp_ranges / azure_ranges
/ oracle_ranges / alibaba_ranges — identical asset contract: service="cloud",
is_hosting=True, provider identity on native_types, empty asset-only verdict)
are fused into a single table-driven source (spec 2026-10-02
cloud-ranges-fusion). Multi-feed single-source precedent: cdn_edges;
directory intermediates + partial-failure tolerance precedent: blocklist_de.

Sources, verbatim from the five old files:
- AWS   ip-ranges.amazonaws.com/ip-ranges.json — the full cloud footprint
        (prefixes + ipv6_prefixes; ALL prefixes, no CLOUDFRONT filter).
- Google gstatic goog.json — the whole Google footprint (ipv4Prefix/ipv6Prefix).
- Azure Service Tags (Public cloud), date-stamped behind a JS-gated download
        page → two-step fetch; harvest keeps only the cloud-wide `AzureCloud`
        tag (region tags are subsets and would double-count).
- Oracle Cloud docs.oracle.com public_ip_ranges.json — regions[].cidrs[].
- Alibaba cloud-ip-ranges.com — third-party aggregator of the official
        ranges (NOT publisher-self: reliability 0.75 vs 0.95; license
        unstated, user-approved 2026-09-28). Content guard: the site is a
        Rails app; a 200-HTML error/maintenance page must never replace the
        intermediate (same P1 class as danmeuk's rate-limit page).

Each provider keeps the guards it always had (fetch verbatim-official JSON
for aws/gcp/oracle/azure; alibaba validates ≥1 ipaddress-acceptable line and
returns normalized CIDR-per-line text). Intermediates live per provider in
<data_dir>/cloud_ranges/ (aws.json / gcp.json / azure.json / oracle.json /
alibaba.txt), native format each; missing provider files are tolerated at
rebuild (blocklist_de semantics). reliability is per-row from the table:
publisher-self 0.95 ×4, Alibaba aggregator 0.75.
"""
import ipaddress
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Iterator

from .._evidence import Evidence
from .._source_base import Source
from .._types import FeedHealth, SourceHealth
from ._download import redact_url

logger = logging.getLogger(__name__)

_AWS_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
_GCP_URL = "https://www.gstatic.com/ipranges/goog.json"
_ORACLE_URL = "https://docs.oracle.com/iaas/tools/public_ip_ranges.json"
_ALIBABA_URL = "https://cloud-ip-ranges.com/download/alibaba.txt"
# details/confirmation page → current ServiceTags_Public_<date>.json link
_PAGE = "https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519"
_LINK_RE = re.compile(r"https://download\.microsoft\.com/download/[^\s\"']+"
                      r"ServiceTags_Public_\d+\.json")


# ── fetch: HTTP 经 Source._http_get;返回写入中间文件的原始字节 ──
# (token 形参为 download 循环统一调用形态保留,传输层不可取消)

def _fetch_json(url: str, token=None) -> bytes:
    """官方 JSON 原文直取(守卫:空响应与非 JSON 均 raise —— 200-HTML 错误页
    不得换掉好中间文件;azure/alibaba 各自已有守卫,此为 aws/gcp/oracle
    补齐;raise 由 download 计入单家失败,走部分容忍路径)。"""
    data = Source._http_get(url)
    if not data.strip():
        raise RuntimeError(f"empty response from {redact_url(url)}")
    try:
        json.loads(data)
    except ValueError:
        raise RuntimeError(
            f"non-JSON response from {redact_url(url)} — likely an HTML error page")
    return data


def _fetch_aws(token=None) -> bytes:
    return _fetch_json(_AWS_URL, token)


def _fetch_gcp(token=None) -> bytes:
    return _fetch_json(_GCP_URL, token)


def _fetch_oracle(token=None) -> bytes:
    return _fetch_json(_ORACLE_URL, token)


def _fetch_azure(token=None) -> bytes:
    """两步抓取(逐字移植 azure_ranges):确认页(浏览器 UA)暴露当前直链,
    regex 无链接即 raise;直链 JSON 非空校验后原文返回。"""
    html = Source._http_get(
        _PAGE,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ).decode("utf-8", errors="replace")
    m = _LINK_RE.search(html)
    if not m:
        raise RuntimeError("no ServiceTags_Public link on confirmation page")
    data = Source._http_get(m.group(0))
    if not data.strip():
        raise RuntimeError("empty ServiceTags JSON")
    return data


def _iplist_lines(raw: bytes) -> list[str]:
    """CIDR-per-line 文本 → 行列表(IpListSource.parse_raw 移植:去空白、
    跳过 # 注释与空行;不做逐行校验 — 校验在 _validate_raw/_parse_alibaba)。"""
    return [
        line.strip()
        for line in raw.decode(errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _validate_raw(raw: bytes) -> None:
    """Content guard(alibaba feed,逐字移植):要求 ≥1 行 ipaddress 可接受
    (与 parse 同一解析器);否则视为 200-HTML 错误/维护页并 raise —— 垃圾
    不得成为中间文件。"""
    for line in _iplist_lines(raw):
        try:
            ipaddress.ip_network(line, strict=False)
            return
        except ValueError:
            continue
    raise RuntimeError(
        "no IP/CIDR lines in response — likely an HTML error/maintenance page")


def _fetch_alibaba(token=None) -> bytes:
    """聚合商文本:守卫校验 + 归一化为 CIDR-per-line 中间文件(旧 download
    的 parse_raw → join 路径移植)。"""
    raw = Source._http_get(_ALIBABA_URL)
    _validate_raw(raw)
    entries = _iplist_lines(raw)
    return ("\n".join(entries) + "\n").encode("utf-8")


# ── parse: 中间文件字节 → CIDR 迭代器(逐字移植各旧 harvest) ──

def _parse_aws(data: bytes) -> Iterator[str]:
    d = json.loads(data)
    for p in d.get("prefixes", []):
        prefix = p.get("ip_prefix")
        if prefix:
            yield prefix
    for p in d.get("ipv6_prefixes", []):
        prefix = p.get("ipv6_prefix")
        if prefix and ":" in prefix:
            yield prefix


def _parse_gcp(data: bytes) -> Iterator[str]:
    d = json.loads(data)
    for p in d.get("prefixes", []):
        v4 = p.get("ipv4Prefix")
        v6 = p.get("ipv6Prefix")
        if v4:
            yield v4
        if v6 and ":" in v6:
            yield v6


def _parse_azure(data: bytes) -> Iterator[str]:
    d = json.loads(data)
    for v in d.get("values", []):
        if v.get("name") != "AzureCloud":
            continue   # region tags (AzureCloud.EastUS …) are subsets → skip
        for prefix in (v.get("properties") or {}).get("addressPrefixes", []):
            yield prefix


def _parse_oracle(data: bytes) -> Iterator[str]:
    d = json.loads(data)
    for region in d.get("regions", []):
        for c in region.get("cidrs", []):
            cidr = c.get("cidr") if isinstance(c, dict) else c
            if cidr:
                yield cidr


def _parse_alibaba(data: bytes) -> Iterator[str]:
    for line in _iplist_lines(data):
        try:
            yield str(ipaddress.ip_network(line, strict=False))
        except ValueError:
            continue


# (provider 展示名, fetch_fn, parse_fn, 中间文件名, reliability, stale_days)
# provider 名冻结 = native_types.service 现值(零答案变化承诺的组成部分);
# per-provider reliability:官方四家 0.95 / 第三方聚合商 Alibaba 0.75;
# Azure stale 14 = 官方周更节奏放宽,其余 7。
_FEEDS = (
    ("AWS", _fetch_aws, _parse_aws, "aws.json", 0.95, 7),
    ("Google", _fetch_gcp, _parse_gcp, "gcp.json", 0.95, 7),
    ("Azure", _fetch_azure, _parse_azure, "azure.json", 0.95, 14),
    ("Oracle Cloud", _fetch_oracle, _parse_oracle, "oracle.json", 0.95, 7),
    ("Alibaba", _fetch_alibaba, _parse_alibaba, "alibaba.txt", 0.75, 7),
)

_BY_FILE = {entry[3]: entry for entry in _FEEDS}

# 五个旧单源时代的数据文件名(download 首跑清理目标);sidecar 命名沿
# Source 基类:<name>.lmdb.<epoch>/ 目录 + ptr/count/cov 文件 + .v6.lmdb.*
# 变体(blocklist_de._cleanup_legacy 同款 glob,加 v6)。
_LEGACY_FILES = (
    "aws_ranges.json",
    "gcp_ranges.json",
    "azure_ranges.json",
    "oracle_ranges.json",
    "alibaba_ranges.txt",
)


def _provider_by_file(filename: str) -> str | None:
    """中间文件名 → provider 展示名查表(None = 非本源 feed 文件)。"""
    entry = _BY_FILE.get(filename)
    return entry[0] if entry else None


class CloudRangesSource(Source):
    """五家云厂商 range 源融合(见模块 docstring);rebuild 用基类
    Source.rebuild(吃 harvest 累积,五旧源现状即如此)。"""

    name = "cloud_ranges"
    category = "asset"
    filename = "cloud_ranges"      # → _path 为目录,blocklist_de 同式
    fields = ("service", "is_hosting")
    authoritative_for = ()
    reliability = 0.95             # 源级 = 官方四家;per-row 查表(Alibaba 0.75)
    url = None                     # 单源多 host,无单一权威 URL(cn_isp 先例)
    stale_days = 7                 # scheduler due 节奏消费此值;per-feed 阈值在 _FEEDS

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self._path = data_dir / "cloud_ranges"   # directory, not file
        # 最近一次 download 的失败家(provider 展示名;空列表 = 全绿)。
        # RefreshScheduler 消费此信号:非空 = "done 但部分失败" → 走
        # _BACKOFF_SECONDS 封顶的 backoff 重试而非 +stale_days(spec §2.3)。
        self.last_partial_failure: list[str] = []

    @property
    def download_host(self) -> str | None:
        # 单源多 host(五家出版方各自域名),无单一权威主机 — cn_isp 先例。
        return None

    def _cleanup_legacy(self) -> None:
        """删除五个旧单源时代的数据文件及其 LMDB sidecar(含 v6 变体)。

        sidecar 形态两种(blocklist_de 同款):epoch 目录 rmtree;
        ptr/count/cov 等文件 sidecar unlink。"""
        for name in _LEGACY_FILES:
            (self._path.parent / name).unlink(missing_ok=True)
            for pattern in (f"{name}.lmdb.*", f"{name}.v6.lmdb.*"):
                for side in self._path.parent.glob(pattern):
                    if side.is_dir():
                        shutil.rmtree(side, ignore_errors=True)
                    else:
                        side.unlink(missing_ok=True)

    def download(self, token=None) -> None:
        """五家逐个:fetch → scratch `<file>.dl` → os.replace 原子落地。

        单家失败 logger.warning 计数且保留旧中间文件(cn_isp 部分容忍:
        harvest 本就容忍缺家,旧数据继续可用),失败家名记入
        self.last_partial_failure(scheduler 据此对 done-但-部分失败走
        backoff 封顶重试);五家全挂才 raise。os.replace 落地新目录项,
        目录 mtime 随之前进 — needs_convert 语义保持。_cleanup_legacy 在
        fetch 循环之后(回滚安全:升级首跑 fetch 全挂时五个旧单源文件还在,
        回滚上一版本仍可用;旧中间文件对新源本就不可读,后置零差别)。"""
        self._path.mkdir(parents=True, exist_ok=True)
        failed: list[str] = []
        for provider, fetch, _parse, filename, _rel, _stale in _FEEDS:
            dest = self._path / filename
            scratch = dest.with_name(dest.name + ".dl")
            try:
                data = fetch(token)
                scratch.write_bytes(data)
                os.replace(scratch, dest)
                logger.info(f"cloud_ranges: downloaded {provider} ({filename})")
            except Exception as e:
                failed.append(provider)
                logger.warning(
                    f"cloud_ranges: {provider} download failed "
                    f"({filename}): {e} — keeping existing intermediate")
            finally:
                scratch.unlink(missing_ok=True)
        self.last_partial_failure = failed
        if len(failed) == len(_FEEDS):
            raise RuntimeError(
                f"all cloud_ranges feeds failed to download: "
                f"{[f[0] for f in _FEEDS]}")
        self._cleanup_legacy()

    def health(self) -> SourceHealth:
        """目录形覆写(blocklist_de 同式):逐家 mtime → FeedHealth,阈值查
        _FEEDS 表(Azure 14,不硬编码);任一家超期或无任何文件即源级
        stale;last_updated = max-mtime;其余字段沿基类语义。"""
        feeds = []
        mtimes = []
        for provider, _fetch, _parse, filename, _rel, stale_days in _FEEDS:
            p = self._path / filename
            if p.exists():
                mtime = p.stat().st_mtime
                mtimes.append(mtime)
                feeds.append(FeedHealth(
                    name=provider,
                    last_updated=time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime)),
                    is_stale=time.time() - mtime > stale_days * 86400,
                ))
            else:
                feeds.append(FeedHealth(
                    name=provider, last_updated=None, is_stale=True))
        file_mtime = max(mtimes) if mtimes else None
        return SourceHealth(
            name=self.name,
            loaded=self._reader is not None,
            record_count=self._count,
            last_updated=(time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(file_mtime))
                          if file_mtime else None),
            is_stale=file_mtime is None or any(f.is_stale for f in feeds),
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets,
            feeds=feeds,
        )

    def harvest(self):
        if not self._path.exists():
            return
        for provider, _fetch, parse, filename, reliability, _stale in _FEEDS:
            p = self._path / filename
            if not p.exists():
                logger.warning(f"cloud_ranges: missing {provider} "
                               f"intermediate ({filename}) — skipped")
                continue
            ev = Evidence(
                service="cloud",
                is_hosting=True,
                native_types={"service": provider},
                # 弃权拼写:由 to_dict 特判保留,读回按 "" 处理不兑底(R17A-1)
                verdict="",
                reliability=reliability,
            )
            for cidr in parse(p.read_bytes()):
                yield cidr, ev
