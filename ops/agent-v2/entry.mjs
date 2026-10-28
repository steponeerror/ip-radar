#!/usr/bin/env node
// entry.mjs — cron 式入口(票 #225;spec 定案 5:cron 起进程 → Harness.open(SQLite)
// → submit 轮次 → 跑完退出,无常驻进程;崩溃=下个 cron tick 起进程 resume 续跑)。
// 薄适配层(定案 6):框架面只在本文件 + registry.mjs + tasks/ 收口。
//
// 用法:node entry.mjs <roundId> [--content TEXT] [--db PATH] [--model provider/modelId]
//        [--round health|discover] [--stage NAME] [--crash-after-submit]
//   roundId    轮次标识(月轮日期等;进 requestId 幂等键)
//   --content  轮次输入(骨架期必填;真实轮次内容/任务由 T3/T4 的 defineTask 接管)
//   --db       SQLite 库路径(缺省见 resolveDbPath;测试/复跑同库同 requestId)
//   --crash-after-submit  submit 承认即 SIGKILL 自杀(resume 演示/测试面)
// 退出码:0=settled done;1=settled unanswered;2=用法错。
// 契约:stdout 末行单行 JSON 轮次信封(骨架形状,T5 冻结对齐旧契约);进度走 stderr。
import path from "node:path";
import { pathToFileURL } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { Harness } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { loadModels, parseModelRef } from "./models.mjs";
import { buildRegistry } from "./registry.mjs";

export const ROOT = path.resolve(import.meta.dirname, "..", ".."); // 仓根(与 ops/agent/tools/shared.mjs 同推导)

// SQLite 落位(t1-notes 建议3):DOCS_ROOT/ops/ 派生面(与 rounds/items 同树规则);
// OPS_V2_DB 覆盖(测试隔离)。journal=WAL+synchronous=NORMAL 由 chord 适配器缺省
// 设置(node_modules/@earendil-works/chord/dist/sqlite/node.js:159-161)——进程崩溃
// commit 安全,断电可能丢最新一笔(轮次粒度可接受,api-map §0)。
export function resolveDbPath(env = process.env) {
  if (env.OPS_V2_DB) return env.OPS_V2_DB;
  const docsRoot = env.DOCS_ROOT ?? path.join(ROOT, "docs");
  return path.join(docsRoot, "ops", "agent-v2.sqlite");
}

// requestId 纪律(t1-notes 风险12):`round-<roundId>[-<stage>]` 形,cron 重启幂等
// 靠它(同键重放返回既有 submission,零新模型调用;T0 smoke 已证)。
export function requestIdFor(roundId, stage) {
  return stage ? `round-${roundId}-${stage}` : `round-${roundId}`;
}

// t1-notes 风险5:DEFAULT_COMPACTION_POLICY 的自动 compaction 会摘要改写上下文,
// shadow 对拍期显式关(golden 稳定后另议);retry/restartLimit 用缺省。
export const HARNESS_SETTINGS = { compaction: { enabled: false } };

export async function openHarness(opts = {}) {
  const dbPath = opts.dbPath ?? resolveDbPath();
  const { models, resolve } = await loadModels(); // 旧管线装载器原样(定案 7;凭证零入日志)
  const storage = await openNodeSqliteStorage(dbPath);
  const harness = await Harness.open(storage, {
    models,
    registry: opts.registry ?? buildRegistry(),
    settings: HARNESS_SETTINGS,
  }, BACKGROUND_CONTEXT);
  return { harness, models, resolve };
}

const lastAssistantText = (view) => (view.entries.filter((e) => e.kind === "pi.assistant").at(-1)?.model ?? [])
  .flatMap((m) => m.content ?? []).find((b) => b.type === "text")?.text ?? "";

// 一轮 = root conversation 一次 submit(spec 术语映射「轮次」;root 复用
// ROOT_CONVERSATION_ID,月轮→conversation 粒度是 T3/T4 决策,t1-notes 建议4)。
export async function runRound(opts) {
  const requestId = opts.requestId ?? requestIdFor(opts.roundId, opts.stage);
  const { harness, models, resolve } = await openHarness(opts);
  const context = BACKGROUND_CONTEXT;
  harness.resume(); // 幂等:崩溃遗留提交/任务续跑(submit/wait 亦自动使能调度)
  try {
    const model = opts.modelRef
      ? models.getModel(parseModelRef(opts.modelRef).provider, parseModelRef(opts.modelRef).model)
      : resolve(opts.round ?? "health"); // 缺省 flash 档(OPS_MODEL_HEALTH 可覆盖,同源)
    if (!model) throw new Error(`模型未装载:${opts.modelRef ?? opts.round ?? "health"}`);
    const root = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
    process.stderr.write(`[v2] submit requestId=${requestId} model=${model.provider}/${model.id}\n`);
    const sub = await root.submit({ type: "input", content: opts.content, requestId }, context);
    if (opts.crashAfterSubmit) {
      process.stderr.write(`[v2] submit 承认(id=${sub.id})即 SIGKILL 自杀——resume 演示面\n`);
      process.kill(process.pid, "SIGKILL");
    }
    const settled = await sub.wait(context);
    const view = await root.context(context);
    const envelope = {
      round: opts.roundId,
      requestId,
      status: settled.status,
      model: `${model.provider}/${model.id}`,
      answer: lastAssistantText(view),
      usage: await harness.usage(context),
    };
    process.stderr.write(`[v2] settled status=${settled.status}\n`);
    return envelope;
  } finally {
    await harness.close(context);
  }
}

// ---- CLI(cron 面)----
function parseArgs(argv) {
  const [roundId, ...rest] = argv;
  const opts = { roundId };
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "--content") opts.content = rest[++i];
    else if (a === "--db") opts.dbPath = rest[++i];
    else if (a === "--model") opts.modelRef = rest[++i];
    else if (a === "--round") opts.round = rest[++i];
    else if (a === "--stage") opts.stage = rest[++i];
    else if (a === "--crash-after-submit") opts.crashAfterSubmit = true;
    else return { error: `未知参数:${a}` };
  }
  if (!roundId) return { error: "缺 roundId" };
  if (!opts.content) return { error: "缺 --content(骨架期必填;真实轮次内容由 T3/T4 任务面接管)" };
  return { opts };
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.error) {
    process.stderr.write(`用法错:${parsed.error}\nnode entry.mjs <roundId> --content TEXT [--db PATH] [--model provider/modelId] [--round health|discover] [--stage NAME] [--crash-after-submit]\n`);
    process.exit(2);
  }
  process.stderr.write(`[v2] harness open db=${parsed.opts.dbPath ?? resolveDbPath()}\n`);
  const envelope = await runRound(parsed.opts);
  process.stdout.write(`${JSON.stringify(envelope)}\n`); // stdout 末行单行信封(T5 冻结形状)
  process.exit(envelope.status === "done" ? 0 : 1);
}

// 直接执行(非 import)才跑 CLI;测试 import runRound/openHarness 不触发。
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
