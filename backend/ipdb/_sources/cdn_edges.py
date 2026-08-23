"""Live CDN edge ranges from the three publishers that emit clean public feeds.

AWS CloudFront (ip-ranges.json, filter service=CLOUDFRONT), Cloudflare (ips-v4),
and Fastly (public-ip-list) each publish their own edge ranges — publisher-
authoritative, so reliability is high. All three are fetched each refresh and
collapsed into one `service="cdn"` asset stream; the provider identity rides
`native_types` (-> AssetStatement.native_type), so a lookup of an edge IP
surfaces `attributes["service"] = (cdn, "CloudFront")`.

The tool is dual-family (spec 2026-08-23): AWS `ipv6_prefixes` and Fastly's
mixed-family `addresses` are harvested; the Cloudflare v6 sibling feed
(`ips-v6`) lands in PR2. download() fetches the feeds and writes a combined
`cdn_edges.csv` (cidr,provider) intermediate; harvest() maps it to Evidence.
"""
import json
import re

from .._source_base import Source
from .._evidence import Evidence

_V4_CIDR_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$")

# (provider, url, format) — provider rides native_types.service.
_FEEDS = (
    ("CloudFront", "https://ip-ranges.amazonaws.com/ip-ranges.json", "aws"),
    ("Cloudflare", "https://www.cloudflare.com/ips-v4", "cloudflare"),
    ("Fastly", "https://api.fastly.com/public-ip-list", "fastly"),
)


class CdnEdgesSource(Source):
    name = "cdn_edges"
    filename = "cdn_edges.csv"          # combined intermediate written by download()
    fields = ("service",)
    authoritative_for = ["service"]
    stale_days = 7                      # bulky, slow-changing range lists (cf. ip2proxy/iptoasn)
    reliability = 0.95                  # publisher-self-published edge ranges (cf. tor_exits)

    def download(self, token=None) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for provider, url, fmt in _FEEDS:
            data = self._http_get(url)
            rows.extend((cidr, provider) for cidr in _parse(data, fmt))
        self._path.write_text("".join(f"{c},{p}\n" for c, p in rows))

    def harvest(self):
        for line in self._path.read_text().splitlines():
            if not line.strip():
                continue
            cidr, provider = line.split(",", 1)
            yield cidr, Evidence(
                service="cdn",
                native_types={"service": provider},
                verdict="",  # asset-only source; suppress the "malicious" default
            )


def _parse(data: bytes, fmt: str):
    """Yield CIDR strings from one provider's raw bytes (both families).

    v4 走 _V4_CIDR_RE 正则(形态护栏),v6 以 ':' 判定并按 provider 各自的
    v6 键(ipv6_prefixes / addresses 混排)读取;Cloudflare v4-only 是 PR2。
    """
    if fmt == "aws":
        d = json.loads(data)
        for p in d.get("prefixes", []):           # v4 list
            prefix = p.get("ip_prefix")
            if p.get("service") == "CLOUDFRONT" and _V4_CIDR_RE.match(prefix or ""):
                yield prefix
        for p in d.get("ipv6_prefixes", []):       # v6 sibling list
            prefix = p.get("ipv6_prefix")
            if p.get("service") == "CLOUDFRONT" and prefix and ":" in prefix:
                yield prefix
    elif fmt == "cloudflare":
        for line in data.decode("ascii", errors="ignore").splitlines():
            line = line.strip()
            if line and _V4_CIDR_RE.match(line):
                yield line
    elif fmt == "fastly":
        d = json.loads(data)
        for a in d.get("addresses", []):          # single list, mixed families
            if a and (":" in a or _V4_CIDR_RE.match(a)):
                yield a
