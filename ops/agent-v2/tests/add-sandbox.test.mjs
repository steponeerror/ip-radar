// add-sandbox.test.mjs — #333 P2a 红绿面:剥答案无历史沙箱构建器(build-sandbox.mjs)。
// 契约 = spec §重实现基准协议「剥答案沙箱(防泄漏三件套)」前两条:剥离清单(源文件/
// 逐源测试/_classification 内该源 _MAP 块)+ 无历史检出(git init 压缩单根提交,防
// git log 考古)。fixture 全走临时 git 仓,零真仓面;python 语法面条件 skip(判例
// rrsi-split.test.mjs)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";

import { buildSandbox, extractClassificationImports, stripClassificationMaps } from "../bench/add-domain/build-sandbox.mjs";

const ALPHA_MAP_COMMENT = "ALPHA 判据注释块——注释即答案面,须随赋值块一起剥";

function makeFixtureRepo() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "add-sandbox-"));
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "backend", "ipdb", "_sources"), { recursive: true });
  fs.mkdirSync(path.join(repo, "backend", "tests", "sources"), { recursive: true });
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "_classification.py"), [
    '"""fixture classification vocabulary + maps + helpers."""',
    "CLASSIFICATION_TYPES = frozenset({'blacklist', 'scanner'})",
    "",
    `# ${ALPHA_MAP_COMMENT}`,
    "ALPHA_MAP = {",
    '    "ssh": "brute-force",',
    "}",
    "",
    "BETA_MAP = {",
    '    "spam": "spam",',
    "}",
    "",
    "_warned = set()",
    "",
    "def normalize(raw, mapping):",
    "    return mapping.get(raw, 'other')",
    "",
  ].join("\n"));
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "_sources", "alpha.py"),
    "from .._classification import ALPHA_MAP\nname = 'alpha'\n");
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "_sources", "beta.py"),
    "name = 'beta'\n");
  fs.writeFileSync(path.join(repo, "backend", "tests", "sources", "test_alpha.py"),
    "def test_alpha():\n    assert True\n");
  fs.writeFileSync(path.join(repo, "backend", "tests", "sources", "test_beta.py"),
    "def test_beta():\n    assert True\n");
  fs.writeFileSync(path.join(repo, "README.md"), "# fixture repo\n");
  execFileSync("git", ["-C", repo, "init", "-q"]);
  execFileSync("git", ["-C", repo, "add", "-A", "-f"]);
  execFileSync("git", ["-C", repo, "-c", "user.name=fixture", "-c", "user.email=f@x.example", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture root commit(考古锚——沙箱内不得可见)"]);
  // fixture universe:钉死件,含 alpha/beta 两题
  const universePath = path.join(tmp, "universe.jsonl");
  fs.writeFileSync(universePath, [
    JSON.stringify({ kind: "ipradar-add-universe", frozen: true }),
    ...["alpha", "beta"].map((n) => JSON.stringify({ split: "evolve", name: n, url: `https://${n}.example/f.txt`, category: "threat", archetype: "IpListSource", _why: "禁词引用:fixture" })),
  ].join("\n") + "\n");
  return { tmp, repo, universePath };
}

function pyCompileOk(python, file) {
  const r = spawnSync(python, ["-m", "py_compile", file], { encoding: "utf8" });
  if (r.error) return { skip: true };
  return { skip: false, ok: r.status === 0, err: String(r.stderr ?? "") };
}

test("extractClassificationImports:相对/绝对/带括号多行导入面全解析", () => {
  assert.deepEqual(extractClassificationImports("from .._classification import ALPHA_MAP\n"), ["ALPHA_MAP"]);
  assert.deepEqual(extractClassificationImports("from ipdb._classification import normalize, DATAPLANE_LIKE_MAP  # trailing"), ["normalize", "DATAPLANE_LIKE_MAP"]);
  assert.deepEqual(extractClassificationImports("from .._classification import (\n    A_MAP, normalize_counted,\n    unmapped_summary)\n"), ["A_MAP", "normalize_counted", "unmapped_summary"]);
  assert.deepEqual(extractClassificationImports("from .._source_base import Source\n"), []);
});

test("stripClassificationMaps:剥该源赋值块+紧邻判据注释;他源块/词表/函数全保留;剥后可编译", () => {
  const src = [
    '"""doc"""',
    "CLASSIFICATION_TYPES = frozenset({'blacklist'})",
    "",
    `# ${ALPHA_MAP_COMMENT}`,
    "ALPHA_MAP = {",
    '    "ssh": "brute-force",',
    "}",
    "",
    "BETA_MAP = {'spam': 'spam'}",
    "",
    "def normalize(raw, mapping):",
    "    return mapping.get(raw, 'other')",
    "",
  ].join("\n");
  const { text, stripped, absent } = stripClassificationMaps(src, ["ALPHA_MAP"]);
  assert.deepEqual(stripped, ["ALPHA_MAP"]);
  assert.deepEqual(absent, []);
  assert.ok(!text.includes("ALPHA_MAP"), "目标赋值块须剥净");
  assert.ok(!text.includes(ALPHA_MAP_COMMENT), "紧邻判据注释随块剥(注释即答案面)");
  assert.ok(text.includes("BETA_MAP"), "他源块保留");
  assert.ok(text.includes("CLASSIFICATION_TYPES"), "共享词表保留");
  assert.ok(text.includes("def normalize"), "共享函数保留");
  // 目标不在文件 → absent 记账(调用方 throw,防静默半剥)
  const drift = stripClassificationMaps(src, ["GHOST_MAP"]);
  assert.deepEqual(drift.absent, ["GHOST_MAP"]);
  // 真实边(dataplane 形):import 面含共享函数名 normalize + 同源映射表——
  // 函数自然保留不入 absent,只剥赋值块
  const mixed = stripClassificationMaps(src, ["ALPHA_MAP", "normalize"]);
  assert.deepEqual(mixed.stripped, ["ALPHA_MAP"]);
  assert.deepEqual(mixed.absent, []);
  assert.ok(mixed.text.includes("def normalize"));
});

test("buildSandbox:剥答案三件套 + 无历史单根提交 + 考题闸", () => {
  const fx = makeFixtureRepo();
  const outDir = path.join(fx.tmp, "sandbox");
  const res = buildSandbox({ repo: fx.repo, name: "alpha", outDir, universePath: fx.universePath, python: "python3" });
  // 剥离清单:源文件/逐源测试剥,他源面保留
  assert.ok(!fs.existsSync(path.join(outDir, "backend", "ipdb", "_sources", "alpha.py")));
  assert.ok(!fs.existsSync(path.join(outDir, "backend", "tests", "sources", "test_alpha.py")));
  assert.ok(fs.existsSync(path.join(outDir, "backend", "ipdb", "_sources", "beta.py")));
  assert.ok(fs.existsSync(path.join(outDir, "backend", "tests", "sources", "test_beta.py")));
  assert.ok(fs.existsSync(path.join(outDir, "README.md")));
  // _classification:该源块剥净(含判据注释),他源块/词表/函数保留
  const cls = fs.readFileSync(path.join(outDir, "backend", "ipdb", "_classification.py"), "utf8");
  assert.ok(!cls.includes("ALPHA_MAP"));
  assert.ok(!cls.includes(ALPHA_MAP_COMMENT));
  assert.ok(cls.includes("BETA_MAP") && cls.includes("CLASSIFICATION_TYPES") && cls.includes("def normalize"));
  assert.deepEqual(res.stripped, { source: true, test: true, maps: ["ALPHA_MAP"] });
  // 剥后文件可编译(python 缺场 skip,判例 rrsi-split)
  const pc = pyCompileOk("python3", path.join(outDir, "backend", "ipdb", "_classification.py"));
  if (!pc.skip) assert.ok(pc.ok, `剥后 _classification 不可编译:${pc.err}`);
  // 无历史:单根提交,历史考古锚不可见,提交信息不含考题名
  const log = execFileSync("git", ["-C", outDir, "log", "--oneline", "--all"], { encoding: "utf8" });
  assert.equal(log.trim().split("\n").length, 1, "须压缩为单根提交");
  assert.ok(!log.includes("alpha"), "提交信息不得含考题名(git log 考古面)");
  assert.ok(!execFileSync("git", ["-C", outDir, "log", "--all", "--format=%B"], { encoding: "utf8" }).includes("fixture root"), "原历史不可考古");
  const status = execFileSync("git", ["-C", outDir, "status", "--porcelain"], { encoding: "utf8" });
  assert.equal(status, "", "沙箱工作树须干净(全量单根提交)");
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("buildSandbox:考题闸三红——非名单题/未冻结宇宙/目标目录非空", () => {
  const fx = makeFixtureRepo();
  assert.throws(() => buildSandbox({ repo: fx.repo, name: "gamma", outDir: path.join(fx.tmp, "s1"), universePath: fx.universePath }), /gamma.*universe|universe.*gamma/i);
  const unfrozen = path.join(fx.tmp, "unfrozen.jsonl");
  fs.writeFileSync(unfrozen, fs.readFileSync(fx.universePath, "utf8").replace('"frozen":true', '"frozen":false'));
  assert.throws(() => buildSandbox({ repo: fx.repo, name: "alpha", outDir: path.join(fx.tmp, "s2"), universePath: unfrozen }), /frozen|钉死/);
  const busy = path.join(fx.tmp, "busy");
  fs.mkdirSync(busy, { recursive: true });
  fs.writeFileSync(path.join(busy, "x.txt"), "occupied");
  assert.throws(() => buildSandbox({ repo: fx.repo, name: "alpha", outDir: busy, universePath: fx.universePath }), /非空|已存在/);
  // 漂移红:源文件 import 的块不在 _classification → throw(防静默半剥);
  // 构建取 ref 树,漂移须先进 ref(工作树面不入沙箱)
  fs.appendFileSync(path.join(fx.repo, "backend", "ipdb", "_sources", "alpha.py"), "from .._classification import GHOST_MAP\n");
  execFileSync("git", ["-C", fx.repo, "add", "-A", "-f"]);
  execFileSync("git", ["-C", fx.repo, "-c", "user.name=fixture", "-c", "user.email=f@x.example", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "drift"]);
  assert.throws(() => buildSandbox({ repo: fx.repo, name: "alpha", outDir: path.join(fx.tmp, "s3"), universePath: fx.universePath }), /GHOST_MAP/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("buildSandbox:run-dir 布局——--run-dir DIR 落 DIR/<题>/sandbox(打分器扫描布局)", () => {
  const fx = makeFixtureRepo();
  const runDir = path.join(fx.tmp, "trial-01");
  const res = buildSandbox({ repo: fx.repo, name: "beta", runDir, universePath: fx.universePath });
  assert.equal(res.sandbox, path.join(runDir, "beta", "sandbox"));
  assert.ok(fs.existsSync(path.join(runDir, "beta", "sandbox", "README.md")));
  assert.ok(!fs.existsSync(path.join(runDir, "beta", "sandbox", "backend", "ipdb", "_sources", "beta.py")));
  // beta 无 _classification 导入 → maps 空数组(有则剥,无则不剥)
  assert.deepEqual(res.stripped, { source: true, test: true, maps: [] });
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("stripClassificationMaps 缩进定义面:import 名以缩进赋值形残留 = indented 点名(禁静默保留答案面,#333 P2a 评审备忘硬化)", () => {
  const src = [
    '"""doc"""',
    "FLAG = True",
    "if FLAG:",
    "    ALPHA_MAP = {'ssh': 'brute-force'}", // 缩进赋值 = 列 0 剥离器的盲区
    "BETA_MAP = {'spam': 'spam'}",
    "",
  ].join("\n");
  const r = stripClassificationMaps(src, ["ALPHA_MAP"]);
  assert.deepEqual(r.stripped, []); // 列 0 剥不到缩进块
  assert.deepEqual(r.absent, []);   // 名字还在文本里,不是 absent
  assert.deepEqual(r.indented, ["ALPHA_MAP"], "缩进赋值形残留须点名(半剥沙箱禁用,人裁)");
  assert.ok(r.text.includes("ALPHA_MAP"), "文本面如实保留(剥不动机判给人)");
  // 无缩进残留时 indented 恒空(既有面零扰动)
  const clean = stripClassificationMaps("ALPHA_MAP = {\n}\n", ["ALPHA_MAP"]);
  assert.deepEqual(clean.indented, []);
});

test("buildSandbox:_classification 内该源映射以缩进赋值形在场 = throw(缩进定义面 fail-closed)", () => {
  const fx = makeFixtureRepo();
  fs.writeFileSync(path.join(fx.repo, "backend", "ipdb", "_classification.py"), [
    '"""fixture:alpha map 定义在条件块内(缩进赋值形)。"""',
    "_FLAG = True",
    "if _FLAG:",
    "    ALPHA_MAP = {'ssh': 'brute-force'}",
    "",
  ].join("\n"));
  execFileSync("git", ["-C", fx.repo, "add", "-A", "-f"]);
  execFileSync("git", ["-C", fx.repo, "-c", "user.name=fixture", "-c", "user.email=f@x.example", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "indented map"]);
  assert.throws(
    () => buildSandbox({ repo: fx.repo, name: "alpha", outDir: path.join(fx.tmp, "sbx-ind"), universePath: fx.universePath }),
    /缩进|ALPHA_MAP/,
  );
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});
