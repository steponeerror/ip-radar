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
    provenance_tier = "A"                 # A=官方一手(S21):Proofpoint ET 规则发布
    # 转载声明(卡2上半,#464;实测 2026-11-26 生产镜像全库扫描,归档
    # docs/reports/2026-11-26-arch-r4-landing/#451-卡2-转载关系/verify/scan_step3.json(A5:曾为 untracked 本地件
    # dev/arch-r4-scan/,已归档文档仓)):⊇ spamhaus 106,275/106,278
    # (100.0%)。口径:镜像内 IPv4 单地址单元——分母 = 被 spamhaus
    # 覆盖且作 IPv4 单地址单元出现的地址,非 spamhaus 全表(扫描只数 v4 单地址 5,341,414 个;v4 网段 177,090 与 v6 不计)。
    # 「同场共现」非逐字照搬之证(评审 B3:共现亦可能同上游/各自独立
    # 封同一批地址;判式只在同场地址起作用,方向不受影响)。/12 巨块
    # 回声审计实证(DQ-1,2026-10-06):在场且系数不低即剔,宁少算。
    republishes = ("spamhaus",)
    infra_noise_filter = False         # 显式关:存量源行为不变(#531;基类默认已翻 True)
