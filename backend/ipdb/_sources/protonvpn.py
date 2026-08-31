"""ProtonVPN server list — IpListSource subclass.

Proton-published VPN server IPs (entry + exit columns), mirrored by
github.com/mthcht/awesome-lists (updated daily). parse_raw flattens the CSV
into a deduped bare-IP list at download time; server country columns are
left to the authoritative geo axis. ``is_vpn`` asset statement with
"ProtonVPN" native label (x4bnet_vpn precedent); is_vpn authority stays
with x4bnet. Second independent vpn witness → breaks the vpn corroboration
monopoly without touching the axis authority.
"""
from ._base import IpListSource


class ProtonVPNSource(IpListSource):
    name = "protonvpn"
    category = "asset"
    url = ("https://raw.githubusercontent.com/mthcht/awesome-lists/main/"
           "Lists/VPN/ProtonVPN/protonvpn_ip_list.csv")
    filename = "protonvpn.csv"
    fields = ("is_vpn",)
    classification_type = "proxy"        # no vpn vocab slot; x4bnet_vpn precedent
    verdict = "suspicious"
    stale_days = 7
    reliability = 0.75                   # provider-official data via daily mirror
    authoritative_for = ()

    def parse_raw(self, raw: bytes) -> list[str]:
        """CSV ``src_ip_entry,src_ip_exit,cc,cc`` → deduped bare IPs."""
        out: list[str] = []
        seen: set[str] = set()
        for line in raw.decode(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith(("src_ip", "#")):
                continue                 # header / comments
            cols = line.split(",")
            for col in cols[:2]:         # entry + exit IPs
                ip = col.strip()
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
            native_types={"is_vpn": "ProtonVPN"},
        ).to_dict()
