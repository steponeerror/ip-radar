// tools/envelope.mjs — 信封纪律(铁律②:一切失败=结构化信封 {ok:false,code,reason},
// 不抛裸栈不静默;信封禁止入 evidence,降级人裁区)。三分类器单源:spawn 面
// (classifyChannelError)/HTTP 状态面(classifyWebStatus)/MCP 面(classifyMcpSearchError),
// 四码语义同族,文案共读本文件 CHANNEL_HINTS(每码带「下一步合法动作」)。
export const envelope = (code, reason) => ({ ok: false, code, reason });
// ── 通道错误分类(信封四码;PR #177 工具通道修复;判例 docs/ops/precedents/2026-10-24-discover-dual-channel-dead)──
// 2026-10-24 01:59 生产 discover 轮双通道全灭的事故面修复:旧路径 gh_search 失败一律 gh_error
// 兑底(容器无 gh 也不可辨),且 trace.rc 在 ENOENT 时塞字符串违反 outputSchema Number 槽。
// code additive 四码 + 原兑底(gh_error/rg_infra)兼容保留;判定优先级(2026-10-24 裁定;
// 审后修 P2-3 调序并注明 why):channel_missing(spawn ENOENT/rc=127)> quota(stderr 含
// rate limit;GitHub 次级限流形态=403+rate limit 文案,归此才给对「窗口恢复」指引)>
// channel_auth(not logged in/Authentication required/gh auth login 免凭据实测报文/
// GH_TOKEN/401/403,词边界)> transient(超时/网络)> 原兑底。
// 每码文案带「下一步合法动作」(对齐 MCP isError 语义 2026-07-28:错误要能引导模型自纠或
// 升级,出处注明);不可重试三码(channel_missing/channel_auth/quota)由 prompts/discover-system.md
// 信封处置条款消费(基础设施面直接人裁区)。GLOSSARY「通道信封四码」同批录入。
// trace.rc 恒 Number:ENOENT→127;超时被 SIGTERM 杀(execFile code=null)→124(GNU
// timeout(1) 惯例);其余取 execFile 退出码,兑底 1。
const CHANNEL_HINTS = {
  channel_missing: "下一步:该通道本轮不可用——候选直接移人裁区并注明信封内容;修复属部署动作(镜像装配该二进制),勿轮内重试",
  channel_auth: "下一步:凭证属部署面(GH_TOKEN 配置见 deploy/ops-cron.md)——候选移人裁区注明,勿轮内重试、勿改写查询绕行",
  quota: "下一步:账户/配额面——充值或窗口恢复后自然可用;候选移人裁区注明,勿轮内重试", // 措辞兼余额形态(s.jina.ai 402;PR3a),窗口性限流同码
  transient: "下一步:可同参数重试 ≤1 次;再失败即人裁区注明信封内容,勿猜数字",
  gh_error: "下一步:候选移人裁区注明信封原文;勿替失败补数(无证据≠清白)",
  rg_infra: "下一步:基础设施故障非零命中(Minor-3 判例)——人裁区注明;勿当作「无判例」继续推理",
};
export function classifyChannelError(e, bin) {
  const stderr = String(e?.stderr ?? "");
  const msg = String(e?.message ?? e ?? "");
  const exitCode = typeof e?.code === "number" ? e.code : null;
  // 审后修 P2-2/P2-3(2026-10-24,PR #177):timedOut 判据只认 execFile 信号面(killed/
  // SIGTERM/ETIMEDOUT 错误码)——旧 /timed out/i 扫 message 首行含命令行,查询词恰含该
  // 短语会误归 transient;quota 提到 channel_auth 之前(次级限流 403+rate limit 归窗口恢复
  // 指引);channel_auth 补真免凭据报文模式(gh auth login/GH_TOKEN 提示,2026-10-24
  // GH_CONFIG_DIR 隔离实测)并加词边界。
  const timedOut = e?.killed === true || e?.signal === "SIGTERM" || e?.code === "ETIMEDOUT";
  const rc = e?.code === "ENOENT" ? 127 : exitCode ?? (timedOut ? 124 : 1);
  let code;
  if (e?.code === "ENOENT" || exitCode === 127) code = "channel_missing";
  else if (/rate limit|balance|insufficient|\b402\b/i.test(stderr)) code = "quota"; // 402/balance/insufficient=s.jina.ai 余额形态(PR3a):402 显式归 quota 不归 channel_auth——quota 分支先判
  else if (/not logged in|Authentication required|gh auth login|\bGH_TOKEN\b|\b40[13]\b/.test(stderr)) code = "channel_auth";
  else if (timedOut) code = "transient";
  else code = bin === "gh" ? "gh_error" : "rg_infra";
  const detail = `${bin} 通道失败(rc=${rc}):${(stderr || msg).slice(0, 200)}`;
  return { code, rc, reason: `${detail}——${CHANNEL_HINTS[code]}` };
}
// 同族:quota(429/402/余额文案)先于 channel_auth(401/403)——402 归 quota 不归
// channel_auth;文案复用 CHANNEL_HINTS(下一步合法动作,MCP isError 语义);状态面
// 无 spawn,rc 恒 HTTP status;http_error 无 hint(提示词暂态条款辖,同 fetch_url)。
export function classifyWebStatus(status, bodyText, channel) {
  const body = String(bodyText ?? "").replace(/\s+/g, " ").trim().slice(0, 160);
  let code;
  if (status === 429 || status === 402 || /balance|insufficient/i.test(body)) code = "quota";
  else if (status === 401 || status === 403) code = "channel_auth";
  else code = "http_error";
  const detail = `${channel} HTTP ${status}${body ? `:${body}` : ""}`;
  const hint = CHANNEL_HINTS[code];
  return { code, rc: status, reason: hint ? `${detail}——${hint}` : detail };
}
// MCP 面失败分类(四码同族;SearchProviderError.kind 词汇入判定):
// channel_missing(spawn ENOENT/rc127、config 形坏=部署面)> quota(402/429/balance/
// insufficient)> channel_auth(credential/auth/401/403)> transient(超时/network/aborted)
// > io_error 兑底(解析/协议面,文案带下一步:人裁区注明勿补数)。
const MCP_SEARCH_KINDS = new Set(["transient", "quota", "network", "credential", "config", "auth", "invalid-request", "invalid-response", "unsupported", "aborted", "unknown"]);
export function classifyMcpSearchError(failure, { rc } = {}) {
  const msg = String(failure?.message ?? failure ?? "");
  let code; let rcr = typeof rc === "number" ? rc : 1;
  if (failure?.code === "ENOENT" || rcr === 127) { code = "channel_missing"; rcr = 127; }
  else if (failure?.killed === true || failure?.signal === "SIGTERM" || failure?.code === "ETIMEDOUT" || /timeout|超时|aborted/i.test(msg)) { code = "transient"; rcr = 124; }
  else {
    const kinds = [...msg.matchAll(/(?:failed \(|\[)(\w+)(?:\)|\])/g)].map((m) => m[1]).filter((k) => MCP_SEARCH_KINDS.has(k));
    if (kinds.includes("quota") || /\b40[29]\b|balance|insufficient/i.test(msg)) code = "quota";
    else if (kinds.includes("credential") || kinds.includes("auth") || /credential|not logged in|\b40[13]\b/i.test(msg)) code = "channel_auth";
    else if (kinds.includes("network")) code = "transient";
    else if (kinds.includes("config") || /Failed to parse .*web-search\.json|Invalid config/i.test(msg)) code = "channel_missing";
    else code = "io_error";
  }
  const detail = `web_search 通道失败(pi-web-access MCP;rc=${rcr}):${msg.replace(/\s+/g, " ").slice(0, 200)}`;
  const hint = CHANNEL_HINTS[code] ?? "下一步:候选移人裁区注明信封原文;勿替失败补数(无证据≠清白)";
  return { code, rc: rcr, reason: `${detail}——${hint}` };
}
