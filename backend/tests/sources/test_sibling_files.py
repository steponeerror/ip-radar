"""兄弟文件双 URL 下载:单文件拼接,v6 失败容错,下游分区正确。"""
from unittest.mock import patch


def _fake_http(urls: dict):
    """urls: {url: bytes};未配置的 URL 抛 RuntimeError。"""
    def _get(url, **kw):
        if url not in urls:
            raise RuntimeError(f"fetch failed: {url}")
        return urls[url]
    return _get


# ── spamhaus ──

def test_spamhaus_dual_url_concat(tmp_path):
    from ipdb._source_base import Source
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    v4 = b"1.2.3.0/24 ; SBL123\n"
    v6 = b"2001:678:254::/48 ; SBL456\n"
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://www.spamhaus.org/drop/drop.txt": v4,
                          "https://www.spamhaus.org/drop/dropv6.txt": v6})):
        src.download()
    content = (tmp_path / "spamhaus_drop.txt").read_bytes()
    assert b"1.2.3.0/24" in content and b"2001:678:254::/48" in content
    assert src.last_partial_failure == []            # 全绿清零
    # 下游:rebuild 双族 + sbl_id 保留
    src.rebuild()
    assert src._count == 1 and src._count6 == 1
    hit = src.query("2001:678:254::1")
    assert hit[0].get("extra", {}).get("sbl_id") == "SBL456"


def test_spamhaus_v6_sibling_failure_keeps_old_join_and_flags(tmp_path):
    """F-4(A1/Task 3):v6 兄弟失败 → 不写 v4-only 覆盖,旧 join 文件
    字节级保留(v6 证据不再被静默挤掉),flag=["v6"] 让 scheduler 走
    done-但-部分失败 backoff;不 raise。"""
    from ipdb._source_base import Source
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    old = b"1.2.3.0/24 ; SBL1\n2001:db8::/32 ; SBL2\n"
    src._path.write_bytes(old)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://www.spamhaus.org/drop/drop.txt": b"9.9.9.0/24\n"})):
        src.download()          # dropv6 fetch 失败 → warning,不 raise
    assert src._path.read_bytes() == old          # 旧 join 字节级不变
    assert src.last_partial_failure == ["v6"]


def test_spamhaus_v4_failure_raises(tmp_path):
    import pytest
    from ipdb._source_base import Source
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://www.spamhaus.org/drop/dropv6.txt": b"2001:db8::/32\n"})):
        with pytest.raises(RuntimeError):
            src.download()
    assert src.last_partial_failure == ["v4"]   # 失败侧记名后 raise


def test_spamhaus_empty_v4_raises(tmp_path):
    """P1-3: empty v4 response → RuntimeError, not silent empty file."""
    import pytest
    from ipdb._source_base import Source
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://www.spamhaus.org/drop/drop.txt": b"  \n  \t  \n",
                          "https://www.spamhaus.org/drop/dropv6.txt": b"2001:db8::/32\n"})):
        with pytest.raises(RuntimeError, match="empty response"):
            src.download()


def test_spamhaus_empty_v6_keeps_old_join_and_flags(tmp_path):
    """P1-3 mirror + F-4:空 v6 兄弟与拉取失败同语义 — 不 raise、不写
    v4-only,旧 join 保留,flag=["v6"]。"""
    from ipdb._source_base import Source
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    old = b"1.2.3.0/24 ; SBL1\n2001:db8::/32\n"
    src._path.write_bytes(old)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://www.spamhaus.org/drop/drop.txt": b"1.2.3.0/24 ; SBL1\n",
                          "https://www.spamhaus.org/drop/dropv6.txt": b"   \n"})):
        src.download()  # should NOT raise
    assert src._path.read_bytes() == old
    assert src.last_partial_failure == ["v6"]


# ── x4bnet ──

def test_x4bnet_dual_url_concat(tmp_path):
    from ipdb._source_base import Source
    from ipdb._sources.x4bnet_vpn import X4BNetVPNSource
    src = X4BNetVPNSource(tmp_path)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt": b"1.2.3.4\n",
                          "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt": b"2001:550:1d05::/48\n"})):
        src.download()
    src.rebuild()               # 基类 rebuild:继承即双族
    assert src._count == 1 and src._count6 == 1
    assert src.query("2001:550:1d05::1") is not None


def test_x4bnet_no_trailing_newline(tmp_path):
    """P1-2: v4 fixture without trailing newline → both entries survive."""
    from ipdb._source_base import Source
    from ipdb._sources.x4bnet_vpn import X4BNetVPNSource
    src = X4BNetVPNSource(tmp_path)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt": b"1.2.3.4",
                          "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt": b"2001:550:1d05::/48\n"})):
        src.download()
    src.rebuild()
    assert src._count == 1 and src._count6 == 1


def test_x4bnet_v6_failure_keeps_old_join_and_flags(tmp_path):
    """F-4(spamhaus 同型):v6 失败 → 不写 v4-only 覆盖,旧 join 字节级
    保留 + flag=["v6"];v4 失败记 ["v4"] 并 raise。"""
    import pytest
    from ipdb._source_base import Source
    from ipdb._sources.x4bnet_vpn import X4BNetVPNSource
    src = X4BNetVPNSource(tmp_path)
    old = b"1.2.3.4\n2001:550:1d05::/48\n"
    src._path.write_bytes(old)
    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt": b"9.9.9.9\n"})):
        src.download()          # ipv6 fetch 失败 → warning,不 raise
    assert src._path.read_bytes() == old
    assert src.last_partial_failure == ["v6"]

    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv6.txt": b"2001:db8::/32\n"})):
        with pytest.raises(RuntimeError):
            src.download()      # v4 失败 → raise
    assert src.last_partial_failure == ["v4"]
    assert src._path.read_bytes() == old         # 全程未被触碰


def test_spamhaus_write_failure_keeps_old_file(tmp_path):
    """DL-F2 代表源(join 形):v4+v6 拼接落地时写 scratch 抛(模拟 ENOSPC)
    → 旧数据文件字节级保留、.tmp 无残留,异常上抛走退避。"""
    from pathlib import Path as _Path
    import pytest
    from ipdb._source_base import Source
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    old = b"1.2.3.0/24 ; SBL123\n"
    src._path.write_bytes(old)
    scratch = tmp_path / "spamhaus_drop.txt.tmp"
    real_write = _Path.write_bytes
    wrote_partial = False

    def enospc_mid_write(data: bytes):
        nonlocal wrote_partial
        real_write(scratch, data[: len(data) // 2])  # 半途:盘上已有部分字节
        wrote_partial = True
        raise OSError(28, "No space left on device")

    with patch.object(Source, "_http_get",
                      side_effect=_fake_http({
                          "https://www.spamhaus.org/drop/drop.txt": b"9.9.9.0/24\n",
                          "https://www.spamhaus.org/drop/dropv6.txt": b"2001:db8::/32\n"})):
        with patch.object(_Path, "write_bytes", side_effect=enospc_mid_write):
            with pytest.raises(OSError):
                src.download()
    assert wrote_partial                    # 失败时盘上确有真 scratch
    assert src._path.read_bytes() == old           # 字节级完好
    assert not scratch.exists()
