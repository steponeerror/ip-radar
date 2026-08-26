"""Spamhaus DROP list — IpListSource subclass."""
from .._source_base import Source
from ._base import IpListSource


class SpamhausSource(IpListSource):
    name = "spamhaus"
    url = "https://www.spamhaus.org/drop/drop.txt"
    filename = "spamhaus_drop.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.90
    authoritative_for = ["is_malicious"]

    _V6_URL = "https://www.spamhaus.org/drop/dropv6.txt"

    def download(self, token=None) -> None:
        """双 URL 拉取拼接单文件(spec §5.1)。v6 兄弟失败容忍(dataplane 先例),
        v4 主文件失败 raise 走既有退避。"""
        import logging
        self._data_dir.mkdir(parents=True, exist_ok=True)
        v4 = Source._http_get(self.url)
        if not v4.strip():
            raise RuntimeError(f"empty response from {self.url}")
        try:
            v6 = Source._http_get(self._V6_URL)
            if not v6.strip():
                raise RuntimeError(f"empty v6 sibling from {self._V6_URL}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"spamhaus dropv6 fetch failed: {e}")
            v6 = b""
        if v4 and not v4.endswith(b"\n"):
            v4 += b"\n"
        self._path.write_bytes(v4 + v6)

    def rebuild(self, progress=None) -> int:
        """重建 LMDB。覆写基类：保留 `;` 后的 SBL 案件编号 → extra.sbl_id
        （基类直接截断丢弃）。"""
        import ipaddress as _ipa
        import time
        from ._lmdb import covered_ip_count, rebuild_dual_family
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
        n4, n6 = rebuild_dual_family(
            records, self._lmdb_base, self._lmdb6_base,
            reader_setter4=lambda e: setattr(self, "_reader", e),
            reader_setter6=lambda e: setattr(self, "_reader6", e),
            flag_setter4=lambda v: setattr(self, "_disjoint", v),
            flag_setter6=lambda v: setattr(self, "_disjoint6", v),
            covered4=cov4, covered6=cov6, progress=progress)
        self._count = n4
        self._count6 = n6
        self._covered_ips = cov4
        self._covered_v6_nets = cov6
        self._loaded_at = time.time()
        return n4
