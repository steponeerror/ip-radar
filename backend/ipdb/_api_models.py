"""PR③ T11: 全部 REST 端点的 Pydantic 响应模型(OpenAPI 契约)。

原则:模型描述现状,不重新设计 —— 字段 = main.py 各路由 return 的
真实键(_types.py to_dict / _tasks.py to_dict / _registry._source_info /
_eval_reader 等)。所有模型 extra="allow":dynamic 内层(current layout、
STIX bundle、eval latest 原始报告)保持 dict/Any,漏建模的键也不丢,
response_model 不会静默过滤掉未声明字段。
"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_serializer


class _Out(BaseModel):
    # 契约声明器,不是过滤器:多余键原样透传
    model_config = ConfigDict(extra="allow")


# ── 查询 ──
class AttributionOut(_Out):
    source: str
    value: Any
    reliability: float
    authoritative: bool


class FieldOut(_Out):
    value: Any = None
    confidence: Any = None
    algorithm: Optional[str] = None
    sources: list[AttributionOut] = []
    alternatives: list[dict] = []   # logodds 多类别后验 [{value, probability 0-100}](spec 2026-08-29 §6)


class ThreatSummaryOut(_Out):
    verdict: str
    confidence: Any
    types: list[str]
    is_cdn: bool


class ClassificationOut(_Out):
    type: str
    verdict: str
    detected: bool
    confidence: Any
    algorithm: Optional[str] = None
    corroborated: bool = False
    reporter_total: int = 0
    verdict_conflict: bool = False
    malware_names: list[str] = []
    details: dict = {}
    sources: list[AttributionOut] = []


class AssetStatementOut(_Out):
    source: str
    value: Any
    native_type: Any = None


class LookupResultOut(_Out):
    """GET /api/lookup/{ip} — 与 POST /api/query/stream 每行同构。"""
    ip: str
    country: FieldOut
    city: FieldOut
    city_zh: Optional[str] = None
    location: Optional[dict] = None
    asn: FieldOut
    as_name: FieldOut
    ip_range: FieldOut
    is_isp: bool
    threat: ThreatSummaryOut
    classifications: dict[str, ClassificationOut]
    attributes: dict[str, list[AssetStatementOut]]
    error: Optional[str] = None
    is_reserved: bool

    @model_serializer(mode="wrap")
    def _omit_null_error(self, handler):
        # to_dict 只在出错时写 error 键;模型默认值不得把它补成 null
        # (响应形状零变化红线)。其余键照常。
        out = handler(self)
        if out.get("error") is None:
            out.pop("error", None)
        return out


# ── 源目录 ──
class SourceHealthOut(_Out):
    name: str
    loaded: bool
    record_count: int
    last_updated: Optional[str]
    is_stale: bool
    covered_ips: int = 0
    covered_v6_nets: int = 0
    error: Optional[str] = None


class EvalBadgeOut(_Out):
    verdict: str
    at: Optional[str] = None


class SourceInfoOut(_Out):
    """GET /api/sources 单项;PATCH 返回同构(T7 后含 eval=null)。"""
    name: str
    enabled: bool
    category: str
    archetype: str
    fields: list[str]
    reliability: float
    authoritative_for: list[str]
    classification_type: Optional[str] = None
    url: Optional[str] = None
    stale_days: Optional[int] = None
    health: SourceHealthOut
    eval: Optional[EvalBadgeOut] = None


# ── 更新任务链 ──
class TaskOut(_Out):
    id: str
    source: str
    host: Optional[str] = None  # 实测可为 None(本地/无 host 任务)
    state: str
    error: Optional[str] = None
    batch_id: Optional[str] = None
    received: int
    total: int


class BatchOut(_Out):
    id: str
    state: str
    done: int
    total: int


class TasksSnapshotOut(_Out):
    tasks: list[TaskOut]
    batch: Optional[BatchOut] = None


class TaskAcceptedOut(_Out):
    task_id: str


class AckOut(_Out):
    ok: bool


class UpdateDbOut(_Out):
    batch_id: Optional[str] = None
    refreshed: int


class DbStatusOut(_Out):
    last_updated: str
    record_count: int
    cn_record_count: int
    total_records: int
    scalar_records: int
    threat_records: int
    asset_records: int
    is_stale: bool
    covered_v6_nets: int
    warming_up: bool


class SchedulerSourceOut(_Out):
    name: str
    stale: bool
    last_task_state: Optional[str] = None
    fail_count: int = 0
    last_attempt_at: Optional[str] = None
    next_attempt_at: Optional[str] = None
    next_refresh_at: Optional[str] = None


class SchedulerStatusOut(_Out):
    enabled: bool
    interval_sec: int
    last_scan_at: Optional[str] = None
    next_scan_at: Optional[str] = None
    sources: list[SchedulerSourceOut]


# ── eval 成绩单 ──
class EvalJobOut(_Out):
    job_id: str
    source: str
    state: str
    started_at: str
    error: Optional[str] = None


class EvalVerdictOut(_Out):
    source: str
    verdict: str
    at: Optional[str] = None
    mc: Optional[float] = None
    cg: Optional[float] = None
    oc: Optional[float] = None


class EvalOverviewOut(_Out):
    current_job: Optional[EvalJobOut] = None
    verdicts: list[EvalVerdictOut]


class EvalHistoryItemOut(_Out):
    at: Optional[str] = None
    verdict: str


class EvalJobAcceptedOut(_Out):
    """POST /api/eval/{source}/run 202 —— job_id 是 eval 单槽语义。"""
    job_id: str


class EvalDetailOut(_Out):
    """latest = eval CLI 原始报告(动态 schema,宽松 dict)。"""
    latest: Optional[dict] = None
    history: list[EvalHistoryItemOut]


# ── 系统 ──
class VersionOut(_Out):
    current: str
    latest: Optional[str] = None
    update_available: bool
    summary: Optional[str] = None
    release_url: str
    self_update_enabled: bool


class UpdateStateOut(_Out):
    state: str
    error: Optional[str] = None
    at: Optional[str] = None


class UpdateAcceptedOut(_Out):
    status: str


class PerfLayoutOut(_Out):
    host: dict
    current: dict
    predicted: dict
    tunables: dict
    warnings: list
    memory_valve: dict


# ── 错误信封(所有 4xx/5xx 的统一 schema)──
class ErrorBody(_Out):
    code: str
    message: str
    detail: Any = None
    retry_after: Optional[int] = None


class ErrorEnvelope(_Out):
    error: ErrorBody
