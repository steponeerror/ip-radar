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

// 票 #148:失败 message 人话化短语(驾驶舱单卡「上一轮结果」主行)。覆盖面 =
// 已观测的模型面信封形状(agent.mjs model_face:stopReason=error:NNN + 嵌入
// JSON {code,message};zai 401 令牌过期 / 1113 余额不足)。HTTP 码优先归类,
// 无码时 message 关键词归类(短语不带括号码,不伪造);无可判 → null,调用方
// 回 roundErrorText 可读面 + 原始信封折叠(证据不灭失,不猜)。
export function humanizeRoundMessage(
  raw: string | null | undefined,
): { key: string; vars?: Record<string, string | number> } | null {
  if (!raw) return null;
  const code = raw.match(/(?:stopReason=error:|"code"\s*:\s*"?)(\d{3,4})/)?.[1];
  const jsonMsg = raw.match(/"message"\s*:\s*"([^"]*)"/)?.[1] ?? "";
  const hay = `${raw} ${jsonMsg}`;
  const kw =
    /令牌|token|expired|unauthorized|过期|认证|鉴权/i.test(hay) ? "upstreamAuth"
    : /余额不足|insufficient (?:balance|quota)|欠费/i.test(hay) ? "upstreamBalance"
    : /rate.?limit|too many requests|限流/i.test(hay) ? "upstreamRate"
    : null;
  const cls = code
    ? code === "401" ? "upstreamAuth"
      : code === "402" ? "upstreamBalance"
      : code === "429" ? "upstreamRate"
      : code.startsWith("5") ? "upstreamServer"
      : kw ?? "upstreamOther"
    : kw;
  if (!cls) return null;
  return code
    ? { key: `ops.err.human.${cls}Code`, vars: { code } }
    : { key: `ops.err.human.${cls}` };
}
