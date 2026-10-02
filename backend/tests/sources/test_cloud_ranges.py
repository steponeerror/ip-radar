"""cloud_ranges — 五家云厂商融合源(数据面:harvest/rebuild/query)。

fixture 中间文件逐家镜像真实格式(aws/gcp/azure/oracle 官方 JSON、
alibaba CIDR-per-line 文本)落 tmp_path/cloud_ranges/,rebuild → query
round-trip 钉住:冻结 Evidence 形状、per-provider reliability、缺家文件
容忍、v6 双族路由、fixture 外 miss。断言写法移植自 test_alibaba_ranges.py
的 round-trip 用例(query 返回 evidence dict 列表,verdict="" 落库即省略)。
"""
import json
from pathlib import Path

from ipdb._evidence import Evidence
from ipdb._sources.cloud_ranges import (
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
