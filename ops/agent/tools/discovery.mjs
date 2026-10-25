// tools/discovery.mjs — 发现通道三件(web_read/web_search/rss_parse,PR3a 薄工具批)
// 的归一/解析纯函数核 + pi-web-access MCP 单发会话。不进 MEASUREMENT_TOOLS:发现线索
// 非硬门数字,evidence 语义门不因此放宽(DESIGN §6 2026-10-24 裁定)。
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { Type } from "@earendil-works/pi-ai";
import { B, guardHop, safeFetch, RSS_FRESH_DAYS } from "./shared.mjs";
import { envelope, classifyWebStatus, classifyMcpSearchError } from "./envelope.mjs";

const nodeRequire = createRequire(import.meta.url); // ESM 下解析包内文件真路径(pi-web-access MCP CLI)

// ── 发现通道三件纯函数核(PR3a 薄工具批;DESIGN §6 2026-10-24 修订裁定)──────────
// web_read/web_search/rss_parse 的归一/解析核(离线单测面:selftest-t4 钉归一/截断/
// 畸形行;网络层部署段真网验)。实测事实(2026-10-24,两行为勿写反):r.jina.ai 裸调用
// (无 Authorization)正常,带欠费 key 反 402 → web_read 恒不带 key。
// web_search 引擎 = pi-web-access(2026-10-24 用户令「用 pi-web-access 实现网络搜索」,
// https://pi.dev/packages/pi-web-access;pin 0.44.0):多 provider 网络搜索 + 智能回退
// 链。载体 = 包的 MCP CLI(dist/mcp-cli.js,stdio JSON-RPC)——程序化 dist/index.js
// 只导出 pi extension 面,TS 源在 node_modules 下被 Node 拒绝类型剥离,MCP 是唯一稳定
// 程序化口;每次调用 spawn 一发会话(无守护进程生命周期;预算 ≤6/轮,启动 ~0.3s 可
// 接受)。provider 路由不在代码里选:配置单源 web-search.json(PI_CODING_AGENT_DIR
// 指路,auth.json 同型判例——_ops_rounds._round_env 物化进 ops 树)的 searchRouting
// 回退链 duckduckgo(keyless,isDuckDuckGoAvailable()≡true,零配置一发即活,离线
// 确定性优先)→ jina(可用性 = jinaApiKey/JINA_API_KEY,充值/配置后自然入链);零配置
// Exa MCP 需运行时拉起外部进程,不入链(确定性优先,2026-10-24 裁定)。
export function normalizeJinaRead(rawText, { maxChars = 4000 } = {}) {
  // Jina r 缺省文本面:元数据前缀行(Title:/URL Source:/Markdown Content:,空行分隔);
  // 无前缀(上游形变)则 title=null、整文为正文(宁少算不猜)。
  const lines = String(rawText ?? "").split("\n");
  const skipBlank = (i) => { while (lines[i] !== undefined && lines[i].trim() === "") i++; return i; };
  let title = null, i = 0;
  if (lines[0]?.startsWith("Title:")) {
    title = lines[0].slice("Title:".length).trim() || null;
    i = skipBlank(1);
  }
  // 前缀族逐行可选剥离(审后修 P2:Published Time 行——真 fixture 首发遗漏,带日期页
  // 面该元数据行会漏入正文;同 URL Source 型,出现才吃)
  if (lines[i]?.startsWith("URL Source:")) i = skipBlank(i + 1);
  if (lines[i]?.startsWith("Published Time:")) i = skipBlank(i + 1);
  if (lines[i]?.startsWith("Markdown Content:")) i += 1;
  const body = lines.slice(i).join("\n").trim();
  const content = body.slice(0, maxChars);
  return { title, content, chars_n: content.length, truncated: body.length > content.length };
}

export function parseSerp(rawJson, { num = 5 } = {}) {
  // SERP JSON 归一(通用形状,离线钉解析语义):顶层数组或 {data:[…]} 两形;畸形行
  // (非对象/缺 url)跳过不冒充结果(宁少算);num 本地截断(truncated=服务端多回)。
  // 注:web_search 引擎已换 pi-web-access MCP(PR3a 中程裁定),本画数不再被工具面
  // 调用——保留为 SERP 归一语义钉(零死面:仅 selftest 引)。
  let rows;
  try {
    rows = JSON.parse(String(rawJson ?? ""));
  } catch {
    throw Object.assign(new Error("SERP 响应非 JSON(本地解析失败)"), { code: "io_error" });
  }
  if (rows && typeof rows === "object" && !Array.isArray(rows) && Array.isArray(rows.data)) rows = rows.data;
  if (!Array.isArray(rows)) throw Object.assign(new Error("SERP 形状坏(非数组/data 数组)"), { code: "io_error" });
  const results = [];
  for (const r of rows) {
    if (r == null || typeof r !== "object" || typeof r.url !== "string" || !r.url) continue;
    results.push({
      url: r.url,
      title: String(r.title ?? "").replace(/\s+/g, " ").trim(),
      snippet: String(r.snippet ?? r.description ?? "").replace(/\s+/g, " ").trim().slice(0, 300),
    });
  }
  return { results: results.slice(0, num), n: Math.min(results.length, num), truncated: results.length > num };
}
export function parseRss(rawText, { freshDays = RSS_FRESH_DAYS, now = Date.now() } = {}) {
  // 零依赖最小解析(正则/字符串扫描,勿新增 npm 依赖——薄工具裁定):RSS2.0
  // <item><title>/<link>/<pubDate> + Atom <entry><title>/<link href>/<updated>。
  // 零 item/entry = io_error(feed 结构验证失败,不伪装空读数);无可解析时间 →
  // latest_pubdate/fresh 双 null(fetch_url age_days NO-LM 同型:缺读数≠过期)。
  const text = String(rawText ?? "");
  const strip = (s) => String(s ?? "").replace(/<!\[CDATA\[|\]\]>/g, "").replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
  const pick = (blk, re) => blk.match(re)?.[1] ?? "";
  const items = [];
  let m;
  const itemRe = /<item\b[^>]*>([\s\S]*?)<\/item\s*>/gi;
  while ((m = itemRe.exec(text)) !== null) {
    items.push({
      title: strip(pick(m[1], /<title\b[^>]*>([\s\S]*?)<\/title\s*>/i)),
      link: pick(m[1], /<link\b[^>]*>([\s\S]*?)<\/link\s*>/i).trim(),
      pubdate: pick(m[1], /<pubDate\b[^>]*>([\s\S]*?)<\/pubDate\s*>/i).trim(),
    });
  }
  const entryRe = /<entry\b[^>]*>([\s\S]*?)<\/entry\s*>/gi;
  while ((m = entryRe.exec(text)) !== null) {
    items.push({
      title: strip(pick(m[1], /<title\b[^>]*>([\s\S]*?)<\/title\s*>/i)),
      link: (pick(m[1], /<link\b[^>]*\/?>/i).match(/href\s*=\s*"([^"]*)"/i)?.[1]
        ?? pick(m[1], /<link\b[^>]*>([\s\S]*?)<\/link\s*>/i)).trim(),
      pubdate: pick(m[1], /<updated\b[^>]*>([\s\S]*?)<\/updated\s*>/i).trim(),
    });
  }
  if (!items.length) throw Object.assign(new Error("非 RSS2.0/Atom 形状:零 <item>/<entry>(feed 结构验证失败)"), { code: "io_error" });
  let latest = null, latestStr = null;
  for (const it of items) {
    if (!it.pubdate) continue;
    const t = Date.parse(it.pubdate);
    if (Number.isNaN(t)) continue;
    if (latest === null || t > latest) { latest = t; latestStr = it.pubdate; }
  }
  const ageDays = latest === null ? null : Math.max(0, Math.floor((now - latest) / 86_400_000)); // 时钟偏移铳 0(fetch_url 同口径)
  return {
    items_n: items.length,
    latest_pubdate: latestStr,
    fresh: ageDays === null ? null : ageDays <= freshDays,
    sample: items.slice(0, 3).map((it) => it.title || "(无题)"),
  };
}

// HTTP 状态面通道分类(web_read/web_search 共用;四码语义与 classifyChannelError
// 同族:quota(429/402/余额文案)先于 channel_auth(401/403)——402 归 quota 不归
// channel_auth;文案复用 CHANNEL_HINTS(下一步合法动作,MCP isError 语义);状态面
// ── web_search 引擎:pi-web-access MCP 单发会话(2026-10-24 用户令;见上节选型注)──
const MCP_SEARCH_CMD = "pi-web-access-mcp web_search"; // trace 展示名(真 CLI = resolveMcpCliPath)

function resolveMcpCliPath() {
  // 包无 exports 字段,子路径走 legacy 解析到真实文件;包 pin 0.44.0(package.json)
  return nodeRequire.resolve("pi-web-access/dist/mcp-cli.js");
}

// 单发 MCP 会话:initialize → initialized → tools/call → 收应答即退。stderr 首个
// Error: 行即时捕获(坏配置时 CLI 启动即崩,栈很长,首行是唯一真因面;尾窗只作兑底)。
async function mcpCallToolOnce(toolName, args, timeoutMs) {
  const cli = resolveMcpCliPath();
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [cli], { stdio: ["pipe", "pipe", "pipe"] });
    let buf = "";
    let stderrTail = "";
    let stderrErrLine = null;
    let settled = false;
    const finish = (fn, v) => { if (!settled) { settled = true; clearTimeout(timer); child.kill(); fn(v); } };
    const timer = setTimeout(() => finish(reject, Object.assign(new Error(`MCP 会话超时(>${timeoutMs}ms)`), { killed: true })), timeoutMs);
    const send = (o) => child.stdin.write(JSON.stringify(o) + "\n");
    // stdin EPIPE 守卫(审后修 P2):child 在应答后、下条 send 前死亡时 write 触发
    // EPIPE——未挂监听会让流错误裸崩 agent 进程(违铁律②);此处静默,结局由既有
    // exit/error 事件携带(MCP CLI 提前退出信封),无信息丢失。
    child.stdin.on("error", () => {});
    child.on("error", (e) => finish(reject, e)); // ENOENT(spawn 面)走 classifyMcpSearchError → channel_missing
    child.stderr?.on("data", (d) => {
      const s = String(d);
      stderrTail = `${stderrTail}${s}`.slice(-400);
      if (!stderrErrLine) stderrErrLine = /(?:^|\n)(Error:[^\n]+)/.exec(s)?.[1] ?? /(Failed to parse[^\n]+)/.exec(s)?.[1] ?? null;
    });
    child.on("exit", (code) => finish(reject, Object.assign(
      new Error(`MCP CLI 提前退出(rc=${code ?? "null"})${(stderrErrLine ?? stderrTail) ? `:${String(stderrErrLine ?? stderrTail).replace(/\s+/g, " ").trim().slice(0, 200)}` : ""}`),
      { code: typeof code === "number" ? code : undefined })));
    child.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        let msg;
        try { msg = JSON.parse(line); } catch { continue; }
        if (msg.id === 1) {
          send({ jsonrpc: "2.0", method: "notifications/initialized" });
          send({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: toolName, arguments: args } });
        } else if (msg.id === 2) {
          if (msg.error) finish(resolve, { isError: true, text: `MCP 协议错误:${msg.error.message ?? ""}` });
          else {
            const r = msg.result ?? {};
            finish(resolve, {
              isError: r.isError === true,
              text: (Array.isArray(r.content) ? r.content : []).map((c) => (c && typeof c.text === "string" ? c.text : "")).join("\n"),
            });
          }
        }
      }
    });
    send({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "ip-radar-ops-agent", version: "1.0" } } });
  });
}

// pi-web-access 的 MCP wire 面只吐文本(structuredContent 被剥,formatSearchSummary
// 语法):`**Provider:** <p>` 头 + Sources 块(`N. title\n   url`) + 段内机会式
// `Source: t (u)` 尾行(前文=该源摘要,duckduckgo 形;无此形则 snippet 留空——宁少算)。
// 错误面:provider 失败以 `Error: …` 行内嵌(isError:false!);真 fixture 钉死语法。
export function parseMcpSearchText(text) {
  const t = String(text ?? "");
  const provider = t.match(/^\*\*Provider:\*\*\s*(.+)$/m)?.[1]?.trim() ?? null;
  const srcIdx = t.indexOf("**Sources:**");
  const results = [];
  if (srcIdx >= 0) {
    const end = t.indexOf("\n---", srcIdx);
    const block = t.slice(srcIdx, end >= 0 ? end : undefined);
    const re = /^(\d+)\.\s+(.*?)\r?\n\s+(\S+)\s*$/gm;
    let m;
    while ((m = re.exec(block)) !== null) results.push({ url: m[3].trim(), title: m[2].trim(), snippet: "" });
  }
  if (results.length) {
    const byUrl = new Map(results.map((r) => [r.url, r]));
    for (const para of t.slice(0, srcIdx >= 0 ? srcIdx : t.length).split(/\n{2,}/)) {
      const sm = para.match(/^(?:.|\n)*?Source:\s+.*?\((https?:\/\/[^\s)]+)\)\s*$/);
      if (!sm) continue;
      const r = byUrl.get(sm[1]);
      if (r && !r.snippet) r.snippet = para.replace(/Source:\s+.*$/, "").replace(/\s+/g, " ").trim().slice(0, 300);
    }
  }
  const error = t.match(/^Error:\s*(.+)$/m)?.[1]?.trim() ?? null;
  // wire 漂移哨(审后修 P2:升级后语法漂移会伪装成「零命中」):0.44.0 成功面必有
  // **Provider:** 头(真网实拍 fixture 钉);三无(provider/Sources/Error)且文本非空
  // = wire 变形 → io_error 信封,宁报通道异常不报假零。**包升级必须复跑真网 fixture**
  // (selftest 钉的是 0.44.0 语法)。
  if (!provider && !results.length && !error && t.trim()) {
    throw Object.assign(new Error("MCP wire 文本无 Provider/Sources/Error 标记(语法漂移?pi-web-access 版本升级须复验)"), { code: "io_error" });
  }
  return { provider, results, error };
}

// ── 工具方法(实现零改动,经门面 Object.assign 挂 ToolHost.prototype)────────
export const discoveryMethods = {
  // ── 发现通道三件(PR3a;DESIGN §6 2026-10-24 裁定;不进 MEASUREMENT_TOOLS——发现
  // 线索非硬门数字,evidence 语义门不因此放宽)──────────────────────────────
  webRead() {
    return {
      name: "web_read",
      label: "网页正文读",
      description: "只读。GET r.jina.ai/<url> 取 markdown 正文(awesome 列表/厂商页取证)。恒无鉴权头(实测 2026-10-24:裸调用可用,带欠费 key 反 402);目标 url 先过 SSRF 私网面,逐跳防护同 fetch_url;正文截断头 max_chars(≤8000 缺省 4000);20s;每轮≤8 次。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        url: Type.String({ pattern: "^https?://", maxLength: 500 }),
        max_chars: Type.Optional(Type.Number({ minimum: 200, maximum: 8000, description: "正文保留头 N 字,缺省 4000" })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), url: Type.String(),
        title: Type.Union([Type.String(), Type.Null()]),
        content: Type.String(), chars_n: Type.Number(), truncated: Type.Boolean(),
        trace: Type.Object({ channel: Type.String(), status: Type.Number() }),
      }),
      execute: async (callId, p) => {
        try {
          await guardHop(p.url); // 目标 url 先过 checkPrivateIp 面(SSRF 同 fetch_url 规;Jina 中继不当内网探针)
          const res = await safeFetch(`https://r.jina.ai/${p.url}`, {
            method: "GET", maxBytes: B.fetchBytes, timeoutMs: B.webReadTimeoutMs,
            allowStatus: true, // ≥400 状态码走 classifyWebStatus 四码(Jina r 429/403→quota/channel_auth 文案自然衔接)
          });
          const text = res.body.toString("utf8");
          if (res.status >= 400) {
            const cls = classifyWebStatus(res.status, text, "web_read");
            return this.finish(callId, "web_read",
              { ok: false, code: cls.code, reason: cls.reason, url: p.url, trace: { channel: "r.jina.ai", status: res.status } },
              `web_read 失败信封:${cls.code}: ${cls.reason}`);
          }
          const norm = normalizeJinaRead(text, { maxChars: p.max_chars ?? 4000 });
          const st = { ok: true, url: p.url, ...norm, trace: { channel: "r.jina.ai", status: res.status } };
          return this.finish(callId, "web_read", st,
            `读 ${p.url} → ${res.status};title=${norm.title ?? "(无)"};chars=${norm.chars_n}${norm.truncated ? "(截断)" : ""}\n${norm.content}`);
        } catch (e) {
          // 网络错/超时/SSRF 同 fetch_url 语义(暂态族,提示词可重试 ≤1 次)
          const env = envelope(e.code ?? "network", e.message);
          return this.finish(callId, "web_read", { ...env, url: p.url, trace: { channel: "r.jina.ai", status: 0 } },
            `web_read 失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  },
  webSearch() {
    // 引擎 = pi-web-access MCP(2026-10-24 用户令;选型注见纯函数节);provider 路由
    // 走物化 web-search.json 的 searchRouting 链(duckduckgo keyless 起步,jina 配 key
    // 后入链)——零配置一发即活,取代 Jina 充值前置。契约面与本工具原规格一致。
    return {
      name: "web_search",
      label: "通用搜索",
      description: "只读。pi-web-access 多 provider 网络搜索(缺省路由 duckduckgo,零配置可用;jina 配 key 后入回退链):SERP 归一 {url,title,snippet}。失败四码信封(channel_missing/quota/channel_auth/transient,部署/账户面人裁区注明);num≤8 缺省 5(本地截断+truncated);每轮≤6 次。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        query: Type.String({ minLength: 1, maxLength: 256 }),
        num: Type.Optional(Type.Number({ minimum: 1, maximum: 8 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), query: Type.String(), n: Type.Number(), truncated: Type.Boolean(),
        provider: Type.Union([Type.String(), Type.Null()]),
        results: Type.Array(Type.Object({ url: Type.String(), title: Type.String(), snippet: Type.String() })),
        trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId, p) => {
        const num = p.num ?? 5;
        try {
          const r = await mcpCallToolOnce("web_search", { query: p.query, numResults: num }, B.webSearchTimeoutMs);
          const parsed = parseMcpSearchText(r.text);
          if (r.isError || (!parsed.results.length && parsed.error)) {
            const cls = classifyMcpSearchError(parsed.error ?? r.text);
            return this.finish(callId, "web_search",
              { ok: false, code: cls.code, reason: cls.reason, query: p.query, provider: parsed.provider, trace: { cmd: MCP_SEARCH_CMD, rc: cls.rc } },
              `web_search 失败信封:${cls.code}: ${cls.reason}`);
          }
          const truncated = parsed.results.length > num;
          const results = parsed.results.slice(0, num).map((x) => ({ url: x.url, title: x.title, snippet: x.snippet.slice(0, 300) }));
          const st = { ok: true, query: p.query, n: results.length, truncated, provider: parsed.provider, results, trace: { cmd: MCP_SEARCH_CMD, rc: 0 } };
          const c = `搜索 "${p.query}" → ${results.length} 条(provider=${parsed.provider ?? "?"}${truncated ? ";服务端多回本地截断" : ""})\n`
            + results.map((x) => `- ${x.title || x.url}\n  ${x.url}${x.snippet ? `\n  ${x.snippet}` : ""}`).join("\n");
          return this.finish(callId, "web_search", st, c);
        } catch (e) {
          // spawn 面(ENOENT/超时/CLI 启动崩——坏配置 stderr 在消息里)
          const cls = classifyMcpSearchError(e);
          return this.finish(callId, "web_search",
            { ok: false, code: cls.code, reason: cls.reason, query: p.query, provider: null, trace: { cmd: MCP_SEARCH_CMD, rc: cls.rc } },
            `web_search 失败信封:${cls.code}: ${cls.reason}`);
        }
      },
    };
  },
  rssParse() {
    return {
      name: "rss_parse",
      label: "feed 结构解析",
      description: "只读。GET 原始 feed URL(SSRF 逐跳同 fetch_url)→ 本地零依赖最小解析(RSS2.0 <item>/<pubDate> + Atom <entry>/<updated>):条数/最新发布时间/新鲜门≤30 天(可调 stale_days)/前 3 条样本。非 RSS/Atom 形状=io_error 信封;每轮≤6 次。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        url: Type.String({ pattern: "^https?://", maxLength: 500 }),
        stale_days: Type.Optional(Type.Number({ minimum: 1, maximum: 365, description: "新鲜门天数,缺省 30(RSS_FRESH_DAYS)" })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), url: Type.String(), items_n: Type.Number(),
        latest_pubdate: Type.Union([Type.String(), Type.Null()]),
        fresh: Type.Union([Type.Boolean(), Type.Null()]),
        sample: Type.Array(Type.String()), trace: Type.Object({ method: Type.String(), status: Type.Number() }),
      }),
      execute: async (callId, p) => {
        try {
          const res = await safeFetch(p.url, { method: "GET", maxBytes: B.fetchBytes, timeoutMs: B.fetchTimeoutMs });
          const parsed = parseRss(res.body.toString("utf8"), { freshDays: p.stale_days ?? RSS_FRESH_DAYS });
          const st = { ok: true, url: p.url, ...parsed, trace: { method: "GET", status: res.status } };
          const c = `feed ${p.url} → ${res.status};items=${parsed.items_n};最新发布 ${parsed.latest_pubdate ?? "(无可解析时间)"};fresh=${String(parsed.fresh)};样本:${parsed.sample.join(" | ")}`;
          return this.finish(callId, "rss_parse", st, c);
        } catch (e) {
          // parseRss 零 item/entry → io_error(feed 结构验证失败);网络/SSRF 同 fetch_url 语义
          const env = envelope(e.code ?? "io_error", e.message);
          return this.finish(callId, "rss_parse", { ...env, url: p.url, trace: { method: "GET", status: 0 } },
            `rss_parse 失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  },
};
