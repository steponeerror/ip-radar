// pipeline/budget.mjs — P15 预算四界(#199 交付A):旋钮读面 + 环内执法纯函数 + 月度准入 + 调用哈希。
// 单源纪律:OPS_PIPELINE_* 预算旋钮的名字/缺省/校验只在本文件;引擎(pipeline.mjs 检查点)与
// 双面准入(pipeline.mjs runPipeline / agent.mjs runRound)共用本面,不另起炉灶。
// 旋钮校验沿 mkCtx 判例(OPS_PIPELINE_BUDGET_CNY,2026-10):非负有限数,否则 throw {usage:true}
// → CLI 用法错 exit 2,不带病跑轮(零 sick rounds)。
// 四界(#199):①整轮模型调用数帽 ②整轮 token 轨迹预算 ③整轮墙钟 ④整轮花费帽;
// 月度帽(A2)与同参调用拦截线(A4)同表读面。执法语义=宁少算:违界即停后续模型调用
// (不重试——重试=再烧 token;不逐假设降级——降级=继续跑后续假设),已写工件/台账照留
// (哲学①证据永不灭失:已花 token 的证据留存,failStage 落终态)。
// (月度准入/调用哈希面见 A2/A4 段——同文件追加,不另起炉灶)

// 旋钮读面(#199;名字=env 键,缺省=生产口径;改缺省=spec 变更须过票)。点形字面读是刻意的:
// 对拍扫描器(computeReads)只认 process.env.NAME 字面点形,计算下标 env[name] 是已声明盲区
// ——旋钮名单因此不抽象成表驱动(BUDGET_KNOBS 曾试,扫描面丢失即契约对拍丢管)。
const readKnob = (name, raw, def) => { // raw=env 优先(测试注入)与 process.env 字面兜底的合成;非法=用法错
  const s = raw ?? def;
  const v = +s;
  if (!Number.isFinite(v) || v < 0)
    throw Object.assign(new Error(`${name} 须为非负数,得到:${s}`), { usage: true });
  return v;
};

// 读全旋钮(校验同 mkCtx 判例;mkCtx/runRound/门读面共用)。
export function readBudgetKnobs(env = process.env) {
  return {
    maxModelCalls: readKnob("OPS_PIPELINE_MAX_MODEL_CALLS", env.OPS_PIPELINE_MAX_MODEL_CALLS ?? process.env.OPS_PIPELINE_MAX_MODEL_CALLS, "12"), // ①整轮模型调用数帽(attempt 即调用:重试同计,faux 面同执法)
    tokenBudget: readKnob("OPS_PIPELINE_TOKEN_BUDGET", env.OPS_PIPELINE_TOKEN_BUDGET ?? process.env.OPS_PIPELINE_TOKEN_BUDGET, "200000"), // ②整轮 token 轨迹预算(结算后查)
    wallClockS: readKnob("OPS_PIPELINE_WALL_CLOCK_S", env.OPS_PIPELINE_WALL_CLOCK_S ?? process.env.OPS_PIPELINE_WALL_CLOCK_S, "1800"), // ③整轮墙钟秒(步边界+逐假设查;started_at 起)
    spendCapCny: readKnob("OPS_PIPELINE_SPEND_CAP_CNY", env.OPS_PIPELINE_SPEND_CAP_CNY ?? process.env.OPS_PIPELINE_SPEND_CAP_CNY, "3"), // ④整轮花费帽 ¥(结算后查;月度帽另键)
    monthlyCapCny: readKnob("OPS_PIPELINE_MONTHLY_CAP_CNY", env.OPS_PIPELINE_MONTHLY_CAP_CNY ?? process.env.OPS_PIPELINE_MONTHLY_CAP_CNY, "30"), // 月度 kill switch 帽 ¥(A2 准入面)
    dupCallLimit: readKnob("OPS_PIPELINE_DUP_CALL_LIMIT", env.OPS_PIPELINE_DUP_CALL_LIMIT ?? process.env.OPS_PIPELINE_DUP_CALL_LIMIT, "3"), // 同参调用拦截线(A4;第 limit 次同参调用即拦;0=停用)
  };
}

// —— 四界环内执法(纯函数;pipeline.mjs runModelStage/runStages 检查点调用)——
// ①调用数帽:attempt 前查(calls=已计调用数;calls+1=本次将成第几次;> 帽即违界)。
export const overCallsCap = (calls, cap) => calls + 1 > cap;
// ②token 预算 / ④花费帽:结算后查(累计 vs 帽;等号=帽内放行)。
export const overTokenBudget = (totalTokens, cap) => totalTokens > cap;
export const overSpendCap = (cost, cap) => cost > cap;
// ③墙钟:started_at(ISO)起的流逝秒(毫秒精度;不可解析起点的退化轮=0 不误杀)。
export function elapsedWallS(startedAtIso, now = Date.now()) {
  const t0 = Date.parse(startedAtIso);
  return Number.isFinite(t0) ? Math.max(0, (now - t0) / 1000) : 0;
}
export const overWallClock = (startedAtIso, cap, now = Date.now()) => elapsedWallS(startedAtIso, now) > cap;
