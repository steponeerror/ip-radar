"""InsightFlare/asn-blocklist — hosting ASN 清单(ASN 键,查询期 join;票 #332 P1)。
数据:InsightFlare/asn-blocklist 仓 dist/hosting.txt(纯文本行式 `AS<编号>`,
无表头无注释;2026-11-15 实抓 2,957 行全为 AS<数字>,文件内部无时间戳,
新鲜度信号 = 文件 mtime / GitHub commits 路径 dist/hosting.txt)。上游来源
PeeringDB 网络类型 hosting(API 拉取自动生成),周更(周一 Release
v1.YYYYMMDD.0);出版方 InsightFlare = 社区镜像(PeeringDB 官方数据、非
官方发布)→ provenance_tier=B(cloudzy 镜像先例)。
语义:ASN 属 hosting/datacenter 基础设施 = is_hosting=True 资产陈述,
信息位不指控(cloud_ranges/cloudzy 全弃权样板):classification_type 缺省
None、不产分类组、不计威胁票。authoritative_for=()(镜像派生源不作
is_hosting 权威)。
生命周期合同与 caida_asorg 同款(全仓无 LMDB 面的第二例):数据是 ASN
集合,无 CIDR 可入库 → download() 落原始文件(fail-closed 守卫),
load()/rebuild() 解析为内存 set,query(ip) 恒 None;join 走
hosting_for_asn 钩子——_registry 在 asn 胜者解出后注入 is_hosting 资产
陈述(as_org/org_for_asn join 同款形状,allowed_sources 照常过滤)。
"""
import dataclasses
import logging
import time
from pathlib import Path

from .._evidence import Evidence  # noqa: F401 — fields 契约可见性
from .._source_base import Source
from .._types import SourceHealth
from ._download import atomic_write_bytes, redact_url

logger = logging.getLogger(__name__)

_URL = ("https://raw.githubusercontent.com/InsightFlare/asn-blocklist/"
        "main/dist/hosting.txt")

# native label:ASN 的 hosting 归属陈述来源(PeeringDB org 类型 hosting;
# nordvpn "NordVPN"/cloudzy "Cloudzy" 同款自由格式)
_NATIVE_LABEL = "PeeringDB hosting"


class InsightflareAsnBlocklistSource(Source):
    name = "insightflare_asn_blocklist"
    category = "asset"             # 基础设施角色(hosting/datacenter ASN)
    filename = "insightflare_asn_blocklist.txt"
    url = _URL
    fields = ("is_hosting",)
    authoritative_for = ()         # 社区镜像派生,不作 is_hosting 权威
    stale_days = 14                # 周更,双周余量
    reliability = 0.85             # PeeringDB 官方数据经社区镜像(低于自采/官方)
    provenance_tier = "B"          # 社区镜像(cloudzy 先例)
    # 无 per-IP LMDB 面:rebuild=load,文件即持久层(query 恒 None,join 走
    # hosting_for_asn 钩子)→ 豁免 needs_rebuild(caida_asorg 幻影环先例)
    lmdb_backed = False
    # 2026-11-15 实抓 2,957 行;200-OK 空/坏页(HTML 错误页)不落地(fail-closed)
    _MIN_ASN_ROWS = 1_000
    infra_noise_filter = False         # 显式关:存量源行为不变(#531;基类默认已翻 True)

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self._asns: frozenset[int] | None = None   # None = 未加载

    def download(self, token=None) -> None:
        """fail-closed 守卫:仅认可 AS<数字> 行;200-OK 坏页(HTML 错误页/
        空表)不落盘替换旧数据(cloudzy/dns_public 同款)。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = self._http_get(self.url)
        n = sum(1 for ln in data.decode("utf-8", errors="replace").splitlines()
                if _parse_asn(ln) is not None)
        if n < self._MIN_ASN_ROWS:
            raise RuntimeError(
                f"insightflare_asn_blocklist: only {n} valid AS lines "
                f"(<{self._MIN_ASN_ROWS}) from {redact_url(self.url)} "
                f"— existing data file kept")
        atomic_write_bytes(self._path, data)

    # ── 无 LMDB 生命周期:文件即持久层,解析即加载(caida_asorg 同款)──

    def _parse(self) -> frozenset[int]:
        asns = set()
        with open(self._path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                asn = _parse_asn(line)
                if asn is not None:   # 空行/坏行宁少算,坏到守卫线下由 download 拦
                    asns.add(asn)
        return frozenset(asns)

    def load(self) -> int:
        if not self._path.exists():
            self._asns = None
            return 0
        self._asns = self._parse()
        self._loaded_at = time.time()
        return len(self._asns)

    def rebuild(self, progress=None) -> int:
        # 无 LMDB:重建 = 重新解析文件为内存 set(UpdateManager 队列照常调用)
        return self.load()

    def query(self, ip: str):
        return None                # 无 per-IP 面;join 走 hosting_for_asn 钩子

    def hosting_for_asn(self, asn) -> str | None:
        """ASN 在 hosting 清单内 → native label;表外/坏入参 → None。
        _registry 查询期 join 钩子(as_org/org_for_asn 同款合同)。"""
        if self._asns is None:
            return None
        try:
            return _NATIVE_LABEL if int(asn) in self._asns else None
        except (TypeError, ValueError):
            return None

    def health(self) -> SourceHealth:
        # convention 4:鲜度看文件 mtime,不看加载时刻——算法已收 _freshness
        # 单源点(#465 卡16),基类照算,本源只换 loaded / record_count 两个
        # 取法(无 LMDB:内存 set 即持久层)。
        return dataclasses.replace(
            super().health(),
            loaded=self._asns is not None,
            record_count=len(self._asns or ()),
        )


def _parse_asn(line: str) -> int | None:
    """`AS<数字>` 行 → 整数 ASN;其余(空行/裸数字/小写前缀/HTML 残页)
    → None(键列坏整行丢弃惯例)。"""
    s = line.strip()
    if not (s.startswith("AS") and len(s) > 3):
        return None
    body = s[2:]
    if not body.isdigit():
        return None
    return int(body)


# ── 装载约定(PEP 562):stem 的三种规范拼法均可导入;变体不进 dir(),
# 注册表 dir() 枚举不会双注册。①机械形 InsightflareAsnBlocklistSource(主);
# ②品牌拆词形 Insightflare ASN Blocklist → InsightflareAsnBlocklist(同主,免列);
# ③缩写全大写形 INSIGHTFLAREASNBlocklist → 别名。
_IMPORT_ALIASES = {
    "InsightflareASNBlocklistSource": "InsightflareAsnBlocklistSource",
}


def __getattr__(name):
    if name in _IMPORT_ALIASES:
        return globals()[_IMPORT_ALIASES[name]]
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}")
