// round-ctx.mjs — 健康轮 v2 ↔ 旧管线 ctx 适配层(票 #228;spec 定案 1/2:相位语义逐字
// 保留,模型/脚本步实现零复制 import 旧 steps/gates,本文件只造旧 ctx 形状喂它们)。
// 零改动红线约束:旧 pipeline.mjs 的 composeEnvelope/SKIP_WHEN(ctxPaths/ctxShape 同理)
// 是私有函数不 export → 本文件按旧源逐字重实现(适配副本),出处逐处标注;旧文件一动
// 不动。升级/对拍以旧源为准,改这里须同步核旧源。
import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";

export const ROOT = path.resolve(import.meta.dirname, "..", ".."); // 仓根(与 entry.mjs 同推导)

// ops 树根(旧 pipeline.mjs opsRootOf 同形;旧缺省链=tools.mjs import 时读的 DOCS_ROOT,
// v2 缺省=仓根 docs——测试/生产都显式 DOCS_ROOT,两链等价面只在双缺省时且行为一致)
export const opsRootOf = (env) => path.join(env.DOCS_ROOT ?? process.env.DOCS_ROOT ?? path.join(ROOT, "docs"), "ops");

// ctx 派生路径单一形状(旧 pipeline.mjs ctxPaths 逐字副本:私有不 export,适配重实现)
export const ctxPaths = (OPS_ROOT, roundId) => ({
  rulesFile: path.join(OPS_ROOT, "rules", "suppressions.json"),
  itemsDir: path.join(OPS_ROOT, "items"),
  retroFile: path.join(OPS_ROOT, "retro", `${roundId}.json`), retroAuditKey: roundId,
});

// 旧 pipeline/faux.mjs 私有 sha 逐字副本(transcript 行 prompt_sha 同源算法,16 hex)
export const sha16 = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);

const j = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };

// 轮次信封组装(旧 pipeline.mjs composeEnvelope 逐字副本:私有不 export,适配重实现;
// 现有形状只增 pipeline 扩展字段,旧消费方透传零改——v2 CLOSE 相位信封与旧 stdout 末行同形)
export function composeEnvelope(ctx, { ok, code, message }) {
  const pipeline = { round_id: ctx.roundId, resumed_from: ctx.resumedFrom ?? null, replayed_of: ctx.state.replay_of, stages: ctx.state.stages };
  if (ctx.state.finding_exits) pipeline.finding_exits = ctx.state.finding_exits;
  if (ok) return { ok: true, round: ctx.type, pkg: ctx.pkg, usage: { ...ctx.usage }, queue_writes: [],
    verify: ctx.verify ?? { ok: true, cited: 0 }, pipeline };
  const e = { ok: false, round: ctx.type, error: { code, message } };
  if (ctx.pkg) e.pkg = ctx.pkg;
  e.pipeline = pipeline;
  return e;
}

// skipWhen 命名谓词闭集(旧 pipeline.mjs SKIP_WHEN.no_need_deep 逐字副本:私有不 export,适配重实现)
export const skipWhenNoNeedDeep = (ctx) => {
  const b = j(path.join(ctx.dir, "04-dispatch-bundles.json"));
  if (b) return !(b.bundles ?? []).length;
  const h = j(path.join(ctx.dir, "03-triage-hypotheses.json"));
  return !((h?.hypotheses ?? []).some((x) => x.need_deep));
};

// ── 轮次级挥态(进程内;旧 ctxShape 每轮新建 Map 的 v2 对应面)────────────────────
// dupRegistry:微探针同参去重面(旧 ctx.dupRegistry;resume 重开=计数清零,宁少算口径,
// 旧 ctxShape 头注同语义——「resume 重开=usage 从零计,断点前已花量不可回收」)。
const VOLATILE = new Map(); // roundId → { dupRegistry: Map }
export function roundVolatile(roundId) {
  if (!VOLATILE.has(roundId)) VOLATILE.set(roundId, { dupRegistry: new Map() });
  return VOLATILE.get(roundId);
}

// ctx 形状唯一真源的 v2 面(旧 ctxShape 逐字段镜像;state 由健康轮 checkpoint 重建,
// script 步只读 ctx.state、ANCHOR_SWEEP 会写 finding_exits → 步后由任务面同步回 checkpoint)。
export const buildRoundCtx = ({ type, roundId, opsRoot, env, log, fixturesDir, modelFace, budgetCny, budgetKnobs, breakerKnobs, state, usage, modelCalls }) => ({
  type, roundId,
  dir: path.join(opsRoot, "rounds", String(roundId)),
  env, log, fixturesDir, modelFace, budgetCny, budgetKnobs, breakerKnobs,
  modelCalls: modelCalls ?? 0, dupRegistry: roundVolatile(roundId).dupRegistry, opsRoot,
  ...ctxPaths(opsRoot, roundId),
  ledgerFile: env.LEDGER_FILE ?? process.env.LEDGER_FILE ?? path.join(opsRoot, "ledger.md"),
  pkg: null, verify: null, envelope: null,
  discoverHost: null,
  usage: usage ?? { input: 0, output: 0, totalTokens: 0, cost: 0 },
  state,
});

export const addUsage = (to, from) => { for (const k of ["input", "output", "totalTokens", "cost"]) to[k] += from?.[k] ?? 0; }; // 旧 pipeline.mjs addUsage 逐字副本(私有)
