"""六个自定义 rebuild 位点:解析放开 v6 + rebuild 后 v6 ptr 必在(Q3)。

fixture 文件名/目录形态按各源真实 __init__/download 写盘路径修正
(brief 预授权),断言不变。上游实测(2026-08-23 审计):abuseipdb 429 未测、
cn_isp/firehol 上游纯 v4(C 类)——它们的 v6 env 恒空但 ptr 必写。
"""
import importlib
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("modname,cls,filename,content", [
    ("spamhaus", "SpamhausSource", "spamhaus_drop.txt",
     "1.2.3.0/24 ; SBL123\n2001:db8::/32 ; SBL456\n"),
    ("tor_exits", "TorExitSource", "tor-exit-addresses.txt",
     "1.2.3.4,2026-08-23T00:00:00\n2001:db8::1,2026-08-23T00:00:00\n"),
    ("blocklist_de", "BlocklistDeSource", "blocklist_de/all.txt",
     "1.2.3.4\n2001:db8::dead\n"),
])
def test_custom_rebuild_accepts_v6(tmp_path, modname, cls, filename, content):
    mod = importlib.import_module(f"ipdb._sources.{modname}")
    src = getattr(mod, cls)(tmp_path)
    p = tmp_path / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    src.rebuild()
    assert src._count == 1, f"{modname} v4 记录数"
    assert src._count6 == 1, f"{modname} v6 记录数"
    # v6 查询必须安静(分派正确,不抛 ValueError);spamhaus 段内另测
    assert src.query("2001:db8::1") is not None or modname == "spamhaus"


def test_spamhaus_v6_range_lookup(tmp_path):
    from ipdb._sources.spamhaus import SpamhausSource
    src = SpamhausSource(tmp_path)
    (tmp_path / "spamhaus_drop.txt").write_text("2001:db8::/32 ; SBL1\n")
    src.rebuild()
    assert src.query("2001:db8::7777")          # 段内命中(非精确起点)→ 非空证据


def test_tor_exits_v6_range_and_last_seen(tmp_path):
    """tor_exits:裸 v6 行 → /128 记录,ts → last_seen 保留(覆写逻辑不破)。"""
    from ipdb._sources.tor_exits import TorExitSource
    src = TorExitSource(tmp_path)
    (tmp_path / "tor-exit-addresses.txt").write_text(
        "2001:db8::1,2026-08-23T00:00:00\n")
    src.rebuild()
    assert src._count6 == 1
    node = src.query("2001:db8::1")
    assert node is not None
    assert node[0]["last_seen"] == "2026-08-23T00:00:00"


def test_tor_exits_parse_raw_accepts_v6():
    """download 归一化层不丢 v6 ExitAddress 行(rebuild 放开的前置)。"""
    from ipdb._sources.tor_exits import TorExitSource
    src = TorExitSource(Path("/tmp/nonexistent-tor"))
    raw = (b"ExitAddress 1.2.3.4 2026-08-23 00:00:00\n"
           b"ExitAddress 2001:db8::66 2026-08-23 00:00:00\n"
           b"ExitAddress not-an-ip 2026-08-23 00:00:00\n")
    got = src.parse_raw(raw)
    assert "1.2.3.4,2026-08-23T00:00:00" in got
    assert "2001:db8::66,2026-08-23T00:00:00" in got
    assert all("not-an-ip" not in g for g in got)


@pytest.mark.parametrize("modname,cls,mk_files", [
    ("abuseipdb", "AbuseIPDBSource", lambda tmp: [
        (tmp / "abuseipdb.txt",
         json.dumps({"data": [{"ipAddress": "1.2.3.4",
                               "lastReportedAt": "2026-08-23"}]}))]),
    ("cn_isp", "ChineseISPSource", lambda tmp: [
        (tmp / "isp" / "chinatelecom.txt", "1.0.1.0/24\n")]),
    ("firehol", "FireholBlocklistSource", lambda tmp: [
        (tmp / "firehol" / "firehol_level1.netset", "1.2.4.0/24\n")]),
])
def test_v4only_sources_still_write_v6_ptr(tmp_path, modname, cls, mk_files):
    """C 类源(上游纯 v4):rebuild 后 v6 ptr 仍必写(空 env)——Q3 不变量。"""
    mod = importlib.import_module(f"ipdb._sources.{modname}")
    src = getattr(mod, cls)(tmp_path)
    for path, content in mk_files(tmp_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    n = src.rebuild()
    assert n >= 1
    from ipdb._sources._lmdb import read_ptr
    assert read_ptr(src._lmdb6_base) is not None
    assert src._count6 == 0


def test_cn_isp_firehol_v6_query_quiet(tmp_path):
    """覆写 query() 的两个 Source 子类:v6 查询分派到 _query6,安静 {}。"""
    from ipdb._sources.cn_isp import ChineseISPSource
    from ipdb._sources.firehol import FireholBlocklistSource
    d = tmp_path / "isp"
    d.mkdir()
    (d / "chinatelecom.txt").write_text("1.0.1.0/24\n")
    cn = ChineseISPSource(tmp_path)
    cn.rebuild()
    assert cn.query("2001:db8::42") == {}

    f = tmp_path / "firehol"
    f.mkdir()
    (f / "firehol_level1.netset").write_text("1.2.4.0/24\n")
    fh = FireholBlocklistSource(tmp_path)
    fh.rebuild()
    assert fh.query("2001:db8::42") == {}


def test_cn_isp_firehol_load_reads_v6_side(tmp_path):
    """覆写 load() 的两个 Source 子类:load 后 v6 状态解析(空 sidecar 零态)。"""
    from ipdb._sources.cn_isp import ChineseISPSource
    d = tmp_path / "isp"
    d.mkdir()
    (d / "chinatelecom.txt").write_text("1.0.1.0/24\n")
    cn = ChineseISPSource(tmp_path)
    cn.rebuild()
    cn._reader.close()
    cn._reader6.close()
    cn.load()
    assert cn._reader6 is not None        # 空 v6 env 也有 ptr → load 打开空 env
    # 空 env 仍可查询(安静 miss),与 v4 数据共存
    assert cn.query("1.0.1.5") is not None
    assert cn.query("2001:db8::42") == {}
