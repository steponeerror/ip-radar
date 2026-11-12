#!/usr/bin/env node
// score.mjs — 加源重实现基准打分器(票 #333 P2a;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议「打分钥匙」)。
//
// 语义:把 repo 侧真逐源测试文件(backend/tests/sources/test_<name>.py,自带
// tmp_path 样本、单独可跑)装回沙箱原位 → 以主检出 venv 解释器绝对路径 + cwd=
// 沙箱 backend/ 跑(AGENTS worktree 律,沙箱无 venv;bench/score.mjs
// resolvePython 同款)→ 过=1 不过=0;S = 通过源数/考题数。全确定性,无 LLM 判官
// (spec 定案 3)。k 个 run 目录 = k 次重复 → 均值 + 方差带 + 逐题跨次计数
// (spec 定案 4:k≥3 量噪声带,#322 k=1 教训)。
// #343 分级钥匙:逐题另计 score_frac = passed/total 测试函数数(pytest 摘要行
// 「N failed, M passed」→ M/(M+N);collection error 面 → 分子 0 + repo 侧
// --collect-only -q 数出的函数数做分母;spec §钥匙=分级 勘误为判据真源)。
// score_pass(0/1)留档并存——历史 0/1 S 数字与均分不可直比;报表两制并列。
//
// 布局契约(与 build-sandbox.mjs --run-dir 对齐):run 目录 = 每题一子目录
// <run>/<题名>/sandbox;题集 = 冻结 universe 名单单源,表外题/缺 sandbox/
// 缺钥匙一律 fail-closed 红——静默跳过或静默零分都会污染分母(打分是答案面,
// 宁红勿漏)。逐题报告含失败摘要(尾部行);打分前不泄答案内容(盲测纪律,
// 报表仅在打分后产出)。
//
// 用法:node score.mjs --runs DIR [DIR ...] [--repo DIR] [--python BIN]
//                      [--universe PATH] [--out-dir DIR] [--timeout-ms 600000]
// 产物:report.json + report.md(落 --out-dir,缺省首个 run 目录的父目录)。
// 报表含考题名 = 答案面工件:落工件目录(不入仓,文件放置规范)。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // add-domain → 仓根(4 层)
const SUMMARY_TAIL = 15; // 失败摘要尾行数(门命令尾部输出同律)

// 单源导出(#334:考题卡生成器同面消费——frozen 闸+行序读面禁第二份)
export function loadUniverse(universePath) {
  const lines = fs.readFileSync(universePath ?? path.join(import.meta.dirname, "data", "universe.jsonl"), "utf8").split("\n").filter(Boolean);
  const meta = JSON.parse(lines[0]);
  if (meta.frozen !== true)
    throw new Error(`宇宙名单未冻结(frozen≠true):${universePath}——打分分母须钉死`);
  // universe 行序 = 报表题序(确定性);行序 = heldout 先、名字行原生成序
  return lines.slice(1).map((l) => JSON.parse(l));
}

// 摘要行计数解析(#343 分级钥匙;导出=测试单源面):取输出末行,剥 ===/!!! 装饰,
// 读「N failed, M passed(, E errors)」计数。skipped/xfail 族不入票面公式(分数 =
// M/(M+N) 字面);「no tests (ran|collected)」= 全零计数。无可读计数 → null
// (fallback 分母触发条件)。实测形状(/tmp/g343-faces 对拍,2026-11-12,pytest
// -q --no-header):「2 passed in 0.01s」/「1 failed, 2 passed in 0.02s」/
// 「1 error in 0.07s」(collection error 中断,exit 2)/「no tests ran in 0.00s」(exit 5)。
export function parsePytestTally(stdout) {
  const lines = String(stdout ?? "").split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return null;
  const last = lines[lines.length - 1].replace(/^[=!\s]+/, "").replace(/[=!\s]+$/, "");
  if (!/\d+\s+(failed|passed|errors?)\b/.test(last) && !/^no tests (ran|collected)/.test(last)) return null;
  const num = (re) => { const m = last.match(re); return m ? Number(m[1]) : 0; };
  return { failed: num(/(\d+)\s+failed/), passed: num(/(\d+)\s+passed/), errors: num(/(\d+)\s+errors?\b/) };
}

// 分母兜底计数(#343 票面补行):collection error 面(沙箱 import 断,exit 2 中断)
// 无「N failed, M passed」可读 → 分母用 repo 侧(真钥匙+真实现在场,collection 必成)
// `pytest --collect-only -q` 数出的测试函数数;沙箱侧数不可用——collection error
// 本身就意味着同处再数也是 0。项数口径:parametrize 展开按项计,与摘要行分子同口径。
// 失败(repo 侧也不可数,理论不应发生)= 0,宁少算勿多算。
function countKeyFunctions({ name, repo, python, timeoutMs = 600000 }) {
  try {
    const out = execFileSync(python,
      ["-m", "pytest", path.posix.join("tests", "sources", `test_${name}.py`), "--collect-only", "-q", "--no-header"],
      { cwd: path.join(repo, "backend"), encoding: "utf8", timeout: timeoutMs });
    return out.split("\n").filter((l) => l.trim().includes("::")).length;
  } catch { return 0; }
}

// 单题打分:钥匙装回 → 沙箱内跑真测试。返回 {name, pass(0|1), frac, passed_fns, total_fns, summary}。
// #343 分级规则(退出码面):
//   exit 0 = 全过 → pass=1, frac=1(摘要行计数入档;无摘要(stub 面)→ 计数 null 不虚构);
//   exit 1 = 测试面挂(无中断)→ 摘要行计数,frac = passed/(failed+passed+errors)
//     (setup/teardown error 是测试函数级挂面,如实入分母);
//   其余(exit 2 collection error/中断、exit 4/5 用法面、超时、输出不可解析)→
//     分子 0,分母 = repo 侧 collect-only 函数数(countKeyFunctions)。
export function scoreQuestion({ name, sandbox, repo, python, timeoutMs = 600000 }) {
  const keyRel = path.join("backend", "tests", "sources", `test_${name}.py`);
  const keySrc = path.join(repo, keyRel);
  if (!fs.existsSync(keySrc))
    throw new Error(`打分钥匙缺失:repo=${repo} 无 ${keyRel}(考题分母坏了,须人裁——不给静默零分)`);
  const backendDir = path.join(sandbox, "backend");
  if (!fs.existsSync(backendDir))
    throw new Error(`沙箱布局漂移:${sandbox} 无 backend/(非 build-sandbox 产物或已损坏)`);
  // 钥匙装回原位(打分器对沙箱的唯一写入;keyRel 自带 backend/ 前缀,落在沙箱根)
  fs.mkdirSync(path.dirname(path.join(sandbox, keyRel)), { recursive: true });
  fs.copyFileSync(keySrc, path.join(sandbox, keyRel));
  let pass = 0;
  let summary = "";
  let frac = 0;
  let passedFns = null;
  let totalFns = null;
  let status = null; // 0=exit 0(全过);1=exit 1(测试面挂);null=其余面(走 fallback 分母)
  let stdout = "";
  try {
    stdout = execFileSync(python, ["-m", "pytest", path.posix.join("tests", "sources", `test_${name}.py`), "-q", "--no-header"],
      { cwd: backendDir, encoding: "utf8", timeout: timeoutMs });
    status = 0;
  } catch (e) {
    if (e.killed || e.signal === "SIGTERM") {
      summary = `pytest 超时(>${Math.round(timeoutMs / 1000)}s)——不过 0`;
    } else {
      status = e.status === 1 ? 1 : null; // exit 2/3/4/5 = 中断/用法面,计数不可信 → fallback
      stdout = String(e.stdout ?? e.stderr ?? "");
      const out = stdout.trim();
      summary = out ? out.split("\n").filter(Boolean).slice(-SUMMARY_TAIL).join("\n") : `退出码 ${e.status ?? "?"}(无输出)`;
    }
  }
  const tally = parsePytestTally(stdout);
  if (status === 0) {
    pass = 1;
    frac = 1;
    if (tally) { passedFns = tally.passed; totalFns = tally.failed + tally.passed + tally.errors; }
  } else if (status === 1 && tally && tally.failed + tally.passed + tally.errors > 0) {
    passedFns = tally.passed;
    totalFns = tally.failed + tally.passed + tally.errors;
    frac = passedFns / totalFns;
  } else {
    passedFns = 0;
    totalFns = countKeyFunctions({ name, repo, python, timeoutMs });
    frac = 0;
  }
  return { name, pass, frac, passed_fns: passedFns, total_fns: totalFns, summary };
}

// 多 run 聚合:每 run 一个 S;k run → mean/stdev/band + 逐题跨次计数。
// only = 题集子集(端到端单题验证面/崩题补分面):分母改 only 单源,子集仍须
// universe 内(表外题红);k 个 run 须同含子集全部题(缺题红,同全集律)。
export function scoreRuns({ runs, repo, python, universePath, timeoutMs, only }) {
  if (!runs?.length) throw new Error("须给 --runs DIR(一次基准重复 = 一个 run 目录)");
  const universe = loadUniverse(universePath);
  const uniNames = new Set(universe.map((r) => r.name));
  let exam = universe;
  if (only?.length) {
    for (const n of only) if (!uniNames.has(n)) throw new Error(`only 题不在 universe 名单:${n}(子集仍须 universe 单源)`);
    exam = universe.filter((r) => only.includes(r.name));
  }
  const examNames = new Set(exam.map((r) => r.name));
  const runResults = runs.map((runDir) => {
    const questions = [];
    for (const row of exam) {
      const sandbox = path.join(runDir, row.name, "sandbox");
      if (!fs.existsSync(sandbox))
        throw new Error(`run 目录布局漂移:${runDir} 缺题 ${row.name} 的 sandbox/(k 次重复须同题集;缺题禁静默跳过)`);
      questions.push(scoreQuestion({ name: row.name, sandbox, repo, python, timeoutMs }));
    }
    // 表外题混入 = 分母污染(例如旧宇宙残留),红;only 子集面时子集外题同律
    for (const ent of fs.readdirSync(runDir, { withFileTypes: true })) {
      if (ent.isDirectory() && !examNames.has(ent.name))
        throw new Error(`run 目录含表外题:${path.join(runDir, ent.name)} 不在考题面(分母须 universe 单源)`);
    }
    const passed = questions.filter((q) => q.pass === 1).length;
    // #343:meanFrac = 逐题 score_frac 均分(新主判据);S/pass 计数留档副指标
    const meanFrac = questions.length ? questions.reduce((s, q) => s + q.frac, 0) / questions.length : 0;
    return { runDir: path.basename(path.resolve(runDir)), S: questions.length ? passed / questions.length : 0, meanFrac, questions };
  });
  const k = runResults.length;
  const meanS = runResults.reduce((s, r) => s + r.S, 0) / k;
  const meanFrac = runResults.reduce((s, r) => s + r.meanFrac, 0) / k;
  const stdevS = k > 1
    ? Math.sqrt(runResults.reduce((s, r) => s + (r.S - meanS) ** 2, 0) / (k - 1))
    : 0;
  const first = runResults[0].questions.map((q) => q.name);
  const perQuestion = first.map((name) => ({
    name,
    passes: runResults.reduce((s, r) => s + (r.questions.find((q) => q.name === name)?.pass ?? 0), 0),
    meanFrac: runResults.reduce((s, r) => s + (r.questions.find((q) => q.name === name)?.frac ?? 0), 0) / k,
  }));
  return {
    k,
    runs: runResults,
    meanS,
    meanFrac,
    stdevS,
    band: { minS: Math.min(...runResults.map((r) => r.S)), maxS: Math.max(...runResults.map((r) => r.S)) },
    perQuestion,
  };
}

export function renderMarkdown(res) {
  const esc = (s) => String(s ?? "").replaceAll("|", "\\|");
  const pct = (x) => `${(x * 100).toFixed(2)}%`;
  const lines = [];
  lines.push("# 加源重实现基准打分报告(#333;#343 分级钥匙)");
  lines.push("");
  lines.push("## 总分");
  for (const r of res.runs) lines.push(`- run ${r.runDir}:S = ${r.S.toFixed(4)}(${pct(r.S)},${r.questions.filter((q) => q.pass === 1).length}/${r.questions.length}),frac = ${r.meanFrac.toFixed(4)}(${pct(r.meanFrac)})`);
  lines.push(`- k = ${res.k} 次重复:mean S = ${res.meanS.toFixed(4)},mean frac = ${res.meanFrac.toFixed(4)},stdev = ${res.stdevS.toFixed(4)},band = [${res.band.minS.toFixed(4)}, ${res.band.maxS.toFixed(4)}]`);
  lines.push("");
  lines.push("## 逐题(k 次中通过次数 + score_frac 均分)");
  lines.push("| 题目 | 通过/重复 | frac 均分 |");
  lines.push("| --- | --- | --- |");
  for (const q of res.perQuestion) lines.push(`| ${esc(q.name)} | ${q.passes}/${res.k} | ${q.meanFrac.toFixed(4)} |`);
  lines.push("");
  lines.push("## 失败摘要(逐题;打分后产出)");
  for (const run of res.runs) {
    for (const q of run.questions) {
      if (q.pass === 1) continue;
      lines.push("");
      lines.push(`### ${run.runDir} / ${esc(q.name)} —— FAIL`);
      lines.push("```");
      lines.push(q.summary || "(无输出)");
      lines.push("```");
    }
  }
  lines.push("");
  return lines.join("\n");
}

// ── CLI ──
function parseArgs(argv) {
  const out = { runs: [], repo: null, python: null, universe: null, outDir: null, timeoutMs: null, only: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--runs") { out.runs.push(next()); while (argv[i + 1] && !argv[i + 1].startsWith("--")) out.runs.push(argv[++i]); }
    else if (a === "--repo") out.repo = next();
    else if (a === "--python") out.python = next();
    else if (a === "--universe") out.universe = next();
    else if (a === "--out-dir") out.outDir = next();
    else if (a === "--timeout-ms") out.timeoutMs = Number(next());
    else if (a === "--only") out.only = next().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--help" || a === "-h") out.help = true;
    else { console.error(`未知参数:${a}`); process.exit(2); }
  }
  if (out.help || !out.runs.length) {
    console.error("用法:node score.mjs --runs DIR [DIR ...] [--repo DIR] [--python BIN] [--universe PATH] [--out-dir DIR] [--timeout-ms 600000] [--only 名,名,...]");
    process.exit(out.help ? 0 : 2);
  }
  return out;
}

export function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const python = args.python ?? process.env.BENCH_PYTHON ?? "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
  const res = scoreRuns({
    runs: args.runs,
    repo: args.repo ?? ROOT,
    python,
    universePath: args.universe,
    timeoutMs: args.timeoutMs ?? 600000,
    only: args.only,
  });
  const outDir = args.outDir ?? path.dirname(path.resolve(args.runs[0]));
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "report.json"), JSON.stringify(res, null, 2) + "\n");
  fs.writeFileSync(path.join(outDir, "report.md"), renderMarkdown(res));
  console.log(`k=${res.k} mean S = ${res.meanS.toFixed(4)}(band [${res.band.minS.toFixed(4)}, ${res.band.maxS.toFixed(4)}])→ ${path.join(outDir, "report.md")}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  main();
}
