"""X4BNet VPN list source — IpListSource subclass."""
from ._base import IpListSource
from ._download import atomic_write_bytes, redact_url


class X4BNetVPNSource(IpListSource):
    name = "x4bnet_vpn"
    category = "asset"
    url = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt"
    filename = "x4bnet_vpn.txt"
    fields = ("is_vpn",)
    classification_type = "proxy"
    verdict = "suspicious"
    stale_days = 7
    reliability = 0.70
    authoritative_for = ("is_vpn",)
    # 转载声明(卡2上半,#464;实测 2026-11-26 生产镜像全库扫描,归档
    # docs/reports/2026-11-26-arch-r4-landing/#451-卡2-转载关系/verify/scan_step3.json(A5:曾为 untracked 本地件
    # dev/arch-r4-scan/,已归档文档仓)):⊇ protonvpn 2,875/2,875(100%)。
    # 口径:镜像内 IPv4 单地址单元——分母 = 被 protonvpn 覆盖且作 IPv4
    # 单地址单元出现的地址(扫描只数 v4 单地址 5,341,414 个;v4 网段 177,090 与 v6 不计)。「同场共现」非逐字照搬之证(评审
    # B3)。原创 protonvpn r=.75 强于转载者 .70,同场即剔。
    republishes = ("protonvpn",)

    _V6_URL = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt"

    def download(self, token=None) -> None:
        """双 URL 拼接单文件(spamhaus 同型,F-4):v6 兄弟失败 → 不写
        v4-only 覆盖,旧 join 文件字节级保留 + 记 ["v6"];v4 失败记
        ["v4"] 并 raise;两路全挂随 v4 raise 走既有退避。"""
        import logging
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            v4 = self._http_get(self.url)
            if not v4.strip():
                raise RuntimeError(f"empty response from {redact_url(self.url)}")
        except Exception:
            self.last_partial_failure = ["v4"]
            raise
        try:
            v6 = self._http_get(self._V6_URL)
            if not v6.strip():
                raise RuntimeError(f"empty v6 sibling from {redact_url(self._V6_URL)}")
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"x4bnet ipv6 fetch failed: {e} — keeping existing join file")
            self.last_partial_failure = ["v6"]
            return
        self.last_partial_failure = []
        if v4 and not v4.endswith(b"\n"):
            v4 += b"\n"
        atomic_write_bytes(self._path, v4 + v6)

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_vpn=True,
            native_types={"is_vpn": "VPN"},
        ).to_dict()
