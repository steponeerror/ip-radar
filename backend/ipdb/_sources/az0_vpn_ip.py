"""az0/vpn_ip — VPN provider IP list (IpListSource).

Publisher: https://github.com/az0/vpn_ip — hostnames + IPs of consumer VPN
providers (NordVPN, PIA, Windscribe, CyberGhost, ProtonVPN, Hola, ...),
auto-updated by GitHub Actions (update-data.yml). Download face is the CDN
mirror the README pins (http://az0-vpnip-public.oooninja.com/ip.txt), no
auth; the hostname/adguard siblings are domain lists and are NOT consumed.

File shape (2026-11-20 capture, 20634 lines, all bare IPv4, no CIDR):
    # 2026-11-20T12:28:15Z          ← internal freshness stamp, skip
    1.220.90.178 # windscribe       ← IP + inline provider tag
The inline '# provider' tag is provenance annotation only — parse_raw strips
it at download time so the normalized entries file matches rebuild's own
comment-splitting (same normalization both lanes; rebuild tolerates either).
Same archetype as x4bnet_vpn (asset/proxy/is_vpn witness).
"""
from ._base import IpListSource


class Az0VpnIpSource(IpListSource):
    name = "az0_vpn_ip"
    category = "asset"
    url = "http://az0-vpnip-public.oooninja.com/ip.txt"
    filename = "az0_vpn_ip.txt"
    fields = ("is_vpn",)
    classification_type = "proxy"
    verdict = "suspicious"
    stale_days = 7                     # Actions auto-update, daily-or-better cadence
    reliability = 0.70                 # community curated, same tier as x4bnet_vpn
    authoritative_for = ()             # witness; is_vpn 展示层权威不在此

    def parse_raw(self, raw: bytes) -> list[str]:
        """Default IpListSource parse keeps inline '# provider' tags; strip
        them here (same '#'-split rebuild applies) so the entries file holds
        bare IPs and the header timestamp never reaches rebuild."""
        out = []
        for line in raw.decode(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "#" in line:
                line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
        return out

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_vpn=True,
            native_types={"is_vpn": "VPN"},
        ).to_dict()


# PEP 562 拼写家族别名(与主类同名的不列;不出现在 dir(),不双注册)
_IMPORT_ALIASES = {
    "AZ0VpnIpSource": "Az0VpnIpSource",    # 缩写全大写形(品牌段 AZ0)
    "Az0VpnIPSource": "Az0VpnIpSource",    # 品牌拆词形尾部 IP 大写变体
}


def __getattr__(name):
    if name in _IMPORT_ALIASES:
        return globals()[_IMPORT_ALIASES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
