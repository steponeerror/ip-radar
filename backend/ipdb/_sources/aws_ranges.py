"""AWS public ranges — ip-ranges.json, the full cloud footprint.

Publisher-authoritative (same feed cdn_edges filters CLOUDFRONT from);
here ALL AWS prefixes are harvested as asset evidence: service="cloud"
with the provider identity on native_types (→ AssetStatement.native_type),
plus is_hosting=True — the cloud footprint is a hosting witness by
definition. Dual-family: ipv6_prefixes ride the v6 sidecar.
"""
import json

from .._evidence import Evidence
from .._source_base import Source


class AwsRangesSource(Source):
    name = "aws_ranges"
    category = "asset"
    filename = "aws_ranges.json"
    fields = ("service", "is_hosting")
    url = "https://ip-ranges.amazonaws.com/ip-ranges.json"
    stale_days = 7                    # publisher refresh cadence (cf. cdn_edges)
    reliability = 0.95                # publisher-self-published ranges
    authoritative_for = ()

    def harvest(self):
        if not self._path.exists():
            return
        d = json.loads(self._path.read_text())
        ev = Evidence(
            service="cloud",
            is_hosting=True,
            native_types={"service": "AWS"},
            verdict="",                # asset-only; suppress "malicious" default
        )
        for p in d.get("prefixes", []):
            prefix = p.get("ip_prefix")
            if prefix:
                yield prefix, ev
        for p in d.get("ipv6_prefixes", []):
            prefix = p.get("ipv6_prefix")
            if prefix and ":" in prefix:
                yield prefix, ev
