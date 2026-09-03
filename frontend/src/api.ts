import { buildCsvRow, CSV_HEADER, downloadCsv } from "./components/csvExport";

export interface SourceAttribution {
  source: string;
  value: any;
  reliability: number;
  authoritative: boolean;
}

export interface AssetStatement {
  source: string;
  value: boolean | string;
  native_type?: string;
}

export interface MergedField<T = any> {
  value: T;
  confidence: number;           // 0-100 integer
  algorithm: string;            // live: "voting" | "logodds" | "authority" | "specificity" (legacy cascade/pcr6 in old exports)
  sources: SourceAttribution[];
  alternatives?: { value: any; probability: number }[];   // logodds 多类别后验(spec 2026-08-29 §6)
}

export interface ClassificationDetail {
  source: string;
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
  verdict_conflict: boolean;
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
  ip_range: MergedField<string>;
  is_isp: boolean;
  classifications: Record<string, ClassificationAssessment>;
  attributes?: Record<string, AssetStatement[]>;
  error?: string;
  is_reserved?: boolean;
  threat?: ThreatSummary;
  location?: { lat: number; lon: number; accuracy_radius?: number } | null;
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
  total: number;
}

// 所有非 2xx 抛错统一走这里:错误对象带 HTTP status 与后端错误信封的
// error.code(机器可读语义码:"warming" / "no_sources" / "invalid_ip" / ...),
// message 取信封 error.message;非 JSON body(代理 502 HTML 等)退回
// statusText/fallback。调用方按 status+code 分支,不靠文案猜。
function apiError(
  res: Response,
  fallback: string,
  env: { code?: string; message?: string } | null,
  cause?: unknown,
): Error {
  const err = new Error(env?.message || res.statusText || fallback);
  (err as any).status = res.status;
  (err as any).code = env?.code;
  // 过渡兼容:旧读方读 e.reason(曾是 X-IPRadar-Reason 头);信封化后 code 即唯一真相
  (err as any).reason = env?.code ?? res.headers.get("x-ipradar-reason");
  if (cause !== undefined) (err as any).cause = cause;
  return err;
}

async function throwApiError(res: Response, fallback: string): Promise<never> {
  try {
    const body = await res.json();
    throw apiError(res, fallback, body?.error ?? null);
  } catch (e) {
    if (e instanceof Error && (e as any).status === res.status) throw e;
    // body 非 JSON:statusText/fallback 兑底
    throw apiError(res, fallback, null, e);
  }
}

export async function getDbStatus(): Promise<DbStatus> {
  const res = await fetch("/api/db-status");
  if (!res.ok) return throwApiError(res, "Failed to get database status");
  return res.json();
}

export interface Progress {
  done: number;
  total: number;
}

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
      let evt: any;
      try { evt = JSON.parse(line); } catch { continue; }
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
      }
    }
  }

  // done 未到即 EOF(代理截断/进程被杀的干净关闭): 不视为成功
  if (!sawDone && error == null) error = "stream ended before done";

  if (mode === "csv") {
    flushRows();
    if (csvParts.length > 1) {  // more than just the header → has rows
      downloadCsv(csvParts);
      return { results: [], csvDownloaded: true, invalidLines, error, total };
    }
    return { results: [], csvDownloaded: false, invalidLines, error, total };
  }

  // table mode — reassemble in idx order
  const results = Array.from({ length: total }, (_, i) => resultsByIdx.get(i)).filter(
    (x): x is LookupResult => x !== undefined,
  );
  return { results, csvDownloaded: false, invalidLines, error, total };
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

export async function queryIpsStream(
  ips: string[],
  onProgress: (p: Progress) => void,
): Promise<StreamOutcome> {
  const controller = new AbortController();
  const { resetIdle, clear } = streamFetchTimeout(controller);
  try {
    const res = await fetch(`/api/query/stream`, {
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
      throw new Error("Request timed out (120s idle)");
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
    const res = await fetch(`/api/upload/stream`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    if (!res.ok) return throwApiError(res, "Upload failed");
    resetIdle();
    return await readStream(res, onProgress, resetIdle);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("Request timed out (120s idle)");
    }
    throw e;
  } finally {
    clear();
  }
}

export interface SourceHealth {
  name: string;
  loaded: boolean;
  record_count: number;
  covered_ips: number;
  last_updated: string | null;
  is_stale: boolean;
  error: string | null;
}

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
  return (res as any)?.latest ?? null;
}

// --- Task client: enqueue / control / subscribe (SSE) ---

export interface TaskState {
  id: string;
  source: string;
  host: string | null;
  state: "queued" | "throttled" | "downloading" | "loading" | "done" | "failed" | "cancelled";
  error: string | null;
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
  if (!res.ok) throw new Error("Failed to load tasks");
  return res.json();
}

export async function enqueueBatch(): Promise<{ batch_id: string | null; refreshed?: number }> {
  const res = await fetch("/api/update-db", { method: "POST" });
  if (!res.ok) throw new Error("Failed to start batch");
  return res.json();
}

export async function enqueueSingle(name: string): Promise<{ task_id: string }> {
  const res = await fetch(`/api/sources/${encodeURIComponent(name)}/update`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to update ${name}`);
  return res.json();
}

export async function cancelTask(id: string): Promise<void> {
  await fetch(`/api/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export async function cancelBatch(): Promise<void> {
  await fetch("/api/update-db/cancel", { method: "POST" });
}

export async function pauseBatch(): Promise<void> {
  await fetch("/api/update-db/pause", { method: "POST" });
}

export async function resumeBatch(): Promise<void> {
  await fetch("/api/update-db/resume", { method: "POST" });
}

/**
 * Subscribe to task updates via SSE. `onEvent` receives each parsed JSON
 * payload; `onReconnect` fires on each (re)connection so the caller can
 * re-fetch a snapshot via `getTasks`. Returns an unsubscribe that closes
 * the EventSource. The browser handles auto-reconnect natively.
 */
export function subscribeTasks(
  onEvent: (e: any) => void,
  onReconnect?: () => void,
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
}

export async function getVersion(refresh = false): Promise<VersionInfo> {
  return jsonOrThrow(
    await fetch(`/api/version${refresh ? "?refresh=1" : ""}`),
    "Failed to check version",
  );
}

export interface UpdateStatus {
  state: "idle" | "updating" | "failed";
  error?: string | null;
  at?: string | null;
}

// 不走 jsonOrThrow:202/409 都算"已接受",调用方按 status 分支;网络层错误才 reject
export async function postUpdate(token: string): Promise<{ ok: boolean; status: number; body: any }> {
  const res = await fetch("/api/update", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  return { ok: res.ok, status: res.status, body: await res.json().catch(() => null) };
}

export async function getUpdateStatus(): Promise<UpdateStatus> {
  return jsonOrThrow(await fetch("/api/update/status"), "Failed to get update status");
}

