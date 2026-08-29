"""Load-time source validator — syntax + collision checks ONLY.

Semantic field-mapping decisions ("should this go to a slot or extra?") are the
add-intel-source skill's job, per-feed; this module does NOT try to enforce them
(that's a circular, undecidable check). It catches mechanically-detectable
mistakes: bad classification_type, unknown field_map targets, duplicate targets.

两层护栏(spec 2026-08-28 §5.1):
- metadata_problems():元数据契约(category/reliability/authoritative_for)——
  registry 发现期对其 raise,改漏 = 启动即炸,不静默;
- validate_source():语法类检查(classification_type/field_map)——仅 warning。
"""
from collections import Counter
from ._classification import CLASSIFICATION_TYPES
from ._evidence import ALL_KNOWN

# 权威轴合法字段:路由槽 ∪ 历史权威轴。is_malicious(classification
# verdict 轴)与 is_mobile 非 ALL_KNOWN 路由槽,但 AUTHORITATIVE_SOURCES
# 传统授权它们(迁移快照含这两个键)——合法集必须接纳,否则真源启动即炸。
_AUTHORITY_FIELDS = ALL_KNOWN | {"is_malicious", "is_mobile"}


def metadata_problems(source) -> list[str]:
    """元数据契约检查:违规时 registry 启动即 raise(spec §5.1)。"""
    problems: list[str] = []
    cat = getattr(source, "category", None)
    if cat not in ("geo_asn", "threat", "asset", "other"):
        problems.append(f"category {cat!r} invalid (need geo_asn|threat|asset|other)")
    rel = getattr(source, "reliability", 0.5)
    if not (0.0 <= rel <= 1.0):
        problems.append(f"reliability {rel!r} out of range [0,1]")
    for f in getattr(source, "authoritative_for", ()) or ():
        if f not in _AUTHORITY_FIELDS and not str(f).startswith("extra"):
            problems.append(f"authoritative_for names unknown field {f!r}")
    return problems


def validate_source(source) -> list[str]:
    problems: list[str] = []
    ctype = getattr(source, "classification_type", None)
    if ctype is not None and ctype not in CLASSIFICATION_TYPES and ctype != "other":
        problems.append(
            f"classification_type {ctype!r} not in CLASSIFICATION_TYPES "
            f"(normalize() should have mapped it; check the source's _MAP)")

    fm = getattr(source, "field_map", None)
    if fm:
        targets = []
        for src, tgt in fm.items():
            tgt_slot = tgt[0] if isinstance(tgt, tuple) else tgt
            if tgt_slot not in ALL_KNOWN and not str(tgt_slot).startswith("extra"):
                problems.append(f"field_map {src!r}→{tgt_slot!r} targets unknown slot")
            targets.append(tgt_slot)
        dupes = [t for t, c in Counter(targets).items() if c > 1
                 and not str(t).startswith("extra")]
        for d in dupes:
            problems.append(f"field_map collision: multiple sources → slot {d!r}")

    problems.extend(metadata_problems(source))
    return problems
