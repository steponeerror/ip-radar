// tools/shared.mjs — 跨面基建(票 #195 C6:tools.mjs 单体按面分层,行为零变化)。
// 落位/边界常量/SSRF 安全取数/lib 助手:被各面文件与门面单向共享(面不互指、不回导入
// 门面)。env 读取面(OPSEVAL_PY/DATA_DIR 等)全部集中本文件(selftest-contract 扫描集
// 随 SRCS 扩至 tools/*.mjs)。
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import dns from "node:dns/promises";
import { fileURLToPath } from "node:url";
import { fetch as undiciFetch, Agent } from "undici";

export const execFileP = promisify(execFile);
const AGENT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."); // 面文件居 tools/ 子层:上移一层=ops/agent,ROOT/LIBSH 推导与拆分前同值(C6)
export const ROOT = path.resolve(AGENT_DIR, "..", ".."); // worktree 根(沙箱红线不变式:落位推导)
export const DOCS_ROOT = process.env.DOCS_ROOT ?? path.join(ROOT, "docs"); // 符号链接 → docs 仓
const LIBSH = path.join(AGENT_DIR, "lib.sh");
// ── 边界常量(env 可覆盖,selftest 用)────────────────────────────────────────
export const B = {
  fetchBytes: +(process.env.OPS_FETCH_MAX_BYTES ?? 512 * 1024),
  fetchPerRound: 20,
  fetchTimeoutMs: 15_000,
  ghPerRound: 15,
  ghTimeoutMs: 60_000,
  queuePerRound: 10,
  readBytes: 50 * 1024,
  readLines: 2000,
  probeBytes: +(process.env.OPS_PROBE_MAX_BYTES ?? 256 * 1024 * 1024),
  probeMaxKeys: +(process.env.OPS_PROBE_MAX_KEYS ?? 1_000_000), // bitwire 4.58M OOM 判例:过线体量人裁
  probeDlTimeoutMs: 300_000,
  probeCliTimeoutMs: +(process.env.OPS_PROBE_CLI_TIMEOUT_MS ?? 1_800_000),
  matrixTimeoutMs: +(process.env.OPS_MATRIX_TIMEOUT_MS ?? 1_200_000),
  anchorSweepTimeoutMs: +(process.env.OPS_ANCHOR_SWEEP_TIMEOUT_MS ?? 300_000), // #182:19 锚直调 lookup 远轻于 matrix 全扫(20min);5min 兑底
  hitCap: 8, // 铁律⑦:判例注入与检索命中上限 8(检索深度伤害决策)
  zeroAssetKb: 32,
  webReadPerRound: 8, // 发现通道三件预算行:防失控非省钱(2026-10-24 裁定,DESIGN §6;预算四界另批)
  webSearchPerRound: 6,
  rssParsePerRound: 6,
  webReadTimeoutMs: 20_000, // r.jina.ai 正文面 20s(票面;上游可 10s+)
  webSearchTimeoutMs: 40_000, // pi-web-access MCP:握手 ~1s + DDG 内部 30s 上限(pi-web-access 0.44.0)
};
export const EVAL_PY = process.env.OPS_EVAL_PY ?? "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
export const DATA_DIR = process.env.OPS_DATA_DIR ?? "/home/huxiao/dev/pi-ip-lookup-tool/backend/data";
const UA = "ip-radar-ops-agent/1.0";
export const FROZEN_DAYS = 180; // threatview 判例:sunset 门线
export const RSS_FRESH_DAYS = 30; // rss 新鲜门(feed 活性):独立常量勿复用 FROZEN_DAYS——门线语义不同(活性 vs sunset 冻结);DESIGN §6 2026-10-24 裁定
// ── SSRF:私网/环回/链路本地(逐跳,fetch_url 与 probe 下载共用)────────────────
const BL = new net.BlockList();
for (const [net4, bits] of [["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8],
  ["169.254.0.0", 16], ["172.16.0.0", 12], ["192.168.0.0", 16], ["198.18.0.0", 15],
  ["224.0.0.0", 4], ["240.0.0.0", 4]]) BL.addSubnet(net4, bits);
for (const [net6, bits] of [["::", 128], ["::1", 128], ["fc00::", 7], ["fe80::", 10], ["ff00::", 8]]) BL.addSubnet(net6, bits, "ipv6");
export function checkPrivateIp(ip) {
  if (ip.toLowerCase().startsWith("::ffff:") && net.isIPv4(ip.slice(7))) ip = ip.slice(7); // v4 映射地址
  return BL.check(ip, ip.includes(":") ? "ipv6" : "ipv4");
}

class SsrfError extends Error { constructor(h) { super(`SSRF 拒绝:${h} 解析到私网/环回/链路本地地址`); this.code = "ssrf"; } }

// 返回本跳已验证的安全地址集(供连接层钉死);IP 字面量已验则返回空数组
// (net.connect 对字面量不走 lookup,直连即已验地址)。
export async function guardHop(rawUrl) {
  const u = new URL(rawUrl);
  if (u.protocol !== "http:" && u.protocol !== "https:") throw Object.assign(new Error(`仅许 http(s):${rawUrl}`), { code: "bad_url" });
  const h = u.hostname.replace(/^\[|\]$/g, "");
  if (net.isIP(h)) { if (checkPrivateIp(h)) throw new SsrfError(h); return []; }
  const addrs = await dns.lookup(h, { all: true }).catch(() => { throw Object.assign(new Error(`DNS 解析失败:${h}`), { code: "network" }); });
  const safe = [];
  for (const { address } of addrs) {
    if (checkPrivateIp(address)) throw new SsrfError(`${h}→${address}`);
    safe.push(address);
  }
  return safe;
}

// 连接层钉死:lookup 只吐 guardHop 已验证的地址——验证与连接同一地址集,
// 堵 TTL-0 DNS 重绑定的双解析 TOCTOU(评审 Important-2,2026-10-19)。
// 选 undici Agent + undici.fetch(而非全局 fetch):全局 fetch 不保证消费自定义 dispatcher;
// hostname/SNI/证书校验仍按域名,仅连接地址被钉。导出供单测钉住机制。
export function pinnedLookup(validatedAddrs) {
  return (hostname, options, callback) => {
    callback(null, validatedAddrs.map((a) => ({ address: a, family: net.isIPv6(a) ? 6 : 4 })));
  };
}

// 手动逐跳重定向:每一跳都过 SSRF 门并钉地址(融合必保:D1 逐跳复检)。
// headers/allowStatus 注入面(#173 微探针专用,既有调用面零改):headers 合并覆盖(Range/UA 变体);
// allowStatus=true 时 ≥400 不抛错照常返回——状态码本身是读数(UA 拦截/限流/死键的判别信号,
// 同 lib.sh 把 http_<code>/TOKEN_REQUIRED 当读数的口径),网络/超时/跳数上限才是失败信封。
export async function safeFetch(rawUrl, { method = "GET", maxBytes, timeoutMs, headers = {}, allowStatus = false } = {}) {
  let url = rawUrl, hops = 0, finalRes, active = null;
  try {
    for (;;) {
      const validated = await guardHop(url);
      const hop = new Agent({ connections: 1, connect: { lookup: pinnedLookup(validated) } });
      let r;
      try {
        r = await undiciFetch(url, {
          method, redirect: "manual", signal: AbortSignal.timeout(timeoutMs),
          headers: { "user-agent": UA, ...headers }, dispatcher: hop,
        });
      } catch (e) {
        await hop.close().catch(() => { /* 本跳失败即弃 */ });
        const why = e?.cause?.message ?? e?.message ?? String(e);
        throw Object.assign(new Error(`网络失败:${why}`), { code: /timeout|abort/i.test(why) ? "timeout" : "network" });
      }
      if (active) await active.close().catch(() => { /* 前一跳体已 cancel */ });
      active = hop;
      finalRes = r;
      if ([301, 302, 303, 307, 308].includes(finalRes.status)) {
        const loc = finalRes.headers.get("location");
        await finalRes.body?.cancel().catch(() => { /* 重定向体不消费,显式 cancel 释放在飞请求 */ });
        if (!loc) throw Object.assign(new Error(`${finalRes.status} 无 Location`), { code: "http_error" });
        if (++hops > 5) throw Object.assign(new Error("重定向 >5 跳"), { code: "too_many_hops" });
        url = new URL(loc, url).toString();
        continue;
      }
      break;
    }
    // GET 体必须在本跳 dispatcher 开着时消费(复审 Important,2026-10-19):undici fetch
    // 头部即 resolve,体流是消费者驱动带背压;先 close() 会等在飞请求,体永不被喡 →
    // 卡到超时。实测复现:30MB 体 headers 20ms,close() 4s+ 仍挂起;177KB 则侥幸过。
    let buf = null;
    if (method === "GET") {
      const reader = finalRes.body.getReader();
      const chunks = []; let n = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        n += value.byteLength;
        if (n > maxBytes) { await reader.cancel(); throw Object.assign(new Error(`响应超过 ${maxBytes}B 上限`), { code: "too_large" }); }
        chunks.push(value);
      }
      buf = Buffer.concat(chunks);
    } else {
      await finalRes.body?.cancel().catch(() => { /* HEAD 等无体请求:显式释放 */ });
    }
    if (finalRes.status >= 400 && !allowStatus) throw Object.assign(new Error(`HTTP ${finalRes.status}`), { code: "http_error", status: finalRes.status });
    // 通道复验轮修复(2026-10-24,轮包 2026-10-24-discover-0634 实锤):原函数体 `const headers`
    // 遮蔽参数解构的 headers(#173 微探针注入面)——函数体 const 全作用域 TDZ,构造请求头处即抛
    // Cannot access 'headers' before initialization,fetch_url/exclusive_probe/微探针 100% 必死。
    // 1412 轮「DEEP 探针网络失败(peeringdb 不通)」归因实为本虫(transcript 在案),非网络。
    const resHeaders = Object.fromEntries(finalRes.headers.entries());
    return { finalUrl: url, status: finalRes.status, headers: resHeaders, body: buf, bytes: buf?.byteLength ?? 0 };
  } finally {
    await active?.close().catch(() => { /* 消费/取消/异常后统一收口(钉址 agent 单跳即弃) */ });
  }
}
export const ts = () => {
  const d = new Date(), p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
};
export const runLib = (fn, args = [], timeoutMs = 600_000) =>
  execFileP("bash", ["-c", `. "$0"; ${fn} "$@"`, LIBSH, ...args],
    { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...process.env } });
export const artifactPath = (dir, slug, ext) => {
  fs.mkdirSync(dir, { recursive: true });
  const p = path.join(dir, `${ts()}-${slug}.${ext}`);
  return p;
};

