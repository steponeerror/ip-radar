# backend/test_cn_isp.py
"""cn_isp cross-file priority dedup (具体 ISP overrides '其他') + Source subclass."""
from pathlib import Path

from ipdb._sources.cn_isp import ChineseISPSource


def test_cn_isp_is_subclass_of_source():
    from ipdb._source_base import Source
    assert issubclass(ChineseISPSource, Source)


def test_cn_isp_specific_isp_wins_over_other(tmp_path: Path):
    # The same CIDR in both 中国电信 (chinatelecom) and 其他 (othernet) must
    # resolve to the specific ISP — '其他' is overridden, not duplicated.
    isp_dir = tmp_path / "isp"
    isp_dir.mkdir()
    (isp_dir / "chinatelecom.txt").write_text("1.0.0.0/24\n")
    (isp_dir / "othernet.txt").write_text("1.0.0.0/24\n")

    s = ChineseISPSource(data_dir=tmp_path)
    n = s.rebuild()
    assert n == 1, f"expected 1 deduped CIDR, got {n}"

    rec = s.query("1.0.0.5")
    assert "as_name" not in rec          # D6: region/ISP names never pollute org slot
    assert rec["country_code"] == "CN"
    assert rec["is_isp"] is True         # CN network → ISP badge
    assert rec["carrier"] == "中国电信"
    assert rec["ip_range"] == "1.0.0.0/24"

    # rebuild→load roundtrip: fresh instance must serve identical answers
    s._reader.close()   # LMDB 同进程禁止双开同一 epoch 目录
    s._reader6.close()  # v6 族同约定(T6):重建打开的 reader6 也要关
    s2 = ChineseISPSource(data_dir=tmp_path)
    assert s2.load() == 1
    assert s2.query("1.0.0.5") == rec


def test_cn_isp_hk_no_isp_badge(tmp_path: Path):
    isp_dir = tmp_path / "isp"
    isp_dir.mkdir()
    (isp_dir / "hk.txt").write_text("154.203.132.0/24\n")
    s = ChineseISPSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("154.203.132.81")
    assert rec["country_code"] == "HK"
    assert rec["is_isp"] is False        # D6: HK/MO/TW hosting IPs are not ISPs
    assert rec["carrier"] == "香港"
    assert "as_name" not in rec


def test_cn_isp_content_mtime_tracks_isp_dir(tmp_path: Path):
    """cn_isp 数据在 isp/ 子目录:_path 必须指向它,scheduler._read_mtime 才能
    种子/测 content_age(2026-10-03 线上误报根因:_path 从不存在 → age=None
    按无文件视为 ∞ → 恒报 stale 且成功刷新也测不到 mtime 变化、永不自愈)。"""
    from ipdb._scheduler import RefreshScheduler

    s = ChineseISPSource(data_dir=tmp_path)
    assert RefreshScheduler._read_mtime(s) is None       # 无任何文件 → None 语义不变

    isp = tmp_path / "isp"
    isp.mkdir()
    (isp / "chinatelecom.txt").write_text("1.0.0.0/24\n")
    old = tmp_path / "isp" / "old.txt"
    old.write_text("x\n")
    import os
    os.utime(old, (1000000, 1000000))   # 旧文件:证明取的是 max 而非目录/首个
    mtime = RefreshScheduler._read_mtime(s)
    assert mtime is not None
    assert mtime == max(isp.joinpath("chinatelecom.txt").stat().st_mtime,
                        isp.stat().st_mtime)   # 重写不改目录 mtime,必须取目录内最新文件


def test_all_isp_files_failed_raises(tmp_path):
    """全部 ISP 文件下载失败必须 raise(防空 rebuild 清库)。"""
    import pytest
    from unittest.mock import patch
    from ipdb._sources.cn_isp import ChineseISPSource
    src = ChineseISPSource(tmp_path)
    with patch("urllib.request.urlopen", side_effect=RuntimeError("net down")):
        with pytest.raises(RuntimeError):
            src.download()
