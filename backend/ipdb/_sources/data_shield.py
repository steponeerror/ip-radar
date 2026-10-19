"""duggytuxy/Data-Shield_IPv4_Blocklist — IpListSource subclass.

Aggregated daily IPv4 blocklist (prod variant, ~90k bare IPs; 2026-10-19 fetch
= 90,692 lines, plain list with no header). Scanned 2026-10-18: exclusive rate
47.0% (141/300 vs pool, seed 20261018, control 20/20; dossier
docs/research/2026-10-18-blocklist-sweep.md). License: GPL-3.0 — signed off by
user ruling 2026-10-18. Aggregator with no per-row attribution → r=0.50 floor;
derived=True + provenance_tier="C" (聚合派生;LINEAGE_CLUSTERS 同步入簇)。
All rows are bare malicious-IP accusations → single ``blacklist``/
``malicious`` verdict (binarydefense twin; Convention 2: no force-fit — the
feed carries no per-row category to preserve).
"""
from ._base import IpListSource


class DataShieldSource(IpListSource):
    name = "data_shield"
    category = "threat"
    url = "https://raw.githubusercontent.com/duggytuxy/Data-Shield_IPv4_Blocklist/main/prod_data-shield_ipv4_blocklist.txt"
    filename = "data_shield.txt"
    fields = ("is_malicious",)          # decorative for typed sources; base uses classification_type
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 2                       # daily regen; 2d silence = feed dead
    reliability = 0.50                   # aggregator floor: no per-row attribution (brief 2026-10-19)
    derived = True                       # 聚合器:谱系去重用(registry derived-set,ipsum 同款)
    provenance_tier = "C"                # C=聚合派生(S21)
    authoritative_for = ()               # corroboration only (SM-F1)
