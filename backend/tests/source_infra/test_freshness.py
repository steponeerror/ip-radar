"""#465 卡16:_freshness 单源点的判别测试(伞票 #451)。

只加有判别力的:算法被改坏时必须转红——
① freshness 三分支(文件齐 / 缺一个 / 全缺);② feed_health 每家停更线
不同(同一家 14 天 vs 7 天,同一时刻一个过期一个没过期);③ 目录型源
覆写 _data_files 后 health() 看子文件不看目录(目录比文件旧)。
"""
import os
import time

from ipdb._sources import _freshness


def test_freshness_all_files_present_takes_newest(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("x")
    b.write_text("x")
    now = time.time()
    t_old, t_fresh = now - 100, now - 10
    os.utime(a, (t_old, t_old))
    os.utime(b, (t_fresh, t_fresh))
    last_updated, is_stale = _freshness.freshness(
        [a, b], stale_days=1, now=now)
    assert last_updated == time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_fresh))
    assert is_stale is False


def test_freshness_one_file_missing_uses_remaining(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("x")
    now = time.time()
    t_old = now - 2 * 86400                # 超 stale_days=1 → stale
    os.utime(a, (t_old, t_old))
    last_updated, is_stale = _freshness.freshness(
        [a, tmp_path / "ghost.txt"], stale_days=1, now=now)
    assert last_updated == time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_old))
    assert is_stale is True


def test_freshness_all_files_missing(tmp_path):
    last_updated, is_stale = _freshness.freshness(
        [tmp_path / "ghost.txt"], stale_days=1, now=1_700_000_000.0)
    assert last_updated is None
    assert is_stale is True


def test_feed_health_per_feed_stale_lines(tmp_path):
    """每家停更线不同:同一时刻、同一 mtime,14 天线未过期、7 天线过期
    (cloud_ranges _FEEDS 表形状:阈值逐家查表,health 不硬编码)。"""
    now = time.time()
    azure, aws = tmp_path / "azure.txt", tmp_path / "aws.txt"
    t_age = now - 10 * 86400               # 两家都是 10 天前
    for p in (azure, aws):
        p.write_text("x")
        os.utime(p, (t_age, t_age))
    feeds = _freshness.feed_health(
        [("Azure", azure, 14), ("AWS", aws, 7)], now=now)
    by_name = {f.name: f for f in feeds}
    assert by_name["Azure"].is_stale is False      # 10 天 < 14 天线
    assert by_name["AWS"].is_stale is True         # 10 天 > 7 天线
    assert (by_name["Azure"].last_updated
            == by_name["AWS"].last_updated)


def test_feed_health_missing_file(tmp_path):
    feeds = _freshness.feed_health(
        [("Ghost", tmp_path / "ghost.txt", 7)], now=1_700_000_000.0)
    assert feeds[0].last_updated is None
    assert feeds[0].is_stale is True


def test_dir_source_health_reads_child_files(tmp_path):
    """③ 目录型源覆写 _data_files 后,health() 看子文件不看目录:
    目录 mtime 停在 30 天前,最新子文件 1 小时前刚写(stale_days=1)——
    last_updated 取最新文件的 mtime,is_stale 由文件算出为 False。
    (回归三重判别:改看目录 / 取最小 / 任一退化都转红。)"""
    from ipdb._sources.blocklist_de import BlocklistDeSource
    d = tmp_path / "blocklist_de"
    d.mkdir(parents=True)
    now = time.time()
    fresh, older = d / "ssh.txt", d / "mail.txt"
    fresh.write_text("1.2.3.4\n")
    older.write_text("5.6.7.8\n")
    t_dir, t_older, t_fresh = now - 30 * 86400, now - 2 * 86400, now - 3600
    os.utime(older, (t_older, t_older))
    os.utime(fresh, (t_fresh, t_fresh))
    os.utime(d, (t_dir, t_dir))            # 目录比全部子文件旧
    h = BlocklistDeSource(data_dir=tmp_path).health()
    assert h.last_updated == time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_fresh))
    assert h.is_stale is False


def test_directory_sources_override_data_files():
    """#501:目录型源(数据文件是一个目录的源)必须各自覆写 _data_files(),
    否则更新账本的指纹会退回「目录内全部文件」的旧口径,把下载暂存件
    算进去。新增目录型源时在这里登记类名。"""
    from ipdb._sources._base import SourceBase
    from ipdb._sources import (blocklist_de, echelon, firehol, cn_isp,
                               rir_abuse, rir_delegated, cloud_ranges)

    classes = [
        blocklist_de.BlocklistDeSource, echelon.EchelonSource,
        firehol.FireholBlocklistSource, cn_isp.ChineseISPSource,
        rir_abuse.RirAbuseSource, rir_delegated.RirDelegatedSource,
        cloud_ranges.CloudRangesSource,
    ]
    for cls in classes:
        assert cls._data_files is not SourceBase._data_files, cls.__name__
