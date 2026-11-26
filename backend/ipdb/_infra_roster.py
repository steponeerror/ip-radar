"""Curated public-infrastructure roster — the single home of the text.

卡 15(#466,架构评审第四轮;伞票 #451):名单原文此前住在
`_sources/infra_services.py` 的 `_DATA`,载入期噪声过滤
(`_sources/_infra_filter.py`)要经函数体内的延迟 import 反向从一个源
模块取名单——延迟 import 是为躲 infra_services → _source_base(_source_base.py:27)
→ _rebuild_tail → _infra_filter 的循环引用。文本现搬到此模块:_sources
包外,与 `_paths.py`、`_classification.py` 等跨源共用小模块同层;源模块
与过滤层同读这一份对象(不是第二份)。评审记录:文档仓
`reviews/2026-11-25-architecture-review-round4.md` 第 15 张卡。

内容契约:ROSTER_CSV 是搬前原文逐字节原样(cmp 验收,落地时对 master
_DATA 比对);data/ 下 csv 与 LMDB 都是它的投影(grill Q6 裁决
2026-10-11)。名单内容缺口是 #439 的票,不归本模块。
"""
import csv
import io
import ipaddress

# Columns: ip, service, provider
ROSTER_CSV = """\
8.8.8.8,dns,Google Public DNS
8.8.4.4,dns,Google Public DNS
1.1.1.1,dns,Cloudflare DNS
1.0.0.1,dns,Cloudflare DNS
9.9.9.9,dns,Quad9
149.112.112.112,dns,Quad9
208.67.222.222,dns,Cisco OpenDNS
208.67.220.220,dns,Cisco OpenDNS
94.140.14.14,dns,AdGuard DNS
94.140.15.15,dns,AdGuard DNS
76.76.2.22,dns,ControlD
76.76.10.11,dns,ControlD
223.5.5.5,dns,AliDNS
223.6.6.6,dns,AliDNS
2400:3200::1,dns,AliDNS
2400:3200:baba::1,dns,AliDNS
119.29.29.29,dns,DNSPod Public DNS
119.28.28.28,dns,DNSPod Public DNS
114.114.114.114,dns,114DNS
114.114.115.115,dns,114DNS
180.76.76.76,dns,Baidu Public DNS
77.88.8.8,dns,Yandex DNS
77.88.8.1,dns,Yandex DNS
2001:4860:4860::8888,dns,Google Public DNS
2001:4860:4860::8844,dns,Google Public DNS
2606:4700:4700::1111,dns,Cloudflare DNS
2606:4700:4700::1001,dns,Cloudflare DNS
2620:fe::fe,dns,Quad9
2620:fe::9,dns,Quad9
2620:119::c,dns,Cisco OpenDNS
2620:119:35::35,dns,Cisco OpenDNS
2a10:50c0::ad1:ff,dns,AdGuard DNS
2a10:50c0::ad2:ff,dns,AdGuard DNS
198.41.0.4,dns,a root server
170.247.170.2,dns,b root server
192.33.4.12,dns,c root server
199.7.91.13,dns,d root server
192.203.230.10,dns,e root server
192.5.5.241,dns,f root server
192.112.36.4,dns,g root server
198.97.190.53,dns,h root server
192.36.148.17,dns,i root server
192.58.128.30,dns,j root server
193.0.14.129,dns,k root server
199.7.83.42,dns,l root server
202.12.27.33,dns,m root server
216.239.35.0,ntp,Google NTP
216.239.35.4,ntp,Google NTP
216.239.35.8,ntp,Google NTP
216.239.35.12,ntp,Google NTP
162.159.200.1,ntp,Cloudflare NTP
162.159.200.123,ntp,Cloudflare NTP
132.163.96.2,ntp,NIST NTP
132.163.97.1,ntp,NIST NTP
128.138.140.44,ntp,NIST NTP
129.6.15.28,ntp,NIST NTP
"""


def rows() -> list[tuple[str, str, str]]:
    """名单逐行三元组 (ip, service, provider),空行跳过。

    词法与物化 csv 的回读同一套(csv.reader):「ROSTER_CSV → data/
    csv → harvest 回读」往返逐项一致(#466)。"""
    out = []
    for row in csv.reader(io.StringIO(ROSTER_CSV)):
        if not row:
            continue
        ip, svc, provider = row
        out.append((ip, svc, provider))
    return out


def addresses() -> frozenset:
    """curated 单址网络集(解析循环原样搬自 curated_infra_addresses,
    #466 卡 15:逐项与搬前相同)。不在此缓存——缓存是过滤层消费方的
    关注点,lru_cache 留在 _infra_filter.curated_infra_addresses(身份
    与 monkeypatch 面不变)。"""
    out = set()
    for row in ROSTER_CSV.strip().splitlines():
        ip = row.split(",", 1)[0].strip()
        if ip:
            out.add(ipaddress.ip_network(ip, strict=False))
    return frozenset(out)
