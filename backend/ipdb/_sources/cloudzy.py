"""Cloudzy VPS address ranges — CPS-mirror feed, asset axis (wave 3 T2).

Cloudzy(伊朗系 VPS 商)的地址段标签,信息位不指控:此 IP 属 Cloudzy 托管
空间 = is_hosting=True 资产陈述。Feed = CriticalPathSecurity/
Public-Intelligence-Feeds 的 cloudzy.txt(裸 IPv4 逐行,无注释无表头,尾行
无换行;2026-10-19 实测 3,578 键全唯一);CPS 镜像仓 MIT 许可,publisher
非 Cloudzy 官方 → provenance_tier=B(第三方镜像)。上游维护活跃(触及本
文件的最近 commit 2026-10-18)。段级静态源:排他率 98.0%(294/300,seed
20261018,对照 20/20)属真空白——键是 IP 段不随时间换手,非上游造假信号,
故 stale_days=30 宽窗口足矣。

Phase-1 槽位决策(2026-10-19,依 add-intel-source skill 流程):**选项 A
is_hosting 票**,非选项 B service=(hosting, Cloudzy)。依据:
- 不发明新词表值(九条纪律):is_hosting 是既有 ASSET_SLOTS 布尔槽
  (ip2proxy DCH / cloud_ranges 在产,语义=「托管/机房空间」正覆盖 VPS
  段);"Cloudzy" 走 native_types 自由格式 native label(nordvpn "NordVPN"/
  infra_services "Google Public DNS" 同款)。选项 B 的 service="hosting"
  会在既有 service 角色值域(dns/ntp/cdn/cloud/ix)里新增一个值 = 发明词表值。
- 语义贴合:service 槽现值全是公共基础设施服务角色;Cloudzy 租户 IP 是
  托管空间归属事实,不是服务角色。
- 前端一等消费:asset.is_hosting 徽章(Hosting/机房)+ csvExport 列。

指控面全弃权(cloud_ranges/ip2proxy ADR 0001 全弃权样板):classification_type
缺省 None、verdict=""(R17A-1 弃权拼写,to_dict 特判保留,读回按 "" 处理
不兑底 malicious)——只走 attributes 资产通道,不产分类组、不计威胁票、
不产 STIX Indicator。authoritative_for=()(镜像源不作 is_hosting 权威,
cloud_ranges 同款不扩面);**非 derived 不入 LINEAGE_CLUSTERS**。
"""
import ipaddress

from .._evidence import Evidence
from .._source_base import Source
from ._download import atomic_write_bytes, redact_url

_MIN_IP_LINES = 100   # download 守卫(实测 3,578 行,peeringdb/dns_public 同款 fail-closed)


class CloudzySource(Source):
    name = "cloudzy"
    category = "asset"
    url = ("https://raw.githubusercontent.com/CriticalPathSecurity/"
           "Public-Intelligence-Feeds/master/cloudzy.txt")
    filename = "cloudzy.txt"
    fields = ("is_hosting",)
    authoritative_for = ()
    stale_days = 30                 # 段级静态,键不换手(排他 98% 真空白)
    reliability = 0.90              # brief 定值;出版方非官方镜像,高于社区 feed 低于自采

    def download(self, token=None) -> None:
        """fail-closed 守卫:仅认可解析 IP 行;200-OK 坏页(HTML 错误页/空
        表)不落盘替换旧数据(dns_public 同款,防下轮 rebuild 静默清源)。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = self._http_get(self.url)
        n = sum(1 for ln in data.decode("utf-8", errors="replace").splitlines()
                if _parse_ip(ln))
        if n < _MIN_IP_LINES:
            raise RuntimeError(
                f"cloudzy: only {n} valid IP lines (<{_MIN_IP_LINES}) "
                f"from {redact_url(self.url)} — existing data file kept")
        atomic_write_bytes(self._path, data)

    def harvest(self):
        for line in self._path.read_text(encoding="utf-8").splitlines():
            ip = _parse_ip(line)
            if ip is None:          # 空行/注释/散文/坏行宁少算,坏到守卫线下由 download 拦
                continue
            yield ip, Evidence(
                is_hosting=True,
                native_types={"is_hosting": "Cloudzy"},
                verdict="",  # 弃权拼写:由 to_dict 特判保留,读回按 "" 处理不兑底(R17A-1)
            )


def _parse_ip(line: str) -> str | None:
    """裸 IP 行 → 规范字符串;不可解析(HTML 残页/未来怪行)→ None。
    ip_address 兼容 v6:上游若引入 v6 行,基类 rebuild_dual_family 自然分区。"""
    s = line.strip()
    try:
        return str(ipaddress.ip_address(s))
    except ValueError:
        return None
