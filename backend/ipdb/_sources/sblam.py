"""Sblam! (sblam.com) form-spam blacklist — IpListSource subclass.

Polish Sblam! 自有表单垃圾传感器网络(部署于订阅网站的 HTML form 陷阱)。
裸 IPv4 列表 + '#' 头注释(IpListSource 原生跳过,零 parse 钩子)。许可 =
licencja.html 明文:「Korzystanie z usługi jest darmowe, również dla stron
komercyjnych」(免费含商用)+「Częściowe, zagregowane dane z postów (np.
najpopularniejsze linki, czarna lista IP) mogą być publikowane」(黑 IP 列表
可发布);2026-10-19 实抓核对。实测 2026-10-19:1,136 键 / 排他率 26.7%
(80/300,N=300 对池探针,seed 20261018,对照 20/20)。定位 = spam 轴
第二证人(stopforumspam 先例);逐裸 IP 单一指控 → spam/malicious
(feed 无逐行类别,Convention 2 不强行归类)。
"""
from ._base import IpListSource


class SblamSource(IpListSource):
    name = "sblam"
    category = "threat"
    url = "https://sblam.com/blacklist.txt"
    filename = "sblam"
    fields = ("is_malicious",)          # decorative for typed sources; base uses classification_type
    classification_type = "spam"        # stopforumspam 先例(同轴第二证人)
    verdict = "malicious"
    stale_days = 3                      # daily regen (Generated 时间戳逐日刷新);3d silence = feed dead
    reliability = 0.55                  # brief 2026-10-19
    provenance_tier = "B"               # B=社区(S21;第三方自有传感器非自采)
    authoritative_for = ()               # corroboration only (SM-F1)
    honeypot_methodology = True         # 表单陷阱网络=蜜罐法采集(binarydefense/knock_knock 同族;orchestrator 裁决 2026-10-19,k_nonhoneypot 剔除依据)
