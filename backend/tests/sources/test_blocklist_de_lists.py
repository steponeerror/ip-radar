"""blocklist.de 多列表源 — 目录布局 / 旧文件清理 / 部分状态。"""
from pathlib import Path

from ipdb._sources.blocklist_de import BlocklistDeSource


def test_directory_layout_and_partial_state(tmp_path: Path):
    d = tmp_path / "blocklist_de"
    d.mkdir()
    (d / "ssh.txt").write_text("1.2.3.4\n")
    s = BlocklistDeSource(data_dir=tmp_path)
    n = s.rebuild()
    assert n == 1
    assert s.query("1.2.3.4")[0]["classification_type"] == "brute-force"


def test_download_cleans_legacy_single_file(tmp_path: Path):
    """旧单文件 + sidecar 在 download() 时被清理（不留 feodo.csv 式孤儿）。"""
    legacy = tmp_path / "blocklist_de.txt"
    legacy.write_text("1.2.3.4\n")
    sidecar = tmp_path / "blocklist_de.txt.lmdb.1"
    sidecar.write_text("x")
    epoch_dir = tmp_path / "blocklist_de.txt.lmdb.2"   # LMDB epoch 目录形态
    epoch_dir.mkdir()
    (epoch_dir / "data.mdb").write_text("x")
    s = BlocklistDeSource(data_dir=tmp_path)
    s._path.mkdir(parents=True, exist_ok=True)
    s._cleanup_legacy()
    assert not legacy.exists()
    assert not sidecar.exists()
    assert not epoch_dir.exists()


def test_health_uses_max_mtime(tmp_path: Path):
    import time
    d = tmp_path / "blocklist_de"
    d.mkdir()
    (d / "ssh.txt").write_text("1.2.3.4\n")
    (d / "mail.txt").write_text("5.6.7.8\n")
    s = BlocklistDeSource(data_dir=tmp_path)
    h = s.health()
    assert h.loaded is False
    assert h.last_updated is not None


def test_all_lists_failed_raises(tmp_path):
    """全部 list 下载失败必须 raise(防空 rebuild 清库);见 firehol 同名测试。"""
    import pytest
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path)
    with patch("ipdb._sources.blocklist_de.download_file",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            src.download()


def test_partial_failure_keeps_old_file_and_updates_rest(tmp_path):
    """SA-F1(A1/Task 3,firehol 同款):单列表失败 → 旧 txt 字节级保留、
    其余列表更新、失败名记 last_partial_failure、scratch 无残留。"""
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "mail"])
    src._path.mkdir(parents=True)
    old = src._path / "mail.txt"
    old.write_text("5.6.7.8\n")

    def fake_dl(url, dest, token=None, headers=None, **kw):
        if url.endswith("/ssh.txt"):
            from pathlib import Path
            Path(dest).write_bytes(b"1.2.3.4\n")
        else:
            raise RuntimeError("boom")

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        src.download()          # mail 失败容忍,不 raise
    assert (src._path / "ssh.txt").read_bytes() == b"1.2.3.4\n"
    assert old.read_text() == "5.6.7.8\n"             # 旧文件保留
    assert src.last_partial_failure == ["mail"]
    assert not (src._path / "mail.txt.dl").exists()
