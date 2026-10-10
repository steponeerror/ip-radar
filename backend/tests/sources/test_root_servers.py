"""root_servers (Source subclass) — IANA named.root fetched asset source.

Real named.root sample embedded verbatim (91 lines, v3 serial 2026100701,
trailing-space comments included): 13 root servers, one A + one AAAA each
= 26 total rows. Dual-family n4 convention (T1 Ruling 2026-10-10, same as
test_reportedip): rebuild()/record_count/covered_ips count the 13 v4 rows;
the 13 AAAA rows land in the v6 family (covered_v6_nets == 13). Native
label = "<letter> root server" (lowercase first label of the hostname);
operator names are curated knowledge deliberately not riding the feed.
"""
from pathlib import Path

import pytest

from ipdb._sources.root_servers import RootServersSource

SAMPLE = """\
;       This file holds the information on root name servers needed to 
;       initialize cache of Internet domain name servers
;       (e.g. reference this file in the "cache  .  <file>"
;       configuration file of BIND domain name servers). 
; 
;       This file is made available by InterNIC 
;       under anonymous FTP as
;           file                /domain/named.cache 
;           on server           FTP.INTERNIC.NET
;       -OR-                    RS.INTERNIC.NET
;
;       last update:     October 07, 2026
;       related version of root zone:     2026100701
; 
; FORMERLY NS.INTERNIC.NET 
;
.                        3600000      NS    A.ROOT-SERVERS.NET.
A.ROOT-SERVERS.NET.      3600000      A     198.41.0.4
A.ROOT-SERVERS.NET.      3600000      AAAA  2001:503:ba3e::2:30
; 
; FORMERLY NS1.ISI.EDU 
;
.                        3600000      NS    B.ROOT-SERVERS.NET.
B.ROOT-SERVERS.NET.      3600000      A     170.247.170.2
B.ROOT-SERVERS.NET.      3600000      AAAA  2801:1b8:10::b
; 
; FORMERLY C.PSI.NET 
;
.                        3600000      NS    C.ROOT-SERVERS.NET.
C.ROOT-SERVERS.NET.      3600000      A     192.33.4.12
C.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:2::c
; 
; FORMERLY TERP.UMD.EDU 
;
.                        3600000      NS    D.ROOT-SERVERS.NET.
D.ROOT-SERVERS.NET.      3600000      A     199.7.91.13
D.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:2d::d
; 
; FORMERLY NS.NASA.GOV
;
.                        3600000      NS    E.ROOT-SERVERS.NET.
E.ROOT-SERVERS.NET.      3600000      A     192.203.230.10
E.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:a8::e
; 
; FORMERLY NS.ISC.ORG
;
.                        3600000      NS    F.ROOT-SERVERS.NET.
F.ROOT-SERVERS.NET.      3600000      A     192.5.5.241
F.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:2f::f
; 
; FORMERLY NS.NIC.DDN.MIL
;
.                        3600000      NS    G.ROOT-SERVERS.NET.
G.ROOT-SERVERS.NET.      3600000      A     192.112.36.4
G.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:12::d0d
; 
; FORMERLY AOS.ARL.ARMY.MIL
;
.                        3600000      NS    H.ROOT-SERVERS.NET.
H.ROOT-SERVERS.NET.      3600000      A     198.97.190.53
H.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:1::53
; 
; FORMERLY NIC.NORDU.NET
;
.                        3600000      NS    I.ROOT-SERVERS.NET.
I.ROOT-SERVERS.NET.      3600000      A     192.36.148.17
I.ROOT-SERVERS.NET.      3600000      AAAA  2001:7fe::53
; 
; OPERATED BY VERISIGN, INC.
;
.                        3600000      NS    J.ROOT-SERVERS.NET.
J.ROOT-SERVERS.NET.      3600000      A     192.58.128.30
J.ROOT-SERVERS.NET.      3600000      AAAA  2001:503:c27::2:30
; 
; OPERATED BY RIPE NCC
;
.                        3600000      NS    K.ROOT-SERVERS.NET.
K.ROOT-SERVERS.NET.      3600000      A     193.0.14.129
K.ROOT-SERVERS.NET.      3600000      AAAA  2001:7fd::1
; 
; OPERATED BY ICANN
;
.                        3600000      NS    L.ROOT-SERVERS.NET.
L.ROOT-SERVERS.NET.      3600000      A     199.7.83.42
L.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:9f::42
; 
; OPERATED BY WIDE
;
.                        3600000      NS    M.ROOT-SERVERS.NET.
M.ROOT-SERVERS.NET.      3600000      A     202.12.27.33
M.ROOT-SERVERS.NET.      3600000      AAAA  2001:dc3::35
; End of file"""


def test_root_servers_rebuild_and_health(tmp_path: Path):
    (tmp_path / "root_servers.cache").write_text(SAMPLE)
    s = RootServersSource(data_dir=tmp_path)
    assert s.rebuild() == 13            # 13 A 行;13 AAAA 行入 v6 族(26 总行,n4 口径)
    h = s.health()
    assert h.record_count == 13
    assert h.covered_ips == 13          # 13 个 /32 单址
    assert h.covered_v6_nets == 13      # 13 个 /128 单址
    assert h.is_stale is False          # 样本刚写盘,stale_days=7


def test_root_servers_query_native_label(tmp_path: Path):
    (tmp_path / "root_servers.cache").write_text(SAMPLE)
    s = RootServersSource(data_dir=tmp_path)
    s.rebuild()
    r = s.query("198.41.0.4")[0]        # A.ROOT-SERVERS.NET
    assert r["service"] == "dns"
    assert r["_native_types"] == {"service": "a root server"}
    assert r["verdict"] == ""           # 弃权拼写:读回按 "" 处理不兑底(R17A-1)
    # 字母取自主机名首标签(小写),非硬编码一枚
    assert s.query("202.12.27.33")[0]["_native_types"] == {"service": "m root server"}
    # v6 对经 v6 族查询路径命中
    r6 = s.query("2001:503:ba3e::2:30")[0]
    assert r6["service"] == "dns"
    assert r6["_native_types"] == {"service": "a root server"}


def test_root_servers_tolerates_comments_blank_and_ns_lines(tmp_path: Path):
    """注释/空行/NS glue 行零产出,只采 A/AAAA 记录行。"""
    (tmp_path / "root_servers.cache").write_text(
        "; comment line\n\n"
        ".                        3600000      NS    A.ROOT-SERVERS.NET.\n"
        "A.ROOT-SERVERS.NET.      3600000      A     198.41.0.4\n"
        "A.ROOT-SERVERS.NET.      3600000      AAAA  2001:503:ba3e::2:30\n"
    )
    s = RootServersSource(data_dir=tmp_path)
    assert s.rebuild() == 1             # 仅 1 A 行计 n4;NS/注释/空行不产
    assert s.health().covered_v6_nets == 1
    assert s.query("198.41.0.4")[0]["_native_types"] == {"service": "a root server"}


def test_root_servers_download_guard_rejects_thin_payload(tmp_path: Path, monkeypatch):
    """200-OK 薄内容守卫:<13 A 行即失败,且失败不落盘(空文件会被下次
    rebuild 静默清源,skill Phase 3 §8)。不打网络——_http_get 打桩。"""
    s = RootServersSource(data_dir=tmp_path)
    monkeypatch.setattr(RootServersSource, "_http_get",
                        staticmethod(lambda *a, **k: b"; stale-ish\n1.2.3.4 A\n"))
    with pytest.raises(RuntimeError):
        s.download()
    assert not s._path.exists()         # 原子写未发生,数据文件未被触碰
