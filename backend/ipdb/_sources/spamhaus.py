"""Spamhaus DROP list — IpListSource subclass."""
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

    def rebuild(self, progress=None) -> int:
        """重建 LMDB。覆写基类：保留 `;` 后的 SBL 案件编号 → extra.sbl_id
        （基类直接截断丢弃）。"""
        import ipaddress as _ipa
        import time
        from ._lmdb import covered_ip_count, rebuild_dual_family
        from .._evidence import Evidence
        if not self._path.exists():
            return 0
        old_reader = self._reader
        old_reader6 = self._reader6
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
        try:
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
        finally:
            for old in (old_reader, old_reader6):
                if old is not None:
                    try:
                        old.close()
                    except Exception:
                        pass
