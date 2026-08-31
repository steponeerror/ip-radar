"""TheSpeedX HTTP proxy list — IpListSource subclass.

Live-checked HTTP proxies (github.com/TheSpeedX/PROXY-List http.txt, updated
daily by its own scraper network). Format: ``ip:port`` per line; port dropped
at parse (hookzof twin). Classification ``proxy`` / ``suspicious`` +
``is_proxy`` asset statement; authority stays with ip2proxy.
"""
from ._base import IpListSource


class TheSpeedXSource(IpListSource):
    name = "thespeedx"
    category = "asset"
    url = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
    filename = "thespeedx.txt"
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
            native_types={"is_proxy": "HTTP"},
        ).to_dict()
