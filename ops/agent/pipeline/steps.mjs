// pipeline/steps.mjs — 脚本步实现 + 模型步装配/收编(C 稿 §1 层一;P0,spec #161)。
// 职责线(DESIGN.md §2):脚本步只测量不判断——分区/装配/收编全是确定性数据变换,判断只在上游模型步与门。
//   PROBE = lib.sh 真执行(extract_feed_urls 只读扫描 + feed_freshness;curl 传输层=PATH 解析,
//           测试以 stub 替身零网络——golden curl_age_days 判例)+ matrix 真扫描(tools.mjs
//           matrixScanCli 单源,OPS_EVAL_PY 求值 CLI,stub 判例同 golden stubs.matrix;P1,#163)。
//   VERIFY = 抑制规则库纯函数分区(留痕抑制:压掉的信号进 suppressed 工件,证据降权不灭失)。
//   RETRO = 台账(lib.sh)+ sandbox_assert 真执行 + retro 候选 JSON(候选只产件,永不自动生效)。
// 模型步装配:modelInput(上下文构造)/modelConsume(收编工件)供 faux.mjs 真 Agent 循环调用;
//   DEEP 逐假设循环是引擎数据循环(本文件只供 items 枚举与收编尾,C 稿 §2.1 注)。
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { FROZEN_DAYS, matrixScanCli, matrixArtifactText, resolveField, anchorSweepCli } from "../tools.mjs";
import { loadAnchors, anchorSelect, HIT_CAP } from "./anchors.mjs"; // 锚域词表×旗标选锚(B 三件②;DISPATCH 逐假设判例命中 ≤3,P4 #166)
import { runFindingExits } from "./finding-exit.mjs"; // #184 finding 出口三件套(gh issue+webhook;RETRO 摘要行在本文件 RETRO)
import * as budget from "./budget.mjs"; // #199 A5:09-budget.json 读数面(零环:budget 只依赖 node 内置)
import { mkBreaker, readBreakerKnobs } from "../tools/breaker.mjs"; // #199 B:breaker 观察快照(只读零写;零环:breaker 只依赖 node 内置+lib.sh)
import { itemSignature, fullDedupKey, createOpsItem, parseItemsTree, CAUSE_GROUP_BY_BUCKET } from "./ops-items.mjs"; // 条目库桥(P4 #166:接 _ops_items 同空间)
import { ARTIFACTS as A, deepArtifactName, deepTranscriptName, DEEP_TRANSCRIPT_RE } from "../artifacts.mjs"; // 工件名表单源(#202 C1):步写出/读面禁手抄工件名(磁盘名字节冻结,位等价判例)
import { appendQueueRowLocked } from "../tools/queue-lock.mjs"; // #139 flock 互锁队列写口(#207 T1 ENQUEUE 消费;与 python 侧 append_queue 同构互锁)
import { scanEvidenceFace } from "./citation.mjs"; // #208 T2:证据面三形解析(透传/工件/URL)→span 级存在性

const execFileP = promisify(execFileCb);
const AGENT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LIBSH = path.join(AGENT_DIR, "lib.sh");
const promptFile = (key) => path.join(AGENT_DIR, "prompts", `${key}.md`); // 提示词层真源(P3,#165;C稿 §3.1)
// DEEP 真提示词 = prompts/health/deep.md(P4 #166,C稿 §3.3 草案+A 一律收窄;装配见 deepInput)
const EST_PER_HYP_CNY = 0.016; // C稿 §7 成本模型上限(每假设 ~0.008-0.016;预算估取上限,宁紧勿松)
const MAX_DEEP_HYPOTHESES = 3; // 深验假设数上限(C稿 §7「上限 3 假设」;超即 severity 截尾留痕,P4 #166)
const SEV_RANK = { high: 0, medium: 1, low: 2 }; // DISPATCH 截尾序:低 severity 先丢
export const RULE_PREDICATES = ["bucket", "url_shape", "source", "error_family"]; // 匹配谓词闭集(C稿 §4.2;新增谓词=spec 变更)
export const RULE_ACTIONS = ["suppress", "annotate"]; // 规则动作闭集(C稿 §4.2)
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const infra = (msg) => Object.assign(new Error(msg), { code: "infra" });
// 台账行标签单源(#207 T1):steps RETRO 写面与 gates G_RETRO 读回检查同源,禁各自手抄
// (health=pipeline 历史名字节冻结;discover=pipeline-discover,票面铸词)。
export const LEDGER_TAGS = { health: "pipeline", discover: "pipeline-discover" };
// review_at 缺省 = 采纳日 +90 天(C稿 §4.2:防规则磨烂成新噪音;RETRO P5 到点报人复审)
const addDaysIso = (iso, n) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

const sh = (fn, args = [], timeoutMs = 600_000, env = process.env) => execFileP("bash",
  ["-c", `. "$0"; ${fn} "$@"`, LIBSH, ...args], { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...env } });

const j = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const writeJson = (p, obj) => fs.writeFileSync(p, JSON.stringify(obj, null, 2) + "\n");
const host = (u) => { try { return new URL(u).hostname; } catch { return u; } };
export const hidSlug = (hid) => String(hid).replace(/[^A-Za-z0-9.-]+/g, "-").replace(/^-+|-+$/g, "");
// dedup 全签 = (source, probe_class, error_signature),与 P1 探测器同空间(_ops_items.dedup_key 语义键);
// 折叠族映射与查表真源 = ops-items.mjs itemSignature(#164 偏离①②收口,P4 #166)。
const dedupKey = (f) => fullDedupKey(f);

// ── 抑制规则库(闭集 schema;C稿 §4.2)──────────────────────────────────────
// 真源 = DOCS_ROOT/ops/rules/suppressions.json(人裁采纳才写入,adopt_rule 四键通道 P5);
// 本函数 = 加载→闭集校验→规范化(review_at 缺省补采纳+90天)的纯函数;坏文件=infra 终态,
// 规则零命中=空集照常过(降级直通)。谓词求值见 ruleMatch(纯函数,规则序即优先级)。
export function normalizeRules(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.rules)) throw infra("抑制规则库不可解析:rules 数组缺");
  const seen = new Set();
  const rules = [];
  for (const r of raw.rules) {
    if (!r || typeof r !== "object") throw infra("规则项非对象");
    for (const k of ["id", "adopted", "adopted_via", "action", "note"])
      if (typeof r[k] !== "string" || !r[k].trim()) throw infra(`规则 ${r.id ?? "?"} 缺字符串字段 ${k}`);
    if (!r.match || typeof r.match !== "object" || Array.isArray(r.match)) throw infra(`规则 ${r.id ?? "?"} match 非对象`);
    if (seen.has(r.id)) throw infra(`规则 id 重复:${r.id}`);
    seen.add(r.id);
    if (!RULE_ACTIONS.includes(r.action)) throw infra(`规则动作闭集外:${r.action}(${r.id})`);
    if (!DATE_RE.test(r.adopted)) throw infra(`规则 adopted 形状非法(YYYY-MM-DD):${r.adopted}(${r.id})`);
    const keys = Object.keys(r.match);
    if (!keys.length) throw infra(`规则 match 空(${r.id};谓词闭集 ${RULE_PREDICATES.join("/")})`);
    for (const k of keys) if (!RULE_PREDICATES.includes(k)) throw infra(`抑制规则谓词闭集外:${k}(${r.id})`);
    if (r.review_at !== undefined && !DATE_RE.test(r.review_at)) throw infra(`规则 review_at 形状非法(YYYY-MM-DD):${r.review_at}(${r.id})`);
    rules.push({ id: r.id, adopted: r.adopted, adopted_via: r.adopted_via, match: r.match, action: r.action, note: r.note,
      review_at: r.review_at ?? addDaysIso(r.adopted, 90) });
  }
  return { version: typeof raw.version === "number" ? raw.version : 0, rules };
}

export function readInFlightItems(itemsDir, excludeRoundId = null) {
  return parseItemsTree(itemsDir)
    .filter((it) => !excludeRoundId || it.round_id !== excludeRoundId) // 无 replay 面不过滤(backend 产件无 round_id,不能被 null==null 误杀)
    .filter((it) => it.status === "active" || it.status === "snoozed")
    .map(({ id, status, dedup_key }) => ({ item_id: id, status, ...dedup_key }));
}
// 在飞全签索引:dedup 全签 → 在飞条目 id 列表(VERIFY 抑制溯源 + 门重算共用)
export const inFlightKeys = (items) => {
  const m = new Map();
  for (const i of items) {
    const key = `${i.source}|${i.probe_class}|${i.error_signature}`;
    if (!m.has(key)) m.set(key, []);
    m.get(key).push(i.item_id);
  }
  return m;
};

// ── 脚本步 ─────────────────────────────────────────────────────────────────
async function PROBE(def, ctx) {
  // 标源对模式(P2,#164):URL+标源名(feeds.txt 行内 # 首词)——flags.source 从 host 改为
  // 标源名,对齐 _ops_items.dedup_key.source(在飞不重问同因判定面);无注解行回落 host。
  // URL 集与排序与缺省模式同源同序,位等价面(#163 TSV 逐字节同文)不受影响。
  const pairs = (await sh("extract_feed_urls", ["-t"], 120_000, ctx.env)).stdout.split("\n").map((s) => s.trim()).filter(Boolean)
    .map((l) => { const i = l.indexOf("\t"); return [l.slice(0, i), l.slice(i + 1)]; });
  const srcOf = new Map(pairs);
  const urls = [...new Set(pairs.map(([u]) => u))].sort();
  const tsv = (await sh("feed_freshness", urls, 1200_000, ctx.env)).stdout;
  fs.writeFileSync(path.join(ctx.dir, A.PROBE_FRESHNESS_TSV), tsv);
  // matrix(P1,#163)=真扫描单源 tools.mjs matrixScanCli(legacy health_snapshot 同路径同解析;位等价门=同 stub
  // 下两腿产物逐字节同文,自测 selftest-pipeline 位等价例)。产物路径对照:legacy=<ts>-matrix-scan.json
  // (artifactPath ts-slug 族,ops/artifacts/);管线=01-probe-matrix.json(§4.1 序号前缀族)。
  // 失败=嵌套信封不阻轮(C稿 §2.2,legacy 同语义);差异仅落盘面:legacy 失败不落件只回 sc 嵌套信封,
  // 管线按 §4.1 工件契约落信封进件(证据不灭失)。
  const m = await matrixScanCli();
  fs.writeFileSync(path.join(ctx.dir, A.PROBE_MATRIX), m.ok ? matrixArtifactText(m.d) : JSON.stringify(m.env, null, 1));
  const matrix = m.ok ? { ok: true, exit_code: m.d.exit_code, counts: m.d.counts } : m.env;
  const buckets = { fresh: 0, frozen: 0, unreachable: 0, token_required: 0, no_lm: 0 };
  const flags = [];
  for (const line of tsv.split("\n").filter(Boolean)) {
    const [url, lm, age, fam] = line.split("\t");
    const bucket = age === "UNREACHABLE" ? "unreachable" : age === "TOKEN_REQUIRED" ? "token_required"
      : age === "NO-LM" ? "no_lm" : (/^\d+$/.test(age) && +age >= FROZEN_DAYS ? "frozen" : "fresh"); // 门线常量同源 tools.mjs
    buckets[bucket] += 1;
    if (bucket === "frozen" || bucket === "unreachable") { // freshness_flags 同口径:仅冻结/不可达进旗标(TOKEN_REQUIRED/NO-LM 读数不旗)
      const name = srcOf.get(url);
      flags.push({ signal_id: url, url, bucket,
        source: name && name !== "-" ? name : host(url), // 标源名(_ops_items 同形;缺注解回落 host)
        ...(bucket === "frozen" ? { age_days: +age, last_modified: lm } : {}),
        ...(bucket === "unreachable" && fam ? { error_family: fam } : {}) }); // http_<code>/net_fail(lib.sh _ff_probe 四列,P2 消费)
    }
  }
  writeJson(path.join(ctx.dir, A.PROBE_SUMMARY), { ok: true, round_id: ctx.roundId, urls_n: urls.length,
    attempted_n: tsv.split("\n").filter(Boolean).length, buckets, flags,
    matrix: { ok: matrix.ok === true, exit_code: matrix.exit_code ?? null, violation_n: matrix.counts?.violation ?? null } });
}

// 抑制规则谓词求值(纯函数,闭集键在 normalizeRules 入口拦截;首命中即停,规则序=优先级)
function ruleMatch(match, f) {
  const shape = (pat, s) => new RegExp(`^${String(pat).split("*").map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".*")}$`).test(s);
  for (const [k, v] of Object.entries(match ?? {})) {
    if (k === "bucket" && f.bucket !== v) return false;
    else if (k === "url_shape" && !shape(v, f.url)) return false;
    else if (k === "source" && f.source !== v) return false;
    else if (k === "error_family" && (f.error_family ?? null) !== v) return false;
  }
  return true;
}
async function VERIFY(def, ctx) {
  const summary = j(path.join(ctx.dir, A.PROBE_SUMMARY));
  if (!summary) throw infra(`${A.PROBE_SUMMARY} 不可解析`);
  const rulesExists = fs.existsSync(ctx.rulesFile);
  const raw = rulesExists ? j(ctx.rulesFile) : null;
  if (rulesExists && !raw) throw infra(`抑制规则库不可解析:${ctx.rulesFile}(规则零命中=空集照常过;文件坏=终态)`);
  const rules = raw ? normalizeRules(raw) : { version: 0, rules: [] }; // 缺席=合法零规则态(与 _ops_review 零规则起步同口径;审后修 P1:缺席 infra 会致生产 bootstrap 死锁——init_ops_tree 不建此文件,首轮 VERIFY 必死则 adopt_rule 永不可达)
  // 轮次时点版规则快照(#164 审 P2-6 收口,#167):replay --dry 审计读快照而非现行文件
  // ——规则库事后演进(采纳/删除)不得改写历史轮的门判定;快照=工件面证据不灭失。
  if (rulesExists) fs.copyFileSync(ctx.rulesFile, path.join(ctx.dir, A.VERIFY_RULES));
  else writeJson(path.join(ctx.dir, A.VERIFY_RULES), { version: 0, rules: [] }); // 缺席时快照仍落空库形(门读快照单一口径,不留「快照缺席」分叉)
  const flight = inFlightKeys(readInFlightItems(ctx.itemsDir, ctx.state?.replay_of)); // 同因在飞不重问:全签(source|probe_class|error_signature,P4 #166);replay 排除原轮自己的产物(回声防线)
  const survivors = [], suppressed = [];
  for (const f of summary.flags) {
    const rule = rules.rules.find((r) => ruleMatch(r.match, f)); // 首命中,规则序即优先级
    const key = dedupKey(f);
    if (rule?.action === "suppress") { suppressed.push({ ...f, dedup_key: key, rule_id: rule.id }); continue; } // 留痕抑制
    if (flight.has(key)) { // 同因(全签)在飞不重问:证据不灭失,压掉的进留痕工件可翻案
      suppressed.push({ ...f, dedup_key: key, rule_id: "in_flight", in_flight_items: flight.get(key) });
      continue;
    }
    survivors.push(rule?.action === "annotate" ? { ...f, dedup_key: key, annotated_rule: rule.id } : { ...f, dedup_key: key });
  }
  // known_noise_digest:已知误判模式机器格式(C稿 §3.5——TRIAGE 不注入判例全文,只吃本 digest;
  // 含 review_at 供 RETRO P5 到点复审)。
  writeJson(path.join(ctx.dir, A.VERIFY_SURVIVORS), { survivors,
    known_noise_digest: rules.rules.map(({ id, action, match, note, review_at }) => ({ id, action, match, note, review_at })),
    rules_version: rules.version, in_flight_n: flight.size });
  writeJson(path.join(ctx.dir, A.VERIFY_SUPPRESSED), { suppressed, rules_version: rules.version });
}

async function DISPATCH(def, ctx) {
  const h = j(path.join(ctx.dir, A.TRIAGE_HYPOTHESES)) ?? { hypotheses: [] };
  const sorted = [...(h.hypotheses ?? []).filter((x) => x.need_deep)]
    .sort((a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9));
  // 每假设新上下文的 bundle 装配面(C稿 §2.4-1):hid/假设全文/≤3 相关判例命中(锚域词表×该
  // 假设旗标确定性选锚,缺件锄宁少算不注入)/预算余额;TRIAGE→DEEP 隔真脚本步,门永远有件可查。
  const surv = new Map((j(path.join(ctx.dir, A.VERIFY_SURVIVORS))?.survivors ?? []).map((s) => [s.signal_id, s]));
  const anchors = loadAnchors();
  const precDir = ctx.env.PRECEDENTS_DIR ?? path.join(ctx.env.DOCS_ROOT ?? process.env.DOCS_ROOT ?? AGENT_DIR, "ops", "precedents");
  const hitsOf = (x) => {
    const f = surv.get(x.signal_id);
    if (!f) return []; // 旗标缺席=零注入(宁少算;G_TRIAGE 穷尽性另拦)
    return [...new Set(anchorSelect(anchors.anchors, [f]))].filter((n) => fs.existsSync(path.join(precDir, n))).slice(0, 3); // ≤3(C稿 §3.5)
  };
  const truncated = [];
  while (sorted.length && (sorted.length > MAX_DEEP_HYPOTHESES || sorted.length * EST_PER_HYP_CNY > ctx.budgetCny + 1e-9)) {
    const L = sorted.length; // 被截项在截前所处队列长度
    truncated.push({ x: sorted.pop(), reason: L > MAX_DEEP_HYPOTHESES ? "unresolved(dispatch_cap)" : "unresolved(budget)" }); // 截尾降级非终态:假设数上限(#166)优先归因,其次轮预算门 OPS_PIPELINE_BUDGET_CNY;低 severity 先丢
  }
  const bundles = sorted.map((x) => ({ hid: x.signal_id, budget_cny: Math.floor((ctx.budgetCny / sorted.length) * 1e4) / 1e4, // 审后修 P1-1:toFixed 四舍五入 n=3 时各 0.0167 合计 0.0501>0.05 必砸 G_DISPATCH;改 floor 下取
    prompt_pkg: { hypothesis: x.hypothesis, cause_class: x.cause_class, severity: x.severity, probe_hint: x.probe_hint, url: x.signal_id, precedent_hits: hitsOf(x) } }));
  writeJson(path.join(ctx.dir, A.DISPATCH_BUNDLES), { budget_cny: ctx.budgetCny, est_per_hyp_cny: EST_PER_HYP_CNY, max_hypotheses: MAX_DEEP_HYPOTHESES,
    bundles, truncated: truncated.map(({ x, reason }) => ({ hid: x.signal_id, severity: x.severity, reason })),
    degraded: truncated.length > 0 });
  return truncated.length ? { degraded: `dispatch_truncate:${truncated.length} 条按 severity 截尾(${truncated.filter((t) => t.reason === "unresolved(budget)").length} 预算/${truncated.filter((t) => t.reason === "unresolved(dispatch_cap)").length} 上限;预算 ${ctx.budgetCny}¥/上限 ${MAX_DEEP_HYPOTHESES})` } : undefined;
}

// verdict → 建议动作查表闭集(P4 #166 裁:confirmed→human_ruling 建议复核——人裁终局,永不
// 自动执行;refuted→digest_ignore 低危消化条目 severity=low 默认折叠(附带三小裁②);
// unresolved→human_ruling 交人裁;watch→观察名单)。
const ACTION_BY = { confirmed: "human_ruling", refuted: "digest_ignore", unresolved: "human_ruling", watch: "watch" };
const IMPACT_BY_BUCKET = {
  frozen: (f) => `${f.source} 情报源冻结(Last-Modified ${f.age_days} 天无更新),威胁情报新鲜度受损`,
  unreachable: (f) => `${f.source} 情报源不可达(${f.error_family ?? "未知族"}),威胁覆盖面收缩`, };
async function ITEMIZE(def, ctx) {
  const hyps = j(path.join(ctx.dir, A.TRIAGE_HYPOTHESES))?.hypotheses ?? [];
  const verdictsFile = j(path.join(ctx.dir, A.DEEP_VERDICTS)) ?? { verdicts: [], degraded: [] };
  const verdicts = verdictsFile.verdicts, degradedVerdicts = verdictsFile.degraded;
  const truncated = j(path.join(ctx.dir, A.DISPATCH_BUNDLES))?.truncated ?? [];
  const surv = new Map((j(path.join(ctx.dir, A.VERIFY_SURVIVORS))?.survivors ?? []).map((s) => [s.signal_id, s]));
  const rows = [];
  for (const v of verdicts) rows.push({ hid: v.hid, hyp: hyps.find((h) => h.signal_id === v.hid) ?? {}, outcome: v.verdict, one_line: v.one_line, deep_evidence: v.evidence ?? [] });
  for (const v of degradedVerdicts) rows.push({ hid: v.hid, hyp: hyps.find((h) => h.signal_id === v.hid) ?? {}, outcome: "unresolved", one_line: v.one_line, deep_evidence: [] }); // 重试尽降级 unresolved 同入清单(证据不灭失)
  for (const t of truncated) rows.push({ hid: t.hid, hyp: hyps.find((h) => h.signal_id === t.hid) ?? {}, outcome: "unresolved", one_line: `截尾交人裁(${t.reason})`, deep_evidence: [] });
  for (const h of hyps.filter((x) => !x.need_deep)) rows.push({ hid: h.signal_id, hyp: h, outcome: "watch", one_line: h.one_line, deep_evidence: [] }); // 未深验假设直入清单
  // replay 确定性:原轮 manifest 在场时逐 hid 回声原 outcome(审计重放不改生产条目面);
  // 缺席(原轮 ITEMIZE 半程崩溃重放)走桥内文件回声救回部分写入。
  const origByHid = new Map((ctx.state?.replay_of ? j(path.join(ctx.opsRoot, "rounds", ctx.state.replay_of, A.ITEMIZE_MANIFEST))?.rows ?? [] : []).map((r) => [r.hid, r]));
  let created = 0, reopened = 0, deduped = 0;
  const out = [];
  for (const r of rows) {
    const f = surv.get(r.hid);
    if (!f) throw infra(`条目行旗标缺席:${r.hid}(幸存面与假设面漂移)`); // 宁响亮:G_TRIAGE 穷尽性前置,此为防御面
    const sig = itemSignature(f); // 查表零模型(与 P1 探测器同空间;折叠族映射=#164 偏离①钉死在 ops-items.mjs)
    const severity = r.outcome === "refuted" ? "low" : (r.hyp.severity ?? "low"); // refuted 恒 low 消化条目(附带三小裁②)
    const action = ACTION_BY[r.outcome] ?? "human_ruling";
    const echoRow = origByHid.get(r.hid);
    const res = echoRow && fs.existsSync(path.join(ctx.itemsDir, `${echoRow.item_id}.md`))
      ? { outcome: echoRow.outcome, item: echoRow.item_id, supersedes: echoRow.supersedes ?? null, echo: true }
      : createOpsItem(ctx.itemsDir, { source: f.source, ...sig, action, args: { source: f.source },
        evidence: { signal_id: r.hid, bucket: f.bucket, verdict: r.outcome, hypothesis: r.hyp.hypothesis ?? "",
          ...(f.age_days != null ? { age_days: f.age_days } : {}), ...(f.error_family ? { error_family: f.error_family } : {}),
          ...(f.annotated_rule ? { annotated_rule: f.annotated_rule } : {}), ...(r.deep_evidence.length ? { deep_evidence: r.deep_evidence } : {}) },
        impact: (IMPACT_BY_BUCKET[f.bucket] ?? (() => `${f.source} 信号异常(${f.bucket})`))(f),
        rollback: "复核读数后按四键处置;健康轮探测只读无副作用,无不可逆变更",
        severity, cause_group: CAUSE_GROUP_BY_BUCKET[f.bucket], round_id: ctx.roundId,
        summary: `# 待审:源 ${f.source} ${f.bucket === "frozen" ? `冻结读数 ${f.age_days} 天` : `不可达(${f.error_family ?? "?"})`} 深验 ${r.outcome}\n\n${r.one_line ?? ""};可证伪假设与深验证据见 evidence 字段;建议 ${action}(永不自动执行)。\n` },
        { echoRoundId: ctx.state?.replay_of ?? null, dayIso: ctx.roundId.slice(0, 10) });
    if (res.outcome === "created") created += 1; else if (res.outcome === "reopened") reopened += 1; else deduped += 1;
    out.push({ hid: r.hid, signal_id: r.hid, source: f.source, bucket: f.bucket, verdict: r.outcome, severity, suggested_action: action,
      one_line: r.one_line ?? r.hyp.one_line ?? "", dedup_key: { source: f.source, ...sig },
      item_id: res.item, outcome: res.outcome, supersedes: res.supersedes, ...(res.echo ? { echo: true } : {}) });
  }
  const suppressed = j(path.join(ctx.dir, A.VERIFY_SUPPRESSED))?.suppressed?.length ?? 0;
  writeJson(path.join(ctx.dir, A.ITEMIZE_MANIFEST), { created, reopened, deduped, suppressed, rows: out });
}

// ── RETRO 候选推导(P5 #167;C稿 §2.2/§6-6)─────────────────────────────────
// 机械误判→确定性检查候选:diff 本轮幸存旗标 vs 四键处置(items 树 dismissed 终态)
// vs P1 探测器独立通道(被抑制信号对照在飞条目)——全部确定性查表,零模型。
// 候选只产 adopt_rule 待审条目(经四键人裁采纳才进 rules/suppressions.json,
// 写口=backend _ops_review 人裁面;永不自动生效=责任线铁律,DESIGN.md §3)。
export const RETRO_ITEM_CAP = 1; // 每轮至多立一条待审条目(C稿 §2.2「可选一条 adopt_rule 待审条目」;候选清单全量入 retro JSON,宁少算)
const dayIso = () => new Date().toISOString().slice(0, 10);
const keyTriple = (dk) => `${dk.source}|${dk.probe_class}|${dk.error_signature}`;
// 候选 match 草案:旗标 → 谓词闭集内最窄匹配(source+bucket+精确 error_family;
// 宁少算:先窄后人裁可 modify 放宽;url_shape 归纳不在确定性面,不自动造)。
const matchOf = (f) => ({ ...(f.source ? { source: f.source } : {}), bucket: f.bucket, ...(f.error_family ? { error_family: f.error_family } : {}) });
const matchKey = (m) => Object.keys(m).sort().map((k) => `${k}=${m[k]}`).join("&");
export function retroDiff({ survivors, suppressed, items, rules, today }) {
  // ① 规则命中统计(replay 审计面同源数据):suppress 计入 suppressed,annotate 计入幸存 annotated_rule
  const hits = new Map();
  for (const x of suppressed ?? []) if (x.rule_id && x.rule_id !== "in_flight") hits.set(x.rule_id, (hits.get(x.rule_id) ?? 0) + 1);
  for (const s of survivors ?? []) if (s.annotated_rule) hits.set(s.annotated_rule, (hits.get(s.annotated_rule) ?? 0) + 1);
  const rule_hits = rules.rules.map((r) => ({ id: r.id, action: r.action, hits_n: hits.get(r.id) ?? 0, review_at: r.review_at }));
  // ② review_at 到点报复审(C稿 §4.2:防规则腐烂;零命中/高命中均交人看)
  const rules_due_review = rule_hits.filter((r) => r.review_at <= today);
  // ③ 机械误判:同签信号被四键 ignore 过(dismissed=人判误报)而本轮仍幸存 → 候选 suppress 草案
  const dismissedByKey = new Map();
  for (const it of items ?? []) if (it.status === "dismissed") {
    const k = keyTriple(it.dedup_key);
    if (!dismissedByKey.has(k)) dismissedByKey.set(k, []);
    dismissedByKey.get(k).push(it.id);
  }
  const seen = new Set();
  const candidates = [];
  for (const s of survivors ?? []) {
    const ids = dismissedByKey.get(s.dedup_key);
    if (!ids?.length) continue;
    const m = matchOf(s), mk = matchKey(m);
    if (seen.has(mk)) continue; // 同 match 形状去重(同源同族多条旗标=一条候选)
    seen.add(mk);
    candidates.push({ match: m, action: "suppress",
      note: `同签信号已被四键 ignore ${ids.length} 次(条目 ${ids.join(",")})而本轮仍幸存——机械误判候选,建议采纳为抑制规则`,
      evidence: { signal_id: s.signal_id, dedup_key: s.dedup_key, dismissed_items: ids } });
  }
  candidates.sort((a, b) => matchKey(a.match) < matchKey(b.match) ? -1 : 1); // 确定性序
  // ④ 两通道矛盾(C稿 §4.6 风险 2):规则抑制的信号在 P1 探测器通道仍有在飞条目
  //   (探测器不经过规则库)=规则可能压真信号——仅报复审,不产候选(建言不裁决)。
  const channel_conflicts = [];
  for (const x of suppressed ?? []) {
    if (!x.rule_id || x.rule_id === "in_flight") continue;
    const live = (items ?? []).filter((it) => (it.status === "active" || it.status === "snoozed")
      && keyTriple(it.dedup_key) === x.dedup_key).map((it) => it.id);
    if (live.length) channel_conflicts.push({ dedup_key: x.dedup_key, rule_id: x.rule_id, in_flight_items: live });
  }
  return { candidates, rules_due_review, rule_hits, channel_conflicts };
}
// 候选 → adopt_rule 待审条目(dedup:source=retro|probe_class=adopt_rule|error_signature=match 规范键)。
// 立项节流(RETRO_ITEM_CAP):每轮至多一次立项尝试;已被裁(done=采纳/dismissed=否决)的
// 候选键不再立项(已否决不重复打扰人裁),队位让给下一条未裁候选(确定性序,防饿死)。
function adoptRuleItem(ctx, cand) {
  const mk = matchKey(cand.match);
  const res = createOpsItem(ctx.itemsDir, { source: "retro", probe_class: "adopt_rule", error_signature: mk,
    action: "adopt_rule", // 四键面识别词:agree/modify → _ops_review 采纳写规则(唯一写口);ignore → 否决
    args: { match: cand.match, action: cand.action, note: cand.note },
    evidence: { round_id: ctx.roundId, ...cand.evidence },
    impact: `采纳后同形信号(${mk})将被 VERIFY 抑制规则压掉(留痕进 suppressed 工件,证据降权不灭失)`,
    rollback: "删除 rules/suppressions.json 中对应规则行即恢复(规则库人裁可逆;review_at 90 天到点强制复审)",
    severity: "low", cause_group: "rule_proposal",
    summary: `# 待审(adopt_rule):抑制规则候选 ${mk}\n\n${cand.note};证据见 evidence 字段(dismissed 条目链)。\n四键:agree/modify=采纳进规则库(下一轮 VERIFY 生效);ignore=否决本候选。永不自动生效。\n` },
    { dayIso: ctx.roundId.slice(0, 10) });
  return { outcome: res.outcome, item_id: res.item, supersedes: res.supersedes ?? null, ...(res.echo ? { echo: true } : {}) };
}
async function RETRO(def, ctx) {
  const usage = `in=${ctx.usage.input} out=${ctx.usage.output} total=${ctx.usage.totalTokens} cost=${ctx.usage.cost.toFixed(8)}`;
  // 幂等重入(resume #167):台账已有本轮行则零追加(crash 后恢复不双记账——回声防线)
  const ledgerTag = LEDGER_TAGS[ctx.type ?? "health"]; // #207 T1:轮型→标签单源
  let ledgerNow = null;
  try { ledgerNow = fs.readFileSync(ctx.ledgerFile, "utf8"); } catch { /* 首轮无台账文件=正常 */ }
  if (!(ledgerNow ?? "").includes(`${ledgerTag}:${ctx.roundId}`))
    try { await sh("ledger_append", [ctx.type ?? "health", ctx.state?.model_face === "real" ? "pipeline-real" : "faux-pipeline", usage, `${ledgerTag}:${ctx.roundId}`], 120_000, ctx.env); } catch (e) { throw Object.assign(new Error(`台账写败:${e.message}`), { code: "ledger_failed" }); } // 台账先记(#170 起真面记 pipeline-real;faux 面标签不变向后兼容;轮次列=轮型)
  try { await sh("sandbox_assert", [], 60_000, ctx.env); } // 沙箱红线真执行(backend/frontend 零改动)
  catch (e) { throw Object.assign(new Error("sandbox_assert rc≠0(backend/frontend 污染)"), { code: "sandbox_violation" }); }
  let degraded;
  try { // 候选产出失败=降级(跳过 retro,轮仍成功);台账/sandbox 失败已先行终态(C稿 §2.2 语义序)
    fs.mkdirSync(path.dirname(ctx.retroFile), { recursive: true });
    if (ctx.type === "discover") { // 发现轮 retro 体(#207 T1):计数面=d1-d4 工件回算;无规则/条目 diff 面(健康轮律不适用)
      const scan = j(path.join(ctx.dir, A.DISCOVER_SCAN));
      const shortlist = j(path.join(ctx.dir, A.DISCOVER_SHORTLIST));
      const measure = j(path.join(ctx.dir, A.DISCOVER_MEASURE));
      const enqueue = j(path.join(ctx.dir, A.DISCOVER_ENQUEUE));
      writeJson(ctx.retroFile, { round_id: ctx.roundId, type: "discover", generated_at: new Date().toISOString(),
        counts: { scan_n: scan?.candidates?.length ?? 0, shortlist_n: shortlist?.candidates?.length ?? 0,
          measure_hold_n: measure?.hold_n ?? 0, enqueue_n: enqueue?.n_enqueued ?? 0 },
        degraded_traces: [shortlist?.degraded].filter(Boolean), // 降级留痕集中面(SHORTLIST 解析失败等)
        candidates: [], // T1 无 retro 候选(T2 #208 强化门时随面扩展)
        sandbox_assert_pass: true, sandbox_assert_rc: 0, degraded: false });
      return undefined;
    }
    const s = j(path.join(ctx.dir, A.PROBE_SUMMARY));
    const survivors = j(path.join(ctx.dir, A.VERIFY_SURVIVORS))?.survivors ?? [];
    const suppressedF = j(path.join(ctx.dir, A.VERIFY_SUPPRESSED));
    const rawRules = j(ctx.rulesFile);
    const rules = rawRules ? normalizeRules(rawRules) : { version: 0, rules: [] }; // 步侧已过门,坏文件不会到这;缺席=零规则照常
    const items = parseItemsTree(ctx.itemsDir);
    // #184 出口③:finding 计入 RETRO 摘要工件(读 08 工件只计数零出口动作;G_RETRO 机检与工件回算一致)。
    // 降级轮(08=失败信封)记 status=degraded(诚实面:求值面死非零 finding);resume 旧轮防御:出口记录缺席则补初始化。
    const sweepArt = j(path.join(ctx.dir, A.ANCHOR_SWEEP));
    const anchorSweep = sweepArt && Array.isArray(sweepArt.results)
      ? { status: "ok", n_total: sweepArt.results.length, n_fail: sweepArt.n_fail,
          findings: sweepArt.results.filter((x) => !x.ok).map(({ ip, expect, verdict, confidence, accusers }) => ({ ip, expect, verdict, confidence, accusers })) }
      : { status: "degraded" };
    if (!ctx.state.finding_exits)
      ctx.state.finding_exits = { triggered: false, findings_n: 0, dry_run: false, reason: "resume_legacy_round(#184 前状态文件无出口记录)", gh_issue: { status: "skip", reason: "legacy" }, webhook: { status: "skip", reason: "legacy" } };
    ctx.state.finding_exits.retrospective_summary = { status: anchorSweep.status === "ok" ? "counted" : anchorSweep.status, n_fail: anchorSweep.n_fail ?? null };
    const diff = retroDiff({ survivors, suppressed: suppressedF?.suppressed ?? [], items, rules, today: dayIso() });
    // 待审条目:首条未裁候选立项(RETRO_ITEM_CAP=一次尝试/轮);replay 恒零写
    // (审计重放不改生产条目面,同 ITEMIZE 回声律)。
    let placed = false;
    for (const c of diff.candidates) {
      if (ctx.state?.replay_of) { c.item = { skipped: "replay" }; continue; }
      if (placed) { c.item = { skipped: "cap" }; continue; }
      const mk = matchKey(c.match);
      const ruled = items.some((it) => it.dedup_key.source === "retro" && it.dedup_key.probe_class === "adopt_rule"
        && it.dedup_key.error_signature === mk && (it.status === "done" || it.status === "dismissed"));
      if (ruled) { c.item = { skipped: "already_ruled" }; continue; }
      c.item = adoptRuleItem(ctx, c);
      placed = true;
    }
    fs.mkdirSync(path.dirname(ctx.retroFile), { recursive: true });
    writeJson(ctx.retroFile, { round_id: ctx.roundId, generated_at: new Date().toISOString(),
      flags_n: (s?.flags ?? []).length, survivors_n: survivors.length, suppressed_n: suppressedF?.suppressed?.length ?? 0,
      verdicts_n: j(path.join(ctx.dir, A.DEEP_VERDICTS))?.verdicts?.length ?? 0,
      anchor_sweep: anchorSweep, // #184 出口③:巡检 finding 摘要行(G_RETRO 机检:与 08 工件回算一致)
      rules_version: rules.version,
      ...diff, // candidates(P5 #167:机械误判→adopt_rule 候选,仅产条目永不自动生效)/rules_due_review/rule_hits/channel_conflicts
      sandbox_assert_pass: true, sandbox_assert_rc: 0, degraded: false });
  } catch (e) {
    degraded = { degraded: `skip_retro:retro 候选写败(${e.message})——轮仍成功`, skipGate: true };
  }
  return degraded;
}

async function CLOSE(def, ctx) { // 书挡步:存在性校验(闭合双层的外层)+ 信封原料
  // #199 A5:预算四界读数工件(09-budget.json)。先于 pkg 存在性早退——预算面必落:
  // 报告缺席轮的谱系/审计面不随早退丢。读数=环内执法同一 ctx 计数面(usage 快照/调用数/
  // 墙钟/dup_top3 观察+月度准入投影);门面 G_CLOSE 做回声哨对拍(环内已执法,门只防工件漂移)。
  const isDiscover = ctx.type === "discover";
  const knobs = ctx.budgetKnobs ?? (isDiscover ? budget.readDiscoverKnobs(ctx.env ?? {}) : budget.readBudgetKnobs(ctx.env ?? {})); // #207 T1:发现轮旋钮族同面(轮始已校验,此为回退面)
  // #199 B:breaker 快照只读观察面(回声律:不造文件——状态文件仅在通道面首次结算时创建,
  // 生产首轮自动建 CHANGELOG 注记);旋钮生效值随快照落盘=可证伪。轮始校验同 budget 判例
  // (mkCtx 读一次,非法=用法错 exit 2 不带病跑轮)。
  const breakerFace = mkBreaker({
    file: path.join(ctx.opsRoot ?? path.dirname(ctx.dir), "breaker.json"),
    env: ctx.env ?? {}, round: ctx.roundId ?? "health", knobs: ctx.breakerKnobs ?? readBreakerKnobs(ctx.env ?? {}),
  });
  writeJson(path.join(ctx.dir, A.BUDGET), {
    round_id: ctx.roundId,
    generated_at: new Date().toISOString(),
    env: isDiscover // 生效值 per-type(#207 T1):发现轮=三旋钮+est+共享月帽(无 token 界——发现轮不预设轨迹预算);健康轮 7 键面字节不变(位等价)
      ? { OPS_PIPELINE_BUDGET_CNY: ctx.budgetCny, OPS_DISCOVER_MAX_MODEL_CALLS: knobs.maxModelCalls,
          OPS_DISCOVER_WALL_CLOCK_S: knobs.wallClockS, OPS_DISCOVER_SPEND_CAP_CNY: knobs.spendCapCny,
          OPS_PIPELINE_MONTHLY_CAP_CNY: knobs.monthlyCapCny }
      : { // 生效值(含 OPS_PIPELINE_BUDGET_CNY:语义=DISPATCH 准告警线,真执法=A1 四界)
        OPS_PIPELINE_BUDGET_CNY: ctx.budgetCny,
        OPS_PIPELINE_MAX_MODEL_CALLS: knobs.maxModelCalls,
        OPS_PIPELINE_TOKEN_BUDGET: knobs.tokenBudget,
        OPS_PIPELINE_WALL_CLOCK_S: knobs.wallClockS,
        OPS_PIPELINE_SPEND_CAP_CNY: knobs.spendCapCny,
        OPS_PIPELINE_MONTHLY_CAP_CNY: knobs.monthlyCapCny,
        OPS_PIPELINE_DUP_CALL_LIMIT: knobs.dupCallLimit,
      },
    readings: {
      usage: { ...ctx.usage },
      model_calls: ctx.modelCalls ?? 0,
      wall_s: Number(budget.elapsedWallS(ctx.state?.started_at).toFixed(1)),
      dup_top3: budget.dupTop(ctx.dupRegistry ?? new Map(), 3),
      monthly: ctx.state?.monthly_admission ?? null, // A2 准入留痕(replay 面无准入=null)
      breaker: breakerFace.snapshot(), // #199 B:五通道闭集态+生效旋钮(观察不裁决,G_CLOSE 不对拍帽——无帽可拍)
    },
  });
  if (isDiscover) { ctx.pkg = null; return; } // 发现轮无报告步/无判例校验面(#207 T1;信封 pkg=null 恒)
  const report = path.join(ctx.dir, A.SYNTH_REPORT);
  ctx.pkg = fs.existsSync(report) ? report : null;
  if (!ctx.pkg) return;
  try {
    const v = await sh("verify_cited_precedents", [ctx.pkg], 120_000, ctx.env);
    ctx.verify = { ok: true, cited: Number((v.stdout.match(/(\d+) 条判例路径全部存在/) ?? [])[1] ?? 0) };
  } catch (e) { throw Object.assign(new Error(`判例存在性校验败:${e.message}`), { code: "verify_failed" }); }
}

// ── ANCHOR_SWEEP(#182):生产查询路径锚巡检(只测量不判断;判断在门/finding 面)──
// 求值=tools.mjs anchorSweepCli(python -m ipdb._eval --anchor-sweep --json;OPS_EVAL_PY/OPS_DATA_DIR
// 桥=backend _round_env 注入,容器内解释器与数据面=后端查询进程同一套——读数即生产读数,
// 零认证零网络,matrixScanCli 同型先例)。锚 finding=读数非故障(工件原样落盘交 G_ANCHOR_SWEEP
// 验形状,不持门);求值面死=RETRO 同款降级旁路(失败信封四码/infra 落件证据不灭失,轮仍成功);
// #184 finding 出口三件套接线:gh issue+webhook 在本步触发(finding>0;只写不动作,出口永不败轮;
// replay 恒零外发),RETRO 摘要行由 RETRO 步读本工件计数(出口③)。
async function ANCHOR_SWEEP(def, ctx) {
  const r = await anchorSweepCli();
  fs.writeFileSync(path.join(ctx.dir, A.ANCHOR_SWEEP),
    r.ok ? `${JSON.stringify(r.d, null, 1)}\n` : `${JSON.stringify(r.env, null, 1)}\n`);
  ctx.state.finding_exits = await runFindingExits({ roundId: ctx.roundId, sweepD: r.ok ? r.d : null, dir: ctx.dir,
    env: ctx.env, replayOf: ctx.state?.replay_of ?? null }); // #184:信封 pipeline.finding_exits 留痕(skip/failed 同合法态)
  if (r.ok) return undefined; // finding 在场=读数面照常评门(不持门=门验形状不验 finding 数)
  return { degraded: `anchor_sweep_degraded:${r.env.code}(巡检面死,失败信封落件;出口三件套零触发)`, skipGate: true };
}

// ── 模型步装配/收编(faux.mjs 真 Agent 循环的上下文与落盘;判断仍全在模型步+门)────────
// 空转金轨迹(#162 审 P2-2,2026-10-23 裁定①):零 need_deep 轮 DEEP 仍跑一条 canned-假设 faux 回路,
// 零成本保模型步回路活性;金轨迹 hid 不入 verdicts(不污染条目),由 deepFinalize 收编为 golden_track。
const GOLDEN_BUNDLE = { hid: "golden-track-canned", golden: true, budget_cny: 0,
  prompt_pkg: { hypothesis: "金轨迹保活 canned 假设:若冻结读数为真,HEAD 复测 age_days 应保持不变", cause_class: "frozen_feed", severity: "low", probe_hint: "reprobe_get", url: "(canned)", precedent_hits: [] } };
function triageInput(ctx) {
  const sv = j(path.join(ctx.dir, A.VERIFY_SURVIVORS));
  const rows = (sv?.survivors ?? []).map(({ signal_id, source, bucket, age_days, url, error_family, annotated_rule }) =>
    ({ signal_id, source, bucket, ...(age_days != null ? { age_days } : {}), url,
      ...(error_family ? { error_family } : {}), ...(annotated_rule ? { annotated_rule } : {}) }));
  // 已知误判模式 digest 同入(C稿 §3.5:TRIAGE 只吃机器 digest,不注入判例全文;闭集校验面不膨胀)
  return { systemPrompt: fs.readFileSync(promptFile("health/triage"), "utf8"),
    userMsg: JSON.stringify({ survivors: rows, known_noise_digest: sv?.known_noise_digest ?? [] }) };
}
function triageConsume(ctx, _item, { text }) {
  let h;
  try { h = JSON.parse(text); } catch { throw Object.assign(new Error("TRIAGE 输出非 JSON(schema 违例)"), { code: "model_face" }); }
  if (!h || !Array.isArray(h.hypotheses)) throw Object.assign(new Error("TRIAGE 输出缺 hypotheses 数组"), { code: "model_face" });
  writeJson(path.join(ctx.dir, A.TRIAGE_HYPOTHESES), h);
}
const deepItems = (ctx) => {
  const bundles = j(path.join(ctx.dir, A.DISPATCH_BUNDLES))?.bundles ?? [];
  return bundles.length ? bundles : [GOLDEN_BUNDLE]; // 零 bundle=金轨迹回路(#162 审 P2-2,裁定①)
};
// DEEP 登记表重建(P4 #166):逐假设 transcript 的 registry_seed 行 → Map(call_id → {tool, sc});
// 宿主回填(G_DEEP 写前语义门同源重算)与门重算共用本面(单一解析语义,不另起炉灶)。
export function deepSeeds(dir, hid = null) {
  const m = new Map();
  const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => DEEP_TRANSCRIPT_RE.test(f)
    && (hid === null || f === deepTranscriptName(hidSlug(hid)))) : [];
  for (const f of files)
    for (const line of fs.readFileSync(path.join(dir, f), "utf8").split("\n").filter(Boolean)) {
      let r; try { r = JSON.parse(line); } catch { continue; }
      if (r?.type === "registry_seed") m.set(r.call_id, { tool: r.tool, sc: r.sc });
    }
  return m;
}
function deepInput(ctx, item) {
  return { systemPrompt: fs.readFileSync(promptFile("health/deep"), "utf8"), // 真提示词 P4 #166(C稿 §3.3+A 一律)
    userMsg: JSON.stringify({ hypothesis_bundle: item.prompt_pkg, budget_cny: item.budget_cny, ...(item.golden ? { golden: true } : {}) }) };
}
function deepConsume(ctx, item, { text }) {
  let v;
  try { v = JSON.parse(text); } catch { throw Object.assign(new Error(`DEEP 输出非 JSON(${item.hid})`), { code: "model_face" }); }
  if (!v || typeof v.verdict !== "string") throw Object.assign(new Error(`DEEP 输出缺 verdict(${item.hid})`), { code: "model_face" });
  if (v.evidence !== undefined && !Array.isArray(v.evidence)) throw Object.assign(new Error(`DEEP 输出 evidence 非数组(${item.hid})`), { code: "model_face" });
  for (const e of v.evidence ?? [])
    if (!e || typeof e !== "object" || typeof e.call_id !== "string" || typeof e.field !== "string")
      throw Object.assign(new Error(`DEEP evidence 非选择对 {call_id,field}(${item.hid};A 一律:值由宿主回填)`, { code: "model_face" }));
  // A 一律宿主回填(P4 #166):模型只交 call_id+field 选择对,值从登记表(本假设 transcript 的
  // registry_seed 结构化返回)回填;模型复述的 value 原样透传——不符由 G_DEEP 写前语义门拒(复述
  // 不符即门败,不在此静默纠正——静默改写会把复述漂移藏成门永远看不见的面)。
  const seeds = deepSeeds(ctx.dir, item.hid);
  const evidence = (v.evidence ?? []).map((e) => ({ call_id: e.call_id, field: e.field,
    value: e.value !== undefined ? e.value : resolveField(seeds.get(e.call_id)?.sc, e.field) }));
  writeJson(path.join(ctx.dir, deepArtifactName(hidSlug(item.hid))), { hid: item.hid, ...(item.golden ? { golden: true } : {}), ...v, evidence });
}
function deepFinalize(ctx, { degradedItems }) { // 收编尾:逐假设工件 → 单 verdicts 集(降级项入 degraded;金轨迹单收 golden_track)
  const verdicts = [], golden = [];
  for (const b of deepItems(ctx)) {
    const f = j(path.join(ctx.dir, deepArtifactName(hidSlug(b.hid))));
    if (!f) continue;
    const row = { hid: f.hid, verdict: f.verdict, evidence: f.evidence ?? [], one_line: f.one_line ?? "" };
    (f.golden || b.golden ? golden : verdicts).push(row);
  }
  writeJson(path.join(ctx.dir, A.DEEP_VERDICTS), { verdicts, degraded: degradedItems, golden_track: golden });
}
async function synthInput(ctx) {
  // 判例注入只在 SYNTH(闭合校验面集中,C稿 §3.5);检索词=锚域词表(B 三件②,P3 接线:
  // agent.mjs KWS.health 硬编码退役,词表单一真源=anchors-health.json)+ 锚词表×幸存旗标确定性选锚。
  const anchors = loadAnchors();
  const flags = j(path.join(ctx.dir, A.VERIFY_SURVIVORS))?.survivors ?? [];
  const docsRoot = ctx.env.DOCS_ROOT ?? path.resolve(AGENT_DIR, "..", "..", "docs"); // 同 lib.sh 派生链
  const precDir = ctx.env.PRECEDENTS_DIR ?? path.join(docsRoot, "ops", "precedents");
  const onDisk = (n) => fs.existsSync(path.join(precDir, n)); // 锚选目标须在真源判例库在场(缺件锚宁少算不注入)
  const anchored = [...new Set(anchorSelect(anchors.anchors, flags))].filter(onDisk);
  const kws = [...new Set(anchors.anchors.flatMap((a) => a.keywords))];
  const inj = await sh("inject_precedents", kws, 120_000, ctx.env);
  const hitNames = [...inj.stdout.matchAll(/^- ([0-9]{4}-[0-9]{2}-[0-9]{2}-[^\s]+\.md)\s*$/gm)].map((m) => m[1]);
  const injected = [...new Set([...anchored, ...hitNames])].slice(0, HIT_CAP);
  // 条目明细(ADR 0006:报告=条目集只读渲染;异常清单每行对应真实条目)——直读本轮 manifest rows
  // (P4 #166:真条目在 ops/items 树,轮内产物面=manifest 行,item_id 供四键走查对号)
  const rows = j(path.join(ctx.dir, A.ITEMIZE_MANIFEST))?.rows ?? [];
  const itemsDetail = rows.map(({ source, verdict, severity, suggested_action, one_line, item_id }) => ({ source, verdict, severity, suggested_action, one_line, item_id }));
  const input = { injected, manifest: j(path.join(ctx.dir, A.ITEMIZE_MANIFEST)), items: itemsDetail,
    verdicts_digest: (j(path.join(ctx.dir, A.DEEP_VERDICTS))?.verdicts ?? []).map(({ hid, verdict }) => ({ hid, verdict })),
    probe: (({ urls_n, buckets, matrix }) => ({ urls_n, buckets, matrix }))(j(path.join(ctx.dir, A.PROBE_SUMMARY)) ?? {}) };
  // 锚选不在检索命中内的,以锚域 note 补一行 gist(具名引用禁裸 id,研究 #71);超帽沿铁律⑦截前 8
  const anchoredExtra = anchored.filter((n) => !hitNames.includes(n)).map((n) => {
    const a = anchors.anchors.find((x) => x.precedents.includes(n));
    return `- ${n}\n  - 锚域 ${a?.domain ?? "?"}: ${a?.note ?? ""}`;
  });
  // 展示面=闭合集(审后修 P1):注入块里出现的命中行必须 ∈ injected(G_SYNTH 的 allowed 集为同源),
  // 否则模型诚实引用注入块内文件名也会被 closure_check 误杀成轮终态——过滤无条件化,不分命中多寡。
  const injectedHitN = hitNames.filter((n) => injected.includes(n)).length;
  const block = synthInjectionBlock(inj.stdout, anchoredExtra, hitNames, injected)
    + (hitNames.length > injectedHitN ? `\n(命中 ${hitNames.length} 条,注入 ${injectedHitN} 条——铁律⑦)` : "");
  return { systemPrompt: fs.readFileSync(promptFile("health/synth"), "utf8"), userMsg: `${block.trim()}\n\n# 本轮输入\n${JSON.stringify(input)}`, meta: { injected } };
}

// 注入块构造(纯函数,审后修 P1 抽出钉负例):命中行仅当 ∈ injected 才展示;锚补行(锚选⊆injected 恒成立)直出。
export function synthInjectionBlock(injStdout, anchoredExtra, hitNames, injected) {
  const lines = injStdout.split("\n").filter((l) => {
    const m = l.match(/^- ([0-9]{4}-[0-9]{2}-[0-9]{2}-[^\s]+\.md)\s*$/);
    return !m || injected.includes(m[1]);
  });
  return `${lines.join("\n")}${anchoredExtra.length ? `\n${anchoredExtra.join("\n")}` : ""}`;
}
function synthConsume(ctx, _item, { text }) {
  if (!text.trim()) throw Object.assign(new Error("SYNTH 最终文本为空"), { code: "empty_text" });
  fs.writeFileSync(path.join(ctx.dir, A.SYNTH_REPORT), text);
}

// 发现轮 SHORTLIST(#207 T1):输入=SCAN 候选宇宙;输出=结构化候选(JSON,span 级引用=T2 #208 强化)。
// 解析失败=降级空清单留痕不炸轮(spec T1 明律:零候选合法面,同 TRIAGE 零假设;不重试不 model_face)。
function shortlistInput(ctx) {
  const scan = j(path.join(ctx.dir, A.DISCOVER_SCAN)) ?? { candidates: [] };
  return { systemPrompt: fs.readFileSync(promptFile("discover/shortlist"), "utf8"),
    userMsg: JSON.stringify({ candidates: scan.candidates, note: "T1 候选宇宙=registry+needs 两面(web 面 T3 #209 接线);产出结构化候选 JSON" }) };
}
function shortlistConsume(ctx, _item, { text }) {
  let out;
  try {
    const body = (text.match(/\{[\s\S]*\}/) ?? [])[0]; // 散文/围栏包裹的 JSON 体宽容提取(提取不出仍走降级)
    if (!body) throw new Error("无 JSON 体");
    const parsed = JSON.parse(body);
    if (!Array.isArray(parsed?.candidates)) throw new Error("candidates 非数组");
    out = { round_id: ctx.roundId, candidates: parsed.candidates };
  } catch (e) {
    out = { round_id: ctx.roundId, candidates: [], degraded: `shortlist_parse:${e.message}(降级空清单留痕,轮不炸;spec T1)` };
  }
  writeJson(path.join(ctx.dir, A.DISCOVER_SHORTLIST), out);
}

// 模型步工件完备判定(#167 resume 三规则②):「有 transcript(=本步工件集齐)→ 只补门
// 评估,不重花 token」。单发步=def.out 全在场;逐假设步(DEEP)=该假设 05-deep-<hid>.json
// + transcript 在场(聚合 verdicts 由 finalize 从逐假设工件重建,不算完备判据)。
export function modelItemComplete(def, ctx, item) {
  if (def.forEach) { // forEach 今日仅 DEEP;命名面=deepConsume 同源(05-deep-<slug> 族,名表参数族工厂)
    return fs.existsSync(path.join(ctx.dir, deepArtifactName(hidSlug(item.hid))))
      && fs.existsSync(path.join(ctx.dir, deepTranscriptName(hidSlug(item.hid))));
  }
  return def.out.every((f) => fs.existsSync(path.join(ctx.dir, f)));
}

// ── 发现轮四步(#207 T1;spec /tmp/discover-pipeline-spec.md T1 节;ADR 0010 六步骨架)──────────
// SCAN:确定性候选宇宙快照(零模型零网络):两面=已接源注册表(backend/ipdb/_sources/*.py,下划线
// 前缀=内部模块非源)+ NEEDS.md 缺口行(AGENTS.md:NEEDS=「想问而无槽」index;状态 open/候选=缺口)。
// web 渠道=T3 #209 接线占位(留痕不炸轮)。证据永不灭失:registry 面指针=repo 相对模块路径,
// needs 面=NEEDS.md 行锚——候选可原样回算。同 commit 重扫逐字节同(确定性,无网络无时钟入候选面)。
const NEEDS_STATUS = ["open", "候选"]; // 缺口行状态闭集(已立项/已闭不入候选宇宙)
async function SCAN(def, ctx) {
  // #208 T2 faux 缝:显式 faux 面(缺省真面)且 fixture 在场→候选宇宙=罐装钉死。理由:
  // span 门使罐装 quote 与 NEEDS.md 原文耦合,真仓演进会破门(ops CI 随文案红);
  // faux=罐装 I/O 是仓律(#170 面选择);真轮(缺省)不受影响。证据永不灭失不破:
  // 罐装宇宙自带 text 面,span 回引在轮工件内可回算。
  if (ctx.modelFace === "faux" && typeof ctx.fixturesDir === "string") {
    const fxPath = path.join(ctx.fixturesDir, A.DISCOVER_SCAN);
    if (fs.existsSync(fxPath)) {
      const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
      writeJson(path.join(ctx.dir, A.DISCOVER_SCAN), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
        candidates: fx.candidates, channels: fx.channels });
      return;
    }
  }
  const repoRoot = path.resolve(AGENT_DIR, "..", "..");
  const registry = fs.existsSync(path.join(repoRoot, "backend", "ipdb", "_sources"))
    ? fs.readdirSync(path.join(repoRoot, "backend", "ipdb", "_sources")).filter((f) => f.endsWith(".py") && !f.startsWith("_")).sort()
      .map((f) => ({ name: f.replace(/\.py$/, ""), url: null, evidence_ptr: `backend/ipdb/_sources/${f}`, source_channel: "source_registry", status: "integrated" }))
    : [];
  const needsRows = [];
  const needsFile = path.join(repoRoot, "NEEDS.md");
  if (fs.existsSync(needsFile)) {
    const lines = fs.readFileSync(needsFile, "utf8").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const cells = lines[i].split("|").map((c) => c.trim());
      if (cells.length < 5 || !NEEDS_STATUS.includes(cells[3])) continue;
      const url = (cells[1].match(/https?:\/\/\S+/) ?? [null])[0];
      needsRows.push({ name: cells[1].replace(/https?:\/\/\S+/g, "").replace(/\s+/g, " ").trim() || url,
        url, evidence_ptr: `NEEDS.md:L${i + 1}`, source_channel: "needs", status: cells[3],
        text: lines[i].trim() }); // #208 T2:原文行快照入工件——span 门(逐字回引)对账面在轮工件内,回放可回算;registry 面结构性(canonicalJson 面),不带 text
    }
  }
  writeJson(path.join(ctx.dir, A.DISCOVER_SCAN), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
    candidates: [...registry, ...needsRows],
    channels: { registry: { status: "ok", n: registry.length }, needs: { status: "ok", n: needsRows.length },
      web: { status: "placeholder", n: 0, note: "T3 #209 接线(PR3a web_search 渠道;T1 只留占位留痕)" } } });
}

// MEASURE:确定性存在性测量(T1 最小面=本地证据存在性:shortlist 候选 evidence_ptr 是否在
// SCAN 宇宙内可解析);探针/对照接线=T3 #209。超时/未测=uncertainty hold(无证据≠清白:
// 不入队也不除名,留痕待复测),不炸轮。
async function MEASURE(def, ctx) {
  const scan = j(path.join(ctx.dir, A.DISCOVER_SCAN)) ?? { candidates: [] };
  const shortlist = j(path.join(ctx.dir, A.DISCOVER_SHORTLIST)) ?? { candidates: [] };
  const results = shortlist.candidates.map((c) => ({
    candidate: candidateSlug(c.name), name: c.name,
    // #208 T2:存在性从「指针集合相等」升格为三形解析(scanEvidenceFace:透传/工件/URL)
    // ——T1 自报语义「是否在 SCAN 宇宙内可解析」的真实现;幽灵指针/幽灵 URL=not ok。
    evidence_local_ok: scanEvidenceFace(scan, c.evidence_ptr).ok,
    status: "uncertainty", // T1 全 hold(测量面未接线);T3 接线后按实测分
    uncertainty_reason: "measure 面未接线(T3 #209):存在性=SCAN 宇宙三形指针解析(citation.mjs),网络测量+阳性对照留待接线",
    exclusivity_estimate: c.exclusivity_estimate ?? null, control_executable: null }));
  writeJson(path.join(ctx.dir, A.DISCOVER_MEASURE), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
    results, n: results.length, hold_n: results.length });
}

// ENQUEUE:只写不动作(#139):过三判据(证据存在性全过+排他率≥0.25+阳性对照可执行)的候选
// 经 queue-lock(#139 flock 路径,与 python append_queue 同构互锁)写 queue.md 一行候选卡;
// 不开票不接源。判据=常量(spec:判据在代码不在 prompt,模型无权改)。写败=fail-closed infra
// (证据不灭失优先于轮成功)。
export const ENQUEUE_EXCLUSIVITY_GATE = 0.25; // spec T1:排他率预估门槛(常量,步/门同源导出;模型无权改判据——判据在代码不在 prompt;T4 北星校准走旋钮前不动)
const candidateSlug = (name) => String(name).toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 32) || "cand"; // queue source 面 ^[a-z0-9_]{1,32}$ 适配
async function ENQUEUE(def, ctx) {
  const shortlist = j(path.join(ctx.dir, A.DISCOVER_SHORTLIST)) ?? { candidates: [] };
  const measure = j(path.join(ctx.dir, A.DISCOVER_MEASURE)) ?? { results: [] };
  const byCand = new Map(measure.results.map((r) => [r.candidate, r]));
  const enqueued = []; const skipped = [];
  for (const c of shortlist.candidates) {
    const m = byCand.get(candidateSlug(c.name));
    const reasons = [];
    if (!m || m.evidence_local_ok !== true) reasons.push("evidence");
    if (!m || !((m.exclusivity_estimate ?? -1) >= ENQUEUE_EXCLUSIVITY_GATE)) reasons.push("exclusivity");
    if (!m || m.control_executable !== true) reasons.push("control");
    (reasons.length ? skipped : enqueued).push({ candidate: candidateSlug(c.name), name: c.name, reasons });
  }
  const queueFile = path.join(ctx.opsRoot, "queue.md");
  for (const row of enqueued) {
    const m = byCand.get(row.candidate);
    const r = await appendQueueRowLocked({ queueFile, round: ctx.roundId, action: "ENQUEUE", source: row.candidate, predicate: null,
      evidence: [
        { call_id: "d3-measure", field: "evidence_local_ok", value: true },
        { call_id: "d3-measure", field: "exclusivity_estimate", value: m.exclusivity_estimate },
        { call_id: "d3-measure", field: "control_executable", value: true }] }, { env: ctx.env ?? {} });
    if (!r.ok) throw infra(`queue 写败(${row.candidate}):${r.code ?? "io_error"}`); // fail-closed
  }
  writeJson(path.join(ctx.dir, A.DISCOVER_ENQUEUE), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
    gate_exclusivity: ENQUEUE_EXCLUSIVITY_GATE, enqueued, skipped, n_enqueued: enqueued.length, n_skipped: skipped.length });
}

const SCRIPT = { PROBE, VERIFY, DISPATCH, ITEMIZE, RETRO, ANCHOR_SWEEP, CLOSE, SCAN, MEASURE, ENQUEUE };
export async function runStage(def, ctx) {
  const fn = SCRIPT[def.name];
  if (!fn) throw Object.assign(new Error(`脚本步未实现:${def.name}(定义表与实现漂移)`), { code: "infra" });
  return fn(def, ctx);
}
const MODEL_IO = {
  TRIAGE: { input: triageInput, consume: triageConsume, finalize: null },
  DEEP: { input: deepInput, consume: deepConsume, finalize: deepFinalize, items: deepItems },
  SYNTH: { input: synthInput, consume: synthConsume, finalize: null },
  SHORTLIST: { input: shortlistInput, consume: shortlistConsume, finalize: null }, // #207 T1:发现轮唯一模型步;零工具注入(T3 #209 接线点)
};
export const modelIO = (def) => {
  const io = MODEL_IO[def.name];
  if (!io) throw Object.assign(new Error(`模型步未装配:${def.name}`), { code: "infra" });
  return io;
};
export function forEachItems(def, ctx) { return modelIO(def).items?.(ctx) ?? [null]; }
