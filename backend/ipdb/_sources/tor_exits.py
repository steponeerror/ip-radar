"""Tor exit addresses source — IpListSource with custom parse_raw.

归一化文件行形态：`ip[,ts]`（ts 为 ExitAddress 行内时间戳，空格已转 T）；
无 ts 行兼容（仅 ip）。
"""
import ipaddress
import re
from ._base import IpListSource


_EXIT_ADDR_RE = re.compile(r"^ExitAddress\s+(\S+)(?:\s+(\S+ \S+))?")


class TorExitSource(IpListSource):
    name = "tor_exits"
    category = "asset"
    url = "https://check.torproject.org/exit-addresses"
    filename = "tor-exit-addresses.txt"
    fields = ("is_tor",)
    classification_type = "tor"
    verdict = "suspicious"
    stale_days = 1
    reliability = 0.95
    authoritative_for = ("is_tor",)

    def parse_raw(self, raw: bytes) -> list[str]:
        ips = []
        for line in raw.decode(errors="ignore").splitlines():
            m = _EXIT_ADDR_RE.match(line)
            if m:
                try:
                    ipaddress.ip_address(m.group(1))   # 版本感知(v6 ExitAddress 也收)
                except (ipaddress.AddressValueError, ValueError):
                    continue
                ts = m.group(2).replace(" ", "T") if m.group(2) else ""
                ips.append(f"{m.group(1)},{ts}" if ts else m.group(1))
        return ips

    def rebuild(self, progress=None) -> int:
        """重建 LMDB。覆写基类：文件行为 `ip[,ts]`（parse_raw 归一化产物），
        ts → last_seen（per-row，基类单一 insert_data 不支持）。"""
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
                ip, _, ts = line.partition(",")
                try:
                    net = _ipa.ip_network(
                        f"{ip.strip()}/{'128' if ':' in ip else '32'}",
                        strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                ev = Evidence(
                    classification_type=self.classification_type,
                    verdict=self.verdict,
                    reliability=self.reliability,
                    is_tor=True,
                    native_types={"is_tor": "TOR"},
                    last_seen=ts.strip() or None,
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
    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_tor=True,
            native_types={"is_tor": "TOR"},
        ).to_dict()
