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


def test_all_lists_failed_raises_even_with_old_files(tmp_path):
    """全挂判据 = 本轮失败计数,非文件存在性(SA-F1 语义修正;firehol 同名
    测试同款):旧实现下旧文件还在时全挂会静默不 raise,源停在旧证据且无信号。"""
    import pytest
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "mail"])
    src._path.mkdir(parents=True)
    (src._path / "ssh.txt").write_text("1.2.3.4\n")
    with patch("ipdb._sources.blocklist_de.download_file",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            src.download()
    assert (src._path / "ssh.txt").read_text() == "1.2.3.4\n"


def test_partial_failure_keeps_old_file_and_updates_rest(tmp_path):
    """SA-F1(A1/Task 3,firehol 同款):单列表抓取失败 → 旧 txt 字节级保留、
    其余列表更新、失败名记 last_partial_failure、scratch 无残留。锚(all)
    健康故其余照常落地。"""
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "mail", "all"])
    src._path.mkdir(parents=True)
    old = src._path / "mail.txt"
    old.write_text("5.6.7.8\n")

    def fake_dl(url, dest, token=None, headers=None, **kw):
        if url.endswith("/mail.txt"):
            raise RuntimeError("boom")
        Path(dest).write_bytes(b"1.2.3.4\n")

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        src.download()          # mail 失败容忍,不 raise
    assert (src._path / "ssh.txt").read_bytes() == b"1.2.3.4\n"
    assert (src._path / "all.txt").read_bytes() == b"1.2.3.4\n"
    assert old.read_text() == "5.6.7.8\n"             # 旧文件保留
    assert src.last_partial_failure == ["mail"]
    assert not (src._path / "mail.txt.dl").exists()


def test_legit_empty_sublist_lands_zero_byte_file(tmp_path):
    """合法空(GLOSSARY,判例 ircbot 2026-10-15):bare-IP 列表无头部
    格式,200 空 body = 发布方声明「当前无此类条目」→ 0 字节文件照落
    (下一 epoch 出清旧条目)、不计失败。"""
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "ircbot", "all"])
    src._path.mkdir(parents=True)
    (src._path / "ircbot.txt").write_text("6.6.6.6\n")  # 旧条目待出清

    def fake_dl(url, dest, token=None, headers=None, **kw):
        if url.endswith("/ircbot.txt"):
            Path(dest).write_bytes(b"")
        elif url.endswith("/ssh.txt"):
            Path(dest).write_bytes(b"1.2.3.4\n")
        else:                                             # all 活性锚健康
            Path(dest).write_bytes(b"1.2.3.4\n6.6.6.6\n")

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        src.download()
    assert (src._path / "ircbot.txt").read_bytes() == b""  # 空文件落地
    assert (src._path / "ssh.txt").read_bytes() == b"1.2.3.4\n"
    assert src.last_partial_failure == []


def test_anchor_empty_replaces_nothing(tmp_path):
    """锚空(GLOSSARY 活性锚):all.txt 200 空 → 本轮零替换(旧文件
    mtime/内容不动,fail-closed 防灾难性全空清库)、"all" 记真失败走
    部分失败梯,不 raise。"""
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "all"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh.txt"
    old.write_text("1.2.3.4\n")
    before = old.stat().st_mtime_ns

    def fake_dl(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(b"" if url.endswith("/all.txt") else b"5.6.7.8\n")

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        src.download()          # 锚空不 raise,经告警侧暴露
    assert old.read_bytes() == b"1.2.3.4\n"           # 零替换
    assert old.stat().st_mtime_ns == before
    assert src.last_partial_failure == ["all"]
    assert not (src._path / "ssh.txt.dl").exists()    # landed scratch 全清
    assert not (src._path / "all.txt.dl").exists()


def test_anchor_fetch_failure_replaces_nothing(tmp_path):
    """锚挂(404/超时):其余子列表健康也零替换("all" 在
    last_partial_failure)—— 锚在,出版方存活才可信,单列表失败语义
    (旧文件保留)对锚同样成立。"""
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "all"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh.txt"
    old.write_text("1.2.3.4\n")
    before = old.stat().st_mtime_ns

    def fake_dl(url, dest, token=None, headers=None, **kw):
        if url.endswith("/all.txt"):
            raise RuntimeError("404")
        Path(dest).write_bytes(b"5.6.7.8\n")

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        src.download()          # 不 raise:锚挂走部分失败梯
    assert old.read_bytes() == b"1.2.3.4\n"           # 零替换
    assert old.stat().st_mtime_ns == before
    assert src.last_partial_failure == ["all"]
    assert not (src._path / "ssh.txt.dl").exists()


def test_all_empty_no_raise_zero_replace(tmp_path):
    """全空断供(all 空 + 其余也空)= 锚空而非全挂:len(failed)=1 <
    列表数,不 raise;零替换 + "all" 记真失败,失败信号走告警侧而非
    RuntimeError。"""
    from unittest.mock import patch
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "all"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh.txt"
    old.write_text("1.2.3.4\n")

    def fake_dl(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(b"")

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        src.download()
    assert old.read_bytes() == b"1.2.3.4\n"           # 零替换
    assert src.last_partial_failure == ["all"]
    assert not (src._path / "ssh.txt.dl").exists()
    assert not (src._path / "all.txt.dl").exists()


def test_cancel_mid_download_leaves_no_scratch(tmp_path):
    """cancel 照旧 raise CancelledError;两阶段下已抓未裁决的 scratch
    必须清掉(等价保持现行逐列表 finally 清理语义),旧文件不动。"""
    import pytest
    from unittest.mock import patch
    from ipdb._sources._download import CancelToken, CancelledError
    from ipdb._sources.blocklist_de import BlocklistDeSource
    src = BlocklistDeSource(tmp_path, selected_lists=["ssh", "all"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh.txt"
    old.write_text("1.2.3.4\n")
    token = CancelToken()

    def fake_dl(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(b"5.6.7.8\n")
        token.cancel()                    # ssh 抓完即取消,all 轮头 raise

    with patch("ipdb._sources.blocklist_de.download_file", side_effect=fake_dl):
        with pytest.raises(CancelledError):
            src.download(token=token)
    assert old.read_text() == "1.2.3.4\n"
    assert not (src._path / "ssh.txt.dl").exists()
