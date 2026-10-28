#!/usr/bin/env node
// run-discover.mjs — 发现轮启动器(票 #227 T3;cron 面与 golden 对拍面同一程序面)。
// 职责(spec 定案 5/6 + t1-notes 建议4):开 harness → 准入(admitRound)→ 创建轮会话
// (agent 面=modelRef+shortlist 提示词+发现工具扩展;任务内无 configure 面,会话必须
// 在任务外带 agent 创建,见 tasks/discover-round.mjs 头注「轮会话来源」)→ 经
// Conversation.commit(tx.createTask) 绑 ops.discover-round 任务 → waitForTask → stdout
// 末行=轮次信封 JSON(旧契约形;T5 冻结前不增删)。
// 模型面:缺省=real(loadModels resolve("discover"));--fixtures DIR / FAUX_FIXTURES=faux
// (fauxProvider 罐装 shortlist turns,零网络零花费——同旧 pipeline.mjs 显式 fixtures 律)。
// 轮 id 形状律(P2-5 对称面,旧 mkCtx:156 同律):YYYY-MM-DD-HHMM-discover(-rN),
// 先于准入拒跑(note-9 同序:调用方错不被月帽掩蔽)。
// 用法:node run-discover.mjs <roundId> [--fixtures DIR] [--db PATH] [--model provider/modelId]
//        [--crash-after-phase PHASE](SIGKILL 自杀面=resume 测试;任务内 crashHook 消费 env)
// 退出码:0=completed;1=failed/refused;2=用法错;3=运行期异常(ENVELOPE.md 冻结面)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { defineDoc } from "@earendil-works/pi-durable";
import { DISCOVER_PIPELINE } from "../agent/pipeline.mjs"; // 零复制:SHORTLIST def(提示词键单源)
import { DISCOVER_TOOLS_EXTENSION } from "./registry.mjs";
import { openHarness } from "./entry.mjs";
import { admitRound } from "./tasks/budget-guard.mjs";
import { discoverRoundTask } from "./tasks/discover-round.mjs";

// 轮→任务索引(session 单例 doc;Harness 无 scanTasks 面,见 1.4.0 types):
// roundId → {taskId, conversationId}。创建与登记同一 commit(原子;崩溃要么都有要么都无)。
export const RoundsDoc = defineDoc({ kind: "ops.discover-rounds", scope: "session", version: 1, checkpointWhen: () => true, initial: () => ({ rounds: {} }) });

// SHORTLIST 提示词路径:与旧 steps.mjs promptFile 同式(<ops/agent>/prompts/<def.model>.md;
// def.model="discover/shortlist" 单源取自 DISCOVER_PIPELINE,仅 prompts 根目录在 v2 推导
// 一次——drift 面由 golden 对拍 transcript system_sha 钉死)。
export function shortlistPromptPath() {
  const def = DISCOVER_PIPELINE.find((d) => d.name === "SHORTLIST");
  return path.join(path.resolve(import.meta.dirname, "..", ".."), "ops", "agent", "prompts", `${def.model}.md`);
}

// faux 模型面(旧 faux.mjs runFauxStep 同构:faux-discover-<键> + fixtures turns 罐装)
export async function fauxBundle(fixturesDir) {
  const { fauxProvider, createModels } = await import("@earendil-works/pi-ai");
  const fx = JSON.parse(fs.readFileSync(path.join(fixturesDir, "shortlist.json"), "utf8"));
  const faux = fauxProvider({ models: [{ id: "faux-discover-shortlist" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses(fx.turns);
  return { models, resolve: () => faux.getModel() };
}

// ── 一轮(程序面;CLI 与测试共用)──
// 返回 {status:"completed",envelope} | {status:"failed",error} | {status:"refused",...};
// envelope=outcome.result(信封形见 tasks/discover-round.mjs composeEnvelope)。
export async function runDiscoverRound(opts) {
  const env = opts.env ?? process.env;
  const roundId = opts.roundId;
  const fixturesDir = opts.fixturesDir ?? null;
  const log = (l) => (opts.stderr ?? process.stderr).write(`${l}\n`);
  // 轮 id 形状律(P2-5,旧 mkCtx:156 同律;先于准入——note-9 同序):
  if (!/^\d{4}-\d{2}-\d{2}-\d{4}-discover(-r\d+)?$/.test(roundId ?? ""))
    return { status: "failed", error: { code: "bad_round", message: `round_id 形状须 YYYY-MM-DD-HHMM-discover:${roundId}` } };
  // —— 步前准入(月度 kill switch;与 entry.runRound 同壳,budget-guard 单源)——
  const admission = await admitRound({ env, log, roundType: "discover", ledgerFile: opts.ledgerFile });
  if (admission.refused)
    return { status: "refused", code: admission.code, message: admission.message, budget: { admission: admission.admission } };
  const modelRef = opts.modelRef ?? (fixturesDir ? { provider: "faux", modelId: "faux-discover-shortlist" } : null);
  if (!modelRef) throw Object.assign(new Error("模型面缺:real 面须 --model provider/modelId(或经 opts.modelRef)"), { usage: true }); // P0-⑥ 用法错 exit 2(裸 Error 会落 exit 3,与 ENVELOPE.md 码表不符)
  const { harness } = await openHarness({
    dbPath: opts.dbPath,
    env,
    registry: opts.registry,
    models: fixturesDir ? await fauxBundle(fixturesDir) : undefined,
  });
  const context = BACKGROUND_CONTEXT;
  try {
    harness.resume();
    // 幂等键律(v2 口径,对应旧「同 id 重跑走 replay」):同库同轮已有任务→复用续跑/重放
    // (requestId 幂等零新模型调用,零双写);跨库新任务撞已有轮目录仍被任务内建轮守卫拦
    // (bad_round,tasks/discover-round.mjs bootstrapRoundDir)。
    const index = await harness.snapshot(RoundsDoc, context);
    const prior = index?.rounds?.[roundId];
    let taskId, conversationId;
    if (prior && typeof prior.taskId === "number") {
      taskId = prior.taskId;
      conversationId = prior.conversationId;
      log(`[v2-discover] round=${roundId} 复用任务 ${taskId}(checkpoint 续跑/终态重放,零新建)`);
    } else {
      // 轮会话:ownerless(一轮一会话;粒度决策=spec 定案 5「一轮=一次任务运行」,
      // 详见 tasks/discover-round.mjs 头注)。agent 面钉死=旧模型步语义:全新上下文+
      // 提示词+工具闭集;extensions 显式=[DISCOVER_TOOLS_EXTENSION](未显式=缺省全装,
      // agent.js selectExtensions——root 面零工具红线由 entry.mjs 钉 [] 对照)。
      const conv = await harness.createConversation({
        ownership: { kind: "ownerless" },
        agent: {
          model: modelRef,
          instructions: fs.readFileSync(shortlistPromptPath(), "utf8"),
          extensions: [DISCOVER_TOOLS_EXTENSION],
        },
      }, context);
      // 任务绑定本会话+登记索引:同一 commit(原子;Session 级 commit 无绑定会话,
      // conversationId 须显式——TaskOptions 文档律)
      taskId = await harness.commit(async (tx) => {
        const id = await tx.createTask(discoverRoundTask, {
          roundId,
          knobs: admission.knobs, // 轮始冻结(旧律:state.budget_knobs 同位)
          budgetCny: admission.estCny,
          modelFace: fixturesDir ? "faux" : "real",
          fixturesDir,
          admission: admission.admission ?? null, // 准入读数记录(ok/projected/month/…;旧 state.monthly_admission 同面,经 checkpoint 冻结)
          modelRef,
        }, { ownership: { kind: "conversation" }, conversationId: conv.id });
        const doc = await tx.doc(RoundsDoc);
        doc.rounds[roundId] = { taskId: id, conversationId: conv.id };
        return id;
      }, context);
      conversationId = conv.id;
    }
    log(`[v2-discover] round=${roundId} task=${taskId} conv=${conversationId} model=${modelRef.provider}/${modelRef.modelId}`);
    const settled = await harness.waitForTask(taskId, context);
    const outcome = settled.state.outcome;
    if (outcome?.status === "completed") return { status: "completed", envelope: outcome.result, taskId, conversationId };
    if (outcome) return { status: "failed", error: outcome.error, taskId, conversationId };
    return { status: "parked", taskId, conversationId, state: settled.state }; // restartLimit 面等(restartCount 连击);报告级,CLI 退 1(终审硬违修复:原引 else 块内 conv,复用路径 ReferenceError)
  } finally {
    await harness.close(context);
  }
}

// ── CLI ──
function usage() {
  process.stderr.write(`用法:node run-discover.mjs <roundId> [--fixtures DIR] [--db PATH] [--model provider/modelId] [--crash-after-phase PHASE]\n`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const roundId = args[0] && !args[0].startsWith("--") ? args[0] : undefined // 位置首参=roundId(终审修复:flag 先于位置参时原 find 会把 flag 值误当 id);
  const flag = (name) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
  if (!roundId) { usage(); process.exitCode = 2; } // exitCode 而非 exit:stdout 写入异步落管,process.exit 可截断单行信封(旧 pipeline.mjs:547 判例)
  else {
    if (flag("crash-after-phase")) process.env.OPS_V2_CRASH_AFTER_PHASE = flag("crash-after-phase");
    try {
      // --model 校验(run-health 同律,P0-⑥):无斜杠/空段=用法错 exit 2,不带病开库
      let modelRef;
      const modelRefArg = flag("model");
      if (modelRefArg) {
        const i = modelRefArg.indexOf("/");
        if (i <= 0 || i >= modelRefArg.length - 1) throw Object.assign(new Error(`--model 须 provider/modelId,得到:${modelRefArg}`), { usage: true });
        modelRef = { provider: modelRefArg.slice(0, i), modelId: modelRefArg.slice(i + 1) };
      }
      const r = await runDiscoverRound({
        roundId,
        fixturesDir: flag("fixtures") ? path.resolve(flag("fixtures")) : null,
        dbPath: flag("db"),
        modelRef,
      });
      // stdout 末行=旧形轮次信封(ENVELOPE.md 冻结面;wrapper 状态走 exit 码+stderr,不口 stdout)。
      // P0-①:任务域失败三元组的真码在 error.detail.code(finishFailed 的 scriptPhase 包装
      // 面),顶层 error.code 仅启动器层失败有——读序 detail.code → code → infra 兜底。
      const out = r.status === "completed" ? r.envelope
        : r.status === "refused" ? { ok: false, round: "discover", error: { code: r.code, message: r.message } }
        : { ok: false, round: "discover", error: { code: r.error?.detail?.code ?? r.error?.code ?? "infra", message: r.error?.message ?? "发现轮失败" } };
      process.stdout.write(`${JSON.stringify(out)}\n`);
      process.exitCode = r.status === "completed" ? 0 : 1;
    } catch (e) {
      if (e?.usage) usage(); // 用法错=纯 stderr+exit 2,不发 JSON
      else process.stderr.write(`${e.stack ?? e}\n`);
      process.exitCode = e?.usage ? 2 : 3; // 3=T5 冻结(ENVELOPE.md):运行期异常与轮次未成分码,cron 层可区分
    }
  }
}
