// pipeline/discovery-host.mjs — 发现轮 web 三工具宿主(票 #209/T3,ADR 0010;spec
// T3 节):SHORTLIST/MEASURE 步的 web_read/web_search/rss_parse 注入面,microprobes
// (DEEP 真面,#173)同形制——工具=pi-agent-core AgentTool 面(initialState.tools 直装),
// seeds=chronological 登记行 {call_id,tool,sc}(faux.mjs 发 registry_seed 行,G_* 门
// 对账面)。工具实现零复制:discoveryMethods(tools/discovery.mjs,#179)经 Object.assign
// 挂适配器复用——真网络/解析/信封面单源;守卫链 dup→breaker→cap 与 tools.mjs
// ToolHost.beforeToolCall 同序同义(自决已录,#199 B 判例),被拒=零执行零登记(microprobes
// 头注律)但入 blocked 观察面。配额一等公民:通道分列计数 host 内建(channelCounts),
// 纯聚合 aggregateChannelCalls(种子行→计数,回放/对账可算)+构造器
// discoverChannelReadings(T1 CLOSE 进 09-budget.json readings 用;breaker 态快照沿用
// steps.mjs 既有 readings.breaker 面,不重造)。
// 接线协议(T1/T3 合流面,详见 worktree 根 DP-T3-REPORT.md):
//   mkDiscoveryHost({dupRegistry, dupLimit, budgets, breaker, methods}) → {tools, seeds, channelCounts, call}
//   - SHORTLIST(模型步):tools 直装 initialState.tools;dupRegistry 传 ctx 级 Map(
//     与模型调用同 registry,dup 判例 #199 A4 同律);breaker 传轮级 mkBreaker() 实例。
//   - MEASURE(确定性步,零模型):host.call(name, args) 宿主补发 measure-N call-id
//     直调(执行同样过守卫链、同样登记 seed)。
//   - CLOSE:readings 面 discover_channels=discoverChannelReadings(host.channelCounts)
//     (键名由 T1 定,构造器只出值);breaker 快照仍走既有 readings.breaker。
import fs from "node:fs";
import path from "node:path";
import { Type } from "@earendil-works/pi-ai";
import { discoveryMethods } from "../tools/discovery.mjs";
import { BREAKER_CHANNELS, mkBreaker, readBreakerKnobs } from "../tools/breaker.mjs";
import { B } from "../tools/shared.mjs";
import { dupRecord } from "./budget.mjs";
import { ARTIFACTS as A, DISCOVER_SHORTLIST_TRANSCRIPT } from "../artifacts.mjs"; // 工件名单源(C1 判例:回放读面禁手抄磁盘名)

// 发现宿主工具闭集(=BREAKER_CHANNELS 的 web 三员;gh_search 留 legacy 面,spec T3)
export const DISCOVERY_TOOLS = Object.freeze(["web_read", "web_search", "rss_parse"]);
// 每轮帽缺省=tools/shared.mjs B 常量单源(与 legacy discover 轮 ToolHost budgets 同源,
// tools.mjs:31——两宿主同一事实,不另立数字);T1 合流时如需 OPS_DISCOVER_* 旋钮化,
// 经 opts.budgets 注入,缺省面不动。
export const DEFAULT_DISCOVERY_BUDGETS = Object.freeze({
  web_read: B.webReadPerRound,
  web_search: B.webSearchPerRound,
  rss_parse: B.rssParsePerRound,
});

export function mkDiscoveryHost({
  dupRegistry = new Map(),
  dupLimit = 3,
  budgets = DEFAULT_DISCOVERY_BUDGETS,
  breaker = null, // mkBreaker() 产物(可选;管线面由 T1 传轮级实例,测试可注假面)
  methods = discoveryMethods, // 测试缝:注入假实现面(真面走真网络/spawn 不可离线测)
} = {}) {
  const seeds = [];
  const channelCounts = {}; // {[tool]: {executed, ok, failed, blocked}} 惰性建
  const cell = (t) => channelCounts[t] ?? (channelCounts[t] = { executed: 0, ok: 0, failed: 0, blocked: 0 });
  let seq = 0;

  const reject = (callId, tool, code, reason) => { // 被拒=零执行零登记;入 blocked 观察面
    cell(tool).blocked += 1;
    return {
      content: [{ type: "text", text: `[call_id=${callId}] 拒绝信封(code=${code}):${reason}` }],
      structuredContent: { ok: false, code, reason: String(reason).slice(0, 200) },
    };
  };
  // 适配器:this.finish=登记收口(失败信封也登记——被引时门内识别 ok:false)+
  // 通道计数+熔断回写+call_id 上翻(tools.mjs finish 同判例:模型看不到运行时 id)
  const adapter = {
    finish(callId, name, structured, contentText) {
      seeds.push({ call_id: callId, tool: name, sc: structured });
      const c = cell(name);
      c.executed += 1;
      if (structured?.ok === true) c.ok += 1; else c.failed += 1;
      if (breaker && BREAKER_CHANNELS.includes(name) && structured && typeof structured.ok === "boolean")
        breaker.record(name, { ok: structured.ok, code: structured.code });
      return { content: [{ type: "text", text: `[call_id=${callId}] ${contentText}` }], structuredContent: structured };
    },
  };
  Object.assign(adapter, methods);
  // 守卫链(与 tools.mjs beforeToolCall 同序:dup→breaker→cap;被拦零执行零花费不占帽)
  const guardDup = (name, p) => {
    if (!(dupLimit > 0)) return null;
    const rec = dupRecord(dupRegistry, name, p, dupLimit);
    return rec.blocked ? { code: "repeat_storm",
      reason: `同参调用第 ${rec.count} 次≥拦截线 ${dupLimit}(OPS_PIPELINE_DUP_CALL_LIMIT);同参数重发不会出新读数——改参数(换 URL/检索词)或升级人裁` } : null;
  };
  const guardBreaker = (name) => {
    if (!breaker || !BREAKER_CHANNELS.includes(name)) return null;
    const v = breaker.verdict(name);
    return v.action === "block" ? { code: "channel_open",
      reason: `通道 ${name} 熔断开断中(冷却剩 ${v.probe_in_flight ? "探活在飞" : `${v.retryAfterS}s`});开断期该通道零调用——改用本地读面或升级人裁` } : null;
  };
  const guardCap = (name) => {
    const max = budgets[name];
    if (max !== undefined && cell(name).executed >= max)
      return { code: "budget", reason: `预算超限:${name} 每轮上限 ${max} 次已用满;升级人裁区` };
    return null;
  };
  const METHOD_OF = Object.freeze({ web_read: "webRead", web_search: "webSearch", rss_parse: "rssParse" });
  const wrap = (tool) => ({
    ...tool,
    execute: async (callId, p) => {
      const dj = guardDup(tool.name, p); if (dj) return reject(callId, tool.name, dj.code, dj.reason);
      const bj = guardBreaker(tool.name); if (bj) return reject(callId, tool.name, bj.code, bj.reason);
      const cj = guardCap(tool.name); if (cj) return reject(callId, tool.name, cj.code, cj.reason);
      // this=adapter(实现面 this.finish 收口;箭头 execute 词法 this 已绑,常规函数面
      // .call 兜底——注入协议要求 methods 为适配器方法形)
      return tool.execute.call(adapter, callId, p);
    },
  });
  const tools = DISCOVERY_TOOLS.map((n) => wrap(adapter[METHOD_OF[n]]()));
  // MEASURE 侧确定性直调(T1 占位对齐):宿主补发 measure-N(与运行时模型 call-id
  // 不撞);同样过守卫链、同样登记。
  async function call(name, args) {
    const tool = tools.find((x) => x.name === name);
    if (!tool) throw new Error(`未知工具 ${name}(发现宿主闭集:${DISCOVERY_TOOLS.join("/")})`);
    return tool.execute(`measure-${(seq += 1)}`, args);
  }
  return { tools, seeds, channelCounts, call };
}

// ── 接线面(#217 T3.5;头注接线协议的落地消费点)────────────────────────
// breaker 态文件路径单源:CLOSE 观察快照(steps.mjs)与发现宿主 record 读写共用同一文件
// ——两处各自手拼=漂移即双态(一文件一拼)。ctx 面与 steps.mjs CLOSE 原判例同形。
export const breakerFileOf = (ctx) => path.join(ctx.opsRoot ?? path.dirname(ctx.dir), "breaker.json");

// 轮级发现宿主单例:惰性建于 ctx.discoverHost——SHORTLIST(真面工具直装 initialState.tools)
// 与 MEASURE(host.call 补发 measure-N)共用同一实例=同守卫链同配额面。dupRegistry=ctx 级
// Map(与模型调用同 registry,dup 判例 #199 A4 同律);dupLimit=发现旋钮 dupCallLimit
// (readDiscoverKnobs,#217 T3.5 追键);breaker=轮级 mkBreaker() 绑 ops/breaker.json(与
// CLOSE 快照同文件同旋钮)。resume 后宿主缺席=常态(已录步跳过),CLOSE 读数走工件回放
// (replayDiscoverSeeds)。测试缝:methods 注假实现面(缺省真面=网络/spawn 不可离线测)。
export function ensureDiscoverHost(ctx, { methods = discoveryMethods } = {}) {
  if (ctx.discoverHost) return ctx.discoverHost;
  ctx.discoverHost = mkDiscoveryHost({
    dupRegistry: ctx.dupRegistry ?? new Map(),
    dupLimit: ctx.budgetKnobs?.dupCallLimit ?? 3,
    breaker: mkBreaker({
      file: breakerFileOf(ctx), env: ctx.env ?? {}, round: ctx.roundId ?? "discover",
      knobs: ctx.breakerKnobs ?? readBreakerKnobs(ctx.env ?? {}), ledgerFile: ctx.ledgerFile, log: ctx.log,
    }),
    methods,
  });
  return ctx.discoverHost;
}

// faux 罐装方法面(零网络律):fixtures measure.json web_reads 表→web_read 罐装读数
// (未罐装 URL=io_error 未罐装信封;罐 ok:false 行=罐装失败面,供测试确定性模拟死链/鉴权);
// web_search/rss_parse faux 面恒 io_error 未罐装——faux 宇宙只罐 MEASURE 消费的读面,
// 不罐不虚构。方法形状与 discoveryMethods 同构(name/label/description/annotations/
// parameters/execute;this.finish 收口同注入协议)。
export function fixtureDiscoveryMethods(fx = {}) {
  const reads = new Map((Array.isArray(fx.web_reads) ? fx.web_reads : []).map((r) => [String(r?.url ?? ""), r]));
  const miss = (code, reason) => ({ ok: false, code, reason });
  const cannedFail = (r, url) => ({ ok: false, code: String(r?.code ?? "channel_missing"), reason: String(r?.reason ?? "faux 罐装失败面(measure.json web_reads ok:false)"), url, trace: { channel: "faux", status: Number(r?.status ?? 0) } });
  const uncanned = (url) => ({ ok: false, code: "io_error", reason: `faux 未罐装该 URL(零网络律;fixtures measure.json web_reads 补)`, url, trace: { channel: "faux", status: 0 } });
  // 注意方法形:this=适配器(Object.assign 挂 adapter 后经 adapter.<factory>() 调用,
  // execute 箭头捕获方法 this——与 discoveryMethods 同注入协议,勿改成脱对象工厂函数;
  // notCannedTool 须常规函数:.call(this) 传导 adapter 进闭包(箭头函数 .call 无效)
  function notCannedTool(tool) {
    return {
    name: tool, label: `${tool}(faux 未罐装)`,
    description: "faux 面恒 io_error 未罐装(零网络;MEASURE 面不消费本工具)",
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    parameters: Type.Object({ query: Type.String({ maxLength: 500 }) }),
    execute: async (callId) => this.finish(callId, tool, miss("io_error", `faux 未罐装 ${tool}(零网络律)`),
        `${tool} 失败信封(faux):io_error: 未罐装`),
    };
  }
  return {
    webRead() {
      return {
        name: "web_read", label: "网页正文读(faux 罐装)",
        description: "faux 面罐装读数(measure.json web_reads 表;未罐装=io_error,罐 ok:false=罐装失败面;零网络)",
        annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
        parameters: Type.Object({ url: Type.String({ pattern: "^https?://", maxLength: 500 }) }),
        execute: async (callId, p) => {
          const r = reads.get(p.url);
          if (!r) return this.finish(callId, "web_read", uncanned(p.url), `web_read 失败信封(faux):io_error: 未罐装 ${p.url}`);
          if (r.ok !== true) return this.finish(callId, "web_read", cannedFail(r, p.url), `web_read 失败信封(faux):${r.code}: ${r.reason}`);
          const content = String(r.content ?? "");
          return this.finish(callId, "web_read",
            { ok: true, url: p.url, title: r.title ?? null, content, chars_n: content.length, truncated: Boolean(r.truncated ?? false), trace: { channel: "faux", status: 200 } },
            `读(faux 罐装) ${p.url};title=${r.title ?? "(无)"};chars=${content.length}\n${content}`);
        },
      };
    },
    webSearch() { return notCannedTool.call(this, "web_search"); },
    rssParse() { return notCannedTool.call(this, "rss_parse"); },
  };
}

// 工件回放重算(证据永不灭失):宿主缺席(resume 后 MEASURE 已录跳过)时 CLOSE 读数面的
// 回放源=d2 transcript registry_seed 行(真面 SHORTLIST 工具调用留痕)+ d3-measure.json
// tool_seeds(MEASURE 补发留痕)。被拒不入种子(头注律)→回放面恒宁少算(blocked 观察面
// 不回放);坏行跳过不掷错(回放是补面非门面——门面吞坏行才是假读数,回放面宁少算)。
// 工具名过滤=DISCOVERY_TOOLS 闭集(健康轮 probe 工具不混入)。
export function replayDiscoverSeeds(ctx) {
  const rows = [];
  try {
    for (const line of fs.readFileSync(path.join(ctx.dir, DISCOVER_SHORTLIST_TRANSCRIPT), "utf8").split("\n")) {
      if (!line.trim()) continue;
      let o; try { o = JSON.parse(line); } catch { continue; } // 坏行跳过(宁少算)
      if (o?.type === "registry_seed" && DISCOVERY_TOOLS.includes(o.tool) && o.sc && typeof o.sc.ok === "boolean")
        rows.push({ tool: o.tool, ok: o.sc.ok });
    }
  } catch { /* transcript 缺席=零真面工具调用(faux 轮常态) */ }
  let m = null;
  try { m = JSON.parse(fs.readFileSync(path.join(ctx.dir, A.DISCOVER_MEASURE), "utf8")); } catch { /* 缺席=步未达 */ }
  if (m && Array.isArray(m.tool_seeds))
    for (const s of m.tool_seeds)
      if (s && DISCOVERY_TOOLS.includes(s.tool) && s.sc && typeof s.sc.ok === "boolean") rows.push({ tool: s.tool, ok: s.sc.ok });
  return rows;
}

// 纯聚合:种子行(registry_seed 面 {tool, sc:{ok}})或扁平行 {tool, ok} → 通道分列
// 调用计数。只聚已执行面(被拒不入种子,宁少算);行形状坏(缺 tool/ok 非布尔)掷错
// 不静默吞——本面供 G_ENQUEUE/RETRO 对账与 CLOSE 回放重算,吞坏行=假读数。
export function aggregateChannelCalls(rows) {
  const out = {};
  for (const r of rows ?? []) {
    if (!r || typeof r.tool !== "string")
      throw new Error(`计数行缺 tool:${JSON.stringify(r)?.slice(0, 120)}`);
    const ok = typeof r.ok === "boolean" ? r.ok
      : r.sc && typeof r.sc.ok === "boolean" ? r.sc.ok : undefined;
    if (ok === undefined)
      throw new Error(`计数行 ${r.tool} 的 ok 非布尔(种子行须带 sc.ok):${JSON.stringify(r)?.slice(0, 120)}`);
    const c = out[r.tool] ?? (out[r.tool] = { calls: 0, ok: 0, failed: 0 });
    c.calls += 1;
    if (ok) c.ok += 1; else c.failed += 1;
  }
  return out;
}

// 09-budget.json readings 构造器(T1 CLOSE 消费):host 面 channelCounts(executed+
// blocked)或 aggregateChannelCalls 输出(calls,无 blocked)皆可入——两词一义=已执行。
// 不变量 ok+failed=calls 违者/非非负整数=掷错(构造期响,不落错读数进工件)。
// breaker 态快照沿用 steps.mjs 既有 readings.breaker 面——本构造器不重造(票面明示)。
export function discoverChannelReadings(channelCounts) {
  const channels = {};
  let calls_total = 0, blocked_total = 0;
  for (const [tool, raw] of Object.entries(channelCounts ?? {})) {
    const c = raw ?? {};
    const calls = c.calls ?? c.executed ?? 0;
    const ok = c.ok ?? 0, failed = c.failed ?? 0, blocked = c.blocked ?? 0;
    if (![calls, ok, failed, blocked].every((n) => Number.isInteger(n) && n >= 0))
      throw new Error(`通道 ${tool} 计数非非负整数:${JSON.stringify(c)}`);
    if (ok + failed !== calls)
      throw new Error(`通道 ${tool} 不变量破:ok(${ok})+failed(${failed})≠calls(${calls})`);
    channels[tool] = Object.freeze({ calls, ok, failed, blocked });
    calls_total += calls;
    blocked_total += blocked;
  }
  return Object.freeze({ channels: Object.freeze(channels), calls_total, blocked_total });
}
