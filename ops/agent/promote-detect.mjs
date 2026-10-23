#!/usr/bin/env node
// promote-detect.mjs — 判例升格通道检测器(B 稿 §3.2 升格候选确定性规则;P2,票 #164,仅立项)。
// 同因人裁留痕 ≥2 且 ruling_agreement 一致 → retro/promotion-candidates/ 候选文件;
// 同因 = 键并集union(文本归一键全等 ∨ 源身份词相交,B 稿「同 (source, cause_group)」);
// 三门槛(可机检/可证伪/非环境特异性)在候选里以 pending 门待人裁逐项核——
// 人裁采纳(adopt_rule 四键通道,P5)才升格为概念判例;本检测器永不写判例区(判例 0db230187f:永不自动执行)。
// 用法:node ops/agent/promote-detect.mjs [--docs-root DIR] [--out DIR] [--dry]
//   判例目录缺省 = $PRECEDENTS_DIR ?? <docs-root>/ops/precedents;候选目录缺省 = <docs-root>/ops/retro/promotion-candidates。
//   --dry:只打印不写盘(报告/巡检面)。幂等:同因候选已存在 → 跳过(append-only,不改写)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(AGENT_DIR, "..", "..");

export const PROMOTION_GATES = [ // 三门槛(票 #164;verdict=pending 起步,人裁逐项核)
  { id: "machine_checkable", question: "可机检:该因可转确定性检查(抑制规则/阶段门/探测器)?" },
  { id: "falsifiable", question: "可证伪:判例主张带可算反例面(换读数即翻案)?" },
  { id: "non_env_specific", question: "非环境特异:结论不依赖本机/本部署环境(换环境仍成立)?" },
];

// 留痕判例 frontmatter 解析(write_ruling 冻结面:id/date/subject/recommendation/human_ruling/reward/lineage)
export function parseRuling(text) {
  const fm = text.split(/^---\s*$/m)[1] ?? "";
  const val = (k) => { const m = fm.match(new RegExp(`^${k}:[ \\t]*(.*)$`, "m")); return m ? m[1].trim().replace(/^["']|["']$/g, "") : null; };
  const agreement = (fm.match(/^  ruling_agreement:[ \t]*(\S+)/m) ?? [])[1] ?? null;
  const sup = val("superseded_by");
  return { id: val("id"), date: val("date"), subject: val("subject"), recommendation: val("recommendation"),
    ruling_agreement: agreement, superseded_by: sup && sup !== "null" ? sup : null };
}

// 文本归一键:URL→host(路径是定位非因)→摘括注(条目 id/理由=模板变量)→截分号附录
// →数字折叠(n;天数/计数随轮变)→压空白小写。
export function causeKey(recommendation) {
  return String(recommendation ?? "")
    .replace(/https?:\/\/([^/\s]+)\S*/g, "$1")
    .replace(/\([^)]*\)/g, "")
    .replace(/;.*$/s, "")
    .replace(/\d+/g, "n")
    .replace(/\s+/g, " ")
    .trim().toLowerCase();
}

// 源身份词:归一文本里 host 首标(urlhaus.abuse.ch→urlhaus)+ 独立源名词([a-z0-9_-]≥4,剔噪声词)。
const SRC_STOP = new Set(["retry", "download", "retry_download", "last", "modified", "http", "https", "www", "com", "gmt",
  "csv", "online", "downloads", "exports", "unreachable"]);
export function sourceTokens(recommendation) {
  const norm = causeKey(recommendation);
  const toks = new Set();
  for (const h of norm.match(/[a-z0-9][a-z0-9.-]*\.[a-z]{2,}/g) ?? []) {
    const label = h.split(".")[0].replace(/^[-_]+|[-_]+$/g, "");
    if (label.length >= 4 && !SRC_STOP.has(label)) toks.add(label);
  }
  for (const t of norm.match(/[a-z0-9_-]{4,}/g) ?? []) {
    if (!SRC_STOP.has(t) && !/^n+$/.test(t)) toks.add(t.replace(/^[-_]+|[-_]+$/g, ""));
  }
  return [...toks].filter(Boolean);
}

// 检测:live(superseded 链上被取代者不计数——谱系回声,哲学③宁少算)→ 键并集 union 成组
// → ≥2 且 ruling_agreement 一致 → 候选。纯函数。
export function detectCandidates(rulings, minN = 2) {
  const live = rulings.filter((r) => !r.superseded_by);
  const keysOf = (r) => [`text:${causeKey(r.recommendation)}`, ...sourceTokens(r.recommendation).map((t) => `src:${t}`)];
  const parent = live.map((_, i) => i);
  const find = (i) => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  const union = (a, b) => { parent[find(a)] = find(b); };
  const byKey = new Map();
  live.forEach((r, i) => {
    for (const k of keysOf(r)) {
      if (byKey.has(k)) union(byKey.get(k), i);
      else byKey.set(k, i);
    }
  });
  const groups = new Map();
  live.forEach((r, i) => {
    const root = find(i);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(r);
  });
  const out = [];
  for (const rs of groups.values()) {
    if (rs.length < minN) continue;
    const agreements = new Set(rs.map((r) => r.ruling_agreement));
    if (agreements.size !== 1) continue; // 人裁一致才立项(B 稿 §3.2;不一致=判例未稳)
    const shared = rs[0] && rs.length > 1
      ? sourceTokens(rs[0].recommendation).find((t) => rs.slice(1).some((r) => sourceTokens(r.recommendation).includes(t)))
      : null;
    out.push({ cause_key: shared ? `同源:${shared}` : `同文:${causeKey(rs[0].recommendation)}`,
      rulings: rs.map((r) => r.name).sort(), ruling_agreement: [...agreements][0] });
  }
  return out.sort((a, b) => a.cause_key.localeCompare(b.cause_key));
}

export function candidateText(c, generatedAt) {
  return JSON.stringify({
    schema: 1,
    status: "proposed", // 仅立项:人裁采纳(adopt_rule)才入概念判例;检测器永不写判例区
    generated_at: generatedAt,
    cause_key: c.cause_key,
    rulings: c.rulings,
    ruling_agreement: c.ruling_agreement,
    gates: PROMOTION_GATES.map((g) => ({ ...g, verdict: "pending" })),
    note: "同因人裁留痕≥2 且一致 → 升格候选(仅立项)。三门槛待人裁逐项核;采纳走 adopt_rule 人裁通道(P5 闭环),概念判例 lineage 必列本候选 rulings(谱系可回算)。",
  }, null, 2) + "\n";
}

const slug = (s) => s.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "cause";

function main() {
  const args = process.argv.slice(2);
  const flag = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
  const docsRoot = path.resolve(flag("--docs-root") ?? process.env.DOCS_ROOT ?? path.join(ROOT, "docs"));
  const precDir = process.env.PRECEDENTS_DIR ?? path.join(docsRoot, "ops", "precedents");
  const outDir = path.resolve(flag("--out") ?? path.join(docsRoot, "ops", "retro", "promotion-candidates"));
  const dry = args.includes("--dry");
  if (!fs.existsSync(precDir)) { console.error(`判例目录缺:${precDir}`); process.exit(2); }
  const rulings = fs.readdirSync(precDir).filter((f) => /^[\d-]+-ruling-.*\.md$/.test(f)).sort()
    .map((name) => ({ name, ...parseRuling(fs.readFileSync(path.join(precDir, name), "utf8")) }));
  const cands = detectCandidates(rulings);
  for (const c of cands) console.log(`CANDIDATE [${c.ruling_agreement}] ${c.cause_key} ← ${c.rulings.join(", ")}`);
  if (dry || !cands.length) {
    console.log(`promote-detect: 留痕 ${rulings.length} 条(live ${rulings.filter((r) => !r.superseded_by).length})→ 候选 ${cands.length}${dry ? "(dry)" : ""}`);
    return;
  }
  fs.mkdirSync(outDir, { recursive: true });
  const today = new Date().toISOString().slice(0, 10);
  let wrote = 0, kept = 0;
  for (const c of cands) {
    const p = path.join(outDir, `${today}-${slug(c.cause_key)}.json`);
    if (fs.existsSync(p)) { kept += 1; continue; } // 幂等:不改写既有候选(append-only)
    fs.writeFileSync(p, candidateText(c, new Date().toISOString()));
    console.log(`CANDIDATE-WROTE ${path.relative(docsRoot, p)}`);
    wrote += 1;
  }
  console.log(`promote-detect: 留痕 ${rulings.length} 条(live ${rulings.filter((r) => !r.superseded_by).length})→ 候选 ${cands.length}(新写 ${wrote},幂等保留 ${kept})`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
