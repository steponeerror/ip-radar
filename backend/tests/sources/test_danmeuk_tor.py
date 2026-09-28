"""dan.me.uk Tor node list — IpListSource (plain IP-per-line, no timestamps).

Second independent witness for is_tor / classification `tor`
(tor_exits = official check.torproject.org exits; this list covers the
full relay set — ~10.7k rows, 2026-08-23 archived capture re-verified
2026-09-28).
"""
from pathlib import Path

import pytest

from ipdb._sources.danmeuk_tor import DanMeUkTorSource

# 观测到的限速页(2026-09-28):HTTP 200 + 文本 body,非 4xx —— 基类
# IpListSource.download() 的空 body / 零解析行两道守卫都会放行它。
_BLOCK_PAGE = (
    b"Umm... You can only fetch the data every 30 minutes - sorry.\n"
    b"Please keep trying.\n"
)


def test_danmeuk_rebuild_and_query_hit_miss(tmp_path: Path):
    f = tmp_path / "danmeuk_tor.txt"
    f.write_text("# comment\n203.0.113.7\n198.51.100.9\nnot-an-ip\n2001:db8::1\n")
    s = DanMeUkTorSource(data_dir=tmp_path)
    n = s.rebuild()
    assert n == 2                                  # invalid line dropped; v6 行入 v6 族不计 n4
    assert s.health().record_count == 2
    rec = s.query("203.0.113.7")[0]                # hit → list of evidence
    assert rec["classification_type"] == "tor"
    assert rec["is_tor"] is True
    assert s.query("2001:db8::1")[0]["is_tor"] is True   # v6 行命中 v6 族
    assert s.query("192.0.2.1") == {}              # miss → {}


def test_danmeuk_get_insert_data_is_evidence_contract(tmp_path: Path):
    """get_insert_data() must construct via Evidence so the declared
    reliability (0.85) reaches the record and _native_types stays in
    lockstep with Evidence.to_dict()."""
    from ipdb._evidence import Evidence
    s = DanMeUkTorSource(data_dir=tmp_path)
    assert s.get_insert_data() == Evidence(
        classification_type="tor", verdict="suspicious", reliability=0.85,
        is_tor=True, native_types={"is_tor": "RELAY"},
    ).to_dict()


def test_danmeuk_fresh_instance_load(tmp_path: Path):
    """Fresh instance on the same data_dir re-opens the env (convention 7 —
    never load() on the instance that rebuilt)."""
    (tmp_path / "danmeuk_tor.txt").write_text("203.0.113.7\n")
    s = DanMeUkTorSource(data_dir=tmp_path)
    s.rebuild()
    if s._reader is not None:                      # convention 7:同进程双开禁,先关再开
        s._reader.close()
    if s._reader6 is not None:
        s._reader6.close()
    s2 = DanMeUkTorSource(data_dir=tmp_path)
    assert s2.load() == 1
    assert s2.query("203.0.113.7")[0]["is_tor"] is True


def test_danmeuk_download_rejects_rate_limit_page(tmp_path: Path, monkeypatch):
    """限速页 = HTTP 200 + HTML/文本 body(观测 2026-09-28,非 4xx):基类
    守卫放行它 → 数据文件被垃圾替换 → 下次 rebuild 提交空 env,源被静默清空。
    覆写必须拒绝且不碰既有数据文件(Phase 3 step 8 内容守卫)。"""
    s = DanMeUkTorSource(data_dir=tmp_path)

    # 验证钩子(无网络):限速页拒,合法清单过
    with pytest.raises(RuntimeError, match="rate-limit"):
        s._validate_raw(_BLOCK_PAGE)
    s._validate_raw(b"# x\n203.0.113.7\n2001:db8::1\n")          # no raise

    def _serve(url, dest, token=None, **kw):
        dest.write_bytes(_BLOCK_PAGE)               # 模拟 download_file 落盘契约

    good = "203.0.113.7\n198.51.100.9\n"
    (tmp_path / "danmeuk_tor.txt").write_text(good)
    monkeypatch.setattr("ipdb._sources._download.download_file", _serve)
    with pytest.raises(RuntimeError, match="rate-limit"):
        s.download()
    assert (tmp_path / "danmeuk_tor.txt").read_text() == good   # 数据文件原样
    assert not (tmp_path / "danmeuk_tor.txt.dl").exists()       # scratch 已清理

    # 合法载荷走完整通路:解析条目落盘(与基类行为一致)
    def _serve_list(url, dest, token=None, **kw):
        dest.write_bytes(b"# header\n203.0.113.7\n")

    monkeypatch.setattr("ipdb._sources._download.download_file", _serve_list)
    s.download()
    assert (tmp_path / "danmeuk_tor.txt").read_text() == "203.0.113.7\n"


def test_danmeuk_metadata_declared():
    """Phase 3 step 6 contract: in-file metadata, no central dict edits."""
    s = DanMeUkTorSource.__new__(DanMeUkTorSource)
    assert s.category == "asset"
    assert 0 < s.reliability <= 1
    assert s.authoritative_for == ()               # witness, not veto (official stays authority)
    assert s.stale_days == 1
