"""Spamhaus DROP list — IpListSource subclass."""
from .._source_base import Source
from ._base import IpListSource
from ._download import atomic_write_bytes, redact_url


class SpamhausSource(IpListSource):
    name = "spamhaus"
    category = "threat"
    url = "https://www.spamhaus.org/drop/drop.txt"
    filename = "spamhaus_drop.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.90
    authoritative_for = ()               # SM-F1:is_malicious 无证据键生产者(幻影轴),不声明

    _V6_URL = "https://www.spamhaus.org/drop/dropv6.txt"

    def download(self, token=None) -> None:
        """双 URL 拉取拼接单文件(spec §5.1)。F-4:任一兄弟失败 → 不写
        缺半边的覆盖(旧 join 文件字节级保留),失败侧记
        self.last_partial_failure(["v4"]/["v6"],scheduler 对 v6 走 done-但-
        部分失败 backoff);v4 失败/两路全挂 raise 走既有退避。"""
        import logging
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            v4 = Source._http_get(self.url)
            if not v4.strip():
                raise RuntimeError(f"empty response from {redact_url(self.url)}")
        except Exception:
            self.last_partial_failure = ["v4"]
            raise
        try:
            v6 = Source._http_get(self._V6_URL)
            if not v6.strip():
                raise RuntimeError(f"empty v6 sibling from {self._V6_URL}")
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"spamhaus dropv6 fetch failed: {e} — keeping existing join file")
            self.last_partial_failure = ["v6"]
            return
        self.last_partial_failure = []
        if v4 and not v4.endswith(b"\n"):
            v4 += b"\n"
        atomic_write_bytes(self._path, v4 + v6)

    def rebuild(self, progress=None) -> int:
        """重建 LMDB。覆写基类：保留 `;` 后的 SBL 案件编号 → extra.sbl_id
        （基类直接截断丢弃）。"""
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family, commit_dual_family
        from .._evidence import Evidence
        if not self._path.exists():
            return 0
        records = []
        covered = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                sbl_id = ""
                if ";" in line:
                    line, _, tail = line.partition(";")
                    line = line.strip()
                    tail = tail.strip()
                    if tail.startswith("SBL"):
                        sbl_id = tail.split()[0]
                if not line:
                    continue
                try:
                    net = _ipa.ip_network(line, strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                ev = Evidence(
                    classification_type=self.classification_type,
                    verdict=self.verdict,
                    reliability=self.reliability,
                    extra={"sbl_id": sbl_id} if sbl_id else None,
                ).to_dict()
                records.append((str(net), [ev]))
                covered.append(str(net))
        cov4 = covered_ip_count(c for c in covered if ":" not in c)
        cov6 = covered_ip_count(
            (c for c in covered if ":" in c), ip_version=6)
        return commit_dual_family(
            self, records, cov4=cov4, cov6=cov6, progress=progress)
