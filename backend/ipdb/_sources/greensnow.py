"""GreenSnow — IpListSource subclass.

greensnow.co publishes a blocklist of malicious IPs (compromised machines
observed attacking). Migrated to an independent subdomain after the legacy
``/list`` path 404'd; plain IP list, no auth, daily cadence.

  https://blocklist.greensnow.co/greensnow.txt
"""
from ._base import IpListSource


class GreensnowSource(IpListSource):
    name = "greensnow"
    category = "threat"
    url = "https://blocklist.greensnow.co/greensnow.txt"
    filename = "greensnow.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.60
    derived = True                        # 聚合器:谱系去重用(spec 2026-08-29 §3.3)
    authoritative_for = ()
