// tools.mjs — 融合领域工具面(11 工具 = discover 10 + health 1;PR3a 发现通道三件并入,
// 2026-10-24 裁定)+ 写前语义门(计划书 Task 4 终稿;融合必保 6 条
// = tool-critic-1/2 并集;铁律①-⑦ 见各段注释)。
//
// 结构性红线(铁律⑥):零内建工具——本文件只注册下列领域工具,agent 无 bash/write/edit;
// 唯一写口 = queue_action(append-only,恒 vetoable,幂等去重),包/台账/判例写回全在 host。
// 警察函数(校验/沙箱/台账)不注册为工具(被审计者不持审计工具)。
//
// 失败面统一(铁律②):一切失败 = 结构化信封 {ok:false,code,reason},不抛裸栈、不静默;
// 信封禁止入 evidence(语义门拒绝),降级人裁区。硬门数字只认 structuredContent,
// 测量工具恒带 trace{cmd,rc,artifact}(铁律③)。
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import dns from "node:dns/promises";
import { fileURLToPath } from "node:url";
import { fetch as undiciFetch, Agent } from "undici";
import { Type } from "@earendil-works/pi-ai";

const execFileP = promisify(execFile);
const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(AGENT_DIR, "..", ".."); // worktree 根(沙箱红线不变式:落位推导)
export const DOCS_ROOT = process.env.DOCS_ROOT ?? path.join(ROOT, "docs"); // 符号链接 → docs 仓
const LIBSH = path.join(AGENT_DIR, "lib.sh");

// ── 边界常量(env 可覆盖,selftest 用)────────────────────────────────────────
const B = {
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
  hitCap: 8, // 铁律⑦:判例注入与检索命中上限 8(检索深度伤害决策)
  zeroAssetKb: 32,
  webReadPerRound: 8, // 发现通道三件预算行:防失控非省钱(2026-10-24 裁定,DESIGN §6;预算四界另批)
  webSearchPerRound: 6,
  rssParsePerRound: 6,
  webReadTimeoutMs: 20_000, // r.jina.ai 正文面 20s(票面;上游可 10s+)
  webSearchTimeoutMs: 30_000, // s.jina.ai SERP 首查常 10-20s,给 30s
};
const EVAL_PY = process.env.OPS_EVAL_PY ?? "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
const DATA_DIR = process.env.OPS_DATA_DIR ?? "/home/huxiao/dev/pi-ip-lookup-tool/backend/data";
const UA = "ip-radar-ops-agent/1.0";
export const FROZEN_DAYS = 180; // threatview 判例:sunset 门线
export const RSS_FRESH_DAYS = 30; // rss 新鲜门(feed 活性):独立常量勿复用 FROZEN_DAYS——门线语义不同(活性 vs sunset 冻结);DESIGN §6 2026-10-24 裁定
const PREDICATES = ["sunset_frozen", "mirror_echo", "zero_asset"]; // discover 谓词表闭集
const MEASUREMENT_TOOLS = new Set(["fetch_url", "gh_search", "exclusive_probe", "matrix_scan_summary"]);
// 发现通道三件(web_read/web_search/rss_parse,PR3a)不进 MEASUREMENT_TOOLS:与测量工具的边界
// =数据形状天然隔离(发现线索非硬门数字),evidence 语义门不因发现通道放宽(DESIGN §6 2026-10-24 裁定)。

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
async function guardHop(rawUrl) {
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

// ── 通用助手 ──────────────────────────────────────────────────────────────
const envelope = (code, reason) => ({ ok: false, code, reason });
const ts = () => {
  const d = new Date(), p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
};
const runLib = (fn, args = [], timeoutMs = 600_000) =>
  execFileP("bash", ["-c", `. "$0"; ${fn} "$@"`, LIBSH, ...args],
    { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...process.env } });
const artifactPath = (dir, slug, ext) => {
  fs.mkdirSync(dir, { recursive: true });
  const p = path.join(dir, `${ts()}-${slug}.${ext}`);
  return p;
};

// ── matrix 扫描 CLI 单源(P1,#163)───────────────────────────────────────────
// tools.mjs health_snapshot(matrix 腿)与 pipeline/steps.mjs PROBE 共用同一调用路径:
// 位等价=同 EVAL_PY 命令+同解析+同工件序列化(matrixArtifactText);legacy 侧零行为改动
// (runMatrixScan 只剩三分支收编的薄包装)。返回分支:
//   {ok:true, d, rc, cmd}               读数(rc 0/1/2 都是读数,round.sh T3 判例)
//   {ok:false, env, cmd, trace:null}     stdout 带 error 键的失败信封(无 trace,同原语义)
//   {ok:false, env, cmd, trace:{cmd,rc}} 裸失败信封(带 trace)
export async function matrixScanCli() {
  const cmd = `cd backend && IP_RADAR_DATA_DIR=${DATA_DIR} ${EVAL_PY} -m ipdb._eval --matrix-scan --json --assets-dir ${DATA_DIR}/eval/assets`;
  try {
    const { stdout } = await execFileP(EVAL_PY,
      ["-m", "ipdb._eval", "--matrix-scan", "--json", "--assets-dir", `${DATA_DIR}/eval/assets`],
      { cwd: path.join(ROOT, "backend"), env: { ...process.env, IP_RADAR_DATA_DIR: DATA_DIR },
        timeout: B.matrixTimeoutMs, maxBuffer: 32 * 1024 * 1024 });
    const d = JSON.parse(stdout);
    if (d.error) return { ok: false, env: envelope(d.error.code ?? "matrix_failed", d.error.message ?? ""), cmd, trace: null };
    return { ok: true, d, rc: 0, cmd };
  } catch (e) {
    // rc 0/1/2 = 读数(干净/pending/violation,round.sh T3 判例);execFile 对非零退出 reject,
    // 但 stdout 携带带 exit_code 的有效 JSON 时仍是读数不是故障
    try {
      const d = JSON.parse(String(e.stdout ?? ""));
      if (typeof d.exit_code === "number") return { ok: true, d, rc: e.code ?? 0, cmd };
      if (d.error) return { ok: false, env: envelope(d.error.code ?? "matrix_failed", d.error.message ?? ""), cmd, trace: null };
    } catch { /* 裸失败走信封 */ }
    return { ok: false, env: envelope("matrix_failed", String(e.stderr ?? e.message ?? "").slice(0, 300)), cmd, trace: { cmd, rc: e.code ?? 1 } };
  }
}
export const matrixArtifactText = (d) => JSON.stringify(d, null, 1); // matrix 工件序列化单源:legacy <ts>-matrix-scan.json 与管线 01-probe-matrix.json 逐字节同文(#163 位等价)

export function countFeedKeys(text) { // probe 键量:IPv4 去重(exclusive.py _IP_RE 同口径的 v4 面)
  return new Set(text.match(/(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?/g)?.map((t) => t.split("/")[0]) ?? []).size;
}

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

// ── 判例检索单源(PR #177;判例 2026-10-24-discover-dual-channel-dead)────────────
// rg spawn argv 逐字对齐 backend/ipdb/_ops_store.rg_search_precedents(Python 参考实现,
// Python 面零改动):["rg","-i","-l","-g","*.md","-g","!_*",...每词 "-e",kw,dir]。
// 成功路径注入块与 lib.sh inject_precedents 逐字节等价(golden/inject-block.* 钉死;
// fmField 重实现 fm_block 拍平语义);失败面走 classifyChannelError 分类信封
// (rc=1 = 真零命中;rc≥2/ENOENT/超时 ≠ 零命中)。agent.mjs 宿主预注入同调本函数(单源);
// lib.sh inject_precedents 保留仅供 pipeline/steps.mjs(pipeline 面本批冻结不触;
// 两路输出 golden 字节等价由 selftest-t4 对拍钉死)。
export const RG_TIMEOUT_MS = 60_000; // _ops_store._RG_TIMEOUT_S 同值(两侧同签,勿单边改)

export function resolvePrecedentsDir(env = process.env) {
  // call-time 解析(契约表 PRECEDENTS_DIR phase=call-time;DOCS_ROOT 用模块顶 import-time 值兑底)
  return env.PRECEDENTS_DIR ?? path.join(env.DOCS_ROOT ?? DOCS_ROOT, "ops", "precedents");
}

// fmField — lib.sh fm_block 的 JS 逐语义重实现(frontmatter 顶层字段拍平摘要,非 YAML 解析)。
// 字节等价的隐藏细节(golden 钉死,以现行为准不顺手修正):
//   - key 行内联值记入,块标示符(> / |)起头不记:折叠字段首个续行拍平后带前导空格 →
//     「context:  」双空格是现行输出真形状;
//   - 字段块内任何非缩进行(含空行)= 块终止(awk exit 语义:单引号多行值 key 行后空行即截断);
//   - 续行/嵌套子键(reward 映射)两侧 [ \t] 裁剪后以单空格连接,空续行跳过。
export function fmField(text, field) {
  const lines = text.split("\n");
  if (lines[0] !== "---") return ""; // NR==1 非 ---:无 frontmatter
  let out = "", active = false;
  for (let i = 1; i < lines.length; i++) {
    const l = lines[i];
    if (/^---/.test(l)) break; // frontmatter 终线
    const m = l.match(/^([A-Za-z_][A-Za-z0-9_]*):/); // 顶层键(列 0;缩进子键不命中)
    if (m) {
      if (m[1] === field) {
        active = true;
        const rest = l.slice(m[0].length).replace(/^[ \t]+/, "").replace(/[ \t]+$/, "");
        if (rest !== "" && !/^[|>]/.test(rest)) out += (out === "" ? "" : " ") + rest;
      } else if (active) break; // 下一顶层键 = 本字段块结束
      continue;
    }
    if (active && /^[ \t]/.test(l)) {
      const line = l.replace(/^[ \t]+/, "").replace(/[ \t]+$/, "");
      if (line !== "") out += " " + line; // 首续行前导空格 = 双空格细节的来源
    } else if (active) break; // 非缩进行(含空行)= 字段块终止
  }
  return out;
}

// 返回 { block, files, trace }:block=注入块文本(逐字节等价 lib.sh;含尾换行);files=
// 排序去重命中路径(sort -u 语义;词法序——判例文件名全 ASCII 日期前缀,locale 无关);
// trace={cmd:真 argv,rc:真 rc}。失败抛 Error(.envelope={code,rc,reason} 分类信封 + .trace)。
export async function searchPrecedentsCore(keywords, { precedentsDir, env = process.env, timeoutMs = RG_TIMEOUT_MS } = {}) {
  const dir = path.resolve(precedentsDir ?? resolvePrecedentsDir(env));
  // execFile(file,args) 的 args 不含二进制名(Python subprocess 全 argv 含 "rg" ——两侧逻辑
  // argv 逐字对齐,此处拼接点不同);trace.cmd 展示含 rg 的完整逻辑 argv
  const args = ["-i", "-l", "-g", "*.md", "-g", "!_*"];
  for (const kw of keywords) args.push("-e", kw);
  args.push(dir);
  const cmd = ["rg", ...args].map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ");
  let stdout = "";
  if (keywords.length) { // 零词守卫(lib.sh 同形:不跑 rg——rg 无 pattern 会 rc=2;Python 面由 ValueError 拒词,契约对拍不覆盖零词)
    try {
      ({ stdout } = await execFileP("rg", args, { timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024, env }));
    } catch (e) {
      if (e.code === 1) stdout = String(e.stdout ?? ""); // rc=1 = 真零命中(Python 参考同语义;execFile 对非零退出 reject,此处置回成功面)
      else {
        const cls = classifyChannelError(e, "rg");
        throw Object.assign(new Error(cls.reason), { envelope: cls, trace: { cmd, rc: cls.rc } });
      }
    }
  }
  const files = [...new Set(stdout.split("\n").filter((l) => l !== ""))].sort();
  const kwsLine = keywords.join(" ");
  if (!files.length) {
    return { block: `### 注入判例(检索词: ${kwsLine})\n无判例(检索词: ${kwsLine})\n`, files, trace: { cmd, rc: 0 } };
  }
  const blockLines = [`### 注入判例(检索词: ${kwsLine})`];
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8"); // rg 输出行即路径(与 lib.sh fm_block "$f" 同读法)
    blockLines.push(`- ${path.basename(f)}`);
    for (const field of ["context", "human_ruling", "reward"]) blockLines.push(`  - ${field}: ${fmField(text, field)}`);
  }
  return { block: `${blockLines.join("\n")}\n`, files, trace: { cmd, rc: 0 } };
}

// ── 发现通道三件纯函数核(PR3a 薄工具批;DESIGN §6 2026-10-24 修订裁定)──────────
// web_read/web_search/rss_parse 的归一/解析核(离线单测面:selftest-t4 钉归一/截断/
// 畸形行;网络层部署段真网验)。实测事实(2026-10-24,两行为勿写反):r.jina.ai 裸调用
// (无 Authorization)正常,带欠费 key 反 402 → web_read 恒不带 key;s.jina.ai 必须
// Bearer key(缺配=channel_auth 部署面;欠费 402=quota 账户面,充值即活,信封诚实报)。
export function normalizeJinaRead(rawText, { maxChars = 4000 } = {}) {
  // Jina r 缺省文本面:元数据前缀行(Title:/URL Source:/Markdown Content:);
  // 无前缀(上游形变)则 title=null、整文为正文(宁少算不猜)。
  const lines = String(rawText ?? "").split("\n");
  let title = null, start = 0;
  if (lines[0]?.startsWith("Title:")) {
    title = lines[0].slice("Title:".length).trim() || null;
    start = 1;
  }
  if (lines[start]?.startsWith("URL Source:")) start += 1;
  if (lines[start]?.startsWith("Markdown Content:")) start += 1;
  const body = lines.slice(start).join("\n").trim();
  const content = body.slice(0, maxChars);
  return { title, content, chars_n: content.length, truncated: body.length > content.length };
}

export function parseSerp(rawJson, { num = 5 } = {}) {
  // s.jina.ai SERP 归一:顶层数组或 {data:[…]} 两形;畸形行(非对象/缺 url)跳过不
  // 冒充结果(宁少算);num 本地截断(truncated=服务端多回,诚实标)。
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
// 无 spawn,rc 恒 HTTP status;http_error 无 hint(提示词暂态条款辖,同 fetch_url)。
function classifyWebStatus(status, bodyText, channel) {
  const body = String(bodyText ?? "").replace(/\s+/g, " ").trim().slice(0, 160);
  let code;
  if (status === 429 || status === 402 || /balance|insufficient/i.test(body)) code = "quota";
  else if (status === 401 || status === 403) code = "channel_auth";
  else code = "http_error";
  const detail = `${channel} HTTP ${status}${body ? `:${body}` : ""}`;
  const hint = CHANNEL_HINTS[code];
  return { code, rc: status, reason: hint ? `${detail}——${hint}` : detail };
}

// ── 读面白名单(融合必保 4:显式拒 .env/密钥模式/.venv/data;门=实现双层之实现层)──
const DENY_NAME = [/\.env(\.|$)/i, /\.pem$/i, /\.p12$/i, /\.key$/i, /(^|[-_.])(priv|secret|credential)s?([-_.]|$)/i];
const DENY_SEG = [".git", ".venv", "node_modules", "backend/data"];
export function checkReadablePath(absPath) {
  // 不存在的路径不 realpath(ENOENT 会抢在拒读判定前炸):词法归一化即可支撑白名单/拒读判定
  const real = fs.existsSync(absPath) ? fs.realpathSync(absPath) : path.resolve(absPath);
  const rootOf = (r) => (fs.existsSync(r) ? fs.realpathSync(r) : path.resolve(r));
  const roots = [rootOf(ROOT), rootOf(DOCS_ROOT)];
  if (!roots.some((r) => real === r || real.startsWith(r + path.sep))) {
    throw new Error(`路径越界(白名单=仓根+docs 根):${absPath}`);
  }
  const rel = path.relative(ROOT, real);
  if (DENY_SEG.some((s) => rel.split(path.sep).includes(s) || rel.includes(s + path.sep))) {
    throw new Error(`路径禁读(${DENY_SEG.join("/")}):${absPath}`);
  }
  const base = path.basename(real).toLowerCase();
  if (DENY_NAME.some((re) => re.test(base))) throw new Error(`疑似密钥/凭证文件拒读(.env/密钥模式):${absPath}`);
  return real;
}

// evidence 字段点路径解析:"results.0.size_kb" / "results[0].size_kb" → 嵌套取值;无命中 undefined。
// 导出供金轨迹 runner 复用同一解析语义(T6,避免断言侧另起炉灶)。
export function resolveField(obj, field) {
  const parts = String(field).replace(/\[(\d+)\]/g, ".$1").split(".");
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object" || !(p in cur)) return undefined;
    cur = cur[p];
  }
  return cur;
}

// ── 判例引用闭合校验(铁律④:路径 ∈ 预注入 ∪ 本会话检索命中;存在性不够)────────
export function closureCheck(pkgText, allowed /* Set<string> 文件名 */) {
  const lines = pkgText.split("\n");
  const sec = []; let inSec = false;
  for (const l of lines) {
    if (/^#+\s.*注入判例/.test(l)) { inSec = true; continue; }
    if (inSec && /^#+\s/.test(l)) break;
    if (inSec) sec.push(l);
  }
  if (!sec.length) throw new Error("闭合校验:包缺少「注入判例」节");
  const toks = [...new Set(sec.flatMap((l) => (l.match(/[A-Za-z0-9_\-./]+\.md/g) ?? []).map((t) => path.basename(t))))];
  if (!toks.length) {
    if (sec.some((l) => l.includes("无判例"))) return { cited: 0 };
    throw new Error("闭合校验:注入判例节既无路径也无「无判例」");
  }
  const bad = toks.filter((t) => !allowed.has(t));
  if (bad.length) throw new Error(`闭合校验:判例路径不在(预注入∪本会话检索命中)闭集:${bad.join(", ")}(防真实文件假引用)`);
  return { cited: toks.length };
}

// ── 本会话 structuredContent 登记 + 写前语义门(铁律①)────────────────────────
export class ResultRegistry {
  constructor() { this.byCall = new Map(); }
  register(callId, toolName, sc) { this.byCall.set(callId, { tool: toolName, sc }); }
  get(callId) { return this.byCall.get(callId); }
}

export class ToolHost {
  constructor(round, opts = {}) {
    this.round = round;
    this.registry = new ResultRegistry();
    this.searchHits = new Set();        // search_precedents 命中(闭集成员来源之二)
    this.artifacts = [];                // 本轮落盘工件(host 收口进包脚注)
    this.queueWrites = [];              // 本轮 queue_action 结果(脚注+台账备注)
    this.spent = {};                    // 每轮预算计数
    this.budgets = round === "discover"
      ? { fetch_url: B.fetchPerRound, gh_search: B.ghPerRound, queue_action: B.queuePerRound,
          web_read: B.webReadPerRound, web_search: B.webSearchPerRound, rss_parse: B.rssParsePerRound }
      : { health_snapshot: 2 };
    this.queueFile = opts.queueFile ?? path.join(DOCS_ROOT, "ops/queue.md");
    this.artifactDir = opts.artifactDir ?? path.join(DOCS_ROOT, "ops/artifacts");
    this.tools = round === "health" ? [this.healthSnapshot()] : [
      this.searchPrecedents(), this.readFile(), this.fetchUrl(), this.ghSearch(),
      this.exclusiveProbe(), this.matrixScanSummary(), this.queueAction(),
      this.webRead(), this.webSearch(), this.rssParse(), // 发现通道三件(PR3a;不进 MEASUREMENT_TOOLS)
    ];
  }

  budgetSpend(name) { this.spent[name] = (this.spent[name] ?? 0) + 1; }

  async beforeToolCall({ toolCall, args }) {
    const max = this.budgets[toolCall.name];
    if (max !== undefined && (this.spent[toolCall.name] ?? 0) >= max) {
      return { block: true, reason: `预算超限:${toolCall.name} 每轮上限 ${max} 次已用满;升级人裁区` };
    }
    if (toolCall.name === "queue_action") return this.semanticGate(args);
    return undefined;
  }

  // 写前语义门:host 从本会话 structuredContent 重算谓词,不信 rationale/evidence 复述。
  semanticGate(args) {
    const block = (reason) => ({ block: true, reason });
    if (args?.action === "REJECT" && !PREDICATES.includes(args.predicate)) {
      return block(`REJECT 谓词必须在闭集内:${PREDICATES.join("/")}(缺谓词或不在闭集)`);
    }
    const evs = args?.evidence ?? [];
    if (!evs.length) return block("无 evidence:无实测依据不得入队/拒绝(铁律①;失败信封也不算数)");
    const resolved = [];
    for (const ev of evs) {
      const rec = this.registry.get(ev.call_id);
      if (!rec) return block(`evidence 引用未知调用 ${ev.call_id}:证据只认本会话已完成的测量工具调用,编造即拦`);
      if (!MEASUREMENT_TOOLS.has(rec.tool)) {
        return block(`evidence 引用非测量工具(${rec.tool});测量面 = ${[...MEASUREMENT_TOOLS].join("/")}`);
      }
      if (rec.sc?.ok === false) {
        return block(`evidence ${ev.call_id} 是失败信封(ok:false, code=${rec.sc.code});失败信封禁止入 evidence,降级人裁区(铁律②)`);
      }
      if (!rec.sc || resolveField(rec.sc, ev.field) === undefined) return block(`evidence 字段 ${ev.field} 不在 ${ev.call_id}(${rec.tool})的结构化返回(支持点路径如 results.0.size_kb)`);
      const reg = resolveField(rec.sc, ev.field);
      if (typeof reg !== typeof ev.value || reg !== ev.value) {
        return block(`evidence 值不符:${ev.call_id}.${ev.field} 实测=${JSON.stringify(reg)} 复述=${JSON.stringify(ev.value)}(不信复述,逐字比对)`);
      }
      resolved.push({ ev, rec });
    }
    if (args.action === "ENQUEUE") { // 自动入队条件 = 实测 rate≥0.25 且对照闸过
      const ok = resolved.some(({ rec }) => rec.tool === "exclusive_probe"
        && rec.sc.control_pass === true && typeof rec.sc.exclusive_rate === "number" && rec.sc.exclusive_rate >= 0.25);
      return ok ? undefined : block("ENQUEUE 谓词不成立:无本会话 exclusive_probe 实测 exclusive_rate≥0.25 且对照闸过(自动入队条件)");
    }
    if (args.action === "REJECT") {
      if (args.predicate === "mirror_echo") {
        const probes = resolved.filter(({ rec }) => rec.tool === "exclusive_probe");
        if (!probes.length) return block("overlap-REJECT 无 exclusive_probe 实测一律阻断(判例:无实测不得拒,最多 FLAG)");
        if (!probes.some(({ rec }) => typeof rec.sc.exclusive_rate === "number" && rec.sc.exclusive_rate < 0.25)) {
          return block("overlap-REJECT 与实测矛盾:引用探针排他率均 ≥0.25(高排他非回声,见 threatview/CPS 判例)");
        }
        return undefined;
      }
      if (args.predicate === "sunset_frozen") {
        const fets = resolved.filter(({ rec }) => rec.tool === "fetch_url");
        if (!fets.length) return block("sunset-REJECT 须引用本会话 fetch_url 的 age_days 实测");
        for (const { rec } of fets) {
          if (typeof rec.sc.age_days !== "number") return block("sunset-REJECT:引用中存在无 age_days 的读数(缺 Last-Modified 或不可达);冻结须有数,不可达≠死键");
          if (rec.sc.age_days < FROZEN_DAYS) return block(`sunset-REJECT 与实测矛盾:引用 URL age_days=${rec.sc.age_days} < ${FROZEN_DAYS} 活跃(任一 URL 活跃即不命中)`);
        }
        return undefined;
      }
      if (args.predicate === "zero_asset") {
        const ghs = resolved.filter(({ rec }) => rec.tool === "gh_search");
        if (!ghs.length) return block("zero_asset-REJECT 须引用本会话 gh_search 实测");
        const hit = ghs.some(({ rec }) => rec.sc.kind === "code" && rec.sc.results?.length === 0)
          || ghs.some(({ rec }) => rec.sc.kind === "repos" && rec.sc.results?.length > 0
            && rec.sc.results.every((r) => typeof r.size_kb === "number" && r.size_kb <= B.zeroAssetKb));
        return hit ? undefined : block("zero_asset-REJECT 与实测矛盾:引用 gh_search 无零资产读数(仓体积>${B.zeroAssetKb}KB 或代码检索有命中)");
      }
    }
    return block("action 必须在闭集内:ENQUEUE/REJECT");
  }

  // 工具返回统一走这里:登记 structuredContent(信封也登记——被引时门内识别 ok:false)
  // + 预算计数 + 工件记录。content 前缀 call_id:实测(2026-10-19 discover 重放)模型
  // 看不到运行时生成的调用 id,evidence{call_id} 无从逐字回引——必须把 id 上翻给模型。
  finish(callId, name, structured, contentText, details = {}) {
    this.registry.register(callId, name, structured);
    if (structured?.artifact) this.artifacts.push(structured.artifact);
    if (structured?.artifacts) this.artifacts.push(...structured.artifacts);
    this.budgetSpend(name);
    return { content: [{ type: "text", text: `[call_id=${callId}] ${contentText}` }], details, structuredContent: structured };
  }

  // ── 健康轮唯一工具:零参快照(旗标+计数进上下文,全量落工件;flash 无 search/read)──
  healthSnapshot() {
    return {
      name: "health_snapshot",
      label: "健康快照",
      description: "零参。本地实测:全部源 feed 冻结检测(HEAD/Last-Modified)+ 语义矩阵违例扫描。返回旗标与计数(全量原始读数落工件文件);matrix 失败以嵌套信封呈现,不算轮次失败。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({}),
      outputSchema: Type.Object({
        ok: Type.Boolean(), urls_n: Type.Number(), frozen_n: Type.Number(), near_band_n: Type.Number(),
        unreachable_n: Type.Number(), no_lm_n: Type.Number(), token_required_n: Type.Number(),
        matrix_ok: Type.Boolean(), matrix_exit_code: Type.Number(),
        artifacts: Type.Array(Type.String()),
      }),
      execute: async (callId) => {
        const arts = [];
        try {
          const { stdout: urlOut } = await runLib("extract_feed_urls", [], 120_000);
          const urls = urlOut.split("\n").map((s) => s.trim()).filter(Boolean);
          if (!urls.length) throw Object.assign(new Error("extract_feed_urls 零 URL"), { code: "extract_failed" });
          const { stdout: tsv } = await runLib("feed_freshness", urls, 900_000);
          // TSV 四类读数(P1 T2 修约,spec #152 §2a:401/403 → TOKEN_REQUIRED
          // 需令牌·正常——不算不可达不进 unreachable,与 NO-LM 同待遇只计数;
          // 契约修约判例 2026-10-20:消费方未现=修约非违约)
          const frozen = [], near = [], unreachable = [], noLm = [], tokenReq = [];
          for (const line of tsv.trimEnd().split("\n")) {
            const [url, lm, age] = line.split("\t");
            if (age === "UNREACHABLE") unreachable.push(url);
            else if (age === "TOKEN_REQUIRED") tokenReq.push(url);
            else if (age === "NO-LM") noLm.push(url);
            else {
              const a = +age;
              if (a >= FROZEN_DAYS) frozen.push({ url, last_modified: lm, age_days: a });
              else if (a >= 90) near.push({ url, age_days: a });
            }
          }
          const tsvArt = artifactPath(this.artifactDir, "health-freshness", "tsv");
          fs.writeFileSync(tsvArt, tsv);
          arts.push(tsvArt);
          const matrix = await this.runMatrixScan(arts);
          const st = {
            ok: true, urls_n: urls.length, frozen, frozen_n: frozen.length, near_band: near, near_band_n: near.length,
            unreachable, unreachable_n: unreachable.length, no_lm_n: noLm.length,
            token_required: tokenReq, token_required_n: tokenReq.length,
            matrix_ok: matrix.ok, matrix_exit_code: matrix.exit_code ?? -1,
            matrix: matrix.ok ? matrix : { envelope: matrix }, artifacts: arts,
          };
          const c = [`源 URL ${urls.length};冻结≥${FROZEN_DAYS}天 ${frozen.length};近带(90-179) ${near.length};不可达 ${unreachable.length};NO-LM ${noLm.length};需令牌(401/403) ${tokenReq.length}`,
            ...frozen.map((f) => `- 死键嫌疑·建议复核: ${f.url}(冻结 ${f.age_days} 天;Last-Modified: ${f.last_modified})`),
            ...unreachable.map((u) => `- 不可达·建议复核: ${u}(不可达≠死键)`),
            matrix.ok
              ? [`matrix 读数: exit_code=${matrix.exit_code}(0 干净/1 pending/2 violation) violation=${matrix.counts.violation} pending=${matrix.counts.pending} agreement=${matrix.counts.agreement}`,
                ...Object.entries(matrix.layers).map(([k, v]) => `layer ${k}: ${v.status}${v.notes.length ? `(${v.notes.join(",")})` : ""}`),
                ...matrix.violation_cells.slice(0, 12).map((x) => `violation 格: ${x.cell}${x.note ? `(note: ${x.note})` : ""}`)]
              : [`matrix 测量信封: ${matrix.code}: ${matrix.reason}`].join("\n"),
            `工件: ${arts.join(", ")}`].flat().join("\n");
          return this.finish(callId, "health_snapshot", st, c);
        } catch (e) {
          const env = envelope(e.code ?? "snapshot_failed", e.message);
          return this.finish(callId, "health_snapshot", { ...env, artifacts: arts }, `健康快照失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  }

  // ── discover 工具 ────────────────────────────────────────────────────────
  searchPrecedents() {
    return {
      name: "search_precedents",
      label: "判例检索",
      description: "关键词词法检索(rg)判例库 docs/ops/precedents/(唯一跨轮记忆;无嵌入)。命中≤8 条(铁律⑦);零命中显式返回 none。包内引用判例只许引注入块或本工具命中的文件。",
      annotations: { readOnlyHint: true, idempotentHint: true },
      parameters: Type.Object({
        keywords: Type.Array(Type.String({ minLength: 1, maxLength: 64 }), { minItems: 1, maxItems: 5 }),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), hits: Type.Array(Type.String()), hit_n: Type.Number(),
        truncated: Type.Boolean(), rg_rc: Type.Number(), trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId, p) => {
        // PR #177 单源改造:原生 rg spawn(searchPrecedentsCore),失败面分类信封
        // (判例 2026-10-24-discover-dual-channel-dead:旧路径硬编码 trace rc:0 连失败
        // 路径也带、lib.sh 吞 stderr 2>/dev/null、ENOENT 塞字符串违反 Number 槽)。
        // 成功路径输出与旧 lib.sh 路径逐字节等价(golden 钉死);结构化字段只增不删。
        try {
          const { block, files, trace } = await searchPrecedentsCore(p.keywords);
          const all = files.map((f) => path.basename(f));
          const truncated = all.length > B.hitCap;
          const hits = all.slice(0, B.hitCap);
          hits.forEach((h) => this.searchHits.add(h));
          const st = { ok: true, hits, hit_n: hits.length, truncated, rg_rc: 0, trace };
          return this.finish(callId, "search_precedents", st,
            hits.length ? `${block.trim()}\n(命中 ${all.length} 条${truncated ? `,注入前 ${B.hitCap}(铁律⑦)` : ""})` : block.trim());
        } catch (e) {
          const env = envelope(e.envelope?.code ?? "rg_infra", e.envelope?.reason ?? e.message);
          return this.finish(callId, "search_precedents", { ...env, trace: e.trace ?? { cmd: "(未起跑)", rc: 1 } },
            `判例检索失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  }

  readFile() {
    return {
      name: "read_file",
      label: "白名单读文件",
      description: "只读。白名单=本仓根+docs 根;拒 .env/密钥模式/.venv/backend-data/node_modules。≤50KB/2000 行,支持 pattern 过滤(grep -E 语义)与 offset/limit。",
      annotations: { readOnlyHint: true, idempotentHint: true },
      parameters: Type.Object({
        path: Type.String({ minLength: 1, maxLength: 512 }),
        pattern: Type.Optional(Type.String({ maxLength: 128, description: "正则过滤,仅保留命中行" })),
        offset: Type.Optional(Type.Number({ minimum: 1, maximum: 100000 })),
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 2000 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), path: Type.String(), lines_n: Type.Number(),
        bytes_n: Type.Number(), truncated: Type.Boolean(), content: Type.String(),
      }),
      execute: async (callId, p) => {
        let real;
        try {
          real = checkReadablePath(path.resolve(p.path));
          const stat = fs.statSync(real);
          if (!stat.isFile()) throw Object.assign(new Error("不是普通文件"), { code: "denied" });
          const truncatedBytes = stat.size > B.readBytes;
          const text = fs.readFileSync(real, "utf8").slice(0, B.readBytes);
          let lines = text.split("\n");
          if (p.pattern) {
            let re; try { re = new RegExp(p.pattern); } catch { throw Object.assign(new Error("pattern 非法正则"), { code: "bad_pattern" }); }
            lines = lines.filter((l) => re.test(l));
          }
          const off = (p.offset ?? 1) - 1;
          const lim = p.limit ?? B.readLines;
          const sliced = lines.slice(off, off + lim);
          const st = {
            ok: true, path: real, lines_n: sliced.length, bytes_n: stat.size,
            truncated: truncatedBytes || off + lim < lines.length, content: sliced.join("\n"),
          };
          return this.finish(callId, "read_file", st, sliced.join("\n") || "(空)");
        } catch (e) {
          const env = envelope(e.code === "denied" || /白名单|禁读|密钥/.test(e.message) ? "denied" : (e.code ?? "io_error"), e.message);
          return this.finish(callId, "read_file", { ...env, path: p.path }, `读文件失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  }

  fetchUrl() {
    return {
      name: "fetch_url",
      label: "URL 探测",
      description: "只读 GET/HEAD。逐跳 SSRF 防护(私网/环回拒);512KB/15s/每轮≤20 次。返回 status/last_modified/age_days(GET 附样本≤5 行)。age_days 是 sunset 谓词的唯一数据源;HTTP≥400/超时=失败信封(不可达≠死键)。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        url: Type.String({ pattern: "^https?://", maxLength: 500 }),
        method: Type.Optional(Type.Union([Type.Literal("GET"), Type.Literal("HEAD")], { description: "默认 HEAD;GET 取样本" })),
        max_bytes: Type.Optional(Type.Number({ minimum: 256, maximum: 524288 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), url: Type.String(), final_url: Type.String(), status: Type.Number(),
        last_modified: Type.Union([Type.String(), Type.Null()]), age_days: Type.Union([Type.Number(), Type.Null()]),
        bytes: Type.Number(), sample: Type.Array(Type.String()),
      }),
      execute: async (callId, p) => {
        const method = p.method ?? "HEAD";
        try {
          const res = await safeFetch(p.url, { method, maxBytes: p.max_bytes ?? B.fetchBytes, timeoutMs: B.fetchTimeoutMs });
          const lm = res.headers["last-modified"] ?? null;
          const age = lm ? Math.max(0, Math.floor((Date.now() - Date.parse(lm)) / 86_400_000)) : null;
          const sample = method === "GET" && res.body
            ? res.body.toString("utf8").split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 5).map((l) => l.slice(0, 200)) : [];
          const st = {
            ok: true, url: p.url, final_url: res.finalUrl, status: res.status, last_modified: lm,
            age_days: age, bytes: res.bytes, sample, trace: { method, status: res.status },
          };
          const c = `${method} ${p.url} → ${res.status};Last-Modified: ${lm ?? "(无)"};age_days=${age ?? "null"};bytes=${res.bytes}`
            + (sample.length ? `\n样本:\n${sample.join("\n")}` : "");
          return this.finish(callId, "fetch_url", st, c);
        } catch (e) {
          const env = envelope(e.code ?? "network", e.message);
          return this.finish(callId, "fetch_url", { ...env, url: p.url, method }, `URL 探测失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  }

  ghSearch() {
    const FIELDS = {
      repos: ["fullName", "description", "pushedAt", "updatedAt", "stargazersCount", "language", "isArchived", "size", "url"],
      code: ["path", "repository"],
      commits: ["commit", "repository"],
    };
    const project = (kind, rows) => rows.map((r) => kind === "repos" ? ({
      full_name: r.fullName, description: String(r.description ?? "").slice(0, 120),
      pushed_at: r.pushedAt, updated_at: r.updatedAt, stars: r.stargazersCount,
      language: r.language, archived: r.isArchived, size_kb: r.size, url: r.url,
    }) : kind === "code" ? ({ repo: r.repository?.nameWithOwner, path: r.path })
      : ({ repo: r.repository?.nameWithOwner, sha: String(r.sha ?? "").slice(0, 12), date: r.commit?.committer?.date ?? r.commit?.author?.date ?? null, message: String(r.commit?.message ?? "").split("\n")[0].slice(0, 120) }));
    return {
      name: "gh_search",
      label: "GitHub 检索",
      description: "只读 gh search(子命令白名单仅 search;禁裸 stdout,固定字段投影)。kind=repos(候选仓元数据/size_kb)/code(仓内代码命中;零命中=零资产信号)/commits(出版方活性;注意 commits 检索必须带文本词,纯 qualifier 会报错)。每轮≤15 次。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        query: Type.String({ minLength: 1, maxLength: 256 }),
        kind: Type.Union([Type.Literal("repos"), Type.Literal("code"), Type.Literal("commits")]),
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 30 })),
        // page 已移除(通道复验轮修复 2026-10-24):gh 2.103.x search 无 --page 旗(repos/code
        // 实测均拒 unknown flag)——旧 argv 恒拼 --page 故 gh_search 100% 必死,仅因前置通道先死从未暴露。
        // 分页需求由 limit ≤30(预算面)承担。
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), kind: Type.String(), query: Type.String(), total: Type.Number(),
        results: Type.Array(Type.Object({})), trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId, p) => {
        const argv = ["search", p.kind, p.query, "--json", FIELDS[p.kind].join(","),
          "--limit", String(p.limit ?? 10)];
        const cmd = `gh ${argv.map((a) => /\s/.test(a) ? `"${a}"` : a).join(" ")}`;
        try {
          const { stdout } = await execFileP("gh", argv, { timeout: B.ghTimeoutMs, maxBuffer: 8 * 1024 * 1024 });
          const rows = JSON.parse(stdout);
          const results = project(p.kind, Array.isArray(rows) ? rows : []);
          const st = { ok: true, kind: p.kind, query: p.query, total: results.length, results, trace: { cmd, rc: 0 } };
          const c = `${p.kind} "${p.query}" → ${results.length} 条(字段投影)\n` +
            results.slice(0, 30).map((r) => `- ${JSON.stringify(r)}`).join("\n");
          return this.finish(callId, "gh_search", st, c);
        } catch (e) {
          // PR #177 分类落地(判例 2026-10-24-discover-dual-channel-dead):容器无 gh/
          // 凭证缺失/限流/暂态分四码信封,每码带下一步合法动作;trace.rc 恒 Number
          // (旧 e.code ?? 1 在 ENOENT 时塞字符串违反 outputSchema Number 槽);原 gh_error
          // 兑底兼容保留;成功路径零改动。
          const cls = classifyChannelError(e, "gh");
          const env = envelope(cls.code, cls.reason);
          return this.finish(callId, "gh_search", { ...env, kind: p.kind, query: p.query, trace: { cmd, rc: cls.rc } },
            `gh 检索失败信封:${env.code}:${env.reason}`);
        }
      },
    };
  }

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
  }

  webSearch() {
    return {
      name: "web_search",
      label: "通用搜索",
      description: "只读。GET s.jina.ai/<query 百分号编码> 取 SERP(通用搜索补缺)。需 Bearer JINA_API_KEY(call-time 读 env;缺配=channel_auth、欠费 402=quota——均部署/账户面,人裁区注明);num≤8 缺省 5(本地截断+truncated);每轮≤6 次。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        query: Type.String({ minLength: 1, maxLength: 256 }),
        num: Type.Optional(Type.Number({ minimum: 1, maximum: 8 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), query: Type.String(), n: Type.Number(), truncated: Type.Boolean(),
        results: Type.Array(Type.Object({ url: Type.String(), title: Type.String(), snippet: Type.String() })),
        trace: Type.Object({ channel: Type.String(), status: Type.Number() }),
      }),
      execute: async (callId, p) => {
        const num = p.num ?? 5;
        const key = (process.env.JINA_API_KEY ?? "").trim(); // call-time 读(agent-config tool_keys.jina→_round_env 注入;配置优先改完即生效)
        try {
          if (!key) throw Object.assign(new Error(
            "JINA_API_KEY 未配置(agent-config tool_keys.jina;见 deploy/ops-cron.md):s.jina.ai 2026 起强制 Bearer key——缺配属部署面;余额不足属 quota(充值即活)"), { code: "channel_auth" });
          const res = await safeFetch(`https://s.jina.ai/${encodeURIComponent(p.query)}?num=${num}`, {
            method: "GET", maxBytes: B.fetchBytes, timeoutMs: B.webSearchTimeoutMs,
            headers: { authorization: `Bearer ${key}` }, // 恒带 key(r 端相反:恒不带——两行为勿写反,2026-10-24 实测)
            allowStatus: true, // 402/429→quota、401/403→channel_auth(欠费信封诚实报)
          });
          const text = res.body.toString("utf8");
          if (res.status >= 400) {
            const cls = classifyWebStatus(res.status, text, "web_search");
            return this.finish(callId, "web_search",
              { ok: false, code: cls.code, reason: cls.reason, query: p.query, trace: { channel: "s.jina.ai", status: res.status } },
              `web_search 失败信封:${cls.code}: ${cls.reason}`);
          }
          const { results, truncated } = parseSerp(text, { num });
          const st = { ok: true, query: p.query, n: results.length, truncated, results, trace: { channel: "s.jina.ai", status: res.status } };
          const c = `搜索 "${p.query}" → ${results.length} 条${truncated ? "(服务端多回,本地截断)" : ""}\n`
            + results.map((r) => `- ${r.title || r.url}\n  ${r.url}${r.snippet ? `\n  ${r.snippet}` : ""}`).join("\n");
          return this.finish(callId, "web_search", st, c);
        } catch (e) {
          const env = envelope(e.code ?? "network", e.message);
          return this.finish(callId, "web_search", { ...env, query: p.query, trace: { channel: "s.jina.ai", status: 0 } },
            `web_search 失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  }

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
  }

  exclusiveProbe() {
    return {
      name: "exclusive_probe",
      label: "排他率探针",
      description: "候选 feed 实测排他率(唯一硬门数字生产线;阳性对照闸 20 中 ≥18)。仅收 URL(禁文件路径);内部下载(SSRF 逐跳,≤256MB)→ 键量>1M 走体量信封(bitwire OOM 判例,人裁)→ 子进程跑 python -m ipdb._eval --exclusive --json(seed 缺省 20261018)。串行执行;数据面缺失=结构化信封。ENQUEUE 自动入队条件=本工具 exclusive_rate≥0.25 且 control_pass。",
      annotations: { readOnlyHint: true, openWorldHint: true },
      parameters: Type.Object({
        url: Type.String({ pattern: "^https?://", maxLength: 500 }),
        seed: Type.Optional(Type.Number({ minimum: 0, maximum: 99999999 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), url: Type.String(), seed: Type.Number(),
        exclusive_rate: Type.Number(), exclusive: Type.Number(), sampled: Type.Number(),
        feed_unique_keys: Type.Number(), control_pass: Type.Boolean(),
        covering_sources: Type.Array(Type.Object({})), artifact: Type.String(),
        trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      // 串行一层(评审 P1 修正):SDK 每工具执行模式 pi-agent-core 1.3.0 AgentTool.
      // executionMode(agent-loop executeToolCalls:批次含 sequential 工具即整批逐个执行,
      // 防 SDK 缺省 parallel 下并发 ≤256MB 下载 + _eval CLI/LMDB 读压)。
      executionMode: "sequential",
      execute: async (callId, p) => this.probeQueue(this.runExclusiveProbe(callId, p)),
    };
  }

  // 串行二层(实例级 promise 链 this.probeChain,非模块级;只序落定,起跑由 execute 立即发生)
  // ——并发防护以一层 executionMode 为准,本链兜底 SDK 批层之外的调用路径(LMDB 读压)。
  probeQueue(task) {
    const run = this.probeChain ?? Promise.resolve();
    this.probeChain = run.then(() => task, () => task);
    return this.probeChain;
  }

  async runExclusiveProbe(callId, p) {
    const seed = p.seed ?? 20261018;
    const tmp = path.join(os.tmpdir(), `ops-probe-${process.pid}-${Date.now()}.txt`);
    try {
      const dl = await safeFetch(p.url, { method: "GET", maxBytes: B.probeBytes, timeoutMs: B.probeDlTimeoutMs });
      const text = dl.body.toString("utf8");
      const keys = countFeedKeys(text);
      if (keys === 0) return this.finish(callId, "exclusive_probe",
        envelope("bad_feed", `feed 提取零个 IPv4 键:${p.url}(空分母不冒充 0)`),
        `探针失败信封:bad_feed: feed 零键`);
      if (keys > B.probeMaxKeys) return this.finish(callId, "exclusive_probe",
        envelope("key_cap", `feed 键量 ${keys} > 上限 ${B.probeMaxKeys}(bitwire 4.58M OOM 判例:过线体量人裁)`),
        `探针失败信封:key_cap: 键量 ${keys} 超限,升级人裁区`);
      fs.writeFileSync(tmp, text);
      const cmd = `cd backend && IP_RADAR_DATA_DIR=${DATA_DIR} ${EVAL_PY} -m ipdb._eval --exclusive <tmp> --json --seed ${seed}`;
      const { stdout, stderr } = await execFileP(EVAL_PY,
        ["-m", "ipdb._eval", "--exclusive", tmp, "--json", "--seed", String(seed)],
        { cwd: path.join(ROOT, "backend"), env: { ...process.env, IP_RADAR_DATA_DIR: DATA_DIR },
          timeout: B.probeCliTimeoutMs, maxBuffer: 32 * 1024 * 1024 });
      const res = JSON.parse(stdout);
      const controlPass = res.control.hits >= res.control.required;
      const art = artifactPath(this.artifactDir, `probe-${new URL(p.url).hostname.replace(/\W+/g, "-")}`, "json");
      fs.writeFileSync(art, JSON.stringify({ trace: { cmd, rc: 0 }, result: res }, null, 1));
      const st = {
        ok: true, url: p.url, seed: res.seed, feed_unique_keys: res.feed_unique_keys,
        sampled: res.sampled, exclusive: res.exclusive, covered: res.covered,
        exclusive_rate: res.exclusive_rate, control: res.control, control_pass: controlPass,
        covering_sources: Object.entries(res.coverage_sources).slice(0, 8).map(([source, n]) => ({ source, n })),
        artifact: art, trace: { cmd, rc: 0 },
      };
      const c = `排他率实测:${res.exclusive}/${res.sampled} = ${(res.exclusive_rate * 100).toFixed(1)}%(seed=${res.seed},feed uniq=${res.feed_unique_keys});`
        + `对照闸 binarydefense ${res.control.hits}/${res.control.n}(需≥${res.control.required},${controlPass ? "过" : "未过"});`
        + `覆盖源:${Object.entries(res.coverage_sources).slice(0, 8).map(([s, n]) => `${s}:${n}`).join(",")};工件:${art}`;
      return this.finish(callId, "exclusive_probe", st, c);
    } catch (e) {
      let env;
      try { // CLI --json 失败信封(control_failed/bad_feed/internal)解析优先
        const j = JSON.parse(String(e.stdout ?? ""));
        env = envelope(j.error?.code ?? "probe_failed", j.error?.message ?? String(e.message));
      } catch { env = envelope(e.code === "ENOENT" ? "data_plane_missing" : "probe_failed", String(e.stderr ?? e.message).slice(0, 300)); }
      return this.finish(callId, "exclusive_probe", { ...env, url: p.url, seed }, `探针失败信封:${env.code}: ${env.reason}`);
    } finally {
      try { fs.rmSync(tmp, { force: true }); } catch { /* 轮末清理兜底 */ }
    }
  }

  async runMatrixScan(arts) { // 单源薄包装(P1,#163):真路径在 matrixScanCli,legacy 返回形状零改动
    const r = await matrixScanCli();
    if (r.ok) return this.matrixFromResult(r.d, r.cmd, arts, r.rc);
    return r.trace ? { ...r.env, trace: r.trace } : r.env;
  }

  matrixFromResult(d, cmd, arts, rc) {
    const art = artifactPath(this.artifactDir, "matrix-scan", "json");
    fs.writeFileSync(art, matrixArtifactText(d));
    arts?.push(art);
    return {
      ok: true, exit_code: d.exit_code, counts: d.counts,
      layers: Object.fromEntries(Object.entries(d.layers).map(([k, v]) => [k, { status: v.status, notes: v.notes ?? [] }])),
      violation_cells: (d.buckets?.violation ?? []).map((c) => ({ cell: c.cell, note: c.note ?? null })),
      artifact: art, trace: { cmd, rc },
    };
  }

  matrixScanSummary() {
    return {
      name: "matrix_scan_summary",
      label: "语义矩阵扫描",
      description: "零参。语义契约矩阵现状扫描(四层取样):exit_code 0/1/2=干净/pending/violation + 逐格违例与层状态。数据面缺失=结构化信封不裸栈。",
      annotations: { readOnlyHint: true, idempotentHint: true },
      parameters: Type.Object({}),
      outputSchema: Type.Object({
        ok: Type.Boolean(), exit_code: Type.Number(), violation_n: Type.Number(),
        counts: Type.Object({}), layers: Type.Object({}), trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId) => {
        const r = await this.runMatrixScan();
        if (!r.ok) return this.finish(callId, "matrix_scan_summary", r, `matrix 扫描失败信封:${r.code}: ${r.reason}`);
        this.artifacts.push(r.artifact);
        const c = `exit_code=${r.exit_code}(0 干净/1 pending/2 violation) violation=${r.counts.violation} pending=${r.counts.pending} agreement=${r.counts.agreement}\n`
          + Object.entries(r.layers).map(([k, v]) => `layer ${k}: ${v.status}${v.notes.length ? `(${v.notes.join(",")})` : ""}`).join("\n")
          + (r.violation_cells.length ? `\n违例格:${r.violation_cells.map((x) => x.cell).join(",")}` : "");
        return this.finish(callId, "matrix_scan_summary", { ...r, violation_n: r.counts.violation }, c);
      },
    };
  }

  queueAction() {
    return {
      name: "queue_action",
      label: "动作入队(唯一写)",
      description: "唯一写工具:把 ENQUEUE(自动入队,须本会话 exclusive_probe 实测 rate≥0.25 且对照闸过)/REJECT(谓词闭集 sunset_frozen|mirror_echo|zero_asset,写前语义门从 structuredContent 重算谓词)追加到 docs/ops/queue.md。append-only、幂等去重、恒可否决(veto_cmd);rationale 只落工件包不进行列。evidence[]={call_id,field,value} 必须逐字对应本会话测量工具的结构化返回。",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      parameters: Type.Object({
        source: Type.String({ pattern: "^[a-z0-9_]{1,32}$" }),
        action: Type.Union([Type.Literal("ENQUEUE"), Type.Literal("REJECT")]),
        predicate: Type.Optional(Type.Union([Type.Literal("sunset_frozen"), Type.Literal("mirror_echo"), Type.Literal("zero_asset")])),
        rationale: Type.String({ minLength: 1, maxLength: 2000 }),
        evidence: Type.Array(Type.Object({
          call_id: Type.String({ minLength: 1 }),
          field: Type.String({ minLength: 1 }),
          value: Type.Union([Type.String(), Type.Number(), Type.Boolean(), Type.Null()]),
        }), { minItems: 1, maxItems: 16 }),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), appended: Type.Boolean(), dedup: Type.Boolean(),
        action: Type.String(), source: Type.String(), vetoable: Type.Boolean(), veto_cmd: Type.String(),
      }),
      execute: async (callId, p) => {
        // 预算计数走真实路径:queue_action 不经 finish()(非测量工具,不进登记表),
        // 若不在此计数 spent 永不增长、10/轮上限永不触发(评审 Important-1,2026-10-19)
        this.budgetSpend("queue_action");
        // 幂等去重:同 action+source 已在队列 → 返回既有事实,不双写
        let existing = "";
        try { existing = fs.readFileSync(this.queueFile, "utf8"); } catch { /* 首建 */ }
        const dedupRe = new RegExp(`\\| \\d{4}-\\d{2}-\\d{2} \\| [^|]+ \\| ${p.action} \\| ${p.source} \\|`);
        const dedup = dedupRe.test(existing);
        let lineN = existing ? existing.trimEnd().split("\n").length : 0;
        const rel = path.relative(ROOT, this.queueFile);
        const vetoCmd = `sed -i '/| ${p.action} | ${p.source} |/d' ${rel}`;
        if (!dedup) {
          if (!existing) {
            fs.mkdirSync(path.dirname(this.queueFile), { recursive: true });
            fs.writeFileSync(this.queueFile,
              "# 源生命周期动作队列(queue_action 唯一写口;行由 host 模板渲染,rationale 只落工件)\n\n"
              + "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n|---|---|---|---|---|---|---|\n");
            lineN = 4;
          }
          const ev = p.evidence.map((e) => `${e.call_id}:${e.field}=${JSON.stringify(e.value)}`).join(";");
          const row = `| ${new Date().toISOString().slice(0, 10)} | ${this.round} | ${p.action} | ${p.source} | ${p.predicate ?? "—"} | ${ev} | 是(否决=删除本行) |`;
          fs.appendFileSync(this.queueFile, `${row}\n`);
          lineN += 1;
          const rpath = artifactPath(this.artifactDir, "queue-rationale", "md");
          fs.appendFileSync(rpath, `## ${ts()} ${p.action} ${p.source}\n- predicate: ${p.predicate ?? "(无)"}\n- evidence: ${JSON.stringify(p.evidence)}\n- rationale(模型原话,仅人裁阅读,不进队列行):\n\n${p.rationale}\n\n`);
          this.artifacts.push(rpath);
        }
        const st = {
          ok: true, appended: !dedup, dedup, action: p.action, source: p.source,
          predicate: p.predicate ?? null, vetoable: true, veto_cmd: vetoCmd, queue_file: rel,
        };
        this.queueWrites.push(st);
        const c = `${p.action} ${p.source}${dedup ? "(已在队列,幂等去重,未双写)" : " 已入队"};恒可否决:veto_cmd = \`${vetoCmd}\`;rationale 已落工件(包脚注)。`;
        return { content: [{ type: "text", text: c }], details: {}, structuredContent: st };
      },
    };
  }
}
