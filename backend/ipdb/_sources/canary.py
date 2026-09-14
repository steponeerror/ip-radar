# backend/ipdb/_sources/canary.py
"""Hidden internal canary source — lineage watermark layer 1
(spec: docs/superpowers/specs/2026-09-14-data-watermark-design.md §5.2).

internal=True: query loop YES; /api/sources, get_status, _db_loaded, eval,
toggle, stale list NO (see _registry wiring). Silent disclosure (decision
#10): never mention in README/CHANGELOG/release notes.
"""
import random
import time

from .._evidence import Evidence
from .._types import SourceHealth
from .._watermark import BATCH_SLOT_ZERO, N_MAX, N_MIN, canary_family
from ._base import IpListSource
from ._lmdb import commit_dual_family, covered_ip_count


class CanarySource(IpListSource):
    name = "sentinel"
    category = "threat"
    internal = True              # registry exclusion marker (default False)
    filename = "sentinel"        # LMDB base = <data_dir>/sentinel.lmdb
    url = ""                     # never networked (local-only redline)
    fields = ("is_malicious",)   # shape-compatible with threat sources
    stale_days = 10**6           # belt: health() override is the real guard
    reliability = 0.60           # class-level; per-record derived value wins
    authoritative_for = ()

    def download(self, token=None) -> None:
        return None              # no-op success; never schedules real fetch

    def rebuild(self, progress=None) -> int:
        rng = random.SystemRandom()
        n = rng.randrange(N_MIN, N_MAX)          # 150 <= n < 400, unpublished
        picked = rng.sample(canary_family(), n)
        records, covered = [], []
        for c in picked:
            ev = Evidence(
                classification_type=c.ctype,
                verdict="suspicious",
                reliability=c.reliability,
                first_seen=c.first_seen,
                last_seen=c.last_seen,
                extra={"batch_id": BATCH_SLOT_ZERO},
            ).to_dict()
            cidr = f"{c.ip}/{'128' if c.is_v6 else '32'}"
            records.append((cidr, [ev]))
            covered.append(cidr)
        cov4 = covered_ip_count(x for x in covered if ":" not in x)
        cov6 = covered_ip_count(
            (x for x in covered if ":" in x), ip_version=6)
        n4 = commit_dual_family(
            self, records, cov4=cov4, cov6=cov6, progress=progress)
        # 返回总嵌入数 N(两族合计);commit_dual_family 已回写 _count6=n6
        return n4 + self._count6

    def health(self) -> SourceHealth:
        """F2: loaded 反映真实 reader;is_stale 恒 False;无数据文件 mtime。"""
        last_updated = (time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime(self._loaded_at))
                        if self._loaded_at else None)
        return SourceHealth(
            name=self.name,
            loaded=self._reader is not None or self._reader6 is not None,
            record_count=self._count + self._count6,   # 总嵌入数 N(spec §5.2)
            last_updated=last_updated,
            is_stale=False,
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets,
        )
