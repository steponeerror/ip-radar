#!/usr/bin/env node
// run-health.mjs — 健康轮启动器(票 #229 T5;cron 面驱动器,T4 遗留 4 的收口)。
// 与 run-discover.mjs 同律(spec 定案 5/6):开 harness → 准入(admitRound)→ root.commit
// 建 OPS_HEALTH_ROUND 任务(E2E 判例:ownership={kind:"conversation"} 挂 root 会话;
// 模型子会话由任务内 spawn 自建)→ waitForTask → stdout 末行=旧形轮次信封(ENVELOPE.md 冻结)。
// 模型面:--fixtures DIR=faux(零网络零花费;--model 缺省 faux-discover 同律不需);
// real 面=--model provider/modelId(子任务 spawn 内 loadModels)。
// 退出码(T5 冻结表,ENVELOPE.md):0=completed;1=failed/refused/parked;2=用法错;3=运行期异常。
// 用法:node run-health.mjs <roundId> [--fixtures DIR] [--db PATH] [--model provider/modelId]
//        [--from-phase PHASE](默认全轮 PROBE 起;faux 测试用 TRIAGE 起零网络)
//        [--to-phase PHASE](默认 CLOSE 全链;旧 replay --to 镜像,shadow 载具停笔面)
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineDoc } from "@earendil-works/pi-durable";
import { OPS_HEALTH_ROUND, RUNNABLE as HEALTH_PHASES } from "./tasks/health-round.mjs"; // RUNNABLE=PROBE…RETRO(旧 runnableOf 同推导;fromPhase 闭集面)
import { openHarness } from "./entry.mjs";
import { admitRound } from "./tasks/budget-guard.mjs";

// 轮→任务索引(session 单例 doc;run-discover.mjs RoundsDoc 同律)。创建与登记同一 commit。
export const HealthRoundsDoc = defineDoc({ kind: "ops.health-rounds", scope: "session", version: 1, checkpointWhen: () => true, initial: () => ({ rounds: {} }) });

// 旧形失败信封(ENVELOPE.md 冻结;agent.mjs failureEnvelope 同形:{ok:false,round,error})
const failEnvelope = (code, message) => ({ ok: false, round: "health", error: { code, message } });

export async function runHealthRound(opts) {
  const env = opts.env ?? process.env;
  const roundId = opts.roundId;
  const log = (l) => (opts.stderr ?? process.stderr).write(`${l}\n`);
  // 轮 id 形状律(P2-5,旧 mkCtx 同律):YYYY-MM-DD-HHMM-health(-rN);note-9:用法/形状校验
  // 先于准入——非法轮次是调用方错(exit 1 bad_round),不被月帽拒跑掩蔽。
  if (!/^\d{4}-\d{2}-\d{2}-\d{4}-health(-r\d+)?$/.test(roundId ?? ""))
    return { status: "failed", envelope: failEnvelope("bad_round", `round_id 形状须 YYYY-MM-DD-HHMM-health:${roundId}`) };
  const fixturesDir = opts.fixturesDir ?? null;
  const fromPhase = opts.fromPhase ?? "PROBE";
  if (!HEALTH_PHASES.includes(fromPhase)) throw Object.assign(new Error(`--from-phase 须 ∈ {${HEALTH_PHASES.join("|")}},得到:${fromPhase}`), { usage: true });
  const toPhase = opts.toPhase ?? "CLOSE";
  if (![...HEALTH_PHASES, "CLOSE"].includes(toPhase)) throw Object.assign(new Error(`--to-phase 须 ∈ {${[...HEALTH_PHASES, "CLOSE"].join("|")}},得到:${toPhase}`), { usage: true });
  if (HEALTH_PHASES.includes(toPhase) && HEALTH_PHASES.indexOf(toPhase) <= HEALTH_PHASES.indexOf(fromPhase))
    throw Object.assign(new Error(`--to-phase(${toPhase}) 须晚于 --from-phase(${fromPhase})`), { usage: true }); // CLI 层早拒(exit 2);任务 initial 同闭集重复校验=深防御
  // --model(P1-3):provider/modelId → 任务 input.modelRef(real 面显式覆盖;faux 面被 spawn 内
  // faux 分派优先,同 E2E 注入面优先级)
  let modelRef = null;
  if (opts.model) {
    const i = opts.model.indexOf("/");
    if (i <= 0 || i >= opts.model.length - 1) throw Object.assign(new Error(`--model 须 provider/modelId,得到:${opts.model}`), { usage: true });
    modelRef = { provider: opts.model.slice(0, i), modelId: opts.model.slice(i + 1) };
  }
  const admission = await admitRound({ env, log, roundType: "health", ledgerFile: opts.ledgerFile });
  if (admission.refused)
    return { status: "refused", envelope: failEnvelope(admission.code, admission.message) };
  const { harness } = await openHarness({ dbPath: opts.dbPath, env }); // 模型装载不在此分叉:faux 分派在任务 spawn 内(faux-face),real 走缺省 loadModels
  const context = (await import("@earendil-works/chord/context")).BACKGROUND_CONTEXT;
  try {
    harness.resume();
    const index = await harness.snapshot(HealthRoundsDoc, context);
    const prior = index?.rounds?.[roundId];
    let taskId;
    if (prior && typeof prior.taskId === "number") {
      taskId = prior.taskId; // 幂等:同库同轮复用任务(checkpoint 续跑/终态重放,零新建)
      log(`[v2-health] round=${roundId} 复用任务 ${taskId}`);
    } else {
      const root = await harness.root(context); // 任务挂 root 会话(E2E 判例:root.commit tx 的 conversationId 隐式;Session 级 commit 需显式——TaskOptions 文档律)
      taskId = await root.commit(async (tx) => {
        const id = await tx.createTask(OPS_HEALTH_ROUND, {
          roundId, fromPhase, ...(toPhase !== "CLOSE" ? { toPhase } : {}), ...(modelRef ? { modelRef } : {}),
          modelFace: fixturesDir ? "faux" : "real",
          fixturesDir,
          monthlyAdmission: admission.admission ?? null, // P1-5 读数链:submitter→input→initial→09-budget monthly
        }, { ownership: { kind: "conversation" } });
        const doc = await tx.doc(HealthRoundsDoc);
        doc.rounds[roundId] = { taskId: id };
        return id;
      }, context);
      log(`[v2-health] round=${roundId} task=${taskId} from=${fromPhase} face=${fixturesDir ? "faux" : "real"}`);
    }
    const settled = await harness.waitForTask(taskId, context);
    const outcome = settled.state.outcome;
    if (outcome?.status === "completed") return { status: "completed", envelope: outcome.result.envelope, taskId };
    if (outcome?.status === "failed") return { status: "failed", envelope: outcome.result?.envelope ?? failEnvelope(outcome.error?.code ?? "infra", outcome.error?.message ?? "健康轮失败"), taskId };
    return { status: "parked", envelope: failEnvelope("infra", `任务未终态:${JSON.stringify(settled.state.outcome?.error ?? settled.state.summary ?? {})}`), taskId }; // P2-⑫ 带真错:outcome.error 优先(纯 summary 面在 restartLimit 停摆时无错因可查),summary 兑底
  } finally {
    await harness.close(context);
  }
}

// ── CLI(cron 面;stdout 末行=旧形信封,wrapper 信息走 stderr——ENVELOPE.md 冻结)──
function usage() {
  process.stderr.write(`用法:node run-health.mjs <YYYY-MM-DD-HHMM-health> [--fixtures DIR] [--db PATH] [--model provider/modelId] [--from-phase PHASE] [--to-phase PHASE]\n`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const roundId = args[0] && !args[0].startsWith("--") ? args[0] : undefined // 位置首参=roundId(终审修复:flag 先于位置参时原 find 会把 flag 值误当 id);
  const flag = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
  if (!roundId) { usage(); process.exitCode = 2; } // exitCode 而非 exit:stdout 写入异步落管,process.exit 可截断单行信封(旧 pipeline.mjs:547 判例)
  else {
    try {
      const r = await runHealthRound({
        roundId,
        fixturesDir: flag("fixtures") ? path.resolve(flag("fixtures")) : null,
        dbPath: flag("db"),
        fromPhase: flag("from-phase"),
        toPhase: flag("to-phase"),
        model: flag("model"),
      });
      process.stdout.write(`${JSON.stringify(r.envelope)}\n`); // stdout 末行单行旧形信封(唯一 stdout 内容)
      process.exitCode = r.status === "completed" ? 0 : 1;
    } catch (e) {
      if (e?.usage) usage(); // 用法错=纯 stderr+exit 2,不发 JSON
      else process.stderr.write(`${e.stack ?? e}\n`);
      process.exitCode = e?.usage ? 2 : 3; // 3=T5 冻结:运行期异常≠unanswered(旧 N1 缺口),cron 层可区分
    }
  }
}
