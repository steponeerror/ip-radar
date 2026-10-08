"""X4BNet VPN list source — IpListSource subclass."""
from .._source_base import Source
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

    _V6_URL = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt"

    def download(self, token=None) -> None:
        """双 URL 拼接单文件(spamhaus 同型,F-4):v6 兄弟失败 → 不写
        v4-only 覆盖,旧 join 文件字节级保留 + 记 ["v6"];v4 失败记
        ["v4"] 并 raise;两路全挂随 v4 raise 走既有退避。"""
        import logging
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            v4 = Source._http_get(self.url)
            if not v4.strip():
                raise RuntimeError(f"empty response from {redact_url(self.url)}")
        except Exception:
            self.last_partial_failure = ["v4"]
            raise
        try:
            v6 = Source._http_get(self._V6_URL)
            if not v6.strip():
                raise RuntimeError(f"empty v6 sibling from {self._V6_URL}")
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
