import { buildCsvRow, CSV_HEADER, downloadCsv } from "./components/csvExport";

// api 层非 2xx 抛错统一带 status + code(信封语义码"warming" / "no_sources" /
// "invalid_ip" / ...;见 throwApiError)。调用方按 status+code 分支,不靠文案猜。
export interface ApiError extends Error {
  status: number;
  code?: string;
  retry_after?: number;
  // 过渡兼容:旧读方读 reason(曾是 X-IPRadar-Reason 头);信封化后 code 即唯一真相
  reason?: string | null;
}

export interface SourceAttribution<T = unknown> {
  source: string;
  value: T;
  reliability: number;
  authoritative: boolean;
}

export interface AssetStatement {
  source: string;
  value: boolean | string;
  native_type?: string;
}

export interface MergedField<T = unknown> {
  value: T;
  confidence: number;           // 0-100 integer
  algorithm: string;            // live: "voting" | "logodds" | "authority" | "specificity" (legacy cascade/pcr6 in old exports)
  sources: SourceAttribution<T>[];
  alternatives?: { value: T; probability: number }[];   // logodds 多类别后验(spec 2026-08-29 §6)
  context?: Record<string, string> | null;   // 登记声明上下文,单证人透传,非融合
}

export interface ClassificationDetail {
  source: string;
  verdict: string;             // spec 2026-09-06: 该源证词章
  reliability: number;
  malware_name?: string;
  native_confidence?: number;
  first_seen?: string;
  last_seen?: string;
  comment?: string;
  tags?: string[];
  native_categories?: string[];
  reporter_count?: number;
  extra?: Record<string, unknown>;
}

export interface ClassificationAssessment {
  type: string;
  verdict: string;             // "malicious" | "suspicious" | "benign" | "informational"
  detected: boolean;
  confidence: number;           // 0-100 integer
  algorithm: string;
  corroborated: boolean;
  reporter_total: number;
  verdict_conflict: boolean;   // 真对立(benign×指控);今天恒 false,占位
  has_archive: boolean;        // 存档章在场 → 黄色"含存档记录"
  malware_names: string[];
  details: ClassificationDetail[];
  sources: SourceAttribution[];
}

export interface ThreatSummary {
  verdict: string;
  confidence: number;
  types: string[];
  is_cdn: boolean;
}

export interface LookupResult {
  ip: string;
  country: MergedField<string>;
  city: MergedField<string>;
  city_zh?: string | null;
  asn: MergedField<number | string>;
  as_name: MergedField<string>;
  // ASN→组织级名称(查询期 join,caida_asorg;b/asorg-anycast 2026-10-10);
  // asn 无解或钩子源缺席时 null/undefined
  as_org?: MergedField<string> | null;
  // 滥用联系邮箱(RIPE/AFRINIC 注册库,rir_abuse 单证人;无证人时 N/A/null)
  abuse_contact?: MergedField<string> | null;
  // 注册组织名(RIPE/AFRINIC 注册库 organisation 对象,rir_abuse 单证人;
  // ≠ as_org 路由层组织;无证人时 N/A/null)
  org_name?: MergedField<string> | null;
  ip_range: MergedField<string>;
  is_isp: boolean;
  // 单证人注册元数据块(信息维度批 2026-10-10);reg_country = 注册国≠地理国
  registration?: {
    registry: string;
    reg_country?: string;
    alloc_date?: string;
    status?: string;
  } | null;
  classifications: Record<string, ClassificationAssessment>;
  attributes?: Record<string, AssetStatement[]>;
  error?: string;
  is_reserved?: boolean;
  threat?: ThreatSummary;
  location?: { lat: number; lon: number; accuracy_radius?: number; time_zone?: string } | null;
}

export interface DbStatus {
  last_updated: string;
  total_records: number;
  scalar_records: number;
  threat_records: number;
  asset_records: number;
  is_stale: boolean;
  warnings?: string[];
  warming_up: boolean;
}

// Above this expanded-IP count the UI switches from table to CSV download.
// ResultTable paginates (renders only the current page slice), so DOM cost is
// constant regardless of total — the real ceiling is React state memory
// (results[] held in LookupView state, ~2KB/result → ~100MB at 50k).
export const TABLE_THRESHOLD = 50000;

export interface StreamOutcome {
  results: LookupResult[];   // table mode: populated; csv mode: []
  csvDownloaded: boolean;
  invalidLines: number;
  error?: string | null;   // backend done.error (spec §4)
  error_code?: string | null;  // done.code(backend 语义码)或前端哨兵 "stream_truncated"(U1 视图层 i18n)
  total: number;
}

/** demo 模式下后端要求查询接口带此 header(见 public-demo-mode spec)。 */
export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    headers: { ...(init.headers as Record<string, string>), "x-ipradar-client": "web" },
  });
}


function apiError(
  res: Response,
  fallback: string,
  env: { code?: string; message?: string; retry_after?: number } | null,
  cause?: unknown,
): ApiError {
  const err = new Error(env?.message || res.statusText || fallback) as ApiError;
  err.status = res.status;
  err.code = env?.code;
  // 429 限流的信封 retry_after 秒数(登录暴力破解守卫,Task 8 消费)
  err.retry_after = env?.retry_after;
  err.reason = env?.code ?? res.headers.get("x-ipradar-reason");
  if (cause !== undefined) (err as { cause?: unknown }).cause = cause;
  return err;
}

async function throwApiError(res: Response, fallback: string): Promise<never> {
  try {
    const body = await res.json();
    throw apiError(res, fallback, body?.error ?? null);
  } catch (e) {
    if (e instanceof Error && (e as ApiError).status === res.status) throw e;
    // body 非 JSON:statusText/fallback 兑底
    throw apiError(res, fallback, null, e);
  }
}

export async function getDbStatus(): Promise<DbStatus> {
  const res = await apiFetch("/api/db-status");
  if (!res.ok) return throwApiError(res, "Failed to get database status");
  return res.json();
}

export interface Progress {
  done: number;
  total: number;
}

// /api/query/stream 与 /api/upload/stream 的 NDJSON 事件面(backend 流式
// 查询协议;字段见 readStream 消费处)。
type StreamEvent =
  | { type: "start"; total: number }
  | { type: "row"; idx: number; result: LookupResult }
  | { type: "progress"; done: number; total: number }
  | { type: "done"; invalid_lines?: number; error?: string | null; code?: string | null };

async function readStream(
  res: Response,
  onProgress: (p: Progress) => void,
  keepAlive?: () => void,
): Promise<StreamOutcome> {
  if (!res.body) throw new Error("Streaming not supported");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let total = 0;
  let mode: "table" | "csv" | null = null;
  const resultsByIdx = new Map<number, LookupResult>();
  const csvParts: string[] = [CSV_HEADER];
  let rowBuffer: string[] = [];
  let invalidLines = 0;
  let error: string | null = null;
  let errorCode: string | null = null;
  let sawDone = false;

  const flushRows = () => {
    if (rowBuffer.length) {
      csvParts.push(rowBuffer.join("\n") + "\n");
      rowBuffer = [];
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    keepAlive?.();
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop()!;
    for (const line of lines) {
      if (!line.trim()) continue;
      let evt: StreamEvent;
      try { evt = JSON.parse(line) as StreamEvent; } catch { continue; }
      if (evt.type === "start") {
        total = evt.total;
        mode = total <= TABLE_THRESHOLD ? "table" : "csv";
      } else if (evt.type === "row") {
        const r = evt.result as LookupResult;
        if (mode === "table") {
          resultsByIdx.set(evt.idx, r);
        } else {
          rowBuffer.push(buildCsvRow(r));
          if (rowBuffer.length >= 1000) flushRows();
        }
      } else if (evt.type === "progress") {
        onProgress({ done: evt.done, total: evt.total });
      } else if (evt.type === "done") {
        sawDone = true;
        invalidLines = evt.invalid_lines ?? 0;
        error = evt.error ?? null;
        errorCode = evt.code ?? null;
      }
    }
  }

  // done 未到即 EOF(代理截断/进程被杀的干净关闭): 不视为成功;挂前端
  // 哨兵 code "stream_truncated" 供视图层 i18n(U1)
  if (!sawDone && error == null) {
    error = "stream ended before done";
    errorCode = "stream_truncated";
  }

  if (mode === "csv") {
    flushRows();
    if (csvParts.length > 1) {  // more than just the header → has rows
      downloadCsv(csvParts);
      return { results: [], csvDownloaded: true, invalidLines, error, error_code: errorCode, total };
    }
    return { results: [], csvDownloaded: false, invalidLines, error, error_code: errorCode, total };
  }

  // table mode — reassemble in idx order
  const results = Array.from({ length: total }, (_, i) => resultsByIdx.get(i)).filter(
    (x): x is LookupResult => x !== undefined,
  );
  return { results, csvDownloaded: false, invalidLines, error, error_code: errorCode, total };
}

function streamFetchTimeout(controller: AbortController, connectMs = 30_000, idleMs = 120_000) {
  let timer = setTimeout(() => controller.abort(), connectMs);
  return {
    resetIdle() {
      clearTimeout(timer);
      timer = setTimeout(() => controller.abort(), idleMs);
    },
    clear() {
      clearTimeout(timer);
    },
  };
}

// U1:流式守卫超时(30s 连接 / 120s 空闲)的 AbortError 转结构化
// code="timeout"(视图层据此 i18n);cause 保留原始 DOMException 供诊断。
function timeoutError(cause: unknown): ApiError {
  const err = new Error("Request timed out (120s idle)", { cause }) as ApiError;
  err.status = 0;
  err.code = "timeout";
  return err;
}

export async function queryIpsStream(
  ips: string[],
  onProgress: (p: Progress) => void,
): Promise<StreamOutcome> {
  const controller = new AbortController();
  const { resetIdle, clear } = streamFetchTimeout(controller);
  try {
    const res = await apiFetch(`/api/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ips }),
      signal: controller.signal,
    });
    if (!res.ok) return throwApiError(res, "Query failed");
    resetIdle();
    return await readStream(res, onProgress, resetIdle);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw timeoutError(e);
    }
    throw e;
  } finally {
    clear();
  }
}

export async function uploadFileStream(
  file: File,
  onProgress: (p: Progress) => void,
): Promise<StreamOutcome> {
  const form = new FormData();
  form.append("file", file);
  const controller = new AbortController();
  const { resetIdle, clear } = streamFetchTimeout(controller);
  try {
    const res = await apiFetch(`/api/upload/stream`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    if (!res.ok) return throwApiError(res, "Upload failed");
    resetIdle();
    return await readStream(res, onProgress, resetIdle);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw timeoutError(e);
    }
    throw e;
  } finally {
    clear();
  }
}

/** 多 feed 源的每家出版方健康(T5 cloud_ranges:AWS/Google/Azure/Oracle
 *  Cloud/Alibaba)。backend _omit_null_feeds:单 feed 源响应中省略 feeds 键
 *  (响应形状零变化红线)→ 前端必须可选。 */
export interface FeedHealth {
  name: string;
  last_updated: string | null;
  is_stale: boolean;
}

export interface SourceHealth {
  name: string;
  loaded: boolean;
  record_count: number;
  covered_ips: number;
  last_updated: string | null;
  is_stale: boolean;
  error: string | null;
  // T6 告警诊断对(backend _registry._source_info 合并,_alerts 近 90d 间隔
  // 中位数):content_age_h = now - 原始文件 mtime(小时);observed_interval_h
  // = 实测更新节奏(小时)。null = 无文件 / 事件 <5 条 / 读取失败(后端
  // 永不让 /api/sources 500)。content_age_h 可为负(时钟回拨/未来 mtime),
  // 展示层负责 clamp 0(见 SourcesPage fmtHours)。
  content_age_h: number | null;
  observed_interval_h: number | null;
  // 配置刷新周期(scheduler 档位:stale_days<=1 → 12h,否则 stale_days×24h;
  // backend _registry._source_info 经 _scheduler._period_of 换算)。更新列第二
  // 段渲染此值(2026-10-15 裁决:实测中位数退告警侧,observed_interval_h 仍随
  // payload 下发但仅诊断用)。可选键:旧 payload 无此键 → 展示层按 null 出 "—"。
  refresh_period_h?: number | null;
  feeds?: FeedHealth[] | null;
}

/** 每源最近考分徽章(/api/sources 聚合,backend _eval_reader.read_overview)。
 *  verdict 精确串集含 "NO-DATA"(feed empty / record-count 坍塌 —— W4
 *  verdict.py 钉死,reason ∈ empty/collapsed):源未在贡献,渲染灰底红字。 */
export interface EvalInfo { verdict: string; at: string }

export interface SourceInfo {
  name: string;
  enabled: boolean;
  category: "geo_asn" | "threat" | "asset" | "other";
  archetype: "offline";
  fields: string[];
  reliability: number;
  authoritative_for: string[];
  classification_type: string | null;
  url: string | null;
  stale_days: number | null;
  eval: EvalInfo | null;
  health: SourceHealth;
}

async function jsonOrThrow(res: Response, fallback: string) {
  if (!res.ok) return throwApiError(res, fallback);
  return res.json();
}

export async function getSources(): Promise<SourceInfo[]> {
  return jsonOrThrow(await fetch("/api/sources"), "Failed to load sources");
}

export async function setSourceEnabled(name: string, enabled: boolean): Promise<SourceInfo> {
  const res = await fetch(`/api/sources/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return jsonOrThrow(res, "Failed to update source");
}

// A2 双轨展示:模型评估最新报告里的每源实测 θ(印证率,advisory)。
// theta/ci_* 对未入模源(monopoly-only / 无证据)为 null;API 层已剥离 pairs。
export interface EvalModelScore {
  source: string;
  theta: number | null;
  ci_lo: number | null;
  ci_hi: number | null;
  declared_r: number | null;
}

export interface EvalModel {
  scores?: EvalModelScore[];
}

// 无模型报告时返回 null(页面渲染 θ 列为 —);HTTP 错误照常抛出,由调用方降级。
export async function fetchEvalModel(): Promise<EvalModel | null> {
  const res = await jsonOrThrow(await fetch("/api/eval/model"), "Failed to load eval model");
  return (res as { latest?: EvalModel })?.latest ?? null;
}

// --- Task client: enqueue / control / subscribe (SSE) ---

// /api/events SSE 消息负载(backend 任务流协议)。可选字段容缺:老事件/
// 边界事件可能缺 task/batch;消费方(TaskProvider.applyEvent)自行窄化。
export type TaskEvent =
  | { type: "snapshot"; data?: { tasks: TaskState[]; batch: BatchState | null } }
  | { type: "task"; task?: TaskState }
  | { type: "task_progress"; task_id?: string; received?: number; total?: number }
  | { type: "task_log"; task_id?: string; line?: string } // ops 轮 stderr [turn]/[tool] 行(P2)
  | { type: "batch"; batch?: BatchState | null }
  | { type: "done"; batch?: BatchState | null };

export interface TaskState {
  id: string;
  source: string;
  host: string | null;
  // running = ops 轮相位(P2 票 #134,source="ops";源任务不用——不含
  // running → 轮次不阻查询门,冷启动验收 1)
  state: "queued" | "throttled" | "downloading" | "loading" | "running" | "done" | "failed" | "cancelled";
  error: string | null;
  error_code?: string | null; // failed 语义码;ops 轮 = 信封 error.code 九词闭集透传
  batch_id: string | null;
  received?: number;   // 阶段内进度(相位语义):downloading=字节,loading=记录数
  total?: number;      // 分母;0/缺失=未知(Content-Length 缺失或生成器路径)
  frozenFrac?: number; // 终态冻结分数(TaskProvider 在 failed/cancelled 事件时落位)
}

export interface BatchState {
  id: string;
  state: "running" | "paused" | "done";
  done: number;
  total: number;
}

export interface TasksSnapshot {
  tasks: TaskState[];
  batch: BatchState | null;
}

export async function getTasks(): Promise<TasksSnapshot> {
  const res = await fetch("/api/tasks");
  if (!res.ok) return throwApiError(res, "Failed to load tasks");
  return res.json();
}

export async function enqueueBatch(): Promise<{ batch_id: string | null; refreshed?: number }> {
  const res = await fetch("/api/update-db", { method: "POST" });
  if (!res.ok) return throwApiError(res, "Failed to start batch");
  return res.json();
}

export async function enqueueSingle(name: string): Promise<{ task_id: string }> {
  const res = await fetch(`/api/sources/${encodeURIComponent(name)}/update`, { method: "POST" });
  if (!res.ok) return throwApiError(res, `Failed to update ${name}`);
  return res.json();
}

// 控制类端点成功无业务 body;失败必须 reject(U7:此前非 ok 静默吞掉,
// 按钮点击零反馈)。reject 走统一信封 throwApiError(status+code+message)。
export async function cancelTask(id: string): Promise<void> {
  const res = await fetch(`/api/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" });
  if (!res.ok) return throwApiError(res, "Failed to cancel task");
}

export async function cancelBatch(): Promise<void> {
  const res = await fetch("/api/update-db/cancel", { method: "POST" });
  if (!res.ok) return throwApiError(res, "Failed to cancel batch");
}

export async function pauseBatch(): Promise<void> {
  const res = await fetch("/api/update-db/pause", { method: "POST" });
  if (!res.ok) return throwApiError(res, "Failed to pause batch");
}

export async function resumeBatch(): Promise<void> {
  const res = await fetch("/api/update-db/resume", { method: "POST" });
  if (!res.ok) return throwApiError(res, "Failed to resume batch");
}

/**
 * Subscribe to task updates via SSE. `onEvent` receives each parsed JSON
 * payload; `onReconnect` fires on each (re)connection so the caller can
 * re-fetch a snapshot via `getTasks`. Returns an unsubscribe that closes
 * the EventSource. The browser handles auto-reconnect natively.
 *
 * `onSessionDead` fires when an onerror probe finds the admin session gone
 * (`adminMe()` → null, i.e. 401/503): the stream is closed (stopping the
 * native reconnect loop against a dead session) right before the callback.
 * A failed probe (network error) counts as session-alive — no close, no kick.
 *
 * `onDisconnect` (U8) fires synchronously at the top of onerror, before the
 * probe resolves: the stream dropped and the browser is natively reconnecting
 * — callers surface a transient "reconnecting" hint; recovery is signalled by
 * `onReconnect` (onopen). Purely advisory: no new wire protocol or heartbeat.
 */
export function subscribeTasks(
  onEvent: (e: TaskEvent) => void,
  onReconnect?: () => void,
  onSessionDead?: () => void,
  onDisconnect?: () => void,
): () => void {
  const es = new EventSource("/api/events");
  es.onmessage = (m: MessageEvent) => {
    try {
      onEvent(JSON.parse(m.data));
    } catch {
      /* skip malformed payload */
    }
  };
  es.onopen = () => onReconnect?.();
  // 会话死自愈:一次 onerror 至多探测一次 adminMe;null(401/503)= 会话
  // 真死 → 关流断原生重连并踢出;会话仍在则不动,交浏览器原生重连;探测
  // 自身网络错按正常处理(catch 吞掉),绝不误杀活会话。
  es.onerror = () => {
    // U8:断线即置位(浏览器原生重连中);恢复由 onopen→onReconnect 清。
    // 先于探测发出:会话真死时调用方随即被 onSessionDead 卸载,横幅无关紧要。
    onDisconnect?.();
    adminMe()
      .then((me) => {
        if (me == null) {
          es.close();
          onSessionDead?.();
        }
      })
      .catch(() => { /* probe failed — assume alive, native reconnect continues */ });
  };
  return () => es.close();
}

// --- Version / self-update (in-app update spec) ---

export interface VersionInfo {
  current: string;
  latest: string | null;
  update_available: boolean;
  summary: string | null;
  release_url: string;
  self_update_enabled: boolean;
  public_demo: boolean;
}

export async function getVersion(refresh = false): Promise<VersionInfo> {
  return jsonOrThrow(
    await fetch(`/api/version${refresh ? "?refresh=1" : ""}`),
    "Failed to check version",
  );
}

let publicDemoCache: Promise<boolean> | null = null;

/** 探测公共 demo 模式(缓存;失败按非 demo=false,自部署安全默认)。 */
export function getPublicDemo(): Promise<boolean> {
  if (!publicDemoCache) {
    publicDemoCache = getVersion()
      .then((v) => v.public_demo)
      .catch(() => false);
  }
  return publicDemoCache;
}

export interface UpdateStatus {
  state: "idle" | "updating" | "failed";
  error?: string | null;
  at?: string | null;
}

// 不走 jsonOrThrow:202/409 都算"已接受",调用方按 status 分支;网络层错误才 reject
export async function postUpdate(token: string): Promise<{ ok: boolean; status: number; body: unknown }> {
  const res = await fetch("/api/update", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  return { ok: res.ok, status: res.status, body: await res.json().catch(() => null) };
}

export async function getUpdateStatus(): Promise<UpdateStatus> {
  return jsonOrThrow(await fetch("/api/update/status"), "Failed to get update status");
}

// --- Admin session (three-tier auth, spec 2026-09-21 §9) ---

// GET /api/users/me 的 UserRead(本前端只用 email;Task 9 按需扩字段)
export interface AdminUserRead {
  id: string;
  email: string;
}

// 登录成功是 204 无 body(CookieTransport 硬编码)——会话在 HttpOnly cookie
// ipradar_admin,勿解析 json;失败走统一信封 throwApiError(status/code/
// retry_after 随 Error 走)。表单编码 username/password 是 fastapi-users 约定。
export async function adminLogin(email: string, password: string): Promise<void> {
  const res = await fetch("/api/auth/jwt/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  if (!res.ok) return throwApiError(res, "Login failed");
}

export async function adminLogout(): Promise<void> {
  await fetch("/api/auth/jwt/logout", { method: "POST" });
}

// 未登录(401)/admin 未配置(503)都返回 null —— 调用方按未登录处理;
// 网络层错误 reject,由调用方降级。
export async function adminMe(): Promise<AdminUserRead | null> {
  const res = await fetch("/api/users/me");
  return res.ok ? res.json() : null;
}

// --- Admin API keys(Task 5 契约 FROZEN,snake_case 字段) ---

// 密钥元数据 —— 绝不含 JWT 本体(list 单项 / PATCH 返回形状)。
// sources: null = 全部公开源;web: demo 网页身份种子行(demoweb,只读)。
export interface ApiKeyMetaInfo {
  sub: string;
  name: string;
  created_at: string | null;
  last_used_at: string | null;
  disabled: boolean;
  sources: string[] | null;
  web: boolean;
}

// 列表按创建时间倒序(最新在前),从不返回 key 本体。
export async function listAdminKeys(): Promise<ApiKeyMetaInfo[]> {
  return jsonOrThrow(await fetch("/api/admin/keys"), "Failed to list keys");
}

// 201 返回 {key, meta}:完整 JWT 仅此一次,调用方必须当场展示给用户。
// sources 缺省/null = 全部公开源;显式列表 = 该键专属源集合。
export async function createAdminKey(
  name: string,
  expiresDays?: number,
  sources?: string[] | null,
): Promise<{ key: string; meta: ApiKeyMetaInfo }> {
  const res = await fetch("/api/admin/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, expires_days: expiresDays, sources }),
  });
  return jsonOrThrow(res, "Failed to create key");
}

// 编辑源集合 = PATCH {"sources": [...] | null};null = 重置为全部公开源。
export async function setAdminKeySources(
  sub: string,
  sources: string[] | null,
): Promise<ApiKeyMetaInfo> {
  const res = await fetch(`/api/admin/keys/${encodeURIComponent(sub)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sources }),
  });
  return jsonOrThrow(res, "Failed to update key sources");
}

// 吊销 = PATCH {disabled:true};返回更新后的 meta。
export async function revokeAdminKey(sub: string): Promise<ApiKeyMetaInfo> {
  const res = await fetch(`/api/admin/keys/${encodeURIComponent(sub)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ disabled: true }),
  });
  return jsonOrThrow(res, "Failed to revoke key");
}

// 启用 = PATCH {disabled:false}(revokeAdminKey 镜像,同一端点);返回更新后的 meta。
export async function enableAdminKey(sub: string): Promise<ApiKeyMetaInfo> {
  const res = await fetch(`/api/admin/keys/${encodeURIComponent(sub)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ disabled: false }),
  });
  return jsonOrThrow(res, "Failed to enable key");
}

// DELETE 成功是 204 无 body。
export async function deleteAdminKey(sub: string): Promise<void> {
  const res = await fetch(`/api/admin/keys/${encodeURIComponent(sub)}`, { method: "DELETE" });
  if (!res.ok) return throwApiError(res, "Failed to delete key");
}

// ── ops 运营面(P4,票 #136;契约真源 = backend/main.py ops 路由 +
// _api_models.py Ops* 模型,P2/P3 冻结面;票 #140 +2:agent 配置)── admin 鉴权
// 走同源 cookie 会话,与密钥/token 面同惯例;错误统一走
// throwApiError(status+code+message)。

export type OpsRoundType = "health" | "discover";

// 202 → {task_id};串行车道占用 → 409 eval_busy(拒绝不排队,admin 重试)。
export async function startOpsRound(
  type: OpsRoundType,
  input: string,
): Promise<{ task_id: string }> {
  const res = await fetch("/api/ops/rounds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, input }),
  });
  return jsonOrThrow(res, "Failed to start ops round");
}

export interface OpsPackageInfo {
  name: string;
  size: number;
  modified: string; // ISO-UTC
}

export async function listOpsPackages(): Promise<OpsPackageInfo[]> {
  const r = await jsonOrThrow(await fetch("/api/ops/packages"), "Failed to load packages");
  return r.packages;
}

// 包/台账/判例全文逐字(OpsFileTextOut.text;渲染归本层)。
export async function readOpsPackage(name: string): Promise<string> {
  const r = await jsonOrThrow(
    await fetch(`/api/ops/packages/${encodeURIComponent(name)}`),
    "Failed to load package",
  );
  return r.text;
}

export async function readOpsLedger(): Promise<string> {
  const r = await jsonOrThrow(await fetch("/api/ops/ledger"), "Failed to load ledger");
  return r.text;
}

// kws:空串 = 全量倒序;非空 = 词法检索(逗号/空白分隔多词,后端 rg OR)。
export async function listOpsPrecedents(kws = ""): Promise<string[]> {
  const url = kws
    ? `/api/ops/precedents?kws=${encodeURIComponent(kws)}`
    : "/api/ops/precedents";
  const r = await jsonOrThrow(await fetch(url), "Failed to load precedents");
  return r.precedents;
}

export async function readOpsPrecedent(name: string): Promise<string> {
  const r = await jsonOrThrow(
    await fetch(`/api/ops/precedents/${encodeURIComponent(name)}`),
    "Failed to load precedent",
  );
  return r.text;
}

export type OpsRulingVerdict = "agreed" | "overruled" | "amended";

export interface OpsRulingResult {
  created: boolean; // false = 幂等零副作用(重复同裁)
  precedent: string;
  superseded: string | null; // 被取代的旧条目(原条目永不删)
  queue_appended: boolean; // 裁⑦「已批准待集成」清单是否新入行
}

// 人裁三动作;suggestion = 包内建议原文逐字(后端幂等键入参)。
export async function postOpsRuling(
  pkg: string,
  suggestion: string,
  verdict: OpsRulingVerdict,
  amendment?: string,
): Promise<OpsRulingResult> {
  const res = await fetch("/api/ops/ruling", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      package: pkg, suggestion, verdict,
      ...(verdict === "amended" ? { amendment } : {}),
    }),
  });
  return jsonOrThrow(res, "Failed to record ruling");
}

// 导出 = 全量判例 + 台账(确定性 zip);鉴权同 cookie,Blob 落地下载。
export async function exportOpsPrecedents(): Promise<Blob> {
  const res = await fetch("/api/ops/precedents/export.zip");
  if (!res.ok) return throwApiError(res, "Failed to export precedents");
  return res.blob();
}

// ── ops agent 配置面(票 #140;契约真源 = backend GET/PUT /api/ops/agent-config
// + _api_models.py OpsAgentConfig*)── 模型闭集下拉由后端 allowed_models 驱动
// (单一真相源,裁决 2026-10-20);key 硬约束同 token 面:write-only,状态只
// configured+tail4,完整值永不回显(前端无既有值可回填,输入框恒空)。
export interface OpsAgentKeyStatus {
  configured: boolean;
  tail4: string | null;
}

export interface OpsAgentConfig {
  model_health: string; // 有效值:配置 > env > models.mjs 缺省
  model_discover: string;
  zai_api_key: OpsAgentKeyStatus;
  allowed_models: string[]; // 后端校验闭集(实测 pi-ai 装载目录)
}

export async function getOpsAgentConfig(): Promise<OpsAgentConfig> {
  return jsonOrThrow(await fetch("/api/ops/agent-config"), "Failed to load agent config");
}

// PUT:三字段缺省/空 key = 保持不改(无清除面);闭集外模型 422。
// 成功返回写后状态(与 GET 同形)。
export async function putOpsAgentConfig(
  payload: { model_health: string; model_discover: string; zai_api_key?: string },
): Promise<OpsAgentConfig> {
  const res = await fetch("/api/ops/agent-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_health: payload.model_health,
      model_discover: payload.model_discover,
      ...(payload.zai_api_key ? { zai_api_key: payload.zai_api_key } : {}),
    }),
  });
  return jsonOrThrow(res, "Failed to save agent config");
}

// ── token 界面配置(sources-redesign T3;契约见 backend/main.py admin_token_*
// 与 ipdb/_tokens.py 冻结映射:OTX_API_KEY 一 key 双源)。硬约束:status 只出
// configured + tail4,完整值永不回显 —— 前端无既有值可回填,输入框恒空。
export interface TokenStatus {
  env_var: string;
  sources: string[];
  configured: boolean;
  tail4: string | null;
}

export async function getAdminTokens(): Promise<TokenStatus[]> {
  return jsonOrThrow(await fetch("/api/admin/tokens"), "Failed to list tokens");
}

// PUT 成功是 204 无 body;未知 var/空值 → 422(信封 validation_error)。
export async function putAdminToken(envVar: string, value: string): Promise<void> {
  const res = await fetch(`/api/admin/tokens/${encodeURIComponent(envVar)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) return throwApiError(res, "Failed to save token");
}

// 清除 = DELETE;回落启动快照语义见 _tokens.clear_token(204 无 body)。
export async function clearAdminToken(envVar: string): Promise<void> {
  const res = await fetch(`/api/admin/tokens/${encodeURIComponent(envVar)}`, { method: "DELETE" });
  if (!res.ok) return throwApiError(res, "Failed to clear token");
}

