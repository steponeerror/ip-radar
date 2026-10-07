"""log-odds 评分内核(spec 2026-08-29)。

纯函数、零外部依赖;被 _merge.py(标量/威胁)与 _registry.py(asset)消费。
语义:r = 该源单独作证时答对的频率(单源 conf = r);证据随龄指数衰减,
方向不变强度衰减;多类别带背景质量(未观测答案的隐含概率)。
"""
import math
from datetime import datetime, timezone

DEFAULT_HALF_LIFE_DAYS: float = 60.0
# Phase 2 从数据估(MISP §VI 方法);本期空表 = 全类型统一 60d(spec §3.1)
DECAY_OVERRIDES: dict[str, float] = {}
# 谱系去重的派生源集合(R1-F1):种子 = 无 _registry 导入时的兜底;
# _registry 导入时按源 class attr(derived=True)fill-in-place 覆盖
# (clear+update,同 _merge.SOURCE_RELIABILITY 模式——_eval/audit.py 值
# 绑定本对象身份,严禁重新赋值)。新聚合器声明 derived=True 即入谱系
# 去重,无需改中央字面量表。
DERIVED_SOURCES: set[str] = {
    "firehol", "ipsum", "otx", "otx_subscribed", "greensnow", "drb_ra"}
# 谱系锚(DQ-1,审计 2026-10-06):target → anchor。target 的块清单 ⊇
# anchor 原创清单(emerging_threats ⊇ spamhaus DROP,/12 巨块回声
# LMDB 实证):anchor 在场且系数不低于 target 时 target 视为回声剔除
# (宁少算);anchor 缺席或更弱 → target 保留。firehol⊃DROP 已由
# DERIVED_SOURCES 覆盖,不入此表。
LINEAGE_ANCHORS: dict[str, str] = {"emerging_threats": "spamhaus"}


def logit(p: float) -> float:
    """ln(p/(1-p));上界钳 0.98 防发散(spec §3.4)。"""
    p = min(p, 0.98)
    return math.log(p / (1 - p))


def half_life_for(ctype: str | None) -> float:
    return DECAY_OVERRIDES.get(ctype or "", DEFAULT_HALF_LIFE_DAYS)


def decay_factor(age_days: float | None,
                 half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    if age_days is None:
        return 1.0
    return 2.0 ** (-age_days / half_life_days)


def parse_first_seen(value) -> datetime | None:
    """ISO 解析 first_seen(Z 后缀容忍,naive 视作 UTC);缺失/不可解析
    → None。打分期(_age_days)与 rebuild 绊线(_source_base)共用同一口径
    ——同一函数,免得两边判法漂移。"""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _age_days(first_seen, now: datetime | None) -> float | None:
    ts = parse_first_seen(first_seen)
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 86400.0)


def coefficient(r: float, first_seen: str | None, ctype: str | None = None,
                now: datetime | None = None) -> float:
    """证据系数 = logit(r) × 2^(−age/h);符号随证据方向保留(B3)。"""
    age = _age_days(first_seen, now)
    return logit(r) * decay_factor(age, half_life_for(ctype))


def dedup_lineage(coeffs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """谱系去重(保守近似,spec §3.3):存在非 derived 源时,剔除系数
    不高于最强非 derived 的 derived 源(相等也剔——宁少算勿重算);
    全 derived 则全保留。谱系锚(LINEAGE_ANCHORS)同判式:target 在
    其锚源在场且锚系数不低于它时同样剔除(锚缺席或更弱 → 保留)。"""
    non_derived_max = max((c for s, c in coeffs if s not in DERIVED_SOURCES),
                          default=None)
    if non_derived_max is None:
        return list(coeffs)
    kept: list[tuple[str, float]] = []
    for s, c in coeffs:
        if s in DERIVED_SOURCES and c <= non_derived_max:
            continue
        anchor = LINEAGE_ANCHORS.get(s)
        if anchor is not None:
            anchor_max = max((c2 for s2, c2 in coeffs if s2 == anchor),
                             default=None)
            if anchor_max is not None and anchor_max >= c:
                continue
        kept.append((s, c))
    return kept


def assertion_confidence(coeffs: list[float]) -> int:
    """σ(Σcoeff) → 0-100;空列表 = 50(中立)。"""
    s = sum(coeffs)
    p = 1.0 / (1.0 + math.exp(-s))
    return round(p * 100)


def multicategory_posterior(s_by_value: dict) -> dict:
    """P(v) = exp(s_v)/(Σ_u exp(s_u) + 1);背景质量 1 = 「未观测答案」
    (spec 审计 A1:否则单源 conf=100,违反单源 conf=r)。"""
    exps = {v: math.exp(s) for v, s in s_by_value.items()}
    total = sum(exps.values()) + 1.0
    return {v: e / total for v, e in exps.items()}
