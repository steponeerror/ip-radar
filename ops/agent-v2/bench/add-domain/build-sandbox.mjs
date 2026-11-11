#!/usr/bin/env node
// build-sandbox.mjs — 加源重实现基准剥答案沙箱构建器(票 #333 P2a;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议「剥答案沙箱(防泄漏三件套)」前两条):
//   1. 剥离清单:backend/ipdb/_sources/<name>.py、backend/tests/sources/test_<name>.py、
//      _classification.py 内该源的顶层赋值块(机械派生 = 源文件 import 的 _classification
//      名单——含 <SRC>_MAP 与同源辅助表;有则剥,紧邻判据注释随块剥:注释即答案面);
//   2. 无历史检出:剥答案树 git init + 压缩单根提交——防 git log/git show 考古真实现
//      (工作树剥离挡不住历史面)。提交信息不含考题名。
// 第三件(轮提示词禁令)属加源轮(P2b)提示词面,不在本件。
//
// 检出面 = git archive <ref>(只含 ref 树内 tracked 文件,天然剔除 .git/node_modules/
// backend/data 等未跟踪面);目标目录须不存在或为空(fail-closed,禁复用旧沙箱)。
// 考题闸:题名须在冻结 universe.jsonl 名单内(frozen=true),防名单漂移期误开沙箱。
//
// 用法:
//   node build-sandbox.mjs --name <题名> [--repo DIR] [--ref HEAD] [--universe PATH]
//                          (--run-dir DIR | --out DIR) [--python BIN]
// 布局:--run-dir → <run-dir>/<题名>/sandbox(打分器 score.mjs 按此发现);--out → 沙箱根。
import fs from "node:fs";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import os from "node:os";

const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // add-domain → 仓根(4 层)

// ── 源文件 → _classification 剥离名单(机械派生,禁第二份清单)──
// 解析 `from [..|ipdb]._classification import X, Y` / 括号多行形;返回标识符数组
// (normalize 等共享函数名也会被解析出——剥块时按「顶层赋值」匹配,函数名不命中即自然保留)。
export function extractClassificationImports(sourceText) {
  const out = new Set();
  const re = /from\s+(?:\.{1,2}|ipdb\.)(_classification)\s+import\s+(\([^)]*\)|[^\n(]+)/g;
  for (const m of sourceText.matchAll(re)) {
    const clause = m[2].replace(/[()]/g, " ").split("#")[0];
    for (const part of clause.split(",")) {
      const name = part.trim().split(/\s+as\s+/)[0].trim();
      if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) out.add(name);
    }
  }
  return [...out];
}

// ── _classification.py 顶层赋值块剥离 ──
// 块 = 顶层的 `NAME = …` / `NAME: T = …` 赋值(括号深度回零收口);紧邻上方的连续 #
// 注释行随块剥(判据注释 = 答案面的一部分)。剥后:目标名不得再出现、3+ 连续空行折 2。
// import 面里的共享函数/类(def/class 定义,如 normalize)不形如赋值,自然保留——
// 留存判据 = 剥后文本仍含该名(可导入);完全消失 = absent 记账,调用方 throw:
// 那 .是「源文件 import 但 _classification 无此定义」的真漂移,静默半剥会留下假沙箱。
export function stripClassificationMaps(text, names) {
  const lines = text.split("\n");
  const targets = new Set(names);
  const stripped = [];
  const remove = new Set(); // 行下标
  let depth = 0;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const m = depth === 0 ? line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=/) : null;
    if (m && targets.has(m[1])) {
      // 紧邻上方连续注释行随块剥(注释即答案面)
      let start = i;
      while (start > 0 && lines[start - 1].trim().startsWith("#")) start -= 1;
      // 消费赋值块直至括号深度回零
      let j = i;
      let d = 0;
      do {
        for (const ch of lines[j]) {
          if (ch === "(" || ch === "[" || ch === "{") d += 1;
          else if (ch === ")" || ch === "]" || ch === "}") d -= 1;
        }
        remove.add(j);
        j += 1;
      } while (d > 0 && j < lines.length);
      for (let k = start; k < i; k++) remove.add(k);
      stripped.push(m[1]);
      i = j;
      continue;
    }
    // 深度跟踪仅在多行块内需要;顶层行重置
    depth = 0;
    i += 1;
  }
  const kept = lines.filter((_, idx) => !remove.has(idx));
  // 3+ 连续空行折 2(剥块后残缝整形,确定性)
  const squeezed = [];
  let blanks = 0;
  for (const l of kept) {
    if (l.trim() === "") blanks += 1;
    else blanks = 0;
    if (blanks <= 2) squeezed.push(l);
  }
  let out = squeezed.join("\n");
  if (!out.endsWith("\n")) out += "\n";
  // absent = 既没剥成赋值块、剥后文本也不再含的 import 名(共享 def/class 保留 → 不在列)
  const absent = [...targets].filter((n) => !stripped.includes(n) && !new RegExp(`\\b${n}\\b`).test(out));
  // 缩进定义面(#333 P2a 评审备忘硬化):目标名以缩进赋值形(条件块/嵌套定义)残留 =
  // 机械剥离盲区——既非 absent(名字还在)也非可静默保留(答案面在场);点名交调用方
  // throw(半剥沙箱禁用,人裁)。
  const indented = [...targets].filter((n) => !stripped.includes(n) && new RegExp(`^\\s+${n}\\s*(?::[^=\\n]+)?=`, "m").test(out));
  return { text: out, stripped, absent, indented };
}

// ── 沙箱构建 ──
// opts: { repo, ref=HEAD, name, outDir?|runDir?, universePath, python? }
// 返回 { sandbox, name, stripped: {source, test, maps} }
export function buildSandbox(opts) {
  const { repo, name, universePath, ref = "HEAD" } = opts;
  if (!opts.outDir && !opts.runDir) throw new Error("须给 --out DIR 或 --run-dir DIR 之一");
  if (opts.outDir && opts.runDir) throw new Error("--out 与 --run-dir 互斥");
  // 考题闸:钉死名单内才可开沙箱(防名单漂移期误开)
  const uniLines = fs.readFileSync(universePath ?? path.join(import.meta.dirname, "data", "universe.jsonl"), "utf8").split("\n").filter(Boolean);
  const uniMeta = JSON.parse(uniLines[0]);
  if (uniMeta.frozen !== true)
    throw new Error(`宇宙名单未冻结(frozen≠true):${universePath}——重劈须人裁,禁对未钉死名单开沙箱`);
  const uniNames = new Set(uniLines.slice(1).map((l) => { try { return JSON.parse(l).name; } catch { return null; } }));
  if (!uniNames.has(name))
    throw new Error(`考题闸:${name} 不在 universe 名单(须先入名单钉死才可开沙箱)`);

  const sandbox = opts.runDir ? path.join(opts.runDir, name, "sandbox") : opts.outDir;
  if (fs.existsSync(sandbox) && fs.readdirSync(sandbox).length)
    throw new Error(`目标沙箱目录非空:${sandbox}(旧沙箱禁复用,换新目录或先清理)`);
  fs.mkdirSync(path.dirname(sandbox), { recursive: true });

  // 无历史检出:git archive 只取 ref 树 tracked 文件(无 .git 历史/未跟踪数据面)
  const tarTmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "add-sbx-")), "tree.tar");
  execFileSync("git", ["-C", repo, "archive", "--format=tar", ref, "-o", tarTmp]);
  fs.mkdirSync(sandbox, { recursive: true });
  execFileSync("tar", ["-C", sandbox, "-xf", tarTmp]);
  fs.rmSync(path.dirname(tarTmp), { recursive: true, force: true });

  // 剥离清单 1/2:源文件(必须存在——不在即名单与现实分叉,红)+ 逐源测试(有则剥)
  const srcRel = path.join("backend", "ipdb", "_sources", `${name}.py`);
  const srcAbs = path.join(sandbox, srcRel);
  if (!fs.existsSync(srcAbs)) throw new Error(`源文件缺失:${srcRel}(repo=${repo} ref=${ref})——名单与现实分叉,须人裁`);
  const sourceText = fs.readFileSync(srcAbs, "utf8");
  fs.rmSync(srcAbs);
  const testRel = path.join("backend", "tests", "sources", `test_${name}.py`);
  const testAbs = path.join(sandbox, testRel);
  const hadTest = fs.existsSync(testAbs);
  if (hadTest) fs.rmSync(testAbs);

  // 剥离清单 3:_classification 内该源顶层赋值块(机械派生自源文件 import 面;有则剥)
  let maps = [];
  const clsRel = path.join("backend", "ipdb", "_classification.py");
  const clsAbs = path.join(sandbox, clsRel);
  const wanted = extractClassificationImports(sourceText);
  if (wanted.length && fs.existsSync(clsAbs)) {
    const cls = fs.readFileSync(clsAbs, "utf8");
    // 只剥顶层赋值名:import 面里的共享函数(normalize 等)不形如赋值,自然保留
    const { text, stripped, absent, indented } = stripClassificationMaps(cls, wanted);
    if (absent.length)
      throw new Error(`剥离清单漂移:${name} 源文件 import ${absent.join(", ")} 但 _classification.py 无此定义(赋值块/共享函数都非)——半剥沙箱禁用,须人裁`);
    if (indented.length)
      throw new Error(`剥离不净(缩进定义面):${name} 的映射 ${indented.join(", ")} 在 _classification.py 以缩进赋值形定义(条件块/嵌套),列 0 剥离器剥不到——半剥沙箱禁用,须人裁重构该映射或改判据`);
    // 剥后目标名不得再出现(引用面残留 = import 炸)
    for (const n of stripped)
      if (text.includes(n)) throw new Error(`剥后 _classification.py 仍含 ${n}(剥离不净,禁用)`);
    fs.writeFileSync(clsAbs, text);
    maps = stripped;
    // 语法面:python 可用则 py_compile(剥坏文件当场红,不留给打分器)
    const python = opts.python;
    if (python) {
      const r = spawnSync(python, ["-m", "py_compile", clsAbs], { encoding: "utf8" });
      if (r.error) { /* 解释器缺场:文本断言已做,跳过编译面 */ }
      else if (r.status !== 0)
        throw new Error(`剥后 _classification.py 编译失败:${String(r.stderr ?? "").slice(0, 400)}`);
    }
  }

  // 无历史单根提交(防 git log/git show 考古);信息不含考题名
  execFileSync("git", ["-C", sandbox, "init", "-q"]);
  execFileSync("git", ["-C", sandbox, "add", "-A", "-f"]); // -f:archive 只含 tracked 件,忽略规则不吞树内文件
  execFileSync("git", ["-C", sandbox, "-c", "user.name=ipradar-bench", "-c", "user.email=bench@ipradar.local",
    "-c", "commit.gpgsign=false", "commit", "-q", "-m", "基准沙箱基线(剥答案单根提交,#333 P2a)"]);

  return { sandbox, name, stripped: { source: true, test: hadTest, maps } };
}

// ── CLI ──
function parseArgs(argv) {
  const out = { name: null, repo: null, ref: "HEAD", universe: null, runDir: null, out: null, python: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--name") out.name = next();
    else if (a === "--repo") out.repo = next();
    else if (a === "--ref") out.ref = next();
    else if (a === "--universe") out.universe = next();
    else if (a === "--run-dir") out.runDir = next();
    else if (a === "--out") out.out = next();
    else if (a === "--python") out.python = next();
    else if (a === "--help" || a === "-h") out.help = true;
    else { console.error(`未知参数:${a}`); process.exit(2); }
  }
  if (out.help || !out.name) {
    console.error("用法:node build-sandbox.mjs --name <题名> [--repo DIR] [--ref HEAD] [--universe PATH] (--run-dir DIR | --out DIR) [--python BIN]");
    process.exit(out.help ? 0 : 2);
  }
  return out;
}

export function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const python = args.python ?? process.env.BENCH_PYTHON ?? "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
  const res = buildSandbox({
    repo: args.repo ?? ROOT,
    ref: args.ref,
    name: args.name,
    outDir: args.out,
    runDir: args.runDir,
    universePath: args.universe,
    python,
  });
  console.log(JSON.stringify({ sandbox: res.sandbox, name: res.name, stripped: res.stripped }));
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  main();
}
