"""载入期基础设施噪声过滤(issue #183 / ADR 0008 8.8.8.8+114DNS 事故整改)。

Seam = 源生命周期公开面(rebuild → query),同 test_myip_ms 形制;覆盖:
- curated 集真源 = infra_services._DATA 单址集(勿复制第二真源、勿查可能
  纪元落后的 LMDB——勘察 §4 判例:本地 infra_services LMDB 落后 csv);
- 宁少算:仅排除对 curated 单址的精确指控,含 infra IP 的更大 CIDR 不排;
- 证据永不灭失:数据文件零改写,排除只发生在载入(rebuild)面;
  IP_RADAR_INFRA_NOISE_FILTER=0 重建即复原原摄取;
- 排除留痕:计数 + 被排条目进 rebuild 日志;
- 四事故源声明 infra_noise_filter=True(myip_ms/ziyadnz/cps_collected_iocs
  + tweetfeed 2026-10-29 人裁接入);基类默认 False(显式 opt-in,
  不是全局行为变更)。harvest 车道(Source 基类)与 IpListSource/CsvSource
  车道同款接线。
"""
import ipaddress
import logging
from pathlib import Path

from ipdb._sources._base import CsvSource, IpListSource

ENV_SWITCH = "IP_RADAR_INFRA_NOISE_FILTER"


class _ListSrc(IpListSource):
    name = "fake_noise_list"
    url = "https://example.com/f.txt"
    filename = "f.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    reliability = 0.55
    infra_noise_filter = True


class _CsvSrc(CsvSource):
    name = "fake_noise_csv"
    url = "https://example.com/f.csv"
    filename = "f.csv"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    reliability = 0.55
    skip_lines = 1
    infra_noise_filter = True

    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 2:
            return None
        return {"_ip": row[0].strip(),
                "classification_type": self.classification_type,
                "verdict": self.verdict,
                "reliability": self.reliability}


def test_curated_set_pins_incident_ips():
    from ipdb._sources._infra_filter import curated_infra_addresses
    nets = curated_infra_addresses()
    assert ipaddress.ip_network("8.8.8.8") in nets          # 事故 IP ①
    assert ipaddress.ip_network("114.114.114.114") in nets  # 事故 IP ②
    assert ipaddress.ip_network("223.5.5.5") in nets
    assert ipaddress.ip_network("2606:4700:4700::1111") in nets  # v6 同集
    assert ipaddress.ip_network("203.0.113.7") not in nets  # 文档段非 infra


def test_only_exact_single_address_is_infra_noise():
    from ipdb._sources._infra_filter import is_infra_noise
    assert is_infra_noise(ipaddress.ip_network("8.8.8.8"))
    assert is_infra_noise(ipaddress.ip_network("8.8.8.8/32"))
    assert is_infra_noise(ipaddress.ip_network("114.114.114.114"))
    # 宁少算:更大的 CIDR 是不同断言(不是对 curated 单址的精确指控),不排
    assert not is_infra_noise(ipaddress.ip_network("8.8.8.0/24"))
    assert not is_infra_noise(ipaddress.ip_network("0.0.0.0/0"))
    assert not is_infra_noise(ipaddress.ip_network("198.51.100.1"))


def test_env_switch_off_disables_filter(monkeypatch):
    from ipdb._sources import _infra_filter as f
    assert f.filter_enabled() is True            # 默认开(整改即生效)
    monkeypatch.setenv(ENV_SWITCH, "0")
    assert f.filter_enabled() is False
    monkeypatch.setenv(ENV_SWITCH, "false")
    assert f.filter_enabled() is False
    monkeypatch.setenv(ENV_SWITCH, "1")
    assert f.filter_enabled() is True


def test_iplist_rebuild_excludes_and_logs(tmp_path, caplog):
    (tmp_path / "f.txt").write_text("8.8.8.8\n203.0.113.7\n")
    s = _ListSrc(data_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="ipdb._sources._infra_filter"):
        assert s.rebuild() == 1                  # 8.8.8.8 载入面被排,仅剩 1 键
    assert not s.query("8.8.8.8")                # 事故 IP 不再是证据
    assert s.query("203.0.113.7")                # 非 infra 指控原样保留
    log = [r for r in caplog.records
           if "infra noise filter" in r.getMessage()]
    assert len(log) == 1
    msg = log[0].getMessage()
    assert "fake_noise_list" in msg and "excluded 1" in msg
    assert "8.8.8.8/32" in msg                   # 被排条目明文留痕


def test_filter_off_rebuild_restores_original_ingest(
        tmp_path, monkeypatch):
    """关过滤重建 = 原样回算复原(证据永不灭失:数据文件从未被改写)。
    mtime 显式后移防族级增量把同文件重建判成已收敛而跳过(既有判例同款)。"""
    import os
    import time
    raw = tmp_path / "f.txt"
    raw.write_text("8.8.8.8\n203.0.113.7\n")
    s = _ListSrc(data_dir=tmp_path)
    assert s.rebuild() == 1
    assert not s.query("8.8.8.8")
    monkeypatch.setenv(ENV_SWITCH, "0")
    fut = time.time() + 10
    os.utime(raw, (fut, fut))
    assert s.rebuild() == 2
    assert s.query("8.8.8.8")                    # 复原


def test_csv_rebuild_excludes_and_logs(tmp_path, caplog):
    (tmp_path / "f.csv").write_text(
        "ip,note\n114.114.114.114,x\n203.0.113.8,y\n")
    s = _CsvSrc(data_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="ipdb._sources._infra_filter"):
        assert s.rebuild() == 1
    assert not s.query("114.114.114.114")
    assert s.query("203.0.113.8")
    assert any("114.114.114.114/32" in r.getMessage()
               for r in caplog.records)


def test_off_by_default_for_undeclaring_sources(tmp_path):
    """基类默认 False:过滤是事故源显式 opt-in,未声明源行为零变化。"""

    class Plain(IpListSource):
        name = "plain"
        url = "https://example.com/p.txt"
        filename = "p.txt"
        fields = ("is_malicious",)
        classification_type = "blacklist"
        verdict = "malicious"

    assert IpListSource.infra_noise_filter is False
    assert getattr(Plain, "infra_noise_filter", False) is False
    (tmp_path / "p.txt").write_text("8.8.8.8\n203.0.113.7\n")
    s = Plain(data_dir=tmp_path)
    assert s.rebuild() == 2                      # 无排除
    assert s.query("8.8.8.8")


def test_incident_sources_declare_filter():
    from ipdb._sources.cps_collected_iocs import CpsCollectedIocsSource
    from ipdb._sources.myip_ms import MyipMsSource
    from ipdb._sources.tweetfeed import TweetFeedSource
    from ipdb._sources.ziyadnz import ZiyadnzSource
    for cls in (MyipMsSource, ZiyadnzSource, CpsCollectedIocsSource,
                TweetFeedSource):
        assert cls.infra_noise_filter is True, cls.__name__


def test_tweetfeed_harvest_rebuild_excludes_and_logs(tmp_path, caplog):
    """harvest 车道(Source 基类)同款排除:tweetfeed 2026-10-29 人裁接入,
    样本 = 实测误列行原型(skocherhan 单推 223.5.5.5,空 tag → other)。"""
    from ipdb._sources.tweetfeed import TweetFeedSource
    raw = tmp_path / "tweetfeed.csv"
    raw.write_text(
        "2026-02-09 13:35:39,skocherhan,ip,223.5.5.5,,"
        "https://x.com/skocherhan/status/2020854107163037900\n"
        "2026-02-09 13:36:00,r2,ip,203.0.113.9,#C2,https://x.com/s/2\n")
    s = TweetFeedSource(data_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="ipdb._sources._infra_filter"):
        assert s.rebuild() == 1              # 223.5.5.5 载入面被排,仅剩 1 键
    assert not s.query("223.5.5.5")           # curated 单址不进指控
    assert s.query("203.0.113.9")             # 非 curated 指控原样保留
    log = [r for r in caplog.records
           if "infra noise filter" in r.getMessage()]
    assert len(log) == 1
    msg = log[0].getMessage()
    assert "tweetfeed" in msg and "excluded 1" in msg
    assert "223.5.5.5/32" in msg               # 被排条目明文留痕
    assert raw.read_text().count("223.5.5.5") == 1   # 原始件零改写


def test_tweetfeed_harvest_filter_off_rebuild_restores(
        tmp_path, monkeypatch):
    """关过滤重建 = 原样回算复原(证据永不灭失)。mtime 显式后移防族级
    增量把同文件重建判成已收敛而跳过(test_filter_off_rebuild_restores_
    original_ingest 判例同款)。"""
    import os
    import time
    from ipdb._sources.tweetfeed import TweetFeedSource
    raw = tmp_path / "tweetfeed.csv"
    raw.write_text(
        "2026-02-09 13:35:39,skocherhan,ip,223.5.5.5,,"
        "https://x.com/skocherhan/status/2020854107163037900\n")
    s = TweetFeedSource(data_dir=tmp_path)
    assert s.rebuild() == 0                    # 唯一行被排 → 0 键
    assert not s.query("223.5.5.5")
    monkeypatch.setenv(ENV_SWITCH, "0")
    fut = time.time() + 10
    os.utime(raw, (fut, fut))
    assert s.rebuild() == 1
    rec = s.query("223.5.5.5")[0]
    assert rec["extra"]["reporter"] == "skocherhan"   # 指控面完整复原


def test_off_by_default_for_undeclaring_harvest_sources(tmp_path):
    """Source(harvest 车道)基类默认 False:未声明源行为零变化。"""
    from ipdb._evidence import Evidence
    from ipdb._source_base import Source

    class HarvestPlain(Source):
        name = "plain_harvest"
        url = "https://example.com/p.csv"
        filename = "p.csv"
        fields = ("is_malicious",)

        def harvest(self):
            yield "8.8.8.8", Evidence(classification_type="blacklist",
                                       verdict="malicious",
                                       reliability=0.55)

    assert Source.infra_noise_filter is False
    assert getattr(HarvestPlain, "infra_noise_filter", False) is False
    (tmp_path / "p.csv").write_text("8.8.8.8\n")
    s = HarvestPlain(data_dir=tmp_path)
    assert s.rebuild() == 1                    # 无排除
    assert s.query("8.8.8.8")
