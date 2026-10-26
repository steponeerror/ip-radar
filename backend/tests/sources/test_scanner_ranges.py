"""scanner_ranges (scanner vendors' self-declared ranges) — Evidence shape assertions.

Covers: _FEEDS completeness (66 MISP warninglists + 1 Xpanse direct page,
name set == spec verbatim), MISP list.json parsing (v4/v6 mixed, bare-IP →
host route, garbage drops), Xpanse HTML table parsing (9 spec-verbatim CIDR
+ noise), harvest → scanner/malicious Evidence with the native label
「研究扫描 · <厂商/机构>(自报段)」on native_categories (f3csystems.py:53
先例; spec 2026-10-26 补定 — native_types 只喂 ASSET_SLOTS, scanner 无槽;
渲染链 _merge detail dict → _api_models.py:56 → 前端 SourceDetailRow chip),
dual-family routing, rebuild-level dedup (identical evidence collapses,
distinct vendors coexist), health contract, and registry metadata
(category=threat, r=0.90, authoritative_for=() — corroboration only).
Offline: fixtures only, no network.
"""
import json

from ipdb._evidence import Evidence
from ipdb._sources.scanner_ranges import (
    _FEEDS,
    _MISP_URL_TMPL,
    _XPANSE_URL,
    ScannerRangesSource,
    _parse,
)

# Spec-verbatim 66 MISP warninglist names (census 2026-10-26, CC0/CIRCL,
# -nt- lists deliberately excluded — observation-extracted, not self-declared).
SPEC_MISP_NAMES = frozenset(
    """a10networks-scanning academyforinternetresearch-scanning adscore-scanning
    alphastrike-scanning binaryedge-scanning bitsight-scanning
    bufferoverrun-scanning censys-scanning circl-security-scanning
    circl-ssh-scanning criminalip-scanning crowdstrikefalconsurface-scanning
    cybcube-scanning cybergreen-scanning cyberok-scanning
    cyberresilience-scanning cypex-scanning dataplane-scanning
    deepfield-scanning detectify-scanning edgewatch-scanning eset-scanning
    fofa-scanning groupib-scanning hackertarget-scanning hadrian-scanning
    hunter-scanning infrawatch-scanning internetcleanup-scanner
    internetmeasurementresearch-scanning internetmetrics-scanning
    internetresearchproject-scanning internettl-scanning intrinsec-scanning
    intruder-scanning ipinfo-scanning ipip-scanning ki3-scanning knoq-scanning
    leakix-scanning mandiantasm-scanning modat-scanner netlas-scanning
    netscout-scanning netsecscan-scanning odin-scanning onlyscans-scanning
    onyphe-scanner pocnroll-scanning probethenet-scanning quake-scanning
    rapid7-scanning recordedfuture-scanning recyber-scanning
    researchscanner-scanning rootevidence-scanning securityresearch-scanning
    shadowforce-scanning shodan-scanning stretchoid-scanning
    tenableasm-scanning university-scanning visionheight-scanning
    xmco-scanning zern-scanning zoomeye-scanning""".split()
)

# Spec-verbatim Xpanse direct page CIDR (cortex-docs scanning-activity).
XPANSE_CIDRS = [
    "144.86.173.0/24", "147.185.132.0/23", "162.216.149.0/24",
    "162.216.150.0/24", "172.105.147.0/24", "198.235.24.0/24",
    "205.210.31.0/24", "216.25.88.0/21", "35.203.210.0/23",
]

# Combined-intermediate fixture (cidr,vendor) — exactly what download() writes.
_FIXTURE = """\
162.142.125.0/24,Censys
167.248.133.0/24,Censys
2a0e:7b84::/30,Alpha Strike Labs
40.124.175.0/24,Stretchoid
198.235.24.0/24,Palo Alto Xpanse
"""


def test_feeds_complete_66_misp_plus_1_xpanse():
    """66+1 completeness: name set == spec verbatim; MISP rows share one
    raw.githubusercontent URL template; Xpanse row is the direct docs page."""
    assert len(_FEEDS) == 67
    names = {name for name, _url, _vendor, _fmt in _FEEDS}
    assert names == SPEC_MISP_NAMES | {"xpanse"}
    misp = [f for f in _FEEDS if f[3] == "misp"]
    assert len(misp) == 66
    for name, url, _vendor, _fmt in misp:
        assert url == _MISP_URL_TMPL.format(name=name)
    xpanse = [f for f in _FEEDS if f[0] == "xpanse"][0]
    assert xpanse[1] == _XPANSE_URL
    assert xpanse[2] == "Palo Alto Xpanse"
    # 红线锚:OpenFilters 镜像/-nt-/GreyNoise 一概不接(spec 定案)。
    assert not any("openfilters" in f[1] for f in _FEEDS)
    assert not any("-nt-" in f[0] for f in _FEEDS)


def test_parse_misp_list_json_dual_family_and_garbage():
    """实测缓存形态(/tmp/misl_censys-scanning.json):list 数组 v4/v6 混排,
    裸 IP 收作 /32(实测 66 列表含 22 条裸 IP),非字符串/坏条目弃。"""
    data = json.dumps({
        "name": "Censys IP Ranges Used for Scanning",
        "description": "List containing IP's associated with Censys scanning",
        "version": 3,
        "list": [
            "162.142.125.0/24",        # v4 CIDR
            "2602:801:f000::/44",      # v6 混排
            "162.142.124.7",           # 裸 IP → /32
            "not-an-ip",               # 坏条目 → 弃
            12345,                     # 非字符串 → 弃
            "",                        # 空串 → 弃
        ],
    }).encode()
    assert list(_parse(data, "misp")) == [
        "162.142.125.0/24", "2602:801:f000::/44", "162.142.124.7/32",
    ]


def test_parse_xpanse_html_nine_cidr_verbatim():
    """Xpanse 官方页直读:表格文本里的 9 CIDR 原样提出,页内噪声
    (裸 IP/版本号/邮箱)不产 CIDR。"""
    html = """<!DOCTYPE html>
<html><body>
<h1>Cortex Xpanse Scanning Activity</h1>
<p>Xpanse performs internet-wide scanning from the ranges below.</p>
<table>
<tr><td>35.203.210.0/23</td></tr>
<tr><td>144.86.173.0/24</td></tr>
<tr><td>147.185.132.0/23</td></tr>
<tr><td>162.216.149.0/24</td></tr>
<tr><td>162.216.150.0/24</td></tr>
<tr><td>172.105.147.0/24</td></tr>
<tr><td>198.235.24.0/24</td></tr>
<tr><td>205.210.31.0/24</td></tr>
<tr><td>216.25.88.0/21</td></tr>
</table>
<div>Contact scans@paloaltonetworks.example · page v1.2 · 2026-10-26</div>
</body></html>
""".encode()
    assert sorted(_parse(html, "xpanse")) == sorted(XPANSE_CIDRS)


def test_scanner_ranges_loads_and_routes(tmp_path):
    (tmp_path / "scanner_ranges.csv").write_text(_FIXTURE)
    s = ScannerRangesSource(data_dir=tmp_path)
    assert s.rebuild() == 4          # rebuild() 契约 = v4 族键数(4 v4 + 1 v6)
    # Stretchoid 自报段内 IP(spec 验收烟囱例 40.124.175.29)→ 证据契约整形状
    rec = s.query("40.124.175.29")[0]
    assert rec == Evidence(
        classification_type="scanner",
        verdict="malicious",
        reliability=0.90,
        native_categories=["研究扫描 · Stretchoid(自报段)"],
    ).to_dict()
    # Censys / Xpanse 标签字面量(native_categories 路线,spec 补定)
    assert s.query("162.142.125.10")[0]["native_categories"] == [
        "研究扫描 · Censys(自报段)"]
    assert s.query("198.235.24.1")[0]["native_categories"] == [
        "研究扫描 · Palo Alto Xpanse(自报段)"]
    # 双族:v6 走并行族 reader
    assert s.query("2a0e:7b84::1")[0]["native_categories"] == [
        "研究扫描 · Alpha Strike Labs(自报段)"]
    # 段外 miss
    assert s.query("8.8.8.8") == {}


def test_dedup_identical_collapses_distinct_vendor_keeps(tmp_path):
    (tmp_path / "scanner_ranges.csv").write_text(
        "10.1.0.0/16,Censys\n"
        "10.1.0.0/16,Censys\n"       # 完全同证据 → rebuild 层 acc 去重
        "10.1.0.0/16,Shodan\n"       # 同 CIDR 异厂 → 两票并存
    )
    s = ScannerRangesSource(data_dir=tmp_path)
    assert s.rebuild() == 1
    recs = s.query("10.1.0.5")
    assert len(recs) == 2
    labels = sorted(r["native_categories"][0] for r in recs)
    assert labels == ["研究扫描 · Censys(自报段)", "研究扫描 · Shodan(自报段)"]


def test_health_loaded_not_stale(tmp_path):
    (tmp_path / "scanner_ranges.csv").write_text(_FIXTURE)
    s = ScannerRangesSource(data_dir=tmp_path)
    s.rebuild()
    h = s.health()
    assert h.loaded is True
    assert h.record_count == 4       # DQ-2:record_count = env 主库(v4 族)键数
    assert h.covered_v6_nets == 1    # v6 并行族键数
    assert h.is_stale is False       # stale_days=7; fixture just written


def test_registry_metadata_threat_corroboration_only():
    """自动发现注册(_discover_sources):category/reliability/authoritative_for
    落册形态;authoritative_for=() 保证不进 AUTHORITATIVE_SOURCES(SM-F1,
    test_source_decls 的权威矩阵精确断言不被扰动)。"""
    import ipdb._registry as reg
    src = next(s for s in reg._sources if s.name == "scanner_ranges")
    assert src.category == "threat"
    assert src.reliability == 0.90
    assert src.authoritative_for == ()
    assert src.stale_days == 7
