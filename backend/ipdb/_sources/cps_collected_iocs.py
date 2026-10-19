"""CriticalPathSecurity/Public-Intelligence-Feeds cps-collected-iocs.txt — IpListSource subclass.

CPS(Critical Path Security,具名美国 TI 公司,GitHub 135★,repo 当日活
2026-10-19)自有 IOC 聚合:裸 IPv4 逐行,无表头无注释。2026-10-19 实抓
47,405 行,33% 重复 → 31,767 唯一,rebuild 按键天然去重(rebuild_lmdb
同键覆盖,DQ-2 键数语义)。自有聚合无逐条出处 → Q6b 聚合器声明面:
reliability 0.50 地板 + derived=True + provenance_tier=C(malicious_ip
r=0.50 判例复刻,2026-10-18)。排他率实测 70.3%(211/300,N=300 对池探针,
seed 20261018,对照 20/20;dossier docs/research/2026-10-19-tails-discover.md)。
License: MIT(随 CPS 镜像仓)。stale_days=7:feed 无内部时间戳,CPS bulk
commit 节奏不明,保守取 7d。观察项 = S2 型独有命中质量:排他段为单源
指控,月度 eval 盯,误报冒头 → 撤源单文件回滚。
逐裸 IP 单一指控 → blacklist/malicious(feed 无逐行类别,Convention 2
不强行归类;binarydefense/data_shield 双生)。
"""
from ._base import IpListSource


class CpsCollectedIocsSource(IpListSource):
    name = "cps_collected_iocs"
    category = "threat"
    url = "https://raw.githubusercontent.com/CriticalPathSecurity/Public-Intelligence-Feeds/master/cps-collected-iocs.txt"
    filename = "cps_collected_iocs.txt"
    fields = ("is_malicious",)          # decorative for typed sources; base uses classification_type
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 7                       # 无内部 ts;CPS bulk commit 节奏不明,保守 7d(brief 2026-10-19)
    reliability = 0.50                   # aggregator floor: no per-row attribution (Q6b;malicious_ip 判例)
    derived = True                       # 聚合器:谱系去重用(registry derived-set,data_shield 同款)
    provenance_tier = "C"                # C=聚合派生(S21)
    authoritative_for = ()               # corroboration only (SM-F1)
