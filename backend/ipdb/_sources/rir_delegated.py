"""RIR delegated-extended 五件套 — 注册分配元数据源(信息维度批,2026-10-10 grill #3)。

五 RIR 每日发布的 delegated-extended 文件(NRO 标准 `|` 格式)聚合为单一源。
行:registry|cc|type|start|value|yyyymmdd|status|opaque-id。裁定口径:
- 只收 allocated/assigned;available/reserved 跳过(未分配行信息量为负,宁少算)
- **不投任何合并字段的票**(ip_range/country 已 100% 满格,第四证人是回声,
  违背「回声不是印证」);独有维度走 extra:registry/reg_country/alloc_date/status
  → lookup 的 rir 旁路 → LookupResult.registration 顶层信息块
- reg_country 是**注册国 ≠ 地理国**(geolite "registered_country deliberately
  never read" 同款纪律),绝不进 country_code 融合
- ipv4: start+count(地址数)→ 范围展开 CIDR;ipv6: value=前缀长,直取网络

多 feed 形(cloud_ranges 先例):data_dir/rir_delegated/ 目录,每 RIR 一文件;
部分失败容忍(last_partial_failure → scheduler backoff),全败才 raise;
每 RIR ≥3,000 ipv4 数据行守卫 fail-closed(最小 RIR AFRINIC 实测 6,108,
2026-10-10,余量 2×)。纯元数据证据:无 classification_type(永不进观测/
指控),verdict="" 弃权拼写(R17A1 同款;资产信息位作证不指控)。
"""
import logging
import os
import time
from pathlib import Path

import ipaddress

from .._evidence import Evidence
from .._source_base import Source
from ._download import download_file

logger = logging.getLogger(__name__)

_BASE = {
    "afrinic": "https://ftp.afrinic.net/pub/stats/afrinic/"
               "delegated-afrinic-extended-latest",
    "apnic": "https://ftp.apnic.net/stats/apnic/"
             "delegated-apnic-extended-latest",
    "arin": "https://ftp.arin.net/pub/stats/arin/"
            "delegated-arin-extended-latest",
    "lacnic": "https://ftp.lacnic.net/pub/stats/lacnic/"
              "delegated-lacnic-extended-latest",
    "ripencc": "https://ftp.ripe.net/pub/stats/ripencc/"
               "delegated-ripencc-extended-latest",
}
_MIN_IPV4_ROWS = 3000     # per-RIR guard(最小 RIR 实测 6,108,2026-10-10)
_KEEP_STATUS = frozenset({"allocated", "assigned"})


def _norm_date(raw: str) -> str | None:
    """yyyymmdd → ISO;空/畸形 → None(纯函数,测试直接吃)。"""
    raw = (raw or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _parse_row(parts: list[str]) -> tuple[str, str] | None:
    """一行数据 → (cidr_str, extra_dict);非收录行 → None(纯函数)。

    ipv4: value=count → 范围 summarize(allocations 通常对齐,少数落
    summarize 兜底);ipv6: value=前缀长。坏行静默跳过(宁少算:守卫
    兜总量,残行不炸 harvest)。
    """
    if len(parts) < 7:
        return None
    reg, cc, typ, start, value, date, status = (p.strip() for p in parts[:7])
    if status not in _KEEP_STATUS:
        return None
    extra = {"registry": reg, "status": status}
    if cc and cc != "*":
        extra["reg_country"] = cc
    iso = _norm_date(date)
    if iso:
        extra["alloc_date"] = iso
    if typ == "ipv4":
        try:
            sa = ipaddress.IPv4Address(start)
            count = int(value)
        except (ipaddress.AddressValueError, ValueError):
            return None
        if count <= 0:
            return None
        ea = ipaddress.IPv4Address(int(sa) + count - 1)
        if count == 1:
            nets = [ipaddress.ip_network(f"{sa}/{32}")]
        else:
            nets = list(ipaddress.summarize_address_range(sa, ea))
    elif typ == "ipv6":
        try:
            net = ipaddress.ip_network(f"{start}/{value}", strict=False)
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError,
                ValueError):
            return None
        nets = [net]
    else:
        return None
    # 范围展开可能多网(非对齐分配少数);全部返回,丢了即覆盖缺口。
    # 同行多网共享同一 extra dict — Evidence 每 CIDR 一份,to_dict 原样
    # 序列化,共享安全。
    return [(str(n), extra) for n in nets]


def _parse_rows(line_iter):
    """逐行解析(文件级):summary/头行天然落空。yield (cidr, extra)。"""
    for line in line_iter:
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        parsed = _parse_row(parts)
        if parsed:
            yield from parsed


def _count_ipv4_rows(text: str) -> int:
    return sum(1 for ln in text.splitlines()
               if ln.count("|") >= 6
               and ln.split("|")[2].strip() == "ipv4")


class RirDelegatedSource(Source):
    name = "rir_delegated"
    category = "geo_asn"          # 路由与分配族(展示聚合);零投票字段
    fields = ()                   # 不投任何合并字段的票(回声禁令)
    filename = "rir_delegated"    # 目录名;P1 热修:基类靠 filename 推 _lmdb_base,缺声明则共享裸 `.lmdb`(2026-10-10 生产事故,peeringdb 同病)
    url = None                    # 多 host(五 RIR 各自 ftp),cn_isp/cloud_ranges 先例
    stale_days = 2
    reliability = 0.99            # RIR 官方发布(NRO 标准,五家同步日更)
    authoritative_for = ()
    single_evidence = True        # ~300k CIDR → stream load(OOM 守卫)

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)   # _path/_lmdb_base 全由 filename 推导(目录形)
        self.last_partial_failure: list[str] = []

    @property
    def download_host(self) -> str | None:
        return None                                  # 五 host,无单一权威

    def download(self, token=None) -> None:
        """五家逐个:fetch → scratch → 守卫 → os.replace 原子落地。

        部分失败:保留旧文件记 last_partial_failure(scheduler backoff 消费);
        全败 raise(任务失败,下轮重试)。守卫与 harvest 同口径:仅收
        allocated/assigned 后 ipv4 行 ≥ _MIN_IPV4_ROWS(200-OK 空/坏内容
        不替换旧数据防清源,fail-closed)。
        """
        self._path.mkdir(parents=True, exist_ok=True)
        self.last_partial_failure = []
        for reg, url in _BASE.items():
            dest = self._path / f"{reg}.txt"
            scratch = dest.with_name(dest.name + ".dl")
            try:
                download_file(url, scratch, token=token, timeout=300,
                              headers={"User-Agent": "ip-lookup-tool/1.0"})
                text = scratch.read_text(encoding="utf-8", errors="replace")
                # 守卫数原始 ipv4 行(格式健全性),口径独立于状态过滤
                n4 = _count_ipv4_rows(text)
                if n4 < _MIN_IPV4_ROWS:
                    raise RuntimeError(
                        f"rir_delegated/{reg}: only {n4} ipv4 rows "
                        f"(<{_MIN_IPV4_ROWS}) — existing file kept")
                os.replace(scratch, dest)
                logger.info(f"rir_delegated/{reg}: ok ({n4} ipv4 rows)")
            except Exception as e:
                scratch.unlink(missing_ok=True)
                self.last_partial_failure.append(reg)
                logger.warning(f"rir_delegated/{reg} download failed: {e}")
        if len(self.last_partial_failure) == len(_BASE):
            raise RuntimeError(
                f"all rir_delegated feeds failed: "
                f"{self.last_partial_failure}")

    def health(self):
        """目录形覆写(cloud_ranges 同式):逐 RIR mtime → FeedHealth。"""
        from .._types import FeedHealth, SourceHealth
        feeds, mtimes = [], []
        for reg in _BASE:
            p = self._path / f"{reg}.txt"
            if p.exists():
                m = p.stat().st_mtime
                mtimes.append(m)
                feeds.append(FeedHealth(
                    name=reg,
                    last_updated=time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(m)),
                    is_stale=time.time() - m > self.stale_days * 86400,
                ))
            else:
                feeds.append(FeedHealth(name=reg, last_updated=None,
                                        is_stale=True))
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
        """目录内五文件 → (cidr, Evidence)。v6 由写入侧按 ':' 双族分派。"""
        if not self._path.exists():
            return
        for reg in _BASE:
            p = self._path / f"{reg}.txt"
            if not p.exists():
                logger.warning(f"rir_delegated: missing {reg} file — skipped")
                continue
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for cidr, extra in _parse_rows(f):
                    yield cidr, Evidence(
                        verdict="",       # 弃权拼写(R17A-1):信息位不指控
                        extra=dict(extra),
                    )
