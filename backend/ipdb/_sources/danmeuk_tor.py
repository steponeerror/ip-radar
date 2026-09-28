"""dan.me.uk Tor node list — IpListSource.

Second independent witness for ``is_tor`` / classification ``tor``
(tor_exits = official check.torproject.org exit list, authoritative; this
list covers the full relay set — the /torlist/ URL ships ~10.7k rows
(observed 2026-09-28), an order of magnitude above the ~1.4k live exits,
i.e. all relay roles, not exits only). Publisher: dan.me.uk, community
standard since ~2009.

Plain IP-per-line, no timestamps, no comments beyond '#'. Free, no auth.
Rate-limited to one fetch per 30 minutes (hourly scheduler is well within);
list itself updates every 30 minutes per the publisher's rate-limit page.
"""
from ._base import IpListSource


class DanMeUkTorSource(IpListSource):
    name = "danmeuk_tor"
    category = "asset"
    url = "https://www.dan.me.uk/torlist/"
    filename = "danmeuk_tor.txt"
    fields = ("is_tor",)
    classification_type = "tor"
    verdict = "suspicious"
    stale_days = 1                       # publisher refreshes every 30 min
    reliability = 0.85                   # community standard, occasional multi-day lag
    authoritative_for = ()               # witness only; official tor_exits keeps the veto

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_tor=True,
            native_types={"is_tor": "RELAY"},   # any-role relay (vs official "TOR" exits)
        ).to_dict()
