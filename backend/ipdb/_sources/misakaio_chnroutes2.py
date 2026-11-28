"""misakaio/chnroutes2 — aggregated China network routes (CIDR list).

https://github.com/misakaio/chnroutes2
Raw dump: https://raw.githubusercontent.com/misakaio/chnroutes2/master/chnroutes.txt
Format: two '#' header lines (route-server dump timestamp + aggregation
stats), then one IPv4 CIDR per line (~3904 prefixes, real fetch
2026-11-20). Hourly auto-dump repo — the header timestamp is the freshness
signal. chnroutes6.txt does not exist (404, verified 2026-11-20): v4-only.

Evidence shape follows the geo_asn scalar precedent (geolite_city /
dbip_city / iptoasn): country_code="CN" per CIDR, no fusion-core fields.
country_code authority stays with the geo voters (authoritative_for=());
chnroutes2 joins the country vote as a BGP-derived witness.
"""
from ._base import IpListSource
from .._evidence import Evidence


class MisakaioChnroutes2Source(IpListSource):
    name = "misakaio_chnroutes2"
    category = "geo_asn"
    url = ("https://raw.githubusercontent.com/misakaio/chnroutes2/"
           "master/chnroutes.txt")
    filename = "chnroutes.txt"
    fields = ("country_code",)
    stale_days = 7                # hourly auto-dump; 7d silence = feed dead
    reliability = 0.85            # BGP route-server dump aggregation; cn_isp peer
    authoritative_for = ()        # joins country vote, no exclusive authority
    provenance_tier = "B"         # B=community (single-curator BGP aggregation)
    infra_noise_filter = False         # 良性源用不上;显式声明是 #531 契约(基类默认已翻 True)

    def get_insert_data(self) -> dict:
        # scalar geo shape — same as geolite_city/dbip_city: source sets
        # country_code only; classification/reliability stay unset (fusion
        # core derives reliability from class attr at merge time).
        return Evidence(country_code="CN").to_dict()


# ── PEP 562 import-alias contract(主类名拼法收敛)──
# 消费方 import 冻结拼法;三种规范形都可导入,且均不进 dir()
# (registry 自动发现按 dir() 枚举,避免同类双注册/roster 双行)。
_IMPORT_ALIASES = {
    "Misakaiochnroutes2Source": "MisakaioChnroutes2Source",    # 令牌机械形
    "MisakaioCHNROUTES2Source": "MisakaioChnroutes2Source",    # 缩写全大写形
}


def __getattr__(name):
    if name in _IMPORT_ALIASES:
        return globals()[_IMPORT_ALIASES[name]]
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}")
