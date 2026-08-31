"""Oracle Cloud (OCI) public ranges — official regions/cidrs JSON.

Publisher-authoritative (last_updated_timestamp maintained; observed
2026-08-25). All regions' cidrs harvested: service="cloud", provider on
native_types, is_hosting=True. Dual-family via the cidr strings
themselves (v6 rides the v6 sidecar).
"""
import json

from .._evidence import Evidence
from .._source_base import Source


class OracleRangesSource(Source):
    name = "oracle_ranges"
    category = "asset"
    filename = "oracle_ranges.json"
    fields = ("service", "is_hosting")
    url = "https://docs.oracle.com/iaas/tools/public_ip_ranges.json"
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
            native_types={"service": "Oracle Cloud"},
            verdict="",                # asset-only; suppress "malicious" default
        )
        for region in d.get("regions", []):
            for c in region.get("cidrs", []):
                cidr = c.get("cidr") if isinstance(c, dict) else c
                if cidr:
                    yield cidr, ev
