"""dan.me.uk Tor node list — IpListSource.

Second independent witness for ``is_tor`` / classification ``tor``
(tor_exits = official check.torproject.org exit list, authoritative; this
list covers the full relay set — the /torlist/ URL ships ~10.7k rows
(2026-08-23 archived capture, re-verified 2026-09-28), an order of
magnitude above the ~1.4k live exits, i.e. all relay roles, not exits
only). Publisher: dan.me.uk, community standard since ~2009.

Plain IP-per-line, no timestamps, no comments beyond '#'. Free, no auth.
Rate-limited to one fetch per 30 minutes (list updates on the same
cadence per the publisher's rate-limit page): the 12h auto-refresh
slot grid stays well clear, manual Update counts against the limit
too, and enforcement is observed to exceed the window (a burst
double-fetch earned a block outlasting it) — hence the download()
content guard below.
"""
import logging

from ._base import IpListSource

logger = logging.getLogger(__name__)


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
    authoritative_for = ()               # witness only; is_tor 展示层权威属 tor_exits(SM-F1:veto 机制不存在,措辞如实)

    def _validate_raw(self, raw: bytes) -> None:
        """Content guard (add-intel-source Phase 3 step 8): the publisher's
        rate-limit response is HTTP 200 with an HTML/text body, which the
        base's empty-body / zero-parsed-lines guards both let through.
        Require ≥1 line ipaddress accepts (same parser rebuild uses)."""
        import ipaddress as _ipa
        for line in self.parse_raw(raw):
            try:
                _ipa.ip_network(line, strict=False)
                return
            except ValueError:
                continue
        raise RuntimeError(
            f"{self.name}: no IP/CIDR lines in response — likely the "
            "30-minute rate-limit block page; existing data file kept")

    def download(self, token=None) -> None:
        """Fetch to scratch + validate BEFORE any write: a 200-OK garbage
        payload must never replace the data file (next rebuild would
        silently clear the source)."""
        from ._download import download_file, atomic_write_bytes
        self._data_dir.mkdir(parents=True, exist_ok=True)
        scratch = self._path.with_name(self._path.name + ".dl")
        try:
            download_file(self.url, scratch, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            raw = scratch.read_bytes()
            self._validate_raw(raw)
            entries = self.parse_raw(raw)
            atomic_write_bytes(
                self._path, ("\n".join(entries) + "\n").encode("utf-8"))
            logger.info(f"Downloaded {self.name} ({len(entries)} entries)")
        finally:
            scratch.unlink(missing_ok=True)

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_tor=True,
            native_types={"is_tor": "RELAY"},   # any-role relay (vs official "TOR" exits)
        ).to_dict()
