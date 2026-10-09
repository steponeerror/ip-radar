"""STIX 2.1 Bundle export adapter — the only file that imports stix2.

stix2 ships with the image (pre-installed via requirements.txt) — STIX export
works out of the box. The ImportError path below is a defensive fallback for
trimmed deployments that drop the dependency: with stix2 missing,
to_stix_bundle() returns None (and the endpoint answers 501).
"""
import json
import logging
from uuid import UUID, uuid5

# _ACCUSING 私有名跨模块借道(AS-1):指控章单一口径 —— 与 _types 顶层
# threat_summary 同一集合;本地等义副本会漂移,借道优于复制。
from ._types import LookupResult, _ACCUSING

logger = logging.getLogger(__name__)

# UUIDv5 namespace for deterministic addr SCO IDs (v4/v6)
_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
# Deterministic extension-definition ID (must be <object-type>--<UUID>; a bare
# slug like "ip-radar-threat" is rejected by stix2's identifier validation).
_EXT_ID = f"extension-definition--{uuid5(_NS, 'ip-radar-threat')}"

# Mapping from classification.type → STIX indicator_type (open vocab)
_CLASSIFICATION_INDICATOR_TYPES = {
    "c2-server":           "malicious-activity",
    "blacklist":           "malicious-activity",
    "proxy":               "anonymization",
    "tor":                 "anonymization",
    "scanner":             "anomalous-activity",
    "brute-force":         "brute-force",
    "malware-distribution": "malicious-activity",
    "phishing":            "phishing",
    "vulnerable-system":   "anomalous-activity",
    "undetermined":        "unknown",
}


def to_stix_bundle(lr: LookupResult) -> dict | None:
    """Convert a LookupResult into a STIX 2.1 Bundle (JSON-serializable dict).

    Returns None if the stix2 library is not installed.
    """
    try:
        import stix2  # noqa: F811 — optional import
    except ImportError:
        logger.debug("stix2 not installed, STIX export unavailable")
        return None

    from stix2 import (Bundle, IPv4Address, IPv6Address, AutonomousSystem,
                       Location, Indicator, Identity, Relationship)

    # 1. Identity SCOs — one per participating source
    identities = {}
    seen_sources = set()
    for mf in [lr.country, lr.asn, lr.as_name, lr.ip_range]:
        for s in mf.sources:
            seen_sources.add(s.source)
    for ca in lr.classifications.values():
        for s in ca.sources:
            seen_sources.add(s.source)

    for src_name in seen_sources:
        identities[src_name] = Identity(
            name=src_name,
            identity_class="system",
            x_reliability=_get_src_reliability(src_name),
            x_authoritative=_is_authoritative(src_name),
            allow_custom=True,
        )

    # 2. Address SCO — family-dispatched (PR2 spec §5.2); lr.ip is the
    # compressed canonical form end-to-end (PR1 Q5). Custom props (richness
    # spec §4.5): CDN flag always, asset-attribute bag only when non-empty.
    is_v6 = ":" in lr.ip
    _x_attrs = {
        k: [{"source": s.source, "value": s.value,
             "native_type": s.native_type} for s in stmts]
        for k, stmts in lr.attributes.items()
    } or None
    _x_cdn = lr.threat_summary()["is_cdn"]
    _sco_kw = dict(value=lr.ip, allow_custom=True,
                   x_ipradar_is_cdn=_x_cdn,
                   **({"x_ipradar_attributes": _x_attrs} if _x_attrs else {}))
    if is_v6:
        _sco_kw["id"] = f"ipv6-addr--{uuid5(_NS, lr.ip)}"
        addr_sco = IPv6Address(**_sco_kw)
    else:
        _sco_kw["id"] = f"ipv4-addr--{uuid5(_NS, lr.ip)}"
        addr_sco = IPv4Address(**_sco_kw)

    # 3. Location SDO (from country) and related-to relationship
    objs = [addr_sco]
    if lr.country.value and lr.country.value != "N/A":
        loc_id = f"location--{uuid5(_NS, f'country-{lr.country.value}')}"
        location = Location(
            id=loc_id,
            country=lr.country.value,
            confidence=lr.country.confidence,
            allow_custom=True,
        )
        objs.append(location)
        objs.append(Relationship(
            relationship_type="related-to",
            source_ref=addr_sco.id,
            target_ref=location.id,
        ))

    # 4. Autonomous System (if ASN > 0)
    asn_val = lr.asn.value
    if asn_val and asn_val != 0:
        asn_id = f"autonomous-system--{uuid5(_NS, f'asn-{asn_val}')}"
        as_obj = AutonomousSystem(
            id=asn_id,
            number=asn_val,
            name=lr.as_name.value if lr.as_name.value != "N/A" else None,
        )
        objs.append(as_obj)
        objs.append(Relationship(
            relationship_type="belongs-to",
            source_ref=addr_sco.id,
            target_ref=as_obj.id,
        ))

    # 5. Indicator SDOs — one per ACCUSING classification (AS-1)
    # 存档/弃权章(informational、benign、"")只展示不指控 → 不产 STIX
    # Indicator(Indicator 语义 = 恶性工件断言)。生产路径
    # _assess_classification 恒 detected=True,旧 detected 守卫形同虚设;
    # verdict ∈ 指控章(malicious/suspicious)才是真轴。
    for ctype, ca in lr.classifications.items():
        if ca.verdict not in _ACCUSING:
            continue
        indicator_type = _CLASSIFICATION_INDICATOR_TYPES.get(ctype, "unknown")
        ind = Indicator(
            name=f"IP {lr.ip} — {ctype}/{ca.verdict} ({ca.algorithm})",
            pattern=f"[{'ipv6' if is_v6 else 'ipv4'}-addr:value = '{lr.ip}']",
            pattern_type="stix",
            indicator_types=[indicator_type],
            confidence=ca.confidence,
            x_algorithm=ca.algorithm,
            x_classification_type=ctype,
            x_verdict=ca.verdict,
            x_corroborated=ca.corroborated,
            extensions={
                _EXT_ID: {
                    "extension_type": "toplevel-property-extension",
                    "detected": ca.detected,
                    "confidence": ca.confidence,
                    "algorithm": ca.algorithm,
                    "corroborated": ca.corroborated,
                    "reporter_total": ca.reporter_total,
                    "verdict_conflict": ca.verdict_conflict,
                    "malware_names": list(ca.malware_names),
                    "sources": [
                        {"source": s.source, "reliability": s.reliability,
                         "authoritative": s.authoritative, "value": s.value}
                        for s in ca.sources
                    ],
                    # per-source detail records (each carries its full `extra`
                    # bag, so novel fields like port/sample_hash surface here)
                    "details": [dict(d) for d in ca.details],
                }
            },
            allow_custom=True,
        )
        objs.append(ind)

    # 6. Bundle — return a JSON-serializable dict (not the stix2 object, which
    # FastAPI's jsonable_encoder cannot serialize).
    all_objects = list(identities.values()) + objs
    bundle = Bundle(objects=all_objects, allow_custom=True)
    return json.loads(bundle.serialize())


def _get_src_reliability(name: str) -> float:
    from ._merge import SOURCE_RELIABILITY
    return SOURCE_RELIABILITY.get(name, 0.5)


def _is_authoritative(name: str) -> list[str]:
    from ._merge import AUTHORITATIVE_SOURCES
    return [
        field for field, sources in AUTHORITATIVE_SOURCES.items()
        if name in sources
    ]
