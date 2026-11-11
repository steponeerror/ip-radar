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
// master(定案 9 停止点,接线器不碰 master)。
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
  process.stderr.write(`用法:node run-trial.mjs --name <题名> --card PATH --run-dir DIR [--repo DIR] [--ref HEAD] [--universe PATH] [--fixtures DIR] [--model provider/modelId] [--python BIN] [--round-id ID] [--db PATH] [--timeout-ms 600000]\n  faux 面=--fixtures(bench 形态 turns 不含 DOSSIER 首回合);real 面=--model 必填(P3 花钱面,先批后跑)\n  退出码:0=trial 过 1=trial 红(轮败/泄漏/钥匙红) 2=用法 3=运行期异常\n`);
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
    process.exitCode = e?.usage ? 2 : 3;
  }
}
