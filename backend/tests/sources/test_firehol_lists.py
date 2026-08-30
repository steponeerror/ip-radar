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


# ── per-list classification(2026-08-30 拆子列表)──

def _write(tmp_path, name, text):
    d = tmp_path / "firehol"
    d.mkdir(exist_ok=True)
    (d / f"{name}.netset").write_text(text)


def test_default_lists_cover_five_sublists(tmp_path):
    src = FireholBlocklistSource(tmp_path)
    assert src._lists == ["firehol_level1", "firehol_level2",
                          "firehol_abusers_30d", "firehol_proxies",
                          "firehol_webserver"]


def test_per_list_classification_and_verdict(tmp_path):
    """子列表各投分类(对齐直接源同轴):spam/informational(sfs 轴)、
    proxy/suspicious+is_proxy(代理源轴)、blacklist/malicious(L1/L2 及
    未知列表回退)。"""
    lists = {
        "firehol_level1": "1.0.0.0/24\n",
        "firehol_abusers_30d": "2.0.0.0/24\n",
        "firehol_proxies": "3.0.0.0/24\n",
        "firehol_webserver": "4.0.0.0/24\n",
        "unknown_netset": "5.0.0.0/24\n",
    }
    for name, text in lists.items():
        _write(tmp_path, name, text)
    src = FireholBlocklistSource(tmp_path, selected_lists=list(lists))
    src.rebuild()
    l1 = src.query("1.0.0.1")[0]
    assert (l1["classification_type"], l1["verdict"]) == ("blacklist", "malicious")
    ab = src.query("2.0.0.1")[0]
    assert (ab["classification_type"], ab["verdict"]) == ("spam", "informational")
    px = src.query("3.0.0.1")[0]
    assert (px["classification_type"], px["verdict"]) == ("proxy", "suspicious")
    assert px["is_proxy"] is True
    ws = src.query("4.0.0.1")[0]
    assert (ws["classification_type"], ws["verdict"]) == ("spam", "informational")
    unk = src.query("5.0.0.1")[0]
    assert (unk["classification_type"], unk["verdict"]) == ("blacklist", "malicious")


def test_same_cidr_different_classification_keeps_both(tmp_path):
    """同 CIDR 异分类(abusers∩proxies 实测 6.9k):两条独立证据共存
    (convention 3),tags 各自带归属。"""
    _write(tmp_path, "firehol_abusers_30d", "10.0.0.0/24\n")
    _write(tmp_path, "firehol_proxies", "10.0.0.0/24\n")
    src = FireholBlocklistSource(tmp_path, selected_lists=[
        "firehol_abusers_30d", "firehol_proxies"])
    n = src.rebuild()
    assert n == 1
    recs = src.query("10.0.0.5")
    assert len(recs) == 2
    by_cls = {r["classification_type"]: r for r in recs}
    assert set(by_cls) == {"spam", "proxy"}
    assert by_cls["spam"]["tags"] == ["firehol_abusers_30d"]
    assert by_cls["proxy"]["tags"] == ["firehol_proxies"]


def test_same_cidr_same_classification_merges_tags(tmp_path):
    """同 CIDR 同分类(abusers∩webserver,均 spam):合并 tags 一条证据
    ——推广田 L1∩L2 合并语义。"""
    _write(tmp_path, "firehol_abusers_30d", "10.0.0.0/24\n")
    _write(tmp_path, "firehol_webserver", "10.0.0.0/24\n")
    src = FireholBlocklistSource(tmp_path, selected_lists=[
        "firehol_abusers_30d", "firehol_webserver"])
    n = src.rebuild()
    assert n == 1
    recs = src.query("10.0.0.5")
    assert len(recs) == 1
    assert recs[0]["tags"] == ["firehol_abusers_30d", "firehol_webserver"]
