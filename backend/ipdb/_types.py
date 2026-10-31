from dataclasses import dataclass, field
from typing import Any, Optional

from . import _logodds as _lo


@dataclass
class FeedHealth:
    name: str
    last_updated: Optional[str]
    is_stale: bool


@dataclass
class SourceHealth:
    name: str
    loaded: bool
    record_count: int
    last_updated: Optional[str]
    is_stale: bool
    covered_ips: int = 0
    covered_v6_nets: int = 0
    error: Optional[str] = None
    feeds: Optional[list["FeedHealth"]] = None   # 多 feed 源(如 cloud_ranges);单 feed 源不填


# ── New typed internal model ──

@dataclass
class SourceAttribution:
    """Single source's contribution to a field."""
    source: str
    value: Any
    reliability: float = 0.0
    authoritative: bool = False


@dataclass
class MergedField:
    """Merged result for a single scalar field."""
    value: Any
    confidence: int                     # 0-100
    algorithm: str = "voting"           # "cascade" | "voting" | "logodds" | "pcr6" | "authority" | "specificity"
    sources: list[SourceAttribution] = field(default_factory=list)
    alternatives: list = field(default_factory=list)   # [{value, probability 0-100}](仅 logodds 多类别,spec §6)
    context: Optional[dict] = None   # 登记声明下挂行(abuse-context 2026-10-18):白名单键自单证人 extra 透传,声明非融合不进 conf;None=缺席,to_dict 不写键


@dataclass
class EvidenceObservation:
    """Single source's raw observation of one IP (MISP Attribute analog)."""
    source: str
    classification_type: str                 # IntelMQ classification.type
    verdict: str = "malicious"               # malicious|suspicious|benign|informational
    reliability: float = 0.5
    first_seen: Optional[str] = None         # ISO-8601 +00:00; ordinal across sources
    last_seen: Optional[str] = None          # ISO-8601; newest activity per source
    confidence: Optional[int] = None         # source-native (threatfox %, abuseipdb score)
    malware_name: Optional[str] = None       # raw lowercase, NOT normalized
    comment: Optional[str] = None
    reporter_count: Optional[int] = None     # intra-source reporters (abuseipdb)
    tags: list = field(default_factory=list)
    native_categories: list = field(default_factory=list)
    source_refs: dict = field(default_factory=dict)   # scalar refs only
    extra: dict = field(default_factory=dict)         # arbitrary structured -> STIX x_*


@dataclass
class AssetStatement:
    """Single source's statement about one asset attribute. Pure陈述; no scoring."""
    source: str
    value: Any                              # bool (is_proxy) or str (carrier)
    native_type: Optional[str] = None       # source-native subtype, e.g. "VPN"/"PUB"/"DCH"


@dataclass
class ClassificationAssessment:
    """Corroboration result for one classification.type group."""
    type: str
    verdict: str
    detected: bool
    confidence: int                          # 0-100, log-odds 后验;仅由指控章(malicious/suspicious)源求和,纯存档组退回全量(spec 2026-09-06)
    algorithm: str
    sources: list  # list[SourceAttribution]
    corroborated: bool                       # >=2 independent sources(现状注记:纯 derived 组互证仍算印证,grill Q2 2026-10-11;披露面 _eval/agg_share.py,issue #183)
    reporter_total: int = 0
    verdict_conflict: bool = False           # 真对立:benign × 指控同场(spec 2026-09-06;benign②源接入 #188 起真实产出:infra_services 良性断言与指控同场即 True,如 223.5.5.5)
    has_archive: bool = False                # 组内存档章在场(informational;只展示不计分,黄灯数据源)
    malware_names: list[str] = field(default_factory=list)   # de-duplicated, e.g. ["win.vidar"]
    details: list[dict] = field(default_factory=list)        # per-source rich info


# 指控章全仓单一真源(_merge._assess_classification 与 _eval/anchors.py 引用之,
# A2 遗留三处字面量收口):只有 malicious/suspicious 证人进 P(恶意) 后验;
# 存档(informational)证人只展示不计分。
_ACCUSING = frozenset({"malicious", "suspicious"})


@dataclass
class LookupResult:
    """Complete IP lookup result."""
    ip: str
    country: MergedField
    city: MergedField
    asn: MergedField
    as_name: MergedField
    ip_range: MergedField
    is_isp: bool
    classifications: dict   # dict[str, ClassificationAssessment]
    attributes: dict = field(default_factory=dict)   # dict[str, list[AssetStatement]] — pure陈述
    error: str | None = None
    is_reserved: bool = False
    city_zh: Optional[str] = None      # display-only zh name of winning city
    location: Optional[dict] = None       # display-only {lat, lon, accuracy_radius?, time_zone?} (geolite, spec 2026-08-25; tz 信息维度批 2026-10-10)
    registration: Optional[dict] = None   # display-only {registry, reg_country?, alloc_date?, status?} 单证人(rir_delegated 旁路;reg_country ≠ 地理国)
    as_org: Optional[MergedField] = None # ASN→组织级名称(查询期 join,caida_asorg;b/asorg-anycast 2026-10-10);asn 无解或钩子源缺席则 None
    abuse_contact: Optional[MergedField] = None  # 滥用联系邮箱(per-IP 标量,无 join 钩子;rir_abuse 单证人,无证人/错误/保留地址结果均 None 同 as_org 缺席语义)
    org_name: Optional[MergedField] = None  # 注册组织名(per-IP 标量,rir_abuse 同 dump 扩展;≠ as_org 路由层组织;无证人 None 同缺席语义)
    asof: float | None = None             # F2/S37 时钟锚(epoch 秒):threat_summary 重融合按锚刻衰减;None = 墙钟(默认逐位不变)

    # Verdict precedence for the fused top-level `threat` summary. Mirrors
    # _merge._assess_classification's PRECEDENCE so both layers never disagree.
    _VERDICT_PRECEDENCE = {"malicious": 0, "suspicious": 1, "benign": 2, "informational": 3}

    def threat_summary(self) -> dict:
        """Fused single-view verdict: worst classification by precedence.

        One-line answer for downstream integrations (fail2ban action, Graylog
        lookup table, Wazuh script): verdict + confidence + detected types,
        plus the CDN/service flag so consumers can skip bans on infra edges.
        """
        detected = [v for v in self.classifications.values() if v.detected]
        if detected:
            worst = min(detected, key=lambda v: self._VERDICT_PRECEDENCE.get(v.verdict, 99))
            verdict = worst.verdict
            # 证据级重融合(spec 2026-10-04-refusion §3;共识 2026-10-04):顶层置信度不再是最坏组选角,而是把
            # 全部指控组(malicious/suspicious)的证人明细池化后重算 P(恶意) 后验——
            # 多类别佐证计入。同源跨组取 max(不双计),再走与组内同一套
            # coefficient → dedup_lineage → assertion_confidence 流水线;
            # 单指控组时数字恰好退化为该组 confidence(恒等)。asof
            # (F2/S37)随查询锚入 → to_dict() 时免重查引擎,快照可复算。
            # 池化循环单源化(issue #246,_logodds.accuser_pool——此前为
            # 第 6 份同构内联拷贝):跨组 ctype 逐 detail 携带作第 4 元
            # (各证据按自己类型的半衰期衰减);指控章判定(组级 +
            # detail 级双滤)在生成器内预滤,形态留调用方(#244 判例:
            # 判定面各异,helper 不吞)。排序口径随 helper 统一 sorted:
            # 此前插入序喂 dedup_lineage,仅 Σ 浮点求和顺序有理论 ulp
            # 缝,confidence 为 round 后整数,回放闸门 C2 前后对照把关。
            _now = _lo.asof_to_now(self.asof)
            deduped = _lo.accuser_pool(
                ((d["source"], d["reliability"], d.get("first_seen"), v.type)
                 for v in self.classifications.values()
                 if v.verdict in _ACCUSING
                 for d in v.details
                 if d.get("verdict") in _ACCUSING),
                now=_now)
            # 池非空 ⟹ dedup 非空(现行谱系表下最强非 derived 源必存活,
            # 不会被剔除),以 deduped 判空与旧 if pool: 等价
            if deduped:
                confidence = _lo.assertion_confidence([c for _, c in deduped])
            else:
                # 空池边界:detected 但无指控证据(纯存档组/无 details 的旧载荷)
                # → 沿用现行选角(worst-first 组内 max,informational 组参与),
                # 绝不让空池 σ(0)=50 泄漏。(与网页 threatDisplay.threatSummary 对齐;
                # 回归:66.132.186.179 桌面 65 vs 网页 94)
                confidence = max(v.confidence for v in detected if v.verdict == verdict)
        else:
            verdict = "benign"
            confidence = 0
        attr_stmts = self.attributes.get("service", []) + self.attributes.get("is_cdn", [])
        is_cdn = any(
            "cdn" in str(getattr(a, "native_type", "") or "").lower()
            or getattr(a, "value", None) in ("cdn", True)
            for a in attr_stmts
        )
        return {
            "verdict": verdict,
            "confidence": confidence,
            "types": sorted(v.type for v in detected),
            "is_cdn": is_cdn,
        }

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "country": _field_to_dict(self.country),
            "city": _field_to_dict(self.city),
            "city_zh": self.city_zh,
            "location": self.location,
            "registration": self.registration,
            "asn": _field_to_dict(self.asn),
            "as_name": _field_to_dict(self.as_name),
            "as_org": (_field_to_dict(self.as_org)
                       if self.as_org is not None else None),
            "abuse_contact": (_field_to_dict(self.abuse_contact)
                              if self.abuse_contact is not None else None),
            "org_name": (_field_to_dict(self.org_name)
                         if self.org_name is not None else None),
            "ip_range": _field_to_dict(self.ip_range),
            "is_isp": self.is_isp,
            "threat": self.threat_summary(),
            "classifications": {
                k: {
                    "type": v.type,
                    "verdict": v.verdict,
                    "detected": v.detected,
                    "confidence": v.confidence,
                    "algorithm": v.algorithm,
                    "corroborated": v.corroborated,
                    "reporter_total": v.reporter_total,
                    "verdict_conflict": v.verdict_conflict,
                    "has_archive": v.has_archive,
                    "malware_names": v.malware_names,
                    "details": v.details,
                    "sources": [
                        _attribution_to_dict(s) for s in v.sources
                    ],
                }
                for k, v in self.classifications.items()
            },
            "attributes": {
                key: [{"source": s.source, "value": s.value, "native_type": s.native_type}
                      for s in stmts]
                for key, stmts in self.attributes.items()
            },
            **({"error": self.error} if self.error else {}),
            "is_reserved": self.is_reserved,
        }


def _attribution_to_dict(s: SourceAttribution) -> dict:
    return {
        "source": s.source,
        "value": s.value,
        "reliability": s.reliability,
        "authoritative": s.authoritative,
    }


def _field_to_dict(f: MergedField) -> dict:
    d = {
        "value": f.value,
        "confidence": f.confidence,
        "algorithm": f.algorithm,
        "sources": [_attribution_to_dict(s) for s in f.sources],
    }
    if f.alternatives:
        d["alternatives"] = f.alternatives
    # 下挂行非空才序列化(与 alternatives 条件序列化同例):context 是可选
    # 附属非槽契约,缺席恒不写键(公网 Out extra=allow 透传)
    if f.context:
        d["context"] = f.context
    return d
