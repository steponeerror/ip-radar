#!/usr/bin/env node
// run-round.mjs — 自演化循环轮驱动器(票 #356 RSI 骨架 v1 交付面 1;排程入口)。
//
// 一轮无人值守演化(演化轴;票面「排程自起、提案自改、trial 与护栏自跑、按噪声带
// 自判冠军;冠军并 master 由人裁」):
//   ⓪′ 启动对账(P2-4②+P2-②):扫 dev/evolution/rounds 的无终态孤儿轮逐个按
//      finishFailed 语义收口(断点件在账花费补差入台账+state 留痕+孤儿信封/报告+
//      异常出口;本轮 roundId 跳过=同轮断点续跑是预期流);pre-flush 孤儿(有会话痕迹
//      evolve.sqlite 而断点件从未落盘——崩在提案者会话窗)花费不可追,按「追不回
//      留痕」落零费信封(orphan_pre_flush);收完才准启新轮。
//   ⓪ 拒启双面前置:熄火态(state.json halted)→ 拒;当月累计超月帽 ¥200
//      (dev/evolution/spend.json,ledger.mjs)→ 拒。拒启零花费零建面。
//   ① 基线:冠军指针(state.json champion_ref;缺席=repo HEAD 自举)→ 冠军面
//      worktree(dev/evolution/champions/<域>,跨轮复用)+ 提案者 worktree
//      (dev/evolution/worktrees/<roundId>,分支 evolve/<roundId>,基=冠军面)。
//   ② 矿掘:上一轮候选面 sweep 经 mine-failures.mjs 出报告(提案者第一输入;
//      首轮无 → 占位文本)。
//   ③ 提案者 = 无头 agent 会话(pi-durable 会话 + ADD_TOOLS_EXTENSION 编码工具闭集,
//      instructions=bench/add-domain/SKILL.md,submit 简报=轮次+矿掘报告;机制取舍见
//      本文件尾注「提案者机制取舍」)。产物=worktree 内可归因编辑 + 终答报告。
//   ④ 三护栏(候选 worktree 内跑,票面原句:v2 npm test + leak gate + faux 冒烟):
//      头部先跑驱动器侧 diff 面闸(P1-1)——候选改动(championRef..HEAD 已提交 +
//      untracked)触保护名单(域适配器 protectedFaces:答案/裁判/判分/记账面+
//      护栏执法链三单件,delta P1)=护栏红同罚;执法在驱动器主检出跑,候选树内碰不到
//      执法件。护栏红=候选作废轮终,异常报告,零真 trial 花费。护栏块前先用主检出副本
//      覆写候选树 node_modules(P2-③:node_modules 是 gitignored,两闸腿对它不可见
//      且提案者可改)。
//   ⑤ 同会话成对 trial 批(长期授权 m01882 面):逐题逐副本冠军面/候选面相邻各跑
//      一次 run-trial(面=各自 worktree 的提示词/工具/任务接线整体);真面开沙箱前
//      花费帽由 run-trial 自查(dev/add-bench/spend.json #337 机制复用,faux 不查不记);
//      崩溃重入按 trial.json 断点续跑(已跑副本复用不重跑不重记账)。
//   ⑥ 判分=run-trial 内 score.mjs(#343 分级钥匙 score_frac);judge.mjs 同会话成对
//      +噪声带判冠军候选:gained → 循环冠军指针前移到候选 commit(master 并入仍是
//      人裁位);带内零增益 → 熄火计数+1,连续 3 轮 → halted+熄火异常。
//   ⑦ 花费入账(提案者会话 + 本轮新跑 trial)→ 轮报告 report.md + envelope.json +
//      每轮 gh 票;异常(熄火/超帽/护栏红/判定数据不足/提案者失败)推 lark
//      (exits.mjs,复用 finding 通道契约);全部出口永不败轮、全稿落工件。
//
// 域配置化:域依赖收口 domains.mjs 适配器表(首接 add-domain;rrsi/health 留位)。
// 明确不做(票面):自动并 master/部署、运营轴、真扫描进测试(端到端冒烟全 faux)。
//
// 用法:node bench/evolution/run-round.mjs [roundId] --domain add-domain
//        [--model provider/modelId] [--k 3] [--repo DIR] [--universe PATH] [--cards-dir DIR]
//        [--fixtures DIR](提案者 faux 面)[--trial-fixtures DIR](trial faux 面)
//        [--dev-root DIR][--db PATH][--dry-run-exits]
//   roundId 缺省 = 现铸 YYYY-MM-DD-HHMM-evolve(排程面;形状律同 run-add 族)。
//   real 面 --model 必填(提案者与 trial 同模型;faux 面零网络零花费)。
// 退出码:0=轮完成且判定落定(gained/zero_gain);1=refused/failed;2=用法;3=运行期异常。
// stdout 末行=单行 JSON 轮信封(ENVELOPE.md 律:进度走 stderr;本文件是新入口,非旧形
// 冻结对拍面,信封形状以本文件头注+测试钉)。
//
// ── 提案者机制取舍(durable 会话,非 `pi -p` 子进程)──
//   选 pi-durable 会话(openHarness+conversation.submit)而非 spawn `pi -p`:
//   ①花费计量单源:harness.usage() 直接出 costCny 入台账(pi -p 需另解析 CLI json
//   输出,该输出形状不在仓内契约面);②罐装模型面现成:fauxAddBundle 注入缝=端到端
//   冒烟零新机制(pi -p 的 faux 面要另造假 CLI);③崩溃续跑:同库同 requestId 重放
//   幂等(resume.test.mjs 判例),排程器重启不双花;④工具闭集复用:
//   ADD_TOOLS_EXTENSION 的 write_file/run_bash/run_pytest 自带沙箱遏制(宿主锚
//   worktree),与加源轮同一套执法。代价:提案者无任务级相位 checkpoint(单 submit
//   整体结算,崩在中途=重放同 requestId 续跑)——骨架 v1 可接受,重相位化等健康轮
//   基准后的节奏定档再议。
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { ADD_TOOLS_EXTENSION } from "../../registry.mjs";
import { openHarness } from "../../entry.mjs";
import { sumUsageState } from "../../tasks/budget-guard.mjs";
import { resolveAddPython, fauxAddBundle } from "../../run-add.mjs";
import { ensureAddHost } from "../../tools/add-tools.mjs";
import { mainCheckoutRoot } from "../leak-check.mjs";
import { mineSweepDir, renderReport } from "../add-domain/mine-failures.mjs";
import { evolutionDevRoot, admitEvolutionRound, appendEvolutionSpend, monthSpendTotalCny, evolutionSpendCapCny } from "./ledger.mjs";
import {
  evolutionStatePath, readEvolutionState, writeEvolutionState, domainStateOf,
  applyRoundOutcome, applyRefusal, markHaltedReported, seedChampion, STALL_LIMIT,
} from "./state.mjs";
import { judgePaired } from "./judge.mjs";
import { openRoundIssue, pushAnomalyLark } from "./exits.mjs";
import { evolutionDomainOf } from "./domains.mjs"; // 域适配器(含保护名单 protectedFaces,单源 domains.mjs,delta P1)

const execFileP = promisify(execFileCb);
const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // evolution → 仓根(4 层)
const ROUND_ID_RE = /^\d{4}-\d{2}-\d{2}-\d{4}-evolve(-r\d+)?$/;
// 相位序(断点件 phase 的推进面):init→proposed→guarded→sweeping→swept;崩在 sweeping
// 重入只续 sweep(副本级 trial.json 续跑),不重开提案者/不重跑护栏(防双花双跑)。
const PHASE_RANK = Object.freeze({ init: 0, proposed: 1, guarded: 2, sweeping: 3, swept: 4 });
const phaseAtLeast = (rj, name) => (PHASE_RANK[rj?.phase] ?? 0) >= PHASE_RANK[name];;
const TRIAL_TIMEOUT_MS = 45 * 60_000; // 单 trial 上限(手动演化线 sweep.mjs 同值)
const GIT_ID = ["-c", "user.email=evolve@ipradar.local", "-c", "user.name=evolve-driver", "-c", "commit.gpgsign=false"]; // 提案者漏提交时驱动器代提交的干净身份

// 驱动器侧 diff 面闸(P1-1):候选 worktree 的已提交改动(baseRef..HEAD,--no-renames
// 连改名出的旧路径一并显形)与 untracked 文件(--exclude-standard 非忽略面)中触
// 保护名单的路径。名单按域注入(faces=adapter.protectedFaces,单源 domains.mjs;
// 缺席/空=用法红——接线新域漏声明即红,不静默绿)。返回触表路径列表(空=绿)。
// 执法代码在驱动器主检出,候选树内的任何编辑都碰不到本函数本体。
export async function diffFaceGateTouched(exec, { worktree, baseRef, faces }) {
  if (!Array.isArray(faces) || !faces.length)
    throw Object.assign(new Error("保护名单缺席:diff 面闸须域适配器 protectedFaces(非空 pathspec 数组;接线新域漏声明=此处红,不静默绿)"), { usage: true });
  const committed = (await git(exec, worktree, ["diff", "--name-only", "--no-renames", baseRef, "HEAD", "--", ...faces])).split("\n").filter(Boolean);
  const untracked = (await git(exec, worktree, ["ls-files", "--others", "--exclude-standard", "--", ...faces])).split("\n").filter(Boolean);
  return [...new Set([...committed, ...untracked])];
}

export function mintEvolveRoundId(now = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}-evolve`;
}

const lastText = (view) => (view.entries.filter((e) => e.kind === "pi.assistant").at(-1)?.model ?? [])
  .flatMap((m) => m.content ?? []).find((b) => b.type === "text")?.text ?? "";

// git 薄包(exec 注入缝;失败红带 stderr 尾)
async function git(exec, cwd, args) {
  try {
    const { stdout } = await exec("git", ["-C", cwd, ...args], { maxBuffer: 16 * 1024 * 1024 });
    return String(stdout ?? "").trim();
  } catch (e) {
    throw Object.assign(new Error(`git ${args.join(" ")} 红(rc=${typeof e.code === "number" ? e.code : "?"}):${String(e.stderr ?? e.message).slice(0, 200)}`), { code: "infra" });
  }
}

const readJsonIf = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const writeJsonAtomic = (p, j) => {
  fs.mkdirSync(path.dirname(path.resolve(p)), { recursive: true });
  fs.writeFileSync(`${p}.tmp`, JSON.stringify(j, null, 2) + "\n");
  fs.renameSync(`${p}.tmp`, p);
};

// 提案者简报(工作指令=SKILL.md 已进会话 instructions;这里是轮次输入:基线+矿掘+交付要求)
export function proposerBriefing({ roundId, domain, championRef, miningText }) {
  return [
    `演化轮 ${roundId}(域 ${domain})。基线(循环冠军面)= ${championRef};你的工作树即提案 worktree,编码工具只在此树内可用。`,
    "",
    "矿掘报告(上一轮候选面 sweep 的失败层位;首轮或缺席时为占位):",
    "```",
    String(miningText),
    "```",
    "",
    "按 SKILL.md 工作循环:读矿掘 → 提可归因编辑(开放面内,禁门段/测试/考题面)→ 自跑三护栏 → 终答=完整提案者报告(markdown:每编辑的改了什么/假设/预期救回哪层哪些断言/护栏结果)。",
    "编辑须提交为 worktree 内 git commit(终答前提交完毕);终答文本只放报告本身。",
  ].join("\n");
}

// 矿掘输入:状态件 last_round_id 指向的上一轮候选面 sweep;缺席=首轮占位。
export function minePreviousRound({ devRoot, previousRoundId }) {
  if (!previousRoundId) return { text: "(首轮:无历史 sweep,无矿掘输入——按 SKILL.md 域内先验自选杠杆)", source: null };
  const sweepDir = path.join(devRoot, "rounds", previousRoundId, "sweeps", "candidate");
  if (!fs.existsSync(sweepDir)) return { text: `(上一轮 ${previousRoundId} 无候选面 sweep 工件,矿掘缺席)`, source: null };
  try {
    return { text: renderReport(mineSweepDir(sweepDir)), source: sweepDir };
  } catch (e) {
    return { text: `(矿掘红:${String(e.message).slice(0, 160)}——按域内先验继续,异常已入轮报告)`, source: sweepDir, error: String(e.message).slice(0, 160) };
  }
}

// ── 默认 trial 执行器:spawn 面自己的 run-trial.mjs(面=该检出的提示词/工具/任务接线)──
// 返回解析后的 trial.json(读数真源);exit 4(bench_stop/spend_cap)→ 抛 trial_spend_cap
// 由驱动器停批(后续真 trial 必然同拒,不逐题空转)。
async function spawnTrialCli(exec, { faceRepo, runnerJs, name, cardPath, runDir, modelRef, fixturesDir, timeoutMs }) {
  const args = ["--name", name, "--card", cardPath, "--run-dir", runDir, "--repo", faceRepo];
  if (modelRef) args.push("--model", `${modelRef.provider}/${modelRef.modelId}`);
  if (fixturesDir) args.push("--fixtures", fixturesDir);
  try {
    await exec("node", [runnerJs, ...args], { timeout: timeoutMs ?? TRIAL_TIMEOUT_MS, maxBuffer: 32 * 1024 * 1024 });
  } catch (e) {
    if (e?.code === 4)
      throw Object.assign(new Error(`trial 花费帽拒跑(${name}@${faceRepo}):run-trial exit 4(bench_stop/spend_cap)`), { code: "trial_spend_cap" });
    // 其余退出码(含 trial 红 exit 1):trial.json 是读数真源,落了照读;没落=崩面,读数缺席入 missing
  }
  const t = readJsonIf(path.join(runDir, name, "trial.json"));
  if (!t) throw Object.assign(new Error(`trial 信封缺席:${path.join(runDir, name, "trial.json")}(轮崩溃/中断面)`), { code: "infra" });
  return t;
}

// ── 启动对账(P2-4②):孤儿轮收口,按 finishFailed 语义在启动时补走──
// systemd 击杀(TimeoutStartSec)/机器重启路径:死轮的 finishFailed 不执行,花费
// 永不入月帽、无终态信封;下拍新 roundId 照启=漏账。本函数扫 dev/evolution/rounds 下
// 无终态的轮(round.json 在 ∧ envelope.json 缺席;envelope 是全出口终态标记),逐个:
//   - 断点件在账花费(proposer_cost_cny+trials_cost_cny)补差入台账(同 P1-2 金额面,
//     幂等不双记);断点件坏/缺域字段=花费不可追,不入台账,信封如实留痕;
//   - state 留痕(applyRoundOutcome judged:false:不加不清熄火账,只记轮号);
//   - 孤儿信封/report/exits 落盘 + gh 票 + 异常 lark(追不回的至少异常报告)。
// 本轮 roundId 跳过(同轮断点续跑是预期流,不是孤儿);对账红(如坏台账)向上抛=
// 运行期异常,新轮不启(调用方先于一切建面/花费动作调本函数)。
// 边界:断点件从未写过的轮(P2-②)分两形——有会话痕迹(evolve.sqlite,崩在提案者
// 会话窗=最长窗)的按「追不回留痕」落零费信封(orphan_pre_flush;花费在 sqlite 里
// 不可追,单库重建留健康轮基准后再议,不伪造入账);无会话痕迹(仅 mining.txt,
// 会话未开零花费)不收口。
export async function reconcileOrphanRounds({ devRoot, skipRoundId = null, env = process.env, exec = execFileP, dryRun, stderr = process.stderr }) {
  const roundsRoot = path.join(devRoot, "rounds");
  const ledgerPath = path.join(devRoot, "spend.json");
  const statePath = evolutionStatePath({ ...env, EVOLVE_DEV_ROOT: devRoot });
  const log = (l) => stderr.write(`${l}\n`);
  const numOr0 = (x) => (typeof x === "number" && Number.isFinite(x) ? x : 0);
  if (!fs.existsSync(roundsRoot)) return [];
  const closed = [];
  for (const name of fs.readdirSync(roundsRoot).sort()) {
    const roundDir = path.join(roundsRoot, name);
    if (fs.existsSync(path.join(roundDir, "envelope.json"))) continue; // 终态在=已收口
    if (name === skipRoundId) continue; // 本轮断点续跑面(同 roundId 复跑续扫是预期流)
    const rjPath = path.join(roundDir, "round.json");
    if (!fs.existsSync(rjPath)) {
      // pre-flush 孤儿(P2-②):会话痕迹在(evolve.sqlite)而断点件从未落盘
      if (!fs.existsSync(path.join(roundDir, "evolve.sqlite"))) continue; // 无会话痕迹=会话未开零花费,不收口
      const message = "启动对账收口:断点件从未落盘(崩在首次落盘前,提案者会话窗)——花费不可追(sqlite 单库重建留健康轮基准后再议),零费信封留痕";
      const costs = { proposer_cny: 0, trials_cny: 0 };
      const title = `[evolve] ${name} ?:failed(orphan_pre_flush)(启动对账)`;
      const body = renderReportMd({ roundId: name, domain: "(域不可知)", code: "orphan_pre_flush", message, costs, monthTotal: monthSpendTotalCny(ledgerPath), cap: evolutionSpendCapCny(env), roundDir });
      const lark = renderLarkPlain({ roundId: name, domain: "(域不可知)", code: "orphan_pre_flush", message, costs, monthTotal: monthSpendTotalCny(ledgerPath), cap: evolutionSpendCapCny(env), roundDir }); // #383:lark 面分稿(双面律)
      const issue = await openRoundIssue({ title, body, dryRun, exec });
      const anomaly = await pushAnomalyLark({ title: lark.title, body: lark.body, env, dryRun, exec });
      const envelope = { ok: false, round: "evolve", round_id: name, domain: null, error: { code: "orphan_pre_flush", message }, spend: { ...costs, appended_now_cny: 0 }, issue, anomaly, reconciled_by_round: skipRoundId };
      fs.writeFileSync(path.join(roundDir, "report.md"), body + "\n");
      writeJsonAtomic(path.join(roundDir, "envelope.json"), envelope);
      writeJsonAtomic(path.join(roundDir, "exits.json"), { round_id: name, issue, anomaly });
      closed.push({ round_id: name, domain: null, appended_cny: 0 });
      log(`[evolve] 启动对账:pre-flush 孤儿轮 ${name} 收口(零费信封留痕);新轮才准启`);
      continue;
    }
    const rj = readJsonIf(rjPath);
    const domain = typeof rj?.domain === "string" ? rj.domain : null;
    const costs = { proposer_cny: numOr0(rj?.proposer_cost_cny), trials_cny: numOr0(rj?.trials_cost_cny) };
    const total = costs.proposer_cny + costs.trials_cny;
    const appended = numOr0(rj?.ledger_appended_cny);
    const first = !(rj && "ledger_appended_cny" in rj);
    const delta = total - appended;
    const recoverable = Boolean(rj && domain);
    let appendedNow = 0;
    if (recoverable && (first || delta > 0)) {
      appendEvolutionSpend({ ledgerPath, roundId: name, domain, costCny: Math.max(delta, 0) });
      appendedNow = Math.max(delta, 0);
      writeJsonAtomic(rjPath, { ...rj, ledger_appended_cny: Math.max(total, appended) }); // 断点件同步已入账额(再对账幂等)
    }
    const message = recoverable
      ? `启动对账收口:上次运行无终态(击杀/崩溃,phase=${rj.phase ?? "init"})——断点件在账花费 ¥${total.toFixed(4)} 补差入月帽 ¥${appendedNow.toFixed(4)};未落断点件的花费不可追`
      : "启动对账收口:断点件不可读或缺域字段——花费不可追,不入台账,仅落终态信封留痕";
    if (domain) {
      writeEvolutionState(statePath, applyRoundOutcome(readEvolutionState(statePath), domain, { roundId: name, judged: false, gained: false, candidateRef: null })); // 未判定轮:不加不清熄火账
    }
    const title = `[evolve] ${name} ${domain ?? "?"}:failed(orphan_reconciled)(启动对账)`;
    const body = renderReportMd({ roundId: name, domain: domain ?? "(域不可知)", code: "orphan_reconciled", message, costs, monthTotal: monthSpendTotalCny(ledgerPath), cap: evolutionSpendCapCny(env), roundDir });
    const lark = renderLarkPlain({ roundId: name, domain: domain ?? "(域不可知)", code: "orphan_reconciled", message, costs, monthTotal: monthSpendTotalCny(ledgerPath), cap: evolutionSpendCapCny(env), roundDir }); // #383:lark 面分稿(双面律)
    const issue = await openRoundIssue({ title, body, dryRun, exec });
    const anomaly = await pushAnomalyLark({ title: lark.title, body: lark.body, env, dryRun, exec });
    const envelope = { ok: false, round: "evolve", round_id: name, domain, error: { code: "orphan_reconciled", message }, spend: { ...costs, appended_now_cny: appendedNow }, issue, anomaly, reconciled_by_round: skipRoundId };
    fs.writeFileSync(path.join(roundDir, "report.md"), body + "\n");
    writeJsonAtomic(path.join(roundDir, "envelope.json"), envelope);
    writeJsonAtomic(path.join(roundDir, "exits.json"), { round_id: name, issue, anomaly });
    closed.push({ round_id: name, domain, appended_cny: appendedNow });
    log(`[evolve] 启动对账:孤儿轮 ${name} 收口(补差入账 ¥${appendedNow.toFixed(4)});新轮才准启`);
  }
  return closed;
}

// ── 一轮(程序面;CLI 与测试共用)──
// 返回 {status:"completed",envelope} | {status:"failed"|"refused",code,envelope}。
export async function runEvolveRound(opts) {
  const env = opts.env ?? process.env;
  const exec = opts.exec ?? execFileP;
  const stderr = opts.stderr ?? process.stderr;
  const log = (l) => stderr.write(`${l}\n`);
  const dryRun = opts.dryRun ?? String(env.EVOLVE_EXITS_DRY_RUN ?? "") === "1";

  const roundId = opts.roundId;
  if (!ROUND_ID_RE.test(roundId ?? ""))
    return { status: "failed", code: "bad_round", envelope: { ok: false, round: "evolve", round_id: roundId ?? null, error: { code: "bad_round", message: `round_id 形状须 YYYY-MM-DD-HHMM-evolve(-rN):${roundId}` } } };
  const domain = opts.domain ?? "add-domain";
  const adapter = evolutionDomainOf(domain); // 未接线域=用法红(域配置化留位:domains.mjs)
  const repo = path.resolve(opts.repo ?? ROOT);
  const devRoot = path.resolve(opts.devRoot ?? evolutionDevRoot(env));
  const roundDir = path.join(devRoot, "rounds", roundId);
  const ledgerPath = path.join(devRoot, "spend.json");
  const statePath = evolutionStatePath({ ...env, EVOLVE_DEV_ROOT: devRoot });
  const k = opts.k ?? Number(env.EVOLVE_K ?? 3);
  if (!Number.isInteger(k) || k < 1)
    throw Object.assign(new Error(`--k 须为正整数,得到:${k}`), { usage: true });

  const fixturesDir = opts.fixturesDir ? path.resolve(opts.fixturesDir) : null; // 提案者 faux 面
  const trialFixturesDir = opts.trialFixturesDir ? path.resolve(opts.trialFixturesDir) : fixturesDir; // trial faux 面(缺省随提案者)
  let modelRef = null;
  const modelArg = opts.model ?? env.EVOLVE_MODEL ?? null;
  if (modelArg) {
    const i = modelArg.indexOf("/");
    if (i <= 0 || i >= modelArg.length - 1) throw Object.assign(new Error(`--model 须 provider/modelId,得到:${modelArg}`), { usage: true });
    modelRef = { provider: modelArg.slice(0, i), modelId: modelArg.slice(i + 1) };
  }
  if (!fixturesDir && !modelRef) throw Object.assign(new Error("real 面须 --model provider/modelId(或 --fixtures 走罐装面)"), { usage: true });
  if (!trialFixturesDir && !modelRef) throw Object.assign(new Error("trial real 面须 --model(或 --trial-fixtures 走罐装面)"), { usage: true });

  // 轮断点件(相位完成即写;崩溃重入跳已完成相位,sweep 按副本 trial.json 续跑不重记账)
  const roundJsonPath = path.join(roundDir, "round.json");
  const saveRoundJson = (patch) => {
    // 基面钉 round_id+domain(P2-4② 启动对账从孤儿断点件取域入账/入 state)
    const next = { round_id: roundId, domain, ...(readJsonIf(roundJsonPath) ?? { phase: "init" }), ...patch };
    writeJsonAtomic(roundJsonPath, next);
    return next;
  };
  const readCosts = () => {
    const j = readJsonIf(roundJsonPath) ?? {};
    return { proposer_cny: typeof j.proposer_cost_cny === "number" ? j.proposer_cost_cny : 0, trials_cny: typeof j.trials_cost_cny === "number" ? j.trials_cost_cny : 0 };
  };
  // 入账补差(P1-2):断点件记「已入账金额」非布尔——同 roundId 续跑段的新花费在下次
  // 收口时补差入月帽(首次收口即使 0 也入一笔留痕);返回最新断点件。
  const appendLedgerDelta = () => {
    const j = readJsonIf(roundJsonPath) ?? {};
    const c = readCosts();
    const total = c.proposer_cny + c.trials_cny;
    const appended = typeof j.ledger_appended_cny === "number" && Number.isFinite(j.ledger_appended_cny) ? j.ledger_appended_cny : 0;
    const first = !("ledger_appended_cny" in j);
    const delta = total - appended;
    if (first || delta > 0) {
      appendEvolutionSpend({ ledgerPath, roundId, domain, costCny: Math.max(delta, 0) });
      return saveRoundJson({ ledger_appended_cny: Math.max(total, appended) });
    }
    return j;
  };

  // ── ⓪′ 启动对账(P2-4②):先于拒启闸与一切建面/花费动作;孤儿轮补账后月帽读数
  // 才是真值;对账红向上抛=运行期异常,新轮不启 ──
  await reconcileOrphanRounds({ devRoot, skipRoundId: roundId, env, exec, dryRun, stderr });

  // ── ⓪ 拒启双面(先于一切花费/建面)──
  let state = readEvolutionState(statePath); // 坏台账/坏状态=infra 红(fail-closed)
  let dom = domainStateOf(state, domain);
  const refusal = async (code, message) => {
    log(`[evolve] 拒启 ${code}:${message}`);
    // 出口闸:spend_cap 族=连续同 code 只首次(P2 去重律);stalled 族=halted_reported
    // 闸(P2-3:熄火异常已在产出轮报过=静默拒启不重发;未报过=本拍补报,报完置位)
    const reportNow = code === "stalled" ? !dom.halted_reported : dom.last_refusal?.code !== code;
    state = applyRefusal(state, domain, { roundId, code });
    if (code === "stalled" && reportNow) state = markHaltedReported(state, domain); // 补报位:拒启面报完即置位(state.mjs 头注同语义)
    writeEvolutionState(statePath, state);
    const title = `[evolve] ${roundId} ${domain}:refused(${code})`;
    const body = renderReportMd({ roundId, domain, championRef: null, code, message, costs: { proposer_cny: 0, trials_cny: 0 }, monthTotal: null, cap: null, roundDir });
    const lark = renderLarkPlain({ roundId, domain, code, message, costs: { proposer_cny: 0, trials_cny: 0 }, monthTotal: null, cap: null, roundDir }); // #383:lark 面分稿(双面律)
    const skipReason = code === "stalled" ? "stalled 已报(halted_reported)——静默拒启不重发" : "refusal_dedupe(连续同 code 拒启,已报过)";
    const issue = reportNow ? await openRoundIssue({ title, body, dryRun, exec }) : { status: "skip", reason: skipReason };
    const anomaly = reportNow ? await pushAnomalyLark({ title: lark.title, body: lark.body, env, dryRun, exec }) : { status: "skip", reason: skipReason };
    const envelope = { ok: false, round: "evolve", round_id: roundId, domain, error: { code, message }, issue, anomaly };
    writeJsonAtomic(path.join(roundDir, "envelope.json"), envelope);
    writeJsonAtomic(path.join(roundDir, "exits.json"), { round_id: roundId, issue, anomaly });
    return { status: "refused", code, envelope };
  };
  if (dom.halted) {
    const m = `熄火态(连续 ${STALL_LIMIT} 轮带内零增益已停):处置=人裁 dev/evolution/state.json(${domain}.halted)后恢复;熄火报告见上一轮工件`;
    return refusal("stalled", dom.halted_reported ? `${m};异常已报,本拍静默留痕` : m);
  }
  const admit = admitEvolutionRound({ ledgerPath, env });
  if (!admit.ok) return refusal(admit.code, admit.message);

  // ── ① 基线与 worktree ──
  let championRef = dom.champion_ref;
  if (!championRef) { // 自举种子:锚 repo HEAD 即时落盘(零增益轮不重漂;见 state.mjs seedChampion)
    championRef = await git(exec, repo, ["rev-parse", "HEAD"]);
    state = seedChampion(state, domain, championRef);
    writeEvolutionState(statePath, state);
    dom = domainStateOf(state, domain);
  }
  log(`[evolve] round=${roundId} domain=${domain} champion=${championRef} monthSpend=¥${admit.total.toFixed(4)}/${admit.cap} model=${fixturesDir ? "faux" : `${modelRef.provider}/${modelRef.modelId}`} k=${k}`);
  const proposerWt = path.join(devRoot, "worktrees", roundId);
  if (!fs.existsSync(proposerWt)) await git(exec, repo, ["worktree", "add", "-b", `evolve/${roundId}`, proposerWt, championRef]);
  const championWt = path.join(devRoot, "champions", domain);
  if (!fs.existsSync(championWt)) await git(exec, repo, ["worktree", "add", "--detach", championWt, championRef]);
  else await git(exec, championWt, [...GIT_ID, "checkout", "--detach", championRef]);
  // 运行件:node_modules(worktree-prep.sh,#412 起单包一份;真面必须——护栏与 trial 都在 worktree 内跑 node)
  const prepScript = path.join(repo, "scripts", "worktree-prep.sh");
  await exec("bash", [prepScript, proposerWt], { timeout: 10 * 60_000, maxBuffer: 1024 * 1024 })
    .catch((e) => { throw Object.assign(new Error(`worktree-prep 红(${proposerWt}):${String(e.message ?? e).slice(0, 160)}`), { code: "infra" }); });
  await exec("bash", [prepScript, championWt], { timeout: 10 * 60_000, maxBuffer: 1024 * 1024 })
    .catch(() => { /* 冠军面重复 prep 失败不拦轮:真缺件由 trial 自红 */ });

  // ── ② 矿掘输入 ──
  const mining = minePreviousRound({ devRoot, previousRoundId: dom.last_round_id });
  fs.mkdirSync(roundDir, { recursive: true });
  fs.writeFileSync(path.join(roundDir, "mining.txt"), mining.text + "\n");

  // ── 失败收口(台账+状态+报告+出口一次走完;出口永不败轮;入账走补差面 P1-2)──
  const finishFailed = async (code, message, extra = {}) => {
    const costs = readCosts();
    appendLedgerDelta(); // P1-2:记已入账金额——续跑后此处只补新花费差额,不整笔跳过
    state = applyRoundOutcome(readEvolutionState(statePath), domain, { roundId, judged: false, gained: false, candidateRef: null }); // 未判定轮:不加不清熄火账
    writeEvolutionState(statePath, state);
    const title = `[evolve] ${roundId} ${domain}:failed(${code})`;
    const body = renderReportMd({ roundId, domain, championRef, code, message, mining, costs, monthTotal: admit.total, cap: admit.cap, roundDir, worktree: proposerWt, ...extra });
    const lark = renderLarkPlain({ roundId, domain, code, message, costs, monthTotal: admit.total, cap: admit.cap, roundDir }); // #383:lark 面分稿(双面律)
    const issue = await openRoundIssue({ title, body, dryRun, exec });
    const anomaly = await pushAnomalyLark({ title: lark.title, body: lark.body, env, dryRun, exec });
    const envelope = { ok: false, round: "evolve", round_id: roundId, domain, error: { code, message }, spend: costs, issue, anomaly };
    fs.writeFileSync(path.join(roundDir, "report.md"), body + "\n");
    writeJsonAtomic(path.join(roundDir, "envelope.json"), envelope);
    writeJsonAtomic(path.join(roundDir, "exits.json"), { round_id: roundId, issue, anomaly });
    return { status: "failed", code, envelope };
  };

  // ── ③ 提案者(无头 agent 会话)──
  let rj = readJsonIf(roundJsonPath) ?? { phase: "init" };
  if (!phaseAtLeast(rj, "proposed")) {
    const python = opts.python ?? resolveAddPython(env);
    const skillText = fs.readFileSync(path.join(repo, adapter.skillRel), "utf8");
    const { harness } = await openHarness({
      dbPath: opts.dbPath ?? path.join(roundDir, "evolve.sqlite"),
      env,
      models: fixturesDir ? await fauxAddBundle(fixturesDir) : undefined,
    });
    let proposerCost = 0;
    let answer = "";
    try {
      harness.resume();
      const conv = await harness.createConversation({
        ownership: { kind: "ownerless" },
        agent: {
          model: fixturesDir ? { provider: "faux", modelId: "faux-add-round" } : modelRef,
          instructions: skillText, // 工作指令=域 SKILL.md(驱动器检出面=循环指令稳态单源)
          extensions: [ADD_TOOLS_EXTENSION], // 编码工具闭集(宿主锚提案 worktree;仅本会话选装,红线同加源轮)
        },
      }, BACKGROUND_CONTEXT);
      ensureAddHost({ sandboxRoot: proposerWt, python }, conv.id); // 轮级宿主(工具沙箱遏制面)
      const requestId = `evolve-${roundId}-propose`; // 幂等键律:同库同轮重放不双花
      log(`[evolve] proposer submit requestId=${requestId} worktree=${proposerWt}`);
      const sub = await conv.submit({ type: "input", content: proposerBriefing({ roundId, domain, championRef, miningText: mining.text }), requestId }, BACKGROUND_CONTEXT);
      const settled = await sub.wait(BACKGROUND_CONTEXT);
      answer = lastText(await conv.context(BACKGROUND_CONTEXT));
      proposerCost = sumUsageState(await harness.usage(BACKGROUND_CONTEXT)).costCny; // 轮库单会话:总额即提案者花费(含崩溃重放的旧尝试)
      saveRoundJson({ proposer_cost_cny: proposerCost }); // 花费先落断点件再判失败(收口面从这里取数)
      if (settled.status !== "done") return await finishFailed("model_face", `提案者会话未落定(submission_${settled.status})`);
      if (!answer) return await finishFailed("model_face", "提案者终答空文本");
    } finally {
      await harness.close(BACKGROUND_CONTEXT);
    }
    fs.writeFileSync(path.join(roundDir, "proposer-report.md"), answer + "\n");
    // 未提交残面收口:提案者漏 commit → 驱动器代提交(trial 沙箱基=HEAD,不提交=候选面不可见)
    const dirty = await git(exec, proposerWt, ["status", "--porcelain"]);
    if (dirty) {
      await git(exec, proposerWt, [...GIT_ID, "add", "-A"]);
      await git(exec, proposerWt, [...GIT_ID, "commit", "-m", `evolve: ${roundId} proposer edits(驱动器收口提交)`]);
      log(`[evolve] 提案者残面由驱动器收口提交(${dirty.split("\n").length} 路径)`);
    }
    const candidateRef = await git(exec, proposerWt, ["rev-parse", "HEAD"]);
    log(`[evolve] proposer done candidate=${candidateRef} cost=¥${proposerCost.toFixed(4)}`);
    rj = saveRoundJson({ phase: "proposed", candidate_ref: candidateRef });
  }

  // ── ④ 三护栏 + 头部 diff 面闸(候选 worktree;首红即停,余者记 skipped)──
  if (!phaseAtLeast(rj, "guarded")) {
    // P2-③ 防候选 node_modules 投毒:node_modules 是 gitignored,diff 面闸两腿
    // (diff / ls-files --exclude-standard)对它不可见、提案者可改;护栏块前用主检出
    // 副本覆写(worktree-prep.sh --overwrite,幂等;缺省模式「已在跳过」不覆写,
    // 故此处必须带 --overwrite)。护栏与 trial 都在候选树内跑 node——运行件必须回到
    // 主检出态才可信;覆写红=infra(运行件不可信时不跑护栏,fail-closed)。
    await exec("bash", [prepScript, "--overwrite", proposerWt], { timeout: 10 * 60_000, maxBuffer: 1024 * 1024 })
      .catch((e) => { throw Object.assign(new Error(`worktree-prep 红(护栏前覆写,${proposerWt}):${String(e.message ?? e).slice(0, 160)}`), { code: "infra" }); });
    const guards = [];
    let red = null;
    { // 头部闸:驱动器侧 diff 面闸(P1-1)——执法在主检出跑,候选树内碰不到本函数
      const touched = await diffFaceGateTouched(exec, { worktree: proposerWt, baseRef: championRef, faces: adapter.protectedFaces });
      if (touched.length) {
        const tail = `保护名单被触(${touched.length} 路径):${touched.slice(0, 10).join(", ")}${touched.length > 10 ? "…" : ""}`;
        red = { name: "diff 面闸", rc: 1, tail };
        guards.push({ name: "diff 面闸", cmd: "(driver) diff champion..candidate + untracked vs 保护名单", status: "red", rc: 1, tail });
        log(`[evolve] 护栏红:diff 面闸——${tail}`);
      } else {
        guards.push({ name: "diff 面闸", cmd: "(driver) diff champion..candidate + untracked vs 保护名单", status: "pass" });
        log("[evolve] 护栏绿:diff 面闸(候选改动未触保护名单)");
      }
    }
    for (const g of adapter.guardrails(proposerWt)) {
      if (red) { guards.push({ name: g.name, cmd: g.cmd.join(" "), status: "skipped" }); continue; }
      try {
        await exec(g.cmd[0], g.cmd.slice(1), { cwd: g.cwd, timeout: g.timeoutMs, maxBuffer: 32 * 1024 * 1024 });
        guards.push({ name: g.name, cmd: g.cmd.join(" "), status: "pass" });
        log(`[evolve] 护栏绿:${g.name}`);
      } catch (e) {
        const tail = String(e?.stdout ?? e?.stderr ?? e?.message ?? "").split("\n").filter(Boolean).slice(-15).join("\n");
        red = { name: g.name, rc: typeof e.code === "number" ? e.code : null, tail: tail.slice(0, 2000) };
        guards.push({ name: g.name, cmd: g.cmd.join(" "), status: "red", rc: red.rc, tail: red.tail });
        log(`[evolve] 护栏红:${g.name} rc=${red.rc}`);
      }
    }
    rj = saveRoundJson({ ...(red ? {} : { phase: "guarded" }), guardrails: guards });
    if (red) return await finishFailed("guardrail_red", `护栏红:${red.name}(rc=${red.rc})——候选作废,零真 trial 花费`, { guardrails: guards });
  }

  // ── ⑤ 同会话成对 trial 批(逐题逐副本两面相邻;断点续跑)──
  if (!phaseAtLeast(rj, "swept")) {
    const universePath = opts.universePath ? path.resolve(opts.universePath) : undefined;
    const questions = adapter.evolveQuestions(universePath);
    if (!questions.length) return await finishFailed("cards_missing", "演化集考题为空(universe split=evolve 面 0 题——宇宙/劈分须人裁)");
    const mainRoot = mainCheckoutRoot(repo) ?? repo;
    const cardsDir = path.resolve(opts.cardsDir ?? adapter.cardsDir(mainRoot, env));
    const missingCards = questions.filter((q) => !fs.existsSync(path.join(cardsDir, `${q}.json`)));
    if (missingCards.length)
      return await finishFailed("cards_missing", `考题卡缺席 ${missingCards.length} 张(${missingCards.slice(0, 5).join(", ")}${missingCards.length > 5 ? "…" : ""};cardsDir=${cardsDir},env EVOLVE_CARDS_DIR 可覆写;生成=gen-exam-cards.mjs)`);
    const runTrialFace = opts.trialRunner ?? (async (a) => spawnTrialCli(exec, { ...a, runnerJs: path.join(a.faceRepo, adapter.trialRunnerRel) }));
    const faceRepo = { champion: championWt, candidate: proposerWt };
    const fracs = { champion: {}, candidate: {} }; // face → `${题}#r<i>` → frac|null(缺席/崩面)
    let trialsCost = typeof (readJsonIf(roundJsonPath)?.trials_cost_cny) === "number" ? readJsonIf(roundJsonPath).trials_cost_cny : 0;
    let fresh = readJsonIf(roundJsonPath)?.trials_fresh ?? 0;
    let resumed = readJsonIf(roundJsonPath)?.trials_resumed ?? 0;
    for (const q of questions) {
      for (let i = 1; i <= k; i++) {
        for (const face of ["champion", "candidate"]) { // 成对相邻=同会话窗(会话漂移两面同沾)
          const key = `${q}#r${i}`;
          const runDir = path.join(roundDir, "sweeps", face, q, `r${i}`);
          const prior = readJsonIf(path.join(runDir, q, "trial.json"));
          if (prior) { // 断点续跑:已跑副本复用(手动演化线 sweep.mjs 同律;花费上次已入账,不双计)
            fracs[face][key] = typeof prior?.score?.frac === "number" && Number.isFinite(prior.score.frac) ? prior.score.frac : null;
            resumed += 1;
            continue;
          }
          if (fs.existsSync(runDir) && fs.readdirSync(runDir).length)
            fs.rmSync(runDir, { recursive: true, force: true }); // 中断残沙箱(构建器拒非空目录)
          let t;
          try {
            t = await runTrialFace({ face, faceRepo: faceRepo[face], name: q, cardPath: path.join(cardsDir, `${q}.json`), runDir, modelRef, fixturesDir: trialFixturesDir, timeoutMs: TRIAL_TIMEOUT_MS });
          } catch (e) {
            if (e?.code === "trial_spend_cap") {
              saveRoundJson({ phase: "sweeping", fracs, trials_cost_cny: trialsCost, trials_fresh: fresh, trials_resumed: resumed });
              return await finishFailed("trial_spend_cap", e.message, { trials: { fresh, resumed } });
            }
            throw e; // 其余=infra 红(exit 3)
          }
          fracs[face][key] = typeof t?.score?.frac === "number" && Number.isFinite(t.score.frac) ? t.score.frac : null;
          trialsCost += Number(t?.round?.usage?.cost ?? 0); // 花费未知不伪造:信封缺席记 0(run-trial #337 同律)
          fresh += 1;
          log(`[evolve] trial ${face} ${key} → frac=${fracs[face][key] ?? "?"}(fresh=${fresh} resumed=${resumed})`);
        }
      }
      saveRoundJson({ phase: "sweeping", fracs, trials_cost_cny: trialsCost, trials_fresh: fresh, trials_resumed: resumed }); // 逐题落断点
    }
    rj = saveRoundJson({ phase: "swept", fracs, trials_cost_cny: trialsCost, trials_fresh: fresh, trials_resumed: resumed });
  }

  // ── ⑥ 判定(同会话成对 + 噪声带)──
  const pairs = [];
  for (const [key, champFrac] of Object.entries(rj.fracs?.champion ?? {})) {
    const [question, replica] = key.split("#");
    pairs.push({ question, replica, champFrac, candFrac: rj.fracs?.candidate?.[key] ?? null });
  }
  const judge = judgePaired({ pairs });
  if (judge.insufficient)
    return await finishFailed("judge_insufficient", `判定数据不足:有效成对 ${judge.n} < 3(k≥3 律;missing=${judge.missing})——不入熄火账,交异常通道`);

  // ── ⑦ 台账 + 状态 + 报告 + 出口 ──
  const costs = readCosts();
  rj = appendLedgerDelta(); // P1-2:金额面(与 finishFailed 同源)——续跑段新花费补差入月帽
  state = readEvolutionState(statePath);
  const domBefore = domainStateOf(state, domain);
  state = applyRoundOutcome(state, domain, { roundId, judged: true, gained: judge.gained, candidateRef: rj.candidate_ref });
  const domAfter = domainStateOf(state, domain);
  const haltedNow = domAfter.halted && !domBefore.halted; // 熄火翻转=异常(本轮报;后续静默拒启)
  const outcome = judge.gained ? "gained" : "zero_gain";

  const title = `[evolve] ${roundId} ${domain}:${outcome}${haltedNow ? "(熄火)" : ""}`;
  const body = renderReportMd({
    roundId, domain, championRef, candidateRef: rj.candidate_ref, outcome, judge,
    guardrails: rj.guardrails ?? [], costs,
    trials: { fresh: rj.trials_fresh ?? 0, resumed: rj.trials_resumed ?? 0 },
    monthTotal: admit.total, cap: admit.cap, stall: domAfter, haltedNow, mining, worktree: proposerWt, roundDir,
  });
  const issue = await openRoundIssue({ title, body, dryRun, exec });
  const lark = renderLarkPlain({ roundId, domain, outcome, costs, monthTotal: admit.total, cap: admit.cap, stall: domAfter, haltedNow, roundDir }); // #383:熄火 lark 面分稿(双面律)
  const anomaly = haltedNow
    ? await pushAnomalyLark({ title: lark.title, body: lark.body, env, dryRun, exec })
    : { status: "skip", reason: `outcome=${outcome}(非异常面;仅熄火/超帽/护栏红推 lark)` };
  if (haltedNow) state = markHaltedReported(state, domain); // 报完置位:置位前崩溃=下轮补报,置位后=静默拒启
  writeEvolutionState(statePath, state);

  fs.writeFileSync(path.join(roundDir, "report.md"), body + "\n");
  const envelope = {
    ok: true, round: "evolve", round_id: roundId, domain, outcome,
    champion: { before: championRef, after: domAfter.champion_ref },
    judge: { n: judge.n, missing: judge.missing, mean_diff: judge.mean_diff, sd_diff: judge.sd_diff, gained: judge.gained },
    spend: { ...costs, month_total_cny: admit.total, cap_cny: admit.cap },
    stall: { rounds: domAfter.stall_rounds, limit: STALL_LIMIT, halted: domAfter.halted },
    guardrails: rj.guardrails ?? [],
    worktree: proposerWt, round_dir: roundDir,
    issue, anomaly,
  };
  writeJsonAtomic(path.join(roundDir, "envelope.json"), envelope);
  writeJsonAtomic(path.join(roundDir, "exits.json"), { round_id: roundId, issue, anomaly });
  log(`[evolve] round=${roundId} outcome=${outcome} mean_diff=${judge.mean_diff.toFixed(4)} sd=${judge.sd_diff.toFixed(4)} stall=${domAfter.stall_rounds}/${STALL_LIMIT}`);
  return { status: "completed", envelope };
}

// 轮报告(md;人读面——轮结果单+工件路径,gh 票正文同稿)
export function renderReportMd(j) {
  const pct = (x) => (typeof x === "number" ? x.toFixed(4) : "?");
  const lines = [];
  lines.push(`# 演化轮 ${j.roundId}(域 ${j.domain})`);
  lines.push("");
  if (j.code) {
    lines.push(`## 结果:failed(${j.code})`);
    lines.push(`- ${j.message}`);
  } else {
    lines.push(`## 结果:${j.outcome}${j.haltedNow ? " + 熄火(连续 3 轮带内零增益,循环自停待人裁)" : ""}`);
  }
  lines.push("");
  lines.push("## 面");
  if (j.championRef) lines.push(`- 冠军基线:\`${j.championRef}\``);
  if (j.candidateRef) lines.push(`- 候选 commit:\`${j.candidateRef}\`(worktree ${j.worktree ?? ""};循环冠军指针${j.outcome === "gained" ? "已前移" : "未动"},master 并入人裁)`);
  if (j.mining) lines.push(`- 矿掘输入:${j.mining.source ?? "(首轮/缺席)"}`);
  lines.push("");
  if (j.judge) {
    lines.push("## 判定(同会话成对 + 噪声带)");
    lines.push(`- 有效成对 n=${j.judge.n}(missing=${j.judge.missing});冠军均分 ${pct(j.judge.champ_mean)} vs 候选均分 ${pct(j.judge.cand_mean)}`);
    lines.push(`- 成对均差 ${pct(j.judge.mean_diff)},噪声带 ±${pct(j.judge.sd_diff)}(带 [${pct(j.judge.band?.low)}, ${pct(j.judge.band?.high)}])→ **${j.judge.gained ? "带外正增益=冠军候选" : "带内=零增益"}**`);
    if (j.judge.per_question?.length) {
      lines.push("", "| 题 | 对数 | 均差 |", "| --- | --- | --- |");
      for (const q of j.judge.per_question) lines.push(`| ${q.question} | ${q.pairs} | ${q.mean_diff.toFixed(4)} |`);
    }
  }
  if (j.guardrails?.length) {
    lines.push("", "## 三护栏");
    for (const g of j.guardrails) lines.push(`- ${g.name}:${g.status}${typeof g.rc === "number" ? `(rc=${g.rc})` : ""}`);
  }
  if (j.trials) lines.push("", `## trial 批:新跑 ${j.trials.fresh} · 断点复用 ${j.trials.resumed}`);
  lines.push("", "## 花费(月帽台账)");
  lines.push(`- 提案者 ¥${(j.costs?.proposer_cny ?? 0).toFixed(4)} + trial ¥${(j.costs?.trials_cny ?? 0).toFixed(4)};当月累计 ¥${pct(j.monthTotal)}/帽 ¥${j.cap ?? "?"}`);
  if (j.stall) lines.push("", `## 熄火计数:${j.stall.stall_rounds}/${j.stall.limit}${j.stall.halted ? "(已停)" : ""}`);
  lines.push("", "## 工件路径(dev/ 不入仓)");
  lines.push(`- 轮目录:${j.roundDir ?? "(由 roundId 派生)"}`);
  lines.push("- 报告/信封/出口:report.md · envelope.json · exits.json;提案者报告:proposer-report.md;矿掘:mining.txt;断点件:round.json");
  lines.push("- trial 批:sweeps/{champion,candidate}/<题>/r<k>/(逐题 trial.json=run-trial 信封)");
  lines.push("");
  lines.push("处置:轮结果待人裁;冠军并 master 由人裁位(循环冠军指针 ≠ master)。");
  return lines.join("\n");
}

// ── #383 lark 推送面大白话稿(双面律:renderReportMd/gh 票技术面字节不动)──
// 每条异常两件套:发生了什么 + 下一步怎么办(方向级,不含具体命令);建议来自下方
// 对照表(每条带票号出处)。镜像注:scripts/daily-digest.mjs 的 EVOLVE_CODE_PLAIN 同源
// 同文案(日报零依赖独立成表,改动两处同步);未知码兜底不编造处置。
const larkClock = (roundId) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})-/.exec(String(roundId || ""));
  if (!m) return String(roundId || "?");
  const hh = +m[4];
  const tod = hh < 5 ? "凌晨" : hh < 8 ? "早上" : hh < 11 ? "上午" : hh < 13 ? "中午" : hh < 17 ? "下午" : hh < 19 ? "傍晚" : "晚上";
  return `${m[2]}-${m[3]} ${tod} ${m[4]}:${m[5]}`;
};
const LARK_DOMAIN = Object.freeze({ "add-domain": "加源域" });

// 失败类型→(标题短语 / 发生了什么 / 下一步)(票号出处随行;只给方向不给命令,#383 定案 5/6)
export const EVOLVE_LARK_ADVICE = Object.freeze({
  cards_missing: ["失败:考题卡缺失", "考题卡文件缺失,轮没法考试", "这是配置面问题不会自愈:按轮报告核对考题卡目录(env EVOLVE_CARDS_DIR;生成入口 gen-exam-cards.mjs),交人工或代理处理"], // #356
  guardrail_red: ["失败:护栏拦下提案", "提案改动碰到了受保护文件,被护栏拦下、候选作废", "护栏正常工作,下一轮会自动再试;连续多轮都这样再交代理分诊"], // #356 保护名单闸
  model_face: ["失败:提案者会话没落定", "提案者 AI 会话没正常收尾,轮失败收口", "偶发面,下一轮自动重试;同一失败码连续出现再人工查模型配置"], // #356
  judge_insufficient: ["失败:判定数据不足", "考试成对数据不足,判不出输赢,轮按失败收口(不计熄火)", "多为考试偶发崩溃,下一轮自动重试;连续出现再人工查"], // #356 判定面
  trial_spend_cap: ["停批:考试花费到帽", "考试花费到了单轮帽,停批收口", "预算护栏正常工作,已跑部分已入账;下一轮/下月自动恢复"], // #356+#337 花费帽
  orphan_reconciled: ["收口:上轮崩溃已补账", "上次运行被击杀或崩溃,这轮启动时已自动补账收口", "对账已自动完成,不用动;这台机器频繁非正常停机才值得查原因"], // #356 启动对账 P2-4②
  orphan_pre_flush: ["收口:上轮崩在早期", "上次运行崩得太早,断点文件没写下来,花费追不回(按零费留痕收口)", "已自动收口留档,不用动;频繁出现再查运行环境的超时帽/内存"], // #356 pre-flush 孤儿 P2-②
  spend_cap: ["拒启:月帽到顶", "当月演化花费已到月帽,这轮被拒启(未起跑零花费)", "不用动,这是预算护栏在正常工作;要继续跑须人裁抬帽(env EVOLVE_SPEND_CAP_CNY)或等下月自动恢复"], // #356 拒启双面
  stalled: ["拒启:已熄火", "演化循环已自停(连续 3 轮没赚头),这轮被拒启", "这是设计内的自动停机,不用动;要不要重启演化由人裁(重启须人面改 dev/evolution/state.json),不重启只是不再自动试新方案"], // #356 熄火面
  bad_round: ["拒启:轮号形状坏", "轮次编号形状不对,轮没起跑", "调度参数面问题,人工核对定时器/脚本传入的轮 id"], // #356/#366 形状律
});

// lark 推送稿(纯函数;消费与 renderReportMd 同形的 j + haltedNow 位)。未知码走兜底。
export function renderLarkPlain(j) {
  const when = larkClock(j.roundId);
  const dom = LARK_DOMAIN[j.domain] ?? j.domain ?? "?";
  if (j.haltedNow) {
    const advice = EVOLVE_LARK_ADVICE.stalled;
    return {
      title: `【ip-radar 演化轮】${when} ${dom} 熄火:连续 ${STALL_LIMIT} 轮没赚头`,
      body: [
        "【发生了什么】",
        `${when} 的演化轮(${dom})跑完,判定是带内零增益——连续 ${STALL_LIMIT} 轮没有赚头,演化循环自停(halted),不再自动试新方案;这是设计内行为,不是故障。`,
        ...(typeof j.monthTotal === "number" ? [`本月累计演化花费 ¥${j.monthTotal.toFixed(2)}/帽 ¥${j.cap ?? "?"}(本轮 ¥${((j.costs?.proposer_cny ?? 0) + (j.costs?.trials_cny ?? 0)).toFixed(2)})。`] : []),
        "",
        "【下一步怎么办】",
        advice[2],
        "",
        "【证据与工单指针】",
        "- 已自动开 GitHub 工单(ready-for-human 标签,等人裁);工单正文是技术细节版",
        `- 轮工件目录:${j.roundDir ?? "(由 roundId 派生)"}(report.md=技术细节版 · envelope.json · exits.json)`,
      ].join("\n"),
    };
  }
  const known = EVOLVE_LARK_ADVICE[j.code];
  const refused = j.code === "stalled" || j.code === "spend_cap" || j.code === "bad_round";
  const what = known ? known[1] : `失败码 ${j.code}`;
  return {
    title: `【ip-radar 演化轮】${when} ${dom} ${known ? known[0] : `失败(${j.code})`}`,
    body: [
      "【发生了什么】",
      `${when} 的演化轮(${dom})${refused ? "被拒启" : "失败"}——${what}(${j.code})。原话:${String(j.message ?? "").slice(0, 200)}`,
      ...(typeof j.monthTotal === "number" ? [`本月累计演化花费 ¥${j.monthTotal.toFixed(2)}/帽 ¥${j.cap ?? "?"}。`] : []),
      "",
      "【下一步怎么办】",
      known
        ? known[2]
        : `无现成建议——看轮工件 ${j.roundDir ?? "(由 roundId 派生)"}/report.md(envelope.json 的 error 字段),交代理分诊`,
      "",
      "【证据与工单指针】",
      "- 已自动开 GitHub 工单(ready-for-human 标签,等人裁);工单正文是技术细节版",
      `- 轮工件目录:${j.roundDir ?? "(由 roundId 派生)"}(report.md=技术细节版 · envelope.json · exits.json)`,
    ].join("\n"),
  };
}

// ── CLI ──
function usage() {
  process.stderr.write(`用法:node bench/evolution/run-round.mjs [roundId] --domain add-domain [--model provider/modelId] [--k 3] [--repo DIR] [--universe PATH] [--cards-dir DIR] [--fixtures DIR] [--trial-fixtures DIR] [--dev-root DIR] [--db PATH] [--dry-run-exits]\n  roundId 缺省=现铸 YYYY-MM-DD-HHMM-evolve;real 面须 --model;月帽 env EVOLVE_SPEND_CAP_CNY(缺省 200)、trial 帽 env ADD_BENCH_SPEND_CAP_CNY(run-trial #337 原律)\n  退出码:0=判定落定 1=refused/failed 2=用法 3=运行期异常\n`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const args = process.argv.slice(2);
  const flag = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
  try {
    const roundId = args[0] && !args[0].startsWith("--") ? args[0] : mintEvolveRoundId();
    const r = await runEvolveRound({
      roundId,
      domain: flag("domain"),
      model: flag("model"),
      k: flag("k") !== undefined ? Number(flag("k")) : undefined,
      repo: flag("repo"),
      universePath: flag("universe"),
      cardsDir: flag("cards-dir"),
      fixturesDir: flag("fixtures"),
      trialFixturesDir: flag("trial-fixtures"),
      devRoot: flag("dev-root"),
      dbPath: flag("db"),
      dryRun: args.includes("--dry-run-exits") ? true : undefined,
    });
    const out = r.status === "completed" ? r.envelope
      : { ok: false, round: "evolve", round_id: r.envelope.round_id, domain: r.envelope.domain, error: { code: r.code ?? r.envelope.error?.code, message: r.envelope.error?.message }, issue: r.envelope.issue, anomaly: r.envelope.anomaly };
    process.stdout.write(`${JSON.stringify(out)}\n`);
    process.exitCode = r.status === "completed" ? 0 : 1;
  } catch (e) {
    if (e?.usage) usage();
    else process.stderr.write(`${e.stack ?? e}\n`);
    process.exitCode = e?.usage ? 2 : 3;
  }
}
