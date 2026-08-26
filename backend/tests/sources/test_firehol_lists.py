"""firehol 多 netset 下载:部分失败容忍,全部失败必须 raise(防空库清库)。"""
from unittest.mock import patch

import pytest

from ipdb._sources.firehol import FireholBlocklistSource


def test_all_lists_failed_raises(tmp_path):
    src = FireholBlocklistSource(tmp_path)
    with patch("ipdb._sources.firehol.download_file",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            src.download()


def test_partial_failure_tolerated(tmp_path):
    src = FireholBlocklistSource(tmp_path, selected_lists=["firehol_level1",
                                                           "firehol_level2"])
    real = {"firehol_level1": b"1.2.3.0/24\n"}

    def fake_dl(url, dest, token=None, headers=None, **kw):
        name = url.rsplit("/", 1)[-1].removesuffix(".netset")
        if name in real:
            from pathlib import Path
            Path(dest).write_bytes(real[name])
        else:
            raise RuntimeError("network down")

    with patch("ipdb._sources.firehol.download_file", side_effect=fake_dl):
        src.download()          # level2 失败容忍,不 raise
    assert (src._path / "firehol_level1.netset").exists()
    assert not (src._path / "firehol_level2.netset").exists()
