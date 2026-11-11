#!/usr/bin/env node
// run-trial.mjs — 加源重实现基准 trial 接线器(票 #334 交付面 1+4;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议「一次 trial」)。
//
// 一次 trial = 对一题:
//   ① build-sandbox 剥答案沙箱(P2a:剥源/剥钥匙/剥映射 + git init 无历史单根提交);
//   ② 沙箱内跑 bench 形态加源轮(P1:DOSSIER 跳过[定案 2 开关位],考题卡=交接单预填,
//     VERIFY 照常[预填卡世界由本接线器自种:queue.md PROPOSE+APPROVE 行]);
//   ③ 轮产出 diff 泄漏闸(checkRoundDiffLeak,leak-check.mjs 单源:diff 不得引用被剥路径);
//   ④ score.mjs 装回真测试钥匙跑 → pass/fail(过=1 不过=0,确定性无判官)。
// runner 复用 P2a 三件(build-sandbox/score/宇宙闸)+ P1 轮(runAddRound),零新相位零新门。
//
// 隔离世界(spec Q10「基准不得污染真实运营面」同律):<runDir>/<题名>/ 下自成世界——
//   sandbox/(P2a 打分器扫描位,scoreRuns 可直扫)、bench-world/ops/(queue/ledger/rounds
//   工件,DOCS_ROOT 现场指过去:任务 env 现读不入档律,P1 测试同款 save/restore)、
//   bench.sqlite、trial.json(trial 信封)。真钥匙/轮状态/泄漏三面都记,判交 P3 聚合。
//
// trial 判定:ok = 轮 completed ∧ leak 绿 ∧ score.pass=1;score 对失败/拒跑轮照打
// (剥净沙箱跑真钥匙 = 确定性 0,分母不静默缺题)。轮产出 = 沙箱分支,永不自并入
// master(定案 9 停止点,接线器不碰 master)。real 面 F3 花费帽(#337):STOP 文件/
// dev/add-bench/spend.json 累计超帽拒跑(开沙箱前拦),trial 后追加本轮花费;faux 不记账。
//
// 用法:node run-trial.mjs --name <题名> --card PATH --run-dir DIR [--repo DIR] [--ref HEAD]
//        [--universe PATH] [--fixtures DIR] [--model provider/modelId] [--python BIN]
//        [--round-id ID] [--db PATH] [--timeout-ms 600000]
//   faux 面 = --fixtures(罐装实现者 turns;bench 形态 turns 不含 DOSSIER 首回合,
//   P1 fixtures/add/README 同律);real 面 = --model 必填(P3 花钱面,先批后跑)。
// 退出码:0=trial 过;1=trial 红(轮败/泄漏/钥匙红);2=用法;3=运行期异常(ENVELOPE.md 律)。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildSandbox } from "./build-sandbox.mjs";
import { scoreQuestion } from "./score.mjs";
import { checkRoundDiffLeak } from "../leak-check.mjs";
// 加载序锚(同 gen-exam-cards.mjs):tasks/add-round ↔ run-add ↔ registry ↔ tasks/index
// 有环;先拉 run-add 侧再拉 add-round(与 P1 测试/启动器同序),倒序撞 addRoundTask TDZ。
import { runAddRound, resolveAddPython } from "../../run-add.mjs";
import { dossierShape, slugify } from "../../tasks/add-round.mjs";

const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // add-domain → 仓根(4 层)

// ── 纯函数面(导出=测试单源面)──────────────────────────────────────────

// 轮 id 铸形(YYYY-MM-DD-HHMM-add,本地时;run-add 形状律先于准入)
export function mintRoundId(now = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}-add`;
}

// queue.md 表头(冻结件独立真源:backend/ipdb/_ops_store.py QUEUE_HEADER,不从被测
// 模块导入——P1 tests/add-round.test.mjs 同款双抄对拍纪律)
const QUEUE_HEADER = (
  "# 源生命周期动作队列(三写口:ops 轮 queue_action · 发现轮 ENQUEUE 候选行 · 发现轮候选卡 appendCandidateCard;后两路 action=PROPOSE 一词一拼;行由 host 模板渲染,rationale 只落工件)\n\n" +
  "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n" +
  "|---|---|---|---|---|---|---|\n"
);

// 预填卡世界自种:PROPOSE(candidate:name/url=考题卡面)+ APPROVE(bench 世界人面代行,
// 真实运营面的 APPROVE 写口仅人面——这里写进的是隔离世界自有 queue.md,不碰生产队列)
export function seedQueueWorld(opsDir, { source, card }) {
  fs.mkdirSync(opsDir, { recursive: true });
  const rows = [
    `| 2026-11-11 | add-bench | PROPOSE | ${source} | — | candidate:name=${JSON.stringify(card.name)};candidate:url=${JSON.stringify(card.url)} | 是(否决=删除本行) |`,
    `| 2026-11-11 | human | APPROVE | ${source} | — | human:approved_by="add-bench-trial" | 是(否决=删除本行) |`,
  ];
  fs.writeFileSync(path.join(opsDir, "queue.md"), QUEUE_HEADER + rows.join("\n") + "\n");
}

// 沙箱变更文件收集(轮产出 diff 面):已跟踪改动(diff vs 根提交)+ 未跟踪新增
// (ls-files --others;失败轮可能没走到 REPORT 提交,工作树面也要扫);删除项无内容跳过。
export function sandboxChangedFiles(sandbox, rootSha) {
  const git = (args) => execFileSync("git", ["-C", sandbox, ...args], { encoding: "utf8" });
  const rels = new Set([
    ...git(["diff", "--name-only", rootSha]).split("\n").filter(Boolean),
    ...git(["ls-files", "--others", "--exclude-standard"]).split("\n").filter(Boolean),
  ]);
  const out = [];
  for (const rel of rels) {
    const abs = path.join(sandbox, rel);
    let st;
    try { st = fs.statSync(abs); } catch { continue; } // 删除面/非常规文件跳过
    if (st.isFile()) out.push({ path: rel, text: fs.readFileSync(abs, "utf8") });
  }
  return out;
}

// ── F3 花费帽机械执法(票 #337;#334 评审 F3 转前置)──
// 逐题隔离 ledger 使 admitRound 月帽恒余量——bench 级共享花费台账补机械面:
// 真实(非 faux)trial 前 STOP 文件在场即拒 + 共享台账累计超帽即拒;单次 trial 后
// 追加本轮花费(信封 usage.cost,失败轮信封缺席记 0 留痕,round_status 如实记);
// faux 路零花费,不查帽不记账。帽缺省 40(基准帽 #331 spec),env ADD_BENCH_SPEND_CAP_CNY
// 可覆写;「累计超帽」= 追加后总额严格大于帽才拦后续(trial 内部花费由 OPS_ADD_* 腿帽约束)。
export const SPEND_DIR = path.join(ROOT, "dev", "add-bench");
export const SPEND_LEDGER_FILE = path.join(SPEND_DIR, "spend.json");
export const SPEND_STOP_FILE = path.join(SPEND_DIR, "STOP");

export function spendCapCny(env = process.env) {
  const raw = env.ADD_BENCH_SPEND_CAP_CNY;
  if (raw === undefined || raw === "") return 40;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0)
    throw Object.assign(new Error(`ADD_BENCH_SPEND_CAP_CNY 须为非负数,得到:${raw}`), { usage: true });
  return n;
}

// 台账总额 = entries 机械回算(不信存量 total_cny 字段——证据回算律);缺席=0;坏台账=红
// fail-closed:台账取数坏了就停跑,不猜。
export function spendTotalCny(ledgerPath = SPEND_LEDGER_FILE) {
  if (!fs.existsSync(ledgerPath)) return 0;
  let j;
  try { j = JSON.parse(fs.readFileSync(ledgerPath, "utf8")); } catch (e) {
    throw Object.assign(new Error(`dev/add-bench/spend.json 坏了(不是合法 JSON):${e.message}`), { code: "infra" });
  }
  if (!j || !Array.isArray(j.entries) || j.entries.some((e) => typeof e?.cost_cny !== "number" || !Number.isFinite(e.cost_cny)))
    throw Object.assign(new Error("dev/add-bench/spend.json 坏了(entries 缺席或 cost_cny 非有限数)"), { code: "infra" });
  return j.entries.reduce((a, e) => a + e.cost_cny, 0);
}

// 真实 trial 准入(拒跑双面):STOP 文件在场即拒(bench_stop,人工停跑面);台账累计超帽即拒
// (spend_cap)。返回 {ok:true,cap,total} 或 {ok:false,code,message}。
export function admitTrialSpend({ spendDir = SPEND_DIR, env = process.env } = {}) {
  if (fs.existsSync(path.join(spendDir, "STOP")))
    return { ok: false, code: "bench_stop", message: "STOP 文件在场(dev/add-bench/STOP):基准停跑,真实 trial 拒跑(移除该文件恢复)" };
  const cap = spendCapCny(env);
  const total = spendTotalCny(path.join(spendDir, "spend.json"));
  if (total > cap)
    return { ok: false, code: "spend_cap", message: `共享台账累计 ¥${total.toFixed(4)} 超帽 ¥${cap}(env ADD_BENCH_SPEND_CAP_CNY 可覆写):后续真实 trial 拒跑` };
  return { ok: true, cap, total };
}

// 单次 trial 后追加本轮花费(共享台账累计面;faux 不调本函数)
export function appendSpend({ ledgerPath = SPEND_LEDGER_FILE, name, roundId, roundStatus, costCny, now = new Date() }) {
  const p = path.resolve(ledgerPath);
  let entries = [];
  if (fs.existsSync(p)) {
    try {
      const j = JSON.parse(fs.readFileSync(p, "utf8"));
      if (j && Array.isArray(j.entries)) entries = j.entries;
    } catch { /* 坏台账在 spendTotalCny 准入面已拦;到这则是追加竞态损坏——重建丢证据,红 */
      throw Object.assign(new Error(`dev/add-bench/spend.json 坏了(追加前解析失败)`), { code: "infra" });
    }
  }
  const cost = Number(costCny);
  if (!Number.isFinite(cost)) throw Object.assign(new Error(`costCny 须为有限数,得到:${costCny}`), { usage: true });
  entries = [...entries, { at: now.toISOString(), name, round_id: roundId, round_status: roundStatus, cost_cny: cost }];
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify({ entries, total_cny: entries.reduce((a, e) => a + e.cost_cny, 0) }, null, 2) + "\n");
}

// ── 一 trial(程序面;CLI 与测试共用)───────────────────────────────────
// 返回 {ok,name,roundId,round:{status,error?,sandbox?,usage?},leak,score,pass,sandbox,trialFile};
// ok = 轮 completed ∧ leak 绿 ∧ score.pass=1(三面全记,判交调用方/P3 聚合)。
// 串行契约:runTrial 直接改写 process.env(DOCS_ROOT/LEDGER_FILE 等)并在 finally 恢复,
// 并行调用会互相踩踏——本文件所有入口按串行设计(#334 评审 F6 记档)。
export async function runTrial(opts) {
  const { name, runDir, cardPath } = opts;
  if (!name || !runDir || !cardPath)
    throw Object.assign(new Error("须给 --name/--run-dir/--card(一次 trial = 一题一卡一 run 目录)"), { usage: true });
  // 考题卡:形状门(dossierShape 单源,与轮 DOSSIER 同门)+ stem 契约(卡名 slugify=题名,
  // 打分器钥匙面 test_<name>.py 才对得上)——不带病开沙箱
  const card = JSON.parse(fs.readFileSync(path.resolve(cardPath), "utf8"));
  const shape = dossierShape(card);
  if (!shape.ok) throw Object.assign(new Error(`考题卡形状坏(交接单七键):${shape.reason}`), { usage: true });
  if (slugify(card.name) !== name)
    throw Object.assign(new Error(`stem 契约红:slugify(card.name)=${slugify(card.name)} ≠ 题名 ${name}(打分器钥匙面 test_${name}.py 对不上)`), { usage: true });
  const python = opts.python ?? resolveAddPython();
  const repo = opts.repo ? path.resolve(opts.repo) : ROOT;

  // ⓪ F3 花费帽准入(真实面;拒跑双面:STOP 文件/台账累计超帽)——在开沙箱前拦,
  // 拒跑零建面零花费;faux 面零花费,不查帽不记账(#337)。
  if (!opts.fixturesDir) {
    const admit = admitTrialSpend({ spendDir: opts.spendDir ? path.resolve(opts.spendDir) : SPEND_DIR });
    if (!admit.ok) throw Object.assign(new Error(admit.message), { code: admit.code });
  }

  // ① 剥答案沙箱(考题闸/冻结宇宙闸在 build-sandbox 内,fail-closed)
  const { sandbox } = buildSandbox({
    repo, ref: opts.ref ?? "HEAD", name,
    runDir: path.resolve(runDir), universePath: opts.universePath, python,
  });
  const rootSha = execFileSync("git", ["-C", sandbox, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();

  // ② 预填卡世界 + bench 形态轮(隔离 opsRoot:任务 env 现读,DOCS_ROOT/LEDGER_FILE
  // 现场 save/restore 指试世界——P1 测试同款;台账/工件/轮目录全落 <runDir>/<题>/)
  const worldDir = path.join(path.resolve(runDir), name, "bench-world");
  const opsDir = path.join(worldDir, "ops");
  seedQueueWorld(opsDir, { source: name, card });
  const roundId = opts.roundId ?? mintRoundId();
  const saved = ["DOCS_ROOT", "LEDGER_FILE"].map((k) => [k, process.env[k]]);
  let round;
  try {
    process.env.DOCS_ROOT = worldDir;
    process.env.LEDGER_FILE = path.join(opsDir, "ledger.md");
    round = await runAddRound({
      roundId, source: name, sandboxRoot: sandbox,
      fixturesDir: opts.fixturesDir ? path.resolve(opts.fixturesDir) : null,
      dbPath: opts.dbPath ?? path.join(path.resolve(runDir), name, "bench.sqlite"),
      bench: true, dossier: card,
      modelRef: opts.modelRef ?? null,
      python, env: { ...process.env },
      ledgerFile: path.join(opsDir, "ledger.md"),
      stderr: opts.stderr ?? process.stderr,
    });
  } finally {
    for (const [k, v] of saved) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
  }

  // F3 记账面:轮一返回就追加(后缝闸/打分崩了钱也已落账;轮本身抛异常时信封缺席,
  // 花费未知不伪造——月帽 admitRound 台账保有权威逐轮记录,本面不猜)。faux 不记账。
  if (!opts.fixturesDir) {
    appendSpend({
      ledgerPath: path.join(opts.spendDir ? path.resolve(opts.spendDir) : SPEND_DIR, "spend.json"),
      name, roundId, roundStatus: round?.status ?? "failed",
      costCny: Number(round?.envelope?.usage?.cost ?? 0),
    });
  }

  // ③ 轮产出 diff 泄漏闸(diff 不得引用被剥路径——主检答案树绝对路径面)
  const leak = checkRoundDiffLeak({
    repoRoot: repo, name,
    files: sandboxChangedFiles(sandbox, rootSha),
  });

  // ④ 真钥匙装回打分(失败/拒跑轮照打:剥净沙箱跑真钥匙=确定性 0,分母不静默缺题)
  const score = scoreQuestion({ name, sandbox, repo, python, timeoutMs: opts.timeoutMs ?? 600000 });

  const ok = round.status === "completed" && leak.ok && score.pass === 1;
  const result = {
    ok, name, roundId,
    round: {
      status: round.status,
      ...(round.error ? { error: round.error } : {}),
      ...(round.envelope ? { sandbox: round.envelope.sandbox ?? null, usage: round.envelope.usage ?? null } : {}),
    },
    leak: { ok: leak.ok, hits: leak.hits.map((h) => ({ file: h.file, line: h.line, needle: h.needle })) },
    score: { pass: score.pass },
    pass: score.pass === 1,
    sandbox,
    trialFile: path.join(path.resolve(runDir), name, "trial.json"),
    generated_at: new Date().toISOString(),
  };
  fs.mkdirSync(path.dirname(result.trialFile), { recursive: true });
  fs.writeFileSync(result.trialFile, JSON.stringify({ ...result, score: { pass: score.pass, summary: score.summary } }, null, 2) + "\n");
  return result;
}

// ── CLI ──
function usage() {
  process.stderr.write(`用法:node run-trial.mjs --name <题名> --card PATH --run-dir DIR [--repo DIR] [--ref HEAD] [--universe PATH] [--fixtures DIR] [--model provider/modelId] [--python BIN] [--round-id ID] [--db PATH] [--timeout-ms 600000]\n  faux 面=--fixtures(bench 形态 turns 不含 DOSSIER 首回合);real 面=--model 必填(P3 花钱面,先批后跑)\n  real 面花费帽(#337):dev/add-bench/STOP 在场或共享台账 dev/add-bench/spend.json 累计超帽(缺省 40,env ADD_BENCH_SPEND_CAP_CNY 覆写)拒跑;faux 不查不记\n  退出码:0=trial 过 1=trial 红(轮败/泄漏/钥匙红) 2=用法 3=运行期异常 4=花费帽拒跑(bench_stop/spend_cap)\n`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const args = process.argv.slice(2);
  const flag = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
  const need = (n) => {
    if (flag(n) === undefined) throw Object.assign(new Error(`缺 --${n}`), { usage: true });
    return flag(n);
  };
  try {
    let modelRef;
    const modelRefArg = flag("model");
    if (modelRefArg) {
      const i = modelRefArg.indexOf("/");
      if (i <= 0 || i >= modelRefArg.length - 1) throw Object.assign(new Error(`--model 须 provider/modelId,得到:${modelRefArg}`), { usage: true });
      modelRef = { provider: modelRefArg.slice(0, i), modelId: modelRefArg.slice(i + 1) };
    }
    const timeoutMs = flag("timeout-ms") ? Number(flag("timeout-ms")) : undefined;
    if (timeoutMs !== undefined && (!Number.isFinite(timeoutMs) || timeoutMs <= 0))
      throw Object.assign(new Error(`--timeout-ms 须为正数,得到:${flag("timeout-ms")}`), { usage: true });
    const r = await runTrial({
      name: need("name"),
      cardPath: need("card"),
      runDir: need("run-dir"),
      repo: flag("repo"),
      ref: flag("ref"),
      universePath: flag("universe"),
      fixturesDir: flag("fixtures"),
      modelRef,
      python: flag("python"),
      roundId: flag("round-id"),
      dbPath: flag("db"),
      timeoutMs,
    });
    // stdout 末行=trial 信封单行(运行面工件;题名/分数与 score 报表同律)
    const out = { ok: r.ok, round: "add-trial", name: r.name, round_id: r.roundId, round_status: r.round.status, leak_ok: r.leak.ok, score_pass: r.score.pass };
    process.stdout.write(`${JSON.stringify(out)}\n`);
    process.exitCode = r.ok ? 0 : 1;
  } catch (e) {
    if (e?.usage) usage();
    else process.stderr.write(`${e.stack ?? e}\n`);
    process.exitCode = e?.usage ? 2 : e?.code === "bench_stop" || e?.code === "spend_cap" ? 4 : 3;
  }
}
