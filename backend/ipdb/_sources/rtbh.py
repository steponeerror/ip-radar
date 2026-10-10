"""RTBH.com.tr national RTBH attacker list — IpListSource subclass.

Turkish RTBH project: 54 sensors in 50+ locations, algorithmic detection,
auto-blackholing DDoS-class malicious traffic sources via BGP
(list.rtbh.com.tr, updated intraday; methodology public). Publisher mission
is DDoS source isolation → dedicated ``ddos`` slot, this pool's first
dedicated ddos witness (tweetfeed tags were the only prior reach). No
explicit license on the feed endpoint — accepted for this self-hosted,
non-commercial OSS deployment by user ruling 2026-10-10 (discover FLAG
sign-off). Verified live 2026-10-10 (69.5k keys; Uniq 58.0%, N=300 vs pool;
not even in firehol's 342-feed catalog).
"""
from ._base import IpListSource


class RtbhSource(IpListSource):
    name = "rtbh"
    category = "threat"
    url = "https://list.rtbh.com.tr/output.txt"
    filename = "rtbh.txt"
    fields = ("is_malicious",)
    classification_type = "ddos"
    verdict = "malicious"
    stale_days = 3                       # intraday updates; 3d silence = feed dead
    reliability = 0.70                   # 54-sensor algorithmic detection, no per-entry attribution
    authoritative_for = ()               # corroboration only (SM-F1)
