#!/usr/bin/env node
// ledger.mjs — 自演化循环月帽花费台账(票 #356 骨架 v1 交付面 2)。
//
// 语义:演化循环(跨域:add-domain 首接,rrsi/health 留位)共享一个月帽 ¥200(票面
// 「整个自动循环总帽」);每轮结束入账一次(提案者会话花费 + 本轮真 trial 花费);
// 轮启前读当月累计,超帽拒启(拒跑零花费,先于开 worktree/开沙箱)。
//
// 机制 = spend.json 开沙箱前拦机制的推广(run-trial.mjs F3 #337 同律):
//   - 台账形 = {entries:[{at,round_id,domain,cost_cny}], total_cny}(与 dev/add-bench/
//     spend.json 同形,total_cny 仅展示位);
//   - 总额 = entries 机械回算,不信存量 total_cny 字段(证据回算律);
//   - 坏台账 fail-closed 红(不是合法 JSON / entries 缺席 / cost_cny 非有限数),
//     不猜不重建;
//   - 「累计超帽」= 追加后当月总额严格大于帽才拦(与 admitTrialSpend 同边界)。
//   差异面(推广点):月窗 = 记账 at 的 ISO 年月与「现在」同月才计入(票面月帽语义;
//     trial 台账是累计-无窗,两帽并存两律,各自执法)。落位 dev/evolution/spend.json
//     (主检出锚,worktree 跑法下证据不随树删——spendDirFor 同律),env
//     EVOLVE_DEV_ROOT 覆写(测试/搬家隔离缝)。
// 帽缺省 200,env EVOLVE_SPEND_CAP_CNY 覆写(非负数,非法=用法红)。
import fs from "node:fs";
import path from "node:path";
import { mainCheckoutRoot } from "../leak-check.mjs"; // 主检出锚单源(#337 P2-2 同算式)

const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // evolution → 仓根(4 层)

export const EVOLUTION_SPEND_DIR = path.join(ROOT, "dev", "evolution");
export function evolutionDevRoot(env = process.env) {
  if (env.EVOLVE_DEV_ROOT) return path.resolve(env.EVOLVE_DEV_ROOT);
  return path.join(mainCheckoutRoot(ROOT) ?? ROOT, "dev", "evolution");
}
export const EVOLUTION_LEDGER_FILE = path.join(EVOLUTION_SPEND_DIR, "spend.json");

export function evolutionSpendCapCny(env = process.env) {
  const raw = env.EVOLVE_SPEND_CAP_CNY;
  if (raw === undefined || raw === "") return 200;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0)
    throw Object.assign(new Error(`EVOLVE_SPEND_CAP_CNY 须为非负数,得到:${raw}`), { usage: true });
  return n;
}

// 月窗键:ISO 时间戳的年月(at 为 ISO 串;非 ISO 行=坏台账红,fail-closed)
export function monthKeyIso(at, now = new Date()) {
  const m = /^(\d{4})-(\d{2})-/.test(String(at)) ? String(at).match(/^(\d{4})-(\d{2})-/).slice(1, 3).join("-") : null;
  if (!m) throw Object.assign(new Error(`dev/evolution/spend.json 坏了(at 非形:${String(at).slice(0, 40)})`), { code: "infra" });
  return m;
}

// 当月累计(回算律;缺席=0;坏=红)。读面单源:admit 与报告共用。
export function monthSpendTotalCny(ledgerPath = EVOLUTION_LEDGER_FILE, now = new Date()) {
  if (!fs.existsSync(ledgerPath)) return 0;
  let j;
  try { j = JSON.parse(fs.readFileSync(ledgerPath, "utf8")); } catch (e) {
    throw Object.assign(new Error(`dev/evolution/spend.json 坏了(不是合法 JSON):${e.message}`), { code: "infra" });
  }
  if (!j || !Array.isArray(j.entries) || j.entries.some((e) => typeof e?.cost_cny !== "number" || !Number.isFinite(e.cost_cny) || typeof e?.at !== "string"))
    throw Object.assign(new Error("dev/evolution/spend.json 坏了(entries 缺席或 cost_cny/at 非法)"), { code: "infra" });
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  return j.entries.filter((e) => monthKeyIso(e.at) === month).reduce((a, e) => a + e.cost_cny, 0);
}

// 轮启准入(拒启面):当月累计超帽 → {ok:false,code:"spend_cap"}(先于一切花费动作)。
export function admitEvolutionRound({ ledgerPath = EVOLUTION_LEDGER_FILE, env = process.env, now = new Date() } = {}) {
  const cap = evolutionSpendCapCny(env);
  const total = monthSpendTotalCny(ledgerPath, now);
  if (total > cap)
    return { ok: false, code: "spend_cap", message: `演化循环当月累计 ¥${total.toFixed(4)} 超月帽 ¥${cap}(env EVOLVE_SPEND_CAP_CNY 可覆写):本轮拒启,下月窗自动恢复` };
  return { ok: true, cap, total };
}

// 轮后入账(提案者 + 真 trial 花费一次一笔;faux 面 cost=0 也入账留痕)。
// 坏台账在 monthSpendTotalCny 准入面已拦;到这再坏=追加竞态损坏,红不重建。
// 原子写(P2-①,tmp+rename;state.mjs writeEvolutionState 同款):直写被击杀在
// 半途=台账撕裂→整循环 infra 红停摆;tmp+rename 保证任一崩溃点台账要么旧值要么
// 新值,永不撕裂。余窗(入账完→round.json 回写 ledger_appended_cny 前)重入会补差
// 双记——方向多记=fail-closed(月帽早拒不晚拒),窗 ms 级,与断点件补差面(P1-2)
// 同容忍度。
export function appendEvolutionSpend({ ledgerPath = EVOLUTION_LEDGER_FILE, roundId, domain, costCny, now = new Date() }) {
  const p = path.resolve(ledgerPath);
  let entries = [];
  if (fs.existsSync(p)) {
    try {
      const j = JSON.parse(fs.readFileSync(p, "utf8"));
      if (j && Array.isArray(j.entries)) entries = j.entries;
    } catch {
      throw Object.assign(new Error("dev/evolution/spend.json 坏了(追加前解析失败)"), { code: "infra" });
    }
  }
  const cost = Number(costCny);
  if (!Number.isFinite(cost)) throw Object.assign(new Error(`costCny 须为有限数,得到:${costCny}`), { usage: true });
  entries = [...entries, { at: now.toISOString(), round_id: roundId, domain, cost_cny: cost }];
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(`${p}.tmp`, JSON.stringify({ entries, total_cny: entries.reduce((a, e) => a + e.cost_cny, 0) }, null, 2) + "\n");
  fs.renameSync(`${p}.tmp`, p);
}
