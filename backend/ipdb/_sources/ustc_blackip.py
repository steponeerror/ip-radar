"""USTC blackip (blackip.ustc.edu.cn) 校园自保黑名单 — IpListSource。

中国科学技术大学网络信息中心发布的校园边界自保黑名单,持续运行约 15 年;
解封需发信 james@ustc.edu.cn 人工复议——人工复议流程即策展性来源(非机械
聚合)。文件为混合清单:2026-10-19 实抓 14,168 行 = v4 单 IP 9,325 +
v4 CIDR 4,658 + v6 185(IpListSource rebuild 原生 ip_network 双族解析,
零 parse 钩子);文件无内部时间戳,活性证据 = 落地页实时统计今日新增/
失效数千条滚动(freshness gate 走 publisher-liveness 通道)。排他率
47.0%(141/300,N=300 对池探针,seed 20261018,对照 20/20)按**去 CIDR
纯单 IP 口径**测得——混合口径探针 31.3% 属 CIDR 稀释放大失真,判例:
CIDR 混合源探针一律先 de-CIDR(dossier docs/research/2026-10-19-tails-
discover.md §4.5)。CN 网段浓度高(独家样本 171.222.185.8/183.93.45.242
等)= 池内 CN 威胁视角补强。无逐行 reason/类别 → 整体单一指控
blacklist/malicious(Convention 2 不强行归类)。许可:站点无声明,按用户
裁决 2026-10-19「有增量价值的都入队」签核收录(rtbh 判例同款)。
honeypot_methodology=False:生产网边界防御观测(真实封禁/复议管线),
非诱饵部署。
"""
from ._base import IpListSource


class UstcBlackipSource(IpListSource):
    name = "ustc_blackip"
    category = "threat"
    url = "https://blackip.ustc.edu.cn/list.php?txt"
    filename = "ustc_blackip"
    fields = ("is_malicious",)          # decorative for typed sources; base uses classification_type
    classification_type = "blacklist"   # brief 2026-10-19 wave-4 T1
    verdict = "malicious"
    stale_days = 3                      # 落地页逐日滚动更新;3d silence = feed dead
    reliability = 0.55                  # brief 2026-10-19
    provenance_tier = "B"               # B=社区(高校第一方自保,非自家采集;sblam 同档)
    authoritative_for = ()               # corroboration only (SM-F1)
    honeypot_methodology = False        # 生产网边界观测非诱饵(docstring 详证)
