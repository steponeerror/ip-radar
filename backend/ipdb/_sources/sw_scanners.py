"""sw_scanners (ShadowWhisperer/IPs · Lists/Scanners.csv) — CsvSource subclass.

ShadowWhisperer 自采策展 scanner IP 清单(与 sw_threats 同出版社同仓库,
Lists/ 目录姊妹篇)。两列 ip,company,日更,Unlicense。实测 2026-10-19:
62,711 行;排他率 73.0%(N=300,seed 20261018,对照 20/20;dossier
docs/research/2026-10-18-blocklist-sweep.md,scanner 槽波 2 首选;
活体新鲜度:当日实抓存活)。

provenance_tier="A"(自采策展,非聚合——sw_threats 同款;**非 derived**,
不入 LINEAGE_CLUSTERS)。r=0.55(brief 2026-10-19;自采方法学未公开,
取聚合源同档保守值)。

全部行=scanner 指控→scanner/malicious(turris_greylist 同款单类;池内
scanner 槽 4 源 dshield/f3csystems/otx/turris_greylist 均 verdict=malicious);
无逐行类别列,无需 normalize 映射。company 是证据细节乘客→extra["company"]
(urlhaus reporter 先例),空 company 不发 extra(to_dict 丢空契约);
坏 IP/短行弃(rebuild 解析期逐行闸)。
"""
from ._base import CsvSource


class SWScannersSource(CsvSource):
    name = "sw_scanners"
    category = "threat"
    url = ("https://raw.githubusercontent.com/ShadowWhisperer/IPs/"
           "master/Lists/Scanners.csv")
    filename = "sw_scanners.csv"
    fields = ("is_malicious",)
    classification_type = "scanner"
    verdict = "malicious"
    stale_days = 2                       # daily regen;2d silence = feed dead
    reliability = 0.55                   # brief 2026-10-19
    provenance_tier = "A"                # A=官方/自采(S21;自采策展非聚合)
    authoritative_for = ()               # corroboration only (SM-F1)
    skip_lines = 1   # header: ip,company

    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 2:
            return None
        company = row[1].strip()
        rec: dict = {
            "_ip": row[0].strip(),
            "classification_type": self.classification_type,
            "verdict": self.verdict,
            "reliability": self.reliability,   # CsvSource 存 parse_row dict 原样,须自带(ziyadnz/sw_threats 同款)
        }
        if company:
            rec["extra"] = {"company": company}   # 证据细节乘客(urlhaus reporter 先例)
        return rec
