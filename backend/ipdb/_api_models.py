"""PR③ T11: 全部 REST 端点的 Pydantic 响应模型(OpenAPI 契约)。

原则:模型描述现状,不重新设计 —— 字段 = main.py 各路由 return 的
真实键(_types.py to_dict / _tasks.py to_dict / _registry._source_info /
_eval_reader 等)。所有模型 extra="allow":dynamic 内层(current layout、
STIX bundle、eval latest 原始报告)保持 dict/Any,漏建模的键也不丢,
response_model 不会静默过滤掉未声明字段。
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer


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
    confidence: Any = None   # 0-100;0 = 无源命中(无证据,非清白)
    algorithm: Optional[str] = None
    sources: list[AttributionOut] = []
    # alternatives([{value, probability 0-100}] 后验降序, spec 2026-08-29 §6)
    # 不声明字段:_field_to_dict 仅非空才写,声明默认值会给每个标量字段
    # 恒补空数组(GET 与 NDJSON 流同形红线);真值经 extra=allow 透传。


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
    verdict_conflict: bool = False  # 真对立(benign × 指控,spec 2026-09-06;今天恒 False,占位)
    has_archive: bool = False   # 存档章在场(spec 2026-09-06;黄灯数据源)
    malware_names: list[str] = []
    details: list[dict] = []   # per-source 富信息(_types.to_dict 产 list;#41 曾误声明 dict → GET 单查 500)
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
    registration: Optional[dict] = None   # 单证人注册元数据块(信息维度批)
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
class FeedHealthOut(_Out):
    name: str
    last_updated: Optional[str]
    is_stale: bool


class SourceHealthOut(_Out):
    name: str
    loaded: bool
    record_count: int
    last_updated: Optional[str]
    is_stale: bool
    covered_ips: int = 0
    covered_v6_nets: int = 0
    error: Optional[str] = None
    feeds: Optional[list[FeedHealthOut]] = None   # 多 feed 源(如 cloud_ranges);单 feed 源不填

    @model_serializer(mode="wrap")
    def _omit_null_feeds(self, handler):
        # feeds 只在多 feed 源出现;模型默认值不得给单 feed 源补成 null
        # (响应形状零变化红线,同 _omit_null_error)。其余键照常。
        out = handler(self)
        if out.get("feeds") is None:
            out.pop("feeds", None)
        return out


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
    total_records: int
    scalar_records: int
    threat_records: int
    asset_records: int
    is_stale: bool
    covered_v6_nets: int
    warming_up: bool


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


class EvalModelOut(_Out):
    """GET /api/eval/model —— 最新舰队 corroboration-contrast 报告(advisory,
    宽松 dict:kind/w/checks/scores/…,layout 见 _eval.suite.write_model_report)。"""
    latest: Optional[dict] = None


# ── 系统 ──
# ── admin API key 管理(spec 2026-09-21 §7;契约对 Task 9 前端 FROZEN)──
class ApiKeyCreateIn(BaseModel):
    """POST /api/admin/keys 入参(严格模型:多余输入字段 422,非 _Out 透传)。"""
    name: str = Field(min_length=1)
    expires_days: Optional[int] = Field(default=None, ge=1)
    sources: Optional[list[str]] = None   # None=全部公开源;[] 拒绝(main 校验 422)


class ApiKeyPatchIn(BaseModel):
    """PATCH /api/admin/keys/{sub} 入参:省略=不改;sources 显式 null=重置
    (路由按 model_fields_set 区分省略与 null)。"""
    disabled: Optional[bool] = None
    sources: Optional[list[str]] = None


# ── token 界面配置（sources-redesign T1；契约对 Task 3 前端 FROZEN）──
class TokenStatusOut(_Out):
    """GET /api/admin/tokens 出参行。硬约束：完整 token 值永不回显，
    仅 configured + tail4（≤4 字符）。"""
    env_var: str
    sources: list[str]
    configured: bool
    tail4: Optional[str] = None


class TokenSetIn(BaseModel):
    """PUT /api/admin/tokens/{env_var} 入参。长度上限不在此声明：pydantic 422
    detail 会回带 input 原值，违反「永不回显」；≤512 在 _tokens.set_token 校验
    （HTTPException 信封不带值）。"""
    value: str = Field(min_length=1)


class OpsRoundIn(BaseModel):
    """POST /api/ops/rounds 入参（P2，票 #134）。type 闭集 {health, discover}
    与 input 非空在 handler 校验（422；闭集真源 = agent.mjs KWS，桥不复制
    九词/轮次闭集常量，防双源漂移）。"""
    type: str
    input: str


class OpsPackageOut(_Out):
    """GET /api/ops/packages 列表项（P3，票 #135）。modified = ISO-UTC。"""
    name: str
    size: int
    modified: str


class OpsPackagesOut(_Out):
    packages: list[OpsPackageOut]


class OpsFileTextOut(_Out):
    """包/台账/判例全文（逐字；渲染归 P4 前端）。"""
    text: str


class OpsPrecedentsOut(_Out):
    """判例名列表（无 kws = 全量倒序；kws = rg 命中面，_schema.md 排除）。"""
    precedents: list[str]


class OpsRulingIn(BaseModel):
    """POST /api/ops/ruling 入参（P3，票 #135）。verdict 闭集
    {agreed, overruled, amended}（T1 ruling_agreement 去 pending）与 amendment
    存在性约束（仅 amended 带）在 handler 校验（422；闭集真源 = 判例
    _schema.md，路由不复制常量防双源漂移——P2 同惯例）。"""
    package: str
    suggestion: str
    verdict: str
    amendment: Optional[str] = None


class OpsRulingOut(_Out):
    """人裁写回结果：created=False = 幂等零副作用（重复同裁）；superseded =
    被取代的旧条目文件名（原条目永不删）；queue_appended = 裁⑦清单是否新入行。"""
    created: bool
    precedent: str
    superseded: Optional[str] = None
    queue_appended: bool


class OpsItemOut(_Out):
    """GET /api/ops/items 列表项（P1 §1，票 #153）。十字段冻结（spec #152）；
    supersedes = 复开链指的旧条目 id（仅复开条目携带，原条目永不删）；
    modified = ISO-UTC。审阅四键写面 = T3，不在 T1 契约内。"""
    id: str
    action: str
    args: dict
    evidence: dict
    impact: str
    rollback: str
    dedup_key: dict
    severity: str
    cause_group: str
    status: str
    supersedes: Optional[str] = None
    modified: str


class OpsItemsOut(_Out):
    items: list[OpsItemOut]


# ── ops agent 配置面（票 #140 立；票 #143 多供应商扩面；永不回显约束同
# token 面 sources-redesign T1）──
class OpsAgentKeyStatusOut(_Out):
    """key 状态：configured + tail4（≤4 字符）。硬约束：完整 key 永不回显
    （沿 TokenStatusOut 先例）；空串/缺省 = 保持不改（无清除面）。"""
    configured: bool
    tail4: Optional[str] = None


class OpsModelCostOut(_Out):
    """pi-ai Model.cost 原样（单位 $/1M tokens；catalog.mjs dump 逐字）。"""
    input: Optional[float] = None
    output: Optional[float] = None
    cacheRead: Optional[float] = None
    cacheWrite: Optional[float] = None


class OpsCatalogModelOut(_Out):
    """目录单项（catalog.mjs dump 形状）；cost=None → UI 成本提示隐去。"""
    id: str
    name: str
    cost: Optional[OpsModelCostOut] = None


class OpsAgentConfigOut(_Out):
    """GET/PUT /api/ops/agent-config 出参（票 #143 多供应商形状）。model_* =
    有效值（配置 > env > models.mjs 缺省，qualified "provider/model" 归一，
    优先级链见 _ops_config 模块头）；api_keys = 逐 provider key 状态；catalog =
    动态目录（node 子调用 dump，TTL 缓存，失败兜底闭集），catalog_source 显式
    dynamic|fallback；前端双下拉单一真相源（裁决 2026-10-20）。"""
    model_health: str
    model_discover: str
    api_keys: dict[str, OpsAgentKeyStatusOut]
    catalog: dict[str, list[OpsCatalogModelOut]]
    catalog_source: str


class OpsAgentConfigIn(BaseModel):
    """PUT 入参：字段全可省（缺省 = 保持不改）；api_keys 值空串 = 该家保持
    不改。api_keys 故意不声明 dict[str,str]（pydantic 422 detail 回带 input
    原值，非 str 值会被回显——违「永不回显」）；类型/长度/形状校验全在
    _ops_config.update（HTTPException 信封不带值）。"""
    model_health: Optional[str] = None
    model_discover: Optional[str] = None
    api_keys: Optional[dict] = None


class ApiKeyOut(_Out):
    """密钥元数据 —— 绝不含 JWT 本体(list 单项 / PATCH 返回形状)。"""
    sub: str
    name: str
    created_at: Optional[datetime] = None   # legacy NULL 行合法(迁移锚点,spec §9)
    last_used_at: Optional[datetime] = None
    disabled: bool
    sources: Optional[list[str]] = None
    web: bool = False                     # 种子行徽章(仅展示)


class ApiKeyCreatedOut(_Out):
    """POST /api/admin/keys 201 —— 完整 key 仅此一次出现。"""
    key: str
    meta: ApiKeyOut


class VersionOut(_Out):
    current: str
    latest: Optional[str] = None
    update_available: bool
    summary: Optional[str] = None
    release_url: str
    self_update_enabled: bool
    public_demo: bool = False   # 公开演示守卫开启且请求方非维护者(demo 探测字段)


class UpdateStateOut(_Out):
    state: str
    error: Optional[str] = None
    at: Optional[str] = None


class UpdateAcceptedOut(_Out):
    status: str


# ── 错误信封(所有 4xx/5xx 的统一 schema)──
class ErrorBody(_Out):
    code: str
    message: str
    detail: Any = None
    retry_after: Optional[int] = None


class ErrorEnvelope(_Out):
    error: ErrorBody
