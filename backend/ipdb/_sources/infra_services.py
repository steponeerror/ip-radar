"""Curated well-known public infrastructure IPs — static Source subclass.

Stable, canonical IPs operated by well-known public services: DNS resolvers
— international providers plus Chinese public DNS (AliDNS/DNSPod/114DNS/
Baidu Public DNS) with IPv6 companions for the major resolvers — and public
NTP servers. The 13 DNS root servers moved out to the dedicated root_servers
fetched source (2026-10-10 batch) and are no longer curated here. Data is
hardcoded (no remote download); the service role rides the `service` asset
slot and the provider/identity rides `native_types`
(→ AssetStatement.native_type), so a lookup of e.g. 8.8.8.8 surfaces
`attributes["service"] = (dns, "Google Public DNS")` alongside the
existing is_proxy/is_hosting asset statements.

#188 升格(2026-10-24):除资产面外同 payload 还产 benign② 良性断言
(classification_type=服务角色, verdict="benign")——公共基础设施单址
的良性判定面输入;与指控同场 → verdict_conflict=True(真对立出海),
不自动压制指控(宁少算)。见 GLOSSARY「benign(两层,勿混)」②。

Why a source (not a lookup table): multiple infra sources emit `service`
(curated-static here; scanner_egress / cdn_edges feeds later) and the asset
channel auto-merges their statements into `attributes["service"]`. `download()`
is a local materialize (writes the embedded CSV) so the file-based lifecycle
(health mtime, load convert-trigger) works unchanged.
"""
import csv
import io
import logging

from ._download import atomic_write_bytes
from .._source_base import Source
from .._evidence import Evidence

logger = logging.getLogger(__name__)

# Columns: ip, service, provider
_DATA = """\
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


class InfraServicesSource(Source):
    name = "infra_services"
    category = "asset"
    filename = "infra_services.csv"
    fields = ("service",)
    authoritative_for = ("service",)
    stale_days = 36500            # curated static; never stale
    reliability = 0.95
    # no `url` — download() materializes the embedded CSV locally, not a fetch

    def download(self, token=None) -> None:
        """Materialize the embedded curated CSV (no remote fetch)."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self._path, _DATA.encode("utf-8"))

    def _sync_projection(self) -> None:
        """投影同步(grill Q6 裁决 2026-10-11):_DATA 是唯一真相源,data/
        下 csv 是物化投影——文件缺失或内容与 _DATA 不一致 → 重物化。修
        2026-10-10 生产挂账:旧码只在文件缺失时物化,代码改 _DATA 后卷上
        旧 csv mtime 不动 → needs_convert 恒 False → 旧纪元永不重建(生产
        曾靠 docker rm csv+restart 外科治愈)。风险锚点(评审 a–e):
        (a) load 写副作用:load() 会写盘,但仅内容不一致时一次;同内容零写
        (零变化契约),KB 级 _DATA 一次 read+memcmp 毫秒级。
        (b) pool 子进程并发写:批池 worker 的 load_db 可与本进程并发重物化;
        双方字节恒同,atomic_write_bytes 走 .tmp+os.replace 原子换入,读者
        永不见半写;极端时序下落后者的 .tmp 已被前者换走 → 其 load 报错,
        经 load_db OL-4 路径可见,下轮 load 收敛(幂等),不污染 epoch。
        (c) 覆写语义:手工改过的 data/ csv 会被覆写——特性,_DATA 是真相。
        (d) mtime 收敛:重物化 bump csv mtime → needs_convert True → 一次
        rebuild 后 ptr 更新即收敛;同内容不再写,无循环。epoch 损坏遇内容
        变更亦借此自愈(bump 直接入重建队列,不再 load_error 永久瘫痪)。
        (e) 零记录守卫交互:_DATA 若退化到零行,_lmdb 零记录守卫拒提交保旧
        epoch,needs_convert 维持 True 走退避重试——可见失败非静默。"""
        if not self._path.exists() or self._path.read_text() != _DATA:
            self.download()

    def load(self) -> int:
        # Self-heal: a cold start without a prior download still loads;
        # content drift re-materializes (projection semantics, see above).
        self._sync_projection()
        return super().load()

    def rebuild(self, progress=None) -> int:
        # Self-heal: same as load() — cold start without prior download;
        # 直入 rebuild(未经 load)也不采到旧 csv。
        self._sync_projection()
        return super().rebuild(progress=progress)

    def harvest(self):
        # 良性断言(benign②,#188,2026-10-24):公共基础设施单址产良性断言
        # ——同一 payload 双面:service 资产槽/native_types 照旧(资产面),
        # classification_type=服务角色(dns/ntp)+ verdict="benign" 进
        # 分类面。真对立(良性断言×指控同场=verdict_conflict)在
        # _registry.lookup 分组注入面接线;宁少算不变式(良性不投票/不
        # 压制指控)由 _merge._assess_classification 既有 _ACCUSING 池逻辑
        # 承担。占位期(verdict="" 弃权拼写)已随本升格作废。
        for row in csv.reader(io.StringIO(self._path.read_text())):
            if not row:
                continue
            ip, svc, provider = row
            yield ip, Evidence(
                service=svc,
                native_types={"service": provider},
                classification_type=svc,
                verdict="benign",
            )
