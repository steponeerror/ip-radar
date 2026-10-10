"""IANA root name servers (named.root hints) — fetched Source subclass.

https://www.internic.net/domain/named.root is the canonical IANA hints
file: 13 root servers A–M, one A + one AAAA each (bare-address rows; the
address itself decides v4/v6 family in rebuild_dual_family). The root rows
moved out of curated infra_services to this dedicated fetched source
(2026-10-10 DNS resolver coverage batch) so refreshes track IANA edits —
the zone serial bumps a few times a year, 7-day staleness is generous.
service="dns" rides the asset slot; the native label is "<letter> root
server" (lowercase first label of the hostname, e.g. "a root server").
Operator names (Verisign, RIPE NCC, ICANN, WIDE …) are curated knowledge
that does not ride the feed and is deliberately dropped — the endorsement
stays purely IANA. verdict="" abstention, same spelling as infra_services
(R17A-1: to_dict 特判保留,读回按 "" 处理不兑底).
"""
import logging
import re

from .._evidence import Evidence
from .._source_base import Source
from ._download import atomic_write_bytes, redact_url

logger = logging.getLogger(__name__)

_URL = "https://www.internic.net/domain/named.root"

# 记录行:`A.ROOT-SERVERS.NET.      3600000      A     198.41.0.4`
# A/AAAA 同形;NS glue 行(`.  3600000  NS  X.ROOT-SERVERS.NET.`)、注释、
# 空行天然不匹配。裸地址决定 v4/v6 族,无需按 rtype 分流。
_RECORD_RE = re.compile(
    r"^([A-Z])\.ROOT-SERVERS\.NET\.\s+\d+\s+(?P<rtype>A|AAAA)\s+(?P<ip>\S+)$",
    re.IGNORECASE)


class RootServersSource(Source):
    name = "root_servers"
    category = "asset"
    fields = ("service",)
    url = _URL
    filename = "root_servers.cache"
    stale_days = 7
    reliability = 0.99
    authoritative_for = ("service",)

    def download(self, token=None) -> None:
        """GET named.root → 校验 → 原子落盘。

        ≥13 A 记录行才放行(200-OK 空/薄内容守卫,skill Phase 3 §8:空文件
        落地会被下次 rebuild 静默清源);失败在写盘前抛出,既有数据文件不动。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = self._http_get(_URL)
        text = data.decode("utf-8", errors="replace")
        n_a = sum(1 for ln in text.splitlines()
                  if (m := _RECORD_RE.match(ln.strip()))
                  and m["rtype"].upper() == "A")
        if n_a < 13:
            raise RuntimeError(
                f"root_servers: only {n_a} A-record lines (<13) from "
                f"{redact_url(_URL)} — existing data file kept")
        atomic_write_bytes(self._path, data)
        logger.info(f"Downloaded {self.name} ({n_a} root A records)")

    def harvest(self):
        import ipaddress as _ipa
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                m = _RECORD_RE.match(line.strip())
                if not m:
                    continue            # 注释/空行/NS glue 行容错跳过
                try:
                    _ipa.ip_address(m["ip"])   # 信任边界:坏地址不入库
                except ValueError:
                    continue
                yield m["ip"], Evidence(
                    service="dns",
                    native_types={"service": f"{m[1].lower()} root server"},
                    verdict="",  # 弃权拼写:同 infra_services(R17A-1)
                )
