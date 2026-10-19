# backend/tests/eval/test_eval_matrix_scan.py
"""矩阵现状扫描引擎测试(ADR 0003 Task 2)。

契约(task-2-brief.md / 计划 Task 2):
- 通道判定(存在性语义,不计数):score = _ACCUSING verdict 组且组级
  confidence 非缺席;UI = 组 detected=true(任意 verdict 含 informational)
  + asset(attributes 陈述)+ clean(threat 块空);stix = 镜像
  _stix_export 判定点(Indicator 只产 _ACCUSING 组;attributes 产
  x_ipradar_attributes),内存载荷不落盘;
- 采样契约:infra 全量,truth/neutral/consensus 稳定 seed ≤300;
- 三桶:violation = observed × ruled illegal;pending = ruled pending
  (观测与否都进,治理债可见);agreement = observed × legal;未观测格
  无话(无证据即无话);
- 证据 ≤3 IP + 涉及源名;lookup 失败即抛(2026-10-10 假零判例);
- CLI:--matrix-scan [--json] 退出码 0/1/2 = 干净/有 pending/有 violation。

全部 fake/stub(合成 registry fixture + tmp 资产 + 内存裁决矩阵),
零网络零 DB;真实扫描归控制器(Task 3),本文件只钉引擎与 CLI 契约。
"""
import json

import pytest

from ipdb._eval.__main__ import main
from ipdb._eval.assets import AssetMeta, fingerprint, save_asset
from ipdb._eval.layered import assemble_four_layers
from ipdb._eval.matrix import (CHANNELS, LABELS, LAYERS, RuledCell,
                               SemanticMatrix, save_matrix)
from ipdb._eval.matrix_scan import (CellObservation, Evidence,
                                    channel_labels, diff_matrix,
                                    ip_observations, layer_sample,
                                    render_md, run_matrix_scan, scan_layers)


# ── 合成 fixture(内存 source 假显形) ──────────────────────────

def _save_layer(root, kind, ips, version="v1"):
    save_asset(root / kind, ips, AssetMeta(
        version=version, kind=kind, fingerprint=fingerprint(ips),
        member_count=len(ips), params={}, eval_env="monthly",
        created_at="2026-10-19"))


_PREC = {"malicious": 0, "suspicious": 1, "benign": 2, "informational": 3}


def _group(ctype, verdict, *, detected=None, confidence=90,
           details=(("src", "malicious"),)):
    return {"type": ctype, "verdict": verdict,
            "detected": (verdict in ("malicious", "suspicious")
                         if detected is None else detected),
            "confidence": confidence,
            "details": [{"source": s, "verdict": v, "reliability": 0.5}
                        for s, v in details]}


def _payload(ip, groups=(), attributes=None):
    """to_dict 形状载荷;threat 块按 detected 组重融合(引擎同款选角)。"""
    groups = list(groups)
    detected = [g for g in groups if g["detected"]]
    if detected:
        worst = min(detected, key=lambda g: _PREC[g["verdict"]])
        threat = {"verdict": worst["verdict"], "confidence": 90,
                  "types": sorted({g["type"] for g in detected}),
                  "is_cdn": False}
    else:
        threat = {"verdict": "benign", "confidence": 0, "types": [],
                  "is_cdn": False}
    return {"ip": ip, "classifications": {g["type"]: g for g in groups},
            "threat": threat, "attributes": attributes or {}}


def _lookup(results):
    miss = _payload("miss")
    def fn(ip):
        return results.get(ip, miss)
    return fn


# ── 通道判定(单一真源 ip_observations) ────────────────────────


def test_accusing_group_scores_and_exports_on_all_channels():
    p = _payload("203.0.113.9", [_group("blacklist", "malicious",
                                        details=(("feed_a", "malicious"),))])
    cl = channel_labels(p)
    assert cl["score"] == {"malicious"}
    assert cl["UI"] == {"malicious"}
    assert cl["stix"] == {"malicious"}       # 有指控显形 → 无 clean


def test_score_requires_nonabsent_group_confidence():
    p = _payload("203.0.113.9",
                 [_group("blacklist", "malicious", confidence=None)])
    cl = channel_labels(p)
    assert cl["score"] == {"clean"}          # 组级 confidence 缺席 = 未进 P
    assert cl["UI"] == {"malicious"}         # UI 照显(detected)
    assert cl["stix"] == {"malicious"}       # _stix_export 不看 confidence


def test_informational_shows_on_ui_only():
    # 8.8.8.8 事故形状:infra IP 经存档章显形 spam
    p = _payload("8.8.8.8", [_group("spam", "informational", detected=True,
                                    details=(("firehol_abusers_30d",
                                              "informational"),))])
    cl = channel_labels(p)
    assert cl["UI"] == {"informational"}     # verdict 任意,含 informational
    assert cl["score"] == {"clean"}          # 存档证人不进 P
    assert cl["stix"] == {"clean"}           # 存档章不产 Indicator


def test_benign_detected_group_shows_on_ui():
    p = _payload("203.0.113.9", [_group("abuse", "benign", detected=True,
                                        details=(("feed_b", "benign"),))])
    cl = channel_labels(p)
    assert cl["UI"] == {"benign"}
    assert cl["score"] == {"clean"} and cl["stix"] == {"clean"}


def test_asset_statements_surface_on_ui_and_stix_not_score():
    attrs = {"is_hosting": [{"source": "cloud_ranges", "value": True,
                             "native_type": "AWS"}]}
    cl = channel_labels(_payload("52.95.116.115", attributes=attrs))
    assert "asset" in cl["UI"] and "asset" in cl["stix"]
    assert "asset" not in cl["score"]        # 纯陈述不进 P(_types.AssetStatement)
    assert "clean" in cl["UI"]               # threat 块空 = clean 显形


def test_empty_payload_is_clean_on_all_channels():
    assert channel_labels(_payload("203.0.113.9")) == {
        "score": {"clean"}, "stix": {"clean"}, "UI": {"clean"}}


def test_evidence_sources_score_accusing_only_ui_all():
    p = _payload("203.0.113.9",
                 [_group("blacklist", "malicious",
                         details=(("feed_a", "malicious"),
                                  ("feed_arch", "informational")))])
    obs = ip_observations(p)
    assert obs[("score", "malicious")] == {"feed_a"}        # 存档证人不进 P
    assert obs[("UI", "malicious")] == {"feed_a", "feed_arch"}  # UI 展示全员


# ── 采样契约 ──────────────────────────────────────────────────


def test_layer_sample_infra_full_others_capped_and_stable():
    ips = [f"198.51.{i // 250}.{i % 250}" for i in range(400)]
    assert layer_sample("infra", ips, seed=1) == ips        # infra 全量
    a = layer_sample("truth", ips, seed=1)
    b = layer_sample("truth", ips, seed=1)
    assert a == b and len(a) == 300 and len(set(a)) == 300  # 同 seed 同序封顶
    assert layer_sample("truth", ips, seed=2) != a          # 异 seed 异序
    small = ips[:50]
    assert sorted(layer_sample("neutral", small, seed=1)) == sorted(small)  # 不足全取


# ── diff 三桶 ─────────────────────────────────────────────────


def _synth_matrix(overrides):
    cells = {(l, b, c): RuledCell(state="illegal", note="conservative-default")
             for l in LAYERS for b in LABELS for c in CHANNELS}
    cells.update(overrides)
    return SemanticMatrix(cells=cells)


def _obs(layer, label, channel, ips_sources):
    ev = tuple(Evidence(ip=ip, sources=tuple(srcs))
               for ip, srcs in ips_sources)
    return {(layer, label, channel):
            CellObservation(cell=(layer, label, channel), evidence=ev)}


def test_diff_three_buckets():
    m = _synth_matrix({
        ("infra", "informational", "UI"):
            RuledCell(state="pending", note="待裁:8.8.8.8 事故"),
        ("truth", "malicious", "score"):
            RuledCell(state="legal", provenance="ADR 0002"),
    })
    obs = {}
    obs.update(_obs("infra", "informational", "UI",
                    [("8.8.8.8", ["firehol_abusers_30d"])]))
    obs.update(_obs("truth", "malicious", "score", [("1.2.3.4", ["feed_a"])]))
    obs.update(_obs("infra", "asset", "stix",
                    [("52.95.116.115", ["cloud_ranges"])]))
    buckets = diff_matrix(m, obs)
    assert {e["cell"] for e in buckets["violation"]} == {"infra|asset|stix"}
    assert buckets["violation"][0]["evidence"] == [
        {"ip": "52.95.116.115", "sources": ["cloud_ranges"]}]
    assert {e["cell"] for e in buckets["pending"]} == {"infra|informational|UI"}
    assert buckets["pending"][0]["note"] == "待裁:8.8.8.8 事故"
    assert buckets["pending"][0]["evidence"] == [
        {"ip": "8.8.8.8", "sources": ["firehol_abusers_30d"]}]
    agreement = {e["cell"]: e for e in buckets["agreement"]}
    assert set(agreement) == {"truth|malicious|score"}
    assert agreement["truth|malicious|score"]["provenance"] == "ADR 0002"


def test_diff_pending_cell_surfaced_even_unobserved():
    # ruled pending 格不论观测与否都进 pending 桶(治理债可见)
    m = _synth_matrix({("neutral", "benign", "stix"):
                       RuledCell(state="pending", note="待裁")})
    buckets = diff_matrix(m, {})
    assert [e["cell"] for e in buckets["pending"]] == ["neutral|benign|stix"]
    assert buckets["pending"][0]["evidence"] == []
    assert buckets["violation"] == [] and buckets["agreement"] == []


def test_diff_unobserved_illegal_stays_silent():
    # 未观测非法格无断言(无证据即无话),不冒充 agreement
    assert diff_matrix(_synth_matrix({}), {}) == {
        "violation": [], "pending": [], "agreement": []}


# ── 扫描:证据封顶 / 失败传播 / NO-LAYER 哨兵 ──────────────────


def test_scan_caps_evidence_at_three(tmp_path):
    ips = [f"198.51.0.{i}" for i in range(1, 6)]
    _save_layer(tmp_path, "infra", ips)
    fn = _lookup({ip: _payload(ip, [_group(
        "spam", "informational", detected=True,
        details=(("firehol_abusers_30d", "informational"),))]) for ip in ips})
    obs, stats = scan_layers(fn, assemble_four_layers(tmp_path))
    o = obs[("infra", "informational", "UI")]
    assert len(o.evidence) == 3                       # ≤3 IP
    assert o.evidence[0].ip == ips[0]                 # 查询序前 3
    assert o.evidence[0].sources == ("firehol_abusers_30d",)
    assert stats["infra"] == {"status": "OK", "members": 5, "sampled": 5}
    for kind in ("truth", "neutral", "consensus"):
        assert stats[kind]["status"] == "NO-LAYER"    # 缺层≠0 层,不查不观测


def test_scan_lookup_failure_propagates(tmp_path):
    _save_layer(tmp_path, "infra", ["198.51.0.1"])
    def boom(ip):
        raise RuntimeError("db down")
    with pytest.raises(RuntimeError, match="db down"):  # 假零判例:不吞
        scan_layers(boom, assemble_four_layers(tmp_path))


# ── 端到端(真 matrix.json 裁决) ──────────────────────────────


def test_run_matrix_scan_real_matrix_violation(tmp_path):
    _save_layer(tmp_path, "infra", ["8.8.8.8"])
    _save_layer(tmp_path, "truth", ["198.51.100.7"])
    fn = _lookup({
        "8.8.8.8": _payload("8.8.8.8", [_group(
            "spam", "informational", detected=True,
            details=(("firehol_abusers_30d", "informational"),))]),
        "198.51.100.7": _payload("198.51.100.7",
                                 [_group("blacklist", "malicious")]),
    })
    res = run_matrix_scan(fn, tmp_path)
    assert res["counts"] == {"violation": 1, "pending": 0, "agreement": 5}
    v = res["buckets"]["violation"][0]
    assert v["cell"] == "infra|informational|UI"      # 事故格 = 保守默认非法
    assert v["evidence"] == [{"ip": "8.8.8.8",
                              "sources": ["firehol_abusers_30d"]}]
    # truth 指控显形 = 五组合法格 → agreement 不产断言
    assert {e["cell"] for e in res["buckets"]["agreement"]} == {
        "infra|clean|score", "infra|clean|stix",
        "truth|malicious|score", "truth|malicious|UI", "truth|malicious|stix"}
    assert res["exit_code"] == 2
    assert res["layers"]["truth"] == {"status": "OK", "members": 1,
                                      "sampled": 1}


def test_run_matrix_scan_pending_only_exit1(tmp_path):
    _save_layer(tmp_path, "infra", ["8.8.8.8"])
    m = _synth_matrix({(l, "clean", c): RuledCell(state="pending",
                                                  note="待裁例")
                       for l in ("infra",) for c in CHANNELS})
    mpath = tmp_path / "matrix.json"
    save_matrix(m, mpath)
    res = run_matrix_scan(_lookup({}), tmp_path, matrix_path=mpath)
    assert res["exit_code"] == 1
    assert {e["cell"] for e in res["buckets"]["pending"]} == {
        "infra|clean|UI", "infra|clean|score", "infra|clean|stix"}
    assert res["buckets"]["violation"] == []


def test_seed_stability_same_seed_identical_result(tmp_path):
    ips = [f"198.51.{i // 250}.{i % 250}" for i in range(400)]
    _save_layer(tmp_path, "truth", ips)
    hits = {ip: _payload(ip, [_group("blacklist", "malicious")])
            for ip in ips[:200]}
    fn = _lookup(hits)
    a = run_matrix_scan(fn, tmp_path)
    b = run_matrix_scan(fn, tmp_path)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["layers"]["truth"]["sampled"] == 300    # truth 层稳定 seed ≤300


# ── CLI wiring ────────────────────────────────────────────────


class _Result:
    """_real_registry().lookup 包装层调 .to_dict() —— 假 LookupResult。"""
    def __init__(self, payload):
        self._p = payload
    def to_dict(self):
        return self._p


def _install_registry(monkeypatch, fn):
    import ipdb._registry as reg
    monkeypatch.setattr(reg, "_sources", [])
    monkeypatch.setattr(reg, "load_db", lambda: None)
    monkeypatch.setattr(reg, "lookup",
                        lambda ip, allowed_sources=None, *, asof=None:
                        _Result(fn(ip)))


_811 = _payload("8.8.8.8", [_group("spam", "informational", detected=True,
                                   details=(("firehol_abusers_30d",
                                             "informational"),))])


def test_cli_matrix_scan_json_exit2(monkeypatch, tmp_path, capsys):
    _save_layer(tmp_path, "infra", ["8.8.8.8"])
    _install_registry(monkeypatch, _lookup({"8.8.8.8": _811}))
    with pytest.raises(SystemExit) as ei:
        main(["--matrix-scan", "--assets-dir", str(tmp_path), "--json"])
    assert ei.value.code == 2
    res = json.loads(capsys.readouterr().out)
    assert res["counts"]["violation"] == 1
    assert res["eval_env"] == "dev"
    assert res["buckets"]["violation"][0]["cell"] == "infra|informational|UI"


def test_cli_matrix_scan_clean_exit0(monkeypatch, tmp_path, capsys):
    _save_layer(tmp_path, "infra", ["8.8.8.8"])
    _install_registry(monkeypatch, _lookup({}))
    with pytest.raises(SystemExit) as ei:
        main(["--matrix-scan", "--assets-dir", str(tmp_path), "--json"])
    assert ei.value.code == 0
    res = json.loads(capsys.readouterr().out)
    assert res["counts"] == {"violation": 0, "pending": 0, "agreement": 3}


def test_cli_matrix_scan_pending_exit1(monkeypatch, tmp_path, capsys):
    _save_layer(tmp_path, "infra", ["8.8.8.8"])
    m = _synth_matrix({(l, "clean", c): RuledCell(state="pending",
                                                  note="待裁例")
                       for l in ("infra",) for c in CHANNELS})
    mpath = tmp_path / "matrix.json"
    save_matrix(m, mpath)
    from ipdb._eval import matrix_scan
    monkeypatch.setattr(matrix_scan, "MATRIX_PATH", mpath)
    _install_registry(monkeypatch, _lookup({}))
    with pytest.raises(SystemExit) as ei:
        main(["--matrix-scan", "--assets-dir", str(tmp_path), "--json"])
    assert ei.value.code == 1


def test_cli_matrix_scan_missing_matrix_json_envelope_rc2(monkeypatch,
                                                          tmp_path, capsys):
    # 终审 M-1:matrix.json 缺失 → rc 2 + JSON 错误信封(--exclusive 先例,
    # §5.2 要信封不裸栈),不再是裸栈 rc 1;pending=1 语义保持无歧义
    _install_registry(monkeypatch, _lookup({}))
    from ipdb._eval import matrix_scan
    monkeypatch.setattr(matrix_scan, "MATRIX_PATH", tmp_path / "nope.json")
    with pytest.raises(SystemExit) as ei:
        main(["--matrix-scan", "--assets-dir", str(tmp_path), "--json"])
    assert ei.value.code == 2
    res = json.loads(capsys.readouterr().out)
    assert res["error"]["code"] == "matrix_scan_failed"
    assert "nope.json" in res["error"]["message"]


def test_cli_matrix_scan_human_md(monkeypatch, tmp_path, capsys):
    _save_layer(tmp_path, "infra", ["8.8.8.8"])
    _install_registry(monkeypatch, _lookup({"8.8.8.8": _811}))
    with pytest.raises(SystemExit) as ei:
        main(["--matrix-scan", "--assets-dir", str(tmp_path)])
    assert ei.value.code == 2
    out = capsys.readouterr().out
    assert "待裁" in out                          # 建议栏「待裁」
    assert "8.8.8.8" in out and "firehol_abusers_30d" in out
    assert "informational" in out and "violation 1" in out


# ── md 报告 ───────────────────────────────────────────────────


def test_render_md_violation_row_carries_evidence_and_pending_column():
    res = {
        "seed": 20261018, "sample_n": 300, "eval_env": "dev",
        "assets_dir": "/x",
        "layers": {"infra": {"status": "OK", "members": 1, "sampled": 1}},
        "buckets": {
            "violation": [{"cell": "infra|informational|UI",
                           "state": "illegal",
                           "note": "conservative-default",
                           "evidence": [{"ip": "8.8.8.8",
                                         "sources": ["firehol_abusers_30d"]}]}],
            "pending": [], "agreement": []},
        "counts": {"violation": 1, "pending": 0, "agreement": 0},
        "exit_code": 2}
    md = render_md(res)
    assert "infra\\|informational\\|UI" in md     # md 表格转义管道
    assert "8.8.8.8" in md and "firehol_abusers_30d" in md
    assert "待裁" in md


# ── stix 镜像守卫(Task 2 终审 Minor-1b) ──────────────────────

try:
    import stix2 as _stix2  # noqa: F401
    _HAS_STIX2 = True
except ImportError:
    _HAS_STIX2 = False


@pytest.mark.skipif(not _HAS_STIX2, reason="stix2 not installed")
def test_stix_mirror_channel_matches_real_export():
    """channel_labels 的 stix 通道是 _stix_export 判定点的镜像(模块注释
    同步义务句):上游判定点变更而镜像未同步时,本守卫炸(Minor-1b,
    Task 2 终审遗留)。合成 LookupResult = 指控 + 存档 + attributes 三证人
    (tests/core/test_stix.py fixture 先例)。"""
    from ipdb._stix_export import to_stix_bundle
    from ipdb._types import (AssetStatement, ClassificationAssessment,
                             LookupResult, MergedField, SourceAttribution)
    accusing = ClassificationAssessment(
        type="blacklist", verdict="malicious", detected=True, confidence=88,
        algorithm="corroboration",
        sources=[SourceAttribution("feed_a", True, 0.7, False)],
        corroborated=False,
        details=[{"source": "feed_a", "verdict": "malicious",
                  "reliability": 0.7}])
    archived = ClassificationAssessment(
        type="spam", verdict="informational", detected=True, confidence=0,
        algorithm="corroboration", sources=[], corroborated=False,
        details=[{"source": "firehol_abusers_30d", "verdict": "informational",
                  "reliability": 0.5}])
    lr = LookupResult(
        ip="203.0.113.9",
        country=MergedField("N/A", 0, "voting", []),
        city=MergedField("N/A", 0, "voting", []),
        asn=MergedField(0, 0, "voting", []),
        as_name=MergedField("N/A", 0, "voting", []),
        ip_range=MergedField("N/A", 0, "voting", []),
        is_isp=False,
        classifications={"blacklist": accusing, "spam": archived},
        attributes={"is_hosting": [AssetStatement("cloud_ranges", True,
                                                  "AWS")]})
    stix_labels = channel_labels(lr.to_dict())["stix"]
    assert stix_labels == {"malicious", "asset"}   # 存档章不产 Indicator
    bundle = to_stix_bundle(lr)
    indicators = [o for o in bundle["objects"] if o["type"] == "indicator"]
    assert {i["x_verdict"] for i in indicators} == \
        stix_labels - {"asset", "clean"}
    addr = next(o for o in bundle["objects"] if o["type"].startswith("ipv"))
    assert ("x_ipradar_attributes" in addr) == ("asset" in stix_labels)
