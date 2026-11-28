"""印证对聚合器占比披露(spec #180 Q4 租户 / issue #183)。

corroborated 语义已改(#522,2026-11-28 丙口径:「非派生且系数非零」
的源 ≥2 才算印证):纯 derived 组不再亮旗,本披露的分母随之缩小;
本测试钉生产旗面(fixture 的 corroborated 键)+ 镜像重算一致性
(corroborated_after_dedup)两条腿。Seam = 纯函数面(lookup 载荷 →
占比结构)+ probe_ips 采样装配;载荷用生产 to_dict 形状
(classifications/details/corroborated)。
"""
import json
from pathlib import Path

from ipdb._eval.agg_share import corroboration_agg_share, probe_ips


def _payload(groups):
    """生产 to_dict 形状的最小载荷:groups = [(ctype, verdict, corroborated,
    [(source, reliability, verdict), ...]), ...]。"""
    classifications = {}
    for ctype, verdict, corr, voters in groups:
        classifications[ctype] = {
            "type": ctype, "verdict": verdict, "detected": True,
            "confidence": 55, "corroborated": corr,
            "details": [{"source": s, "reliability": r, "verdict": v}
                        for s, r, v in voters],
        }
    return {"ip": "x", "classifications": classifications,
            "is_reserved": False, "attributes": {}}


# 事故形状(2026-10-24 114DNS 机制正身):纯 derived 组互证(ziyadnz
# 0.55 + cps 0.50)。#522 起生产不再给这类组亮旗(qualifying=0);此处
# 保留 corroborated=True 旧载荷,钉「镜像重算不一致 → 不计入」的防漂
# 移腿(若生产回退旧判式,本 fixture 会重新计入 → 测试红)。
_INCIDENT = _payload([("blacklist", "malicious", True, [
    ("ziyadnz", 0.55, "malicious"),
    ("cps_collected_iocs", 0.50, "malicious"),
])])
# 混合印证:两个非 derived 证人 + 更强的聚合器票(derived 系数 ≤ 最强
# 非 derived 会被 dedup_lineage 剔,更强则幸存——幸存派生票不算印证
# 资格但计入聚合器占比)。#522:旗由两个非 derived 非零证人抬。
_MIXED = _payload([("blacklist", "malicious", True, [
    ("abuseipdb", 0.80, "malicious"),
    ("spamhaus", 0.70, "malicious"),
    ("ziyadnz", 0.90, "malicious"),
])])
# 单源未印证
_SINGLE = _payload([("blacklist", "malicious", False, [
    ("myip_ms", 0.55, "malicious"),
])])


def test_pure_derived_group_no_longer_corroborated():
    """#522 丙口径:纯 derived 互证(qualifying=0)不再算印证——即使
    载荷仍带旧旗 corroborated=True,镜像重算(corroborated_after_dedup)
    判不一致 → 不计入分母、不产例。生产若回退旧判式,本测试红。"""
    res = corroboration_agg_share(lambda ip: _INCIDENT, ["203.0.113.7"])
    assert res["n_probe"] == 1
    assert res["n_corroborated_groups"] == 0
    assert res["n_pure_derived_groups"] == 0
    assert res["examples"] == []


def test_mixed_corroboration_counts_votes_not_echo():
    res = corroboration_agg_share(lambda ip: _MIXED, ["203.0.113.7"])
    assert res["n_corroborated_groups"] == 1
    assert res["n_pure_derived_groups"] == 0
    assert res["derived_vote_share"] == 1 / 3       # 池内 3 票(abuseipdb/spamhaus/ziyadnz)中 1 票是聚合器;旗由两个非 derived 非零证人抬(#522)
    assert res["examples"] == []            # 纯 derived 互证结构性不可亮旗 → 无例


def test_uncorroborated_and_clean_not_counted():
    res = corroboration_agg_share(
        lambda ip: _MIXED if ip.endswith(".7") else
        (_SINGLE if ip.endswith(".8") else
         {"classifications": {}, "is_reserved": False}),
        ["203.0.113.7", "203.0.113.8", "203.0.113.9"])
    assert res["n_probe"] == 3
    assert res["n_corroborated_groups"] == 1        # 单源/clean 不进分母
    assert res["n_pure_derived_groups"] == 0


def test_lineage_anchor_echo_not_double_counted():
    """锚对回声已被 dedup_lineage 剔除 → 不产纯 derived 例(firehol/greensnow
    镜像对判例);占比按 dedup 后池计。"""
    anchored = _payload([("blacklist", "malicious", True, [
        ("emerging_threats", 0.60, "malicious"),   # 非 derived
        ("spamhaus", 0.55, "malicious"),
    ])])
    res = corroboration_agg_share(lambda ip: anchored, ["203.0.113.7"])
    assert res["n_corroborated_groups"] == 1
    assert res["derived_vote_share"] == 0.0


def test_suspicious_verdict_is_accusing_chapter():
    # #522 起纯 derived 双源不再亮旗,改用两个非 derived 证人钉
    # 「suspicious 章计入印证判定」不变。
    susp = _payload([("bruteforce", "suspicious", True, [
        ("threatfox", 0.60, "suspicious"),
        ("urlhaus", 0.60, "suspicious"),
    ])])
    res = corroboration_agg_share(lambda ip: susp, ["203.0.113.7"])
    assert res["n_corroborated_groups"] == 1
    assert res["n_pure_derived_groups"] == 0


class _FakeSource:
    def __init__(self, name, path, ctype="blacklist", verdict="malicious"):
        self.name = name
        self._path = path
        self.classification_type = ctype
        self.verdict = verdict


def test_probe_ips_samples_accusing_sources_only(tmp_path):
    """指控源入探针(容量帽截到 ≤ TOTAL_CAP),资产/弃权源不入。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("\n".join(f"10.1.0.{i}" for i in range(1, 60)) + "\n")
    f2 = tmp_path / "b.txt"
    f2.write_text("\n".join(f"10.2.0.{i}" for i in range(1, 60)) + "\n")
    accusing = [_FakeSource("a", f1), _FakeSource("b", f2)]
    asset = _FakeSource("geo", tmp_path / "missing.txt")
    asset.classification_type = None
    ips = probe_ips(accusing + [asset], total=50)
    assert len(ips) <= 50
    assert {ip.rsplit(".", 1)[0] for ip in ips} == {"10.1.0", "10.2.0"}
    # 稳定采样:同输入同输出(逐字节可复算)
    assert ips == probe_ips(accusing + [asset], total=50)


def test_agg_share_cli_lands_report_and_exits_zero(
        monkeypatch, capsys, tmp_path):
    """CLI 腿:--agg-share 只测量不持门(main 正常 return = exit 0),
    JSON stdout + model/agg-share-<ts>.json 落盘(anchors 报告族同形)。"""
    from types import SimpleNamespace
    import ipdb._eval.__main__ as M

    raw = tmp_path / "a.txt"
    raw.write_text("203.0.113.7\n203.0.113.8\n203.0.113.9\n")
    src = SimpleNamespace(name="a", _path=raw,
                          classification_type="blacklist",
                          verdict="malicious")
    reg = SimpleNamespace(load_db=lambda: None, lookup=lambda ip: _MIXED,
                          sources=[src])
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(M, "_real_registry", lambda: reg)
    M.main(["--agg-share", "--json"])      # 不 SystemExit:披露非闸门
    out = json.loads(capsys.readouterr().out)
    assert out["n_probe"] == 3
    assert out["n_corroborated_groups"] == 3
    assert out["n_pure_derived_groups"] == 0        # #522:纯 derived 互证结构性不可亮旗
    files = list((tmp_path / "model").glob("agg-share-*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["kind"] == "agg_share"
