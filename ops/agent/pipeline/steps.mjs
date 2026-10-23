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
import { itemSignature, fullDedupKey, createOpsItem, parseItemsTree, CAUSE_GROUP_BY_BUCKET } from "./ops-items.mjs"; // 条目库桥(P4 #166:接 _ops_items 同空间)

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
  writeJson(path.join(ctx.dir, "02-verify-survivors.json"), { survivors,
    known_noise_digest: rules.rules.map(({ id, action, match, note, review_at }) => ({ id, action, match, note, review_at })),
    rules_version: rules.version, in_flight_n: flight.size });
  writeJson(path.join(ctx.dir, "02-verify-suppressed.json"), { suppressed, rules_version: rules.version });
}

async function DISPATCH(def, ctx) {
  const h = j(path.join(ctx.dir, "03-triage-hypotheses.json")) ?? { hypotheses: [] };
  const sorted = [...(h.hypotheses ?? []).filter((x) => x.need_deep)]
    .sort((a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9));
  // 每假设新上下文的 bundle 装配面(C稿 §2.4-1):hid/假设全文/≤3 相关判例命中(锚域词表×该
  // 假设旗标确定性选锚,缺件锄宁少算不注入)/预算余额;TRIAGE→DEEP 隔真脚本步,门永远有件可查。
  const surv = new Map((j(path.join(ctx.dir, "02-verify-survivors.json"))?.survivors ?? []).map((s) => [s.signal_id, s]));
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
  writeJson(path.join(ctx.dir, "04-dispatch-bundles.json"), { budget_cny: ctx.budgetCny, est_per_hyp_cny: EST_PER_HYP_CNY, max_hypotheses: MAX_DEEP_HYPOTHESES,
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
  const hyps = j(path.join(ctx.dir, "03-triage-hypotheses.json"))?.hypotheses ?? [];
  const verdictsFile = j(path.join(ctx.dir, "05-deep-verdicts.json")) ?? { verdicts: [], degraded: [] };
  const verdicts = verdictsFile.verdicts, degradedVerdicts = verdictsFile.degraded;
  const truncated = j(path.join(ctx.dir, "04-dispatch-bundles.json"))?.truncated ?? [];
  const surv = new Map((j(path.join(ctx.dir, "02-verify-survivors.json"))?.survivors ?? []).map((s) => [s.signal_id, s]));
  const rows = [];
  for (const v of verdicts) rows.push({ hid: v.hid, hyp: hyps.find((h) => h.signal_id === v.hid) ?? {}, outcome: v.verdict, one_line: v.one_line, deep_evidence: v.evidence ?? [] });
  for (const v of degradedVerdicts) rows.push({ hid: v.hid, hyp: hyps.find((h) => h.signal_id === v.hid) ?? {}, outcome: "unresolved", one_line: v.one_line, deep_evidence: [] }); // 重试尽降级 unresolved 同入清单(证据不灭失)
  for (const t of truncated) rows.push({ hid: t.hid, hyp: hyps.find((h) => h.signal_id === t.hid) ?? {}, outcome: "unresolved", one_line: `截尾交人裁(${t.reason})`, deep_evidence: [] });
  for (const h of hyps.filter((x) => !x.need_deep)) rows.push({ hid: h.signal_id, hyp: h, outcome: "watch", one_line: h.one_line, deep_evidence: [] }); // 未深验假设直入清单
  // replay 确定性:原轮 manifest 在场时逐 hid 回声原 outcome(审计重放不改生产条目面);
  // 缺席(原轮 ITEMIZE 半程崩溃重放)走桥内文件回声救回部分写入。
  const origByHid = new Map((ctx.state?.replay_of ? j(path.join(ctx.opsRoot, "rounds", ctx.state.replay_of, "06-itemize-manifest.json"))?.rows ?? [] : []).map((r) => [r.hid, r]));
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
  const suppressed = j(path.join(ctx.dir, "02-verify-suppressed.json"))?.suppressed?.length ?? 0;
  writeJson(path.join(ctx.dir, "06-itemize-manifest.json"), { created, reopened, deduped, suppressed, rows: out });
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
  prompt_pkg: { hypothesis: "金轨迹保活 canned 假设:若冻结读数为真,HEAD 复测 age_days 应保持不变", cause_class: "frozen_feed", severity: "low", probe_hint: "reprobe_get", url: "(canned)", precedent_hits: [] } };
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
// DEEP 登记表重建(P4 #166):逐假设 transcript 的 registry_seed 行 → Map(call_id → {tool, sc});
// 宿主回填(G_DEEP 写前语义门同源重算)与门重算共用本面(单一解析语义,不另起炉灶)。
export function deepSeeds(dir, hid = null) {
  const m = new Map();
  const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => /^05-deep-.*-transcript\.jsonl$/.test(f)
    && (hid === null || f === `05-deep-${hidSlug(hid)}-transcript.jsonl`)) : [];
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
  writeJson(path.join(ctx.dir, `05-deep-${hidSlug(item.hid)}.json`), { hid: item.hid, ...(item.golden ? { golden: true } : {}), ...v, evidence });
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
  // 条目明细(ADR 0006:报告=条目集只读渲染;异常清单每行对应真实条目)——直读本轮 manifest rows
  // (P4 #166:真条目在 ops/items 树,轮内产物面=manifest 行,item_id 供四键走查对号)
  const rows = j(path.join(ctx.dir, "06-itemize-manifest.json"))?.rows ?? [];
  const itemsDetail = rows.map(({ source, verdict, severity, suggested_action, one_line, item_id }) => ({ source, verdict, severity, suggested_action, one_line, item_id }));
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
