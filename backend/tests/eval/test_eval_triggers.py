# backend/tests/eval/test_eval_triggers.py
"""人裁触发集 S1-S4 测试 (spec 2026-10-12-eval-loop-hardening-design.md §3.1)。

契约 (Phase 2 T5; 输出=旗标行, 零写路径 —— 声明 r: 触发集只升旗强制
人裁, 不自动动作):
- S1 抄尺防护: 包含度 = |候选键集 ∩ truth 资产成员| / |候选键集|
  (R3: 候选抄真值语料的方向; 分母=候选键集), >0.5 且非蜜罐方法学声明
  → 旗; 空候选键集不触发 (containment=0.0, 不冒充)。
- S2 好得可疑: 「独有命中份额≥0.8 × OC<0.7」象限, 或真值层 delta
  显著正 (rate_delta>0 且 bootstrap p_one_sided<0.05) 且 OC<0.7 → 旗;
  任一臂输入无定义 (None) → 该臂不评。
- S3 OC 极端: OC≥0.9 且非声明派生 → 人裁; 0.7≤OC<0.9 → 敏感带
  report-only band 标注 (不入 mandatory_review)。
- S4 层回归: 任一层 bootstrap p_one_sided<0.05 且 rate delta 在该层
  恶化方向, 且 verdict ∉ {NEGATIVE, MIXED} → 旗; 恶化方向按层角色
  (§2.1 层定义: truth=威胁真值锚 ↓恶化; infra/neutral=误报锚与基线
  ↑恶化, 演示 A 判例方向; consensus=Q22 诊断层 ↑恶化); NO-LAYER(None)
  与 stats=None(n=0 无定义)层跳过不评。
- evaluate_triggers(gate_outputs): 基础触发集 (verdict∈{NEGATIVE,
  MIXED, NO-DATA}) + S1-S4 汇总; T6 接线增补键 (candidate_keyset/
  truth_members/honeypot_declared/oc/unique_share/declared_derived)
  缺省 → 对应触发不评 (宁少算, 不冒充触发)。
"""
from ipdb._eval.triggers import (evaluate_triggers, s1_yardstick_derivation,
                                 s2_too_good, s3_oc_extreme,
                                 s4_layer_regression)

_TRUTH = [f"10.0.0.{i}" for i in range(1, 11)]


def _layer_delta(rate_delta, p, *, n=10):
    """T4 gate._layer_delta 落地形态的最小构型 (triggers 只读 rate_delta
    与 stats.paired_bootstrap.p_one_sided, 其余键带全保形)。"""
    return {
        "n": n, "off_hits": 0, "on_hits": 0,
        "rate_off": 0.0, "rate_on": rate_delta, "rate_delta": rate_delta,
        "stats": {"paired_bootstrap": {
            "delta": rate_delta, "ci_lo": rate_delta - 0.01,
            "ci_hi": rate_delta + 0.01, "p_one_sided": p},
            "mcnemar": {"b": 0, "c": 0, "p": 1.0}},
        "k_all": {}, "k_nonhoneypot": {},
    }


def _four_layers(**over):
    """四层全不触发的基线, 单层覆写。"""
    base = {"truth": _layer_delta(0.0, 1.0), "infra": _layer_delta(0.0, 1.0),
            "neutral": _layer_delta(0.0, 1.0),
            "consensus": _layer_delta(0.0, 1.0)}
    base.update(over)
    return base


def _gate(*, state="POSITIVE-VERIFIED", deltas=None, **extra):
    """T4 run_gate payload 最小形 + T6 接线增补键 (extra)。"""
    payload = {
        "candidate_stratum": {"verdict": {"state": state}},
        "deltas": deltas if deltas is not None else _four_layers(),
    }
    payload.update(extra)
    return payload


# ── S1 抄尺防护 (spec §3.1 S1) ────────────────────────────────


def test_s1_flags_containment_above_half():
    cand = _TRUTH[:6] + [f"10.9.9.{i}" for i in range(1, 5)]  # 6/10 重叠
    assert s1_yardstick_derivation(cand, _TRUTH, honeypot_declared=False) == {
        "flag": True, "containment": 0.6}
    # R3 方向: 分母=候选键集 —— truth 大而候选子集 → 1.0 而非小数
    assert s1_yardstick_derivation(
        ["10.0.0.1"], _TRUTH, honeypot_declared=False) == {
        "flag": True, "containment": 1.0}


def test_s1_boundary_empty_keyset_and_honeypot_exemption():
    # 恰 0.5 (spec 措辞「包含度>0.5」, 边界不旗): 10 候选中 5 真值成员
    assert s1_yardstick_derivation(
        _TRUTH[:5] + [f"10.9.9.{i}" for i in range(1, 6)], _TRUTH,
        honeypot_declared=False)["flag"] is False
    # 空候选键集不触发 (R3), containment=0.0 不冒充
    assert s1_yardstick_derivation([], _TRUTH, honeypot_declared=False) == {
        "flag": False, "containment": 0.0}
    # 蜜罐方法学声明源豁免: 整抄 (containment=1.0) 也不旗
    assert s1_yardstick_derivation(
        _TRUTH, _TRUTH, honeypot_declared=True) == {
        "flag": False, "containment": 1.0}


# ── S2 好得可疑 (spec §3.1 S2) ────────────────────────────────


def test_s2_unique_hits_low_oc_quadrant():
    quiet = _layer_delta(0.0, 1.0)
    assert s2_too_good(0.85, 0.12, quiet)["flag"] is True
    # 象限两轴缺一不旗: 独有不足 / OC 在敏感带内不算低
    assert s2_too_good(0.5, 0.12, quiet)["flag"] is False
    assert s2_too_good(0.85, 0.7, quiet)["flag"] is False
    # unique_share 无定义 (None) → 象限臂不评
    assert s2_too_good(None, 0.12, quiet)["flag"] is False


def test_s2_truth_delta_significant_positive_low_oc():
    assert s2_too_good(0.1, 0.3, _layer_delta(0.5, 0.01))["flag"] is True
    # 显著但方向非正 / 正但不显著 / OC 不低 → 不旗
    assert s2_too_good(0.1, 0.3, _layer_delta(-0.5, 0.01))["flag"] is False
    assert s2_too_good(0.1, 0.3, _layer_delta(0.5, 0.5))["flag"] is False
    assert s2_too_good(0.1, 0.8, _layer_delta(0.5, 0.01))["flag"] is False
    # truth 层 NO-LAYER (None) / OC 无定义 (None) → 不评
    assert s2_too_good(0.1, 0.3, None)["flag"] is False
    assert s2_too_good(0.9, None, _layer_delta(0.5, 0.01))["flag"] is False


# ── S3 OC 极端 + 0.7-0.9 敏感带 (spec §3.1 S3) ────────────────


def test_s3_extreme_band_and_declared_exemption():
    assert s3_oc_extreme(0.95, declared_derived=False) == {"flag": True, "band": ""}
    # 声明派生豁免 (自愿声明 → 不属「未声明派生」)
    assert s3_oc_extreme(0.95, declared_derived=True) == {"flag": False, "band": ""}
    # 0.7-0.9 敏感带: report-only band, 不入人裁 (spec「报告不触发」)
    assert s3_oc_extreme(0.85, declared_derived=False) == {"flag": False, "band": "0.7-0.9"}
    assert s3_oc_extreme(0.7, declared_derived=False)["band"] == "0.7-0.9"   # 下边界入带
    assert s3_oc_extreme(0.69, declared_derived=False) == {"flag": False, "band": ""}
    # 上边界 0.9 = 极端档 (≥0.9), 不入带
    assert s3_oc_extreme(0.9, declared_derived=False) == {"flag": True, "band": ""}


# ── S4 层回归 (spec §3.1 S4) ──────────────────────────────────


def test_s4_flags_significant_worsening_behind_benign_verdict():
    deltas = _four_layers(neutral=_layer_delta(0.2, 0.01),
                          truth=_layer_delta(0.5, 0.01))  # truth ↑=改善方向不旗
    assert s4_layer_regression(deltas, "N/A-ASSET") == {
        "flag": True, "layers": ["neutral"]}


def test_s4_directions_exclusions_and_sentries():
    # truth 召回方向: rate ↓ 显著 = 恶化 (§2.1 非循环真值锚)
    assert s4_layer_regression(_four_layers(truth=_layer_delta(-0.2, 0.01)),
                               "POSITIVE-VERIFIED") == {
        "flag": True, "layers": ["truth"]}
    # 多层同旗按装配优先序 (PRIORITY) 定序
    r = s4_layer_regression(_four_layers(infra=_layer_delta(0.1, 0.01),
                                         consensus=_layer_delta(0.1, 0.02)),
                            "MARGINAL")
    assert r["layers"] == ["infra", "consensus"]
    # verdict ∈ {NEGATIVE, MIXED} (基础触发集已收) → S4 不旗 (spec: 非
    # NEGATIVE/MIXED 才旗)
    for state in ("NEGATIVE", "MIXED"):
        assert s4_layer_regression(_four_layers(neutral=_layer_delta(0.2, 0.01)),
                                   state)["flag"] is False
    # 不显著 (p≥0.05) → 不旗
    assert s4_layer_regression(_four_layers(neutral=_layer_delta(0.2, 0.06)),
                               "MARGINAL")["flag"] is False
    # NO-LAYER 哨兵 (None 层) 跳过不评 (缺层≠恶化)
    assert s4_layer_regression(
        {"truth": None, "neutral": _layer_delta(0.2, 0.01)},
        "MARGINAL") == {"flag": True, "layers": ["neutral"]}
    # n=0 层 stats=None (配对统计无定义) 不冒充显著
    d = _layer_delta(0.2, 0.01)
    d["stats"] = None
    assert s4_layer_regression(_four_layers(neutral=d),
                               "MARGINAL")["flag"] is False
    # 未知层 kind: 无层角色即无恶化方向, 不猜 (宁少算)
    assert s4_layer_regression({"weird": _layer_delta(0.2, 0.01)},
                               "MARGINAL") == {"flag": False, "layers": []}


# ── evaluate_triggers 汇总 (R2: 基础触发集 + S1-S4) ───────────


def test_evaluate_triggers_base_set_three_states():
    for state in ("NEGATIVE", "MIXED", "NO-DATA"):
        res = evaluate_triggers(_gate(state=state))
        assert len(res["mandatory_review"]) == 1
        row = res["mandatory_review"][0]
        assert "基础触发集" in row and state in row and "强制人裁" in row
        assert res["bands"] == []
    # 其余 5 态不入基础集, 全改善 delta → 零旗标
    for state in ("POSITIVE-VERIFIED", "POSITIVE-UNVERIFIED", "MARGINAL",
                  "INSUFFICIENT-SAMPLE", "N/A-ASSET"):
        assert evaluate_triggers(_gate(state=state)) == {
            "mandatory_review": [], "bands": []}


def test_evaluate_triggers_aggregates_base_s1_s4_and_band():
    res = evaluate_triggers(_gate(
        state="NO-DATA",                       # 基础集 (S4 不排 NO-DATA)
        deltas=_four_layers(neutral=_layer_delta(0.25, 0.01)),  # S4
        candidate_keyset=_TRUTH[:8] + ["10.9.9.1", "10.9.9.2"],   # S1: 8/10=0.8
        truth_members=_TRUTH,
        honeypot_declared=False, oc=0.8,       # S3 敏感带 (不入人裁)
    ))
    assert set(res) == {"mandatory_review", "bands"}
    rows = res["mandatory_review"]
    assert len(rows) == 3
    assert "基础触发集" in rows[0] and "NO-DATA" in rows[0]
    assert any(r.startswith("S1") and "0.80" in r and "强制人裁" in r for r in rows)
    assert any(r.startswith("S4") and "neutral" in r and "N/A-ASSET" not in r
               and "NO-DATA" in r for r in rows)
    assert len(res["bands"]) == 1 and "0.7-0.9" in res["bands"][0] \
        and "0.80" in res["bands"][0]


def test_evaluate_triggers_s2_and_s3_fire_from_t6_keys():
    # S2 低 OC 象限 (与 S3 高 OC 互斥, 分例)
    res = evaluate_triggers(_gate(state="POSITIVE-UNVERIFIED",
                                  unique_share=0.85, oc=0.12,
                                  candidate_keyset=_TRUTH[:2]
                                                   + [f"10.9.9.{i}"
                                                      for i in range(1, 9)],
                                  truth_members=_TRUTH,
                                  honeypot_declared=False))  # S1: 2/10=0.2 不旗
    assert [r[:2] for r in res["mandatory_review"]] == ["S2"]
    assert "0.85" in res["mandatory_review"][0] and "0.12" in res["mandatory_review"][0]
    # S3 极端档未声明派生
    res = evaluate_triggers(_gate(state="MARGINAL", oc=0.95,
                                  declared_derived=False))
    assert [r[:2] for r in res["mandatory_review"]] == ["S3"]
    assert "0.95" in res["mandatory_review"][0]
    # 声明派生豁免 → 无旗无带
    assert evaluate_triggers(_gate(state="MARGINAL", oc=0.95,
                                   declared_derived=True)) == {
        "mandatory_review": [], "bands": []}
    # T6 增补键全缺 (纯 T4 payload) → 四触发皆不评不冒充
    assert evaluate_triggers(_gate(state="POSITIVE-VERIFIED")) == {
        "mandatory_review": [], "bands": []}
