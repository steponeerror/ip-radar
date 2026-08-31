"""NordVPN server list — IpListSource subclass.

NordVPN server IPs mirrored by github.com/mthcht/awesome-lists (daily).
parse_raw flattens to bare IPs at download time; server names are
operational metadata, dropped. ``is_vpn`` asset statement with "NordVPN"
native label; is_vpn authority stays with x4bnet. Independent vpn witness
(distinct upstream from protonvpn — different provider, same curator).
"""
from ._base import IpListSource


class NordVPNSource(IpListSource):
    name = "nordvpn"
    category = "asset"
    url = ("https://raw.githubusercontent.com/mthcht/awesome-lists/main/"
           "Lists/VPN/NordVPN/nordvpn_ip_list.csv")
    filename = "nordvpn.csv"
    fields = ("is_vpn",)
    classification_type = "proxy"        # no vpn vocab slot; x4bnet_vpn precedent
    verdict = "suspicious"
    stale_days = 7
    reliability = 0.75                   # provider-official data via daily mirror
    authoritative_for = ()

    def parse_raw(self, raw: bytes) -> list[str]:
        """CSV ``src_ip,servername,comment`` → deduped bare IPs."""
        out: list[str] = []
        seen: set[str] = set()
        for line in raw.decode(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith(("src_ip", "#")):
                continue                 # header / comments
            ip = line.split(",", 1)[0].strip()
            if ip and ip not in seen:
                seen.add(ip)
                out.append(ip)
        return out

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_vpn=True,
            native_types={"is_vpn": "NordVPN"},
        ).to_dict()
