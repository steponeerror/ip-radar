// tasks/budget-guard.mjs — v2 双点执法接线面(票 #226;spec 定案 3:接线点在 entry/tasks 层,
// 不 hook/memo 化)。旧管线接线参考(读码定位,ops/agent/pipeline.mjs):
//   步前准入  = runPipeline/agent.mjs runRound 的 budget.admitOrRefuse(月度 kill switch;
//               拒跑零花费,先于模型装载/harness 开启)
//   环内①③ attempt 前查 = runModelStage 检查点(calls+1>帽、墙钟超=违界即停,不重试不降级)
//   环内②④ 结算后查     = runModelStage 检查点(token 轨迹/花费;发现轮 tokenBudget
//               undefined 即跳过——#207 T1 发现轮无 token 界)
//   环内③ 步边界查       = runStages 每步体前(resume 沿原 started_at 续算)
// 本 guard 为上述检查点的 v2 同构纯函数面:决策对象 {ok, code?, message?, remaining?}
// (allow/deny+剩余量,供同参哈希对拍逐条断言);执法真源=旧 budget.mjs 纯函数
// (overCallsCap/overWallClock/overTokenBudget/overSpendCap),本文件不另立判据;
// 文案逐字对齐旧检查点(含 per-type 旋钮名指认,#207 T1)。
// T3/T4 相位边界消费本面(相位 handler 尾/头调 stepBoundary/preModelCall);entry.mjs
// 在 submit 前后接线(轮粒度)。月帽语义(DESIGN.md §6 预算四界行):每轮 ¥3 ∧ 月度 ¥30,
// 同台账(ledger.md)并发安全,flock 锁内读,拒跑留痕——budget.mjs 原样,零改动。
import path from "node:path";
import * as budget from "../budget.mjs"; // 零复制 seam(单一真源=旧管线 budget.mjs)

const ROOT = path.resolve(import.meta.dirname, "..", "..", ".."); // 仓根(本文件居 tasks/ 子层,三层上移;entry.mjs 居浅一层故两层,两处落点须同仓根——对拍由 budget-parity 台账落位测试钉死。不 import entry 防环)

// per-type 旋钮读面(pipeline.mjs mkCtx 同选择:discover→readDiscoverKnobs,其余→readBudgetKnobs;
// 月帽/dup 两键两族共享同键同缺省)。非法值 throw {usage:true} → CLI 用法错 exit 2(不带病跑轮)。
export const roundKnobs = (env, roundType = "health") =>
  (roundType === "discover" ? budget.readDiscoverKnobs : budget.readBudgetKnobs)(env ?? process.env);

// per-type 旋钮名指认(旧 runModelStage knobSrc 同表:报错文案指向真读键)。
export const knobNames = (roundType) => roundType === "discover"
  ? { calls: "OPS_DISCOVER_MAX_MODEL_CALLS", wall: "OPS_DISCOVER_WALL_CLOCK_S", spend: "OPS_DISCOVER_SPEND_CAP_CNY" }
  : { calls: "OPS_PIPELINE_MAX_MODEL_CALLS", wall: "OPS_PIPELINE_WALL_CLOCK_S", spend: "OPS_PIPELINE_SPEND_CAP_CNY" };

// 台账路径推导(旧 agent.mjs runRound 同形:LEDGER_FILE > DOCS_ROOT/ops/ledger.md;
// 月帽是全 agent 面共享底线,同裁决同留痕。shadow 期实际接线:DOCS_ROOT 指影子根,
// v2 轮读写影子世界自种清零的独立 ledger.md,不碰生产台账;切流后才指生产根)。
export function resolveLedgerPath(env = process.env) {
  return env.LEDGER_FILE ?? process.env.LEDGER_FILE
    ?? path.join(env.DOCS_ROOT ?? path.join(ROOT, "docs"), "ops", "ledger.md");
}

// —— 步前准入(双点之一;旧 runPipeline/agent.mjs runRound 的 admitOrRefuse 同壳)——
// est=本轮预算上界(OPS_PIPELINE_BUDGET_CNY,与旧 mkCtx/agent.mjs 同读同校验同文案);
// 拒跑留痕([admission] log+台账行)全在旧 admitOrRefuse 内(原样);返回追加 knobs/est 读数。
export async function admitRound({ env = process.env, log = () => {}, roundType = "health", ledgerFile } = {}) {
  const knobs = roundKnobs(env, roundType);
  const estRaw = env.OPS_PIPELINE_BUDGET_CNY ?? process.env.OPS_PIPELINE_BUDGET_CNY ?? "0.05";
  const estCny = +estRaw;
  if (!Number.isFinite(estCny) || estCny < 0)
    throw Object.assign(new Error(`OPS_PIPELINE_BUDGET_CNY 须为非负数,得到:${estRaw}`), { usage: true });
  const file = ledgerFile ?? resolveLedgerPath(env);
  const admission = await budget.admitOrRefuse({ ledgerFile: file, capCny: knobs.monthlyCapCny, estCny, env, log, round: roundType });
  return { ...admission, knobs, estCny, ledgerFile: file };
}

// —— 环内①③ attempt 前查(双点之二;旧 runModelStage 检查点同构,①→③ 顺序)——
// 剩余量=符号值(帽−已用;负=超出):calls 为 attempt 后口径(cap−calls−1),对拍逐条断言用。
export function preModelCall({ roundType = "health", knobs, modelCalls, startedAtIso, now = Date.now() }) {
  const src = knobNames(roundType);
  if (budget.overCallsCap(modelCalls, knobs.maxModelCalls))
    return { ok: false, code: "budget_exceeded", fatalBudget: true,
      message: `预算四界①:模型调用将超帽(已计 ${modelCalls}+1 > ${knobs.maxModelCalls},${src.calls})`,
      remaining: { calls: knobs.maxModelCalls - modelCalls } };
  if (budget.overWallClock(startedAtIso, knobs.wallClockS, now))
    return { ok: false, code: "wall_clock_exceeded", fatalBudget: true,
      message: `预算四界③:墙钟 ${budget.elapsedWallS(startedAtIso, now).toFixed(1)}s 超帽 ${knobs.wallClockS}s(${src.wall})`,
      remaining: { calls: knobs.maxModelCalls - modelCalls, wallS: knobs.wallClockS - budget.elapsedWallS(startedAtIso, now) } };
  return { ok: true, remaining: {
    calls: knobs.maxModelCalls - modelCalls - 1,
    wallS: knobs.wallClockS - budget.elapsedWallS(startedAtIso, now),
  } };
}

// —— 环内③ 步边界查(旧 runStages 步边界同构:步体前查,超=终态先于步体)——
export function stepBoundary({ roundType = "health", knobs, startedAtIso, now = Date.now() }) {
  if (!budget.overWallClock(startedAtIso, knobs.wallClockS, now))
    return { ok: true, remaining: { wallS: knobs.wallClockS - budget.elapsedWallS(startedAtIso, now) } };
  return { ok: false, code: "wall_clock_exceeded",
    message: `预算四界③:墙钟 ${budget.elapsedWallS(startedAtIso, now).toFixed(1)}s 超帽 ${knobs.wallClockS}s(${knobNames(roundType).wall})`,
    remaining: { wallS: knobs.wallClockS - budget.elapsedWallS(startedAtIso, now) } };
}

// —— 环内②④ 结算后查(旧 runModelStage 检查点同构,②→④ 顺序;发现轮无 token 界=跳过②)——
export function postModelCall({ roundType = "health", knobs, totalTokens, costCny }) {
  const src = knobNames(roundType);
  if (knobs.tokenBudget !== undefined && budget.overTokenBudget(totalTokens, knobs.tokenBudget))
    return { ok: false, code: "budget_exceeded", fatalBudget: true,
      message: `预算四界②:token 轨迹 ${totalTokens} 超预算 ${knobs.tokenBudget}(OPS_PIPELINE_TOKEN_BUDGET)`,
      remaining: { tokens: knobs.tokenBudget - totalTokens, spendCny: knobs.spendCapCny - costCny } };
  if (budget.overSpendCap(costCny, knobs.spendCapCny))
    return { ok: false, code: "budget_exceeded", fatalBudget: true,
      message: `预算四界④:花费 ¥${costCny.toFixed(8)} 超帽 ¥${knobs.spendCapCny}(${src.spend})`,
      remaining: { tokens: knobs.tokenBudget === undefined ? undefined : knobs.tokenBudget - totalTokens, spendCny: knobs.spendCapCny - costCny } };
  return { ok: true, remaining: {
    tokens: knobs.tokenBudget === undefined ? undefined : knobs.tokenBudget - totalTokens,
    spendCny: knobs.spendCapCny - costCny,
  } };
}

// —— 环内 usage 聚合:轮次 token/花费 = settle 后 session usage − submit 前 snapshot ——
// v2 口径(t1-notes 风险7:预算口径自算保留):UsageState(harness.usage() 形状,models+tools
// 两桶,pi-ai Usage.totalTokens/cost.total)求和后差分=本轮增量;≡ 旧 agent.mjs subscribe
// 回合累计口径(in/out/total/cost.total 逐回合累加)。reasoning 计入口径:pi-ai Usage
// output 已含 reasoning,totalTokens 为 provider 实报总量,与旧面同源无分裂。
export function sumUsageState(state) {
  let totalTokens = 0, costCny = 0;
  for (const bucket of [state?.models, state?.tools])
    for (const u of Object.values(bucket ?? {})) {
      totalTokens += u?.totalTokens ?? 0;
      costCny += u?.cost?.total ?? 0;
    }
  return { totalTokens, costCny };
}
