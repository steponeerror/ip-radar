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
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFileCb);
const LIBSH = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "lib.sh"); // ops/agent/lib.sh(steps.mjs sh() 同形)

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

// 发现轮旋钮族(#207 T1;ADR 0010;spec /tmp/discover-pipeline-spec.md T4 首月缺省):三旋钮独立
// (轮内调用帽/墙钟/花费帽,宁少算:发现轮无 token 界——不预设轨迹预算,四界只执①③④);月帽
// 共享 OPS_PIPELINE_MONTHLY_CAP_CNY 同键同源(月帽是全 agent 面共享底线,不另立月门:admitOrRefuse
// 同一函数消费,双拒跑同码同文案)。dup 面沿 OPS_PIPELINE_DUP_CALL_LIMIT 同键同缺省
// (#217 T3.5 接线消费:发现工具宿主 mkDiscoveryHost dupLimit;原「T3 接线时消费」注记兑现);
// 哈希 dupKey 沿用不另立。
export function readDiscoverKnobs(env = process.env) {
  return {
    maxModelCalls: readKnob("OPS_DISCOVER_MAX_MODEL_CALLS", env.OPS_DISCOVER_MAX_MODEL_CALLS ?? process.env.OPS_DISCOVER_MAX_MODEL_CALLS, "30"), // ①整轮模型调用数帽(30 调用)
    wallClockS: readKnob("OPS_DISCOVER_WALL_CLOCK_S", env.OPS_DISCOVER_WALL_CLOCK_S ?? process.env.OPS_DISCOVER_WALL_CLOCK_S, "3600"), // ③整轮墙钟秒
    spendCapCny: readKnob("OPS_DISCOVER_SPEND_CAP_CNY", env.OPS_DISCOVER_SPEND_CAP_CNY ?? process.env.OPS_DISCOVER_SPEND_CAP_CNY, "5"), // ④整轮花费帽 ¥
    monthlyCapCny: readKnob("OPS_PIPELINE_MONTHLY_CAP_CNY", env.OPS_PIPELINE_MONTHLY_CAP_CNY ?? process.env.OPS_PIPELINE_MONTHLY_CAP_CNY, "30"), // 月帽共享(与 readBudgetKnobs 同键同缺省)
    dupCallLimit: readKnob("OPS_PIPELINE_DUP_CALL_LIMIT", env.OPS_PIPELINE_DUP_CALL_LIMIT ?? process.env.OPS_PIPELINE_DUP_CALL_LIMIT, "3"), // 同参调用拦截线(#217 T3.5:发现宿主 dupLimit 消费;同键同缺省不另立)
  };
}

// —— 四界环内执法(纯函数;pipeline.mjs runModelStage/runStages 检查点调用)——
// ①调用数帽:attempt 前查(calls=已计调用数;calls+1=本次将成第几次;> 帽即违界)。
export const overCallsCap = (calls, cap) => calls + 1 > cap;
// ②token 预算 / ④花费帽:结算后查(累计 vs 帽;等号=帽内放行)。
export const overTokenBudget = (totalTokens, cap) => totalTokens > cap;
export const overSpendCap = (cost, cap) => cost > cap;
// ③墙钟:started_at(ISO)起的流逝秒(毫秒精度;不可解析起点的退化轮=0 不误杀)。
// 帽=0 语义=零预算即拒(t=0 也超)——与 DUP_CALL_LIMIT/THRESHOLD 的「0=停用」分立:那两处是拦截线,
// 本处是预算帽(帽为零=什么都不许);停用墙钟=设大值。判例:2026-10-26 CI 首步边界与轮始同毫秒,
// 0.0001 帽竞态假绿(0>0 为假),改零帽+本特例后确定性无时序窗。
export function elapsedWallS(startedAtIso, now = Date.now()) {
  const t0 = Date.parse(startedAtIso);
  return Number.isFinite(t0) ? Math.max(0, (now - t0) / 1000) : 0;
}
export const overWallClock = (startedAtIso, cap, now = Date.now()) =>
  cap === 0 ? true : elapsedWallS(startedAtIso, now) > cap;

// —— 月度 kill switch 准入(A2;双面共享:pipeline.mjs runPipeline / agent.mjs runRound)——
// 容器本地月(monthNow:YYYY-MM);读台账当月行 Σcost(锁内读,与 A3 锁同域
// <ledger>.lock);Σ+本轮预算 est > 月帽 → 拒跑(信封 code=budget_monthly + exit 1 +
// 台账留痕行)。无台账/空文件 = 0 起步照跑;缺 cost 行跳过不猜(无证据即无话),
// 跳过数入读数面(09-budget.json A5 观察面)。
export const monthNow = (now = new Date()) => `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

// 纯函数:台账文本 → 当月花费读数。行形 `| 日期 | 轮次 | model | 用量 | 备注 |`
// (日期=YYYY-MM-DD;cost= 在用量列)。表头/分隔行/异形日期不计不入 skipped;
// 当月行缺 cost= → skipped+1(不猜零:无法计 = 记缺口,不是免费)。
export function monthSpendOfLedgerText(text, month) {
  let spend = 0, counted = 0, skipped = 0;
  for (const line of String(text ?? "").split("\n")) {
    if (!line.startsWith("|")) continue;
    const cells = line.split("|").map((c) => c.trim());
    const date = cells[1] ?? "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !date.startsWith(`${month}-`)) continue;
    const m = /(?:^|\s)cost=([0-9]+(?:\.[0-9]+)?)/.exec(cells[4] ?? "");
    if (!m) { skipped += 1; continue; }
    spend += +m[1]; counted += 1;
  }
  return { spend, counted, skipped };
}

// 纯函数:准入裁决(等号=帽内放行;est=本轮预算上界,宁少算口径)。
// 容差口径唯一真源集中此一处(#203 C2 P2 附注):现行=精确比较无 ε(spend+est>cap 才拒,
// spec 钉「等号放行」);轮预算面 gates.mjs/steps.mjs 的 +1e-9 灰尘容差是其各自面的先例,
// 不入本面;若将来月帽要加 ε,只许加在此处(admitOrRefuse 外壳与双面不得另立容差)。
export const admitMonthly = ({ spendCny, estCny, capCny }) => {
  const projected = spendCny + estCny;
  return { ok: projected <= capCny, projected };
};

export const ledgerLockPath = (ledgerFile) => `${ledgerFile}.lock`; // 与 python _ops_store.LEDGER_LOCK_NAME /lib.sh "$LEDGER_FILE.lock" 同锁域(对拍哨钉)

// 锁内读台账全文(#139 锁形制:flock(1) 同锁域 <ledger>.lock,与 lib.sh/_ops_store 双写面互斥;
// 无台账 = "" 起步)。cat 经 flock 持锁窗口,读与写不交错。
export async function readLedgerTextLocked(ledgerFile) {
  if (!fs.existsSync(ledgerFile)) return "";
  return (await execFileP("flock", ["-w", "30", ledgerLockPath(ledgerFile), "cat", ledgerFile],
    { timeout: 60_000, maxBuffer: 16 * 1024 * 1024 })).stdout;
}

// 准入全流程(读→解→裁;月帽/本轮预算由调用方给,双面各自同形调)。
export async function monthlyAdmission({ ledgerFile, capCny, estCny, now = new Date() }) {
  const month = monthNow(now);
  const { spend, counted, skipped } = monthSpendOfLedgerText(await readLedgerTextLocked(ledgerFile), month);
  const verdict = admitMonthly({ spendCny: spend, estCny, capCny });
  return { ...verdict, month, spend, counted, skipped, est: estCny, cap: capCny };
}

// 拒跑留痕行(经 lib.sh ledger_append 写,表头自建/A3 后自带锁;model/用量列=—,备注列=拒跑读数)。
export async function appendRefusalTrace(ledgerFile, { est, cap }, env = process.env, round = "health") { // round 参数化(#207):发现轮立项后拒跑留痕轮次列随轮型,不再硬编码
  return execFileP("bash", ["-c", `. "$0"; ledger_append "$@"`, LIBSH, round, "—", "—",
    `budget_monthly refused est=${est} cap=${cap}`], { timeout: 120_000, maxBuffer: 32 * 1024 * 1024, env: { ...env, LEDGER_FILE: ledgerFile } });
}

// —— 拒跑块单源(#203 C2):admitOrRefuse 留痕外壳 + refusalOf 纯文案 ——
// 收口判例:拒跑块(文案/台账留痕行/[admission] log)曾双面逐字复制(agent.mjs runRound ↔
// pipeline.mjs runPipeline,#200 Spec 轴核),漂移靠人记;单源后两面只映射出口——agent 面
// throw {code}(main 兜底信封 exit 1)、pipeline 面 emitFail(code, message)(信封 exit 1),
// 出口形状不属本壳(信封纪律:两面行为/日志/台账行/exit code 逐字不变)。
// 纯函数面:裁决真源仍是 admitMonthly(容差语义见其注);refusalOf 只做文案单源。
export const refusalOf = (a) => ({
  code: "budget_monthly",
  message: `月度预算拒跑:当月已花 ¥${a.spend} + 本轮预算 ¥${a.est} > 月帽 ¥${a.cap}(OPS_PIPELINE_MONTHLY_CAP_CNY;当月 ${a.counted} 行计入,${a.skipped} 行缺 cost 跳过不猜)`,
});
// 留痕外壳:monthlyAdmission 读→裁;拒跑则 [admission] log + 台账留痕行(写败只 log 不
// 翻转裁决——宁拒不跑),返回 {refused:true, code, message};放行返回 {refused:false,
// admission}(读数对象原样回传,state.monthly_admission/09-budget.json 观察面字节不变)。
export async function admitOrRefuse({ ledgerFile, capCny, estCny, env, log, round = "health" }) { // round 只影响留痕轮次列(#207);裁决真源 admitMonthly 与两面出口形状不变
  const admission = await monthlyAdmission({ ledgerFile, capCny, estCny });
  if (admission.ok) return { refused: false, admission };
  log(`[admission] budget_monthly refused month=${admission.month} spend=${admission.spend} est=${admission.est} cap=${admission.cap} skipped=${admission.skipped}`);
  try { await appendRefusalTrace(ledgerFile, { est: estCny, cap: capCny }, env, round); }
  catch (e) { log(`[admission] 拒跑留痕行写败(不翻转裁决):${e.message}`); } // 台账写败不吞拒跑:宁拒不跑
  return { refused: true, ...refusalOf(admission) };
}

// (调用哈希面见 A4 段——同文件追加,不另起炉灶)
import { createHash } from "node:crypto";

// —— 重复调用哈希(A4;双面注入:tools.mjs ToolHost.beforeToolCall / microprobes.mjs)——
// 同参白烧判例(2026-10-24 01:59:真面同参数重发连环烧 token零新读数):第 limit 次同参调用
// 拦(code=repeat_storm);合法瞬态重试≤2 不受影响(第 1 次+1 重试=2 < 3)。计数面入
// 09-budget.json dup_top3(A5;观察非裁决)。0=停用。
// canonicalJson:递归键序稳定化(数组保序——顺序是语义);undefined 归一 null(与 JSON.stringify 同)。
export function canonicalJson(v) {
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(",")}]`;
  if (v && typeof v === "object")
    return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canonicalJson(v[k])}`).join(",")}}`;
  return JSON.stringify(v) ?? "null";
}
// 键=sha256(tool + "\n" + canonicalJson(args)) 前 16 hex(观察面非安全面:碰撞率足够低)。
export const dupKey = (tool, args) =>
  createHash("sha256").update(`${tool}\n${canonicalJson(args ?? {})}`).digest("hex").slice(0, 16);
// 记录一次调用尝试(尝试即计——执行前拦;返回 blocked=第 limit 次及以后)。registry=Map(key→{tool,key,count})。
export function dupRecord(registry, tool, args, limit) {
  const key = dupKey(tool, args);
  const prev = registry.get(key) ?? { tool, key, count: 0 };
  prev.count += 1;
  registry.set(key, prev);
  return { count: prev.count, blocked: limit > 0 && prev.count >= limit };
}
// 观察面:计数前 N 降序(09-budget.json dup_top3;A5 工件面)。
export const dupTop = (registry, n = 3) =>
  [...registry.values()].sort((a, b) => b.count - a.count).slice(0, n).map((r) => ({ tool: r.tool, key: r.key, count: r.count }));
