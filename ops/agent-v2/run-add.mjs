#!/usr/bin/env node
// run-add.mjs — 加源轮启动器(票 #332 P1;与 run-discover.mjs 同壳同纪律,轮型=add)。
// 职责(docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md §架构):
// 开 harness → 准入(admitRound,roundType="add" → OPS_ADD_* 旋钮族)→ 创建轮会话
// (agent 面=modelRef+add/system.md 提示词+ADD_TOOLS_EXTENSION 编码工具闭集)→ 经
// conversation.commit(tx.createTask) 绑 ops.add-round 任务 → waitForTask → stdout
// 末行=轮次信封 JSON(ENVELOPE.md add 节)。
// 沙箱律:--sandbox DIR 必须已存在(沙箱 worktree 由调用方/人面构建,轮只消费不建);
// 沙箱测试解释器缺省=主检出 venv 绝对路径(git-common-dir 推导;worktree 无 venv,
// AGENTS 仓律 2026-11-03),可经 OPS_ADD_PYTHON/--python 覆盖。
// bench 形态(定案 2 开关位,P2b 基准接线消费):--bench 跳过 DOSSIER 相位,交接单
// 预填经 --dossier-file(缺=用法错)。
// 轮 id 形状律:YYYY-MM-DD-HHMM-add(-rN),先于准入拒跑(note-9 同序)。
// 用法:node run-add.mjs <roundId> --source <source> --sandbox DIR [--fixtures DIR]
//        [--model provider/modelId] [--python PATH] [--bench --dossier-file F]
//        [--db PATH] [--crash-after-phase PHASE]
// 退出码:0=completed;1=failed/refused;2=用法错;3=运行期异常(ENVELOPE.md 冻结面)。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { defineDoc } from "@earendil-works/pi-durable";
import { ADD_TOOLS_EXTENSION } from "./registry.mjs";
import { openHarness } from "./entry.mjs";
import { admitRound } from "./tasks/budget-guard.mjs";
import { addRoundTask } from "./tasks/add-round.mjs";

const ROOT = path.resolve(import.meta.dirname, "..", ".."); // ops/agent-v2 → 仓根(entry.mjs 同推导)

// 轮→任务索引(session 单例 doc;同 run-discover RoundsDoc 原子登记面)
export const AddRoundsDoc = defineDoc({ kind: "ops.add-rounds", scope: "session", version: 1, checkpointWhen: () => true, initial: () => ({ rounds: {} }) });

// add 提示词路径:ops/agent/prompts/add/<file>.md(run-add 定义面;tasks/add-round.mjs
// 运行时互引——函数声明循环安全,run-discover/discover-round 同律)。
const promptsRoot = () => path.join(ROOT, "ops", "agent", "prompts");
export const addPromptPath = (file) => path.join(promptsRoot(), "add", file);

// faux 模型面(fauxBundle 同构:fixtures/add/turns.json 罐装回合驱动真工具,零网络零花费)
export async function fauxAddBundle(fixturesDir) {
  const { fauxProvider, createModels } = await import("@earendil-works/pi-ai");
  const fx = JSON.parse(fs.readFileSync(path.join(fixturesDir, "turns.json"), "utf8"));
  const faux = fauxProvider({ models: [{ id: "faux-add-round" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses(fx.turns);
  return { models, resolve: () => faux.getModel() };
}

// 沙箱测试解释器:OPS_ADD_PYTHON 显式优先;缺省=主检出 venv 绝对路径(spec 定案 8
// GATE 跑法;worktree 检出自 .git 文件指向主检出 .git,git-common-dir=主检出 .git,
// dirname 即主检出根;主检出自身时同算式退化为自身——单一代码路径两形态都对)。
export function resolveAddPython(env = process.env) {
  if (env.OPS_ADD_PYTHON) return env.OPS_ADD_PYTHON;
  try {
    const out = execFileSync("git", ["-C", ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"], { encoding: "utf8" }).trim();
    return path.join(path.dirname(path.resolve(out)), "backend", ".venv", "bin", "python");
  } catch {
    return path.join(ROOT, "backend", ".venv", "bin", "python");
  }
}

// ── 一轮(程序面;CLI 与测试共用)──
// 返回 {status:"completed",envelope} | {status:"failed",error} | {status:"refused",...};
// 信封形见 tasks/add-round.mjs composeEnvelope(ENVELOPE.md add 节)。
export async function runAddRound(opts) {
  const env = opts.env ?? process.env;
  const roundId = opts.roundId;
  const source = opts.source;
  const sandboxRoot = opts.sandboxRoot ? path.resolve(opts.sandboxRoot) : null;
  const fixturesDir = opts.fixturesDir ? path.resolve(opts.fixturesDir) : null;
  const bench = opts.bench === true;
  const log = (l) => (opts.stderr ?? process.stderr).write(`${l}\n`);
  // 轮 id 形状律(先于准入——note-9 同序:调用方错不被月帽掩蔽):
  if (!/^\d{4}-\d{2}-\d{2}-\d{4}-add(-r\d+)?$/.test(roundId ?? ""))
    return { status: "failed", error: { code: "bad_round", message: `round_id 形状须 YYYY-MM-DD-HHMM-add:${roundId}` } };
  // 输入域(usage 错 exit 2,不带病开库):source 形状=queue source 面([a-z0-9_]{1,32});
  // 沙箱已存在(调用方构建);bench 须配 dossier。
  if (!/^[a-z0-9_]{1,32}$/.test(source ?? ""))
    throw Object.assign(new Error(`--source 形状须 ^[a-z0-9_]{1,32}$:${source}`), { usage: true });
  if (!sandboxRoot || !fs.existsSync(sandboxRoot))
    throw Object.assign(new Error(`沙箱缺席:${sandboxRoot}(沙箱 worktree 由调用方构建,轮只消费;先 git worktree add)`), { usage: true });
  if (bench && !opts.dossier)
    throw Object.assign(new Error("bench 形态须 --dossier-file(交接单预填,DOSSIER 相位跳过)"), { usage: true });
  // —— 步前准入(月度 kill switch;budget-guard 单源,add 旋钮族)——
  const admission = await admitRound({ env, log, roundType: "add", ledgerFile: opts.ledgerFile });
  if (admission.refused)
    return { status: "refused", code: admission.code, message: admission.message, budget: { admission: admission.admission } };
  const modelRef = opts.modelRef ?? (fixturesDir ? { provider: "faux", modelId: "faux-add-round" } : null);
  if (!modelRef) throw Object.assign(new Error("模型面缺:real 面须 --model provider/modelId(或经 opts.modelRef)"), { usage: true });
  const python = opts.python ?? resolveAddPython(env);
  if (!fs.existsSync(python))
    throw Object.assign(new Error(`沙箱测试解释器缺席:${python}(主检出 backend/.venv;或经 --python/OPS_ADD_PYTHON 指定)`), { usage: true });
  const { harness } = await openHarness({
    dbPath: opts.dbPath,
    env,
    registry: opts.registry,
    models: fixturesDir ? await fauxAddBundle(fixturesDir) : undefined,
  });
  const context = BACKGROUND_CONTEXT;
  try {
    harness.resume();
    // 幂等键律(同 run-discover):同库同轮复用任务续跑/重放;跨库撞轮目录由任务内建轮守卫拦。
    const index = await harness.snapshot(AddRoundsDoc, context);
    const prior = index?.rounds?.[roundId];
    let taskId, conversationId;
    if (prior && typeof prior.taskId === "number") {
      taskId = prior.taskId;
      conversationId = prior.conversationId;
      log(`[v2-add] round=${roundId} 复用任务 ${taskId}(checkpoint 续跑/终态重放,零新建)`);
    } else {
      const conv = await harness.createConversation({
        ownership: { kind: "ownerless" },
        agent: {
          model: modelRef,
          instructions: fs.readFileSync(addPromptPath("system.md"), "utf8"),
          extensions: [ADD_TOOLS_EXTENSION], // 编码工具闭集(write_file/run_bash/run_pytest;定案 7)
        },
      }, context);
      taskId = await harness.commit(async (tx) => {
        const id = await tx.createTask(addRoundTask, {
          roundId,
          source,
          sandboxRoot,
          python, // 解释器路径非凭证(工具体=本地文件系统路径);env 现读不入档律不适用
          knobs: admission.knobs, // 轮始冻结(旧律)
          budgetCny: admission.estCny,
          modelFace: fixturesDir ? "faux" : "real",
          fixturesDir,
          admission: admission.admission ?? null,
          modelRef,
          bench,
          dossier: bench ? opts.dossier : undefined, // bench 预填交接单(定案 2 开关位)
        }, { ownership: { kind: "conversation" }, conversationId: conv.id });
        const doc = await tx.doc(AddRoundsDoc);
        doc.rounds[roundId] = { taskId: id, conversationId: conv.id };
        return id;
      }, context);
      conversationId = conv.id;
    }
    log(`[v2-add] round=${roundId} source=${source} task=${taskId} conv=${conversationId} sandbox=${sandboxRoot} model=${modelRef.provider}/${modelRef.modelId}${bench ? " bench=on" : ""}`);
    const settled = await harness.waitForTask(taskId, context);
    const outcome = settled.state.outcome;
    if (outcome?.status === "completed") return { status: "completed", envelope: outcome.result, taskId, conversationId };
    if (outcome) return { status: "failed", error: outcome.error, taskId, conversationId };
    return { status: "parked", taskId, conversationId, state: settled.state };
  } finally {
    await harness.close(context);
  }
}

// ── CLI ──
function usage() {
  process.stderr.write(`用法:node run-add.mjs <roundId> --source <source> --sandbox DIR [--fixtures DIR] [--model provider/modelId] [--python PATH] [--bench --dossier-file F] [--db PATH] [--crash-after-phase PHASE]\n`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const roundId = args[0] && !args[0].startsWith("--") ? args[0] : undefined;
  const flag = (name) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
  if (!roundId) { usage(); process.exitCode = 2; }
  else {
    if (flag("crash-after-phase")) process.env.OPS_V2_CRASH_AFTER_PHASE = flag("crash-after-phase");
    try {
      let modelRef;
      const modelRefArg = flag("model");
      if (modelRefArg) {
        const i = modelRefArg.indexOf("/");
        if (i <= 0 || i >= modelRefArg.length - 1) throw Object.assign(new Error(`--model 须 provider/modelId,得到:${modelRefArg}`), { usage: true });
        modelRef = { provider: modelRefArg.slice(0, i), modelId: modelRefArg.slice(i + 1) };
      }
      let dossier;
      if (flag("dossier-file")) dossier = JSON.parse(fs.readFileSync(path.resolve(flag("dossier-file")), "utf8")); // 形状由任务 DOSSIER 相位门校验
      const r = await runAddRound({
        roundId,
        source: flag("source"),
        sandboxRoot: flag("sandbox"),
        fixturesDir: flag("fixtures"),
        dbPath: flag("db"),
        modelRef,
        python: flag("python"),
        bench: args.includes("--bench"),
        dossier,
      });
      // stdout 末行=轮次信封(ENVELOPE.md 冻结面;读序 detail.code → code → infra 兜底,run-discover 同律)
      const out = r.status === "completed" ? r.envelope
        : r.status === "refused" ? { ok: false, round: "add", error: { code: r.code, message: r.message } }
        : { ok: false, round: "add", error: { code: r.error?.detail?.code ?? r.error?.code ?? "infra", message: r.error?.message ?? "加源轮失败" } };
      process.stdout.write(`${JSON.stringify(out)}\n`);
      process.exitCode = r.status === "completed" ? 0 : 1;
    } catch (e) {
      if (e?.usage) usage();
      else process.stderr.write(`${e.stack ?? e}\n`);
      process.exitCode = e?.usage ? 2 : 3;
    }
  }
}
