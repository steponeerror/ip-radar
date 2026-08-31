"""SiberKapan threat feed — IpListSource subclass.

Turkish honeypot network + FortiGate/nginx sensor blocklist (siberkapan.org,
official MISP default feed). Plain IPv4 list with '#' headers; regenerated
daily. Undifferentiated sensor abuse maps to the generic ``blacklist`` slot
(Convention 2: no force-fit). Turkish-infra focus biases the geo mix.
"""
from ._base import IpListSource


class SiberKapanSource(IpListSource):
    name = "siberkapan"
    category = "threat"
    url = "https://siberkapan.org/api/v1/list/txt"
    filename = "siberkapan.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.60                   # sensor-sourced: automated but evidence-based
    authoritative_for = ()
