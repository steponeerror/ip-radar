"""Tests for IpListSource base class behavior."""
import tempfile
from pathlib import Path
from ipdb._sources._base import IpListSource


class TestIpListSource:
    def test_parse_raw_strips_comments(self):
        class TestSource(IpListSource):
            name = "test"
            url = "https://example.com/test.txt"
            filename = "test.txt"
            fields = ("is_test",)

        src = TestSource(data_dir=Path("/tmp"))
        raw = b"1.2.3.4\n# comment\n5.6.7.0/24\n"
        entries = src.parse_raw(raw)
        assert entries == ["1.2.3.4", "5.6.7.0/24"]

    def test_get_insert_data_default(self):
        class TestSource(IpListSource):
            name = "test"
            url = "https://example.com/test.txt"
            filename = "test.txt"
            fields = ("is_malicious",)

        src = TestSource(data_dir=Path("/tmp"))
        data = src.get_insert_data()
        assert data == {"is_malicious": True}

    def test_load_strips_inline_comments(self, tmp_path):
        # spamhaus DROP format: "CIDR ; SBLxxxx" — inline comment after CIDR.
        # Must load all CIDRs/IPs, not silently drop them.
        class SpamhausLike(IpListSource):
            name = "spamhaus_like"
            url = "https://example.com/drop.txt"
            filename = "drop.txt"
            fields = ("is_malicious",)

        (tmp_path / "drop.txt").write_text(
            "; header comment line\n"
            "1.10.16.0/20 ; SBL256894\n"
            "1.2.3.4\n"
            "5.6.7.0/24 ; SBL000001\n"
            "\n"
        )
        src = SpamhausLike(data_dir=tmp_path)
        count = src.rebuild()

        assert count == 3
        assert src.query("1.10.16.5") == [{"is_malicious": True}]
        assert src.query("5.6.7.1") == [{"is_malicious": True}]
        assert src.query("9.9.9.9") == {}


def test_get_insert_data_with_classification_type(tmp_path):
    class TypedSource(IpListSource):
        name = "typed"
        url = "https://example.com/list.txt"
        filename = "list.txt"
        fields = ("is_malicious",)
        classification_type = "blacklist"
        verdict = "malicious"

    src = TypedSource(data_dir=tmp_path)
    data = src.get_insert_data()
    assert data["classification_type"] == "blacklist"
    assert data["verdict"] == "malicious"
    assert "native_type" not in (data.get("extra") or {})  # retired (Plan B Task 1)


def test_get_insert_data_without_classification_type_unchanged():
    class LegacySource(IpListSource):
        name = "legacy"
        url = "https://example.com/legacy.txt"
        filename = "legacy.txt"
        fields = ("is_legacy",)

    src = LegacySource(data_dir=Path("/tmp"))
    data = src.get_insert_data()
    assert "extra" not in data
    assert data == {"is_legacy": True}


# ── download 失败契约(A1/Task 3 except-unlink 重构)──


class _Simple(IpListSource):
    name = "simple"
    url = "https://example.com/simple.txt"
    filename = "simple.txt"
    fields = ("is_malicious",)


def _serve_bytes(body: bytes):
    """模拟 download_file 落盘契约:直接把 body 写到给定 dest(scratch)。"""
    def _fake(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(body)
    return _fake


def test_download_parse_failure_keeps_old_file_and_cleans_scratch(
        tmp_path, monkeypatch):
    """解析失败(零 entries):旧 entries 文件字节级完好(旧实现 except
    分支 unlink 把刚顶掉旧文件的好证据删光)、scratch(.dl/.dl.tmp)无
    残留、RuntimeError 信号保留。"""
    import pytest
    old = b"1.2.3.0/24\n5.6.7.0/24\n"
    (tmp_path / "simple.txt").write_bytes(old)
    src = _Simple(data_dir=tmp_path)
    monkeypatch.setattr("ipdb._sources._download.download_file",
                        _serve_bytes(b"# only a comment line\n"))
    with pytest.raises(RuntimeError, match="No entries parsed"):
        src.download()
    assert (tmp_path / "simple.txt").read_bytes() == old
    assert not (tmp_path / "simple.txt.dl").exists()
    assert not (tmp_path / "simple.txt.dl.tmp").exists()


def test_download_parse_crash_keeps_old_file(tmp_path, monkeypatch):
    """parse_raw 自身抛异常(如解码/格式炸):同契约 — _path 不被触碰。"""
    import pytest

    class _BadParse(_Simple):
        def parse_raw(self, raw):
            raise ValueError("bad format")

    old = b"1.2.3.0/24\n"
    (tmp_path / "simple.txt").write_bytes(old)
    src = _BadParse(data_dir=tmp_path)
    monkeypatch.setattr("ipdb._sources._download.download_file",
                        _serve_bytes(b"garbage"))
    with pytest.raises(ValueError, match="bad format"):
        src.download()
    assert (tmp_path / "simple.txt").read_bytes() == old
    assert not (tmp_path / "simple.txt.dl").exists()


def test_download_empty_body_keeps_old_file(tmp_path, monkeypatch):
    """空 body:RuntimeError 信号保留,旧文件字节级完好,scratch 清理。"""
    import pytest
    old = b"1.2.3.0/24\n"
    (tmp_path / "simple.txt").write_bytes(old)
    src = _Simple(data_dir=tmp_path)
    monkeypatch.setattr("ipdb._sources._download.download_file",
                        _serve_bytes(b"  \n\t\n"))
    with pytest.raises(RuntimeError, match="Empty response"):
        src.download()
    assert (tmp_path / "simple.txt").read_bytes() == old
    assert not (tmp_path / "simple.txt.dl").exists()


def test_download_success_installs_entries_and_leaves_no_scratch(
        tmp_path, monkeypatch):
    """成功路径行为不变(无损红线):最终内容 = 解析后 entries(+尾行),
    scratch 不残留 — 与旧实现产物字节一致。"""
    src = _Simple(data_dir=tmp_path)
    monkeypatch.setattr("ipdb._sources._download.download_file",
                        _serve_bytes(b"# header\n1.2.3.0/24\n\n5.6.7.0/24\n"))
    src.download()
    assert (tmp_path / "simple.txt").read_bytes() == b"1.2.3.0/24\n5.6.7.0/24\n"
    assert not (tmp_path / "simple.txt.dl").exists()
    assert src.last_partial_failure == []       # 基类接线默认值在位


def test_load_pure_mmap_does_not_rebuild(tmp_path, monkeypatch):
    """load() 纯 mmap:有 LMDB ptr 就开 env,没有则 _reader=None。不触发任何 harvest。"""
    from ipdb._source_base import Source
    from ipdb._sources._lmdb import rebuild_lmdb
    from ipdb._evidence import Evidence

    class _S(Source):
        name = "t"; filename = "t.txt"; fields = ("is_x",)
        single_evidence = True
        harvest_calls = 0
        def harvest(self):
            _S.harvest_calls += 1
            yield "1.2.3.0/24", Evidence(verdict="malicious")

    s = _S(tmp_path)
    # 预置一个已建库(双 buffer 的"旧 epoch"场景);立即 close 避免同进程双开
    rebuild_lmdb([("9.9.9.0/24", [{"k": "v"}])], tmp_path / "t.txt.lmdb",
                 reader_setter=lambda e: e.close())

    n = s.load()
    assert n == 1
    assert s.query("9.9.9.9") == [{"k": "v"}]
    assert _S.harvest_calls == 0            # load 不重建,不调 harvest

    s._reader.close()


def test_load_no_mmdb_returns_zero(tmp_path):
    """没有 mmdb 文件,load 返回 0,_reader=None。"""
    from ipdb._source_base import Source
    from ipdb._evidence import Evidence
    class _S(Source):
        name = "t"; filename = "t.txt"; fields = ("is_x",)
        single_evidence = True
        def harvest(self):
            yield "1.2.3.0/24", Evidence(verdict="malicious")
    s = _S(tmp_path)
    assert s.load() == 0
    assert s._reader is None
    assert s.query("1.2.3.4") == {}


def test_rebuild_writes_mmdb_and_swaps_reader(tmp_path):
    """rebuild() 调 rebuild_lmdb,写出新 epoch + ptr + count + cov,reader 可查新数据。"""
    from ipdb._source_base import Source
    from ipdb._evidence import Evidence
    class _S(Source):
        name = "t"; filename = "t.txt"; fields = ("is_x",)
        single_evidence = True
        def harvest(self):
            yield "5.6.7.0/24", Evidence(classification_type="proxy", verdict="suspicious")

    s = _S(tmp_path)
    (tmp_path / "t.txt").write_text("placeholder")  # raw 存在,触发 harvest
    n = s.rebuild()
    assert n == 1
    assert (tmp_path / "t.txt.lmdb.ptr").exists()
    assert (tmp_path / "t.txt.lmdb.count").read_text() == "1"
    assert int((tmp_path / "t.txt.lmdb.cov").read_text()) == 256
    assert s.query("5.6.7.8") is not None   # 新 reader 可查
    s._reader.close()


def test_iplistsource_rebuild_accumulates(tmp_path):
    """IpListSource.rebuild: 从 raw txt 读 CIDR,写 mmdb,可查。"""
    from ipdb._sources._base import IpListSource
    class _S(IpListSource):
        name = "t"; filename = "t.txt"; fields = ("is_x",)
        def get_insert_data(self):
            return {"is_x": True}
    s = _S(tmp_path)
    (tmp_path / "t.txt").write_text("1.2.3.0/24\n5.6.7.0/24\n")
    n = s.rebuild()
    assert n == 2
    assert s.query("1.2.3.4") == [{"is_x": True}]
    s._reader.close()


def test_csvsource_rebuild_dedup(tmp_path):
    """CsvSource.rebuild: CSV 行去重后写 mmdb。"""
    from ipdb._sources._base import CsvSource
    class _S(CsvSource):
        name = "t"; filename = "t.csv"; fields = ("is_x",)
        def parse_row(self, row):
            return {"_ip": row[0], "is_x": True}
    s = _S(tmp_path)
    (tmp_path / "t.csv").write_text("1.2.3.4\n1.2.3.4\n5.6.7.8\n")
    n = s.rebuild()
    assert n == 2  # 1.2.3.4 去重
    s._reader.close()


def test_iplistsource_load_pure_mmap(tmp_path):
    """IpListSource.load 不重建。"""
    from ipdb._sources._base import IpListSource
    from ipdb._sources._lmdb import rebuild_lmdb
    class _S(IpListSource):
        name = "t"; filename = "t.txt"; fields = ("is_x",)
        def get_insert_data(self):
            return {"is_x": True}
    s = _S(tmp_path)
    # 预置一个已建库(立即 close 避免同进程双开)
    rebuild_lmdb([("9.9.9.0/24", [{"is_x": True}])], tmp_path / "t.txt.lmdb",
                 reader_setter=lambda e: e.close())
    assert s.load() == 1
    assert s.query("9.9.9.9") == [{"is_x": True}]
    s._reader.close()


def test_query_tolerates_closed_reader(tmp_path, monkeypatch):
    """query 撞到被 close 的 env 时,读 ptr 重开重试,不抛。"""
    from ipdb._source_base import Source
    from ipdb._sources._lmdb import rebuild_lmdb
    class _S(Source):
        name = "t"; filename = "t.txt"; fields = ("is_x",)
        single_evidence = True
        def harvest(self):
            yield from []
    s = _S(tmp_path)
    rebuild_lmdb([("9.9.9.0/24", {"k": "v"})], tmp_path / "t.txt.lmdb",
                 reader_setter=lambda e: e.close())
    s.load()
    s._reader.close()                       # 模拟 rebuild 期间被 close
    # query 应容错重开
    assert s.query("9.9.9.9") == {"k": "v"}
    s._reader.close()
