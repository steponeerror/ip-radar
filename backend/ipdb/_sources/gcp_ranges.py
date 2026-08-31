"""Google public ranges — gstatic goog.json, the whole Google footprint.

Publisher-authoritative JSON (syncToken/creationTime/prefixes); covers
Google infra at large (cloud + services). service="cloud" with provider
on native_types, is_hosting=True. Dual-family: ipv6Prefix included.
Overlaps infra_services only on narrow curated IPs (8.8.8.8 etc.) with a
different claim (dns role vs cloud range) — statements coexist by design.
"""
import json

from .._evidence import Evidence
from .._source_base import Source


class GcpRangesSource(Source):
    name = "gcp_ranges"
    category = "asset"
    filename = "gcp_ranges.json"
    fields = ("service", "is_hosting")
    url = "https://www.gstatic.com/ipranges/goog.json"
    stale_days = 7
    reliability = 0.95
    authoritative_for = ()

    def harvest(self):
        if not self._path.exists():
            return
        d = json.loads(self._path.read_text())
        ev = Evidence(
            service="cloud",
            is_hosting=True,
            native_types={"service": "Google"},
            verdict="",                # asset-only; suppress "malicious" default
        )
        for p in d.get("prefixes", []):
            v4 = p.get("ipv4Prefix")
            v6 = p.get("ipv6Prefix")
            if v4:
                yield v4, ev
            if v6 and ":" in v6:
                yield v6, ev
