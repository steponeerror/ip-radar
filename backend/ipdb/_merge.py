"""Merge strategies, PCR6 evidence fusion, source attribution, and enrichment."""

from datetime import datetime, timezone
from typing import Any

import ipaddress
from functools import lru_cache


@lru_cache(maxsize=200_000)
def _parse_net(cidr: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """Cached version-aware network parse. Range strings (e.g. '10.0.0.0/24',
    '2001:db8::/32') repeat heavily across queries, so parse each distinct
    string once. Family is carried by the returned network object."""
    return ipaddress.ip_network(cidr, strict=False)

from ._types import (
    SourceAttribution, MergedField, LookupResult,
    EvidenceObservation, ClassificationAssessment,
)
from . import _logodds as _lo


def to_observation(
    source: str,
    raw: dict,
    *,
    classification_type: str,
    verdict: str,
    reliability: float,
) -> EvidenceObservation:
    """Normalize a source's raw evidence dict into an EvidenceObservation.

    `raw` may override `classification_type`/`verdict` (e.g. a source whose
    type/verdict varies per entry). Unknown keys are ignored.
    """
    def _opt(key):
        return raw.get(key)

    mal = _opt("malware_name")
    return EvidenceObservation(
        source=source,
        classification_type=_opt("classification_type") or classification_type,
        verdict=_opt("verdict") or verdict,
        reliability=reliability,
        first_seen=_opt("first_seen"),
        last_seen=_opt("last_seen"),
        confidence=_opt("confidence"),
        malware_name=(mal.lower() if isinstance(mal, str) else mal),
        comment=_opt("comment"),
        reporter_count=_opt("reporter_count"),
        tags=list(_opt("tags") or []),
        native_categories=list(_opt("native_categories") or []),
        source_refs=dict(_opt("source_refs") or {}),
        extra=dict(_opt("extra") or {}),
    )


# ── Source reliability and authority maps ──
# 运行时由 _registry 从源 attr 派生填充(spec 2026-08-28 §5.1)。
# 对象身份不变:__init__/_stix_export/_to_attributions 的既有 import 靠它,
# 严禁重新赋值——只允许 clear()+update()。
SOURCE_RELIABILITY: dict[str, float] = {}
AUTHORITATIVE_SOURCES: dict[str, list[str]] = {}


# ── Attribution builder ──

def _to_attributions(
    source_values: dict[str, Any], field: str
) -> list[SourceAttribution]:
    """Build SourceAttribution list from raw {source_name: value} dict."""
    attributions = []
    auth_list = AUTHORITATIVE_SOURCES.get(field, [])
    for src, value in source_values.items():
        rel = SOURCE_RELIABILITY.get(src, 0.5)
        auth = src in auth_list
        attributions.append(SourceAttribution(src, value, rel, auth))
    return attributions


# ── Confidence helpers ──

# ── Scalar merge strategies (return MergedField) ──

class FactualVoting:
    """Voting model for factual fields (country, ASN)."""

    def __init__(self, field="country_code", default=None):
        self.field = field
        self.default = default

    def merge(self, source_values: dict[str, Any], context: dict) -> MergedField:
        attributions = _to_attributions(source_values, self.field)
        valid = [
            a for a in attributions
            if a.value is not None and a.value != "" and a.value != "N/A" and a.value != 0
        ]
        if not valid:
            return MergedField(self.default, 0, "voting", attributions)
        if len(valid) == 1:
            return MergedField(valid[0].value, 50, "voting", attributions)
        # Weighted voting (spec 2026-08-16): vote weight = reliability.
        # Winner = highest Σ weight; ties (compare after round(·,9) — different
        # multisets that are mathematically equal differ by float ulp residue)
        # break by higher max single reliability, then lexicographically
        # smallest member source name. Confidence = winner's share of total
        # weight, half-up (int(x+0.5): Python round() is banker's rounding).
        groups: dict[Any, list[SourceAttribution]] = {}
        for a in valid:
            groups.setdefault(a.value, []).append(a)
        ranked = sorted(
            groups.items(),
            key=lambda kv: (
                -round(sum(a.reliability for a in kv[1]), 9),
                -max(a.reliability for a in kv[1]),
                min(a.source for a in kv[1]),
            ),
        )
        best_val, best_members = ranked[0]
        total = sum(a.reliability for a in valid)
        conf = int(sum(a.reliability for a in best_members) / total * 100 + 0.5)
        return MergedField(best_val, conf, "voting", attributions)


class LogOddsVoting:
    """log-odds 多类别融合(spec 2026-08-29 §3.2/§4)。

    每候选值 Σ logit(r)(标量字段无 first_seen → 不衰减),背景质量归一;
    MAP 值 + conf = P(MAP);alternatives 输出后验降序(0-100)。"""

    def __init__(self, field="country_code", default=None):
        self.field = field
        self.default = default

    def merge(self, source_values: dict[str, Any], context: dict) -> MergedField:
        attributions = _to_attributions(source_values, self.field)
        valid = [a for a in attributions
                 if a.value is not None and a.value != "" and a.value != "N/A" and a.value != 0]
        if not valid:
            return MergedField(self.default, 0, "logodds", attributions)
        deduped = _lo.dedup_lineage(
            [(a.source, _lo.logit(a.reliability)) for a in valid])
        keep = {s for s, _ in deduped}
        s_by_value: dict[Any, float] = {}
        for a in valid:
            if a.source in keep:
                s_by_value[a.value] = s_by_value.get(a.value, 0.0) + _lo.logit(a.reliability)
        probs = _lo.multicategory_posterior(s_by_value)
        ranked = sorted(probs.items(), key=lambda kv: (-kv[1], str(kv[0])))
        best_val, best_p = ranked[0]
        alts = [{"value": v, "probability": round(p * 100, 1)} for v, p in ranked]
        return MergedField(best_val, round(best_p * 100), "logodds",
                           attributions, alts)


class NamingAuthority:
    """Authority model for naming fields (as_name).

    cn_isp once held a CN/HK/MO/TW authority branch (conf 90) — removed when
    cn_isp stopped emitting as_name (spec D6): region names like "香港" were
    polluting the org slot. First valid by reliability order wins; see git
    history if a CN authority source ever returns."""

    def __init__(self):
        self.field = "as_name"

    def merge(self, source_values: dict[str, Any], context: dict) -> MergedField:
        attributions = _to_attributions(source_values, self.field)
        valid = [a for a in attributions if a.value and a.value != "N/A"]
        if not valid:
            return MergedField("N/A", 0, "authority", attributions)
        best = sorted(valid, key=lambda a: (-a.reliability, a.source))[0]
        return MergedField(best.value, round(best.reliability * 100),
                           "authority", attributions)


class RangeSpecificity:
    """Specificity model for CIDR ranges (both address families).

    Cross-family attributions are dropped: ``ip_addr not in net`` is True
    for a v4 network vs v6 address (stdlib ``in`` returns False, never
    raises), so only same-family candidates reach the prefixlen max —
    prefixlen stays comparable because survivors share the query's family.
    """

    def __init__(self):
        self.field = "ip_range"

    def merge(self, source_values: dict[str, Any], context: dict) -> MergedField:
        attributions = _to_attributions(source_values, self.field)

        # Prefer the addr parsed once in lookup(); fall back to parsing the
        # raw ip string (standalone/test calls without a pre-parsed addr).
        ip_addr = context.get("addr")
        if ip_addr is None and context.get("ip"):
            try:
                ip_addr = ipaddress.ip_address(context["ip"])
            except (ipaddress.AddressValueError, ValueError):
                ip_addr = None

        valid: list[tuple[
            ipaddress.IPv4Network | ipaddress.IPv6Network,
            SourceAttribution]] = []
        for a in attributions:
            if not a.value or a.value == "N/A":
                continue
            try:
                net = _parse_net(a.value)
            except (ipaddress.AddressValueError, ValueError):
                continue
            if ip_addr is not None and ip_addr not in net:
                continue
            valid.append((net, a))

        if not valid:
            return MergedField("N/A", 0, "specificity", attributions)
        if len(valid) == 1:
            return MergedField(valid[0][1].value, 50, "specificity", attributions)

        most_specific = max(valid, key=lambda na: na[0].prefixlen)
        return MergedField(most_specific[1].value, 85, "specificity", attributions)


def _decay_confidence(base: int, first_seen) -> int:
    """Linear time decay on evidence age. None first_seen => no decay.

    <=90d: unchanged. 90-365d: linear down to 50% of base. >365d: 20% floor.
    """
    if not first_seen:
        return base
    try:
        ts = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))
    except ValueError:
        return base
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - ts).days
    if age_days <= 90:
        return base
    if age_days <= 365:
        return round(base * (1 - 0.5 * (age_days - 90) / 275))
    return round(base * 0.20)


def _assess_classification(group: list) -> ClassificationAssessment:
    """Assess one classification.type group of observations."""
    obs = group
    ctype = obs[0].classification_type

    # Deterministic verdict precedence: malicious > suspicious > benign > informational.
    # Replaces silent obs[0].verdict first-wins.
    PRECEDENCE = {"malicious": 0, "suspicious": 1, "benign": 2, "informational": 3}
    distinct_verdicts = {o.verdict for o in obs}
    verdict = min(distinct_verdicts, key=lambda v: PRECEDENCE.get(v, 99))
    if verdict not in PRECEDENCE:
        # All verdicts unknown: min() over ties is set-iteration-order dependent
        # (process-nondeterministic), so fall back to sorted order for determinism.
        verdict = sorted(distinct_verdicts)[0]
    verdict_conflict = len(distinct_verdicts) > 1

    n = len(obs)
    # Corroboration = ≥2 INDEPENDENT sources, not ≥2 observations. A single
    # source can emit multiple observations (e.g. threatfox lists one IP under
    # two malware families); those share a source and must not count as
    # independent corroboration.
    distinct_sources = {o.source for o in obs}
    corroborated = len(distinct_sources) >= 2

    # Weighted base confidence from reliabilities (mean reliability * 100).
    rels = [o.reliability for o in obs]
    base = round(100 * sum(rels) / len(rels)) if rels else 0
    base = min(100, max(0, base))
    if corroborated:
        base = max(base, 80)                       # Admiralty "Confirmed" band floor

    # Decay by the NEWEST first_seen in the group (max — ISO date strings sort
    # chronologically, so min would be the OLDEST and over-decay). Anchoring on
    # the freshest evidence keeps corroborated confidence high.
    first_seens = [o.first_seen for o in obs if o.first_seen]
    newest = max(first_seens) if first_seens else None
    confidence = _decay_confidence(base, newest)

    # Dedupe sources by name: one source emitting multiple observations in a
    # group yields a single attribution (reliability is source-level, identical
    # across its observations).
    sources = [
        SourceAttribution(source=src, value=True,
                          reliability=next(o.reliability for o in obs
                                           if o.source == src),
                          authoritative=False)
        for src in distinct_sources
    ]
    reporter_total = sum(o.reporter_count or 0 for o in obs)

    # ── Rich fields — surface per-source context to the API ──
    malware_names = sorted({o.malware_name for o in obs if o.malware_name})

    details: list[dict] = []
    for o in obs:
        d: dict[str, Any] = {"source": o.source, "reliability": o.reliability}
        if o.malware_name:
            d["malware_name"] = o.malware_name
        if o.confidence is not None:
            d["native_confidence"] = o.confidence
        if o.first_seen:
            d["first_seen"] = o.first_seen
        if o.last_seen:
            d["last_seen"] = o.last_seen
        if o.comment:
            d["comment"] = o.comment
        if o.tags:
            d["tags"] = list(o.tags)
        if o.reporter_count is not None:
            d["reporter_count"] = o.reporter_count
        if o.extra:
            d["extra"] = dict(o.extra)      # FULL extra, not just native_type
        if o.native_categories:
            d["native_categories"] = list(o.native_categories)
        details.append(d)

    return ClassificationAssessment(
        type=ctype, verdict=verdict, detected=True, confidence=confidence,
        algorithm="corroboration", sources=sources, corroborated=corroborated,
        reporter_total=reporter_total, verdict_conflict=verdict_conflict,
        malware_names=malware_names, details=details,
    )
