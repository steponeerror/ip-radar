#!/usr/bin/env node
// gen-exam-cards.mjs — 加源重实现基准考题卡预填生成器(票 #334 交付面 2;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议「考题卡预填生成」)。
//
// 语义:从宇宙行 + 真源实抓样本生成交接单形考题卡(name/url/samples 3-5 行/format/
// auth/cadence/field_routing)——样本在**构建考题时抓一次冻结进卡**,trial 内不联网
// 抓样本(spec 原话);卡的形状门 = dossierShape(tasks/add-round.mjs 单源,与轮
// DOSSIER 相位同门,禁第二份形状清单);卡名 = 宇宙行名(stem 契约:slugify(name)
// ===题名,打分器 test_<name>.py 钥匙面才对得上)。
//
// 端点覆写表(#331 已记人裁点,生成器不替用户裁):宇宙行内多端点源(url 为仓库/
// 目录前缀形)的真实端点在源文件 _BASE 常量——P3 真跑前用户裁「补端点 or 起点
// 语义」。故 url 解析做成可配:--endpoints JSON({题名: url})优先;未覆写时前缀形
// (尾斜杠)→ endpoint_pending=true 点名进 _provenance,照常出卡,裁决留给 P3。
//
// 产物 = 答案面工件(含考题名+URL):落 --out-dir(缺省 <仓根>/dev/bench-add-domain/
// cards,dev/ 不入仓,文件放置规范);每题一件 <name>.json。roster 取数 = loadRosterText
// 单源(leak-check 同面);meta dump = gen-universe DUMP_META_SCRIPT 单源(stale_days
// 供 cadence 派生)。
//
// 用法:
//   node gen-exam-cards.mjs [--universe PATH] [--roster-file PATH] [--meta-file PATH]
//                           [--endpoints PATH] [--only 名,名,...] [--out-dir DIR]
//                           [--python BIN] [--timeout-ms 30000]
// 退出码:0=全绿;1=有题失败(部分卡已落盘保真,逐题报错);2=用法/取数失败。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { parseRoster } from "../roster.mjs";
import { loadRosterText } from "../leak-check.mjs";
import { DUMP_META_SCRIPT } from "./gen-universe.mjs";
import { loadUniverse } from "./score.mjs";
// 加载序锚(循环导入面纪律,同 tests/add-round.test.mjs 导入序):tasks/add-round.mjs
// ↔ run-add.mjs ↔ registry.mjs ↔ tasks/index.mjs 有环;先拉 run-add 侧再拉 add-round,
// 环从 run-add 面解(与 P1 测试/启动器同序)。倒序会在 index.mjs 聚合表撞 addRoundTask TDZ。
import "../../run-add.mjs";
import { dossierShape, slugify } from "../../tasks/add-round.mjs";

const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // add-domain → 仓根(4 层)
const SAMPLE_LINE_CAP = 300; // 卡内样本行封顶(交接单可读性;嗅探在截断前做)

// ── 纯函数面(导出=测试单源面)──────────────────────────────────────────

// 实抓样本取行:非空行取前 5(封顶);注释行(# / ; / //)优先跳——交接单样本要展示
// 数据面形状,纯注释前 5 行对实现无用;非注释行不足 3 时回退含注释原始行(宁可如实
// 也不造);仍不足 3 返回空集(调用方红——无样本即无卡)。
export function pickSamples(text) {
  const lines = String(text ?? "").split("\n").map((l) => l.replace(/\r$/, "").trim()).filter(Boolean);
  const data = lines.filter((l) => !/^[#;]|^\/\//.test(l));
  const pick = data.length >= 3 ? data : lines;
  return pick.length >= 3 ? pick.slice(0, 5) : [];
}

// 格式嗅探(草案级,交接单 format 面;判定序:json → ip 列表 → tsv → csv → text)
export function sniffFormat(lines) {
  const ls = (lines ?? []).filter(Boolean);
  if (!ls.length) return "text";
  if (/^\s*[[{]/.test(ls[0])) return "json";
  const ipRe = /^\d{1,3}(\.\d{1,3}){3}(\/\d{1,2})?$/;
  if (ls.every((l) => ipRe.test(l.trim()))) return "plain-ip-list";
  if (ls[0].includes("\t") && !ls[0].includes(",")) return "tsv";
  if (ls[0].includes(",")) return "csv";
  return "text";
}

// cadence 派生(源元数据 stale_days → 人话档位;无声明=如实未知,不编)
export function cadenceOf(staleDays) {
  if (typeof staleDays !== "number" || !Number.isFinite(staleDays)) return "未知(源元数据无 stale_days 声明)";
  if (staleDays <= 1) return `daily(源元数据 stale_days=${staleDays})`;
  if (staleDays <= 7) return `weekly 级(源元数据 stale_days=${staleDays})`;
  return `低频/静态(源元数据 stale_days=${staleDays})`;
}

// 字段路由草案(roster fields 面 → 路由行草案;ip 面 → rebuild 键,语义字段 →
// 分类/属性面;子列信号并入草案行——生产里这是人写的草案,生成器产机械可核的等价物)
export function routingDraftOf(fields, category) {
  const f = (fields ?? []).filter(Boolean);
  const lines = [];
  if (f.includes("ip") || !f.length) lines.push("行内 IP/CIDR → rebuild 键(cidr)");
  for (const x of f.filter((y) => y !== "ip")) lines.push(`${x} → ${category} 字段/分类词汇面(草案)`);
  if (!lines.length) lines.push("样本行语义 → 路由草案(交接单人裁)");
  return lines;
}

// 端点面解析(覆写表优先;前缀形未覆写=pending 点名,不替人裁)。pending 判据 = 尾斜杠
// 前缀形(仓库/目录页,不可直接下载)——#331 人裁点正是这一面;完整端点的多 URL 源
// 不 pending(卡钉宇宙行 URL 即可考,无需裁决)。真仓实测前缀面 = 10 题(spec 勘误
// 段列 6,机械判据面更宽,以判据为准)。
export function endpointFace({ row, metaEntry, endpoints }) {
  void metaEntry; // 判据单源 = 尾斜杠前缀形;meta urls 多端面不参与 pending 判定
  const override = endpoints?.[row.name];
  if (typeof override === "string" && override.trim())
    return { url: override.trim(), endpoint_pending: false, endpoint_note: `端点已覆写:endpoints 表(${row.name})` };
  if (/\/$/.test(row.url ?? ""))
    return {
      url: row.url,
      endpoint_pending: true,
      endpoint_note: "前缀 URL(仓库/目录页)未覆写——P3 真跑前须人裁「补端点 or 起点语义」(#331 记账)",
    };
  return { url: row.url, endpoint_pending: false, endpoint_note: null };
}

// 单卡构建:宇宙行 + roster 面 + meta 面 + 实抓文本 → 交接单形卡(+_provenance 冻结面)
export function buildCard({ row, rosterEntry, metaEntry, sampleText, endpoints, fetchedAt }) {
  if (!row?.name) throw new Error("宇宙行缺 name");
  if (slugify(row.name) !== row.name)
    throw new Error(`stem 契约红:宇宙行名 ${row.name} 非 slug 形(slugify≠自身;打分器钥匙面 test_<name>.py 对不上)`);
  if (!rosterEntry) throw new Error(`${row.name}:roster 缺行(宇宙与 roster 分叉,须人裁)`);
  if (!metaEntry) throw new Error(`${row.name}:meta dump 缺行(dump 单源纪律,须人裁)`);
  const raw = pickSamples(sampleText);
  if (!raw.length) throw new Error(`${row.name}:样本不足 3 行实抓(无样本即无卡,fail-closed)`);
  const ep = endpointFace({ row, metaEntry, endpoints });
  const card = {
    name: row.name,
    url: ep.url,
    samples: raw.map((l) => (l.length > SAMPLE_LINE_CAP ? `${l.slice(0, SAMPLE_LINE_CAP)}…` : l)),
    format: sniffFormat(raw),
    auth: "none", // 宇宙面无 auth env 读(gen-universe keyless 反扫钉死;有 key 源不入宇宙)
    cadence: cadenceOf(metaEntry.stale_days),
    field_routing: routingDraftOf(rosterEntry.fields, rosterEntry.category),
    _provenance: {
      fetched_at: fetchedAt,
      endpoint_override: endpoints?.[row.name] !== undefined,
      endpoint_pending: ep.endpoint_pending,
      endpoint_note: ep.endpoint_note,
      universe_split: row.split,
      source_stale_days: metaEntry.stale_days ?? null,
      roster_fields: rosterEntry.fields,
      note: "样本构建考题时抓一次冻结进卡;trial 内不联网抓样本(spec §重实现基准协议)",
    },
  };
  const shape = dossierShape(card); // 与轮 DOSSIER 相位同门(单源形状律)
  if (!shape.ok) throw new Error(`${row.name}:生成卡形状坏:${shape.reason}`);
  return card;
}

// ── 程序面(CLI 与测试共用)────────────────────────────────────────────
// fetchImpl 缝:测试注入 stub(零网络);缺省 = 真 fetch(构建考题时抓一次,非 trial 面)。
export async function genExamCards({ universePath, rosterText, metaDump, endpoints = {}, fetchImpl, outDir, only = [], timeoutMs = 30000, nowIso }) {
  const rows = loadUniverse(universePath); // frozen 闸 + 行序(沙箱/打分器同律)
  const roster = parseRoster(rosterText);
  const fetchText = fetchImpl ?? (async (url) => {
    const res = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(timeoutMs), headers: { "user-agent": "ipradar-add-bench/1.0" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}(fetch ${url})`);
    return res.text();
  });
  fs.mkdirSync(outDir, { recursive: true });
  const written = [];
  const failed = [];
  const fetchedAt = nowIso ?? new Date().toISOString();
  for (const row of rows) {
    if (only.length && !only.includes(row.name)) continue;
    try {
      const card = buildCard({
        row,
        rosterEntry: roster.find((r) => r.name === row.name) ?? null,
        metaEntry: metaDump[row.name] ?? null,
        sampleText: await fetchText(row && (endpoints?.[row.name] ?? row.url)),
        endpoints,
        fetchedAt,
      });
      fs.writeFileSync(path.join(outDir, `${row.name}.json`), JSON.stringify(card, null, 2) + "\n");
      written.push(row.name);
    } catch (e) {
      failed.push({ name: row.name, error: String(e?.message ?? e) }); // 逐题红记账:好卡照写,坏题留名
    }
  }
  return { written, failed, outDir };
}

// ── CLI ──
function parseArgs(argv) {
  const out = { universe: null, rosterFile: null, metaFile: null, endpoints: null, only: null, outDir: null, python: null, timeoutMs: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--universe") out.universe = next();
    else if (a === "--roster-file") out.rosterFile = next();
    else if (a === "--meta-file") out.metaFile = next();
    else if (a === "--endpoints") out.endpoints = next();
    else if (a === "--only") out.only = next().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--out-dir") out.outDir = next();
    else if (a === "--python") out.python = next();
    else if (a === "--timeout-ms") out.timeoutMs = Number(next());
    else if (a === "--help" || a === "-h") out.help = true;
    else { console.error(`未知参数:${a}`); process.exit(2); }
  }
  return out;
}

function resolvePython(flagged) {
  if (flagged) return flagged;
  if (process.env.BENCH_PYTHON) return process.env.BENCH_PYTHON;
  return "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python"; // worktree 律(AGENTS.md;build-sandbox 同款)
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) {
    console.error("用法:node gen-exam-cards.mjs [--universe PATH] [--roster-file PATH] [--meta-file PATH] [--endpoints PATH] [--only 名,名,...] [--out-dir DIR] [--python BIN] [--timeout-ms 30000]");
    return 0;
  }
  const python = resolvePython(args.python);
  const backend = path.join(ROOT, "backend");
  const rosterText = args.rosterFile
    ? fs.readFileSync(path.resolve(args.rosterFile), "utf8")
    : loadRosterText({ pythonBin: python });
  const metaDump = args.metaFile
    ? JSON.parse(fs.readFileSync(path.resolve(args.metaFile), "utf8"))
    : JSON.parse(execFileSync(python, ["-c", DUMP_META_SCRIPT], { cwd: backend, encoding: "utf8" }));
  const endpoints = args.endpoints ? JSON.parse(fs.readFileSync(path.resolve(args.endpoints), "utf8")) : {};
  const universePath = args.universe ?? path.join(import.meta.dirname, "data", "universe.jsonl");
  const outDir = args.outDir ? path.resolve(args.outDir) : path.join(ROOT, "dev", "bench-add-domain", "cards");
  const r = await genExamCards({
    universePath, rosterText, metaDump, endpoints, outDir,
    only: args.only ?? [], timeoutMs: args.timeoutMs ?? 30000,
  });
  for (const f of r.failed) console.error(`✋ ${f.name}: ${f.error}`);
  console.log(`考题卡:写 ${r.written.length} 件 → ${r.outDir}${r.failed.length ? `;失败 ${r.failed.length} 件(见上)` : ""}`);
  return r.failed.length ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  process.exit(await main());
}
