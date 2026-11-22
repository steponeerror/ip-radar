// pipeline/microprobes.mjs — DEEP 真面微探针工具面(票 #173;闭集=deep.md 工具表 3 只,提示词一字不改)。
// 背景:2026-10-24 生产真面冒烟(轮 2026-10-24-1110-health)实证真 glm-5.3 在 tools=[] 下按
// deep.md 白名单声明编造 call_id 出 evidence,G_DEEP 正确门败(model_face)——无真探针则 DEEP
// 无法产合法 confirmed/refuted,轮必死。本文件=纯本地只读网络探测(pi-agent-core 工具面,
// 零依赖新增;装配参照 legacy 轮 agent.mjs ToolHost),接线面=faux.mjs runRealStep(仅 DEEP 真面)。
//
// 探测语义参照 lib.sh _ff_probe 判例:HEAD→GET Range(bytes=0-0)降级 / UA / 超时族 15s(FEED_TIMEOUT_S)。
// 传输层复用 tools.mjs safeFetch(逐跳 SSRF 门+钉址+手动重定向,评审判例 2026-10-19);本票为其加
// headers 注入(Range/UA 变体)与 allowStatus(≥400 状态码也是读数——辨 UA 拦截/限流/死键的判别
// 信号就是状态码本身,同 lib.sh 把 http_<code>/TOKEN_REQUIRED 当读数的口径;网络/超时/跳数/体量
// 上限才是失败信封 {ok:false,code,reason},禁入 evidence 由 G_DEEP 执法)。
//
// 登记表对齐(票面 3):真工具每次已执行调用(含失败信封)发 registry_seed 行,行型与 faux 面
// 逐字同型 {type,call_id,tool,sc}——G_DEEP(≤3/假设+三元组逐字回引)在真面开箱即用,不另起炉灶。
// 预算闸(票面 4;研究 #46:标准由轻载端执行):≤3 次/假设由工具面拒绝,第 4 次调用返回明确拒绝
// 信封(ok:false code=budget)且不发登记行、不执行探测——未发生测量不入登记表;G_DEEP seed 计数
// 只数已执行探测,拒绝后模型转 unresolved 轮仍过门=与门双重执法不互相误杀。
import { Type } from "@earendil-works/pi-ai";
import { safeFetch } from "../tools.mjs";
import { dupRecord } from "./budget.mjs"; // #199 A4:同参调用哈希(零环:budget 只依赖 node 内置)

export const PROBE_TIMEOUT_MS = 15_000; // 超时硬上限(lib.sh FEED_TIMEOUT_S=15 判例,量级 ~15s)
export const PROBE_RANGE_MAX = 256 * 1024; // GET Range ≤256KB(票面:feed 头读数不需要整文件)
// UA 变体(对照探测假象):浏览器形 UA,≠ lib.sh 探测 UA(ip-lookup-tool/1.0)与 tools.mjs UA
// (ip-radar-ops-agent/1.0)——同 URL 换此 UA 的状态码/新鲜度差即 UA 拦截与限流形判别面。
export const PROBE_UA_VARIANT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

const envelope = (code, reason) => ({ ok: false, code, reason: String(reason).slice(0, 200) });
const ageOf = (lm) => (lm ? Math.max(0, Math.floor((Date.now() - Date.parse(lm)) / 86_400_000)) : null); // 同 fetch_url/_ff_probe 口径(时钟偏移钳 0,不出负读数)

// 每假设微探针宿主:三只工具 + 登记行收集 + ≤3 预算闸(逐假设新上下文=每假设新建一个 host)。
// fetchImpl=测试注入缝(自测 fake 传输层经 ctx.probeFetch 传导,零网络);缺省=safeFetch 真网络。
// 返回 { tools, seeds }:tools=pi-agent-core AgentTool 面(initialState.tools 直装);
// seeds=登记行(chronological){call_id,tool,sc}——faux.mjs 据此发 registry_seed transcript 行。
export function mkMicroprobeHost({ fetchImpl = safeFetch, budget = 3, dupRegistry = new Map(), dupLimit = 3 } = {}) {
  const seeds = [];
  const take = (callId, tool, sc, text) => { // 统一收口:登记(失败信封也登记——被引时 G_DEEP 识别 ok:false)+call_id 上翻给模型
    seeds.push({ call_id: callId, tool, sc });
    return { content: [{ type: "text", text: `[call_id=${callId}] ${text}` }], structuredContent: sc };
  }; // call_id 上翻判例=tools.mjs finish:模型看不到运行时生成的调用 id,不翻则 evidence 无从逐字回引
  const rejectOver = (callId) => ({ // 预算拒绝:明确拒绝+出路(转 unresolved);不发登记行不执行(见头注)
    content: [{ type: "text", text: `[call_id=${callId}] 拒绝信封:微探针预算已用满(≤${budget} 次/假设已执行 ${seeds.length} 次)。按 deep.md 预算段转 unresolved——被拦不算你的失败。` }],
    structuredContent: { ok: false, code: "budget", reason: `微探针 ≤${budget} 次/假设已用满;被拦即 unresolved(deep.md 预算段)` },
  });
  const guard = (callId) => (seeds.length >= budget ? rejectOver(callId) : null);
  // #199 A4 同参白烧拦(判例 2026-10-24 01:59 同参重发零新读数):第 dupLimit 次同参调用拒
  // (code=repeat_storm);与 budget 闸同形——不执行不入登记;dupLimit=0 停用;registry
  // 由 faux.mjs 从 ctx 传入(轮次级,跨假设累计;观察面 dup_top3 入 09-budget.json,A5)。
  const rejectDup = (callId, count) => ({
    content: [{ type: "text", text: `[call_id=${callId}] 拒绝信封:同参调用第 ${count} 次≥拦截线 ${dupLimit}。同参数重发不会出新读数(2026-10-24 01:59 同参白烧判例)——换 URL/换工具/换 UA 变体,或转 unresolved/升级人裁。被拦不算你的失败。` }],
    structuredContent: { ok: false, code: "repeat_storm", reason: `同参调用第 ${count} 次≥拦截线 ${dupLimit}(OPS_PIPELINE_DUP_CALL_LIMIT);未执行不入登记` },
  });
  const dupGuard = (callId, tool, p) => {
    if (!(dupLimit > 0)) return null;
    const rec = dupRecord(dupRegistry, tool, p, dupLimit);
    return rec.blocked ? rejectDup(callId, rec.count) : null;
  };

  const reprobeGet = () => ({
    name: "reprobe_get",
    label: "GET 复测",
    description: "只读微探针。同 URL 换 GET+Range(≤256KB)复测,返回 status/last_modified/age_days/bytes(辨 HEAD 假象)。完成 HTTP 交换即读数(≥400 状态码也是读数);网络/超时(15s 硬上限)=失败信封 {ok:false,code,reason},禁入 evidence。",
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    parameters: Type.Object({ url: Type.String({ pattern: "^https?://", maxLength: 500 }) }),
    outputSchema: Type.Object({
      ok: Type.Boolean(), url: Type.String(), final_url: Type.String(), method: Type.String(), status: Type.Number(),
      last_modified: Type.Union([Type.String(), Type.Null()]), age_days: Type.Union([Type.Number(), Type.Null()]), bytes: Type.Number(),
    }),
    execute: async (callId, p) => {
      const dj = dupGuard(callId, "reprobe_get", p); if (dj) return dj;
      const rej = guard(callId); if (rej) return rej;
      try {
        const res = await fetchImpl(p.url, { method: "GET", maxBytes: PROBE_RANGE_MAX, timeoutMs: PROBE_TIMEOUT_MS,
          allowStatus: true, headers: { range: `bytes=0-${PROBE_RANGE_MAX - 1}` } });
        const lm = res.headers["last-modified"] ?? null;
        const sc = { ok: true, url: p.url, final_url: res.finalUrl, method: "GET", status: res.status,
          last_modified: lm, age_days: ageOf(lm), bytes: res.bytes };
        return take(callId, "reprobe_get", sc,
          `GET(Range ≤256KB) ${p.url} → ${res.status};last_modified=${lm ?? "(无)"};age_days=${sc.age_days ?? "null"};bytes=${res.bytes}`);
      } catch (e) {
        const env = envelope(e.code ?? "network", e.message);
        return take(callId, "reprobe_get", env, `失败信封 code=${env.code}:${env.reason}`);
      }
    },
  });

  const reprobeUa = () => ({
    name: "reprobe_ua",
    label: "UA 变体复测",
    description: "只读微探针。同 URL 换浏览器 UA 变体+GET+Range 复测,返回 status/ua/bytes/last_modified/age_days(辨 UA 拦截与限流形:与探测 UA 的状态码/新鲜度差即判别面)。失败信封 {ok:false,code,reason} 禁入 evidence。",
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    parameters: Type.Object({ url: Type.String({ pattern: "^https?://", maxLength: 500 }) }),
    outputSchema: Type.Object({
      ok: Type.Boolean(), url: Type.String(), final_url: Type.String(), method: Type.String(), status: Type.Number(),
      ua: Type.String(), last_modified: Type.Union([Type.String(), Type.Null()]),
      age_days: Type.Union([Type.Number(), Type.Null()]), bytes: Type.Number(),
    }),
    execute: async (callId, p) => {
      const dj = dupGuard(callId, "reprobe_ua", p); if (dj) return dj;
      const rej = guard(callId); if (rej) return rej;
      try {
        const res = await fetchImpl(p.url, { method: "GET", maxBytes: PROBE_RANGE_MAX, timeoutMs: PROBE_TIMEOUT_MS,
          allowStatus: true, headers: { range: `bytes=0-${PROBE_RANGE_MAX - 1}`, "user-agent": PROBE_UA_VARIANT } });
        const lm = res.headers["last-modified"] ?? null;
        const sc = { ok: true, url: p.url, final_url: res.finalUrl, method: "GET", status: res.status, ua: PROBE_UA_VARIANT,
          last_modified: lm, age_days: ageOf(lm), bytes: res.bytes };
        return take(callId, "reprobe_ua", sc,
          `GET(UA 变体,Range ≤256KB) ${p.url} → ${res.status};last_modified=${lm ?? "(无)"};age_days=${sc.age_days ?? "null"};bytes=${res.bytes}`);
      } catch (e) {
        const env = envelope(e.code ?? "network", e.message);
        return take(callId, "reprobe_ua", env, `失败信封 code=${env.code}:${env.reason}`);
      }
    },
  });

  const upstreamCheck = () => ({
    name: "upstream_check",
    label: "上游源头检查",
    description: "只读微探针。上游源头 URL(项目页/releases 索引)活性检查:HEAD 先行,被拒(≥400)或网络败降级 GET Range bytes=0-0(lib.sh _ff_probe 同型);返回 status/server/content_type/last_modified/age_days(辨死键与迁移)。失败信封 {ok:false,code,reason} 禁入 evidence。",
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    parameters: Type.Object({ url: Type.String({ pattern: "^https?://", maxLength: 500 }) }),
    outputSchema: Type.Object({
      ok: Type.Boolean(), url: Type.String(), final_url: Type.String(), method: Type.String(), status: Type.Number(),
      server: Type.Union([Type.String(), Type.Null()]), content_type: Type.Union([Type.String(), Type.Null()]),
      last_modified: Type.Union([Type.String(), Type.Null()]), age_days: Type.Union([Type.Number(), Type.Null()]),
    }),
    execute: async (callId, p) => {
      const dj = dupGuard(callId, "upstream_check", p); if (dj) return dj;
      const rej = guard(callId); if (rej) return rej;
      const read = (res, via) => {
        const lm = res.headers["last-modified"] ?? null;
        const sc = { ok: true, url: p.url, final_url: res.finalUrl, method: via, status: res.status,
          server: res.headers.server ?? null, content_type: res.headers["content-type"] ?? null,
          last_modified: lm, age_days: ageOf(lm) };
        return take(callId, "upstream_check", sc,
          `${via} ${p.url} → ${res.status};server=${sc.server ?? "(无)"};content_type=${sc.content_type ?? "(无)"};last_modified=${lm ?? "(无)"};age_days=${sc.age_days ?? "null"}`);
      };
      try {
        let head = null;
        try { head = await fetchImpl(p.url, { method: "HEAD", timeoutMs: PROBE_TIMEOUT_MS, allowStatus: true }); }
        catch { head = null; } // HEAD 网络败 → GET 降级(_ff_probe_once:rc≠0 也降级)
        if (head && head.status < 400) return read(head, "HEAD");
        try { // HEAD ≥400 或网络败 → GET Range 0-0 取读数(HEAD 专用拒答如 405 由此绕过)
          const g = await fetchImpl(p.url, { method: "GET", maxBytes: PROBE_RANGE_MAX, timeoutMs: PROBE_TIMEOUT_MS,
            allowStatus: true, headers: { range: "bytes=0-0" } });
          return read(g, "GET");
        } catch (e2) {
          if (head) return read(head, "HEAD"); // GET 腿也败但 HEAD 有状态码读数 → 用 HEAD 读数(≥400 也是读数)
          throw e2; // 两腿都网络败 → 失败信封
        }
      } catch (e) {
        const env = envelope(e.code ?? "network", e.message);
        return take(callId, "upstream_check", env, `失败信封 code=${env.code}:${env.reason}`);
      }
    },
  });

  return { tools: [reprobeGet(), reprobeUa(), upstreamCheck()], seeds };
}
