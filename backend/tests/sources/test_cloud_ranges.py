"""cloud_ranges — 五家云厂商融合源(数据面:harvest/rebuild/query)。

fixture 中间文件逐家镜像真实格式(aws/gcp/azure/oracle 官方 JSON、
alibaba CIDR-per-line 文本)落 tmp_path/cloud_ranges/,rebuild → query
round-trip 钉住:冻结 Evidence 形状、per-provider reliability、缺家文件
容忍、v6 双族路由、fixture 外 miss。断言写法移植自 test_alibaba_ranges.py
的 round-trip 用例(query 返回 evidence dict 列表,verdict="" 落库即省略)。
"""
import json
import os
import time
from pathlib import Path

import pytest

from ipdb._evidence import ASSET_SLOTS, Evidence
from ipdb._source_base import Source
from ipdb._types import AssetStatement
from ipdb._sources.cloud_ranges import (
    _ALIBABA_URL,
    _AWS_URL,
    _GCP_URL,
    _ORACLE_URL,
    _PAGE,
    CloudRangesSource,
    _FEEDS,
    _provider_by_file,
)

_DIR = "cloud_ranges"

# 测试网段,不同家不重叠;aws/gcp 各带 1 个 v6 前缀
_AWS = {
    "prefixes": [{"ip_prefix": "203.0.113.0/24"}],
    "ipv6_prefixes": [{"ipv6_prefix": "2001:db8:aaaa::/48"}],
}
_GCP = {
    "prefixes": [
        {"ipv4Prefix": "198.51.100.0/24"},
        {"ipv6Prefix": "2001:db8:bbbb::/48"},
    ],
}
# region tag 是 AzureCloud 的子集:不得被 harvest(旧 azure 守卫,双计防线)
_AZURE = {
    "values": [
        {"name": "AzureCloud",
         "properties": {"addressPrefixes": ["192.0.2.0/24"]}},
        {"name": "AzureCloud.WestEurope",
         "properties": {"addressPrefixes": ["192.0.2.128/25"]}},
    ],
}
_ORACLE = {
    "regions": [
        {"region": "us-ashburn-1", "cidrs": [{"cidr": "198.18.0.0/15"}]},
    ],
}
_ALIBABA = (
    "# alibaba cloud ranges\n"
    "203.0.114.0/24\n"
    "not-a-cidr\n"          # 守卫只要求 ≥1 行可解析;垃圾行由 parse 逐行跳过
    "2001:db8:cccc::/48\n"
)


def _write_all(tmp_path: Path) -> None:
    d = tmp_path / _DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "aws.json").write_text(json.dumps(_AWS))
    (d / "gcp.json").write_text(json.dumps(_GCP))
    (d / "azure.json").write_text(json.dumps(_AZURE))
    (d / "oracle.json").write_text(json.dumps(_ORACLE))
    (d / "alibaba.txt").write_text(_ALIBABA)


def _build(tmp_path: Path) -> CloudRangesSource:
    _write_all(tmp_path)
    s = CloudRangesSource(data_dir=tmp_path)
    n = s.rebuild()
    # v4 CIDR 数:每家 1 个(region tag 不入 = 5 而非 6);v6 行入并行族不计
    assert n == 5
    return s


def test_evidence_shape_frozen(tmp_path: Path):
    s = _build(tmp_path)
    rec = s.query("203.0.113.55")[0]        # AWS fixture 网段内任意 IP
    assert rec["service"] == "cloud"
    assert rec["is_hosting"] is True
    assert "verdict" not in rec             # verdict="" 落库即省略(cdn_edges 同款)
    assert rec["_native_types"] == {"service": "AWS"}
    assert rec["reliability"] == 0.95
    # 写入边界的 Evidence 冻结形状同样钉死(query 侧是它的落库投影)
    by_provider = {}
    cidrs_by_provider = {}
    for cidr, ev in CloudRangesSource(data_dir=tmp_path).harvest():
        provider = ev.native_types["service"]
        by_provider[provider] = ev
        cidrs_by_provider.setdefault(provider, []).append(cidr)
    assert by_provider["AWS"] == Evidence(
        service="cloud",
        is_hosting=True,
        native_types={"service": "AWS"},
        verdict="",                         # asset-only; suppress "malicious" default
        reliability=0.95,
    )
    # azure 只取 AzureCloud tag(region 子集 tag 不入,逐字移植的守卫)
    assert sorted(cidrs_by_provider["Azure"]) == ["192.0.2.0/24"]


def test_per_provider_reliability(tmp_path: Path):
    s = _build(tmp_path)
    assert s.query("203.0.114.7")[0]["reliability"] == 0.75    # Alibaba 聚合商
    assert s.query("203.0.113.55")[0]["reliability"] == 0.95   # 同库 AWS 共存
    assert s.query("203.0.114.7")[0]["_native_types"] == {"service": "Alibaba"}


def test_rebuild_tolerates_missing_provider_file(tmp_path: Path):
    _write_all(tmp_path)
    (tmp_path / _DIR / "azure.json").unlink()     # 缺一家(存量目录部分态)
    s = CloudRangesSource(data_dir=tmp_path)
    assert s.rebuild() > 0
    assert s.query("203.0.113.55")[0]["_native_types"] == {"service": "AWS"}
    assert s.query("198.51.100.7")[0]["_native_types"] == {"service": "Google"}
    assert s.query("192.0.2.55") == {}            # 缺的那家 miss


def test_v6_prefixes_route_to_v6_family(tmp_path: Path):
    s = _build(tmp_path)
    r = s.query("2001:db8:aaaa::9")[0]            # v6 走 _query6 并行族
    assert r["service"] == "cloud"
    assert r["_native_types"] == {"service": "AWS"}
    assert s.query("2001:db8:bbbb::1")[0]["_native_types"] == {"service": "Google"}


def test_non_cloud_ip_miss(tmp_path: Path):
    s = _build(tmp_path)
    assert s.query("203.0.115.1") == {}           # fixture 外公网 v4
    assert s.query("2001:db8:dddd::1") == {}      # fixture 外 v6


def test_cross_provider_same_cidr_statements(tmp_path: Path):
    """spec 验收 §4.1 跨家重叠段的 carve-out 钉死:AWS 与 Alibaba 声明同一
    CIDR → 同一最长前缀桶内两家证据并存 —— 按 _registry.lookup 的
    AssetStatement 收集口径:service 两条(native_type 各异)、is_hosting
    一条(同 source+value+native_type=None 三元组去重)。跨家**嵌套** CIDR
    场景则 LPM 只返回最长前缀桶(更短前缀桶证据不并入),与 cdn_edges
    先例语义一致 —— 文末一并钉死。"""
    d = tmp_path / _DIR
    d.mkdir(parents=True)
    (d / "aws.json").write_text(json.dumps(
        {"prefixes": [{"ip_prefix": "203.0.113.0/24"}]}))
    (d / "alibaba.txt").write_text(
        "203.0.113.0/24\n"          # 与 AWS 同一 CIDR(重叠段)
        "203.0.113.128/25\n")       # 嵌套更长前缀(carve-out 探针)
    (d / "gcp.json").write_text(json.dumps({"prefixes": []}))
    (d / "azure.json").write_text(json.dumps({"values": []}))
    (d / "oracle.json").write_text(json.dumps({"regions": []}))
    s = CloudRangesSource(data_dir=tmp_path)
    assert s.rebuild() > 0

    recs = s.query("203.0.113.55")                 # 同 CIDR 段内
    assert len(recs) == 2                          # 两家证据同桶并存
    by_native = {r["_native_types"]["service"]: r for r in recs}
    assert set(by_native) == {"AWS", "Alibaba"}
    assert by_native["AWS"]["reliability"] == 0.95
    assert by_native["Alibaba"]["reliability"] == 0.75
    # _registry.lookup 同款收集循环(AssetStatement 去重三元组)
    attributes: dict = {}
    for item in recs:
        native_types = item.get("_native_types") or {}
        for akey in ASSET_SLOTS:
            if akey in item:
                stmt = AssetStatement(
                    source=s.name, value=item[akey],
                    native_type=native_types.get(akey))
                if not any(x.source == stmt.source and x.value == stmt.value
                           and x.native_type == stmt.native_type
                           for x in attributes.setdefault(akey, [])):
                    attributes[akey].append(stmt)
    assert len(attributes["service"]) == 2
    assert {st.native_type for st in attributes["service"]} == {"AWS", "Alibaba"}
    assert attributes["is_hosting"] == [AssetStatement(
        source="cloud_ranges", value=True, native_type=None)]

    # 嵌套 carve-out:LPM 只回最长前缀桶(cdn_edges 先例),不并入父段
    # (203.0.113.200 同时落在 Alibaba /25 与两家共有的 /24 桶内,只回 /25 桶)
    nested = s.query("203.0.113.200")
    assert [r["_native_types"]["service"] for r in nested] == ["Alibaba"]


def test_feeds_table_contract():
    """_FEEDS 六元组 = (provider, fetch_fn, parse_fn, filename, reliability,
    stale_days);provider 冻结名与 per-provider 值按 Global Constraints。"""
    assert [f[0] for f in _FEEDS] == [
        "AWS", "Google", "Azure", "Oracle Cloud", "Alibaba"]
    assert [f[3] for f in _FEEDS] == [
        "aws.json", "gcp.json", "azure.json", "oracle.json", "alibaba.txt"]
    assert {f[0]: f[4] for f in _FEEDS} == {
        "AWS": 0.95, "Google": 0.95, "Azure": 0.95,
        "Oracle Cloud": 0.95, "Alibaba": 0.75,
    }
    assert {f[0]: f[5] for f in _FEEDS} == {
        "AWS": 7, "Google": 7, "Azure": 14, "Oracle Cloud": 7, "Alibaba": 7,
    }
    assert _provider_by_file("azure.json") == "Azure"
    assert _provider_by_file("cdn_edges.csv") is None


def test_metadata_declared():
    """类属性钉死值;registry 元数据从 class attr 派生(_registry.py 禁改)。"""
    s = CloudRangesSource.__new__(CloudRangesSource)
    assert s.name == "cloud_ranges"
    assert s.category == "asset"
    assert s.filename == "cloud_ranges"     # 目录形态(blocklist_de 同式)
    assert s.fields == ("service", "is_hosting")
    assert s.authoritative_for == ()
    assert s.reliability == 0.95
    assert s.url is None                    # 单源多 host,无单一权威 URL(cn_isp 先例)
    assert s.stale_days == 7                # 显式声明,防基类默认漂移(scheduler 消费)


# ── Task 3: 运维面(download 部分容忍 / legacy 清理 / feeds health) ──
# monkeypatch Source._http_get(五家 fetch 的统一传输层):查表返回伪造响应,
# fail_urls 直接 raise 模拟单家/全体传输故障,零真实网络。

_AZURE_LINK = ("https://download.microsoft.com/download/x/"
               "ServiceTags_Public_20260101.json")
_OK_RESPONSES = {
    _AWS_URL: b'{"prefixes": [{"ip_prefix": "203.0.113.0/24"}]}',
    _GCP_URL: b'{"prefixes": [{"ipv4Prefix": "198.51.100.0/24"}]}',
    _PAGE: (b'<html><a href="' + _AZURE_LINK.encode() + b'">dl</a></html>'),
    _AZURE_LINK: (b'{"values": [{"name": "AzureCloud", '
                  b'"properties": {"addressPrefixes": ["192.0.2.0/24"]}}]}'),
    _ORACLE_URL: b'{"regions": [{"region": "us-ashburn-1", '
                 b'"cidrs": [{"cidr": "198.18.0.0/15"}]}]}',
    _ALIBABA_URL: b"203.0.114.0/24\n",
}


def _patch_http(monkeypatch, fail_urls=()):
    def fake_get(url, *, headers=None, timeout=120, retries=3):
        if url in fail_urls:
            raise RuntimeError(f"network down: {url}")
        return _OK_RESPONSES[url]

    monkeypatch.setattr(Source, "_http_get", staticmethod(fake_get))


def test_download_partial_failure_keeps_old_file(tmp_path, monkeypatch):
    """azure 单家挂:download 整体成功;旧 azure.json 原样保留(内容+mtime
    不变),其余四家新落地,scratch 不留(cn_isp 部分容忍先例)。"""
    d = tmp_path / _DIR
    d.mkdir(parents=True)
    old = d / "azure.json"
    old.write_text("PREVIOUS INTERMEDIATE")
    old_mtime = old.stat().st_mtime_ns
    _patch_http(monkeypatch, fail_urls=(_PAGE,))      # azure 第一步即挂
    CloudRangesSource(data_dir=tmp_path).download()
    assert old.read_bytes() == b"PREVIOUS INTERMEDIATE"
    assert old.stat().st_mtime_ns == old_mtime
    for url, name in ((_AWS_URL, "aws.json"), (_GCP_URL, "gcp.json"),
                      (_ORACLE_URL, "oracle.json"),
                      (_ALIBABA_URL, "alibaba.txt")):
        assert (d / name).read_bytes() == _OK_RESPONSES[url]
    assert not list(d.glob("*.dl"))                   # scratch 清干净


def test_download_all_failed_raises(tmp_path, monkeypatch):
    """五家全挂必须 raise(防空 rebuild 清库)。"""
    _patch_http(monkeypatch, fail_urls=tuple(_OK_RESPONSES))
    s = CloudRangesSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="all cloud_ranges feeds"):
        s.download()


def test_download_records_partial_failure_signal(tmp_path, monkeypatch):
    """终审 Important#1 源侧:download 把失败家记入 last_partial_failure
    (RefreshScheduler 的 done-但-部分失败信号):全绿 = 空列表,单家挂 =
    该家名,全挂 raise 前同样记录。"""
    (tmp_path / _DIR).mkdir(parents=True)
    s = CloudRangesSource(data_dir=tmp_path)
    assert s.last_partial_failure == []          # 初始态(尚未 download)
    _patch_http(monkeypatch)
    s.download()
    assert s.last_partial_failure == []
    _patch_http(monkeypatch, fail_urls=(_PAGE,))
    s.download()
    assert s.last_partial_failure == ["Azure"]
    _patch_http(monkeypatch, fail_urls=tuple(_OK_RESPONSES))
    with pytest.raises(RuntimeError, match="all cloud_ranges feeds"):
        s.download()
    assert s.last_partial_failure == [
        "AWS", "Google", "Azure", "Oracle Cloud", "Alibaba"]


# Rails 应用可能的 200-HTML 错误/维护页(旧 test_alibaba_ranges.py 同款)
_ERROR_PAGE = (
    b"<!DOCTYPE html><html><body>"
    b"<h1>We're sorry, but something went wrong (500)</h1>"
    b"</body></html>\n"
)


def _patch_http_with(url, body):
    """_patch_http 变体:单一 url 返回 body,其余照 _OK_RESPONSES。"""
    def fake_get(u, *, headers=None, timeout=120, retries=3):
        return body if u == url else _OK_RESPONSES[u]
    return staticmethod(fake_get)


def test_alibaba_html_error_page_end_to_end_guard(tmp_path, monkeypatch):
    """旧 test_alibaba_ranges.py 的 200-HTML 错误页端到端守卫移植(终审
    #6a):Rails 错误页(非空体)穿不透 _validate_raw —— 旧 alibaba.txt
    中间文件原样保留(内容+mtime),该家计失败(部分容忍,非整源炸)。"""
    d = tmp_path / _DIR
    d.mkdir(parents=True)
    good = "203.0.113.0/24\n198.51.100.0/24\n"
    (d / "alibaba.txt").write_text(good)
    old_mtime = (d / "alibaba.txt").stat().st_mtime_ns
    monkeypatch.setattr(Source, "_http_get",
                        _patch_http_with(_ALIBABA_URL, _ERROR_PAGE))
    s = CloudRangesSource(data_dir=tmp_path)
    s.download()                                    # 整体成功:其余四家照常
    assert (d / "alibaba.txt").read_text() == good  # 旧中间文件原样保留
    assert (d / "alibaba.txt").stat().st_mtime_ns == old_mtime
    assert s.last_partial_failure == ["Alibaba"]    # 该家计失败
    assert (d / "aws.json").exists()
    assert not list(d.glob("*.dl"))                 # scratch 清干净


def test_fetch_json_rejects_html_error_page(tmp_path, monkeypatch):
    """终审 #4:aws/gcp/oracle 的 _fetch_json 补 JSON 可解析守卫 ——
    200-HTML 不得换掉好中间文件(azure/alibaba 已有守卫);失败走单家
    部分容忍路径。"""
    d = tmp_path / _DIR
    d.mkdir(parents=True)
    good = json.dumps({"prefixes": [{"ipv4Prefix": "198.51.100.0/24"}]})
    (d / "gcp.json").write_text(good)
    old_mtime = (d / "gcp.json").stat().st_mtime_ns
    monkeypatch.setattr(Source, "_http_get",
                        _patch_http_with(_GCP_URL, _ERROR_PAGE))
    s = CloudRangesSource(data_dir=tmp_path)
    s.download()                                    # 单家挂不炸整源
    assert (d / "gcp.json").read_text() == good    # 好中间文件原样保留
    assert (d / "gcp.json").stat().st_mtime_ns == old_mtime
    assert s.last_partial_failure == ["Google"]


def test_cleanup_legacy_deferred_until_fetch_lands(tmp_path, monkeypatch):
    """终审 #3 回滚安全:_cleanup_legacy 在 fetch 循环**之后** —— 升级首跑
    fetch 全挂(raise)时五个旧单源文件还在,回滚上一版本仍可用;旧中间
    文件对新源本就不可读,后置对成功路径零差别(见上例
    test_cleanup_legacy_only_touches_five_families)。"""
    legacy = tmp_path / "aws_ranges.json"
    legacy.write_text("{}")
    orphan = tmp_path / "alibaba_ranges.txt"
    orphan.write_text("203.0.113.0/24\n")
    _patch_http(monkeypatch, fail_urls=tuple(_OK_RESPONSES))
    s = CloudRangesSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="all cloud_ranges feeds"):
        s.download()
    assert legacy.exists()
    assert orphan.exists()


def test_cleanup_legacy_only_touches_five_families(tmp_path, monkeypatch):
    """旧单源文件名 + .lmdb.*/.v6.lmdb.* sidecar(epoch 目录与 ptr 文件两
    形态)在首次 download 后全消失;旁源文件原样。"""
    legacy_file = tmp_path / "aws_ranges.json"
    legacy_file.write_text("{}")
    epoch_dir = tmp_path / "aws_ranges.json.lmdb.1"   # LMDB epoch 目录形态
    epoch_dir.mkdir()
    (epoch_dir / "data.mdb").write_text("x")
    ptr = tmp_path / "aws_ranges.json.lmdb.ptr"       # ptr/count/cov 文件形态
    ptr.write_text("1")
    v6_dir = tmp_path / "alibaba_ranges.txt.v6.lmdb.2"   # v6 变体目录
    v6_dir.mkdir()
    v6_ptr = tmp_path / "alibaba_ranges.txt.v6.lmdb.ptr"
    v6_ptr.write_text("2")
    orphan_txt = tmp_path / "alibaba_ranges.txt"
    orphan_txt.write_text("203.0.114.0/24\n")
    bystander_dir = tmp_path / "blocklist_de"         # 旁源:不得误伤
    bystander_dir.mkdir()
    (bystander_dir / "ssh.txt").write_text("1.2.3.4\n")
    bystander_file = tmp_path / "blocklist_de.txt"
    bystander_file.write_text("1.2.3.4\n")

    _patch_http(monkeypatch)          # 五家全成功;download 首步执行清理
    CloudRangesSource(data_dir=tmp_path).download()

    for gone in (legacy_file, epoch_dir, ptr, v6_dir, v6_ptr, orphan_txt):
        assert not gone.exists()
    assert (bystander_dir / "ssh.txt").exists()
    assert bystander_file.exists()


def test_health_any_stale(tmp_path):
    """feeds 逐家 mtime → FeedHealth;任一超期即源级 stale;last_updated =
    max-mtime;Azure 阈值 14 查 _FEEDS 表(health 内不硬编码:13 天不超期)。"""
    _write_all(tmp_path)
    azure = tmp_path / _DIR / "azure.json"
    now = time.time()
    os.utime(azure, (now - 15 * 86400,) * 2)         # Azure 阈值 14 → 超期
    h = CloudRangesSource(data_dir=tmp_path).health()
    by_name = {f.name: f for f in h.feeds}
    assert set(by_name) == {f[0] for f in _FEEDS}
    assert by_name["Azure"].is_stale is True
    assert by_name["AWS"].is_stale is False
    assert h.is_stale is True
    newest = max((tmp_path / _DIR / f[3]).stat().st_mtime for f in _FEEDS)
    assert h.last_updated == time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime(newest))
    os.utime(azure, (now - 13 * 86400,) * 2)         # 13 < 14 → 不超期
    h2 = CloudRangesSource(data_dir=tmp_path).health()
    assert {f.name: f.is_stale for f in h2.feeds}["Azure"] is False
    assert h2.is_stale is False


def test_health_no_files_stale(tmp_path):
    """无任何文件(目录不存在):源级 stale、last_updated None,五家 feed
    全部 last_updated=None / is_stale=True。"""
    h = CloudRangesSource(data_dir=tmp_path).health()
    assert h.is_stale is True
    assert h.last_updated is None
    assert len(h.feeds) == len(_FEEDS)
    assert all(f.last_updated is None and f.is_stale for f in h.feeds)


def test_download_host_is_none(tmp_path):
    """五家出版方无单一权威主机(cn_isp 先例)——registry 名册落 '-'。"""
    assert CloudRangesSource(data_dir=tmp_path).download_host is None
