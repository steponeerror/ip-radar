"""Knock-Knock honeypot attacker blocklist — IpListSource subclass.

First-party multi-protocol honeypot fleet (knock-knock.net; SSH/Telnet/FTP/RDP/
SMB/SIP/HTTP/SMTP, methodology + detection code public in repo = auditable
derivation). Month-window attacker IPs, regenerated hourly. Flat list carries
no per-protocol signal → undifferentiated honeypot attackers map to
``blacklist`` (binarydefense twin precedent; Convention 2: no force-fit).
Repo MIT, feed free, no auth. Verified live 2026-10-10 (37.7k month / 194k
year keys; Uniq 54.7%, N=300 vs pool).
"""
from ._base import IpListSource


class KnockKnockSource(IpListSource):
    name = "knock_knock"
    category = "threat"
    url = "https://knock-knock.net/static/ip-blocklist-month.txt"
    filename = "knock_knock.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 3                       # hourly regen; 3d silence = feed dead
    reliability = 0.70                   # measured attacks, single-network geo bias
    authoritative_for = ()               # corroboration only (SM-F1)
