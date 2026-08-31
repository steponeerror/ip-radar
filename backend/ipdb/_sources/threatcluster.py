"""ThreatCluster public IOC feed — IpListSource subclass.

Curated high-confidence malicious IPs (last 30 days) from threatcluster.io.
Plain IP list with '#' headers, regenerated daily. Volume is honestly tiny
(~40 IPs) but curated — kept as a c2/mal corroboration witness, not a
coverage source.
"""
from ._base import IpListSource


class ThreatClusterSource(IpListSource):
    name = "threatcluster"
    category = "threat"
    url = "https://threatcluster.io/api/iocs/public/ips.txt"
    filename = "threatcluster.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 3
    reliability = 0.70                   # human-curated, high-confidence
    authoritative_for = ()
