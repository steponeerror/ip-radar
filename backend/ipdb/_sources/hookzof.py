"""hookzof socks5 proxy list — IpListSource subclass.

Live-checked SOCKS5 proxies (github.com/hookzof/socks5_list, updated several
times daily by its own checking network — not a proxyscrape mirror).
Format: ``ip:port`` per line; the port is structural and dropped at parse.
Classification ``proxy`` / ``suspicious`` + ``is_proxy`` asset statement
(proxyscrape precedent). is_proxy authority stays with ip2proxy.
"""
from ._base import IpListSource


class HookzofSource(IpListSource):
    name = "hookzof"
    category = "asset"
    url = "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"
    filename = "hookzof.txt"
    fields = ("is_proxy",)
    classification_type = "proxy"
    verdict = "suspicious"
    stale_days = 1
    reliability = 0.50
    authoritative_for = ()

    def parse_raw(self, raw: bytes) -> list[str]:
        """``ip:port`` → bare IPs (port is structural noise for lookups)."""
        return [
            line.split(":", 1)[0].strip()
            for line in raw.decode(errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_proxy=True,
            native_types={"is_proxy": "SOCKS5"},
        ).to_dict()
