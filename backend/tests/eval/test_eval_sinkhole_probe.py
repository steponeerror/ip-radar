"""sinkhole 污染探针(ADR 0013 / issue #233 T2)。

Seam = 语料资产面(仓内静态资产 + provenance sidecar 双 pin)+ 纯函数面
(lookup 载荷 × 语料成员 → 污染读数;指控池按生产合并语义重算,镜像对不
双计)+ CLI 面(只测量不持门)。载荷用生产 to_dict 形状
(classifications/details);零网络(语料已固化仓内,取数一次性)。
"""
import json
from pathlib import Path

from ipdb._eval.sinkhole_probe import (
    load_sinkhole_ranges, sinkhole_match, sinkhole_probe)

_PKG = Path(__file__).resolve().parents[2] / "ipdb" / "_eval"
_ASSET = _PKG / "sinkhole_ranges.json"
_SIDECAR = _PKG / "sinkhole_ranges.provenance.json"

# 双 pin 字面量(独立真源 = provenance 调研 2026-10-28 + 取数实测,非实现回算;
# version 逐字保留 MISP 上游类型 int)
_PIN_VERSION = 20261014               # MISP list version(YYYYMMDD 规约)
_PIN_SHA256 = ("de791ba3fcbf7fe087ba6c55103212d781a538e574282716"
               "df60d8609d1b3c7f")  # 上游 list.json 内容 SHA256
_PIN_UPSTREAM_SHA = "1a284cd902e4bf023f1e45aa79a5d7d3dfff5abf"  # brakmic/Sinkholes


# ── 语料资产面 ───────────────────────────────────────────────────────────

def test_corpus_asset_pinned_to_provenance_sidecar():
    """仓内语料 = MISP sinkholes 203 项(186 裸 IP + 17 CIDR),sidecar
    双 pin 与资产件逐项一致(条目构成数是 pin 的一部分)。"""
    import ipaddress
    d = json.loads(_ASSET.read_text(encoding="utf-8"))
    ips, cidrs = d["ip"], d["cidr"]
    assert len(ips) == 186 and len(cidrs) == 17
    assert len(ips) + len(cidrs) == 203
    assert all("/" not in e for e in ips)          # MISP 原拼写:裸 IP 不带 /32
    assert all("/" in e for e in cidrs)
    for e in ips:                                   # 全量可解析(防坏件缩水)
        ipaddress.IPv4Address(e)
    for e in cidrs:
        net = ipaddress.ip_network(e, strict=False)
        assert net.version == 4
    # provenance 调研钉死的具名条目在场(独立于生成脚本的锚)
    assert "104.244.12.0/22" in cidrs               # 最大 /22
    assert "104.244.14.252/31" in cidrs             # 最小 /31

    side = json.loads(_SIDECAR.read_text(encoding="utf-8"))
    assert side["misp"]["version"] == _PIN_VERSION
    assert side["misp"]["sha256"] == _PIN_SHA256
    assert side["upstream"]["commit_sha"] == _PIN_UPSTREAM_SHA
    assert side["entries"] == {"total": 203, "ip": 186, "cidr": 17}
    assert side["generated"]                        # 生成日期在场可回查
    # 侧车与资产件互证:条目构成数一致
    assert side["entries"]["ip"] == len(ips)
    assert side["entries"]["cidr"] == len(cidrs)


def test_load_sinkhole_ranges_rejects_corrupt_entry(tmp_path):
    """坏条目(不可解析 IP/CIDR)必须炸出,不许静默缩水(证据不灭失)。"""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(
        {"ip": ["999.999.1.1"], "cidr": ["198.51.100.0/24"]}), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        load_sinkhole_ranges(bad)


# ── 纯函数面:成员判定 ──────────────────────────────────────────────────

_RANGES = {"ip": ["192.0.2.10"], "cidr": ["198.51.100.0/24"]}


def test_sinkhole_match_exact_ip_cidr_and_none():
    assert sinkhole_match("192.0.2.10", _RANGES) == "192.0.2.10"   # 精确裸 IP
    assert sinkhole_match("198.51.100.7", _RANGES) == "198.51.100.0/24"  # CIDR 包含
    assert sinkhole_match("203.0.113.9", _RANGES) is None          # 非成员
    assert sinkhole_match("192.0.2.11", _RANGES) is None           # 同段非成员
    # 非法 token(_IP_RE 允许 999.x)非语料成员,不炸(成员判定语义)
    assert sinkhole_match("999.1.1.1", _RANGES) is None


# ── 纯函数面:污染归因(生产合并语义) ─────────────────────────────────

def _payload(groups):
    """生产 to_dict 形状最小载荷:groups = [(ctype, [(source, reliability,
    verdict), ...]), ...] —— 污染归因只看指控 detail,单源即算(不要求
    corroborated:单源把 sinkhole IP 上榜已是该源的污染证据)。"""
    classifications = {}
    for ctype, voters in groups:
        classifications[ctype] = {
            "type": ctype, "verdict": "malicious", "detected": True,
            "confidence": 55, "corroborated": False,
            "details": [{"source": s, "reliability": r, "verdict": v}
                        for s, r, v in voters],
        }
    return {"ip": "x", "classifications": classifications,
            "is_reserved": False, "attributes": {}}


def test_lineage_dedup_mirror_not_double_attributed():
    """镜像回声不双计:firehol(derived,系数低)被 dedup_lineage 剔除,
    只有锚证人记污染(宁少算;裸用 detail.source 会把镜像对算两次)。"""
    pay = _payload([("blacklist", [
        ("abuseipdb", 0.80, "malicious"),   # 非 derived 最强
        ("firehol", 0.60, "malicious"),     # derived ≤ 非 derived max → 剔
    ])])
    res = sinkhole_probe(lambda ip: pay, ["192.0.2.10"], _RANGES)
    assert res["n_probe"] == 1
    assert res["n_members"] == 1
    assert list(res["polluted_sources"]) == ["abuseipdb"]
    p = res["polluted_sources"]["abuseipdb"]
    assert p["hits"] == 1 and p["share"] == 1.0
    assert res["evidence"] == [{"source": "abuseipdb", "ip": "192.0.2.10",
                                "sinkhole_entry": "192.0.2.10"}]


def test_layered_subreadings_cidr_vs_bare_ip():
    """分层读数:CIDR 基(强信号)与单 IP 基(弱信号,重指派残余风险)
    分开计数;分母 = |probe|(指控源命中数/探针规模)。"""
    pay = _payload([("blacklist", [("abuseipdb", 0.80, "malicious")])])
    res = sinkhole_probe(
        lambda ip: pay,
        ["198.51.100.7", "192.0.2.10", "203.0.113.9"],   # CIDR 成员/裸成员/非成员
        _RANGES)
    assert res["n_probe"] == 3
    assert res["n_members"] == 2
    assert res["n_members_cidr"] == 1 and res["n_members_ip"] == 1
    p = res["polluted_sources"]["abuseipdb"]
    assert p["hits"] == 2 and abs(p["share"] - 2 / 3) < 1e-12
    assert p["hits_cidr"] == 1 and p["hits_ip"] == 1
    assert abs(p["share_cidr"] - 1 / 3) < 1e-12
    assert abs(p["share_ip"] - 1 / 3) < 1e-12
    assert {(e["ip"], e["sinkhole_entry"]) for e in res["evidence"]} == {
        ("198.51.100.7", "198.51.100.0/24"), ("192.0.2.10", "192.0.2.10")}


def test_same_source_two_groups_counts_once_per_ip():
    """同源同 IP 多指控组只记一次命中(per-IP accuser 并集,宁少算)。"""
    pay = _payload([
        ("blacklist", [("abuseipdb", 0.80, "malicious")]),
        ("scanner", [("abuseipdb", 0.70, "suspicious")]),
    ])
    res = sinkhole_probe(lambda ip: pay, ["192.0.2.10"], _RANGES)
    assert res["polluted_sources"]["abuseipdb"]["hits"] == 1
    assert len(res["evidence"]) == 1


def test_non_accusing_details_not_attributed():
    """弃权/良性 detail 不记污染(指控判定 = verdict ∈ _ACCUSING 同口径)。"""
    pay = _payload([
        ("blacklist", [("infra_services", 0.95, "benign"),
                       ("ghost", 0.55, "")]),
    ])
    res = sinkhole_probe(lambda ip: pay, ["192.0.2.10"], _RANGES)
    assert res["n_members"] == 1
    assert res["polluted_sources"] == {}
    assert res["evidence"] == []


def test_no_members_zero_readings_not_zero_fabrication():
    """零命中 = 空读数面(不虚构 0 占比;缺层≠0 层)。"""
    pay = _payload([("blacklist", [("abuseipdb", 0.80, "malicious")])])
    res = sinkhole_probe(lambda ip: pay, ["203.0.113.9"], _RANGES)
    assert res["n_members"] == 0
    assert res["polluted_sources"] == {}
    assert res["evidence"] == []
    assert res["n_probe"] == 1


# ── CLI 面:只测量不持门 ────────────────────────────────────────────────

def test_sinkhole_probe_cli_lands_report_and_exits_zero(
        monkeypatch, capsys, tmp_path):
    """CLI 腿:--sinkhole-probe 只测量不持门(main 正常 return = exit 0),
    JSON stdout + model/sinkhole-probe-<ts>.json 落盘 + 采样参数随件
    (agg-share 报告族同形)。"""
    from types import SimpleNamespace
    import ipdb._eval.__main__ as M

    # 真语料资产:104.244.12.5 ∈ 104.244.12.0/22(钉死条目)
    raw = tmp_path / "a.txt"
    raw.write_text("104.244.12.5\n203.0.113.7\n203.0.113.8\n")
    src = SimpleNamespace(name="a", _path=raw,
                          classification_type="blacklist",
                          verdict="malicious")
    pay = _payload([("blacklist", [("abuseipdb", 0.80, "malicious")])])
    reg = SimpleNamespace(load_db=lambda: None, lookup=lambda ip: pay,
                          sources=[src])
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(M, "_real_registry", lambda: reg)
    M.main(["--sinkhole-probe", "--json"])      # 不 SystemExit:测量非闸门
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "sinkhole_probe"
    assert out["n_probe"] == 3
    assert out["n_members"] == 1
    assert out["n_members_cidr"] == 1
    assert out["polluted_sources"]["abuseipdb"]["hits"] == 1
    assert out["evidence"][0]["sinkhole_entry"] == "104.244.12.0/22"
    # 采样参数随件(N/seed 可回算,census 纪律 ADR 0013)
    assert out["sample"]["seed"] == 20261018
    assert out["sample"]["per_source"] == 100 and out["sample"]["total"] == 1000
    # 双 pin 随件透传
    assert out["corpus"]["version"] == _PIN_VERSION
    assert out["corpus"]["sha256"] == _PIN_SHA256
    files = list((tmp_path / "model").glob("sinkhole-probe-*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["kind"] == "sinkhole_probe"
