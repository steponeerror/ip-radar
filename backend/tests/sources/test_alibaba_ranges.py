"""alibaba cloud ranges — cloud-ip-ranges.com aggregator (IpListSource).

China-cloud coverage axis: joins aws/gcp/azure/oracle in the cloud
family (5th member). Publisher = cloud-ip-ranges.com, a third-party
aggregator of the official published ranges (license unstated —
user-approved for this non-commercial tool, 2026-09-28; NOT
publisher-self, hence reliability 0.75 vs the 0.95 official houses).
Observed 2026-09-28: 2,394 CIDRs (v4 2,148 / v6 246), zero exact
dupes, Last-Modified header advances daily 04:00 UTC — freshness
gate = header liveness (no in-file timestamps).
"""
from pathlib import Path

import pytest

from ipdb._sources.alibaba_ranges import AlibabaRangesSource

# Rails 应用可能的 200-HTML 错误/维护页(观测风险,非实弹):基类
# 空体/零解析行两道守卫都不放行它 → 复用 danmeuk 的内容守卫模式。
_ERROR_PAGE = (
    b"<!DOCTYPE html><html><body>"
    b"<h1>We're sorry, but something went wrong (500)</h1>"
    b"</body></html>\n"
)


def test_alibaba_rebuild_and_query_hit_miss(tmp_path: Path):
    f = tmp_path / "alibaba_ranges.txt"
    f.write_text(
        "# alibaba cloud ranges\n"
        "203.0.113.0/24\n"
        "203.0.113.128/25\n"          # 嵌套子网:该 feed 实况(父/子并存),同证据
        "198.51.100.0/24\n"
        "not-a-cidr\n"
        "2001:db8:1::/48\n"
    )
    s = AlibabaRangesSource(data_dir=tmp_path)
    n = s.rebuild()
    assert n == 3                                  # v4 CIDR 数;v6 行入并行族不计
    rec = s.query("203.0.113.55")[0]               # 网段内任意 IP 命中(嵌套走最长前缀)
    assert rec["service"] == "cloud"
    assert rec["is_hosting"] is True
    assert s.query("198.51.100.77")[0]["service"] == "cloud"
    assert s.query("2001:db8:1::9")[0]["service"] == "cloud"   # v6 族命中
    assert s.query("192.0.2.1") == {}              # miss → {}


def test_alibaba_get_insert_data_is_evidence_contract(tmp_path: Path):
    """get_insert_data() 必须与 aws/gcp 同款证据契约:service=cloud +
    is_hosting + native service 标签 + 空裁决(asset-only)。"""
    from ipdb._evidence import Evidence
    s = AlibabaRangesSource(data_dir=tmp_path)
    assert s.get_insert_data() == Evidence(
        service="cloud",
        is_hosting=True,
        native_types={"service": "Alibaba"},
        verdict="",                # asset-only; suppress "malicious" default
    ).to_dict()


def test_alibaba_fresh_instance_load(tmp_path: Path):
    """同 data_dir 新实例重开 env(convention 7 — 重建实例永不 load())。"""
    (tmp_path / "alibaba_ranges.txt").write_text("203.0.113.0/24\n")
    s = AlibabaRangesSource(data_dir=tmp_path)
    s.rebuild()
    if s._reader is not None:
        s._reader.close()
    if s._reader6 is not None:
        s._reader6.close()
    s2 = AlibabaRangesSource(data_dir=tmp_path)
    assert s2.load() == 1
    assert s2.query("203.0.113.7")[0]["service"] == "cloud"


def test_alibaba_download_rejects_html_error_page(tmp_path: Path, monkeypatch):
    """200-HTML 错误页(非空体、非零行)穿透基类守卫 → 垃圾换掉数据文件 →
    rebuild 提交空 env 静默清源。内容守卫必须拒且不碰既有文件。"""
    s = AlibabaRangesSource(data_dir=tmp_path)

    with pytest.raises(RuntimeError, match="no IP/CIDR lines"):
        s._validate_raw(_ERROR_PAGE)
    s._validate_raw(b"# x\n203.0.113.0/24\n2001:db8::/32\n")      # no raise

    def _serve(url, dest, token=None, **kw):
        dest.write_bytes(_ERROR_PAGE)               # 模拟 download_file 落盘契约

    good = "203.0.113.0/24\n198.51.100.0/24\n"
    (tmp_path / "alibaba_ranges.txt").write_text(good)
    monkeypatch.setattr("ipdb._sources._download.download_file", _serve)
    with pytest.raises(RuntimeError, match="no IP/CIDR lines"):
        s.download()
    assert (tmp_path / "alibaba_ranges.txt").read_text() == good   # 数据文件原样
    assert not (tmp_path / "alibaba_ranges.txt.dl").exists()       # scratch 已清理

    def _serve_list(url, dest, token=None, **kw):
        dest.write_bytes(b"# header\n203.0.113.0/24\n")

    monkeypatch.setattr("ipdb._sources._download.download_file", _serve_list)
    s.download()
    assert (tmp_path / "alibaba_ranges.txt").read_text() == "203.0.113.0/24\n"


def test_alibaba_metadata_declared():
    """Phase 3 step 6 contract: in-file metadata, no central dict edits."""
    s = AlibabaRangesSource.__new__(AlibabaRangesSource)
    assert s.category == "asset"
    assert 0 < s.reliability <= 1
    assert s.authoritative_for == ()               # aggregator, no veto anywhere
    assert s.stale_days == 7                       # 云网段缓变,对齐 aws/gcp
