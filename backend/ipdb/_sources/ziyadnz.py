"""ziyadnz threat-intel-ip-feeds — CsvSource subclass (aggregated threat feed).

ziyadnz/threat-intel-ip-feeds (GitHub) aggregates ~10 public sources (RTBH
Turkiye / Spamhaus DROP / AbuseIPDB / Stamparm IPsum / CINS Army / SGB …)
into a daily per-IP CSV that keeps per-row lineage: pipe-joined ``sources``,
a ``source_count``, the feed's 0-100 ``confidence``, a raw ``category``, and
first/last-seen (regenerated daily — all rows share the publish instant;
stored verbatim as-is, first_seen feeds decay, semantics recorded not judged).

Measured 2026-10-18 (eval probe, seed 20261018): 120,510 keys, exclusive rate
44.7% (134/300 vs pool, control 20/20) — above the 25% gate; dossier
docs/research/2026-10-18-blocklist-sweep.md. GPL-3.0 feed, owner sign-off on
file (dossier row: 已签核).

All rows are aggregated malicious-IP accusations → a single ``blacklist``
classification (ipsum/knock_knock twin precedent; Convention 2: no force-fit —
raw categories survive verbatim in ``native_categories``).
"""
from ._base import CsvSource


class ZiyadnzSource(CsvSource):
    name = "ziyadnz"
    category = "threat"
    url = ("https://raw.githubusercontent.com/ziyadnz/threat-intel-ip-feeds/"
           "master/output/blacklist.csv")
    filename = "ziyadnz.csv"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 2                       # daily regen; 2d silence = feed dead
    reliability = 0.55                   # aggregated multi-party accusations (brief 2026-10-18)
    derived = True                       # 聚合器:谱系去重用(registry derived-set,ipsum 同款)
    provenance_tier = "C"                # C=聚合派生(S21)
    authoritative_for = ()               # corroboration only (SM-F1)
    skip_lines = 1   # header: ip,type,is_cidr,sources,source_count,category,confidence,first_seen,last_seen

    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 9:
            return None
        # type 门:ipv6 行越族即弃(brief 2026-10-18:type!=ipv4 行跳);
        # is_cidr 列不读——ip 列的 CIDR 形由 rebuild 的 ip_network 解析定夺,
        # 解析失败即脏行丢弃,无需双重校验。
        if row[1].strip() != "ipv4":
            return None
        extra: dict = {}
        sources = [s.strip() for s in row[3].split("|") if s.strip()]
        if sources:
            extra["sources"] = sources   # 谱系声明:per-row upstream lineage
        try:
            extra["source_count"] = int(row[4])
        except ValueError:
            pass
        try:
            # grill Q3 2026-10-18:feed 自家 0-100 分 ≠ Evidence.confidence
            # 语义槽,走 extra 乘客不进融合数学。
            extra["confidence"] = int(row[6])
        except ValueError:
            pass
        return {
            "_ip": row[0].strip(),
            "classification_type": self.classification_type,
            "verdict": self.verdict,
            "reliability": self.reliability,   # CsvSource 存 parse_row dict 原样,须自带(bruteforce 同款)
            "first_seen": row[7].strip(),
            "last_seen": row[8].strip(),
            "native_categories": [row[5].strip()],   # category 原值(three-way rule)
            "extra": extra,
        }
