"""dns_public (Source subclass) — DNSCrypt public-resolvers feed asset source.

Synthetic mini fixture only (offline; stamps generated in-test from the v3
grammar: byte0 proto, u64 LE props, then varstrings) — real feed numbers are
NOT pinned, the feed drifts weekly by design. Dual-family n4 convention
(T1 Ruling 2026-10-10, same as test_reportedip/test_root_servers): v4 stamps
count into rebuild()/record_count/covered_ips; v6 stamps land in the v6 family
(covered_v6_nets). Skipped shapes: hostname-only / empty address (宁少算 —
no DNS resolution); same IP under two sections dedups to one row, provider
label = first section's name verbatim.
"""
import base64
import struct
from pathlib import Path

import pytest

from ipdb._sources.dns_public import DnsPublicSource


def _stamp(proto: int, addr: bytes, *rest: bytes) -> str:
    """v3 stamp generator: proto(1) + props u64 LE(8) + varstr(len+bytes)..."""
    body = bytes([proto]) + struct.pack("<Q", 0) + bytes([len(addr)]) + addr
    body += b"".join(bytes([len(v)]) + v for v in rest)
    return "sdns://" + base64.urlsafe_b64encode(body).decode().rstrip("=")


_PUBKEY = b"\x11" * 8   # 解码器只读首 varstr,余下 varstr 用哑元占形


def _fixture() -> str:
    return f"""\
# public-resolvers (synthetic test fixture)

Header prose mentioning sdns:// mid-line must be ignored (not line-start).
urls = ['https://example.invalid/public-resolvers.md']
minisign_key = 'RW...'

--
A line-start stamp BEFORE the first section header — no owner section, must be
skipped (钉住 section is None 防御分支;rebuild()==3 若变 4 即漏跳).
{_stamp(2, b"203.0.113.42", b"", b"dns.pre-section.example", b"/dns-query")}

## test-doh-ip

Synthetic DoH with plain v4 literal and bracketed v6 literal.

{_stamp(2, b"203.0.113.10", b"", b"dns.test.example", b"/dns-query")}
{_stamp(2, b"[2001:db8::10]", b"", b"dns.test.example", b"/dns-query")}

## test-dnscrypt-port

Synthetic DNSCrypt with v4:port (port stripped) — section header noise and
prose lines like this one never produce rows.

{_stamp(1, b"192.0.2.7:5353", _PUBKEY, b"2.dnscrypt-cert.test")}

## test-odoh-conservative

Unknown proto 0x03: conservative rule — same first-varstr treatment, IP
literal still harvested (0x03/0x04/0x05 一律按首 varstr,非字面量才跳).

{_stamp(3, b"198.51.100.7", b"", b"dns.test.example", b"/dns-query")}

## test-doh-hostname

Hostname-only address → skipped (宁少算: no DNS resolution).

{_stamp(2, b"dns.hostname-only.example", b"", b"dns.hostname-only.example", b"/dns-query")}

## test-doh-empty

Empty address → skipped.

{_stamp(2, b"", b"", b"dns.empty.example", b"/dns-query")}

## test-dup-second

Same 203.0.113.10 again — dedup to one row, provider stays first section.

{_stamp(2, b"203.0.113.10", b"", b"dns.other.example", b"/dns-query")}

## test-dup-v6-second

Same v6 again via DNSCrypt [v6]:port — dedup, provider stays test-doh-ip.

{_stamp(1, b"[2001:db8::10]:8443", _PUBKEY, b"2.dnscrypt-cert.test")}
"""


def test_dns_public_rebuild_dual_family(tmp_path: Path):
    (tmp_path / "dns_public.md").write_text(_fixture())
    s = DnsPublicSource(data_dir=tmp_path)
    assert s.rebuild() == 3             # 203.0.113.10 / 192.0.2.7 / 198.51.100.7
    h = s.health()
    assert h.record_count == 3
    assert h.covered_ips == 3           # 3 个 /32 单址
    assert h.covered_v6_nets == 1       # 2001:db8::10 → v6 族 1 个 /128
    assert h.is_stale is False          # 样本刚写盘,stale_days=7


def test_dns_public_query_first_section_wins(tmp_path: Path):
    (tmp_path / "dns_public.md").write_text(_fixture())
    s = DnsPublicSource(data_dir=tmp_path)
    s.rebuild()
    r = s.query("203.0.113.10")[0]      # 双 section 同 IP → 文件序首见者胜
    assert r["service"] == "dns"
    assert r["_native_types"] == {"service": "test-doh-ip"}
    assert r["verdict"] == ""           # 弃权拼写:读回按 "" 处理不兑底(R17A-1)
    # DNSCrypt v4:port → 端口剥除,slug 取该 section 名
    assert s.query("192.0.2.7")[0]["_native_types"] == {"service": "test-dnscrypt-port"}
    # 未知 proto 0x03 保守规则:首 varstr 是字面量即收
    assert s.query("198.51.100.7")[0]["_native_types"] == {"service": "test-odoh-conservative"}
    # v6 查询走 v6 族路径;跨族同 IP 去重,首见 slug 同样生效
    r6 = s.query("2001:db8::10")[0]
    assert r6["service"] == "dns"
    assert r6["_native_types"] == {"service": "test-doh-ip"}


def test_dns_public_skipped_shapes_leave_no_rows(tmp_path: Path):
    """hostname-only / 空地址条目零产出:其(不存在的)IP 查询空,计数不含。"""
    (tmp_path / "dns_public.md").write_text(_fixture())
    s = DnsPublicSource(data_dir=tmp_path)
    assert s.rebuild() == 3             # 若漏跳会被 5 打破(hostname/empty 各 1)
    assert s.query("192.0.2.99") == {}  # fixture 外 IP 无行
    assert s.query("2001:db8::99") == {}


def test_dns_public_download_guard_rejects_thin_payload(tmp_path: Path, monkeypatch):
    """200-OK 薄内容守卫:<50 sdns 行即失败,且失败不落盘(空文件会被下次
    rebuild 静默清源,skill Phase 3 §8)。不打网络——_http_get 打桩。"""
    s = DnsPublicSource(data_dir=tmp_path)
    monkeypatch.setattr(
        DnsPublicSource, "_http_get",
        staticmethod(lambda *a, **k: b"# garbage\nno stamps here\n"))
    with pytest.raises(RuntimeError):
        s.download()
    assert not s._path.exists()         # 原子写未发生,数据文件未被触碰
