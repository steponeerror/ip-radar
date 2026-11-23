// tasks/discover-round.mjs — 发现轮 defineTask 化(票 #227 = T3;spec
// docs/superpowers/specs/2026-10-28-ops-agent-pidurable-migration-design.md;
// 旧发现六步管线化语义 = ADR 0010 / #207 T1)。
//
// ── 相位映射(旧步 → v2 相位;语义逐相位零复制驱动旧实现)──
//   SCAN→scan SHORTLIST→shortlist MEASURE→measure ENQUEUE→enqueue RETRO→retro CLOSE→close
//   脚本相位(scan/measure/enqueue/retro/close)直接 runStage 旧步(ops/pipeline-core/pipeline/steps.mjs
//   零 import 改动);SHORTLIST(唯一模型步)由本文件的会话提交驱动(见下)。
//   FAILED 旧终态书挡 → v2 terminal outcome {status:"failed"}(等价语义位)。
//
// ── 月轮↔conversation 粒度决策(T0 未决1;依 t1-notes 建议4)──
//   **每发现轮 = 自有 conversation**(harness.createConversation ownerless;轮任务
//   ownership={kind:"conversation"} 绑定该会话;root 会话只做骨架/引导,不承载轮)。
//   理由:①旧管线每模型步全新 Agent 上下文(faux.mjs runRealStep),跨轮零渗漏是旧律,
//     v2 一轮一会话同律保持;②轮的 transcript+UsageDoc(=spec 定案的台账真源)天然按轮
//     闭合:轮预算/轮恢复/轮审计各自完备,不掺宿主骨架噪声;③崩溃 resume 同会话继续,
//     requestId 幂等(见下)保证不双花;月度帽=跨轮共享(旧律,准入面 admitRound 已在
//     entry 执法,task 内不重复)——粒度选**轮**不选**月**,月粒度会把无关轮的失败恢复
//     耦合在同一会话里(一坏俱坏),违背 spec 定案 5「一轮=一次 submit/任务运行」。
//   T4(#228 健康轮)同法。
//
// ── requestId 纪律(幂等)──
//   attempt 1 = round-<roundId>-shortlist;attempt ≥2(上次已结算但答案坏:非 JSON 降级
//   不算坏,empty_text/infra 才重发)= round-<roundId>-shortlist-a<N>。崩溃发生在提交后、
//   结算前 → 同 key 重放 = pi-durable 恰好一次语义,恢复零新调用、零双花。
//
// ── 预算执法(T2 遗留1+2 收口)──
//   startedAtIso 在 initial() 一次性落 checkpoint,任何相位/恢复不改写 → 崩溃 resume
//   墙钟**续算**(遗留1);预算执法逐 attempt 双点(遗留2):
//     · 每相位头 stepBoundary(③墙钟)——脚本相位唯一执法点(旧律:脚本步无模型面);
//     · shortlist 相位内,每次 attempt 提交前 preModelCall(①调用数③墙钟)+ 提交结算后
//       postModelCall(②token[发现轮无 token 界=skip]④花费),usage 取会话 UsageDoc 活和
//       (sumUsageState;模型自报,与旧引擎同源)。
//   违约 → terminal failed outcome(旧 fatalBudget 不重试律;code=budget_exceeded|
//   wall_clock_exceeded,message 逐字 budget-guard 旧文案)。
//   checkpoint 在相位边界提交 modelCalls/usage;相位中途崩溃丢当次 attempt 计数
//   (requestId 重放恢复,不双花;少算 = 旧律宁少算)。
//
// ── 凭证红线 ── env 不入 checkpoint/input(过程 env 现读,同旧 runResume 现境面);
//   input 只带 roundId/knobs(轮始冻结)/budgetCny/modelFace/fixturesDir/admission/modelRef。
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { defineTask, UsageDoc } from "@earendil-works/pi-durable";
import { ctxShape, DISCOVER_PIPELINE } from "../../pipeline-core/pipeline.mjs"; // 零复制:ctx 形状+步定义表(单一真源)
import { runStage, modelIO } from "../../pipeline-core/pipeline/steps.mjs"; // 零复制:脚本步+模型 IO
import * as gates from "../../pipeline-core/pipeline/gates.mjs"; // 零复制:门评估+工件(gates.json)
import { readBreakerKnobs } from "../../pipeline-core/tools/breaker.mjs"; // 零复制(写侧经宿主适配器,见 tools/discovery-tools.mjs)
import { preModelCall, postModelCall, stepBoundary } from "./budget-guard.mjs"; // T2 执法面(文案/界值零漂移;token/cost 之和在本文件 roundUsage 逐字段展开)
import { ensureRoundHost, roundDupRegistries } from "../tools/discovery-tools.mjs"; // 轮级发现宿主(工具面+熔断写侧随迁)
import { enqueueStageIssueExit } from "../tools/enqueue-issues.mjs"; // #384:ENQUEUE 出口改 GH issue(PROPOSE 行停写;判据分类 v1 classifyEnqueue 单源)
import { benchScan } from "../bench/scan.mjs"; // bench SCAN 变体(票 #318:候选宇宙=仅 NEEDS 面;real 面走 runStage 旧步不受影响)
import { writeRoundReport } from "../../pipeline-core/pipeline/round-report.mjs"; // #403:轮报告件单源(v2 零复制 import v1;bench 轮照写=沙箱 opsRoot 天然隔离)
import { writeTerminalRoundState, writeOwnedRoundState } from "./round-state.mjs"; // #408:CLOSE 终态回写 state.json 镜像(与报告件同接线点);#415:失败/中止出口同写(属主判在内)
import { shortlistBenchPromptPath } from "../run-discover.mjs"; // bench SHORTLIST 基准提示词路径(票 #319;函数声明面循环安全:run-discover↔tasks 仅运行时互引)

const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);

export const DISCOVER_TASK_NAME = "ops.discover-round";
export const DISCOVER_PHASES = Object.freeze(["scan", "shortlist", "measure", "enqueue", "retro", "close"]);
const STAGE_OF_PHASE = Object.freeze({ scan: "SCAN", shortlist: "SHORTLIST", measure: "MEASURE", enqueue: "ENQUEUE", retro: "RETRO", close: "CLOSE" });
const defOf = (stage) => DISCOVER_PIPELINE.find((d) => d.name === stage);
const nextPhase = (p) => DISCOVER_PHASES[DISCOVER_PHASES.indexOf(p) + 1] ?? null;

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../.."); // ops/agent-v2/tasks → 仓根(3 层;4 层会落到 .worktrees/ 份外——T2 F1 同类病,钉死)
function resolveOpsRoot(env = process.env) { // 旧 opsRootOf 同算式(未导出,本地同形;drift 由 golden 对拍钉)
  return path.join(env.DOCS_ROOT ?? path.join(REPO_ROOT, "docs"), "ops");
}

// 崩溃钩子(测试面;env 现读不入档):进入指定相位头即 SIGKILL 自杀——上一相位 checkpoint
// 已提交,等价「该相位头进程崩溃」。真崩溃恢复路径与测试同一代码路径,零 mock。
function crashHook(phase) {
  if (process.env.OPS_V2_CRASH_AFTER_PHASE === phase) process.kill(process.pid, "SIGKILL");
}

// 工件漂移注入缝(测试面;env 现读不入档,crashHook 同律;工单 #415 专项 E2E 的 G_CLOSE 红注入面)。
// Why 需要缝:G_CLOSE 是回声哨——环内已执法(相位头 stepBoundary/attempt 前 preModelCall
// 与本门读同一计数、同一轮始冻结旋钮对象 input.knobs),读数≤帽在健康轮恒成立,门无法
// 自然红;门存在的理由=09-budget.json 工件漂移/篡改。本缝在 close 步后、G_CLOSE 门前把
// 读数改成超帽(=造一次漂移),门评估/门红出口零绕行(生产 env 不设=零行为变化)。
// 只装 discover:两处 #408 评审 P2-2 出口(步抛/G_CLOSE 红)在本文件;health 的 close 相位
// 是单 catch 汇聚(runClose),报告写败 E2E 已覆盖同一出口。
function budgetDriftHook(phase, ctx) {
  if (phase !== "close" || process.env.OPS_V2_FAULT !== "budget_drift") return;
  const file = path.join(ctx.dir, "09-budget.json");
  const b = JSON.parse(fs.readFileSync(file, "utf8"));
  b.readings.model_calls = b.env.OPS_DISCOVER_MAX_MODEL_CALLS + 1;
  fs.writeFileSync(file, JSON.stringify(b, null, 2) + "\n");
}

// bench 模式开关(票 #318,spec §3.1):input.benchOpsRoot 在场即 bench 盲测轮——
// opsRoot=沙箱 dev/bench-rediscover/<roundId>/(随 opsRoot 派生的 breaker/工件树全落沙箱),
// 台账随沙箱派生(breaker 三转移留痕面 mkBreaker 经 ctx.ledgerFile);SCAN=bench 变体,
// 相位截断 SCAN→SHORTLIST→CLOSE。real 轮(benchOpsRoot 缺席)行为零变化(golden 对拍钉)。
const isBench = (input) => typeof input?.benchOpsRoot === "string";

// ── 旧 ctx 重建(checkpoint→ctxShape;每相位一次,环境现读)──
function buildCtx(input, checkpoint) {
  const env = process.env; // 旧律:env 现读不入档(凭证红线;DOCS_ROOT 等由启动进程环境携带)
  const ctx = ctxShape({
    type: "discover",
    roundId: input.roundId,
    opsRoot: isBench(input) ? input.benchOpsRoot : resolveOpsRoot(env), // bench:沙箱 opsRoot(轮始冻结,恢复不改址)
    env,
    log: (line) => process.stderr.write(`[discover:${checkpoint.phase}] ${line}\n`), // P2-⑦ stdout 只留末行信封(ENVELOPE.md 冻结面);进度行走 stderr(run-health/model-round 同律)
    fixturesDir: input.fixturesDir,
    modelFace: input.modelFace,
    budgetCny: input.budgetCny,
    budgetKnobs: input.knobs,
    breakerKnobs: readBreakerKnobs(env),
    state: { // 旧 state.json 面(CLOSE/RETRO 读字段同旧;checkpoint 为真源,本对象仅为旧步接口适配)
      schema: 1,
      round_id: input.roundId,
      type: "discover",
      pipeline_mode: "pipeline",
      status: "running",
      stages: checkpoint.stages.map((r) => r.name),
      budget_cny: input.budgetCny,
      budget_knobs: input.knobs,
      fixtures_dir: input.fixturesDir,
      model_face: input.modelFace,
      prompt_hashes: checkpoint.prompt_hashes,
      started_at: checkpoint.startedAtIso, // 墙钟续算真源(遗留1)
      updated_at: new Date().toISOString(),
      resume_count: 0,
      replay_of: null,
      monthly_admission: input.admission ?? null,
    },
  });
  ctx.modelCalls = checkpoint.modelCalls;
  ctx.usage = { ...checkpoint.usage };
  if (isBench(input)) { // bench 台账随沙箱派生(runner admitRound 同路径;防 env 兜底漏到真实 docs);
    ctx.ledgerFile = path.join(input.benchOpsRoot, "ledger.md");
    ctx.bench = true; // bench 旗标(G_SHORTLIST 第四证据面开关,票 #319:转录行指针仅 bench 轮可过;真实轮恒缺席=零漂移)
  }
  return ctx;
}

// ── 建轮(旧 runPipeline 建轮段同义:同 id 守卫+mkdir+state 骨架;pipeline.mjs:397-399)──
// v2 真源=checkpoint;state.json 降级为进度镜像(观察面/旧工具兼容):每相位 advance 后
// 尽力重写。守卫只在全新启动(checkpoint.stages 空)时判:state.json 同 round 且 stages
// 非空=旧律同 id 重跑(bad_round,走 replay);stages 空=自家崩溃在建轮窗口,续跑;
// round_id 不符=异物树,bad_round。resume(stages 非空)不判不重建,只镜像推进。
function bootstrapRoundDir(ctx, checkpoint) {
  const stateFile = path.join(ctx.dir, "state.json");
  if (checkpoint.stages.length === 0) {
    let prior = null;
    try { prior = JSON.parse(fs.readFileSync(stateFile, "utf8")); } catch { /* 无=全新 */ }
    if (prior && (prior.round_id !== ctx.roundId || (Array.isArray(prior.stages) && prior.stages.length > 0)))
      throw Object.assign(new Error(`rounds/${ctx.roundId} 已存在(同 id 重跑走 replay)`), { code: "bad_round" });
    fs.mkdirSync(ctx.dir, { recursive: true });
    fs.writeFileSync(stateFile, JSON.stringify(ctx.state, null, 2) + "\n"); // 骨架镜像(崩溃可重写:stages 空判掎同轮自救)
    return;
  }
  fs.mkdirSync(ctx.dir, { recursive: true }); // resume:目录必在(防御);镜像在 advance 落
}
function mirrorState(ctx, checkpoint) { // 进度镜像(best-effort;真源=checkpoint,失败不炸轮)
  try {
    ctx.state.stages = checkpoint.stages.map((r) => r.name);
    ctx.state.updated_at = new Date().toISOString();
    fs.writeFileSync(path.join(ctx.dir, "state.json"), JSON.stringify(ctx.state, null, 2) + "\n");
  } catch { /* 镜像失败不阻断相位推进(哲学①:证据在 checkpoint+工件) */ }
}

// 相位完成落账:提交 checkpoint(相位推进+step 记录+计数),恢复点=相位边界(旧律同粒度)。
async function advance(runtime, context, checkpoint, patch = {}, ctx = null) {
  await runtime.commit((tx, cur) => ({
    status: "running",
    checkpoint: { ...cur.checkpoint, ...checkpoint, ...patch },
  }), context);
  if (ctx) mirrorState(ctx, checkpoint); // 尽力镜像(真源=checkpoint;失败不炸轮)
}
// #415:全部失败终态出口经此(与 outcome 终态同一出口);带 ctx=镜像同写 failed——属主判在
// writeOwnedRoundState(未建轮/异物树/同 id 旧轮终态件不写=不把别轮终态改判)。
async function finishFailed(runtime, context, error, ctx = null) {
  if (ctx) writeOwnedRoundState(ctx, "failed");
  return runtime.commit(() => ({
    status: "terminal",
    outcome: { status: "failed", error },
  }), context);
}
async function finishOk(runtime, context, result) {
  return runtime.commit(() => ({
    status: "terminal",
    outcome: { status: "completed", result },
  }), context);
}

// 信封(旧引擎 composeEnvelope 发现轮分支同形;pkg=null 恒、queue_writes 恒空数组——回放
// 兼容不删字段;键序=旧 golden pipeline_ok 键序断言面,T5 冻结面唯一 sanctioned 增键=
// issues_opened(#384 票面明令:issue 出口读数,digest/复盘可读;ENVELOPE.md 同步)。
function composeEnvelope(checkpoint, ctx) {
  return {
    ok: true,
    round: "discover",
    pipeline: {
      round_id: checkpoint.roundId,
      resumed_from: null, // v2 恢复证据在 task record(resume 后 startedAtIso 续算)+gates.json 双录;本字段恒 null(T5 冻结面再议)
      replayed_of: null,
      stages: checkpoint.stages,
    },
    pkg: null,
    queue_writes: [],
    issues_opened: checkpoint.issuesOpened ?? 0, // #384:enqueue 相位出口读数(真源=checkpoint;崩溃重入由 emit 守卫回补)
    usage: { ...ctx.usage },
    verify: { ok: true, cited: 0 },
  };
}

// ── 脚本相位(通用:预算墙钟头执法 → runStage 旧步 → 门评估+落 gates.json → checkpoint)──
async function scriptPhase(task, runtime, context, phase) {
  const input = task.input;
  const cur = task.state.checkpoint;
  crashHook(phase);
  const ctx = buildCtx(input, cur); // 终审 P1:提前构造——预算墙出口需要 ctx 定位轮目录写终态镜像(#415:本函数每个失败出口都带 ctx)
  if (isBench(input) && phase !== "scan" && phase !== "close") // fail-closed 防御:bench 轮相位截断后 measure/enqueue/retro 不可达,唯有 checkpoint 异物/篡改可至;真面 MEASURE=真网络探测,宁可终态不可误跑
    return finishFailed(runtime, context, { message: `BENCH:${STAGE_OF_PHASE[phase]} 相位越界(bench 轮=SCAN→SHORTLIST→CLOSE 截断)`, detail: { code: "infra", stage: STAGE_OF_PHASE[phase] } }, ctx);
  const b = stepBoundary({ roundType: "discover", knobs: input.knobs, startedAtIso: cur.startedAtIso }); // ③(每相位头;遗留2 脚本面)
  if (!b.ok) // #415:任意相位头预算墙=终态失败,镜像同写(属主判在 finishFailed;修前仅 close 相位写)
    return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: STAGE_OF_PHASE[phase] } }, ctx);
  const def = defOf(STAGE_OF_PHASE[phase]);
  if (phase === "scan") {
    try { bootstrapRoundDir(ctx, cur); } // 建轮同义(bad_round 域错→终态,同下)
    catch (e) { // P0-① 实测面:原裸抛逃逸 handler → 框架 fault+重启循环,真码永不落 outcome、信封恒 infra——收进同款 finishFailed(detail.code)终态
      return finishFailed(runtime, context, { message: `${def.name}:${e.message}`, detail: { code: e.code ?? "infra", stage: def.name } }, ctx);
    }
  }
  // dup 登记表跨相位同对象(CLOSE dup_top3 读数面;旧 ctx.dupRegistry 单例律)
  const dup = roundDupRegistries.get(runtime.conversationId);
  if (dup) ctx.dupRegistry = dup;
  else ensureRoundHost(ctx, runtime.conversationId); // 首相位(scan)亦预立:后续相位携带同表
  const stage = { name: def.name, status: "done", attempts: 1, dur_ms: 0, usage: null };
  const t0 = Date.now();
  let rec;
  try {
    // #384:enqueue 相位走 v2 issue 出口变体(benchScan 先例):达标候选(enqueued+
    // flagged)开 GH issue(needs-triage 人裁),queue.md PROPOSE 行停写;d4-enqueue.json
    // 与 v1 逐字段同形(判据分类 classifyEnqueue 单源),G_ENQUEUE 门面不变;issue 出口
    // fail-soft 永不败轮(工具面注释见 tools/enqueue-issues.mjs 头注)。
    rec = isBench(input) && phase === "scan" ? benchScan(ctx)
      : phase === "enqueue" ? await enqueueStageIssueExit(ctx)
      : await runStage(def, ctx); // bench SCAN 变体(零复制旧步;RETRO 可能 {degraded}
  } catch (e) { // 域失败=终态(旧 fail 三元组;handler 不抛=pi-durable fault 不消耗 restart)
    // #415:任意脚本相位步抛=轮终态失败,镜像同写(#408 评审 P2-2 的 close 相位出口 + mid-round 同形;
    // stages=checkpoint 已提交相位,未成相位不造名)
    return finishFailed(runtime, context, { message: `${def.name}:${e.message}`, detail: { code: e.code ?? "infra", stage: def.name } }, ctx);
  }
  stage.dur_ms = Date.now() - t0;
  if (rec?.degraded) { stage.status = "degraded"; stage.reason = rec.degraded; } // 旧 degrade 路径(RETRO skip_retro)
  // 脚本步恒零模型面:stage.usage=null(旧律;旧 golden pipeline_ok 断言=各步 usage 求和==信封 usage,
  // 轮累计回填每步会把 SHORTLIST 计数回声 6 次)
  const staged = [...cur.stages, stage];
  if (phase === "close") ctx.envelope = composeEnvelope({ ...cur, stages: staged }, ctx); // G_CLOSE 前置(旧引擎职责位;含 CLOSE 自身=旧门读 6 stages 序)
  budgetDriftHook(phase, ctx); // #415 测试面漂移注入(生产 env 不设=空操作)
  const gate = gates.evalStageGate(def, ctx);
  if (rec?.skipGate) gates.appendGateBypass(ctx.dir, ctx.roundId, def, String(rec.degraded));
  else gates.appendGate(ctx.dir, ctx.roundId, gate);
  if (!gate.pass) // 门红=终态(旧 fail-closed);#415:镜像同写(含 G_CLOSE 红=#408 评审 P2-2 第二出口)
    return finishFailed(runtime, context, { message: `GATE:${def.name}:${gate.reason}`, detail: { code: gate.code ?? "infra", stage: def.name } }, ctx);
  const next = nextPhase(phase);
  // #384:enqueue 相位把 issue 出口读数入 checkpoint(信封 issues_opened 真源;崩溃重入由 emit 守卫回补)
  const issuesPatch = phase === "enqueue" && typeof rec?.issues_opened === "number" ? { issuesOpened: rec.issues_opened } : {};
  const checkpoint = { ...cur, ...(next ? { phase: next } : {}), stages: [...cur.stages, stage], modelCalls: ctx.modelCalls, usage: { ...ctx.usage }, ...issuesPatch }; // 相位推进=phase 字段前移(缺它=同相位重跑死循环)
  if (!next) { // close 终态:#403 先落轮报告件(packages 断供修复;stages=staged 记录面,ctx.state.stages 是名字镜像),再 result=信封
    try {
      // 评审 P2-1:报告面 CLOSE 行 dur_ms 归零——实测值(Date.now()-t0)入文,则崩溃落在
      // 报告落盘与终态 commit 之间重入时幂等重写字节漂移;归零对齐 health/v1 的 0 值面
      // (round-report.mjs 头注「无时钟入文」不变量三面统一成立),checkpoint 侧实测值保留不动。
      const reportStages = staged.map((s) => (s.name === "CLOSE" ? { ...s, dur_ms: 0 } : s));
      writeRoundReport({ roundId: input.roundId, type: "discover", engine: "pipeline-v2", ctx, stages: reportStages, opsRoot: ctx.opsRoot });
      // #408:终态回写镜像(done;v1 finishClose 同序=报告→state;stages 名单推进到含
      // CLOSE;updated_at 保盘值=崩溃重入 CLOSE 重写字节级不变)
      writeTerminalRoundState(ctx, { status: "done", stages: staged.map((s) => s.name) });
    } catch (e) { // fail loud + v2 律(P0-①):handler 不裸抛(framework fault 重启循环)→ 终态失败留真码
      writeTerminalRoundState(ctx, { status: "failed" }); // #408:报告写败=轮失败,镜像终态 failed(v1 failStage 同语义;stages 止于 RETRO=close 未成不造 CLOSE 名)
      return finishFailed(runtime, context, { message: `CLOSE:轮报告件写败:${e.message}`, detail: { code: e.code ?? "infra", stage: "CLOSE" } });
    }
    return finishOk(runtime, context, composeEnvelope(checkpoint, ctx)); // close 终态=result=信封(旧信封同形)
  }
  return advance(runtime, context, checkpoint, {}, ctx);
}

// ── SHORTLIST 相位(唯一模型步;自有会话提交)──
async function shortlistPhase(task, runtime, context) {
  const input = task.input;
  const cur = task.state.checkpoint;
  crashHook("shortlist");
  const ctx = buildCtx(input, cur); // #415:提前构造——相位头预算墙出口要 ctx 写终态镜像(scriptPhase 同形)
  const b = stepBoundary({ roundType: "discover", knobs: input.knobs, startedAtIso: cur.startedAtIso }); // ③
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: "SHORTLIST" } }, ctx);

  const def = defOf("SHORTLIST");
  const io = modelIO(def);
  const { systemPrompt, userMsg } = io.input(ctx); // 旧输入构造零复制(d1-scan.json 候选宇宙)
  // bench 轮会话 instructions=基准提示词 shortlist-bench.md(run-bench 创建会话时装,票 #319);
  // v1 步 readFileSync 面装的是真实提示词——transcript system_sha/prompt_hashes 须哈希实际
  // 指令面,bench 轮在此换面(真实轮零变化)。
  const sys = isBench(input) ? fs.readFileSync(shortlistBenchPromptPath(), "utf8") : systemPrompt;
  const convId = runtime.conversationId; // 绑定会话=轮会话(启动器创建;头注「轮会话来源」)
  return shortlistSubmit(task, runtime, context, { ctx, def, io, systemPrompt: sys, userMsg, convId });
}

// 提交腿(attempt 循环=旧 retry≤1 面;requestId 纪律见头注)
async function shortlistSubmit(task, runtime, context, s) {
  const input = task.input;
  const cur = task.state.checkpoint;
  const attempt = cur.attempt ?? 1;
  const requestId = attempt <= 1 ? `round-${input.roundId}-shortlist` : `round-${input.roundId}-shortlist-a${attempt}`; // 纪律形;同 attempt 崩溃重放同 key

  const b = preModelCall({ roundType: "discover", knobs: input.knobs, modelCalls: cur.modelCalls, startedAtIso: cur.startedAtIso }); // ①③(每 attempt 提交前;遗留2)
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: "SHORTLIST" } }, s.ctx);

  const conversation = await runtime.conversation(s.convId, context); // ConversationHandle(绑定会话;invocation 内有效)
  if (!conversation) return finishFailed(runtime, context, { message: "SHORTLIST:轮会话缺席", detail: { code: "infra", stage: "SHORTLIST" } }, s.ctx);
  ensureRoundHost(s.ctx, s.convId); // 轮级发现宿主(模型面工具;faux=罐装方法零网络)

  const submission = await conversation.submit({ type: "input", content: s.userMsg, requestId }, context);
  const settled = await submission.wait(context); // 恰好一次;同 key 崩溃重放不双花
  if (settled.status !== "done") { // unanswered(中止/机故障)→ 旧 retry≤1:attempt+1 新 requestId 再来
    if (attempt >= 2) return finishFailed(runtime, context, { message: `SHORTLIST:submission_${settled.status}`, detail: { code: "model_face", stage: "SHORTLIST" } }, s.ctx);
    // P0-③ attempt 即调用(旧律 budget.mjs:34「重试同计」):失败 attempt 同步入账 modelCalls,
    // 否则相位边界提交的 cur.modelCalls+1 会漏掉全部失败回合;usage 不补(UsageDoc 会话
    // 累计面,失败回合 usage 已自然含在下一次 usageNow 读数里)
    return advance(runtime, context, cur, { attempt: attempt + 1, modelCalls: cur.modelCalls + 1 }, s.ctx);
  }

  // 答案提取:会话上下文=最后一条 assistant 文本(旧 runRealStep text 面)
  const view = await runtime.context(s.convId, context);
  const messages = view.entries.filter((e) => e.kind === "pi.assistant").flatMap((e) => e.model);
  const last = messages[messages.length - 1];
  const text = last?.content?.filter((c) => c.type === "text").map((c) => c.text).join("") ?? "";
  if (!text && attempt < 2) return advance(runtime, context, cur, { attempt: attempt + 1, modelCalls: cur.modelCalls + 1 }, s.ctx); // empty_text 面重发(新 requestId);P0-③ 同上:失败 attempt 同计
  if (!text) return finishFailed(runtime, context, { message: "SHORTLIST:empty_text", detail: { code: "empty_text", stage: "SHORTLIST" } }, s.ctx);

  const usageNow = await roundUsage(runtime, s.convId, context);
  const post = postModelCall({ roundType: "discover", knobs: input.knobs, totalTokens: usageNow.totalTokens, costCny: usageNow.cost }); // ②(skip:无 token 界)④
  if (!post.ok) return finishFailed(runtime, context, { message: post.message, detail: { code: post.code, stage: "SHORTLIST" } }, s.ctx);

  s.ctx.modelCalls = cur.modelCalls + 1;
  s.ctx.usage = usageNow;
  s.io.consume(s.ctx, null, { text }); // 旧消费零复制:JSON 解析失败=降级空清单(步 done,零候选合法,轮不炸)

  // transcript(旧 faux.mjs 行型逐字同构:input/registry_seed/message;prompt hash 同算法。
  // message 行仅取 role/content/stopReason——pi 会话 entry 的 model 消息带 provider 元数据
  // (api/provider/model/timestamp/usage/durationMs),旧事件流面无此字段,多写=对拍噪音)
  const host = s.ctx.discoverHost;
  const lines = [
    JSON.stringify({ type: "input", stage: "SHORTLIST", system_sha: sha(s.systemPrompt), user_sha: sha(s.userMsg), meta: null }),
    ...(host?.seeds ?? []).map((sd) => JSON.stringify({ type: "registry_seed", call_id: sd.call_id, tool: sd.tool, sc: sd.sc })),
    ...messages.map((m) => JSON.stringify({ type: "message", role: m.role, content: m.content, stopReason: m.stopReason ?? null })),
  ];
  fs.appendFileSync(path.join(s.ctx.dir, "d2-shortlist-transcript.jsonl"), lines.join("\n") + "\n");

  const gate = gates.evalStageGate(defOf("SHORTLIST"), s.ctx);
  gates.appendGate(s.ctx.dir, s.ctx.roundId, gate);
  if (!gate.pass) return finishFailed(runtime, context, { message: `GATE:SHORTLIST:${gate.reason}`, detail: { code: gate.code ?? "infra", stage: "SHORTLIST" } }, s.ctx);

  const checkpoint = {
    ...cur, phase: isBench(input) ? "close" : "measure", attempt: 1, // bench 相位截断(#318):SHORTLIST 后直达 CLOSE(MEASURE/ENQUEUE/RETRO 跳过)
    stages: [...cur.stages, { name: "SHORTLIST", status: "done", attempts: attempt, dur_ms: 0, usage: { ...usageNow } }],
    modelCalls: s.ctx.modelCalls,
    usage: { ...usageNow },
    prompt_hashes: { ...cur.prompt_hashes, SHORTLIST: sha(`${s.systemPrompt}\n${s.userMsg}`) },
  };
  return advance(runtime, context, checkpoint, {}, s.ctx);
}

// ── 轮会话来源(粒度决策的落地形态)──
// 会话由**轮启动器**(run-discover.mjs;golden/entry 同一程序面)在任务外创建:
// harness.createConversation 带 agent 面(model=轮始冻结 modelRef + instructions=
// discover/shortlist 提示词 + extensions=[ops-discover-tools]);任务经
// Conversation.commit(tx.createTask) 以 ownership={kind:"conversation"} 绑进该会话。
// 任务内不再自建会话:TaskRuntime 的 tx.createConversation 无 agent 面且
// ConversationHandle 无 configure,任务内造会话=无模型面死路(实测 API 面,1.4.0
// dist/types.d.ts Tx.createConversation 仅 ownership;harness/types.d.ts ConversationHandle)。
// 相位内会话操作全走 runtime.conversationId(=绑定会话):ConversationHandle submit /
// runtime.context 读面 / runtime.documentState(UsageDoc) 计量面。

// ── defineTask(initial 只定相;phases 按 checkpoint.phase 分发)──

// 会话 UsageDoc 活和(模型自报=旧引擎 usage 同源;字段面=旧 ctx.usage 形状
// {input,output,totalTokens,cost}——RETRO 台账行 toFixed(8) 等旧步消费面零改)。
// 注:TaskRuntime 只暴露 snapshot(值直读),无 Session 级 documentState(实测 1.4.0)。
async function roundUsage(runtime, convId, context) {
  const v = await runtime.snapshot(UsageDoc, convId, context) ?? {};
  let input = 0, output = 0, totalTokens = 0, cost = 0;
  for (const bucket of [v.models, v.tools])
    for (const u of Object.values(bucket ?? {})) {
      input += u?.input ?? 0; output += u?.output ?? 0;
      totalTokens += u?.totalTokens ?? 0; cost += u?.cost?.total ?? 0;
    }
  return { input, output, totalTokens, cost };
}

// ── defineTask(initial 只定相;phases 按 checkpoint.phase 分发)──
export const discoverRoundTask = defineTask({
  name: DISCOVER_TASK_NAME,
  version: 1,
  initial: (input) => ({
    phase: "scan",
    roundId: input.roundId,
    startedAtIso: new Date().toISOString(), // 墙钟真源:initial 一次,恢复不改写(遗留1)
    modelCalls: 0,
    usage: { input: 0, output: 0, totalTokens: 0, cost: 0 },
    stages: [],
    prompt_hashes: {},
    attempt: 1,
  }),
  phases: {
    scan: (task, runtime, context) => scriptPhase(task, runtime, context, "scan"),
    shortlist: (task, runtime, context) => shortlistPhase(task, runtime, context),
    measure: (task, runtime, context) => scriptPhase(task, runtime, context, "measure"),
    enqueue: (task, runtime, context) => scriptPhase(task, runtime, context, "enqueue"),
    retro: (task, runtime, context) => scriptPhase(task, runtime, context, "retro"),
    close: (task, runtime, context) => scriptPhase(task, runtime, context, "close"),
  },
  abort: async (task, runtime, context) => { // P2-⑧ 中止终态留痕(model-round/health-round mkAbort 同款;缺省=框架 fault 面无终态,信封永不落)
    // #415:中止=任务终态,镜像同词 aborted(属主判同失败出口;中止时所处相位未成=stages 不造名)
    if (task.state?.checkpoint) writeOwnedRoundState(buildCtx(task.input, task.state.checkpoint), "aborted");
    await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), context);
  },
});
