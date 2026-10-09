import type { ApiError } from "../api";

// U1:查询/上传错误横幅的数据形状 — 主行必为 i18n 键;detail 是信封 message
// 等有用细节(具体 IP / status),作为次要小字行渲染;retryAfter 来自 429
// 信封 retry_after(秒)。
export interface BannerError {
  key: string;
  detail?: string;
  retryAfter?: number;
}

// 信封语义码 / 前端抛点 code → i18n 主行键。未列出的码(warming/internal/
// not_found/...)与无码 Error 走 fallbackKey(调用方传入的已本地化 failMsg
// 键),message 降级为次要行。
const CODE_KEYS: Record<string, string> = {
  rate_limited: "lookup.error.rate_limited",
  timeout: "lookup.error.timeout",
  stream_truncated: "lookup.error.stream_truncated",
  validation_error: "lookup.error.validation_error",
  bad_request: "lookup.error.bad_request",
  invalid_ip: "lookup.error.invalid_ip",
};

// 这些码的信封 message 与主行文案语义重复(如 "rate limit exceeded" /
// "request validation failed"),不再作为次要行重复展示;其余码的 message
// 可含具体细节(如 invalid_ip 带出非法 IP 串),保留。
const REDUNDANT_DETAIL = new Set([
  "rate_limited",
  "timeout",
  "stream_truncated",
  "validation_error",
  "bad_request",
]);

/** 抛出的 ApiError / 裸 Error → 横幅形状(主行 i18n 键)。 */
export function errorToBanner(e: unknown, fallbackKey: string): BannerError {
  const api = e as Partial<ApiError>;
  const banner: BannerError = {
    key: (api.code != null && CODE_KEYS[api.code]) || fallbackKey,
  };
  if (api.code == null || !REDUNDANT_DETAIL.has(api.code)) {
    const msg = e instanceof Error ? e.message : undefined;
    if (msg) banner.detail = msg;
  }
  if (typeof api.retry_after === "number" && api.retry_after > 0) {
    banner.retryAfter = api.retry_after;
  }
  return banner;
}

/** 流式 outcome 的 done.error(backend 串 + 可选 done.code;EOF 截断为前端
 *  哨兵 error_code="stream_truncated")→ 横幅形状;无错误返回 null。 */
export function outcomeToBanner(
  r: { error?: string | null; error_code?: string | null },
  fallbackKey: string,
): BannerError | null {
  if (r.error == null) return null;
  if (r.error_code === "stream_truncated") {
    // 前端哨兵串 "stream ended before done" 不上屏,主行即完整语义
    return { key: CODE_KEYS.stream_truncated };
  }
  return { key: (r.error_code != null && CODE_KEYS[r.error_code]) || fallbackKey, detail: r.error };
}
