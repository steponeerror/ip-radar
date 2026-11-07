#!/usr/bin/env node
// score.mjs — 重发现基准打分器(#320,规格 docs/research/2026-11-07-rediscover-bench-spec.md §3.3)。
// 输入一轮盲测工件目录(含 d2-shortlist.json),同目录产出 report.md + report.json。
// 答案表 = `python -m ipdb._registry --roster` + 源模块声明的下载 URL/发布者(机械派生,
// 禁手工第二份清单,规格 §2 Q12);免考 = exam-rules.json 冻结 8(Q8);别名 = aliases.json
// (版本化,人工裁决一次入一条,Q3)。匹配四层(Q3):完整 URL → 发布者/域名 → 名字归一化 → 别名。
// otx 与 otx_subscribed 同发布者双记;github 家族(raw.githubusercontent.com/github.com)
// 多源共用主机,按 repo 路径段(owner/repo)区分不误并。确定性门:同工件目录重跑字节级同分。
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";

export const BENCH_DIR = import.meta.dirname;
export const D2_SHORTLIST = "d2-shortlist.json";

// github 家族 = 同仓多源共用主机,host 相等不足以并/分,按 repo 路径段区分
// (规格 §3.3「raw.githubusercontent 12 行按 repo 路径段区分不误并」;家族含
// github.com 仓页 URL——模型常给仓页而非 raw 直链,同一 repo 才算同发布面)。
const GITHUB_FAMILY = new Set(["github.com", "raw.githubusercontent.com"]);
const CATEGORY_ORDER = ["threat", "geo_asn", "asset"];

// ── 归一化(匹配键的机械定义,测试钉死)──

// 名字归一化:小写、去点去下划线去连字符(规格 Q3;「Blocklist.de」对 blocklist_de 需归一)。
export function normalizeName(s) {
  return String(s ?? "").toLowerCase().replace(/[._-]+/g, "");
}

// URL 归一化:仅取 http(s);host/path/query 小写、去 fragment、去尾斜杠。
// 返回 null = 无可用的 URL 匹配键(候选 url 缺省/非 URL 形状,一/二层照常落空)。
export function normalizeUrl(u) {
  const raw = String(u ?? "").trim();
  if (!raw) return null;
  let url;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  url.hash = "";
  const full = `${url.protocol}//${url.host}${url.pathname.replace(/\/+$/, "")}${url.search}`.toLowerCase();
  const host = url.hostname.toLowerCase();
  const segs = url.pathname.split("/").filter(Boolean).map((s) => s.toLowerCase());
  const repo = segs.length >= 2 ? `${segs[0]}/${segs[1]}` : null;
  return { full, host, repo };
}

// ── 答案表:roster dump × 免考规则 × URL 声明(机械派生)──

// roster 行:`name | category | download_host | fields [| 子列表]`(roster() 的固定格式,
// 子列表键并入 fields 供参考;host '-' = 无下载面)。
export function parseRoster(text) {
  const rows = [];
  for (const line of String(text ?? "").split("\n")) {
    const t = line.trim();
    if (!t) continue;
    const parts = t.split("|").map((p) => p.trim());
    if (parts.length < 4) throw new Error(`roster 行列数不足(须 ≥4:name|category|host|fields):${t}`);
    const [name, category, host, ...rest] = parts;
    rows.push({ name, category, host, fields: rest.flatMap((c) => c.split(",")).filter(Boolean) });
  }
  if (!rows.length) throw new Error("roster 输出为空");
  return rows;
}

// roster 命令之外的第二取数面:源模块声明的下载 URL(python -c 机械 dump,见 DUMP_URLS_SCRIPT)。
// 交叉校验:name 集合与 host 逐源一致——不一致即红,不给静默漂移留门(roster 单源纪律,Q12)。
// exam-rules 形状(票 D #321 定稿):exempt = [{name, reason, reclaim}];reclaim 非空
// ({date, ruling},用户裁决一次) = 捞回进考题分母参与召回;null = 免考不入分母。
export function buildAnswerTable({ rosterText, urlDumpJson, examRules, aliases }) {
  const rows = parseRoster(rosterText);
  let dump;
  try {
    dump = JSON.parse(String(urlDumpJson ?? "{}"));
  } catch (e) {
    throw new Error(`url dump 不是合法 JSON:${e.message}`);
  }
  const rosterNames = new Set(rows.map((r) => r.name));
  for (const [name, entry] of Object.entries(dump)) {
    const row = rows.find((r) => r.name === name);
    if (!row) throw new Error(`url dump 源不在 roster:${name}`);
    if ((entry.host ?? "-") !== row.host) {
      throw new Error(`url dump host 与 roster 不一致:${name} dump=${entry.host ?? "-"} roster=${row.host}`);
    }
  }
  for (const r of rows) {
    if (!(r.name in dump)) throw new Error(`url dump 缺 roster 源:${r.name}`);
  }
  const entries = examRules.exempt ?? [];
  for (const e of entries) {
    if (!e || typeof e.name !== "string" || !e.name) {
      throw new Error(`exam-rules.exempt 条目缺 name(D 形状 {name,reason,reclaim}):${JSON.stringify(e)}`);
    }
    if (!rosterNames.has(e.name)) throw new Error(`免考名单源不在 roster(冻结名单对不上现实):${e.name}`);
  }
  // reclaim 非空 = 用户已裁决捞回 → 进考题分母;null = 免考不入分母(D 版 _doc 口径)
  const exemptNames = new Set(entries.filter((e) => e.reclaim == null).map((e) => e.name));
  const aliasEntries = Object.entries(aliases.aliases ?? {});
  const build = (row) => {
    const urls = [...new Set(dump[row.name].urls ?? [])];
    const repos = [
      ...new Set(urls
        .map((u) => normalizeUrl(u))
        .filter((k) => k && GITHUB_FAMILY.has(k.host) && k.repo)
        .map((k) => k.repo)),
    ].sort();
    return {
      name: row.name,
      category: row.category,
      host: row.host,
      fields: row.fields,
      urls,
      repos,
      normName: normalizeName(row.name),
      aliasNames: aliasEntries
        .filter(([, target]) => target === row.name || normalizeName(target) === normalizeName(row.name))
        .map(([alias]) => normalizeName(alias))
        .sort(),
    };
  };
  return {
    rosterTotal: rows.length,
    exam: rows.filter((r) => !exemptNames.has(r.name)).map(build),
    exempt: rows.filter((r) => exemptNames.has(r.name)).map(build),
  };
}

// 匹配器:四层,1 完整 URL → 2 发布者/域名 → 3 名字归一化 → 4 别名表;先高层后低层,
// 返回首个命中的层号(1|2|3|4),未中返回 null。逐答案独立匹配——otx/otx_subscribed
// 同发布者,一条候选 URL 在第 2 层同时命中两源(规格:「同发布者双记」)。
export function matchLayer(answer, cand) {
  const key = normalizeUrl(cand?.url);
  if (key) {
    // L1 完整 URL:与源模块声明的任一下载 URL 归一化后全等
    if (answer.urls.some((u) => normalizeUrl(u)?.full === key.full)) return 1;
    // L2 发布者/域名:github 家族按 repo 路径段(owner/repo)区分,不同 repo 不并;
    // 其余主机 host 相等即同发布面(otx 双记走本支)
    if (GITHUB_FAMILY.has(answer.host)) {
      if (GITHUB_FAMILY.has(key.host) && key.repo && answer.repos.includes(key.repo)) return 2;
    } else if (key.host === answer.host) {
      return 2;
    }
  }
  const norm = normalizeName(cand?.name);
  if (!norm) return null;
  // L3 名字归一化;L4 别名表(人工裁决入条)
  if (norm === answer.normName) return 3;
  if (answer.aliasNames.includes(norm)) return 4;
  return null;
}

// ── 评分与报表 ──

// 逐考题源找最佳命中:层号优先(1 完整 URL > 2 发布者 > 3 名字 > 4 别名),同层取最早候选;
// 需要渠道分栏时看全部命中候选(任一命中候选 source_channel=needs 即计「靠 NEEDS 提示找到」,
// 票面口径:候选 source_channel=needs 且被 NEEDS 行点名者标前者,其余为纯 web)。
// 表外新候选 = 未命中任何 roster 源(考题∪免考)的候选;命中免考源的候选不入新候选,留痕免考栏。
function bestMatch(answer, candidates) {
  let best = null; // {layer, idx}
  const matchedIdx = [];
  candidates.forEach((c, idx) => {
    const layer = matchLayer(answer, c);
    if (layer == null) return;
    matchedIdx.push(idx);
    if (!best || layer < best.layer) best = { layer, idx }; // 同层不抢先:取最早候选
  });
  return { best, matchedIdx };
}

export function scoreRound(table, candidates) {
  const found = [];
  const unfound = [];
  let needsAssisted = 0;
  let pureWeb = 0;
  const byCat = new Map(CATEGORY_ORDER.map((c) => [c, { category: c, found: 0, total: 0 }]));
  for (const a of table.exam) {
    const cat = byCat.get(a.category);
    if (cat) cat.total += 1;
    const { best, matchedIdx } = bestMatch(a, candidates);
    if (!best) {
      unfound.push({ name: a.name, host: a.host });
      continue;
    }
    const via = candidates[best.idx];
    const needs = matchedIdx.some((i) => candidates[i].source_channel === "needs");
    if (needs) needsAssisted += 1;
    else pureWeb += 1;
    if (cat) cat.found += 1;
    found.push({ answer: a.name, layer: best.layer, via: { name: via.name, url: via.url ?? null, source_channel: via.source_channel ?? null } });
  }
  // 表外新候选:考题与免考源都未命中的候选
  const exemptHits = [];
  const newCandidates = [];
  candidates.forEach((c, idx) => {
    const hitExam = table.exam.some((a) => matchLayer(a, c) != null);
    const hitExempt = table.exempt.find((a) => matchLayer(a, c) != null);
    if (hitExam) return;
    if (hitExempt) {
      exemptHits.push({ name: c.name, url: c.url ?? null, source_channel: c.source_channel ?? null, hit: hitExempt.name });
      return;
    }
    newCandidates.push({ name: c.name, url: c.url ?? null, note: String(c.notes ?? "").replace(/\s+/g, " ").trim() });
  });
  const total = table.exam.length;
  const foundN = found.length;
  return {
    rosterTotal: table.rosterTotal,
    examCount: total,
    exemptCount: table.exempt.length,
    recall: { found: foundN, total, pct: total ? Math.round((foundN / total) * 10000) / 100 : 0 },
    byCategory: CATEGORY_ORDER.map((c) => byCat.get(c)),
    byChannel: { needsAssisted, pureWeb },
    exempt: table.exempt.map((a) => a.name),
    exemptHits,
    found,
    unfound,
    newCandidates,
  };
}

export function renderMarkdown(r) {
  // 表格单元格内的 | 转义(评审 P2-3):候选名/URL/备注可能带竖线,不转会拆列
  const esc = (s) => String(s ?? "").replaceAll("|", "\\|");
  const lines = [];
  lines.push(`# 重发现基准打分报告`);
  lines.push("");
  lines.push(`## 总召回`);
  lines.push(`${r.recall.found}/${r.recall.total}(${r.recall.pct.toFixed(2)}%)`);
  lines.push("");
  lines.push(`## 按 category`);
  for (const c of r.byCategory) lines.push(`- ${c.category}: ${c.found}/${c.total}`);
  lines.push("");
  lines.push(`## 靠 NEEDS 提示 vs 纯 web`);
  lines.push(`- 靠 NEEDS 提示:${r.byChannel.needsAssisted}`);
  lines.push(`- 纯 web:${r.byChannel.pureWeb}`);
  lines.push("");
  lines.push(`## 免考(${r.exemptCount},不入分母)`);
  if (r.exempt.length) for (const n of r.exempt) lines.push(`- ${n}`);
  else lines.push("- (无)");
  if (r.exemptHits.length) {
    lines.push("");
    lines.push(`命中免考源的候选(${r.exemptHits.length};不入召回,仅留痕):`);
    for (const h of r.exemptHits) lines.push(`- ${h.name} → ${h.hit}(${h.url ?? "无 URL"})`);
  }
  lines.push("");
  lines.push(`## 命中明细`);
  lines.push(`| 源 | 层 | 命中候选 | 渠道 |`);
  lines.push(`| --- | --- | --- | --- |`);
  for (const f of r.found) lines.push(`| ${esc(f.answer)} | L${f.layer} | ${esc(f.via.name)} | ${esc(f.via.source_channel ?? "-")} |`);
  lines.push("");
  lines.push(`## 表外新候选(${r.newCandidates.length})`);
  if (r.newCandidates.length) {
    lines.push(`| 名 | URL | 一句 |`);
    lines.push(`| --- | --- | --- |`);
    for (const c of r.newCandidates) lines.push(`| ${esc(c.name)} | ${esc(c.url ?? "-")} | ${esc(c.note || "-")} |`);
  } else {
    lines.push("- (无)");
  }
  lines.push("");
  lines.push(`## 未搜到(${r.unfound.length})`);
  if (r.unfound.length) for (const u of r.unfound) lines.push(`- ${u.name}(${u.host})`);
  else lines.push("- (无)");
  lines.push("");
  return lines.join("\n");
}

// 工件目录打分入口:读 <dir>/d2-shortlist.json(candidates 数组,七键形状契约)→
// 同目录写 report.md + report.json。确定性门:不写时间戳/环境信息,同输入字节级同产出。
export function runScoring(artifactsDir, { rosterText, urlDumpJson, examRules, aliases }) {
  const d2Path = path.join(artifactsDir, D2_SHORTLIST);
  if (!fs.existsSync(d2Path)) throw new Error(`工件目录缺 ${D2_SHORTLIST}:${d2Path}`);
  let d2;
  try {
    d2 = JSON.parse(fs.readFileSync(d2Path, "utf8"));
  } catch (e) {
    throw new Error(`${D2_SHORTLIST} 不是合法 JSON:${e.message}`);
  }
  if (!Array.isArray(d2?.candidates)) throw new Error(`${D2_SHORTLIST} 缺 candidates 数组(形状契约 = d2-shortlist.json 的 candidates)`);
  const table = buildAnswerTable({ rosterText, urlDumpJson, examRules, aliases });
  const result = scoreRound(table, d2.candidates);
  const report = { round: path.basename(path.resolve(artifactsDir)), ...result };
  fs.writeFileSync(path.join(artifactsDir, "report.json"), JSON.stringify(report, null, 2) + "\n");
  fs.writeFileSync(path.join(artifactsDir, "report.md"), renderMarkdown(result));
  return report;
}

// ── CLI:答案表机械派生 + 入口 ──

// 源模块声明的下载 URL 机械 dump(答案表第二取数面,规格 Q12;与 roster 同源 import,禁手工清单):
// 每源取 url 类属性 + 模块源文本中 hostname 与本源 download host 一致的 http(s) 字面量
// (多端点源 url 为空串、真实地址在模块常量里,如 firehol 的 _BASE_URL)。host 口径与 roster() 逐字同。
const DUMP_URLS_SCRIPT = `
import inspect, json, re, sys
from urllib.parse import urlparse
from ipdb import _registry
GITHUB = {"github.com", "raw.githubusercontent.com"}
def same_host(lit, host):
    if lit == host:
        return True
    return host in GITHUB and lit in GITHUB
out = {}
for s in _registry._sources:
    cls = s if isinstance(s, type) else type(s)
    try:
        src = inspect.getsource(sys.modules[cls.__module__])
    except Exception:
        src = ""
    url = getattr(s, "url", None) or ""
    urls = [url] if isinstance(url, str) and url else []
    host = getattr(s, "download_host", None) or (urlparse(url).hostname if url else None) or "-"
    for lit in re.findall(r"https?://[A-Za-z0-9._~:/?#\\[\\]@!$&'()*+,;=%-]+", src):
        try:
            lh = urlparse(lit).hostname
        except Exception:
            continue
        if lh and same_host(lh, host):
            urls.append(lit)
    out[s.name] = {"host": host, "urls": sorted(set(urls))}
print(json.dumps(out))
`;

export function deriveInputs({ python, backend }) {
  const rosterText = execFileSync(python, ["-m", "ipdb._registry", "--roster"], { cwd: backend, encoding: "utf8" });
  const urlDumpJson = execFileSync(python, ["-c", DUMP_URLS_SCRIPT], { cwd: backend, encoding: "utf8" });
  return { rosterText, urlDumpJson };
}

function resolvePython(flagged) {
  if (flagged) return flagged;
  if (process.env.BENCH_PYTHON) return process.env.BENCH_PYTHON;
  // worktree 判例(AGENTS.md):worktree 无 venv,用主检出解释器绝对路径 + cwd=worktree backend/
  return "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
}

function resolveBackend(flagged) {
  if (flagged) return flagged;
  if (process.env.BENCH_BACKEND) return process.env.BENCH_BACKEND;
  return path.resolve(BENCH_DIR, "..", "..", "..", "backend");
}

export function main(argv = process.argv.slice(2)) {
  const { values, positionals } = parseArgs({
    args: argv,
    options: {
      python: { type: "string" },
      backend: { type: "string" },
    },
    allowPositionals: true,
  });
  const dir = positionals[0];
  if (!dir) {
    console.error("用法:node score.mjs <工件目录> [--python 解释器] [--backend backend目录]");
    process.exit(2);
  }
  const python = resolvePython(values.python);
  const backend = resolveBackend(values.backend);
  const examRules = JSON.parse(fs.readFileSync(path.join(BENCH_DIR, "exam-rules.json"), "utf8"));
  const aliases = JSON.parse(fs.readFileSync(path.join(BENCH_DIR, "aliases.json"), "utf8"));
  const { rosterText, urlDumpJson } = deriveInputs({ python, backend });
  const report = runScoring(dir, { rosterText, urlDumpJson, examRules, aliases });
  console.log(`总召回 ${report.recall.found}/${report.recall.total}(${report.recall.pct}%) · 未搜到 ${report.unfound.length} · 表外新候选 ${report.newCandidates.length} · 报告 → ${path.join(dir, "report.md")}`);
  return report;
}

// 直接执行时跑 CLI;被 import 时(测试)不跑。
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (e) {
    console.error(String(e?.message ?? e));
    process.exit(1);
  }
}
