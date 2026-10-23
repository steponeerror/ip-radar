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
import { FROZEN_DAYS, matrixScanCli, matrixArtifactText, resolveField } from "../tools.mjs";
import { loadAnchors, anchorSelect, HIT_CAP } from "./anchors.mjs"; // 锚域词表×旗标选锚(B 三件②;DISPATCH 逐假设判例命中 ≤3,P4 #166)
import { itemSignature, fullDedupKey, createOpsItem, CAUSE_GROUP_BY_BUCKET } from "./ops-items.mjs"; // 条目库桥(P4 #166:接 _ops_items 同空间)

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

// ── 在飞条目集(P2 真读 _ops_items 面;同因在飞不重问=P1 探测器双开防线同律)────
// 在飞 = status ∈ {active, snoozed}(_ops_items.ITEM_STATUSES;done/dismissed 终态不算,
// 复开走 supersedes 链指);同因判定 = 源级对齐(dedup_key.source;probe_class/error_signature
// 全签 P4)。坏条目文件宁响亮不猜测(_ops_items._parse_item 同律)——在飞集不可靠则停轮。
export function readInFlightItems(itemsDir) {
  if (!fs.existsSync(itemsDir)) return [];
  const out = [];
  for (const f of fs.readdirSync(itemsDir).filter((x) => x.endsWith(".md")).sort()) {
    const text = fs.readFileSync(path.join(itemsDir, f), "utf8");
    const fm = text.split(/^---\s*$/m)[1];
    if (!fm) throw infra(`条目 frontmatter 缺:${f}(_ops_items 十字段冻结面)`);
    const status = (fm.match(/^status:[ \t]*(\S+)/m) ?? [])[1];
    if (!status) throw infra(`条目 status 行缺:${f}`);
    const dk = {};
    let inDk = false;
    for (const line of fm.split("\n")) {
      if (/^dedup_key:/.test(line)) { inDk = true; continue; }
      if (!inDk) continue;
      const kv = line.match(/^[ \t]+([a-z_]+):[ \t]*(.+)$/);
      if (kv) dk[kv[1]] = kv[2].trim().replace(/^["']|["']$/g, "");
      else break;
    }
    if (!dk.source) throw infra(`条目 dedup_key.source 缺:${f}`);
    out.push({ item_id: f.replace(/\.md$/, ""), status, source: dk.source,
      probe_class: dk.probe_class ?? null, error_signature: dk.error_signature ?? null });
  }
  return out;
}
// 在飞源索引:source → 在飞条目 id 列表(VERIFY 抑制溯源 + 门重算共用)
export const inFlightSources = (items) => {
  const m = new Map();
  for (const i of items) {
    if (i.status !== "active" && i.status !== "snoozed") continue;
    if (!m.has(i.source)) m.set(i.source, []);
    m.get(i.source).push(i.item_id);
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
  fs.writeFileSync(path.join(ctx.dir, "01-probe-freshness.tsv"), tsv);
  // matrix(P1,#163)=真扫描单源 tools.mjs matrixScanCli(legacy health_snapshot 同路径同解析;位等价门=同 stub
  // 下两腿产物逐字节同文,自测 selftest-pipeline 位等价例)。产物路径对照:legacy=<ts>-matrix-scan.json
  // (artifactPath ts-slug 族,ops/artifacts/);管线=01-probe-matrix.json(§4.1 序号前缀族)。
  // 失败=嵌套信封不阻轮(C稿 §2.2,legacy 同语义);差异仅落盘面:legacy 失败不落件只回 sc 嵌套信封,
  // 管线按 §4.1 工件契约落信封进件(证据不灭失)。
  const m = await matrixScanCli();
  fs.writeFileSync(path.join(ctx.dir, "01-probe-matrix.json"), m.ok ? matrixArtifactText(m.d) : JSON.stringify(m.env, null, 1));
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
  writeJson(path.join(ctx.dir, "01-probe-summary.json"), { ok: true, round_id: ctx.roundId, urls_n: urls.length,
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
  const summary = j(path.join(ctx.dir, "01-probe-summary.json"));
  if (!summary) throw infra("01-probe-summary.json 不可解析");
  const raw = j(ctx.rulesFile);
  if (!raw) throw infra(`抑制规则库不可解析:${ctx.rulesFile}(规则零命中=空集照常过;文件坏=终态)`);
  const rules = normalizeRules(raw); // 闭集校验+review_at 规范化;坏=infra 终态(C稿 §2.2)
  const flight = inFlightSources(readInFlightItems(ctx.itemsDir)); // 同因在飞不重问:真读 _ops_items 面(P2,#164)
  const survivors = [], suppressed = [];
  for (const f of summary.flags) {
    const rule = rules.rules.find((r) => ruleMatch(r.match, f)); // 首命中,规则序即优先级
    const key = dedupKey(f);
    if (rule?.action === "suppress") { suppressed.push({ ...f, dedup_key: key, rule_id: rule.id }); continue; } // 留痕抑制
    if (flight.has(f.source)) { // 同源在飞不重问(源级同因;full 签 P4):证据不灭失,压掉的进留痕工件可翻案
      suppressed.push({ ...f, dedup_key: key, rule_id: "in_flight", in_flight_items: flight.get(f.source) });
      continue;
    }
    survivors.push(rule?.action === "annotate" ? { ...f, dedup_key: key, annotated_rule: rule.id } : { ...f, dedup_key: key });
  }
  // known_noise_digest:已知误判模式机器格式(C稿 §3.5——TRIAGE 不注入判例全文,只吃本 digest;
  // 含 review_at 供 RETRO P5 到点复审)。
  writeJson(path.join(ctx.dir, "02-verify-survivors.json"), { survivors,
    known_noise_digest: rules.rules.map(({ id, action, match, note, review_at }) => ({ id, action, match, note, review_at })),
    rules_version: rules.version, in_flight_n: flight.size });
  writeJson(path.join(ctx.dir, "02-verify-suppressed.json"), { suppressed, rules_version: rules.version });
}

async function DISPATCH(def, ctx) {
  const h = j(path.join(ctx.dir, "03-triage-hypotheses.json")) ?? { hypotheses: [] };
  const sorted = [...(h.hypotheses ?? []).filter((x) => x.need_deep)]
    .sort((a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9));
  const truncated = [];
  while (sorted.length && sorted.length * EST_PER_HYP_CNY > ctx.budgetCny + 1e-9) truncated.push(sorted.pop()); // 预算降级:severity 截尾,被截标 unresolved(budget)
  const bundles = sorted.map((x) => ({ hid: x.signal_id, budget_cny: +(ctx.budgetCny / sorted.length).toFixed(4),
    prompt_pkg: { hypothesis: x.hypothesis, cause_class: x.cause_class, severity: x.severity, probe_hint: x.probe_hint, url: x.signal_id } }));
  writeJson(path.join(ctx.dir, "04-dispatch-bundles.json"), { budget_cny: ctx.budgetCny, est_per_hyp_cny: EST_PER_HYP_CNY,
    bundles, truncated: truncated.map((x) => ({ hid: x.signal_id, severity: x.severity, reason: "unresolved(budget)" })),
    degraded: truncated.length > 0 });
  return truncated.length ? { degraded: `budget_truncate:${truncated.length} 条按 severity 截尾标 unresolved(budget)(预算 ${ctx.budgetCny}¥)` } : undefined;
}

const ACTION_BY = { confirmed: "review_freeze", refuted: "digest_ignore", unresolved: "human_ruling", watch: "watch" }; // 查表闭集(C稿 §2.4-4)
async function ITEMIZE(def, ctx) {
  const hyps = j(path.join(ctx.dir, "03-triage-hypotheses.json"))?.hypotheses ?? [];
  const verdictsFile = j(path.join(ctx.dir, "05-deep-verdicts.json")) ?? { verdicts: [], degraded: [] };
  const verdicts = verdictsFile.verdicts, degradedVerdicts = verdictsFile.degraded;
  const truncated = j(path.join(ctx.dir, "04-dispatch-bundles.json"))?.truncated ?? [];
  const surv = new Map((j(path.join(ctx.dir, "02-verify-survivors.json"))?.survivors ?? []).map((s) => [s.signal_id, s]));
  const rows = [];
  for (const v of verdicts) rows.push({ hid: v.hid, hyp: hyps.find((h) => h.signal_id === v.hid) ?? {}, outcome: v.verdict, one_line: v.one_line });
  for (const v of degradedVerdicts) rows.push({ hid: v.hid, hyp: hyps.find((h) => h.signal_id === v.hid) ?? {}, outcome: "unresolved", one_line: v.one_line }); // 重试尽降级 unresolved 同入清单(证据不灭失)
  for (const t of truncated) rows.push({ hid: t.hid, hyp: hyps.find((h) => h.signal_id === t.hid) ?? {}, outcome: "unresolved", one_line: "预算截尾,交人裁" });
  for (const h of hyps.filter((x) => !x.need_deep)) rows.push({ hid: h.signal_id, hyp: h, outcome: "watch", one_line: h.one_line }); // 未深验假设直入清单
  const itemsDir = path.join(ctx.dir, "items");
  fs.mkdirSync(itemsDir, { recursive: true });
  let created = 0, deduped = 0;
  const names = [];
  for (const r of rows) {
    const f = surv.get(r.hid) ?? {};
    const item = { dedup_key: dedupKey(f), source: f.source ?? host(f.url ?? r.hid), bucket: f.bucket ?? "unknown",
      verdict: r.outcome, severity: r.outcome === "refuted" ? "low" : (r.hyp.severity ?? "low"), // refuted 恒 low 消化条目(附带三小裁②,2026-10-23 裁)
      suggested_action: ACTION_BY[r.outcome] ?? "human_ruling", one_line: r.one_line ?? r.hyp.one_line ?? "", round_id: ctx.roundId };
    const name = `${hidSlug(item.dedup_key)}.json`;
    const p = path.join(itemsDir, name);
    if (fs.existsSync(p)) { deduped += 1; names.push(name); continue; } // create_item 幂等兜底同语义(P4 换真条目库);原件不改写
    writeJson(p, item);
    created += 1;
    names.push(name);
  }
  const suppressed = j(path.join(ctx.dir, "02-verify-suppressed.json"))?.suppressed?.length ?? 0;
  writeJson(path.join(ctx.dir, "06-itemize-manifest.json"), { created, reopened: 0, deduped, suppressed, items: names }); // reopened=P4 接条目库在飞集后启用
}

async function RETRO(def, ctx) {
  const usage = `in=${ctx.usage.input} out=${ctx.usage.output} total=${ctx.usage.totalTokens} cost=${ctx.usage.cost.toFixed(8)}`;
  try { await sh("ledger_append", ["health", "faux-pipeline", usage, `pipeline:${ctx.roundId}`], 120_000, ctx.env); } // 台账先记(faux 零成本仍记行)
  catch (e) { throw Object.assign(new Error(`台账写败:${e.message}`), { code: "ledger_failed" }); }
  try { await sh("sandbox_assert", [], 60_000, ctx.env); } // 沙箱红线真执行(backend/frontend 零改动)
  catch (e) { throw Object.assign(new Error("sandbox_assert rc≠0(backend/frontend 污染)"), { code: "sandbox_violation" }); }
  let degraded;
  try { // 候选产出失败=降级(跳过 retro,轮仍成功);台账/sandbox 失败已先行终态(C稿 §2.2 语义序)
    const s = j(path.join(ctx.dir, "01-probe-summary.json"));
    fs.mkdirSync(path.dirname(ctx.retroFile), { recursive: true });
    writeJson(ctx.retroFile, { round_id: ctx.roundId, generated_at: new Date().toISOString(),
      flags_n: (s?.flags ?? []).length,
      survivors_n: j(path.join(ctx.dir, "02-verify-survivors.json"))?.survivors?.length ?? 0,
      suppressed_n: j(path.join(ctx.dir, "02-verify-suppressed.json"))?.suppressed?.length ?? 0,
      verdicts_n: j(path.join(ctx.dir, "05-deep-verdicts.json"))?.verdicts?.length ?? 0,
      candidates: [], // 候选确定性检查=P5 闭环(adopt_rule 四键通道);P0 空集起步
      sandbox_assert_pass: true, sandbox_assert_rc: 0, degraded: false });
  } catch (e) {
    degraded = { degraded: `skip_retro:retro 候选写败(${e.message})——轮仍成功`, skipGate: true };
  }
  return degraded;
}

async function CLOSE(def, ctx) { // 书挡步:存在性校验(闭合双层的外层)+ 信封原料
  const report = path.join(ctx.dir, "07-synth-report.md");
  ctx.pkg = fs.existsSync(report) ? report : null;
  if (!ctx.pkg) return;
  try {
    const v = await sh("verify_cited_precedents", [ctx.pkg], 120_000, ctx.env);
    ctx.verify = { ok: true, cited: Number((v.stdout.match(/(\d+) 条判例路径全部存在/) ?? [])[1] ?? 0) };
  } catch (e) { throw Object.assign(new Error(`判例存在性校验败:${e.message}`), { code: "verify_failed" }); }
}

// ── 模型步装配/收编(faux.mjs 真 Agent 循环的上下文与落盘;判断仍全在模型步+门)────────
// 空转金轨迹(#162 审 P2-2,2026-10-23 裁定①):零 need_deep 轮 DEEP 仍跑一条 canned-假设 faux 回路,
// 零成本保模型步回路活性;金轨迹 hid 不入 verdicts(不污染条目),由 deepFinalize 收编为 golden_track。
const GOLDEN_BUNDLE = { hid: "golden-track-canned", golden: true, budget_cny: 0,
  prompt_pkg: { hypothesis: "金轨迹保活 canned 假设:若冻结读数为真,HEAD 复测 age_days 应保持不变", cause_class: "frozen_feed", severity: "low", probe_hint: "reprobe_get", url: "(canned)" } };
function triageInput(ctx) {
  const sv = j(path.join(ctx.dir, "02-verify-survivors.json"));
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
  writeJson(path.join(ctx.dir, "03-triage-hypotheses.json"), h);
}
const deepItems = (ctx) => {
  const bundles = j(path.join(ctx.dir, "04-dispatch-bundles.json"))?.bundles ?? [];
  return bundles.length ? bundles : [GOLDEN_BUNDLE]; // 零 bundle=金轨迹回路(#162 审 P2-2,裁定①)
};
function deepInput(ctx, item) {
  return { systemPrompt: DEEP_STUB_PROMPT, userMsg: JSON.stringify({ hypothesis_bundle: item.prompt_pkg, budget_cny: item.budget_cny, ...(item.golden ? { golden: true } : {}) }) };
}
function deepConsume(ctx, item, { text }) {
  let v;
  try { v = JSON.parse(text); } catch { throw Object.assign(new Error(`DEEP 输出非 JSON(${item.hid})`), { code: "model_face" }); }
  if (!v || typeof v.verdict !== "string") throw Object.assign(new Error(`DEEP 输出缺 verdict(${item.hid})`), { code: "model_face" });
  writeJson(path.join(ctx.dir, `05-deep-${hidSlug(item.hid)}.json`), { hid: item.hid, ...(item.golden ? { golden: true } : {}), ...v });
}
function deepFinalize(ctx, { degradedItems }) { // 收编尾:逐假设工件 → 单 verdicts 集(降级项入 degraded;金轨迹单收 golden_track)
  const verdicts = [], golden = [];
  for (const b of deepItems(ctx)) {
    const f = j(path.join(ctx.dir, `05-deep-${hidSlug(b.hid)}.json`));
    if (!f) continue;
    const row = { hid: f.hid, verdict: f.verdict, evidence: f.evidence ?? [], one_line: f.one_line ?? "" };
    (f.golden || b.golden ? golden : verdicts).push(row);
  }
  writeJson(path.join(ctx.dir, "05-deep-verdicts.json"), { verdicts, degraded: degradedItems, golden_track: golden });
}
async function synthInput(ctx) {
  // 判例注入只在 SYNTH(闭合校验面集中,C稿 §3.5);检索词=锚域词表(B 三件②,P3 接线:
  // agent.mjs KWS.health 硬编码退役,词表单一真源=anchors-health.json)+ 锚词表×幸存旗标确定性选锚。
  const anchors = loadAnchors();
  const flags = j(path.join(ctx.dir, "02-verify-survivors.json"))?.survivors ?? [];
  const docsRoot = ctx.env.DOCS_ROOT ?? path.resolve(AGENT_DIR, "..", "..", "docs"); // 同 lib.sh 派生链
  const precDir = ctx.env.PRECEDENTS_DIR ?? path.join(docsRoot, "ops", "precedents");
  const onDisk = (n) => fs.existsSync(path.join(precDir, n)); // 锚选目标须在真源判例库在场(缺件锚宁少算不注入)
  const anchored = [...new Set(anchorSelect(anchors.anchors, flags))].filter(onDisk);
  const kws = [...new Set(anchors.anchors.flatMap((a) => a.keywords))];
  const inj = await sh("inject_precedents", kws, 120_000, ctx.env);
  const hitNames = [...inj.stdout.matchAll(/^- ([0-9]{4}-[0-9]{2}-[0-9]{2}-[^\s]+\.md)\s*$/gm)].map((m) => m[1]);
  const injected = [...new Set([...anchored, ...hitNames])].slice(0, HIT_CAP);
  // 条目明细(ADR 0006:报告=条目集只读渲染;异常清单每行对应真实条目)——直读本轮 items/ 工件
  const itemsDir = path.join(ctx.dir, "items");
  const itemsDetail = fs.existsSync(itemsDir) ? fs.readdirSync(itemsDir).filter((f) => f.endsWith(".json")).sort()
    .map((f) => j(path.join(itemsDir, f))).filter(Boolean)
    .map(({ source, verdict, severity, suggested_action, one_line }) => ({ source, verdict, severity, suggested_action, one_line })) : [];
  const input = { injected, manifest: j(path.join(ctx.dir, "06-itemize-manifest.json")), items: itemsDetail,
    verdicts_digest: (j(path.join(ctx.dir, "05-deep-verdicts.json"))?.verdicts ?? []).map(({ hid, verdict }) => ({ hid, verdict })),
    probe: (({ urls_n, buckets, matrix }) => ({ urls_n, buckets, matrix }))(j(path.join(ctx.dir, "01-probe-summary.json")) ?? {}) };
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
  fs.writeFileSync(path.join(ctx.dir, "07-synth-report.md"), text);
}

const SCRIPT = { PROBE, VERIFY, DISPATCH, ITEMIZE, RETRO, CLOSE };
export async function runStage(def, ctx) {
  const fn = SCRIPT[def.name];
  if (!fn) throw Object.assign(new Error(`脚本步未实现:${def.name}(定义表与实现漂移)`), { code: "infra" });
  return fn(def, ctx);
}
const MODEL_IO = {
  TRIAGE: { input: triageInput, consume: triageConsume, finalize: null },
  DEEP: { input: deepInput, consume: deepConsume, finalize: deepFinalize, items: deepItems },
  SYNTH: { input: synthInput, consume: synthConsume, finalize: null },
};
export const modelIO = (def) => {
  const io = MODEL_IO[def.name];
  if (!io) throw Object.assign(new Error(`模型步未装配:${def.name}`), { code: "infra" });
  return io;
};
export function forEachItems(def, ctx) { return modelIO(def).items?.(ctx) ?? [null]; }
