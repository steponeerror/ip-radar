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

export const ROOT = path.resolve(import.meta.dirname, "..", "..", ".."); // ops/agent-v2/bench → 仓根(3 层;4 层病同 tasks/discover-round.mjs:61 钉死款)

export const EXEMPT_MARKER = "禁词引用"; // #308 判例字样,与 .git/hooks/pre-commit 同款

// 基准面名单载体文件名(§3.3:免考规则与别名表)——缺省扫描面剔除
export const ROSTER_CARRIER_FILES = new Set(["exam-rules.json", "aliases.json"]);

export function shortlistBenchPromptPath(root = ROOT) {
  return path.join(root, "ops", "agent", "prompts", "discover", "shortlist-bench.md");
}

// ── 归一化与匹配 ──
export function squeeze(text) {
  return text.toLowerCase().replace(/[^a-z0-9]/g, "");
}

// roster 行形:`name | category | download_host | fields`(python -m ipdb._registry --roster);
// download_host '-' = 免考(Q8),折成 null(域名无针,源名仍红)。
export function parseRoster(text) {
  const entries = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const [name, category, host] = line.split(/\s*\|\s*/);
    if (!name || !category) continue;
    entries.push({ name: name.trim(), category: category.trim(), host: host && host.trim() !== "-" ? host.trim() : null });
  }
  return entries;
}

// 每源漏题针:名字归一化形 + 下载域名(全域名 + 去 www 类首段后的父域;三段以上才剥,
// 且只剥一段——再剥会把多级域名剥到公共后缀,误红一片。
export function buildNeedles(entries) {
  return entries.map((e) => {
    const domains = new Set();
    if (e.host) {
      const sq = squeeze(e.host);
      domains.add(sq);
      const labels = e.host.split(".");
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

// 缺省扫描面:基准提示词(在才扫;票 B 未落=空集放行)+ bench/ 下除名单载体外全部
// 文本文件(递归;排序确定)。leak-check.mjs 自身也在面内——自扫自红,名单零硬编码。
export function defaultScanSurface(root = ROOT) {
  const files = [];
  const prompt = shortlistBenchPromptPath(root);
  if (fs.existsSync(prompt)) files.push(prompt);
  const benchDir = path.join(root, "ops", "agent-v2", "bench");
  const walk = (dir) => {
    if (!fs.existsSync(dir)) return;
    for (const ent of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (ent.isFile() && !ROSTER_CARRIER_FILES.has(ent.name)) files.push(p);
    }
  };
  walk(benchDir);
  return files.sort();
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

// 目录递归收集(explicit 面不剔除名单载体——用户点名要扫就扫全;缺省面才剔除)
function walkFiles(dir, out) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walkFiles(p, out);
    else if (ent.isFile()) out.push(p);
  }
  return out;
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
        ? explicit.flatMap((p) => { const ap = path.resolve(p); return fs.statSync(ap).isDirectory() ? walkFiles(ap, []) : [ap]; })
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
