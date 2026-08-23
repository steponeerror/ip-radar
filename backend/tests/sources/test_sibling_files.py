"""兄弟文件双 URL 下载:单文件拼接,v6 失败容错,下游分区正确。"""
from unittest.mock import patch
import urllib.request


def _fake_urlopen(urls: dict):
    """Return a mock urlopen that serves bytes from *urls* dict;
    unconfigured URLs raise RuntimeError."""
    class _Resp:
        def __init__(self, data): self.data = data
        def read(self): return self.data
    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, 'full_url') else req
        if url not in urls:
            raise RuntimeError(f"fetch failed: {url}")
        return _Resp(urls[url])
    return _open


def test_spamhaus_dual_url_concat(tmp_path):
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    v4 = b"1.2.3.0/24 ; SBL123\n"
    v6 = b"2001:678:254::/48 ; SBL456\n"
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen({
                   "https://www.spamhaus.org/drop/drop.txt": v4,
                   "https://www.spamhaus.org/drop/dropv6.txt": v6})):
        src.download()
    content = (tmp_path / "spamhaus_drop.txt").read_bytes()
    assert b"1.2.3.0/24" in content and b"2001:678:254::/48" in content
    # 下游:rebuild 双族 + sbl_id 保留
    src.rebuild()
    assert src._count == 1 and src._count6 == 1
    hit = src.query("2001:678:254::1")
    assert hit[0].get("extra", {}).get("sbl_id") == "SBL456"


def test_spamhaus_v6_sibling_failure_tolerated(tmp_path):
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen({
                   "https://www.spamhaus.org/drop/drop.txt": b"1.2.3.0/24 ; SBL1\n"})):
        src.download()          # dropv6 fetch 失败 → warning,不 raise
    content = (tmp_path / "spamhaus_drop.txt").read_bytes()
    assert b"1.2.3.0/24" in content and b":" not in content


def test_spamhaus_v4_failure_raises(tmp_path):
    import pytest
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen({
                   "https://www.spamhaus.org/drop/dropv6.txt": b"2001:db8::/32\n"})):
        with pytest.raises(RuntimeError):
            src.download()


def test_x4bnet_dual_url_concat(tmp_path):
    from ipdb._sources.x4bnet_vpn import X4BNetVPNSource
    src = X4BNetVPNSource(tmp_path)
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen({
                   "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt": b"1.2.3.4\n",
                   "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt": b"2001:550:1d05::/48\n"})):
        src.download()
    src.rebuild()               # 基类 rebuild:继承即双族
    assert src._count == 1 and src._count6 == 1
    assert src.query("2001:550:1d05::1") is not None
