#!/usr/bin/env node
// gen-split.mjs — RRSI 劈分生成器(票 #325;裁决 #322 R1:53 考题劈 40 演化/13 留出)。
// 产物 data/split.jsonl 生成后【人工检查 + 手改 meta.frozen=true】入仓——冻结件是答案分发
// 面,此后名单漂移由 tests/rrsi-split.test.mjs 不变式红报警(roster 演进 → 重新裁决再生成,
// 禁静默重跑覆盖)。
//
// 规则(spec:类别分层、固定种子、名单钉死):
//   1. roster dump × exam-rules.json 免考面 → 考题宇宙(票面 61−8=53);
//   2. 最大余数法把 heldout 名额分到类别:每类 floor(n_c·H/N),余席位按余数降序,
//      余数并列按类别字典序(全确定性);
//   3. 类内 mulberry32(seed) 洗牌取前 h_c 进留出集;RNG 消费序 = 类别字典序 × 名字字典序;
//   4. 输出 JSONL:meta 行 + 每名一行 {set,name,category,host};名字行带行级豁免标记
//      「禁词引用:#308 判例——答案键载体」,leak 闸与 pre-commit 钩子同款放行。
//
// 确定性:同种子同输入 → 字节级同输出(无时间戳/无随机路径序);tests 双跑比对钉住。
// 用法(只在 ip-radar 仓内跑——拷进 RRSI domains/ 后无 ../exam-rules.json 邻接,缺省路径断):
//   node gen-split.mjs --roster-file <dump> [--exam-rules PATH] [--out PATH]
//                      [--evolve 40] [--heldout 13] [--seed 20261108]
import fs from "node:fs";
import path from "node:path";
import { parseRoster } from "../roster.mjs";
import { largestRemainder } from "./split-lib.mjs"; // #325 F2:分席算法单源(split-lib.mjs,与测试共用)

const DEFAULT_SEED = 20261108;

function parseArgs(argv) {
  const out = { rosterFile: null, examRules: null, out: null, evolve: 40, heldout: 13, seed: DEFAULT_SEED };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--roster-file") out.rosterFile = next();
    else if (a === "--exam-rules") out.examRules = next();
    else if (a === "--out") out.out = next();
    else if (a === "--evolve") out.evolve = Number(next());
    else if (a === "--heldout") out.heldout = Number(next());
    else if (a === "--seed") out.seed = Number(next());
    else if (a === "--help" || a === "-h") { out.help = true; }
    else { console.error(`未知参数:${a}`); process.exit(2); }
  }
  if (out.help || !out.rosterFile) {
    console.error("用法:node gen-split.mjs --roster-file <dump> [--exam-rules PATH] [--out PATH] [--evolve 40] [--heldout 13] [--seed 20261108]");
    process.exit(out.help ? 0 : 2);
  }
  return out;
}

// mulberry32:跨 node 版稳定的 32 位 PRNG(仅用 >>>/Math.imul,无浮点路径分叉)
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Fisher–Yates(向后洗牌,rng 注入可测)
function shuffled(arr, rng) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// 最大余数法分席:已迁 split-lib.mjs(#325 F2 抽出单源,gen-split 与 rrsi-split 测试共用)

const args = parseArgs(process.argv.slice(2));
const examRules = JSON.parse(fs.readFileSync(args.examRules ?? path.join(import.meta.dirname, "..", "exam-rules.json"), "utf8"));
const roster = parseRoster(fs.readFileSync(args.rosterFile, "utf8"));

// 免考面单源 = exam-rules.json exempt[].name;交叉断言其判据(download_host='-')成立
const exemptNames = new Set((examRules.exempt ?? []).map((e) => e.name));
for (const r of roster) {
  if (exemptNames.has(r.name) && r.host !== "-") {
    throw new Error(`免考判据漂移:${r.name} 在 exam-rules 免考面但 download_host='${r.host}'≠'-'`);
  }
}
const exam = roster.filter((r) => !exemptNames.has(r.name));
if (exam.length !== args.evolve + args.heldout) {
  throw new Error(`考题宇宙 ${exam.length} ≠ evolve+heldout ${args.evolve + args.heldout}——roster 演进须重裁,禁静默重劈`);
}

// 类别分层(类别序、类内名字序均字典序 = RNG 消费序钉死)
const byCat = new Map();
for (const r of exam) {
  if (!byCat.has(r.category)) byCat.set(r.category, []);
  byCat.get(r.category).push(r);
}
for (const list of byCat.values()) list.sort((x, y) => (x.name < y.name ? -1 : 1));
const heldSeats = largestRemainder(Object.fromEntries([...byCat].map(([c, l]) => [c, l.length])), args.heldout);

const rng = mulberry32(args.seed);
const heldout = new Map(); // name → category
for (const cat of [...byCat.keys()].sort()) {
  const picked = shuffled(byCat.get(cat).map((r) => r.name), rng).slice(0, heldSeats.get(cat));
  for (const name of picked) heldout.set(name, cat);
}

const rows = [
  ...exam.filter((r) => heldout.has(r.name)).map((r) => ({ set: "heldout", name: r.name, category: r.category, host: r.host })),
  ...exam.filter((r) => !heldout.has(r.name)).map((r) => ({ set: "evolve", name: r.name, category: r.category, host: r.host })),
].map((r) => ({ ...r, _why: "禁词引用:#308 判例——答案键载体行,行级豁免" }));

const meta = {
  kind: "ipradar-rrsi-split",
  version: 1,
  seed: args.seed,
  rule: "roster×exam-rules 免考面 → 类别分层最大余数法分席 → 类内 mulberry32(seed) 洗牌取留出;类别/名字双字典序为 RNG 消费序",
  total: exam.length,
  evolve: args.evolve,
  heldout: args.heldout,
  heldoutSeats: Object.fromEntries([...heldSeats.entries()].sort(([a], [b]) => (a < b ? -1 : 1))),
  rosterTotal: roster.length,
  exemptTotal: roster.length - exam.length,
  frozen: false, // 生成器只产未冻结件;入仓冻结 = 人工检查后改 true(名单钉死,重劈须重裁)
  ticket: "#325",
};

const outPath = args.out ?? path.join(import.meta.dirname, "data", "split.jsonl");
// 冻结件拒绝覆盖(#325 F2):劈分是答案分发面,已冻结(frozen=true)的名单禁被静默
// 重写——重劈须重走 #322 裁决,先手工把 meta.frozen 改回 false 确认意图。
if (fs.existsSync(outPath)) {
  const head = fs.readFileSync(outPath, "utf8").split("\n")[0];
  let frozenHead = false;
  try { frozenHead = JSON.parse(head).frozen === true; } catch { /* 非法首行当未冻结件放行 */ }
  if (frozenHead) {
    console.error(`拒绝覆盖:${outPath} 是已冻结劈分件(frozen=true)。重劈须重走 #322 裁决——先手工把 meta.frozen 改回 false 再跑。`);
    process.exit(1);
  }
}
const lines = [JSON.stringify(meta), ...rows.map((r) => JSON.stringify(r))];
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, lines.join("\n") + "\n");

const stat = (set) => {
  const m = new Map();
  for (const r of rows) if (r.set === set) m.set(r.category, (m.get(r.category) ?? 0) + 1);
  return Object.fromEntries([...m.entries()].sort(([a], [b]) => (a < b ? -1 : 1)));
};
console.log(`split 写入 ${outPath}`);
console.log(`  heldout=${args.heldout} ${JSON.stringify(stat("heldout"))}`);
console.log(`  evolve=${args.evolve} ${JSON.stringify(stat("evolve"))}`);
console.log(`  frozen=false → 人工检查后改 meta.frozen=true 入仓(名单钉死)`);
