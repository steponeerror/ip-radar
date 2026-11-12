// tasks/add-round.mjs — 加源轮 defineTask 化(票 #332 P1;设计真源 docs/superpowers/
// specs/2026-11-11-add-round-reimplementation-bench-design.md §架构 + §相位表 + 定案 2/7/8/9)。
// 运营 agent 第三轮型 add:把已人裁 APPROVE 的候选卡实现进沙箱 worktree 的源代码。
//
// ── 纪律头注(仿 tasks/discover-round.mjs,零复制沿用既有执法面)──
//   一轮 = 自有 conversation(run-add.mjs 创建,agent 面 = add/system.md 提示词 +
//   ADD_TOOLS_EXTENSION 编码工具闭集;任务 ownership={kind:"conversation"} 绑进该会话)。
//   requestId 幂等:round-<roundId>-<phase>,attempt ≥2(结算坏/空文本/形状坏重发)=
//   -a<N> 后缀;崩溃发生在提交后结算前 → 同 key 重放 = pi-durable 恰好一次语义。
//   预算执法(budget-guard 双点,OPS_ADD_* 独立旋钮族):每相位头 stepBoundary(③墙钟);
//   模型相位每次 attempt 提交前 preModelCall(①③)+ 结算后 postModelCall(②④,usage 取
//   会话 UsageDoc 活和)。模型调用计数 = 会话累计 assistant 模型回合数(IMPLEMENT 是
//   工具循环大步,一次 submit 多回合——逐回合计数,attempt 即调用的逐回合推广)。
//   checkpoint 纪律:相位边界提交(modelCalls/usage/dossier/card/sandboxFace);凭证红线
//   env 不入 checkpoint(过程现读);input 只带路径/旋钮/只读配置(python 解释器路径非凭证)。
//
// ── 六相位(§相位表定稿名)──
//   VERIFY    脚本零模型:卡消费(只读 queue.md,只认 status=approved=有 APPROVE 行的
//             PROPOSE 卡;轮无写口改卡状态)+ roster diff(python -m ipdb._registry
//             --roster 对 download_host/子列,同出版方=STOP)+ 鲜活度门(数据内时间戳
//             ≤30d;file-mtime/URL 响应不算;真实面 4 组合探活 GET/HEAD×UA)。faux 面
//             读 fixtures/add/verify.json 罐装读数(与发现轮 MEASURE fixtures 缝同律)。
//   DOSSIER   脚本+模型:薄卡补交接单(实抓样本 3-5 行/格式/auth/cadence/字段路由草案),
//             终答=单条 JSON;形状坏重试 ≤1 再败=终态 model_face。
//             bench 形态(input.bench=true)跳过本相位——交接单预填在 input.dossier
//             (定案 2 开关位接口,P2b 基准接线消费;形与非 bench 同门校验)。
//   IMPLEMENT 模型大步:TDD 硬序(先写 backend/tests/sources/ 测试亲眼红,再写
//             backend/ipdb/_sources/ 源转绿;分类映射落 _classification.py;元数据类属性
//             在源文件内声明)——经编码工具(write_file/run_bash/run_pytest)真执行;
//             G_IMPLEMENT 机检:首跑红末跑绿(转录 run_pytest 种子序)+ 双文件沙箱在场
//             + stem 一致。
//   GATE      脚本零模型:沙箱内命令集(真实面=逐源测试+tests/source_infra/+目录源审计
//             三连;跑法=主检出 venv 解释器绝对路径+cwd=沙箱 backend/,定案 8;faux 面=
//             fixtures/add/gate.json 罐装清单,命令真执行零网络)。任一 rc≠0=门红终态。
//   REPORT    脚本:沙箱 git 提交+分支指针(rev-parse);轮产出=沙箱分支,永不自并入
//             master(定案 8/9 停止点;人裁并入)。
//   CLOSE     bookend:主检出 sandbox_assert 防线 + 台账行(pipeline-add 标签,lib.sh
//             同锁域)+ 09-budget.json(OPS_ADD_* env 面)+ 信封(stdout 末行,ENVELOPE.md)。
//
// ── 错误码 ── 复用 ENVELOPE.md 闭集(bad_round/model_face/empty_text/infra/
//   budget_exceeded/wall_clock_exceeded/sandbox_violation/ledger_failed)+ add 域词
//   (card_missing/card_not_approved/duplicate_publisher/freshness_gate/gate_failed)。
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { defineTask, UsageDoc } from "@earendil-works/pi-durable";
import { elapsedWallS } from "../budget.mjs"; // 零复制 re-export seam(旧管线纯函数单一真源)
import { preModelCall, postModelCall, stepBoundary } from "./budget-guard.mjs"; // 执法面(文案/界值零漂移)
import * as gates from "../../agent/pipeline/gates.mjs"; // 零复制:gates.json 留痕件(appendGate 通用面)
import { addPromptPath } from "../run-add.mjs"; // 提示词路径(run-add 定义面;函数声明循环安全:运行时互引,discover 同律)
import { ensureAddHost } from "../tools/add-tools.mjs"; // 轮级编码宿主(工具面种子登记)
import { DUMP_META_SCRIPT } from "../bench/add-domain/gen-universe.mjs"; // roster 侧 url 证据面判据单源(#337 F4;gen-exam-cards 同源消费)
import { mainCheckoutRoot } from "../bench/leak-check.mjs"; // #340 缓存文件主检出锚单源(git-common-dir 推导,spend.json #337 同算式零复制)

const execFileP = promisify(execFileCb);
const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);

export const ADD_TASK_NAME = "ops.add-round";
export const ADD_PHASES = Object.freeze(["verify", "dossier", "implement", "gate", "report", "close"]);
const STAGE_OF = Object.freeze({ verify: "VERIFY", dossier: "DOSSIER", implement: "IMPLEMENT", gate: "GATE", report: "REPORT", close: "CLOSE" });
const GATE_OF = Object.freeze({ verify: "G_VERIFY", dossier: "G_DOSSIER", implement: "G_IMPLEMENT", gate: "G_GATE", report: "G_REPORT", close: "G_CLOSE" });
// 工件名(加源轮自有前缀 a1-a5;09-budget.json 沿 CLOSE 预算快照名)
const ART = Object.freeze({
  VERIFY: "a1-verify.json",
  DOSSIER: "a2-dossier.json", DOSSIER_T: "a2-dossier-transcript.jsonl",
  IMPL: "a3-implement.json", IMPL_T: "a3-implement-transcript.jsonl",
  GATE: "a4-gate.json", REPORT: "a5-report.json", BUDGET: "09-budget.json",
});
// 台账行标签(#332 P1:旧 steps.mjs LEDGER_TAGS 属主零改动红线,add 域词在此单源;
// 消费面 monthSpendOfLedgerText 只读 cost 列,标签词不影响解析)
const ADD_LEDGER_TAG = "pipeline-add";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../.."); // ops/agent-v2/tasks → 仓根
const LIBSH = path.join(REPO_ROOT, "ops", "agent", "lib.sh"); // 台账/sandbox_assert(RETRO 同款 sh 面)
const sh = (fn, args = [], timeoutMs = 600_000, env = process.env) => execFileP("bash",
  ["-c", `. "$0"; ${fn} "$@"`, LIBSH, ...args], { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...env } });

// ── 纯函数面(导出=测试单源面)──────────────────────────────────────────

// 描述名 → 源文件名 stem(house style [a-z0-9_];实现契约:测试/源文件 stem 钉死同值)
export const slugify = (name) =>
  String(name).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "source";

// queue.md 行解析:冻结行形(| 日期 | 轮次 | action | source | predicate | evidence | vetoable |);
// evidence 值面是 JSON 串——引号内的 ";" 不裂(状态机切分),值 JSON.parse 兜底原样。
export function parseQueueRows(text) {
  const rows = [];
  for (const line of String(text ?? "").split("\n")) {
    if (!/^\|\s*\d{4}-\d{2}-\d{2}\s*\|/.test(line)) continue;
    const cells = line.split("|").map((c) => c.trim());
    if (cells.length < 8) continue;
    rows.push({ date: cells[1], round: cells[2], action: cells[3], source: cells[4], predicate: cells[5], evidence: parseEvidenceCell(cells[6]) });
  }
  return rows;
}
function parseEvidenceCell(cell) {
  const map = new Map();
  if (!cell || cell === "—") return map;
  const parts = [];
  let buf = "", inStr = false, esc = false;
  for (const ch of cell) {
    if (esc) { buf += ch; esc = false; continue; }
    if (ch === "\\") { buf += ch; esc = true; continue; }
    if (ch === '"') { buf += ch; inStr = !inStr; continue; }
    if (ch === ";" && !inStr) { parts.push(buf); buf = ""; continue; }
    buf += ch;
  }
  if (buf.trim()) parts.push(buf);
  for (const p of parts) {
    const i = p.indexOf("=");
    if (i <= 0) continue;
    const key = p.slice(0, i).trim();
    const raw = p.slice(i + 1);
    let val = raw;
    try { val = JSON.parse(raw); } catch { /* 裸数/bool 兜底原样(渲染面恒 JSON 串,防御读) */ }
    map.set(key, val);
  }
  return map;
}

// roster 撞卡(add-intel-source 技能 Phase 1 律:候选域名对 download_host+子列;
// dataplane 前例 2026-09-05)。roster 行形 = _registry.roster():name | cat | host | fields [| 子列]。
// www. 前缀去后再比(#334 消化件①:www.dataplane.org vs dataplane.org 逐字相等会漏拦
// 同出版方;双侧剥前导 www.,子列信号面同理不受伤——子列本就非域名形);
// 命中回报 roster 原文形(host 小写化)。
// github 家族判据(#337 F4,推翻 #334 时代「共享分发域互撞=已知局限」段):家族三 host
// 是发布方中立分发面,host 级比对会把同主机异发布方误当重复源(发现轮 gate 2026-10-10
// 判例)——家族内改按 URL 路径键比对(路径段去空小写 join,= owner/repo+剩余路径):
// 同发布方同文件才红;同仓不同文件=绿(同发布方不同清单,sw_scanners/sw_threats 同仓
// 判例,#337 补充规格);家族成员 host 不区分(github.com ↔ raw.githubusercontent.com
// 是同一发布内容)。roster 侧 url 证据 = rosterUrls Map(name→urls,真面经 DUMP_META_SCRIPT
// 机械 dump);家族行无 url 证据=保守 host 级红(fail-closed,不带 url 面装绿)。
export const GITHUB_FAMILY_HOSTS = new Set(["github.com", "raw.githubusercontent.com", "codeload.github.com"]);

// 家族 host 判定(#342 A2 起 probeLiveness 第三基排他也消费):www 前缀剥除后对
// GITHUB_FAMILY_HOSTS 查;返回剥除后 host(在家族内)或 null。githubCommitsQuery 同消费
// (单源;原先两函数各自手抄剥除式)。
export function githubFamilyHost(url) {
  let u;
  try { u = new URL(String(url ?? "")); } catch { return null; }
  const host = u.hostname.toLowerCase();
  const stripped = host.startsWith("www.") ? host.slice(4) : host;
  return GITHUB_FAMILY_HOSTS.has(stripped) ? stripped : null;
}

// 家族路径键:URL 的 pathname 段去空小写 join("/");非家族 URL/裸 host/解析失败 → null。
function githubPathKey(url) {
  let u;
  try { u = new URL(String(url ?? "")); } catch { return null; }
  const host = u.hostname.toLowerCase();
  const stripped = host.startsWith("www.") ? host.slice(4) : host;
  if (!GITHUB_FAMILY_HOSTS.has(stripped)) return null;
  const segs = u.pathname.split("/").filter(Boolean).map((s) => s.toLowerCase());
  return segs.length ? segs.join("/") : null;
}

// github 家族 commits API 面参数(#339 ① 活性证据回退的查询构造):owner/repo 取路径
// 前两段(保留原大小写——API 接受任意大小写 owner/repo);文件路径剥 ref 段(raw 形
// ref=第 3 段;github.com 形 blob|raw|tree 前缀后接 ref;codeload 归档无文件粒度;
// releases 两形(#342 B)releases/latest/download/<file> 与 releases/download/<tag>/<file>
// 都剥前三段取文件名——发布资产的发布粒度=文件,回退查询 path=文件名与 raw.* 三段形
// 同律;仓根/归档=path 空 → repo 级最新 commit)。家族判定复用 #337 F4 常量
// GITHUB_FAMILY_HOSTS;非家族/缺 owner-repo 对/非 URL → null(不回退,fail-closed)。
export function githubCommitsQuery(url) {
  let u;
  try { u = new URL(String(url ?? "")); } catch { return null; }
  const fam = githubFamilyHost(url);
  if (!fam) return null;
  const segs = u.pathname.split("/").filter(Boolean);
  if (segs.length < 2) return null;
  const [owner, repo, ...rest] = segs;
  let fileSegs = rest;
  if (fam === "raw.githubusercontent.com") fileSegs = rest.slice(1); // /<owner>/<repo>/<ref>/<路径…>
  else if (fam === "codeload.github.com") fileSegs = []; // zip|tar.gz/<ref>:整仓归档
  else if (["blob", "raw", "tree"].includes(rest[0])) fileSegs = rest.slice(2); // /blob/<ref>/<路径…>
  // releases 两形(#342 B):两形都剥前三段(latest/download 走 release 与 download/<tag>
  // 差在第三段是 download 还是 tag,剩余都是文件路径)
  else if (rest[0] === "releases" && (rest[1] === "download" || (rest[1] === "latest" && rest[2] === "download"))) fileSegs = rest.slice(3);
  const q = new URLSearchParams({ per_page: "1" });
  if (fileSegs.length) q.set("path", fileSegs.join("/"));
  return { api: `https://api.github.com/repos/${owner}/${repo}/commits?${q}`, path: fileSegs.join("/") };
}

// ── #340 github commits API 限流记忆化(优化环几十上百次 trial 面)──
// api.github.com 匿名配额 60 req/h/按 IP(#340 票面):每轮 VERIFY 12 题必发回退调用,
// 优化环确定撞 403→fail-closed none→G_VERIFY 系统性只红 github 家族题。两层记忆化:
// 进程内 Map(键=commits API URL,owner/repo+path 的确定性函数)→ 跨进程文件缓存
// (主检出锚 dev/add-bench/github-freshness-cache.json;worktree 完删树不灭缓存,
// spend.json #337 同锚点)。Conditional GET(#340 ②):过期条目带 etag→If-None-Match,
// 304 不占配额且视为新鲜证据(cached_at 更新为再验证时刻;304 无 body,
// committer_date 沿缓存)。命中=basis github_commit 带 cached_at 面(取得时刻入档,
// age 用取得时刻算——记忆化答案原样回放,缺省 6h TTL=与 now 口径的误差上界);文件
// 缓存坏=弃=未命中重探,不红不阻跑(cache_note 留痕);失败面不落缓存(fail-closed
// 答案不记忆化,etag 条目留存给下轮再验证)。出处:「304 不占配额」=GitHub REST API
// Best practices(Docs: Best practices for using the REST API → Conditional requests,
// docs.github.com——未命中配额的 conditional request 返回 304 不计入 rate limit)。
export const GITHUB_FRESHNESS_MEM = new Map(); // 进程内一层:commits API URL → {etag, committer_date, cached_at}
const GITHUB_FRESHNESS_TTL_MS_DEFAULT = 6 * 3600_000; // 缺省 6h;OPS_GITHUB_FRESHNESS_TTL_MS 可配

// 文件一层缺省路径:主检出锚(git-common-dir 推导单源复用 leak-check.mjs);git 探败
// 退化 REPO_ROOT(记忆化降级为本树文件,不红)。
export function githubFreshnessCacheDefaultPath() {
  return path.join(mainCheckoutRoot(REPO_ROOT) ?? REPO_ROOT, "dev", "add-bench", "github-freshness-cache.json");
}

// 文件一层读:缺席/不可读=未命中(静默——冷缓存是常态);JSON 坏/形状坏=corrupt
// 留痕(弃缓存重探,#340 ①:不红不阻跑)。
function readGithubFreshnessFile(file) {
  let text;
  try { text = fs.readFileSync(file, "utf8"); } catch { return { entries: null }; }
  try {
    const j = JSON.parse(text);
    if (!j || typeof j !== "object" || Array.isArray(j) || !j.entries || typeof j.entries !== "object" || Array.isArray(j.entries))
      return { entries: null, corrupt: true };
    return { entries: j.entries };
  } catch { return { entries: null, corrupt: true }; }
}

// 文件一层写:读改写合并(并发进程各写各键,整文件后者胜;条目粒度覆盖)+ tmp-rename
// 原子换面(读方不见半截 JSON;半截=坏=弃,下轮自愈)。写败静默降级=进程内一层
// (只读 FS 面记忆化仍成立,性能面不红轮)。
function writeGithubFreshnessFile(file, api, entry) {
  const { entries } = readGithubFreshnessFile(file); // 坏/缺席从空重建(弃缓存不阻跑)
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const tmp = `${file}.tmp-${process.pid}`;
    fs.writeFileSync(tmp, `${JSON.stringify({ version: 1, entries: { ...(entries ?? {}), [api]: entry } }, null, 2)}\n`);
    fs.renameSync(tmp, file);
  } catch { /* 降级进程内一层;见上 */ }
}

// 条目可用性:committer_date/cached_at 均可解析才可用(单条目坏=跳过重探,不算文件坏)
function githubFreshnessEntryUsable(raw) {
  if (!raw || typeof raw !== "object") return null;
  const commitMs = Date.parse(raw.committer_date), cachedMs = Date.parse(raw.cached_at);
  if (!Number.isFinite(commitMs) || !Number.isFinite(cachedMs)) return null;
  return {
    commitMs, cachedMs,
    etag: typeof raw.etag === "string" && raw.etag ? raw.etag : null,
    committer_date: raw.committer_date, cached_at: raw.cached_at,
  };
}

export function rosterCollisions(candidate, rosterLines, rosterUrls = new Map()) {
  const stripWww = (h) => (h.startsWith("www.") ? h.slice(4) : h);
  // 候选面:URL 形取 hostname(家族另取路径键);裸 host 形(旧测试面)整串当 host
  let candHost = "";
  try {
    candHost = stripWww(new URL(String(candidate ?? "")).hostname.toLowerCase());
  } catch {
    candHost = stripWww(String(candidate ?? "").toLowerCase());
  }
  if (!candHost) return [];
  const candKey = GITHUB_FAMILY_HOSTS.has(candHost) ? githubPathKey(candidate) : null;
  const hits = [];
  for (const line of rosterLines ?? []) {
    const cells = String(line).split("|").map((c) => c.trim());
    if (cells.length < 4) continue;
    const name = cells[0];
    const host = (cells[2] ?? "").toLowerCase();
    const rosterHost = stripWww(host);
    const subs = (cells[4] ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    if (subs.includes(candHost)) hits.push(candHost); // 子列信号面(dataplane 前例;非域名形,host/家族判据之外)
    if (candKey) {
      if (!GITHUB_FAMILY_HOSTS.has(rosterHost)) continue; // 家族外可注册域位 ≠ 同发布方
      const urls = rosterUrls.get(name) ?? [];
      const matched = urls.find((u) => githubPathKey(u) === candKey);
      if (matched) hits.push(String(matched)); // 撞卡证据形=命中 roster url 原文
      else if (!urls.some((u) => githubPathKey(u))) hits.push(host); // 无 url 证据=保守 host 级红
    } else if (host && rosterHost === candHost) {
      hits.push(host); // host 级(非家族;或家族候选无路径键——裸域/截断形保守退化)
    }
  }
  return [...new Set(hits)];
}

// 鲜活度门(定案 8 VERIFY 行):数据内时间戳 ≤30d 过;无活性证据(last-modified/
// github commits API/响应头内嵌日期三基均未取得)=fail-closed
// (file-mtime/「URL 响应了」不算活性证据——sunset 源冻结文件也 200;发布方活性证据
// 面=github 家族 commits API 已接 #339 ① probeLiveness 回退,basis=github_commit;
// #342 A2 第三基 embedded_date=响应头 content-disposition 文件名内嵌日期,非家族且
// 前两基皆空才看,详 probeLiveness 注释;变更对抓等深水面仍不接入不谎报)。
export function freshnessOf(liveness, nowMs = Date.now()) {
  const age = liveness?.age_days;
  if (typeof age === "number" && Number.isFinite(age)) {
    if (age <= 30) return { ok: true, basis: liveness.basis ?? "age_days", age_days: age };
    return { ok: false, basis: liveness.basis ?? "age_days", age_days: age, reason: `数据内部时间戳 age_days=${age}>30(sunset 嫌疑)` };
  }
  return { ok: false, basis: "none", reason: "无活性证据(直接探活无 last-modified、家族 commits 证据未取得或非家族、响应头亦无可解析内嵌日期;无证据即无话,fail-closed)" };
}

// 交接单形状(定案 2:实抓样本 3-5 行/格式/auth/cadence/字段路由草案)
export function dossierShape(d) {
  const no = (reason) => ({ ok: false, reason });
  if (d == null || typeof d !== "object" || Array.isArray(d)) return no("dossier 须是非数组对象");
  for (const k of ["name", "url", "format", "auth", "cadence"])
    if (typeof d[k] !== "string" || !d[k].trim()) return no(`${k} 缺失或非非空字符串`);
  if (!/^https?:\/\//.test(d.url)) return no("url 须 http(s) 形");
  if (!Array.isArray(d.samples) || d.samples.length < 3 || d.samples.length > 5)
    return no(`samples 须 3-5 行实抓样本(得到 ${Array.isArray(d.samples) ? d.samples.length : "非数组"})`);
  for (const s of d.samples) if (typeof s !== "string" || !s.trim()) return no("samples 行须非空字符串");
  if (!Array.isArray(d.field_routing) || !d.field_routing.length || d.field_routing.some((s) => typeof s !== "string" || !s.trim()))
    return no("field_routing 须非空字符串数组(字段路由草案)");
  return { ok: true, dossier: d };
}

// 实现摘要形状(TDD 硬序自报面;红绿序的机检在 G_IMPLEMENT 转录面,自报+机检双钉)
export function implementSummaryShape(s) {
  const no = (reason) => ({ ok: false, reason });
  if (s == null || typeof s !== "object" || Array.isArray(s)) return no("summary 须是非数组对象");
  for (const k of ["name", "test_file", "source_file"])
    if (typeof s[k] !== "string" || !s[k].trim()) return no(`${k} 缺失或非非空字符串`);
  if (s.red_observed !== true) return no("red_observed 须 true(TDD 硬序:先亲眼红)");
  if (s.green_observed !== true) return no("green_observed 须 true(后转绿)");
  return { ok: true, summary: s };
}

// GATE 命令集:真实面=定案 8 三连(逐源测试+source_infra+目录源审计;解释器由调用方
// 传入=主检出 venv 绝对路径);faux 面=fixtures/add/gate.json 罐装清单(命令真执行,
// 只是最小沙箱树跑不了全仓三连——机制面等价:执行+记录+门红绿)。
export function gateCommandsFor({ stem, modelFace, fixturesDir }) {
  if (modelFace === "faux" && typeof fixturesDir === "string") {
    const p = path.join(fixturesDir, "gate.json");
    let fx = null;
    try { fx = JSON.parse(fs.readFileSync(p, "utf8")); } catch { /* 缺席=fail-closed,同下 */ }
    if (!fx || !Array.isArray(fx.commands) || !fx.commands.length)
      throw Object.assign(new Error(`faux 面缺 gate.json 罐装命令清单:${p}`), { code: "infra" });
    return fx.commands.map((c) => ({ args: [...c.args], cwd: c.cwd ?? "" }));
  }
  return [
    { args: ["-m", "pytest", `tests/sources/test_${stem}.py`, "-q"], cwd: "backend" },
    { args: ["-m", "pytest", "tests/source_infra/", "-q"], cwd: "backend" },
    { args: ["scripts/audit_lmdb_invariants.py"], cwd: "" },
  ];
}

const writeJson = (p, o) => fs.writeFileSync(p, JSON.stringify(o, null, 2) + "\n"); // 旧 steps.mjs writeJson 同形
const readJson = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const jsonlOf = (p) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) : []);

function resolveOpsRoot(env = process.env) { // 旧 opsRootOf 同算式(discover-round 同形)
  return path.join(env.DOCS_ROOT ?? path.join(REPO_ROOT, "docs"), "ops");
}

// ── ctx(本文件私有形状:加源轮无旧步零复制面,不挂 ctxShape)──────────────
function buildCtx(input, checkpoint) {
  const env = process.env; // 旧律:env 现读不入档(凭证红线)
  const opsRoot = resolveOpsRoot(env);
  return {
    type: "add",
    roundId: input.roundId,
    source: input.source,
    bench: input.bench === true,
    dir: path.join(opsRoot, "rounds", input.roundId),
    opsRoot,
    queueFile: path.join(opsRoot, "queue.md"),
    env,
    log: (line) => process.stderr.write(`[add:${checkpoint.phase}] ${line}\n`), // stdout 只留末行信封(ENVELOPE.md)
    fixturesDir: input.fixturesDir,
    modelFace: input.modelFace,
    budgetCny: input.budgetCny,
    budgetKnobs: input.knobs,
    sandboxRoot: input.sandboxRoot,
    python: input.python,
    ledgerFile: env.LEDGER_FILE ?? process.env.LEDGER_FILE ?? path.join(opsRoot, "ledger.md"),
    modelCalls: checkpoint.modelCalls,
    usage: { ...checkpoint.usage },
    sandboxFace: checkpoint.sandboxFace ?? null,
    card: checkpoint.card ?? null,
    envelope: null,
    addHost: null,
    state: { // state.json 镜像面(观察面;真源=checkpoint)
      schema: 1, round_id: input.roundId, type: "add", pipeline_mode: "pipeline", status: "running",
      stages: checkpoint.stages.map((r) => r.name),
      budget_cny: input.budgetCny, budget_knobs: input.knobs,
      fixtures_dir: input.fixturesDir, model_face: input.modelFace,
      prompt_hashes: checkpoint.prompt_hashes,
      started_at: checkpoint.startedAtIso, updated_at: new Date().toISOString(),
      resume_count: 0, replay_of: null, monthly_admission: input.admission ?? null,
      source: input.source, sandbox_root: input.sandboxRoot, bench: input.bench === true,
    },
  };
}

// ── 建轮/镜像/推进(discover-round 同律拷形:同 id 守卫+mkdir+state 骨架;镜像尽力)──
function bootstrapRoundDir(ctx, checkpoint) {
  const stateFile = path.join(ctx.dir, "state.json");
  if (checkpoint.stages.length === 0) {
    let prior = null;
    try { prior = JSON.parse(fs.readFileSync(stateFile, "utf8")); } catch { /* 无=全新 */ }
    if (prior && (prior.round_id !== ctx.roundId || (Array.isArray(prior.stages) && prior.stages.length > 0)))
      throw Object.assign(new Error(`rounds/${ctx.roundId} 已存在(同 id 重跑走 replay)`), { code: "bad_round" });
    fs.mkdirSync(ctx.dir, { recursive: true });
    fs.writeFileSync(stateFile, JSON.stringify(ctx.state, null, 2) + "\n");
    return;
  }
  fs.mkdirSync(ctx.dir, { recursive: true }); // resume:目录必在(防御)
}
function mirrorState(ctx, checkpoint) {
  try {
    ctx.state.stages = checkpoint.stages.map((r) => r.name);
    ctx.state.updated_at = new Date().toISOString();
    fs.writeFileSync(path.join(ctx.dir, "state.json"), JSON.stringify(ctx.state, null, 2) + "\n");
  } catch { /* 镜像失败不阻断相位推进(哲学①:证据在 checkpoint+工件) */ }
}
async function advance(runtime, context, checkpoint, patch = {}, ctx = null) {
  await runtime.commit((tx, cur) => ({
    status: "running",
    checkpoint: { ...cur.checkpoint, ...checkpoint, ...patch },
  }), context);
  if (ctx) mirrorState(ctx, checkpoint);
}
async function finishFailed(runtime, context, error) {
  return runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error } }), context);
}
async function finishOk(runtime, context, result) {
  return runtime.commit(() => ({ status: "terminal", outcome: { status: "completed", result } }), context);
}

// 崩溃钩子(测试面;env 现读不入档):进入指定相位头即 SIGKILL 自杀(上一相位
// checkpoint 已提交=该相位头进程崩溃;真崩溃恢复路径与测试同一代码路径,零 mock)。
function crashHook(phase) {
  if (process.env.OPS_V2_CRASH_AFTER_PHASE === phase) process.kill(process.pid, "SIGKILL");
}

// 相位推进(bench 形态的 DOSSIER 截断不走本表:dossierPhase 的 bench 分支自身就是
// 开关位接口——写 a2(bench:true)+过门+零 stage 记录直进 implement,定案 2)

// ── 门(表驱动,留痕经旧 gates.appendGate 同件)──────────────────────────
const j = (ctx, name) => readJson(path.join(ctx.dir, name));
const gateFail = (reason, inputs, code) => ({ pass: false, reason, inputs, code });
const gatePass = (reason, inputs) => ({ pass: true, reason, inputs });
function insideSandbox(sandboxRoot, p) {
  const root = path.resolve(sandboxRoot);
  let target;
  try { target = path.resolve(root, p ?? ""); } catch { return null; }
  return target === root || target.startsWith(root + path.sep) ? target : null;
}

export const ADD_GATES = {
  G_VERIFY: (ctx) => {
    const inputs = [ART.VERIFY, "queue.md"];
    const v = j(ctx, ART.VERIFY);
    if (!v) return gateFail(`${ART.VERIFY} 不可解析`, inputs, "infra");
    if (!v.card?.name || !v.card?.url) return gateFail("卡面缺 name/url(PROPOSE 行 evidence)", inputs, "card_missing");
    if ((v.roster?.collisions ?? []).length)
      return gateFail(`同出版方已在库(roster 撞卡:${v.roster.collisions.join(",")})——信号走既有源的面,不按新源立项`, inputs, "duplicate_publisher");
    if (v.freshness?.ok !== true) return gateFail(`鲜活度门:${v.freshness?.reason ?? "证据缺席"}`, inputs, "freshness_gate");
    return gatePass(`卡 ${v.source} APPROVE 读回;roster ${v.roster.rows_n} 行零撞;freshness ${v.freshness.basis} age_days=${v.freshness.age_days}`, inputs);
  },
  G_DOSSIER: (ctx) => {
    const inputs = [ART.DOSSIER, ART.DOSSIER_T];
    const d = j(ctx, ART.DOSSIER);
    if (!d?.dossier) return gateFail(`${ART.DOSSIER} 不可解析/缺 dossier`, inputs, "model_face");
    const r = dossierShape(d.dossier);
    if (!r.ok) return gateFail(`交接单形状:${r.reason}`, inputs, "model_face");
    return gatePass(`交接单过(name=${d.dossier.name} 样本 ${d.dossier.samples.length} 行;${d.bench ? "bench 预填" : "模型补卡"})`, inputs);
  },
  G_IMPLEMENT: (ctx) => {
    const inputs = [ART.IMPL, ART.IMPL_T, "(sandbox)"];
    const a = j(ctx, ART.IMPL);
    if (!a?.summary) return gateFail(`${ART.IMPL} 不可解析/缺 summary`, inputs, "model_face");
    const r = implementSummaryShape(a.summary);
    if (!r.ok) return gateFail(`实现摘要:${r.reason}`, inputs, "model_face");
    if (a.summary.name !== a.stem) return gateFail(`stem 漂移:${a.summary.name}≠${a.stem}(文件名契约钉死)`, inputs, "model_face");
    // 评审修批(#332 评审 P2):路径逐字钉死 stem 契约——任意在场路径即过会让偏航拖到 GATE 才暴露
    const canonical = { test_file: `backend/tests/sources/test_${a.stem}.py`, source_file: `backend/ipdb/_sources/${a.stem}.py` };
    for (const key of ["test_file", "source_file"]) {
      const rel = a.summary[key];
      if (rel !== canonical[key]) return gateFail(`路径契约:${key}=${rel}≠${canonical[key]}(stem 逐字)`, inputs, "model_face");
      const target = insideSandbox(ctx.sandboxRoot, rel);
      if (!target || !fs.existsSync(target)) return gateFail(`声明文件不在沙箱:${rel}`, inputs, "model_face");
    }
    // TDD 硬序机检:转录 run_pytest 种子序首红末绿(自报 red/green_observed 之外的独立回算)
    const pys = jsonlOf(path.join(ctx.dir, ART.IMPL_T)).filter((l) => l.type === "registry_seed" && l.tool === "run_pytest").map((l) => l.sc?.ok === true);
    if (!(pys.length >= 2 && pys[0] === false && pys[pys.length - 1] === true))
      return gateFail(`TDD 硬序未走:run_pytest 种子序须首跑红(模块缺)末跑绿(得到 [${pys.join(",")}])——先写测试亲眼看红,再写源转绿`, inputs, "model_face");
    return gatePass(`摘要过+双文件沙箱在场+TDD 序首红末绿(${pys.length} 跑)`, inputs);
  },
  G_GATE: (ctx) => {
    const inputs = [ART.GATE];
    const g = j(ctx, ART.GATE);
    if (!g || !Array.isArray(g.results) || !g.results.length) return gateFail(`${ART.GATE} 不可解析/零命令`, inputs, "infra");
    const red = g.results.filter((r) => r.rc !== 0);
    if (red.length) return gateFail(`门命令红 ${red.length}/${g.results.length}:${red.map((r) => `${r.label}(rc=${r.rc})`).join(";")}${red[0].tail ? ` 尾部:${String(red[0].tail).slice(0, 200)}` : ""}`, inputs, "gate_failed");
    return gatePass(`${g.results.length} 命令全绿(${g.results.map((r) => `${r.label} ${r.dur_ms}ms`).join(",")})`, inputs);
  },
  G_REPORT: (ctx) => {
    const inputs = [ART.REPORT, "(sandbox git)"];
    const rep = j(ctx, ART.REPORT);
    if (!rep?.sandbox) return gateFail(`${ART.REPORT} 不可解析`, inputs, "infra");
    if (rep.sandbox.repo === false) return gatePass("沙箱非 git 仓:如实记 repo=false(分支指针缺席,人裁面可见)", inputs);
    if (typeof rep.sandbox.sha !== "string" || !rep.sandbox.sha) return gateFail("沙箱 git 仓缺分支指针(sha)", inputs, "infra");
    return gatePass(`分支指针 ${rep.sandbox.sha.slice(0, 12)}(${rep.sandbox.branch}${rep.sandbox.committed ? ",本轮提交" : ",无新提交"})`, inputs);
  },
  G_CLOSE: (ctx) => {
    const inputs = ["(stdout 轮次信封)", ART.BUDGET, "(ledger)", ART.VERIFY];
    // 零队列写防线第 2 锚(#334 消化件②):a1 钉的 queue.md sha 对拍现读——轮零队列写
    // 红线(写口仅人面)的镜像台账行读回同律;改写=红 sandbox_violation,轮判失败。
    const a1 = j(ctx, ART.VERIFY);
    if (!a1?.queue_sha) return gateFail(`a1 缺 queue_sha(形状漂移:零队列写防线装不上)`, inputs, "infra");
    const queueNow = fs.existsSync(ctx.queueFile) ? fs.readFileSync(ctx.queueFile, "utf8") : "";
    if (sha(queueNow) !== a1.queue_sha)
      return gateFail(`queue.md 在轮内被改写(a1 sha ${a1.queue_sha} ≠ 现 ${sha(queueNow)}):轮零队列写红线,写口仅人面(#139 flock 纪律)`, inputs, "sandbox_violation");
    if (!ctx.envelope) return gateFail("信封未组装", inputs, "infra");
    const s = JSON.stringify(ctx.envelope);
    if (s.includes("\n")) return gateFail("信封非单行", inputs, "infra");
    if (JSON.parse(s).ok !== ctx.envelope.ok) return gateFail("信封不可往返解析", inputs, "infra");
    const b = j(ctx, ART.BUDGET); // 预算回声哨(环内已执法;门只对拍读数≤生效帽,防工件漂移——G_CLOSE 旧律)
    if (!b?.env || !b?.readings) return gateFail(`${ART.BUDGET} 缺席/形状坏(env+readings 必在场)`, inputs, "infra");
    if (b.readings.model_calls > b.env.OPS_ADD_MAX_MODEL_CALLS) return gateFail(`回声哨:model_calls=${b.readings.model_calls}>${b.env.OPS_ADD_MAX_MODEL_CALLS}`, inputs, "budget_exceeded");
    if ((b.readings.usage?.cost ?? 0) > b.env.OPS_ADD_SPEND_CAP_CNY) return gateFail(`回声哨:cost=${b.readings.usage.cost}>${b.env.OPS_ADD_SPEND_CAP_CNY}`, inputs, "budget_exceeded");
    if ((b.readings.wall_s ?? 0) > b.env.OPS_ADD_WALL_CLOCK_S) return gateFail(`回声哨:wall_s=${b.readings.wall_s}>${b.env.OPS_ADD_WALL_CLOCK_S}`, inputs, "wall_clock_exceeded");
    const ledger = fs.existsSync(ctx.ledgerFile) ? fs.readFileSync(ctx.ledgerFile, "utf8") : null;
    if (ledger === null || !ledger.includes(`${ADD_LEDGER_TAG}:${ctx.roundId}`)) return gateFail("台账读回缺本轮行(pipeline-add)", inputs, "ledger_failed");
    return gatePass(`信封单行可往返;预算回声 ${b.readings.model_calls} 调用/¥${(b.readings.usage?.cost ?? 0).toFixed(8)}/${b.readings.wall_s}s ≤ 帽;台账行读回`, inputs);
  },
};
function evalGate(phase, ctx) {
  const name = GATE_OF[phase];
  const fn = ADD_GATES[name];
  const t0 = performance.now();
  const r = fn ? fn(ctx) : { pass: false, reason: `未知门 ${name}(定义表漂移)`, inputs: [] };
  return { stage: STAGE_OF[phase], name, pass: !!r.pass, reason: r.reason, dur_ms: Math.round(performance.now() - t0), inputs: r.inputs ?? [], ...(r.code ? { code: r.code } : {}) };
}

// ── 信封(ENVELOPE.md add 节:发现轮 7 键族+add 域两键 source/sandbox;pkg 恒 null、
//    queue_writes 恒空——轮无写口改卡状态,定案 9)──────────────────────────
function composeEnvelope(checkpoint, ctx) {
  return {
    ok: true,
    round: "add",
    pipeline: { round_id: checkpoint.roundId, resumed_from: null, replayed_of: null, stages: checkpoint.stages },
    source: ctx.source,
    sandbox: { root: ctx.sandboxRoot, branch: ctx.sandboxFace?.branch ?? null, sha: ctx.sandboxFace?.sha ?? null },
    pkg: null,
    queue_writes: [],
    usage: { ...ctx.usage },
    verify: { ok: true, cited: 0 },
  };
}

// ── 相位步(脚本面)────────────────────────────────────────────────────

// VERIFY:卡消费 + roster diff + 鲜活度(证据全落 a1;域错 card_* 先炸——无卡无可记)
async function runVerify(ctx) {
  const text = fs.existsSync(ctx.queueFile) ? fs.readFileSync(ctx.queueFile, "utf8") : "";
  const rows = parseQueueRows(text);
  const approve = rows.find((r) => r.action === "APPROVE" && r.source === ctx.source);
  if (!approve)
    throw Object.assign(new Error(`卡 ${ctx.source} 未 APPROVE(加源轮只消费 status=approved 的卡;APPROVE 写口仅人面,轮不改卡状态)`), { code: "card_not_approved" });
  const cardRow = rows.filter((r) => r.action === "PROPOSE" && r.source === ctx.source).at(-1);
  if (!cardRow)
    throw Object.assign(new Error(`卡 ${ctx.source} 无 PROPOSE 候选行(APPROVE 在场但候选卡缺席——队列崩殘态,人面补卡)`), { code: "card_missing" });
  const card = {
    name: typeof cardRow.evidence.get("candidate:name") === "string" ? cardRow.evidence.get("candidate:name") : ctx.source,
    url: typeof cardRow.evidence.get("candidate:url") === "string" ? cardRow.evidence.get("candidate:url") : null,
    approved_by: cardRow.evidence.get("human:approved_by") ?? approve.evidence.get("human:approved_by") ?? null,
  };
  // 零队列写防线第 1 锚(#334 消化件②):a1 相位记 queue.md sha,G_CLOSE 对拍——
  // 轮内任何面(含模型工具 run_bash 绝对路径写)改写队列,门红 sandbox_violation。
  const queue_sha = sha(text);
  // roster diff:faux=罐装行(+可选 roster_urls 证据面);真实面=沙箱内
  // python -m ipdb._registry --roster(定案 8 跑法)+ meta dump urls(#337 F4 家族判据证据面,
  // DUMP_META_SCRIPT 判据单源——与 gen-exam-cards 同源消费)
  let roster;
  let rosterUrls = new Map();
  let liveness;
  if (ctx.modelFace === "faux" && typeof ctx.fixturesDir === "string") {
    const fx = readJson(path.join(ctx.fixturesDir, "verify.json")) ?? {};
    roster = Array.isArray(fx.roster) ? fx.roster : [];
    rosterUrls = new Map(Object.entries(fx.roster_urls ?? {}).map(([n, us]) => [n, Array.isArray(us) ? us.map(String) : []]));
    liveness = fx.liveness ?? {};
  } else {
    roster = (await execFileP(ctx.python, ["-m", "ipdb._registry", "--roster"],
      { cwd: path.join(ctx.sandboxRoot, "backend"), timeout: 120_000, maxBuffer: 16 * 1024 * 1024 })).stdout.split("\n").filter(Boolean);
    const meta = JSON.parse((await execFileP(ctx.python, ["-c", DUMP_META_SCRIPT],
      { cwd: path.join(ctx.sandboxRoot, "backend"), timeout: 120_000, maxBuffer: 16 * 1024 * 1024 })).stdout);
    rosterUrls = new Map(Object.entries(meta).map(([n, e]) => [n, Array.isArray(e?.urls) ? e.urls.map(String) : []]));
    liveness = await probeLiveness(card.url);
  }
  const collisions = card.url ? rosterCollisions(card.url, roster, rosterUrls) : [];
  const freshness = freshnessOf(liveness);
  writeJson(path.join(ctx.dir, ART.VERIFY), {
    round_id: ctx.roundId, source: ctx.source, generated_at: new Date().toISOString(),
    card, queue_sha, roster: { rows_n: roster.length, collisions }, liveness, freshness,
  });
  return { patch: { card } };
}

// #342 A2:content-disposition filename 内嵌日期解析(第三证据基 embedded_date 的
// 证据面)。filename 参数引号/裸形都认;日期两形:YYYY-MM-DD 与 yyyymmdd 紧排
// (数字串恰 8 位边界钉死——9 位长串不得按前 8 位误读);真实日历日校验
// (2026-02-30/2026-13-01 不认);多日期取最新(last_modified 组合面 newest 同律)。
// 解析不出 → null = 无证据 fail-closed(裸 200 不算数,A1 拒);范围只做响应头
// 面,不嗅探响应体(体面另议)。实例:anycast_census manycast.net
// `attachment; filename="IPv4-2026-11-12.csv.gz"`——URL 恒 latest 形,真日期只在
// disposition 文件名里(2026-11-12 实测)。
export function embeddedDateFromDisposition(cd) {
  if (typeof cd !== "string" || !cd) return null;
  const fm = cd.match(/filename\s*=\s*(?:"([^"]*)"|([^;\s]+))/i);
  const filename = (fm?.[1] ?? fm?.[2] ?? "").trim();
  if (!filename) return null;
  const cand = [];
  for (const m of filename.matchAll(/(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)/g)) cand.push([+m[1], +m[2] - 1, +m[3]]);
  for (const m of filename.matchAll(/(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)/g)) cand.push([+m[1], +m[2] - 1, +m[3]]);
  const ms = cand.map(([y, mo, d]) => {
    const dt = new Date(Date.UTC(y, mo, d));
    return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo && dt.getUTCDate() === d ? dt.getTime() : NaN; // 非真实日历日 → NaN 弃
  }).filter(Number.isFinite);
  return ms.length ? { ms: Math.max(...ms), filename } : null;
}

// 真实面探活(4 组合 GET/HEAD × UA 有无):last-modified 内时间戳=鲜活度证据面;
// 「响应了」不算证据(sunset 冻结文件也 200——技能 Phase 1 鲜活度门同律)。
// #341 ② 限流退避与重试(主会话 2026-11-12 令,票 #341 修件 2):同 host 高频 4 组合
// 疑似被限流(feeds.dshield.org 实测 last-modified 缺席→fail-closed 误红)——①组合间
// 短退避(首组合零等待,后续每组合前 comboDelayMs,缺省 300ms);②失败组合一次重试
// (重试前 retryDelayMs,缺省 750ms)。失败判据=限流签名:传输错/status 429 或 503;
// 200-无 header 是稳定答案不重试(对天然无 last-modified 的源重试=双倍打,与退避初衷
// 相反)。重试终面原位覆盖,首轮失败以 first_error 留痕(证据不灭失)。参数面
// opts={sleepImpl,comboDelayMs,retryDelayMs} 注入=测试零真实等待。
// github 家族活性证据回退(#339 ①,P3 前置阻断件):直接探活拿不到证据(无 last-modified
// 或连接失败——本机 raw.githubusercontent.com TCP 被墙即此态)且 URL 属家族(GITHUB_
// FAMILY_HOSTS,#337 F4 常量复用)时,转 api.github.com commits API 取最新 commit 的
// committer date(发布方活性证据,主会话裁定 2026-11-12;api.github.com 本机可达,
// stamparm/ipsum 实测 2026-11-11)。证据优先级 last_modified > github_commit;API 失败
// /无 commit = fail-closed none(无证据即无话)。fetchImpl 注入=测试面零网络。
// #340:commits API 回退调用走限流记忆化(两层+Conditional GET,见 GITHUB_FRESHNESS_
// MEM 注释;注入缝 githubCacheMem/githubCacheFile/githubCacheTtlMs 同风格)。
// #342 A2 第三基 embedded_date:直接探活无 last-modified、又非 github 家族时,响应头
// content-disposition 文件名内嵌日期(解析律见 embeddedDateFromDisposition)采信为
// basis=embedded_date,age 按该日期算(UTC 午夜);日期解析失败=无证据 fail-closed
// (裸 200 不算数,A1 拒;#339 勘误预告「数据内时间戳(未实现)」的响应头面补齐,体面
// 另议)。优先级 last_modified > github_commit > embedded_date——前两基都拿不到才看
// 第三基;github 家族不吃第三基(host 级判家族,家族面仍走 commits 回退,commits
// 失败=fail-closed 不退回)。留痕:embedded_date 面 {date_source=
// content_disposition_filename, filename, date},header 原文随 combos 入档。
export async function probeLiveness(url, fetchImpl = fetch, opts = {}) {
  const { sleepImpl = (ms) => new Promise((r) => setTimeout(r, ms)), comboDelayMs = 300, retryDelayMs = 750,
    githubCacheMem, githubCacheFile, githubCacheTtlMs } = opts; // #340 记忆化注入缝(同风格:undefined=缺省,file=null 关文件层)
  const combos = [];
  const hit = async (method, ua) => {
    const r = await fetchImpl(url, {
      method, redirect: "manual", signal: AbortSignal.timeout(15_000),
      headers: ua ? { "user-agent": "ip-radar-add-round/1.0" } : {},
    });
    return { method, ua, status: r.status, last_modified: r.headers.get("last-modified"), content_disposition: r.headers.get("content-disposition") }; // #342 A2:第三基证据面随组合留痕
  };
  if (url) {
    let first = true;
    for (const method of ["GET", "HEAD"]) {
      for (const ua of [true, false]) {
        if (!first) await sleepImpl(comboDelayMs); // 组合间短退避(#341 ②)
        first = false;
        try {
          combos.push(await hit(method, ua));
        } catch (e) {
          combos.push({ method, ua, error: String(e?.cause?.message ?? e?.message ?? e).slice(0, 160) });
        }
      }
    }
    // 失败组合一次重试(#341 ②:限流签名=传输错/429/503;仅一次,不无限)
    for (const c of combos) {
      if (!(c.error != null || c.status === 429 || c.status === 503)) continue;
      await sleepImpl(retryDelayMs);
      const firstError = c.error ?? `HTTP ${c.status}`;
      try {
        const again = await hit(c.method, c.ua);
        // 重试成功后清陈旧 error(#341 评审 P2-2:避免同档 error+200 并存);first_error 保首轮失败面
        delete c.error;
        Object.assign(c, again, { retried: true, first_error: firstError });
      } catch (e) {
        Object.assign(c, { retried: true, first_error: firstError, error: String(e?.cause?.message ?? e?.message ?? e).slice(0, 160) });
      }
    }
  }
  const newest = combos.map((c) => c.last_modified).filter(Boolean).map((s) => new Date(s))
    .filter((d) => !Number.isNaN(d.getTime())).sort((a, b) => b - a)[0] ?? null;
  const fromLm = newest ? { last_modified: newest.toISOString(), age_days: Math.floor((Date.now() - newest.getTime()) / 86_400_000), basis: "last_modified" } : null;
  const gh = fromLm ? null : await githubCommitEvidence(url, fetchImpl, // 优先级:last_modified 在场不触 API
    { mem: githubCacheMem, file: githubCacheFile, ttlMs: githubCacheTtlMs });
  const fromGh = gh?.dateMs != null
    ? { age_days: Math.floor((gh.ageAsOfMs - gh.dateMs) / 86_400_000), basis: "github_commit" } // age 用取得时刻算(#340:命中=缓存回放面)
    : null;
  // #342 A2 第三基:前两基皆空且非 github 家族(host 级判,githFamilyHost 单源)才看;
  // 多组合取最新(last_modified 同律);解析失败=无证据 fail-closed
  const embCands = (fromLm || fromGh || githubFamilyHost(url)) ? []
    : combos.map((c) => embeddedDateFromDisposition(c.content_disposition)).filter(Boolean);
  const emb = embCands.length ? embCands.reduce((a, b) => (b.ms > a.ms ? b : a)) : null;
  const fromEmb = emb ? { age_days: Math.floor((Date.now() - emb.ms) / 86_400_000), basis: "embedded_date" } : null;
  const evidence = fromLm ?? fromGh ?? fromEmb;
  return {
    combos,
    last_modified: fromLm?.last_modified ?? null,
    age_days: evidence?.age_days,
    basis: evidence?.basis ?? "none",
    github_commit: gh?.evidence ?? gh ?? null, // 回退证据留痕(成败面都留 api/status/日期或 error;证据不灭失,#339 评审 P1:失败面裸 ev 也入档,与未尝试可分诊)
    embedded_date: emb ? { date_source: "content_disposition_filename", filename: emb.filename, date: new Date(emb.ms).toISOString() } : null, // #342 A2 留痕;null=未采或不适用(header 原文在 combos 可分诊)
  };
}

// 家族 commits API 活性证据(#339 ①):GET <api>?path=<文件路径>&per_page=1,取
// commit[0].commit.committer.date。失败面(网络/非 200/非 JSON/空数组/缺 committer
// date)统一 fail-closed 返回无 date 的证据记录;非家族 URL → null。
// #340 限流记忆化(两层+Conditional GET):cache={mem, file, ttlMs} 注入面
// (probeLiveness opts 同风格缝;undefined=缺省,file=null 关文件层)。命中返回
// {dateMs, ageAsOfMs, evidence}——ageAsOfMs=age 计算基准时刻(命中=取得时刻,
// 200/304=now),probeLiveness 据此算 age_days。
async function githubCommitEvidence(url, fetchImpl, cache = {}) {
  const q = githubCommitsQuery(url);
  if (!q) return null;
  const {
    mem = GITHUB_FRESHNESS_MEM,
    file = githubFreshnessCacheDefaultPath(),
    ttlMs = Number(process.env.OPS_GITHUB_FRESHNESS_TTL_MS) > 0 ? Number(process.env.OPS_GITHUB_FRESHNESS_TTL_MS) : GITHUB_FRESHNESS_TTL_MS_DEFAULT,
  } = cache;
  const now = Date.now();
  const ev = { api: q.api, status: null, committer_date: null };
  // 两层读(#340 ①):进程内 → 文件(文件命中回填进程内层)
  let cached = githubFreshnessEntryUsable(mem.get(q.api));
  let cacheNote = null;
  if (!cached && file) {
    const { entries, corrupt } = readGithubFreshnessFile(file);
    if (corrupt) cacheNote = "cache_file_corrupt"; // 弃缓存留痕(可分诊,#339 ③ 同律)
    const raw = entries?.[q.api];
    cached = githubFreshnessEntryUsable(raw);
    if (cached) mem.set(q.api, raw);
  }
  if (cached && now - cached.cachedMs < ttlMs) {
    // TTL 内命中:零网络零配额;age 用取得时刻算(记忆化回放,#340 ①)
    return { dateMs: cached.commitMs, ageAsOfMs: cached.cachedMs,
      evidence: { ...ev, committer_date: cached.committer_date, cached_at: cached.cached_at, cache: "hit" } };
  }
  ev.cache = "miss"; // 触网面(与 hit/未尝试三分可分诊,#339 ③)
  if (cacheNote) ev.cache_note = cacheNote;
  // Conditional GET(#340 ②):过期/未命中条目带 etag → If-None-Match;304 不占配额
  const headers = { "user-agent": "ip-radar-add-round/1.0", accept: "application/vnd.github+json" };
  if (cached?.etag) headers["if-none-match"] = cached.etag;
  try {
    const res = await fetchImpl(q.api, {
      method: "GET", redirect: "manual", signal: AbortSignal.timeout(15_000), headers,
    });
    ev.status = res.status;
    const got = Date.now(); // 取得时刻=fetch 完成后(#340 评审补:P31 毫秒边界——pre-fetch now 会把 age 算短 1ms 使 floor 掉档)
    if (res.status === 304 && cached) {
      // 304=未变更:不占配额,视为新鲜证据——cached_at 更新为再验证时刻(取得时刻),
      // committer_date 沿缓存(304 无 body),条目两层面回写(#340 ②)
      const revalidated = { etag: res.headers.get("etag") ?? cached.etag, committer_date: cached.committer_date, cached_at: new Date(got).toISOString() };
      mem.set(q.api, revalidated);
      if (file) writeGithubFreshnessFile(file, q.api, revalidated);
      return { dateMs: cached.commitMs, ageAsOfMs: got,
        evidence: { ...ev, cache: "revalidated", committer_date: cached.committer_date, cached_at: revalidated.cached_at } };
    }
    if (res.status !== 200) return ev; // fail-closed;缓存条目不动(etag 留给下轮再验证)
    const body = await res.json().catch(() => null);
    const d = Array.isArray(body) ? body[0]?.commit?.committer?.date : null;
    const t = d ? new Date(d).getTime() : NaN;
    if (Number.isFinite(t)) {
      ev.committer_date = new Date(t).toISOString();
      ev.cached_at = new Date(got).toISOString(); // 取得时刻入档(证据不灭失,#340 ①)
      const entry = { etag: res.headers.get("etag"), committer_date: ev.committer_date, cached_at: ev.cached_at };
      mem.set(q.api, entry);
      if (file) writeGithubFreshnessFile(file, q.api, entry);
      return { dateMs: t, ageAsOfMs: got, evidence: ev };
    }
    return ev;
  } catch (e) {
    ev.error = String(e?.cause?.message ?? e?.message ?? e).slice(0, 160);
    return ev;
  }
}

function phaseAfter(phase) {
  return ADD_PHASES[ADD_PHASES.indexOf(phase) + 1] ?? null;
}

// GATE:命令集执行(真实面三连/faux 罐装;命令真执行零网络,rc 全记录,红=门红留证)
async function runGatePhase(ctx, checkpoint) {
  const dossier = checkpoint.dossier;
  if (!dossier) throw Object.assign(new Error("交接单缺席(dossier 相位未过?)"), { code: "infra" });
  const stem = slugify(dossier.name);
  const commands = gateCommandsFor({ stem, modelFace: ctx.modelFace, fixturesDir: ctx.fixturesDir });
  const results = [];
  for (const c of commands) {
    const cwd = insideSandbox(ctx.sandboxRoot, c.cwd ?? "");
    if (!cwd) throw Object.assign(new Error(`GATE cwd 逃逸沙箱:${c.cwd}`), { code: "infra" });
    const t0 = Date.now();
    let rc = 0, tail = "";
    try {
      const r = await execFileP(ctx.python, c.args, { cwd, timeout: 600_000, maxBuffer: 32 * 1024 * 1024 });
      tail = String(r.stdout ?? "").split("\n").filter(Boolean).slice(-15).join("\n").slice(0, 2000);
    } catch (e) {
      rc = typeof e.code === "number" ? e.code : -1;
      tail = `${String(e.stdout ?? "")}\n${String(e.stderr ?? "")}`.split("\n").filter(Boolean).slice(-15).join("\n").slice(0, 2000);
    }
    results.push({ label: c.args.join(" ").slice(0, 120), cwd: c.cwd ?? "", rc, dur_ms: Date.now() - t0, tail });
  }
  writeJson(path.join(ctx.dir, ART.GATE), { round_id: ctx.roundId, stem, commands: results.map(({ label, cwd }) => ({ label, cwd })), results, passed: results.every((r) => r.rc === 0), generated_at: new Date().toISOString() });
  return {};
}

// REPORT:沙箱 git 提交 + 分支指针(轮产出=沙箱分支;git 身份经 -c 注入,沙箱仓无需配置)
async function runReport(ctx) {
  const sandboxFace = { root: ctx.sandboxRoot, repo: false, branch: null, sha: null, committed: false };
  if (fs.existsSync(path.join(ctx.sandboxRoot, ".git"))) {
    sandboxFace.repo = true;
    const git = (args) => execFileP("git", ["-C", ctx.sandboxRoot, ...args], { timeout: 60_000, maxBuffer: 8 * 1024 * 1024 });
    await git(["add", "-A"]);
    try {
      await git(["-c", "user.email=add-round@ipradar.local", "-c", "user.name=add-round", "commit", "-m", `add-round ${ctx.roundId}: ${ctx.source}`]);
      sandboxFace.committed = true;
    } catch (e) {
      if (!/nothing to commit|no changes added/i.test(`${e.stderr ?? ""}\n${e.message ?? ""}`))
        throw Object.assign(new Error(`沙箱提交败:${e.message}`), { code: "infra" });
    }
    sandboxFace.sha = (await git(["rev-parse", "HEAD"])).stdout.trim();
    sandboxFace.branch = (await git(["rev-parse", "--abbrev-ref", "HEAD"])).stdout.trim();
  }
  const gateArt = j(ctx, ART.GATE);
  writeJson(path.join(ctx.dir, ART.REPORT), {
    round_id: ctx.roundId, source: ctx.source, generated_at: new Date().toISOString(),
    sandbox: sandboxFace,
    gate: { commands: gateArt?.results?.length ?? 0, passed: gateArt?.passed ?? null },
    note: "轮产出=沙箱分支,永不自并入 master(人裁终局;spec 定案 9 停止点)",
  });
  return { patch: { sandboxFace } };
}

// CLOSE:主检出防线 + 台账行 + 09-budget 快照(证据先于信封)
async function runClose(ctx, checkpoint) {
  try { await sh("sandbox_assert", [], 60_000, ctx.env); } // 主检出 backend/frontend 零改动防线(RETRO 同款)
  catch (e) { throw Object.assign(new Error(`sandbox_assert rc≠0(主检出污染):${e.message}`), { code: "sandbox_violation" }); }
  const usage = ctx.usage;
  const usageStr = `in=${usage.input} out=${usage.output} total=${usage.totalTokens} cost=${usage.cost.toFixed(8)}`;
  let ledgerNow = null;
  try { ledgerNow = fs.readFileSync(ctx.ledgerFile, "utf8"); } catch { /* 首轮无台账文件=正常 */ }
  if (!(ledgerNow ?? "").includes(`${ADD_LEDGER_TAG}:${ctx.roundId}`)) // 幂等重入:resume 不双记账
    try { await sh("ledger_append", ["add", ctx.modelFace === "real" ? "pipeline-real" : "faux-pipeline", usageStr, `${ADD_LEDGER_TAG}:${ctx.roundId}`], 120_000, ctx.env); }
    catch (e) { throw Object.assign(new Error(`台账写败:${e.message}`), { code: "ledger_failed" }); }
  const knobs = ctx.budgetKnobs;
  writeJson(path.join(ctx.dir, ART.BUDGET), {
    round_id: ctx.roundId, generated_at: new Date().toISOString(),
    env: { // 生效值(OPS_ADD_* 三旋钮+est+共享月帽;无 token 界——发现轮同律)
      OPS_PIPELINE_BUDGET_CNY: ctx.budgetCny,
      OPS_ADD_MAX_MODEL_CALLS: knobs.maxModelCalls,
      OPS_ADD_WALL_CLOCK_S: knobs.wallClockS,
      OPS_ADD_SPEND_CAP_CNY: knobs.spendCapCny,
      OPS_PIPELINE_MONTHLY_CAP_CNY: knobs.monthlyCapCny,
    },
    readings: {
      usage: { ...usage },
      model_calls: ctx.modelCalls ?? 0,
      wall_s: Number(elapsedWallS(checkpoint.startedAtIso).toFixed(1)),
      monthly: checkpoint.admission ?? null,
    },
  });
  return {};
}

const SCRIPT_STEPS = Object.freeze({ verify: runVerify, gate: runGatePhase, report: runReport, close: runClose });

// ── 脚本相位骨架(预算墙钟头执法 → 步 → 门 → checkpoint)────────────────
async function scriptPhase(task, runtime, context, phase) {
  const input = task.input;
  const cur = task.state.checkpoint;
  crashHook(phase);
  const b = stepBoundary({ roundType: "add", knobs: input.knobs, startedAtIso: cur.startedAtIso }); // ③
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: STAGE_OF[phase] } });
  const ctx = buildCtx(input, cur);
  if (phase === "verify") {
    try { bootstrapRoundDir(ctx, cur); }
    catch (e) { return finishFailed(runtime, context, { message: `${STAGE_OF[phase]}:${e.message}`, detail: { code: e.code ?? "infra", stage: STAGE_OF[phase] } }); }
  }
  const stage = { name: STAGE_OF[phase], status: "done", attempts: 1, dur_ms: 0, usage: null }; // 脚本步恒零模型面(旧律)
  const t0 = Date.now();
  let rec;
  try { rec = await SCRIPT_STEPS[phase](ctx, cur); }
  catch (e) { // 域失败=终态(旧 fail 三元组;工件已写面保留=证据不灭失)
    return finishFailed(runtime, context, { message: `${STAGE_OF[phase]}:${e.message}`, detail: { code: e.code ?? "infra", stage: STAGE_OF[phase] } });
  }
  stage.dur_ms = Date.now() - t0;
  const staged = [...cur.stages, stage];
  if (phase === "close") ctx.envelope = composeEnvelope({ ...cur, stages: staged }, ctx); // G_CLOSE 前置(旧引擎职责位)
  const gateRec = evalGate(phase, ctx);
  gates.appendGate(ctx.dir, ctx.roundId, gateRec);
  if (!gateRec.pass) return finishFailed(runtime, context, { message: `GATE:${STAGE_OF[phase]}:${gateRec.reason}`, detail: { code: gateRec.code ?? "infra", stage: STAGE_OF[phase] } }); // 门红=终态(fail-closed)
  const next = phaseAfter(phase);
  const checkpoint = { ...cur, ...(next ? { phase: next } : {}), stages: staged, modelCalls: ctx.modelCalls, usage: { ...ctx.usage }, ...(rec?.patch ?? {}) }; // 相位推进=phase 字段前移(缺它=同相位重跑死循环)
  return next
    ? advance(runtime, context, checkpoint, {}, ctx)
    : finishOk(runtime, context, composeEnvelope(checkpoint, ctx)); // close 终态=result=信封
}

// ── 模型相位(DOSSIER/IMPLEMENT 共骨架;一轮一会话两次 submit)───────────
// 预算执法粒度说明(#334 评论消化件③,至少头注言明):OPS_ADD_* ①③帽在 attempt(=一次
// submit 腿)粒度执法——IMPLEMENT 一次 submit 内的工具循环逐回合无帽间检查(回合计数在
// 结算后入账,超帽在下一次 attempt/相位边界拦);腿中 abort/看门狗留后续票。
const MODEL_LEGS = Object.freeze({
  dossier: { stage: "DOSSIER", gate: "G_DOSSIER", promptFile: "dossier.md", artifact: ART.DOSSIER, transcript: ART.DOSSIER_T },
  implement: { stage: "IMPLEMENT", gate: "G_IMPLEMENT", promptFile: "implement.md", artifact: ART.IMPL, transcript: ART.IMPL_T },
});

// 会话 UsageDoc 活和(discover-round roundUsage 同形拷形;字段面=旧 ctx.usage 形状)
async function roundUsage(runtime, convId, context) {
  const v = await runtime.snapshot(UsageDoc, convId, context) ?? {};
  let input = 0, output = 0, totalTokens = 0, cost = 0;
  for (const bucket of [v.models, v.tools])
    for (const u of Object.values(bucket ?? {})) {
      input += u?.input ?? 0; output += u?.output ?? 0;
      totalTokens += u?.totalTokens ?? 0; cost += u?.cost?.total ?? 0;
    }
  return { input, output, totalTokens, cost };
}

function buildUserMsg(phase, ctx, checkpoint) {
  const prompt = fs.readFileSync(addPromptPath(MODEL_LEGS[phase].promptFile), "utf8");
  if (phase === "dossier")
    return `${prompt}\n\n---\n\n候选卡(已 APPROVE,只读):\n${JSON.stringify(checkpoint.card ?? { source: ctx.source }, null, 2)}\n\n终答契约:单条 JSON(交接单七键;不得夹其他文本)。`;
  const dossier = checkpoint.dossier ?? {};
  const stem = slugify(dossier.name ?? "");
  return `${prompt}\n\n---\n\n交接单:\n${JSON.stringify(dossier, null, 2)}\n\n源文件名 stem(钉死):${stem}\n期望路径:backend/tests/sources/test_${stem}.py 与 backend/ipdb/_sources/${stem}.py\n沙箱根:${ctx.sandboxRoot}\n沙箱 backend 目录:${path.join(ctx.sandboxRoot, "backend")}\npytest 解释器(绝对路径):${ctx.python}\n\n终答契约:单条 JSON {name,test_file,source_file,red_observed,green_observed,notes}(路径相对沙箱根;不得夹其他文本)。`;
}

function consumeModelText(phase, text) {
  let parsed = null;
  try { parsed = JSON.parse(text); } catch { return { ok: false, reason: `终答非 JSON(须单条 JSON,得到 ${text.slice(0, 80)}…)` }; }
  if (phase === "dossier") {
    const r = dossierShape(parsed);
    return r.ok ? { ok: true, value: { dossier: r.dossier } } : { ok: false, reason: `交接单形状:${r.reason}` };
  }
  const r = implementSummaryShape(parsed);
  return r.ok ? { ok: true, value: { summary: r.summary } } : { ok: false, reason: `实现摘要:${r.reason}` };
}

async function modelLeg(task, runtime, context, phase) {
  const input = task.input;
  const cur = task.state.checkpoint;
  crashHook(phase);
  const leg = MODEL_LEGS[phase];
  const b = stepBoundary({ roundType: "add", knobs: input.knobs, startedAtIso: cur.startedAtIso }); // ③
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: leg.stage } });
  const pb = preModelCall({ roundType: "add", knobs: input.knobs, modelCalls: cur.modelCalls, startedAtIso: cur.startedAtIso }); // ①③(每 attempt 提交前)
  if (!pb.ok) return finishFailed(runtime, context, { message: pb.message, detail: { code: pb.code, stage: leg.stage } });

  const ctx = buildCtx(input, cur);
  const conversation = await runtime.conversation(runtime.conversationId, context);
  if (!conversation) return finishFailed(runtime, context, { message: `${leg.stage}:轮会话缺席`, detail: { code: "infra", stage: leg.stage } });
  const host = ensureAddHost(ctx, runtime.conversationId); // 轮级编码宿主(模型面工具;faux=罐装回合驱动真工具)

  const attempt = cur.attempt ?? 1;
  const requestId = attempt <= 1 ? `round-${input.roundId}-${phase}` : `round-${input.roundId}-${phase}-a${attempt}`; // 幂等纪律形;同 attempt 崩溃重放同 key
  const userMsg = buildUserMsg(phase, ctx, cur);
  const t0 = Date.now();
  const submission = await conversation.submit({ type: "input", content: userMsg, requestId }, context);
  const settled = await submission.wait(context); // 恰好一次;同 key 崩溃重放不双花
  const view = await runtime.context(runtime.conversationId, context);
  const messages = view.entries.filter((e) => e.kind === "pi.assistant").flatMap((e) => e.model);
  const modelCallsNow = messages.length; // 会话累计回合数=调用计数(工具循环逐回合计)
  const last = messages[messages.length - 1];
  const text = last?.content?.filter((c) => c.type === "text").map((c) => c.text).join("") ?? "";
  const retryOr = (code, message) => attempt < 2 // 旧 retry≤1 面:结算坏/空文本/形状坏重发新 requestId;失败 attempt 计数同步入账(旧律重试同计)
    ? advance(runtime, context, cur, { attempt: attempt + 1, modelCalls: modelCallsNow }, ctx)
    : finishFailed(runtime, context, { message, detail: { code, stage: leg.stage } });
  if (settled.status !== "done") return retryOr("model_face", `${leg.stage}:submission_${settled.status}`);
  if (!text) return retryOr("empty_text", `${leg.stage}:empty_text`);

  const usageNow = await roundUsage(runtime, runtime.conversationId, context);
  const post = postModelCall({ roundType: "add", knobs: input.knobs, totalTokens: usageNow.totalTokens, costCny: usageNow.cost }); // ②(skip:无 token 界)④
  if (!post.ok) return finishFailed(runtime, context, { message: post.message, detail: { code: post.code, stage: leg.stage } });

  const consumed = consumeModelText(phase, text);
  if (!consumed.ok) return retryOr("model_face", `${leg.stage}:${consumed.reason}`);

  // transcript(input + 本腿种子增量 + 本腿回合增量;行型=旧 faux.mjs:input/registry_seed/message)
  const sys = fs.readFileSync(addPromptPath("system.md"), "utf8"); // 会话 instructions 实际装载面(run-add 创建会话时装入,同源同字)
  const seedBase = host.seedMark ?? 0;
  const lines = [
    JSON.stringify({ type: "input", stage: leg.stage, system_sha: sha(sys), user_sha: sha(userMsg), meta: null }),
    ...host.seeds.slice(seedBase).map((sd) => JSON.stringify({ type: "registry_seed", call_id: sd.call_id, tool: sd.tool, sc: sd.sc })),
    ...messages.slice(cur.modelCalls).map((m) => JSON.stringify({ type: "message", role: m.role, content: m.content, stopReason: m.stopReason ?? null })),
  ];
  fs.appendFileSync(path.join(ctx.dir, leg.transcript), lines.join("\n") + "\n");
  host.seedMark = host.seeds.length;

  // 工件
  if (phase === "dossier") writeJson(path.join(ctx.dir, leg.artifact), { round_id: input.roundId, bench: false, dossier: consumed.value.dossier, generated_at: new Date().toISOString() });
  else writeJson(path.join(ctx.dir, leg.artifact), { round_id: input.roundId, stem: slugify((checkpointDossier(cur, input)?.name) ?? ""), summary: consumed.value.summary, generated_at: new Date().toISOString() });

  const gateRec = evalGate(phase, ctx);
  gates.appendGate(ctx.dir, ctx.roundId, gateRec);
  if (!gateRec.pass) return finishFailed(runtime, context, { message: `GATE:${leg.stage}:${gateRec.reason}`, detail: { code: gateRec.code ?? "model_face", stage: leg.stage } });

  // 相位步 usage=本腿增量(会话累计差分;usage 求和律:各步之和==信封 usage)
  const usageDelta = { input: usageNow.input - cur.usage.input, output: usageNow.output - cur.usage.output, totalTokens: usageNow.totalTokens - cur.usage.totalTokens, cost: usageNow.cost - cur.usage.cost };
  const next = phaseAfter(phase);
  const checkpoint = {
    ...cur, phase: next, attempt: 1,
    stages: [...cur.stages, { name: leg.stage, status: "done", attempts: attempt, dur_ms: Date.now() - t0, usage: usageDelta }],
    modelCalls: modelCallsNow,
    usage: { ...usageNow },
    prompt_hashes: { ...cur.prompt_hashes, [leg.stage]: sha(`${sys}\n${userMsg}`) },
    ...(phase === "dossier" ? { dossier: consumed.value.dossier } : { implement: consumed.value.summary }),
  };
  return advance(runtime, context, checkpoint, {}, ctx);
}
const checkpointDossier = (cur, input) => cur.dossier ?? input.dossier ?? null;

// DOSSIER 相位:bench 形态跳过(定案 2 开关位;交接单=input.dossier 预填,同门校验,零模型面)
async function dossierPhase(task, runtime, context) {
  const input = task.input;
  if (input.bench !== true) return modelLeg(task, runtime, context, "dossier");
  const cur = task.state.checkpoint;
  crashHook("dossier");
  const b = stepBoundary({ roundType: "add", knobs: input.knobs, startedAtIso: cur.startedAtIso });
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: "DOSSIER" } });
  const r = dossierShape(input.dossier);
  if (!r.ok) return finishFailed(runtime, context, { message: `DOSSIER:bench 交接单形状坏:${r.reason}`, detail: { code: "model_face", stage: "DOSSIER" } });
  const ctx = buildCtx(input, cur);
  writeJson(path.join(ctx.dir, ART.DOSSIER), { round_id: input.roundId, bench: true, dossier: r.dossier, generated_at: new Date().toISOString() });
  const gateRec = evalGate("dossier", ctx);
  gates.appendGate(ctx.dir, ctx.roundId, gateRec);
  if (!gateRec.pass) return finishFailed(runtime, context, { message: `GATE:DOSSIER:${gateRec.reason}`, detail: { code: gateRec.code ?? "model_face", stage: "DOSSIER" } });
  return advance(runtime, context, { ...cur, phase: "implement", dossier: r.dossier }, {}, ctx); // stages 不记跳过相位(discover bench 截断同律)
}

// ── defineTask ─────────────────────────────────────────────────────────
export const addRoundTask = defineTask({
  name: ADD_TASK_NAME,
  version: 1,
  initial: (input) => ({
    phase: "verify",
    roundId: input.roundId,
    startedAtIso: new Date().toISOString(), // 墙钟真源:initial 一次,恢复不改写(续算)
    modelCalls: 0,
    usage: { input: 0, output: 0, totalTokens: 0, cost: 0 },
    stages: [],
    prompt_hashes: {},
    attempt: 1,
  }),
  phases: {
    verify: (task, runtime, context) => scriptPhase(task, runtime, context, "verify"),
    dossier: (task, runtime, context) => dossierPhase(task, runtime, context),
    implement: (task, runtime, context) => modelLeg(task, runtime, context, "implement"),
    gate: (task, runtime, context) => scriptPhase(task, runtime, context, "gate"),
    report: (task, runtime, context) => scriptPhase(task, runtime, context, "report"),
    close: (task, runtime, context) => scriptPhase(task, runtime, context, "close"),
  },
  abort: async (_task, runtime, context) => { // 中止终态留痕(discover/health mkAbort 同款)
    await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), context);
  },
});
