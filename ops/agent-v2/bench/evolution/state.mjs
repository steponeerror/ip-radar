#!/usr/bin/env node
// state.mjs — 自演化循环状态件:冠军指针 + 熄火计数(票 #356 骨架 v1 交付面 1/3)。
//
// 落位 dev/evolution/state.json(主检出锚,与 spend.json 台账同根;env EVOLVE_DEV_ROOT
// 同缝覆写)。形状:{domains:{<domain>:{champion_ref, stall_rounds, halted, halted_reported,
// last_refusal:{code,round_id}|null, last_round_id|null}}}。
//
// 冠军指针(champion_ref):演化循环自有面——按噪声带判冠军后指针自动前移到候选 commit,
// 下轮基线/worktree/矿掘全部从它出发;**master 并入是人裁位,指针不碰 master**(票面
// 「全自动到冠军推荐,冠军并 master 由人裁」)。缺席时首跑种子 = 驱动器所在 repo 的
// HEAD(基线自举,由驱动器写入,本模块不调 git)。
//
// 熄火(票面:连续 3 轮带内零增益自动停并报告):
//   - 只数「完成判定且带内零增益」的轮(gained=false)——增益轮清零;
//   - 护栏红/判定数据不足/提案者失败等未完成判定的轮不加不清(异常另有报告通道,
//     不与熄火混账——熄火语义=花钱量了也没进展,不是机器坏);
//   - stall_rounds 达 3 → halted=true;驱动器推熄火异常并把 halted_reported 置 true
//     (先落 issue 工件再置位;置位前崩溃=下轮补报,置位后=静默拒启不重报,防定时器
//     每拍重推)。装机人处置(改 state.json 或删文件)后自动恢复。
// last_refusal:连续同 code 的拒启(spend_cap/stalled)只在首次开票+推 lark,后续
// 拒启静默留痕(信封照落)——月帽到顶后定时器逐拍重触,不重报即不刷屏。stalled 族
// 的闸是 halted_reported 而非 last_refusal 去重(P2-3:熄火异常已在产出轮报过就静默,
// 未报过(产出轮报前崩溃)则拒启拍补报一次并置位——驱动器 refusal() 执法)。
import fs from "node:fs";
import path from "node:path";
import { evolutionDevRoot } from "./ledger.mjs";

export const STALL_LIMIT = 3; // 票面:连续 3 轮带内零增益熄火

export function evolutionStatePath(env = process.env) {
  return path.join(evolutionDevRoot(env), "state.json");
}

// 读态:缺席=空态;坏=红 fail-closed(指针/熄火是钱和停机的依据,不猜)。
export function readEvolutionState(statePath = evolutionStatePath()) {
  if (!fs.existsSync(statePath)) return { domains: {} };
  let j;
  try { j = JSON.parse(fs.readFileSync(statePath, "utf8")); } catch (e) {
    throw Object.assign(new Error(`dev/evolution/state.json 坏了(不是合法 JSON):${e.message}`), { code: "infra" });
  }
  if (!j || typeof j !== "object" || Array.isArray(j) || typeof j.domains !== "object" || Array.isArray(j.domains))
    throw Object.assign(new Error("dev/evolution/state.json 坏了(domains 缺席)"), { code: "infra" });
  return j;
}

// 原子写(tmp+rename;_ops_store 判例同律)。
export function writeEvolutionState(statePath, state) {
  fs.mkdirSync(path.dirname(path.resolve(statePath)), { recursive: true });
  fs.writeFileSync(`${statePath}.tmp`, JSON.stringify(state, null, 2) + "\n");
  fs.renameSync(`${statePath}.tmp`, statePath);
}

// 域态(缺省形;不整体冻结字段——加字段向后兼容,读面用 ?? 容缺)。
export function domainStateOf(state, domain) {
  const d = state.domains[domain] ?? {};
  return {
    champion_ref: typeof d.champion_ref === "string" ? d.champion_ref : null,
    stall_rounds: typeof d.stall_rounds === "number" ? d.stall_rounds : 0,
    halted: d.halted === true,
    halted_reported: d.halted_reported === true,
    last_refusal: d.last_refusal ?? null,
    last_round_id: d.last_round_id ?? null,
  };
}

function withDomain(state, domain, dom) {
  return { ...state, domains: { ...state.domains, [domain]: dom } };
}

// 轮结果入态(纯函数:返回新 state,调用方负责落盘)。
// {roundId, judged, gained, candidateRef}:judged=false = 未完成判定(护栏红/数据不足/
// 机器坏)——不加不清;judged=true ∧ gained → 指针前移+清零;judged=true ∧ !gained →
// 计数+1,达 STALL_LIMIT 翻 halted(halted_reported 留给驱动器报完再置)。
export function applyRoundOutcome(state, domain, { roundId, judged, gained, candidateRef }) {
  const dom = domainStateOf(state, domain);
  const next = { ...dom, last_round_id: roundId };
  if (judged === true) {
    if (gained === true) {
      if (!candidateRef) throw new Error("增益轮须给 candidateRef(冠军指针前移面)");
      Object.assign(next, { champion_ref: candidateRef, stall_rounds: 0, halted: false, halted_reported: false });
    } else {
      next.stall_rounds = dom.stall_rounds + 1;
      if (next.stall_rounds >= STALL_LIMIT) next.halted = true;
    }
  }
  return withDomain(state, domain, next);
}

// 冠军指针种子(驱动器自举面:状态无指针时锚 repo HEAD;幂等——已行则不动)。
// 种子即时落盘:不落则零增益轮后指针仍空,下轮重新自举到已漂移的 HEAD——冠军面
// 会被 master 走动喑中换掉,违背「指针是循环自有点」的钉死语义。
export function seedChampion(state, domain, ref) {
  const dom = domainStateOf(state, domain);
  if (dom.champion_ref) return state;
  return withDomain(state, domain, { ...dom, champion_ref: String(ref) });
}

// 拒启入态(熄火态已报标记 / 连续同 code 拒启去重面)。
export function applyRefusal(state, domain, { roundId, code }) {
  const dom = domainStateOf(state, domain);
  return withDomain(state, domain, { ...dom, last_refusal: { code, round_id: roundId } });
}

// 熄火报完置位(驱动器在 issue 工件落盘后调用;幂等)。
export function markHaltedReported(state, domain) {
  const dom = domainStateOf(state, domain);
  return withDomain(state, domain, { ...dom, halted_reported: true });
}
