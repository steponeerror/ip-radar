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
DERIVED_SOURCES = frozenset({"firehol", "ipsum", "otx", "greensnow", "drb_ra"})


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


def _age_days(first_seen, now: datetime | None) -> float | None:
    if not first_seen:
        return None
    try:
        ts = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
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
    全 derived 则全保留。"""
    non_derived_max = max((c for s, c in coeffs if s not in DERIVED_SOURCES),
                          default=None)
    if non_derived_max is None:
        return list(coeffs)
    return [(s, c) for s, c in coeffs
            if s not in DERIVED_SOURCES or c > non_derived_max]


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
