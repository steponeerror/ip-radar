"""X4BNet VPN list source — IpListSource subclass."""
from ._base import IpListSource


class X4BNetVPNSource(IpListSource):
    name = "x4bnet_vpn"
    url = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt"
    filename = "x4bnet_vpn.txt"
    fields = ("is_vpn",)
    classification_type = "proxy"
    verdict = "suspicious"
    stale_days = 7
    reliability = 0.70
    authoritative_for = ["is_vpn"]

    _V6_URL = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt"

    def download(self, token=None) -> None:
        """双 URL 拼接单文件(spamhaus 同型);v6 兄弟失败容忍。"""
        import logging
        import urllib.request
        self._data_dir.mkdir(parents=True, exist_ok=True)
        v4 = urllib.request.urlopen(
            urllib.request.Request(self.url,
                                   headers={"User-Agent": "ip-lookup-tool/1.0"})
        ).read()
        try:
            v6 = urllib.request.urlopen(
                urllib.request.Request(self._V6_URL,
                                       headers={"User-Agent": "ip-lookup-tool/1.0"})
            ).read()
        except Exception as e:
            logging.getLogger(__name__).warning(f"x4bnet ipv6 fetch failed: {e}")
            v6 = b""
        self._path.write_bytes(v4 + v6)

    def get_insert_data(self) -> dict:
        from .._evidence import Evidence
        return Evidence(
            classification_type=self.classification_type,
            verdict=self.verdict,
            reliability=self.reliability,
            is_vpn=True,
            native_types={"is_vpn": "VPN"},
        ).to_dict()
