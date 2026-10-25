#!/usr/bin/env node
// pipeline.mjs — 健康轮轮次状态机宿主(P2 比稿 C P0 骨架;spec #161;详设 notes/p2-design-c-pipelinefirst-2026-10-23.md §2/§4)。
// 用法: node ops/agent/pipeline.mjs health [--round-id ID] [--fixtures DIR]          ← 跑一轮(显式 --fixtures=faux 面;缺省=真 provider 面,#170)
//       node ops/agent/pipeline.mjs replay <round_id> [--from STAGE] [--to STAGE] [--dry] [--fixtures DIR]
// 三层职责线(DESIGN.md §2):本文件=宿主层只编排——定义表(数据)驱动引擎,门全机检(pipeline/gates.mjs),
// 脚本步(pipeline/steps.mjs)只测量不判断,模型步经 pipeline/faux.mjs(#170:fixtures 面 faux/运行面真 provider;选择=selectModelFace,面记入 state.model_face)。
// 契约沿用 agent.mjs spawn 契约:stdout 末行=轮次信封(现有形状只增 pipeline 扩展字段,C稿 §4.4);
// stderr 阶段行第三次修约(C稿 §5.2):[stage] <NAME> start / done gate=PASS dur=412s artifact=01-….json /
// fail gate=G_X code=<九词> reason=…;错误码沿用九词闭集零新词(哪一步失败由 pipeline.stages[].status 表达);
// 用法错=纯 stderr+exit 2 不发 JSON。env 面 ∈ SPAWN_CONTRACT_ENV(agent.mjs 唯一详述点):
// DOCS_ROOT(rounds/rules/retro 派生根)+OPS_PIPELINE(legacy|pipeline 迁移开关)+OPS_PIPELINE_BUDGET_CNY(预算门)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DOCS_ROOT } from "./tools.mjs";
import { ERROR_CODES } from "./error-codes.mjs"; // 2026-10-24 断环:不再 import agent.mjs(委派路径顶层 await 死锁,见 error-codes.mjs 头注)
import * as steps from "./pipeline/steps.mjs";
import * as gates from "./pipeline/gates.mjs";
import { runModelStep, selectModelFace } from "./pipeline/faux.mjs";
import * as budget from "./pipeline/budget.mjs"; // #199 A1:预算四界旋钮+执法纯函数(单源)
import { readBreakerKnobs } from "./tools/breaker.mjs"; // #199 B:P16 跨轮熔断旋钮(轮始校验同 budget 判例;零环)

const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_FIXTURES_DIR = path.join(AGENT_DIR, "fixtures", "pipeline"); // 缺省 fixtures 路径(自测显式引用=同路径显式面,#170)
// ops 树 = DOCS_ROOT 派生(C稿 §5.2,同 queue/artifacts 判例);按调用 env 解析(P4 #166:
// 条目库真写面 ops/items 共树,自测需逐轮独立 DOCS 树隔离在飞面;CLI 面=进程 env 同一拼写)。
const opsRootOf = (env) => path.join(env.DOCS_ROOT ?? process.env.DOCS_ROOT ?? DOCS_ROOT, "ops");

// ctx 派生路径单一形状源(mkCtx 与崩溃恢复重建共用;终审 smell 收口:加字段不再两处改)
const ctxPaths = (OPS_ROOT, roundId) => ({
  rulesFile: path.join(OPS_ROOT, "rules", "suppressions.json"),
  itemsDir: path.join(OPS_ROOT, "items"), // 在飞条目面真源(_ops_items 树,P2 #164;P4 起兼 ITEMIZE 落笔面)
  retroFile: path.join(OPS_ROOT, "retro", `${roundId}.json`), retroAuditKey: roundId,
});

// ── 轮次定义表(数据非代码;C稿 §2.2 十状态;加状态须过 spec 变更+三元组铁律:无工件/无门/无失败语义=不配当状态)──
// 每态:name/kind(script|model|bookend|terminal)/model(提示词键;执行面选择=faux.mjs selectModelFace,#170)/工件清单(out)/门/失败语义三元组
// fail={retry,terminal,degrade?,perItem?}(重试上限/终态错误码∈九词闭集/降级路径);skipWhen=命名谓词闭集。
// 注:IDLE 准入门(车道/预算/同型在飞,C稿 §2.2 十态之一)不在此表——属宿主接线,落 P5(#167);
// 本表=跑步态集+CLOSE+FAILED,防误读十状态缺一(审后注 reviewer P2-1)。
export const HEALTH_PIPELINE = [
  { name: "PROBE", kind: "script", model: null,
    out: ["01-probe-freshness.tsv", "01-probe-matrix.json", "01-probe-summary.json"],
    gate: "G_PROBE", artifact: "01-probe-summary.json",
    fail: { retry: 2, terminal: "infra" } }, // 暂态(超时/网络)重试≤2;门败=终态 infra(工件保留)
  { name: "VERIFY", kind: "script", model: null,
    out: ["02-verify-survivors.json", "02-verify-suppressed.json", "02-verify-rules.json"],
    gate: "G_VERIFY", artifact: "02-verify-survivors.json",
    fail: { retry: 0, terminal: "infra" } }, // 规则文件坏=终态 infra;规则零命中=空集照常通过(降级直通);02-verify-rules.json=轮次时点版快照(#164 审 P2-6,#167)
  { name: "TRIAGE", kind: "model", model: "health/triage",
    out: ["03-triage-hypotheses.json", "03-triage-transcript.jsonl"],
    gate: "G_TRIAGE", artifact: "03-triage-hypotheses.json",
    fail: { retry: 1, terminal: "model_face" } }, // schema 违例重试≤1;幸存集空=门直过(零假设合法)
  { name: "DISPATCH", kind: "script", model: null, skipWhen: "no_need_deep",
    out: ["04-dispatch-bundles.json"], gate: "G_DISPATCH", artifact: "04-dispatch-bundles.json",
    fail: { retry: 0, degrade: "budget_truncate", terminal: "infra" } }, // 预算不够=降级截尾(非失败);bug=infra
  { name: "DEEP", kind: "model", model: "health/deep", forEach: "bundles",
    out: ["05-deep-verdicts.json"], gate: "G_DEEP", artifact: "05-deep-verdicts.json",
    fail: { retry: 1, perItem: "unresolved", terminal: "model_face" } }, // 真开启 P4 #166:逐假设单发新上下文(独立轮窗),
  // 微探针闭集 ≤3/假设,evidence=A 一律选择对(宿主回填值,G_DEEP 写前语义门逐字回引);单假设败=降级 unresolved;全败=终态 model_face。
  // 不设 skipWhen——零 need_deep 轮仍跑空转金轨迹 canned 回路(#162 审 P2-2,裁定①)。
  { name: "ITEMIZE", kind: "script", model: null,
    out: ["06-itemize-manifest.json"], gate: "G_ITEMIZE", artifact: "06-itemize-manifest.json",
    fail: { retry: 0, terminal: "verify_failed" } }, // 条目写败=可重入终态(条目库幂等兜底)
  { name: "SYNTH", kind: "model", model: "health/synth",
    out: ["07-synth-report.md", "07-synth-transcript.jsonl"], gate: "G_SYNTH", artifact: "07-synth-report.md",
    fail: { retry: 1, terminal: "empty_text" } }, // 契约违例重试≤1;条目已落库不回滚(证据不灭失)
  { name: "ANCHOR_SWEEP", kind: "script", model: null,
    out: ["08-anchor-sweep.json", "08-anchor-sweep-exits.json"], gate: "G_ANCHOR_SWEEP", artifact: "08-anchor-sweep.json",
    fail: { retry: 0, degrade: "anchor_finding", terminal: "infra" } }, // #182(#180 首批租户,加状态经 spec 授权):
  // 生产查询路径锚巡检(ANCHORS 全集,锚集真源=backend/ipdb/_eval/anchors.py);锚 finding 不持门
  // (失败=工件 finding 面,轮照常成功);求值面死=RETRO 同款降级旁路(失败信封落件证据不灭失);
  // 内部 bug=infra 终态。位置=SYNTH 后 RETRO 前(finding 先于台账收口,勘察件 §2.1)。
  { name: "RETRO", kind: "script", model: null,
    out: ["../retro/<round_id>.json"], gate: "G_RETRO", artifact: "retro/<round_id>.json",
    fail: { retry: 0, degrade: "skip_retro", terminal: "ledger_failed" } }, // 候选失败=降级;台账/sandbox=终态
  { name: "CLOSE", kind: "bookend", model: null, out: [], gate: "G_CLOSE", artifact: "(envelope)",
    fail: { retry: 0, terminal: "infra" } }, // 信封写失败=infra;重放不入 CLOSE(原轮次时序)
  { name: "FAILED", kind: "terminal", model: null, out: [], gate: null, artifact: null,
    fail: { retry: 0, terminal: null } }, // 终态书挡:工件全保留,replay 可救
];
const byName = (n) => HEALTH_PIPELINE.find((d) => d.name === n);
const RUNNABLE = HEALTH_PIPELINE.filter((d) => d.kind === "script" || d.kind === "model").map((d) => d.name); // replay 段闭集
const STAGE_PREFIX = { PROBE: "01-", VERIFY: "02-", TRIAGE: "03-", DISPATCH: "04-", DEEP: "05-", ITEMIZE: "06-", SYNTH: "07-", ANCHOR_SWEEP: "08-" }; // 工件序号前缀固定步序(C稿 §4.1;replay 前置工件复制消费,#182 补 08-)

// ══ 引擎(通用代码,≤300 行纪律:下段至文件尾只做定义表驱动的编排,不判任何具体步)══
const nowIso = () => new Date().toISOString();
const roundIdNow = (type) => { const d = new Date(), p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}-${type}`; };
const atomicWrite = (p, text) => { fs.writeFileSync(`${p}.tmp`, text); fs.renameSync(`${p}.tmp`, p); }; // 沿 _ops_store.atomic_write_text 判例
const j = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const SKIP_WHEN = { // 命名谓词闭集(定义表数据引用;新增=spec 变更)
  no_need_deep: (ctx) => {
    const b = j(path.join(ctx.dir, "04-dispatch-bundles.json"));
    if (b) return !(b.bundles ?? []).length; // DISPATCH 已跑:零 bundle(零假设或预算全截尾)
    const h = j(path.join(ctx.dir, "03-triage-hypotheses.json"));
    return !((h?.hypotheses ?? []).some((x) => x.need_deep));
  },
};

function mkCtx(opts, io) {
  const type = opts.type ?? "health";
  if (type !== "health") throw Object.assign(new Error(`P0 仅健康轮管线(discover 立项后自持定义表):${type}`), { code: "bad_round" });
  const roundId = opts.roundId ?? roundIdNow(type);
  if (!/^\d{4}-\d{2}-\d{2}-\d{4}-health(-r\d+)?$/.test(roundId))
    throw Object.assign(new Error(`round_id 形状须 YYYY-MM-DD-HHMM-health:${roundId}`), { code: "bad_round" });
  const budgetRaw = io.env.OPS_PIPELINE_BUDGET_CNY ?? process.env.OPS_PIPELINE_BUDGET_CNY ?? "0.05";
  const budgetCny = +budgetRaw; // NaN 静默放行=审后修 P2-4:非法值退出 2 不带病跑轮
  if (!Number.isFinite(budgetCny) || budgetCny < 0)
    throw Object.assign(new Error(`OPS_PIPELINE_BUDGET_CNY 须为非负数,得到:${budgetRaw}`), { usage: true });
  const budgetKnobs = budget.readBudgetKnobs(io.env); // 四界旋钮(#199 A1;校验同 BUDGET_CNY 判例:非法=用法错 exit 2 不带病跑轮)
  const breakerKnobs = readBreakerKnobs(io.env); // #199 B:熔断旋钮轮始校验(非法=用法错 exit 2 同判例;快照消费=CLOSE)
  const fixturesDir = path.resolve(opts.fixturesDir ?? DEFAULT_FIXTURES_DIR);
  const modelFace = selectModelFace({ fixturesExplicit: opts.fixturesDir != null, inherited: opts.inheritedModelFace ?? null }); // 面选择(#170:显式 fixtures=faux/继承面/缺省 real;纯函数真源在 faux.mjs)
  const state = { schema: 1, round_id: roundId, type, pipeline_mode: io.env.OPS_PIPELINE ?? process.env.OPS_PIPELINE ?? "legacy",
    status: "in_flight", stage: null, stages: [], budget_cny: budgetCny, budget_knobs: budgetKnobs, fixtures_dir: fixturesDir, model_face: modelFace, prompt_hashes: {},
    started_at: nowIso(), updated_at: nowIso(), resume_count: 0, replay_of: opts.replayOf ?? null };
  const OPS_ROOT = opsRootOf(io.env); // 本轮 ops 树(rounds/rules/retro/items 同根;items=条目库真写面 P4 #166)
  return { type, roundId, dir: path.join(OPS_ROOT, "rounds", roundId), env: io.env, log: io.log,
    fixturesDir, modelFace, budgetCny, budgetKnobs, breakerKnobs, modelCalls: 0, dupRegistry: new Map(), opsRoot: OPS_ROOT, ...ctxPaths(OPS_ROOT, roundId),
    ledgerFile: io.env.LEDGER_FILE ?? process.env.LEDGER_FILE ?? path.join(DOCS_ROOT, "ops", "ledger.md"),
    pkg: null, verify: null, envelope: null, usage: { input: 0, output: 0, totalTokens: 0, cost: 0 }, state };
}
const writeState = (ctx) => { ctx.state.updated_at = nowIso(); atomicWrite(path.join(ctx.dir, "state.json"), JSON.stringify(ctx.state, null, 2) + "\n"); };
const addUsage = (to, from) => { for (const k of ["input", "output", "totalTokens", "cost"]) to[k] += from?.[k] ?? 0; };

function composeEnvelope(ctx, { ok, code, message }) { // 现有形状只增 pipeline 扩展字段(C稿 §4.4;旧消费方透传零改)
  const pipeline = { round_id: ctx.roundId, resumed_from: ctx.resumedFrom ?? null, replayed_of: ctx.state.replay_of, stages: ctx.state.stages };
  if (ctx.state.finding_exits) pipeline.finding_exits = ctx.state.finding_exits; // #184:出口三件套信封留痕(webhook 未配置=skip 痕;RESUME 面经 state 持久)
  if (ok) return { ok: true, round: ctx.type, pkg: ctx.pkg, usage: { ...ctx.usage }, queue_writes: [],
    verify: ctx.verify ?? { ok: true, cited: 0 }, pipeline };
  const e = { ok: false, round: ctx.type, error: { code, message } };
  if (ctx.pkg) e.pkg = ctx.pkg; // 包已落盘才回传(轮次失败≠工件灭失)
  e.pipeline = pipeline;
  return e;
}
function failStage(ctx, def, rec, e, gateRec) {
  const code = ERROR_CODES.includes(e?.code) ? e.code : "infra"; // 无 code/闭集外归兜底(同 agent.mjs)
  rec.status = "failed";
  if (!ctx.state.stages.includes(rec)) ctx.state.stages.push(rec);
  ctx.state.status = "failed";
  ctx.state.stage = "FAILED"; // 终态书挡(定义表 FAILED 项)
  writeState(ctx);
  ctx.log(`[stage] ${def.name} fail gate=${gateRec && !gateRec.pass ? def.gate : "-"} code=${code} reason=${e?.message ?? String(e)}`);
  return { code, message: `${def.name}:${e?.message ?? String(e)}` };
}

// 模型步执行(引擎数据循环:DEEP 逐假设独立子进程位=P4;P0 同进程 faux,循环语义已就位)。
// 单发步(TRIAGE/SYNTH)的门评估入重试圈:C稿 §2.2「契约违例重试≤1(同提示词重发)」——门败与
// schema 违例同面重试;逐假设步(DEEP forEach)的门评收编尾后一次(部分态评门=假阴性嗓音)。
async function runModelStage(def, ctx, rec) {
  ctx.budgetKnobs ??= budget.readBudgetKnobs(ctx.env ?? {}); // 手撞 ctx/resume 重建面兑底(#199 A1;幂等)
  ctx.modelCalls ??= 0;
  const io = steps.modelIO(def);
  const items = def.forEach ? steps.forEachItems(def, ctx) : [null];
  const usage = { input: 0, output: 0, totalTokens: 0, cost: 0 };
  const degradedItems = [];
  let failed = 0;
  for (const item of items) {
    if (ctx.resuming && steps.modelItemComplete(def, ctx, item)) continue; // resume 三规则②:工件齐→不重花 token,finalize/门照跑(#167)
    let done = false;
    for (let a = 0; a <= def.fail.retry && !done; a++) {
      rec.attempts += 1;
      // #199 A1 四界检查点①③:attempt 前查调用数帽与墙钟(违界即停:不重试不降级,哲学①已写工件照留)
      if (budget.overCallsCap(ctx.modelCalls, ctx.budgetKnobs.maxModelCalls))
        throw Object.assign(new Error(`预算四界①:模型调用将超帽(已计 ${ctx.modelCalls}+1 > ${ctx.budgetKnobs.maxModelCalls},OPS_PIPELINE_MAX_MODEL_CALLS)`), { code: "budget_exceeded", fatalBudget: true });
      if (budget.overWallClock(ctx.state.started_at, ctx.budgetKnobs.wallClockS))
        throw Object.assign(new Error(`预算四界③:墙钟 ${budget.elapsedWallS(ctx.state.started_at).toFixed(1)}s 超帽 ${ctx.budgetKnobs.wallClockS}s(OPS_PIPELINE_WALL_CLOCK_S)`), { code: "wall_clock_exceeded", fatalBudget: true });
      ctx.modelCalls += 1;
      try {
        const r = await runModelStep(def, ctx, item);
        ctx.state.prompt_hashes[`${def.name}${item ? `:${item.hid}` : ""}`] = r.prompt_sha; // replay 审计面(C稿 §4.5)
        await io.consume(ctx, item, r);
        addUsage(usage, r.usage);
        // #199 A1 四界检查点②④:结算后查 token 轨迹与花费帽(轮内累计=已入库 ctx.usage+本步未收编 usage)
        const roundTokens = ctx.usage.totalTokens + usage.totalTokens;
        const roundCost = ctx.usage.cost + usage.cost;
        if (budget.overTokenBudget(roundTokens, ctx.budgetKnobs.tokenBudget))
          throw Object.assign(new Error(`预算四界②:token 轨迹 ${roundTokens} 超预算 ${ctx.budgetKnobs.tokenBudget}(OPS_PIPELINE_TOKEN_BUDGET)`), { code: "budget_exceeded", fatalBudget: true });
        if (budget.overSpendCap(roundCost, ctx.budgetKnobs.spendCapCny))
          throw Object.assign(new Error(`预算四界④:花费 ¥${roundCost.toFixed(8)} 超帽 ¥${ctx.budgetKnobs.spendCapCny}(OPS_PIPELINE_SPEND_CAP_CNY)`), { code: "budget_exceeded", fatalBudget: true });
        if (!def.forEach) {
          const gateRec = gates.evalStageGate(def, ctx);
          gates.appendGate(ctx.dir, ctx.roundId, gateRec);
          if (!gateRec.pass) throw Object.assign(new Error(`门败 ${def.gate}:${gateRec.reason}`), { code: gateRec.code ?? def.fail.terminal, gateRec });
        }
        done = true;
      } catch (e) {
        if (e?.fatalBudget) throw e; // #199 A1:违界即停——重试=再烧 token、perItem 降级=继续跑后续假设,均违宁少算
        if (a === def.fail.retry) {
          if (def.fail.perItem && items.length) { failed += 1; done = true; // 单假设降级 unresolved(不终态)
            degradedItems.push({ hid: item?.hid ?? def.name, verdict: "unresolved", evidence: [], one_line: `重试尽降级 unresolved(${e.message})` });
          } else throw e;
        } else ctx.log(`[stage] ${def.name} retry(a=${a + 1}:${e.message})`);
      }
    }
  }
  if (def.fail.perItem && items.length && failed === items.length)
    throw Object.assign(new Error(`全部 ${items.length} 假设失败(model_face)`), { code: "model_face" }); // 全败=终态(C稿 §2.2)
  if (io.finalize) await io.finalize(ctx, { degradedItems });
  return { usage, degraded: degradedItems.length > 0, gateDone: !def.forEach }; // gateDone=门已在圈内评过留痕,runStages 不重复评
}

// 段执行器(runPipeline 与 replay 共用):dry=只跑门不调模型不跑步(C稿 §4.5);
// skippedInOriginal=原件轮里被 SKIP_WHEN 跳过的步——dry 审计对这些步跳门(审后修 P2-3):
// 缺席工件判门败是假阴性,静轮 dry 首审即触发;原件 stages[].status=skipped 即不评其门。
async function runStages(ctx, { fromIdx = 0, toIdx = RUNNABLE.length - 1, dry = false, skippedInOriginal = [], resume = false } = {}) {
  const recordedAs = (name) => ctx.state.stages.find((r) => r.name === name && ["done", "skipped", "degraded", "dry"].includes(r.status));
  for (let i = fromIdx; i <= toIdx; i++) {
    const def = byName(RUNNABLE[i]);
    if (resume && recordedAs(def.name)) { // resume:已记录步零重入(幂等;state 与工件一致以工件+门为准的例外=已过关步)
      ctx.state.stage = def.name;
      ctx.log(`[stage] ${def.name} done gate=SKIP(resume:已记录${recordedAs(def.name).status}) dur=0s artifact=-`);
      continue;
    }
    if (dry && skippedInOriginal.includes(def.name)) {
      const srec = { name: def.name, status: "dry-skip", attempts: 0, dur_ms: 0, usage: null };
      ctx.state.stages.push(srec);
      ctx.state.stage = def.name;
      writeState(ctx);
      ctx.log(`[stage] ${def.name} done gate=SKIP(dry:原件 skipped) dur=0s artifact=-`);
      continue;
    }
    // #199 A1 四界检查点③(步边界):墙钟超=终态先于步体(已记录步零重入/dry 零调用不查;
    // resume 沿原 started_at 续算——恢复晚于帽即拒,同 16h 陈旧防线语义)
    ctx.budgetKnobs ??= budget.readBudgetKnobs(ctx.env ?? {});
    if (!dry && budget.overWallClock(ctx.state.started_at, ctx.budgetKnobs.wallClockS)) {
      const wrec = { name: def.name, status: "done", attempts: 0, dur_ms: 0, usage: null };
      return failStage(ctx, def, wrec, Object.assign(new Error(`预算四界③:墙钟 ${budget.elapsedWallS(ctx.state.started_at).toFixed(1)}s 超帽 ${ctx.budgetKnobs.wallClockS}s(OPS_PIPELINE_WALL_CLOCK_S)`), { code: "wall_clock_exceeded" }), null);
    }
    const rec = { name: def.name, status: dry ? "dry" : "done", attempts: 0, dur_ms: 0, usage: null };
    const t0 = performance.now();
    let gateRec = null, degraded = null, gateDone = false;
    try {
      if (!dry && def.skipWhen && SKIP_WHEN[def.skipWhen]?.(ctx)) {
        rec.status = "skipped";
        ctx.state.stages.push(rec);
        ctx.state.stage = def.name;
        writeState(ctx);
        ctx.log(`[stage] ${def.name} done gate=SKIP(${def.skipWhen}) dur=0s artifact=-`); // 转移图 TRIAGE→ITEMIZE 直达
        continue;
      }
      ctx.log(`[stage] ${def.name} start`);
      if (!dry) {
        if (resume && def.kind === "model" && !def.forEach && steps.modelItemComplete(def, ctx, null)) {
          // resume 三规则②(单发步腿):工件齐 → 只补门评估不重花 token(#167,C稿 §4.6)
          rec.recovered = "gate_only";
          const gr = gates.evalStageGate(def, ctx);
          gates.appendGate(ctx.dir, ctx.roundId, gr);
          if (!gr.pass) throw Object.assign(new Error(`门败 ${def.gate}:${gr.reason}`), { code: gr.code ?? def.fail.terminal, gateRec: gr });
          rec.dur_ms = Math.round(performance.now() - t0);
          ctx.state.stages.push(rec);
          ctx.state.stage = def.name;
          writeState(ctx);
          ctx.log(`[stage] ${def.name} done gate=PASS dur=${Math.round(rec.dur_ms / 1000)}s artifact=${def.artifact ?? "-"} recovered=gate_only`);
          continue;
        }
        if (def.kind === "model") {
          const r = await runModelStage(def, ctx, rec);
          rec.usage = r.usage;
          addUsage(ctx.usage, r.usage); // 顶层 usage=各模型步之和(旧字段「整轮求和」语义保持)
          degraded = r.degraded ? { degraded: `${def.fail.perItem} 降级` } : null;
          gateDone = r.gateDone; // 单发步门已在重试圈内评过留痕,不重复评
        } else {
          let attempt = 0;
          for (;;) {
            rec.attempts += 1;
            try { degraded = (await steps.runStage(def, ctx)) ?? null; break; }
            catch (e) {
              if (attempt < def.fail.retry) { attempt += 1; ctx.log(`[stage] ${def.name} retry${attempt}(${e.message})`); continue; }
              throw e;
            }
          }
        }
      }
      if (degraded?.skipGate) gates.appendGateBypass(ctx.dir, ctx.roundId, def, degraded.degraded);
      else if (gateDone) { /* 单发模型步门已在重试圈内评过留痕(见 runModelStage) */ }
      else {
        gateRec = gates.evalStageGate(def, ctx);
        gates.appendGate(ctx.dir, ctx.roundId, gateRec);
        if (!gateRec.pass) throw Object.assign(new Error(`门败 ${def.gate}:${gateRec.reason}`), { code: gateRec.code ?? def.fail.terminal });
      }
      rec.dur_ms = Math.round(performance.now() - t0);
      if (degraded) rec.status = "degraded";
      if (resume) rec.recovered = def.kind === "model" && def.forEach ? "gate_partial" : "rerun"; // DEEP=部分假设补门部分重跑;单发模型步/脚本步=重入(#167 三规则①③)
      ctx.state.stages.push(rec);
      ctx.state.stage = def.name;
      writeState(ctx); // 每步边界原子写(C稿 §4.6)
      ctx.log(`[stage] ${def.name} done gate=${degraded?.skipGate ? "BYPASS" : "PASS"} dur=${Math.round(rec.dur_ms / 1000)}s artifact=${def.artifact?.replace("<round_id>", ctx.roundId) ?? "-"}`);
    } catch (e) {
      rec.dur_ms = Math.round(performance.now() - t0);
      return failStage(ctx, def, rec, e, e?.gateRec ?? gateRec); // 单发步门败时门记录随错误带回(fail 行 gate 名不丢)
    }
  }
  return null;
}

async function finishClose(ctx, io) { // CLOSE 书挡:存在性校验→信封门→state 终写→stdout 末行(重放不入此步)
  const def = byName("CLOSE");
  const rec = { name: "CLOSE", status: "done", attempts: 1, dur_ms: 0, usage: null };
  const t0 = performance.now();
  ctx.log("[stage] CLOSE start");
  try {
    await steps.runStage(def, ctx);
    ctx.state.stages.push(rec);
    const envelope = composeEnvelope(ctx, { ok: true });
    ctx.envelope = envelope;
    const gr = gates.evalStageGate(def, ctx);
    gates.appendGate(ctx.dir, ctx.roundId, gr);
    if (!gr.pass) throw Object.assign(new Error(`门败 G_CLOSE:${gr.reason}`), { code: "infra" });
    rec.dur_ms = Math.round(performance.now() - t0);
    ctx.state.status = "done";
    ctx.state.stage = "CLOSE";
    writeState(ctx);
    ctx.log(`[stage] CLOSE done gate=PASS dur=${Math.round(rec.dur_ms / 1000)}s artifact=(envelope)`);
    io.stdout.write(JSON.stringify(envelope) + "\n");
    return { ok: true, envelope, roundId: ctx.roundId, dir: ctx.dir };
  } catch (e) {
    const f = failStage(ctx, def, rec, e, null);
    const envelope = composeEnvelope(ctx, { ok: false, ...f });
    io.stdout.write(JSON.stringify(envelope) + "\n");
    return { ok: false, envelope, roundId: ctx.roundId, dir: ctx.dir };
  }
}

const bindIo = (opts) => {
  const stdout = opts.stdout ?? process.stdout, stderr = opts.stderr ?? process.stderr;
  return { env: opts.env ?? process.env, stdout, stderr, log: (l) => stderr.write(`${l}\n`) };
};

export async function runPipeline(opts = {}) {
  const io = bindIo(opts);
  const ctx = mkCtx(opts, io);
  const emitFail = (code, message) => { const envelope = composeEnvelope(ctx, { ok: false, code, message });
    io.stdout.write(JSON.stringify(envelope) + "\n"); return { ok: false, envelope, roundId: ctx.roundId, dir: ctx.dir }; };
  // #199 A2 月度 kill switch 准入:mkCtx 后、建轮目录前(拒跑零侧写:无目录无 state);
  // 读数入 state(A5 CLOSE 工件面)。est=本轮预算(BUDGET_CNY 准告警线上界,宁少算口径)。
  const admission = await budget.monthlyAdmission({ ledgerFile: ctx.ledgerFile, capCny: ctx.budgetKnobs.monthlyCapCny, estCny: ctx.budgetCny });
  if (!admission.ok) {
    ctx.log(`[admission] budget_monthly refused month=${admission.month} spend=${admission.spend} est=${admission.est} cap=${admission.cap} skipped=${admission.skipped}`);
    try { await budget.appendRefusalTrace(ctx.ledgerFile, { est: ctx.budgetCny, cap: ctx.budgetKnobs.monthlyCapCny }, io.env); }
    catch (e) { ctx.log(`[admission] 拒跑留痕行写败(不翻转裁决):${e.message}`); } // 台账写败不吞拒跑:宁拒不跑
    return emitFail("budget_monthly", `月度预算拒跑:当月已花 ¥${admission.spend} + 本轮预算 ¥${admission.est} > 月帽 ¥${admission.cap}(OPS_PIPELINE_MONTHLY_CAP_CNY;当月 ${admission.counted} 行计入,${admission.skipped} 行缺 cost 跳过不猜)`);
  }
  ctx.state.monthly_admission = admission; // A5 CLOSE 工件读数面(观察非裁决)
  if (fs.existsSync(path.join(ctx.dir, "state.json"))) return emitFail("bad_round", `rounds/${ctx.roundId} 已存在(同 id 重跑走 replay)`);
  fs.mkdirSync(ctx.dir, { recursive: true });
  writeState(ctx); // 轮次目录 + state.json 建立
  const failure = await runStages(ctx);
  if (failure) return emitFail(failure.code, failure.message);
  return finishClose(ctx, io);
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const copyTree = (src, dst, skip) => { // 原件零改写:只读复制(哲学①证据永不灭失)
  for (const f of fs.readdirSync(src)) {
    if (skip.includes(f)) continue;
    const s = path.join(src, f), d = path.join(dst, f);
    if (fs.statSync(s).isDirectory()) { fs.mkdirSync(d, { recursive: true }); copyTree(s, d, []); }
    else fs.copyFileSync(s, d);
  }
};
export async function runReplay(opts = {}) {
  const io = bindIo(opts);
  const { roundId, from = "PROBE", to = "RETRO", dry = false } = opts;
  for (const s of [from, to]) if (!RUNNABLE.includes(s))
    throw Object.assign(new Error(`replay 步名须 ∈ {${RUNNABLE.join("|")}}(CLOSE 属原轮时序不入重放;FAILED 非可跑步),得到:${s}`), { usage: true });
  if (RUNNABLE.indexOf(from) > RUNNABLE.indexOf(to)) throw Object.assign(new Error(`--from(${from}) 不得晚于 --to(${to})`), { usage: true });
  const OPS_ROOT = opsRootOf(io.env);
  const srcDir = path.join(OPS_ROOT, "rounds", String(roundId));
  if (!fs.existsSync(path.join(srcDir, "state.json"))) throw Object.assign(new Error(`rounds/${roundId} 无 state.json(无可重放轮次)`), { usage: true });
  const roundsDir = path.join(OPS_ROOT, "rounds");
  const seq = 1 + Math.max(0, ...fs.readdirSync(roundsDir)
    .map((f) => { const m = f.match(new RegExp(`^${escapeRe(String(roundId))}-r(\\d+)$`)); return m ? +m[1] : 0; }));
  const replayId = `${roundId}-r${seq}`;
  const dir = path.join(roundsDir, replayId);
  fs.mkdirSync(dir, { recursive: true });
  // 原件零改写(哲学①):只读复制。dry=审计面,全量工件复制供门重算;非 dry 只复制段前置
  // 工件(按序号前缀;段内输出重执行再生——itemize 幂等重入若见复制件会把 created 记成 deduped,
  // 与段内重跑的模型步 canned 产物计数不一致,属假门败)。条目真写在 ops/items 树(P4 #166),
  // 不属轮次工件面;ITEMIZE 重放走原轮 manifest 回声(零写,replay 确定性)。
  if (dry) copyTree(srcDir, dir, ["state.json", "gates.json"]);
  else {
    const prefixes = RUNNABLE.slice(0, RUNNABLE.indexOf(from)).map((n) => STAGE_PREFIX[n]).filter(Boolean);
    for (const f of fs.readdirSync(srcDir)) {
      if (f === "state.json" || f === "gates.json" || fs.statSync(path.join(srcDir, f)).isDirectory()) continue;
      if (prefixes.some((p) => f.startsWith(p))) fs.copyFileSync(path.join(srcDir, f), path.join(dir, f));
    }
  }
  // 原件面读取(#170 继承;先于 mkCtx——面选择消费)与 skipped 集(审后修 P2-3 dry 跳门)。
  // 面继承:真轮重放保真再花真钱;--fixtures=faux 零成本审计 override;pre-#170 轮恒 faux。
  const origState = JSON.parse(fs.readFileSync(path.join(srcDir, "state.json"), "utf8"));
  const origFace = origState?.model_face ?? null;
  const origSkipped = (origState?.stages ?? [])
    .filter((s) => s?.status === "skipped").map((s) => s.name);
  const ctx = mkCtx({ ...opts, roundId: replayId, replayOf: roundId, inheritedModelFace: origFace ?? "faux" }, io);
  ctx.retroAuditKey = dry ? roundId : replayId; // dry 审原件工件;重执行审重放自产
  writeState(ctx);
  const failure = await runStages(ctx, { fromIdx: RUNNABLE.indexOf(from), toIdx: RUNNABLE.indexOf(to), dry, skippedInOriginal: origSkipped });
  ctx.state.status = failure ? "failed" : "done"; // 重放目录必终态(#167:boot 恢复扫描不把 -rN 目录误当活轮)
  writeState(ctx);
  const rp = path.join(dir, "07-synth-report.md");
  if (fs.existsSync(rp)) ctx.pkg = rp; // 重放段产物或复制件
  const envelope = failure ? composeEnvelope(ctx, { ok: false, ...failure }) : composeEnvelope(ctx, { ok: true });
  io.stdout.write(JSON.stringify(envelope) + "\n");
  return { ok: !failure, envelope, roundId: replayId, dir };
}

// runResume — crash 恢复续跑(#167,C稿 §4.6 三规则):同目录续跑 in_flight 轮(区别于 replay 的
// -rN 新目录审计面)。三规则:①脚本步幂等重入(重跑);②模型步工件齐→只补门不重花 token;
// ③工件缺→重跑(损失仅该步 token)。每轮至多一次自动恢复(state.resume_count);二次=infra
// 终态交人(boot 扫描侧已拦,此处兜底);龄>16h(2×8h cron)拒绝(同兜底)。
export async function runResume(opts = {}) {
  const io = bindIo(opts);
  const { roundId } = opts;
  if (!/^\d{4}-\d{2}-\d{2}-\d{4}-health$/.test(String(roundId)))
    throw Object.assign(new Error(`resume 目标须原件轮 id(YYYY-MM-DD-HHMM-health,-rN 重放目录不入恢复):${roundId}`), { usage: true });
  const OPS_ROOT = opsRootOf(io.env);
  const dir = path.join(OPS_ROOT, "rounds", String(roundId));
  const state = j(path.join(dir, "state.json"));
  if (!state) throw Object.assign(new Error(`rounds/${roundId} 无 state.json(无可恢复轮次)`), { usage: true });
  const infra = (msg) => Object.assign(new Error(msg), { code: "infra" });
  if (state.status !== "in_flight") throw infra(`resume 仅 in_flight 态(现 ${state.status});终态轮走 replay`);
  const ageH = (Date.now() - Date.parse(state.updated_at)) / 3_600_000;
  if (!Number.isFinite(ageH) || ageH > 16)
    throw infra(`in_flight 龄 ${Number.isFinite(ageH) ? ageH.toFixed(1) : "?"}h>16h(2×8h cron)——不自动恢复,标 FAILED(infra, stale) 由 boot 扫描处置`);
  if ((state.resume_count ?? 0) >= 1)
    throw infra(`自动恢复已用尽(resume_count=${state.resume_count};每轮至多一次,二次崩溃=FAILED(infra) 交人,replay 提示见台账)`);
  // ctx 重建:state.json 是唯一真源(budget/fixtures 等从崩溃现场复原;usage 从零计——
  // 崩溃尝试的已花量不可回收,恢复轮 usage=下界,宁少算)
  const ctx = { type: state.type, roundId, dir, env: io.env, log: io.log,
    // resume 重开调用登记表(观察面从零起;断点前已花量不可回收,同 usage 下界口径)
    budgetCny: state.budget_cny, budgetKnobs: state.budget_knobs ?? budget.readBudgetKnobs(io.env), breakerKnobs: readBreakerKnobs(io.env), modelCalls: 0, dupRegistry: new Map(), fixturesDir: state.fixtures_dir, modelFace: state.model_face ?? "faux", opsRoot: OPS_ROOT,
    ...ctxPaths(OPS_ROOT, roundId), // 单一形状源(mkCtx 同;终审 smell 收口)
    ledgerFile: io.env.LEDGER_FILE ?? process.env.LEDGER_FILE ?? path.join(DOCS_ROOT, "ops", "ledger.md"),
    pkg: null, verify: null, envelope: null, usage: { input: 0, output: 0, totalTokens: 0, cost: 0 }, state };
  const pending = RUNNABLE.filter((n) => !state.stages.some((r) => r.name === n && ["done", "skipped", "degraded", "dry"].includes(r.status)));
  ctx.resumedFrom = pending[0] ?? null; // 信封 resumed_from(恢复起点;全记录齐=仅 CLOSE 收口)
  ctx.resuming = true; // 引擎旗:模型步工件齐者补门不重跑(runModelStage/runStages 消费)
  state.resume_count = (state.resume_count ?? 0) + 1;
  writeState(ctx); // 计数先行:恢复中再崩即触发「至多一次」防线
  ctx.log(`[stage] RESUME start from=${ctx.resumedFrom ?? "CLOSE"} resume_count=${state.resume_count}`);
  const failure = await runStages(ctx, { resume: true });
  if (failure) { // failStage 已在 runStages catch 内落终态(state=failed/FAILED);此处只补信封
    const envelope = composeEnvelope(ctx, { ok: false, ...failure });
    io.stdout.write(JSON.stringify(envelope) + "\n");
    return { ok: false, envelope, roundId, dir };
  }
  return finishClose(ctx, io);
}

// main(argv, io) — 可测入口(agent.mjs 同型):返回退出码 0/1/2;用法错=纯 stderr 不发 JSON
export async function main(argv, io = {}) {
  const env = io.env ?? process.env;
  const stdout = io.stdout ?? process.stdout, stderr = io.stderr ?? process.stderr;
  const usage = "用法: node ops/agent/pipeline.mjs health [--round-id ID] [--fixtures DIR]\n      node ops/agent/pipeline.mjs replay <round_id> [--from STAGE] [--to STAGE] [--dry] [--fixtures DIR]\n      node ops/agent/pipeline.mjs resume <round_id>(crash 恢复,C稿 §4.6;boot 扫描/运维手用)";
  const flag = (n) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : undefined; };
  const bad = (m) => { stderr.write(`${m}\n${usage}\n`); return 2; };
  const mode = env.OPS_PIPELINE ?? process.env.OPS_PIPELINE ?? "legacy"; // 迁移开关(P2 桥消费;本 CLI 校验值闭集并记入 state.json)
  if (!["legacy", "pipeline"].includes(mode)) return bad(`OPS_PIPELINE 须 legacy|pipeline,得到:${mode}`);
  const [cmd, pos] = argv;
  const emitInfra = (e) => { const code = ERROR_CODES.includes(e?.code) ? e.code : "infra";
    stdout.write(JSON.stringify({ ok: false, round: "health", error: { code, message: e?.message ?? String(e) } }) + "\n"); return 1; };
  try {
    if (cmd === "health") {
      const r = await runPipeline({ type: "health", roundId: flag("--round-id"), fixturesDir: flag("--fixtures"), env, stdout, stderr });
      return r.ok ? 0 : 1;
    }
    if (cmd === "resume") {
      if (!pos || pos.startsWith("-")) return bad("resume 缺 <round_id>");
      const r = await runResume({ roundId: pos, env, stdout, stderr });
      return r.ok ? 0 : 1;
    }
    if (cmd === "replay") {
      if (!pos || pos.startsWith("-")) return bad("replay 缺 <round_id>");
      const r = await runReplay({ roundId: pos, from: flag("--from"), to: flag("--to"), dry: argv.includes("--dry"),
        fixturesDir: flag("--fixtures"), env, stdout, stderr });
      return r.ok ? 0 : 1;
    }
    return bad(`未知子命令:${cmd ?? "(无)"}`);
  } catch (e) {
    if (e?.usage) return bad(e.message);
    return emitInfra(e);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = await main(process.argv.slice(2)); // exitCode 而非 exit:stdout 单行 JSON 必须完整落管(agent.mjs 同判例)
}
