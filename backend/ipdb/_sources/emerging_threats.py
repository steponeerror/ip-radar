"""Emerging Threats firewall block-list — malicious IP/CIDR source.

Replaces the dead shadowserver URL (404). Provenance-curated block list,
no API key required.

  https://rules.emergingthreats.net/fwrules/emerging-Block-IPs.txt
"""
from ._base import IpListSource


class EmergingThreatsSource(IpListSource):
    name = "emerging_threats"
    category = "threat"
    url = ("https://rules.emergingthreats.net/"
           "fwrules/emerging-Block-IPs.txt")
    filename = "emerging-block-ips.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.85
    authoritative_for = ()               # SM-F1:is_malicious 无证据键生产者(幻影轴),不声明
