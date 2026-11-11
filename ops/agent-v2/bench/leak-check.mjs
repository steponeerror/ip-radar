#!/usr/bin/env node
// leak-check.mjs — 重发现基准防漏题闸(票 #321;spec docs/research/2026-11-07-rediscover-bench-spec.md §3.4,Q5/Q8/Q12)。
// 语义:基准面文件全文出现 roster 任何源名(名字归一化形式)或其下载域名 → 红;
// 行级豁免标记「禁词引用:原因」放行该行——判例同主仓 pre-commit 禁词钩子(#308:
// 行内含「禁词引用」字样即放行,理由写在被引行上),两侧语义钉死同构。
// 免考(download_host='-')源名同样红:免考只是不进考题分母,不是许可写进提示词。
// 名单取数机械派生(Q12 禁手工第二份清单):`python -m ipdb._registry --roster`
// (worktree 跑法见 loadRosterText 注),或 --roster-file/env BENCH_ROSTER_FILE 注入 dump。
// 归一化 = 小写化 + 剔除非字母数字(两侧同折):下划线/连字符/点/大小写/融写/中文
// 夹写全折到同一形;代价是跨标点偶接(如「a, b」折成「ab」)可能误红——宁红勿漏
// (Q5 机检哲学),误伤走行级豁免标记。
// 用法:node leak-check.mjs [路径...] [--roster-file PATH] [--python BIN]
//   缺省扫描面 = ops/agent/prompts/discover/shortlist-bench.md(在才扫,票 B 产物;
//   不在=空集放行)+ ops/agent-v2/bench/ 下除 exam-rules.json/aliases.json 外全部文件
//   (两者本就是名单/别名载体,自扫自红无意义)。
// 退出码:0=绿;1=红(有命中);2=用法/名单取数失败。
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { DISCOVER_SHORTLIST_BENCH_PROMPT } from "../../agent/artifacts.mjs"; // 基准提示词路径单源(终审 P2-1:与 run-discover.mjs 同源消费)
import { parseRoster } from "./roster.mjs"; // roster 行解析单源(终审 P2-2:与 score.mjs 同源,失败语义同构 fail-closed)

export const ROOT = path.resolve(import.meta.dirname, "..", "..", ".."); // ops/agent-v2/bench → 仓根(3 层;4 层病同 tasks/discover-round.mjs:61 钉死款)

export const EXEMPT_MARKER = "禁词引用"; // #308 判例字样,与 .git/hooks/pre-commit 同款

// 基准面名单载体文件名(§3.3:免考规则与别名表)——缺省扫描面剔除
export const ROSTER_CARRIER_FILES = new Set(["exam-rules.json", "aliases.json"]);

// 基准提示词路径:文件名单源 DISCOVER_SHORTLIST_BENCH_PROMPT(ops/agent/artifacts.mjs;
// run-discover.mjs shortlistBenchPromptPath 同源消费——双处手抄漂移曾致提示词改名后
// 本面 existsSync 空集放行、漏题闸静默装绿,终审 P2-1)。
export function shortlistBenchPromptPath(root = ROOT) {
  return path.join(root, "ops", "agent", "prompts", DISCOVER_SHORTLIST_BENCH_PROMPT);
}

// ── 加源域扫描面(票 #334 交付面 3:轮提示词不得含考题名单)──
// 轮提示词目录 = ops/agent/prompts/add/(P1 #332 三件 system/dossier/implement;
// bench 形态装载 system+implement,生产形态另装载 dossier,三件全收)。在才扫(同
// 基准提示词律);真仓在场由 leak-check.test.mjs 单源钉死测试把门——改名/移位→钉死
// 测试红,不静默装绿(终审 P2-1 同款防线)。
export function addPromptsDir(root = ROOT) {
  return path.join(root, "ops", "agent", "prompts", "add");
}

// ── 归一化与匹配 ──
export function squeeze(text) {
  return text.toLowerCase().replace(/[^a-z0-9]/g, "");
}

// roster 行解析在 ./roster.mjs 单源(终审 P2-2 抽出,与 score.mjs 同源):坏行列数<4 throw、
// 零有效行 throw——名单取数坏了就红,不带病开闸;download_host '-' 原样保留,'-' 免考
// 语义(Q8)在 buildNeedles 内折无域名针(源名仍红)。

// 每源漏题针:名字归一化形 + 下载域名(全域名 + 去 www 类首段后的父域;三段以上才剥,
// 且只剥一段——再剥会把多级域名剥到公共后缀,误红一片。
export function buildNeedles(entries) {
  return entries.map((e) => {
    const domains = new Set();
    const host = e.host && e.host !== "-" ? e.host : null; // '-' = 免考无下载面(Q8):无域名针(源名针照常红)
    if (host) {
      const sq = squeeze(host);
      domains.add(sq);
      const labels = host.split(".");
      if (labels.length >= 3) domains.add(squeeze(labels.slice(1).join(".")));
    }
    return { source: e.name, name: squeeze(e.name), domains: [...domains] };
  });
}

// 单行检查:行含豁免标记 → 整行放行(#308 判例);否则全行折形后对每源做子串匹配。
// 同源名字针与域名针可折到同形(源名与其下载域名去首段可折到同一字符串):按
// 源+针去重留一记(name 先检先留)——一行一红足够,重复行只呔噪。
export function checkLine(line, needles) {
  if (line.includes(EXEMPT_MARKER)) return [];
  const sq = squeeze(line);
  const hits = [];
  const seen = new Set();
  for (const n of needles) {
    if (sq.includes(n.name)) hits.push({ source: n.source, kind: "name", needle: n.name }), seen.add(`${n.source}/${n.name}`);
    for (const d of n.domains)
      if (sq.includes(d) && !seen.has(`${n.source}/${d}`)) hits.push({ source: n.source, kind: "domain", needle: d });
  }
  return hits;
}

// ── 名单取数(Q12:机械派生,单源 = roster)──
// 注入优先级:rosterText > rosterFile > env BENCH_ROSTER_FILE > spawn python(默认
// `python3 -m ipdb._registry --roster`,cwd=本仓 backend/;env IPDB_PYTHON 换解释器——
// worktree 判例:主检出解释器绝对路径 + cwd 切 worktree 的 backend/,AGENTS.md「worktree
// 里跑后端测试」同款)。取不到 = 用法级失败(exit 2),不带病开闸。
export function loadRosterText(opts = {}) {
  const env = opts.env ?? process.env;
  if (opts.rosterText !== undefined) return opts.rosterText;
  const file = opts.rosterFile ?? (env.BENCH_ROSTER_FILE ? path.resolve(env.BENCH_ROSTER_FILE) : null);
  if (file) return fs.readFileSync(file, "utf8");
  const bin = opts.pythonBin ?? env.IPDB_PYTHON ?? "python3";
  const r = spawnSync(bin, ["-m", "ipdb._registry", "--roster"], { cwd: path.join(opts.root ?? ROOT, "backend"), encoding: "utf8" });
  if (r.error || r.status !== 0)
    throw new Error(`roster 取数失败(${bin} -m ipdb._registry --roster,exit=${r.status}):${r.stderr || r.error?.message || "无输出"};可用 --roster-file 注入 dump`);
  return r.stdout;
}

// 目录递归收集(缺省面/显式面共底座,差一个名单载体剔除集——终审 P2-5 提取,行为不变;
// 排序确定)。缺省面传 ROSTER_CARRIER_FILES,显式面(用户点名要扫就扫全)传 null。
function walkFiles(dir, out, excludeNames) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walkFiles(p, out, excludeNames);
    else if (ent.isFile() && !(excludeNames && excludeNames.has(ent.name))) out.push(p);
  }
  return out;
}

// 缺省扫描面:基准提示词(在才扫;票 B 未落=空集放行)+ bench/ 下除名单载体外全部
// 文本文件(递归;排序确定)。leak-check.mjs 自身也在面内——自扫自红,名单零硬编码。
// #334:加源轮提示词目录 prompts/add/ 同律在才扫(轮提示词不得含考题名单)。
export function defaultScanSurface(root = ROOT) {
  const files = [];
  const prompt = shortlistBenchPromptPath(root);
  if (fs.existsSync(prompt)) files.push(prompt);
  const addPrompts = addPromptsDir(root);
  if (fs.existsSync(addPrompts)) walkFiles(addPrompts, files, null); // 轮提示词面:全收(无名单载体)
  const benchDir = path.join(root, "ops", "agent-v2", "bench");
  if (fs.existsSync(benchDir)) walkFiles(benchDir, files, ROSTER_CARRIER_FILES);
  return files.sort();
}

// ── 轮产出 diff 泄漏针(票 #334 交付面 3:diff 不得引用被剥路径)──
// 被剥路径的可达面 = 答案树在主检出侧的绝对路径:剥答案沙箱由主检出 git archive 构建,
// 轮 diff(相对根提交的变更文件)引用主检答案树/主检 .git(考古面)即泄漏证据。
// 针 = 主检 backend/ipdb 与 backend/tests 两前缀 + 主检 .git(归一化子串匹配,大小写/
// 分隔符折叠);沙箱内相对路径(backend/tests/... 是 IMPLEMENT 合法产出面)不红;
// venv 解释器绝对路径合法入提示词(buildUserMsg 亲手给的跑法),不红——答案树外的
// 主检路径不禁。相对形引用主检答案(`git -C` 相对路径考古)在 diff 层不可区分于沙箱
// 自身合法相对路径,靠提示词禁令兜——不追求物理剥净(spec 原话)。
// 针根双面(票 #337 F5):repoRoot(沙箱构建源仓,worktree 跑法下=worktree)+ 主检出根
// (git-common-dir 推导;worktree 检出的 .git 文件指向主检 .git,dirname 即主检根,
// 主检出自身时同算式退化为自身去重——与 run-add.mjs resolveAddPython 沙箱解释器推导
// 同一算式;此前只盖 repoRoot,worktree 跑法下主检答案树不被针)。mainRoot 显式注入
// 口仅供测试钉面;推导失败(非 git 根)=只针 repoRoot 单根。
// 针不按题名拼(题名形 test_<name>.py 属沙箱合法产出面,按树前缀禁即可)——故无
// 题名参数(#339 ⑤ 删 void 弃用死参,调用点同步)。
// files = [{path, text}](沙箱内相对 path + 全文 text);返回 {ok, hits:[{file,line,needle,text}]}。
export function mainCheckoutRoot(repoRoot) {
  const r = spawnSync("git", ["-C", String(repoRoot), "rev-parse", "--path-format=absolute", "--git-common-dir"], { encoding: "utf8" });
  const out = String(r.stdout ?? "").trim();
  if (r.error || r.status !== 0 || !out) return null;
  return path.dirname(path.resolve(out));
}

export function checkRoundDiffLeak({ repoRoot, mainRoot, files }) {
  const root = path.resolve(String(repoRoot ?? ""));
  if (!root || root === "/") throw new Error("checkRoundDiffLeak 须给主检出 repoRoot(被剥路径针的基准)");
  const roots = [root];
  const main = mainRoot ? path.resolve(String(mainRoot)) : mainCheckoutRoot(root);
  if (main && main !== "/" && !roots.includes(main)) roots.push(main); // F5 针根补主检出(去重:主检出自身退化形)
  const treeNeedles = [...new Set(roots.flatMap((r) => [path.join(r, "backend", "ipdb"), path.join(r, "backend", "tests")]))]
    .map((p) => ({ raw: p, sq: squeeze(p) }));
  // 主检 .git 针:带后缀边界——<root>/.gitignore/.github 等同前缀真路径不误红
  const gitRes = roots.map((r) => ({ root: r, re: new RegExp(r.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\/\\.git(?![\\w.-])") }));
  const hits = [];
  for (const f of files ?? []) {
    const lines = String(f.text ?? "").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const sq = squeeze(lines[i]);
      for (const n of treeNeedles)
        if (sq.includes(n.sq)) hits.push({ file: f.path, line: i + 1, needle: n.raw, text: lines[i].trim().slice(0, 120) });
      for (const g of gitRes)
        if (g.re.test(lines[i])) hits.push({ file: f.path, line: i + 1, needle: path.join(g.root, ".git"), text: lines[i].trim().slice(0, 120) });
    }
  }
  return { ok: hits.length === 0, hits };
}

// ── 程序面(CLI 与测试共用)──
// 返回 { ok, scannedFiles, hits };hits 形 { file, line(1 起), text, source, kind, needle },
// 文件序/行序/roster 序三重确定(同面重跑同报,spec §3.3 确定性同律)。
export function runLeakCheck(opts = {}) {
  const entries = parseRoster(loadRosterText(opts));
  const needles = buildNeedles(entries);
  const hits = [];
  const scannedFiles = [];
  for (const file of opts.files) {
    scannedFiles.push(file);
    const text = fs.readFileSync(file, "utf8");
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++)
      for (const h of checkLine(lines[i], needles))
        hits.push({ file, line: i + 1, text: lines[i].trim().slice(0, 120), ...h });
  }
  return { ok: hits.length === 0, scannedFiles, hits };
}

// ── CLI(run-discover.mjs 同壳:exitCode 而非 exit——stdout 异步落管不截断)──
function usage() {
  process.stderr.write("用法:node leak-check.mjs [路径...] [--roster-file PATH] [--python BIN]\n  缺省扫描面=基准提示词(在才扫)+ ops/agent-v2/bench/ 除 exam-rules.json/aliases.json 外全部\n  名单缺省 spawn python -m ipdb._registry --roster(cwd=<root>/backend);env IPDB_PYTHON 换解释器\n  退出码:0=绿 1=红(命中) 2=用法/名单取数失败\n");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const VALUE_FLAGS = new Set(["--roster-file", "--python"]);
  const flag = (name) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
  // 位置参 = 非 flag 且前一参不是吃值的 flag(run-discover 终审修复同病:flag 值不得误当路径)
  const explicit = args.filter((a, i) => !a.startsWith("--") && !(i > 0 && VALUE_FLAGS.has(args[i - 1])));
  const unknown = args.filter((a) => a.startsWith("--") && !VALUE_FLAGS.has(a));
  if (unknown.length || (flag("roster-file") === undefined && args.includes("--roster-file")) || (flag("python") === undefined && args.includes("--python"))) {
    usage();
    process.exitCode = 2;
  } else {
    try {
      const files = explicit.length
        ? explicit.flatMap((p) => { const ap = path.resolve(p); return fs.statSync(ap).isDirectory() ? walkFiles(ap, [], null) : [ap]; })
        : defaultScanSurface();
      const r = runLeakCheck({ rosterFile: flag("roster-file"), pythonBin: flag("python"), files });
      const rel = (f) => { const r = path.relative(process.cwd(), f); return r && !r.startsWith("..") ? r : f; };
      if (r.ok) process.stdout.write(`leak gate 绿:扫描 ${r.scannedFiles.length} 文件,考题名单零命中\n`);
      else {
        process.stdout.write(`✋ leak gate 红:${r.hits.length} 处命中(行级豁免标记「${EXEMPT_MARKER}:原因」放行该行,判例同 pre-commit 禁词钩子):\n`);
        for (const h of r.hits) process.stdout.write(`  ${rel(h.file)}:${h.line} [${h.source}/${h.kind}] ${h.text}\n`);
      }
      process.exitCode = r.ok ? 0 : 1;
    } catch (err) {
      process.stderr.write(`leak gate 没开成:${err.message}\n`);
      usage();
      process.exitCode = 2;
    }
  }
}
