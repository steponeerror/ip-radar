import type { ApiError } from "../api";
import type { TFn } from "../i18n";

// ops 面 HTTP 失败信封 → 可读文案(票 #136 验收:不裸抛 code)。code 空间 =
// backend ipdb/_errors.ErrorCode 闭集;401 unauthorized 不在文案面(调用方
// 踢回登录页,admin 面既有约定)。未知 code/无 code → 信封 message,再兜底
// fallback——绝不把裸 code 当文案甩给用户。
export function opsErrorText(t: TFn, e: unknown, fallback: string): string {
  const err = e as Partial<ApiError> | null;
  if (err && typeof err === "object" && typeof err.code === "string") {
    const key = `ops.err.${err.code}`;
    const mapped = t(key);
    if (mapped !== key) return mapped;
  }
  return (err && typeof err.message === "string" && err.message) || fallback;
}

// ops 轮失败信封文案:task.error_code = 轮次信封 error.code 九词闭集
// (ops/agent/agent.mjs ERROR_CODES,与 HTTP ErrorCode 是两个闭集)+ 原始
// message(定位细节,如 stderr 尾部)。
export function roundErrorText(
  t: TFn, errorCode: string | null | undefined, message: string | null | undefined,
): string {
  let text = "";
  if (errorCode) {
    const key = `ops.round.err.${errorCode}`;
    const mapped = t(key);
    if (mapped !== key) text = mapped;
  }
  if (message) text = text ? `${text}: ${message}` : message;
  return text;
}
