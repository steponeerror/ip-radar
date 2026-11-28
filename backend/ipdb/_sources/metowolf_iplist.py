"""metowolf/iplist — China mainnet CIDR list (Source subclass, A-family).
https://github.com/metowolf/iplist — community-maintained geo lists derived
from APNIC delegated data; this source consumes data/special/china.txt
(plain per-line IPv4 CIDR, no header/comment/timestamp; ~5.5k lines, near
daily pushes). Every member CIDR is CN mainnet → scalar geo Evidence
(country_code=CN + ip_range), no fusion-core accusation (iptoasn archetype).
Freshness caveat: the file itself carries no timestamp; cadence signal is
repo push activity only (dossier 2026-11-20), hence stale_days=7 tolerance.
"""
import logging
from pathlib import Path
from typing import Iterator
from .._evidence import Evidence
from .._source_base import Source
logger = logging.getLogger(__name__)
class MetowolfIplistSource(Source):
    name = "metowolf_iplist"
    category = "geo_asn"
    url = ("https://raw.githubusercontent.com/metowolf/iplist/master/"
           "data/special/china.txt")
    filename = "metowolf_iplist_china.txt"
    fields = ("country_code", "ip_range")
    stale_days = 7
    reliability = 0.75                 # community aggregation of official APNIC data
    provenance_tier = "C"              # derived/aggregated, not publisher-self
    single_evidence = True             # one evidence per CIDR, each yielded once
    infra_noise_filter = False         # 良性源用不上;显式声明是 #531 契约(基类默认已翻 True)
    def harvest(self) -> Iterator[tuple[str, Evidence]]:
        import ipaddress as _ipa
        with open(self._path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    net = _ipa.ip_network(line, strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue           # key column unparseable → drop row
                yield str(net), Evidence(country_code="CN", ip_range=str(net))
# ── PEP 562 拼法别名:主类名 MetowolfIplistSource;变体不出现在 dir(),
#    注册表 dir() 枚举不会双注册。──
_IMPORT_ALIASES = {
    "MetowolfIPListSource": "MetowolfIplistSource",   # 品牌拆词形 IPList
    "MetowolfIpListSource": "MetowolfIplistSource",   # 令牌机械形的 Ip 变体
}
def __getattr__(name: str):
    if name in _IMPORT_ALIASES:
        return globals()[_IMPORT_ALIASES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
