// tasks/model-errors.mjs — 模型失败面限流分类 + 模型并发/退避旋钮(票 #490,第四轮评审卡 25)。
// 分类出处(2026-11-25~11-27 实测,AGENTS.md「并行派发纪律」段同源):同一智谱账户最多三路
// 并发请求,第 4 路回 HTTP 429 且正文 {"code":"1302","message":"您的账户已达到速率限制,…"}
// ——账户级并发上限,等待重试无效(兄弟任务各自重试=再撞,还会拖死同账户上的其他工作);
// 单请求 429(非 1302)等一会儿能过。
// 错误文本形状 = pi-ai formatProviderError 的 "<status>: <body>"(或 "<prefix> (<status>): <body>",
// ops/node_modules/@earendil-works/pi-ai/dist/utils/error-body.js:111),经 pi-agent-core 落
// 助手消息 errorMessage(model-round lastErrorMessage 读)。
// 会话层自动重试先走(报告口径,票面查证项):pi-durable harness 对 stopReason=error 的请求按
// DEFAULT_RETRY_POLICY 自动重试(enabled,maxRetries=3,base 2s 指数,上限 60s;dist/harness/
// agent.js + generation.js classify 的 sleeping/retry 相位;429 文本命中 pi-ai
// isRetryableAssistantError 的裸状态码模式)——本分类看到的是会话层重试耗尽之后的最终错误,
// 在此再分账户级/单请求两级处置。
// env 读取纪律(契约对拍 selftest-contract「每个 OPS_* 读取 ∈ SPAWN_CONTRACT_ENV」):两个旋钮
// 的 process.env 直读只在本文件这两个小函数,其余代码调函数取值(票面硬性要求)。

const ACCOUNT_LIMIT_BODY = "1302"; // 智谱账户级并发上限的正文码(2026-11-27 实测;单请求限流不带)
const RATE_LIMIT_RE = /rate.?limit|too many requests/i; // 单请求限流的常见正文说法(无状态码前缀时兜底)

// classifyModelError(errorMessage) → "account_rate_limited" | "rate_limited" | null。
//   account_rate_limited:HTTP 429 且正文带 1302(账户级,不可重试)。
//   rate_limited:429(非 1302)或正文是限流的说法(单请求,可退避重试)。
//   null:其余失败(500、普通异常文案、空串/非字符串)——分类缺席,走原 model_face 失败面。
// 状态码取自前缀形状 "<status>:" / "(<status>):"(formatProviderError 两形);正文取首个
// 冒号之后,避免把请求 id 之类的数字误当状态码("req 4292: …" 不匹配)。
export function classifyModelError(errorMessage) {
  if (typeof errorMessage !== "string" || errorMessage.length === 0) return null;
  const m = /(?:^|[(\s])(\d{3})(?=\)|:)/.exec(errorMessage);
  const status = m ? m[1] : null;
  const body = m ? errorMessage.slice(m.index + m[0].length) : errorMessage;
  if (status === "429")
    return body.includes(ACCOUNT_LIMIT_BODY) ? "account_rate_limited" : "rate_limited";
  return RATE_LIMIT_RE.test(errorMessage) ? "rate_limited" : null;
}

const MODEL_MAX_INFLIGHT_DEFAULT = 2; // 轮内 2 路,给同账户上的其他工作留 1 路(2026-11-27 实测账户上限 3)
const MODEL_RETRY_BACKOFF_S_DEFAULT = 30; // 单请求限流重试前的等待秒(智谱 429 无 Retry-After 读数,票面定值)

const warnKnob = (line) => process.stderr.write(`[model-gate] ${line}\n`); // 一行告警(stderr;stdout 是信封专线)

const isBlank = (s) => typeof s === "string" && s.trim() === ""; // 空串不当作 0(Number("")===0 的暗面),按非法走缺省+告警

// DEEP 子任务并发闸取值:没设/空串/不是整数/小于 1/NaN → 缺省 2 并打一行告警;整数 ≥1 就用它。
// 告警随跑随打:让「闸实际生效值」在 cron stderr 里显形,不设也看得见缺省。
export function maxModelInflight() {
  const raw = process.env.OPS_MODEL_MAX_INFLIGHT;
  if (raw !== undefined && !isBlank(raw)) {
    const v = Number(raw);
    if (Number.isInteger(v) && v >= 1) return v;
  }
  warnKnob(`OPS_MODEL_MAX_INFLIGHT=${raw ?? "(未设)"} 不是 ≥1 的整数,用缺省 ${MODEL_MAX_INFLIGHT_DEFAULT}`);
  return MODEL_MAX_INFLIGHT_DEFAULT;
}

// 单请求限流重试退避秒:没设/空串/不是有限数/负数 → 缺省 30 并打一行告警;非负数(含小数,测试面)照用。
export function retryBackoffS() {
  const raw = process.env.OPS_MODEL_RETRY_BACKOFF_S;
  if (raw !== undefined && !isBlank(raw)) {
    const v = Number(raw);
    if (Number.isFinite(v) && v >= 0) return v;
  }
  warnKnob(`OPS_MODEL_RETRY_BACKOFF_S=${raw ?? "(未设)"} 不是非负数,用缺省 ${MODEL_RETRY_BACKOFF_S_DEFAULT}`);
  return MODEL_RETRY_BACKOFF_S_DEFAULT;
}
