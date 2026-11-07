#!/usr/bin/env node
// bench/run-bench.mjs — 重发现基准轮启动器(票 #318=spec §8 票 A;docs/research/
// 2026-11-07-rediscover-bench-spec.md §3.1)。复用 runDiscoverRound 的 durable 底座
// (openHarness+admitRound+轮会话+ops.discover-round 相位机,零 fork)注入 bench 配置:
//   ①候选宇宙=仅 NEEDS 面(bench/scan.mjs;任务内 bench 模式开关=input.benchOpsRoot);
//   ②相位截断 SCAN→SHORTLIST→CLOSE(MEASURE/ENQUEUE/RETRO 跳过;CLOSE 保留=09-budget.json
//     usage/花费读数工件,信封 usage 同在);
//   ③沙箱 opsRoot=dev/bench-rediscover/<roundId>/(台账/熔断/工件/db 全落沙箱,绝不写
//     真实 docs/ops/;admitRound 走沙箱自有 ledgerFile,月帽读数自成世界=spec Q10);
//   ④roundId 沿用现形状 YYYY-MM-DD-HHMM-discover(-rN),复跑轮由调用方加后缀。
// 模型面与真实轮同律:缺省=real(--model provider/modelId 必填,与生产同一 GLM 面=Q11);
// --fixtures DIR=faux 罐装(零网络零花费,CI 冒烟面)。
// 用法:node bench/run-bench.mjs <roundId> [--fixtures DIR] [--db PATH] [--model provider/modelId]
//        [--bench-root PATH](缺省 $OPS_BENCH_ROOT|<仓根>/dev/bench-rediscover;untracked)
// 退出码:0=completed;1=failed/refused;2=用法错;3=运行期异常(ENVELOPE.md 冻结面)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { defineDoc } from "@earendil-works/pi-durable";
import { DISCOVER_TOOLS_EXTENSION } from "../registry.mjs";
import { openHarness } from "../entry.mjs";
import { admitRound } from "../tasks/budget-guard.mjs";
import { discoverRoundTask } from "../tasks/discover-round.mjs";
import { fauxBundle, shortlistPromptPath } from "../run-discover.mjs"; // durable 底座件零 fork(faux 罐装/提示词路径单源)

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", ".."); // ops/agent-v2/bench → 仓根

// bench 沙箱根(env 覆盖=测试隔离缝;缺省 dev/bench-rediscover,放置规范:dev/ 不入仓)
export function benchRootOf(env = process.env) {
  return env.OPS_BENCH_ROOT ?? path.join(REPO_ROOT, "dev", "bench-rediscover");
}

// bench 轮索引(session 单例 doc;独立 kind=基准世界自有,不与真实轮 RoundsDoc 混账——
// spec Q10「基准不得污染真实运营面」;形状与 RoundsDoc 同构)。
export const BenchRoundsDoc = defineDoc({ kind: "ops.bench-discover-rounds", scope: "session", version: 1, checkpointWhen: () => true, initial: () => ({ rounds: {} }) });

// —— 一轮(程序面;CLI 与测试共用)。返回形状与 runDiscoverRound 同律 ——
export async function runBenchRound(opts) {
  const env = opts.env ?? process.env;
  const roundId = opts.roundId;
  const fixturesDir = opts.fixturesDir ?? null;
  const log = (l) => (opts.stderr ?? process.stderr).write(`${l}\n`);
  // 轮 id 形状律(真实轮同律;先于准入——note-9 同序)。
  if (!/^\d{4}-\d{2}-\d{2}-\d{4}-discover(-r\d+)?$/.test(roundId ?? ""))
    return { status: "failed", error: { code: "bad_round", message: `round_id 形状须 YYYY-MM-DD-HHMM-discover:${roundId}` } };
  // 沙箱树:opsRoot=<benchRoot>/<roundId>;台账/db 随 opsRoot 派生(breaker/工件树在
  // 任务内经 opsRoot 派生,见 tasks/discover-round.mjs buildCtx bench 分支)。
  const benchRoot = opts.benchRoot ?? benchRootOf(env);
  const opsRoot = path.join(benchRoot, roundId);
  const ledgerFile = path.join(opsRoot, "ledger.md");
  // —— 步前准入(月度 kill switch;budget-guard 单源,roundType=discover 旋钮族与真实轮
  // 同面;台账=bench 自有 → 月帽在基准世界内计,不读写生产台账=spec Q10)——
  const admission = await admitRound({ env, log, roundType: "discover", ledgerFile });
  if (admission.refused)
    return { status: "refused", code: admission.code, message: admission.message, budget: { admission: admission.admission } };
  const modelRef = opts.modelRef ?? (fixturesDir ? { provider: "faux", modelId: "faux-discover-shortlist" } : null);
  if (!modelRef) throw Object.assign(new Error("模型面缺:real 面须 --model provider/modelId(或经 opts.modelRef)"), { usage: true }); // 用法错 exit 2(run-discover 同律)
  const dbPath = opts.dbPath ?? path.join(opsRoot, "bench.sqlite");
  fs.mkdirSync(opsRoot, { recursive: true }); // 独立 db 先建沙箱根(spec Q10「独立 db」)
  const { harness } = await openHarness({
    dbPath,
    env,
    registry: opts.registry,
    models: fixturesDir ? await fauxBundle(fixturesDir) : undefined,
  });
  const context = BACKGROUND_CONTEXT;
  try {
    harness.resume();
    // 幂等键律(真实轮同律):同库同轮已有任务→复用续跑/重放(零新模型调用零双写)。
    const index = await harness.snapshot(BenchRoundsDoc, context);
    const prior = index?.rounds?.[roundId];
    let taskId, conversationId;
    if (prior && typeof prior.taskId === "number") {
      taskId = prior.taskId;
      conversationId = prior.conversationId;
      log(`[v2-bench] round=${roundId} 复用任务 ${taskId}(checkpoint 续跑/终态重放,零新建)`);
    } else {
      // 轮会话 agent 面同真实轮(model+shortlist 提示词+发现工具闭集;提示词变体=票 B)。
      const conv = await harness.createConversation({
        ownership: { kind: "ownerless" },
        agent: {
          model: modelRef,
          instructions: fs.readFileSync(shortlistPromptPath(), "utf8"),
          extensions: [DISCOVER_TOOLS_EXTENSION],
        },
      }, context);
      taskId = await harness.commit(async (tx) => {
        const id = await tx.createTask(discoverRoundTask, {
          roundId,
          knobs: admission.knobs, // 轮始冻结(真实轮同律)
          budgetCny: admission.estCny,
          modelFace: fixturesDir ? "faux" : "real",
          fixturesDir,
          admission: admission.admission ?? null,
          modelRef,
          benchOpsRoot: opsRoot, // ← bench 模式开关:在场即 bench(SCAN 变体/相位截断/沙箱 opsRoot 全由此驱动)
        }, { ownership: { kind: "conversation" }, conversationId: conv.id });
        const doc = await tx.doc(BenchRoundsDoc);
        doc.rounds[roundId] = { taskId: id, conversationId: conv.id };
        return id;
      }, context);
      conversationId = conv.id;
    }
    log(`[v2-bench] round=${roundId} task=${taskId} conv=${conversationId} model=${modelRef.provider}/${modelRef.modelId} sandbox=${opsRoot}`);
    const settled = await harness.waitForTask(taskId, context);
    const outcome = settled.state.outcome;
    if (outcome?.status === "completed") return { status: "completed", envelope: outcome.result, taskId, conversationId };
    if (outcome) return { status: "failed", error: outcome.error, taskId, conversationId };
    return { status: "parked", taskId, conversationId, state: settled.state };
  } finally {
    await harness.close(context);
  }
}

// —— CLI ——
function usage() {
  process.stderr.write(`用法:node bench/run-bench.mjs <roundId> [--fixtures DIR] [--db PATH] [--model provider/modelId] [--bench-root PATH]\n`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const roundId = args[0] && !args[0].startsWith("--") ? args[0] : undefined; // 位置首参=roundId(run-discover 同律)
  const flag = (name) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
  if (!roundId) { usage(); process.exitCode = 2; }
  else {
    try {
      // --model 校验(run-discover 同律:无斜杠/空段=用法错 exit 2,不带病开库)
      let modelRef;
      const modelRefArg = flag("model");
      if (modelRefArg) {
        const i = modelRefArg.indexOf("/");
        if (i <= 0 || i >= modelRefArg.length - 1) throw Object.assign(new Error(`--model 须 provider/modelId,得到:${modelRefArg}`), { usage: true });
        modelRef = { provider: modelRefArg.slice(0, i), modelId: modelRefArg.slice(i + 1) };
      }
      const r = await runBenchRound({
        roundId,
        fixturesDir: flag("fixtures") ? path.resolve(flag("fixtures")) : null,
        dbPath: flag("db"),
        modelRef,
        benchRoot: flag("bench-root") ? path.resolve(flag("bench-root")) : undefined,
      });
      // stdout 末行=旧形轮次信封(ENVELOPE.md 冻结面;真码读序 detail.code → code → infra 兜底)
      const out = r.status === "completed" ? r.envelope
        : r.status === "refused" ? { ok: false, round: "discover", error: { code: r.code, message: r.message } }
        : { ok: false, round: "discover", error: { code: r.error?.detail?.code ?? r.error?.code ?? "infra", message: r.error?.message ?? "bench 轮失败" } };
      process.stdout.write(`${JSON.stringify(out)}\n`);
      process.exitCode = r.status === "completed" ? 0 : 1;
    } catch (e) {
      if (e?.usage) usage();
      else process.stderr.write(`${e.stack ?? e}\n`);
      process.exitCode = e?.usage ? 2 : 3;
    }
  }
}
