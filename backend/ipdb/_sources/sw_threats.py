"""sw_threats (ShadowWhisperer/IPs · Lists/Threats.csv) — CsvSource subclass.

ShadowWhisperer 自采策展威胁 IP 清单,逐行 category/detail/note/tags/
first_seen/last_seen(daily,日期 YYYY-MM-DD)。Unlicense。实测 2026-10-18:
16,941 行;排他率 58.7%(N=300,seed 20261018,对照 20/20;dossier
docs/research/2026-10-18-blocklist-sweep.md,队列 #1 = 波 1 扩容首选;
活体新鲜度:样本含当日前后 first_seen)。

provenance_tier="A"(自有观测,非聚合 — dossier「一等证据形状」);
**非 derived**:LINEAGE_CLUSTERS 自身规则=「新增 derived 源须同步加簇」,
非 derived 不入簇(orchestrator 裁决 2026-10-18,任务3)。r=0.55(brief;
自采方法学未公开,取聚合源同档保守值,dossier 区间 0.55-0.60 下沿)。

分类三向(convention 2,勿强拟合):SW_THREATS_MAP 覆盖全部六个实测
category——四值映射净词表槽(botnet node→infected-system[词表已无方言
botnet,P1 2026-09-05]/recon→scanner/exploit→exploit/dropper host→
malware-distribution),abuse/intrusion 显式 other。native_categories=
[category, detail] 原值并列(detail 如 mirai/rce 是证据细节,不冒充
malware_name 槽);tags 剥 [] 后按 | 拆进 tags 槽;note→extra 乘客;
first_seen/last_seen 直传(fromisoformat 兼容 YYYY-MM-DD,喂时间衰减);
坏日期行弃——逐行时间戳是本源证据形状的一部分,残缺即脏行。
"""
from datetime import datetime as _dt

from .._classification import normalize, SW_THREATS_MAP
from ._base import CsvSource


class SWThreatsSource(CsvSource):
    name = "sw_threats"
    category = "threat"
    url = ("https://raw.githubusercontent.com/ShadowWhisperer/IPs/"
           "master/Lists/Threats.csv")
    filename = "sw_threats.csv"
    fields = ("is_malicious",)
    classification_type = "blacklist"    # 默认;parse_row 逐行 normalize 覆盖
    verdict = "malicious"
    stale_days = 2                       # daily regen;2d silence = feed dead
    reliability = 0.55                   # brief 2026-10-18(dossier 区间下沿)
    provenance_tier = "A"                # A=官方/自采(S21;dossier:自有观测)
    authoritative_for = ()               # corroboration only (SM-F1)
    skip_lines = 1   # header: ip,category,detail,note,tags,first_seen,last_seen

    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 7:
            return None
        ip, cat, detail, note, tags_raw, first_seen, last_seen = (
            c.strip() for c in row[:7])
        try:
            _dt.strptime(first_seen, "%Y-%m-%d")
            _dt.strptime(last_seen, "%Y-%m-%d")
        except ValueError:
            return None     # 坏日期=脏行(时间戳是本源证据形状的一部分)
        rec: dict = {
            "_ip": ip,
            "classification_type": normalize(cat, SW_THREATS_MAP),
            "verdict": self.verdict,
            "reliability": self.reliability,   # CsvSource 存 parse_row dict 原样,须自带(ziyadnz 同款)
            "first_seen": first_seen,
            "last_seen": last_seen,
        }
        natives = [c for c in (cat, detail) if c]
        if natives:
            rec["native_categories"] = natives   # [category, detail] 原值并列(three-way rule)
        tags = [t.strip() for t in tags_raw.strip("[]").split("|") if t.strip()]
        if tags:
            rec["tags"] = tags
        if note:
            rec["extra"] = {"note": note}
        return rec
