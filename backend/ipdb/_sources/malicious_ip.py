"""malicious-ip 5-shard union (romainmarcoux/malicious-ip) — Source subclass.

Five text shards (full-300k-{aa,ab,ac,ad} + full-40k) concatenated by upstream
split → download() unions them in memory, dedups, sorts, atomically publishes
one sorted bare-IP file. Measured 2026-10-18: ~1.0036M distinct keys, hourly
regen, exclusive rate 82.7% (248/300 vs pool, seed 20261018, control 20/20;
dossier docs/research/2026-10-18-blocklist-sweep.md).

r=0.50 floor (grill 2026-10-18): no per-row attribution and dead-source
residue in the union → aggregated multi-party accusations at the reliability
red line, ipsum/firehol twin. derived=True + provenance_tier="C" (聚合派生,
谱系去重用;LINEAGE_CLUSTERS 同步入簇)。All rows are bare malicious-IP
accusations → single ``blacklist``/``malicious`` verdict (knock_knock twin;
Convention 2: no force-fit — the feed carries no per-row category to preserve).
"""
import ipaddress as _ipa
import logging
from pathlib import Path
from urllib.parse import urlparse

from .._evidence import Evidence
from .._source_base import Source
from ._download import CancelToken, CancelledError

logger = logging.getLogger(__name__)

_BASE_URL = "https://raw.githubusercontent.com/romainmarcoux/malicious-ip/master"
_SHARDS = ("full-300k-aa", "full-300k-ab", "full-300k-ac", "full-300k-ad",
           "full-40k")
# 实测全并集 ~1.004M(2026-10-18);低于一半 = 灾难性截断,拒写防清库。
MIN_UNION_KEYS = 500_000


class MaliciousIPSource(Source):
    name = "malicious_ip"
    category = "threat"
    url = ""  # unused — download() fetches _SHARDS from _BASE_URL (firehol 同款)
    filename = "malicious_ip.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 2                       # hourly regen; 2d silence = feed dead
    reliability = 0.50                   # grill 2026-10-18:无逐行归因+死源残留 → 地板
    derived = True                       # 聚合器:谱系去重用(registry derived-set)
    provenance_tier = "C"                # C=聚合派生(S21)
    authoritative_for = ()               # corroboration only (SM-F1)
    # 百万行:base rebuild() 的 single_evidence 路即 rebuild_dual_family 零参
    # factory 流式(covered=Auto;firehol/ipinfo_lite 大表纪律),不物化 acc。
    single_evidence = True

    @property
    def download_host(self) -> str | None:
        return urlparse(_BASE_URL).hostname

    def download(self, token: CancelToken | None = None) -> None:
        """5 片 → 内存并集 → 排序原子写(无证据管线:并集即键集)。

        单片 404/空容忍记 last_partial_failure(碎片轮换属常态;ae 现为 0B),
        全挂才 raise;并集 < MIN_UNION_KEYS 拒写——空/残缺内容永不落
        _path,下次 rebuild 不可能静默清库(活性锚,abuseipdb 空检同旨)。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        union: set[str] = set()
        failed: list[str] = []
        for shard in _SHARDS:
            if token is not None and token.is_cancelled():
                raise CancelledError(f"{self.name} download cancelled")
            url = f"{_BASE_URL}/{shard}.txt"
            try:
                data = self._http_get(url)
            except Exception as e:
                failed.append(shard)
                logger.warning(f"Failed to download {shard}: {e}")
                continue
            if not data.strip():    # 200-OK 空响应同属失败片(firehol 同款空检)
                failed.append(shard)
                logger.warning(f"Empty response for {shard}")
                continue
            for line in data.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    _ipa.ip_address(line)
                except ValueError:
                    continue             # 脏行非证据
                union.add(line)
        self.last_partial_failure = failed
        if len(failed) == len(_SHARDS):
            raise RuntimeError(
                f"all malicious_ip shards failed to download: {_SHARDS}")
        if len(union) < MIN_UNION_KEYS:
            raise RuntimeError(
                f"malicious_ip union {len(union)} < {MIN_UNION_KEYS} keys "
                f"— refusing to write")
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(union)) + "\n")
            tmp.replace(self._path)
        finally:
            tmp.unlink(missing_ok=True)
        logger.info(f"Downloaded malicious_ip ({len(union)} unique IPs)")

    def harvest(self):
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    _ipa.ip_address(line)
                except ValueError:
                    continue
                yield line, Evidence(
                    classification_type=self.classification_type,
                    verdict=self.verdict,
                    reliability=self.reliability,
                )
