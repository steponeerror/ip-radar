"""Alibaba Cloud public ranges — cloud-ip-ranges.com aggregator.

Fifth member of the cloud family (aws/gcp/azure/oracle + this): the
China-cloud footprint as asset evidence — service="cloud" with the
provider identity on native_types, is_hosting=True, asset-only verdict.

Publisher = cloud-ip-ranges.com, a third-party aggregator of the
officially published Alibaba ranges (NOT publisher-self: reliability
0.75 vs the 0.95 official houses). License unstated on the site —
user-approved for this non-commercial tool on 2026-09-28.

Observed 2026-09-28: 2,394 CIDRs (v4 2,148 / v6 246), zero exact
dupes, some parent/child nesting (kept as-is — longest-prefix lookup
resolves; identical evidence either way). No in-file timestamps:
freshness = Last-Modified header liveness, observed advancing daily
04:00 UTC. Plain CIDR-per-line, free, no auth, no known rate limit.

Download content guard: the site is a Rails app; a 200-HTML error/
maintenance page would pass the base empty-body / zero-parsed-lines
guards (non-empty, non-blank lines) and silently clear the source on
rebuild — same P1 class as danmeuk's rate-limit page, same scratch +
validate-before-write fix (Phase 3 step 8).
"""
import logging

from ._base import IpListSource

logger = logging.getLogger(__name__)


class AlibabaRangesSource(IpListSource):
    name = "alibaba_ranges"
    category = "asset"
    url = "https://cloud-ip-ranges.com/download/alibaba.txt"
    filename = "alibaba_ranges.txt"
    fields = ("service", "is_hosting")
    stale_days = 7                       # cloud footprint is slow-moving (cf. aws/gcp)
    reliability = 0.75                   # third-party aggregator of official ranges
    authoritative_for = ()               # aggregator — no veto on any field

    def _validate_raw(self, raw: bytes) -> None:
        """Content guard: require ≥1 line ipaddress accepts (same parser
        rebuild uses); otherwise keep the existing data file untouched."""
        import ipaddress as _ipa
        for line in self.parse_raw(raw):
            try:
                _ipa.ip_network(line, strict=False)
                return
            except ValueError:
                continue
        raise RuntimeError(
            f"{self.name}: no IP/CIDR lines in response — likely an HTML "
            "error/maintenance page; existing data file kept")

    def download(self, token=None) -> None:
        """Fetch to scratch + validate BEFORE any write: a 200-OK garbage
        payload must never replace the data file (next rebuild would
        silently clear the source)."""
        from ._download import download_file
        self._data_dir.mkdir(parents=True, exist_ok=True)
        scratch = self._path.with_name(self._path.name + ".dl")
        try:
            download_file(self.url, scratch, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            raw = scratch.read_bytes()
            self._validate_raw(raw)
            entries = self.parse_raw(raw)
            with open(self._path, "w", encoding="utf-8") as f:
                f.write("\n".join(entries) + "\n")
            logger.info(f"Downloaded {self.name} ({len(entries)} entries)")
        finally:
            scratch.unlink(missing_ok=True)

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            service="cloud",
            is_hosting=True,
            native_types={"service": "Alibaba"},
            verdict="",                # asset-only; suppress "malicious" default
        ).to_dict()
