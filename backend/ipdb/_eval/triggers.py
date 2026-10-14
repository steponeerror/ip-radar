"""人裁触发集 S1-S4 (spec 2026-10-12-eval-loop-hardening-design.md §3.1, §8
S1-S4): 纯函数升旗器 —— 只产 mandatory_review/bands 旗标行, 零写路径。

声明 r 红线(测量建言, 人裁终局): 触发集**只升旗强制人裁, 不自动动作**
—— 本模块无任何写路径(不动权重/配置/源开关); 旗标行由 T6 接线进 gate
报告, 处置归人。

四个触发器(spec §3.1 措辞, 阈值出处逐条内注):
- S1 抄尺防护: 候选键集对 truth **资产成员**(非原始 raw, 装配哨兵口径)
  的包含度 >0.5 且非蜜罐方法学声明 → 判「尺派生」升旗。
- S2 好得可疑: 「独有命中×低 OC 象限」或「真值层 delta 显著正且 OC 低」。
- S3 OC 极端: OC≥0.9 且非声明派生 → 人裁; 0.7-0.9 → 敏感带 report-only。
- S4 层回归: 任一层 bootstrap p<0.05 且该层 delta 为恶化方向, 且 verdict
  非 NEGATIVE/MIXED(该二态已由基础触发集收)。
"""
from __future__ import annotations

from .layered import PRIORITY

# ── 阈值(spec 有数字者照录; S2 无数字, 锚既有判读, 见各注) ─────
# S1(spec §3.1: 「包含度>0.5」): 恰 0.5 不旗。
S1_CONTAINMENT = 0.5
# S3(spec §3.1: 「OC≥0.9」与「0.7-0.9 OC 敏感带: 报告不触发」):
# [0.7, 0.9) 入带, ≥0.9 入人裁。
S3_OC_MANDATORY = 0.9
S3_OC_BAND = "0.7-0.9"
# S2 低 OC 口径: spec §3.1 无数字; 取 S3 敏感带下沿 0.7(= 既有 advisory
# 关切地板 config.OC_SUSPICION 同值)—— 低于带下沿即「低」。常量独立
# 定义: 触发集阈值不随仪器卫生调参(OC_SUSPICION 是 pairwise OC)漂移。
S2_LOW_OC = 0.7
# S2 独有命中口径: spec §3.1 无数字; 取 C1 specialist 分支
# config.SPECIALIST_UNIQUE_SHARE 同值 0.8 —— 同概念「独有命中份额高」
# 的既有判读。独立常量同上由: 不与 rank 门调参耦合。
S2_UNIQUE_SHARE = 0.8
# S2/S4 显著性(spec §3.1 S4: 「bootstrap p<0.05」; S2「显著」同口径):
# 消费 T7 paired_bootstrap 的 p_one_sided —— 其已按观测方向取对立侧
# (significance.py), 故 p<α 且方向判定即「该方向显著」。
ALPHA = 0.05

# 基础触发集(spec §3.1: 「NEGATIVE/MIXED/NO-DATA 基础上, S3/S4 扩」)
BASE_REVIEW_STATES = frozenset({"NEGATIVE", "MIXED", "NO-DATA"})
# S4 良性门(spec §3.1: 「verdict 非 NEGATIVE/MIXED」—— 该二态基础集已
# 收, S4 只补其外; NO-DATA 不豁免: 死源四层 delta 仍可恶化)
S4_EXCLUDED_STATES = frozenset({"NEGATIVE", "MIXED"})

# 各层「恶化方向」(spec §2.1 层定义表定角色, 方向随之):
# truth=威胁真值层(非循环真值锚) → 命中率**降**=恶化(漏真阳性);
# infra=非指控基础设施层(误报锚)/ neutral=中性层(误报基线) → 命中率
# **升**=恶化(演示 A 判例方向: 关掉 x4bnet_vpn 误报 5.63→1.01);
# consensus=共识代理层(Q22 降格诊断层, 回声/源坍塌监测) → 命中率**升**
# =恶化(指控密度抬升即回声/坍塌监测的关切方向)。未知 kind 无角色即无
# 方向, 不猜(宁少算)。
_WORSEN_SIGN = {"truth": -1, "infra": 1, "neutral": 1, "consensus": 1}


def _boot_p(layer_delta: dict | None) -> float | None:
    """层 delta → paired bootstrap p_one_sided; None/NO-LAYER/stats 缺
    (n=0 无定义) → None, 不冒充。"""
    if not layer_delta:
        return None
    stats = layer_delta.get("stats")
    if not stats:
        return None
    return stats.get("paired_bootstrap", {}).get("p_one_sided")


def s1_yardstick_derivation(candidate_keyset, truth_members,
                            honeypot_declared: bool) -> dict:
    """S1 抄尺防护(spec §3.1 S1): 包含度=|候选键集 ∩ truth 资产成员| /
    |候选键集|(R3: 候选抄真值语料的方向, 分母=候选键集); >0.5 且非蜜罐
    方法学声明 → 旗。空候选键集不触发(containment=0.0 不冒充)。truth
    侧用资产成员(装配哨兵口径), 非原始 raw —— 接线(T6)职责。"""
    cand = set(candidate_keyset or ())
    inter = len(cand & set(truth_members or ()))
    containment = inter / len(cand) if cand else 0.0
    return {"flag": (not honeypot_declared) and containment > S1_CONTAINMENT,
            "containment": containment}


def s2_too_good(unique_share, oc, truth_delta) -> dict:
    """S2 好得可疑绊线(spec §3.1 S2): ①独有命中份额≥S2_UNIQUE_SHARE ×
    OC<S2_LOW_OC 象限, 或 ②真值层 delta 显著正(rate_delta>0 且 bootstrap
    p_one_sided<ALPHA)且 OC 低。任一臂输入无定义(None/NO-LAYER)→ 该臂
    不评(宁少算: 谓词无定义不冒充触发)。亚采样投毒形态锚: R10 必列混杂
    ①「OC 低/MC≫θ/fp=0」。"""
    if oc is None:
        return {"flag": False}
    low_oc = oc < S2_LOW_OC
    quadrant = (low_oc and unique_share is not None
                and unique_share >= S2_UNIQUE_SHARE)
    d = truth_delta.get("rate_delta") if truth_delta else None
    truth_sig_pos = (low_oc and d is not None and d > 0
                     and (p := _boot_p(truth_delta)) is not None and p < ALPHA)
    return {"flag": quadrant or truth_sig_pos}


def s3_oc_extreme(oc, declared_derived: bool) -> dict:
    """S3 OC 极端(spec §3.1 S3): OC≥0.9 且非声明派生 → 人裁; 0.7≤OC<0.9
    → 敏感带 band 标注(report-only, 不入 mandatory_review —— spec「0.7-0.9
    OC 敏感带: 报告不触发」)。声明派生豁免只作用于极端档; 带是纯报告
    注记, 与声明无关。oc 无定义(None)→ 无旗无带。"""
    if oc is None:
        return {"flag": False, "band": ""}
    if oc >= S3_OC_MANDATORY:
        return {"flag": not declared_derived, "band": ""}
    return {"flag": False,
            "band": S3_OC_BAND if oc >= 0.7 else ""}


def s4_layer_regression(layer_deltas: dict, verdict_state: str) -> dict:
    """S4 层回归(spec §3.1 S4): 任一层 bootstrap p_one_sided<ALPHA 且
    rate_delta 在该层恶化方向(_WORSEN_SIGN), 且 verdict ∉ {NEGATIVE,
    MIXED} → 旗。NO-LAYER(None)/stats=None(n=0 无定义)层跳过; 未知 kind
    无方向不猜。层序按装配优先序(PRIORITY)定序。"""
    layers: list[str] = []
    if verdict_state not in S4_EXCLUDED_STATES:
        for kind in PRIORITY:
            delta = layer_deltas.get(kind)
            if not delta or kind not in _WORSEN_SIGN:
                continue
            d = delta.get("rate_delta")
            p = _boot_p(delta)
            if d is None or p is None or p >= ALPHA:
                continue
            if d * _WORSEN_SIGN[kind] > 0:
                layers.append(kind)
    return {"flag": bool(layers), "layers": layers}


def evaluate_triggers(gate_outputs: dict) -> dict:
    """汇总(R2: 基础触发集 + S1-S4): 输出旗标行, 零写路径。

    消费键(T6 接线契约; T4 run_gate payload 已含前两键, 其余为 T6 增补,
    **缺键 → 对应触发不评**(宁少算, 谓词无定义不冒充触发)):
    - ``candidate_stratum.verdict.state``: 8 态(T4 已有)→ 基础集 + S4 良性门
    - ``deltas``: {kind: layer_delta|None}(T4 已有)→ S4 + S2 真值层 delta
    - ``candidate_keyset`` / ``truth_members`` / ``honeypot_declared`` → S1
    - ``oc``(stratum metrics oc.value)→ S2/S3
    - ``unique_share``(suite model 件)→ S2 象限臂
    - ``declared_derived``(registry derived attr / DERIVED_SOURCES)→ S3
    """
    mandatory: list[str] = []
    bands: list[str] = []
    state = (gate_outputs.get("candidate_stratum", {})
             .get("verdict", {}).get("state"))
    oc = gate_outputs.get("oc")
    deltas = gate_outputs.get("deltas") or {}
    truth_delta = deltas.get("truth")

    if state in BASE_REVIEW_STATES:
        mandatory.append(f"基础触发集: verdict={state} → 强制人裁 (spec §3.1)")

    if "candidate_keyset" in gate_outputs and "truth_members" in gate_outputs:
        r1 = s1_yardstick_derivation(
            gate_outputs["candidate_keyset"], gate_outputs["truth_members"],
            bool(gate_outputs.get("honeypot_declared", False)))
        if r1["flag"]:
            mandatory.append(
                f"S1 尺派生: 候选键集对 truth 资产成员包含度="
                f"{r1['containment']:.2f}>{S1_CONTAINMENT} 且非蜜罐方法学"
                f"声明 → 强制人裁 (spec §3.1 S1)")

    if s2_too_good(gate_outputs.get("unique_share"), oc, truth_delta)["flag"]:
        us = gate_outputs.get("unique_share")
        d = truth_delta.get("rate_delta") if truth_delta else None
        mandatory.append(
            f"S2 好得可疑: 独有命中份额={us if us is not None else 'NA'}, "
            f"OC={oc:.2f}<{S2_LOW_OC}, 真值层 rate Δ="
            f"{f'{d:+.2f}' if d is not None else 'NA'} → 强制人裁 "
            f"(spec §3.1 S2)")

    if oc is not None:
        r3 = s3_oc_extreme(oc, bool(gate_outputs.get("declared_derived",
                                                     False)))
        if r3["flag"]:
            mandatory.append(
                f"S3 OC≥{S3_OC_MANDATORY} 未声明派生: OC={oc:.2f} → "
                f"强制人裁 (spec §3.1 S3)")
        if r3["band"]:
            bands.append(
                f"S3 OC 敏感带 {r3['band']}: OC={oc:.2f} → report-only "
                f"标注, 不触发人裁 (spec §3.1)")

    r4 = s4_layer_regression(deltas, state)
    if r4["flag"]:
        mandatory.append(
            f"S4 层 delta 显著恶化: {', '.join(r4['layers'])} "
            f"(bootstrap p<{ALPHA} 且恶化方向) 而 verdict={state} 非 "
            f"NEGATIVE/MIXED → 强制人裁 (spec §3.1 S4)")

    return {"mandatory_review": mandatory, "bands": bands}
