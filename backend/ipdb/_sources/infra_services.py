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

    def load(self) -> int:
        # Self-heal: a cold start without a prior download still loads.
        if not self._path.exists():
            self.download()
        return super().load()

    def rebuild(self, progress=None) -> int:
        # Self-heal: same as load() — cold start without prior download.
        if not self._path.exists():
            self.download()
        return super().rebuild(progress=progress)

    def harvest(self):
        for row in csv.reader(io.StringIO(self._path.read_text())):
            if not row:
                continue
            ip, svc, provider = row
            yield ip, Evidence(
                service=svc,
                native_types={"service": provider},
                verdict="",  # 弃权拼写:由 to_dict 特判保留,读回按 "" 处理不兑底(R17A-1)
            )
