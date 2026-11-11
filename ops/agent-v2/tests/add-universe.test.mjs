// add-universe.test.mjs — #333 P2a 红绿面:加源重实现基准宇宙构建器(gen-universe.mjs)。
// 契约 = spec docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议 + 定案 6:roster − 免考8 − 无key − 无逐源测试 → 劈分沿 40/13 形状
// (类别分层、固定种子、名单钉死)。fixture 全走临时目录,零 python 依赖(CI 供不起
// 解释器;判例 rrsi-split.test.mjs);真 roster 交叉面条件 skip。
// fixture 源名避开 leak-check.test.mjs 的 fixture roster 名字针(不同文件不互扫,
// 双保险零串扰)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { parseRoster } from "../bench/roster.mjs";
import { largestRemainder } from "../bench/rrsi-domain/split-lib.mjs";
import { loadRosterText, runLeakCheck, EXEMPT_MARKER } from "../bench/leak-check.mjs";
import { buildUniverse, renderUniverseJsonl, heldoutSeatsFor, DUMP_META_SCRIPT } from "../bench/add-domain/gen-universe.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOMAIN_DIR = path.resolve(HERE, "..", "bench", "add-domain");
const GEN_PATH = path.join(DOMAIN_DIR, "gen-universe.mjs");
const UNIVERSE_PATH = path.join(DOMAIN_DIR, "data", "universe.jsonl");
const KEYLESS_PATH = path.join(DOMAIN_DIR, "keyless-rules.json");
const EXAM_RULES_PATH = path.resolve(HERE, "..", "bench", "exam-rules.json");

// ── fixture 树:roster 9 行(6 考题 + 免考1 + 无key1 + 无测试1)──
function makeFixtureTree() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "add-universe-"));
  const roster = [
    "alpha_feed | threat | feeds.alpha.example | is_malicious",
    "beta_feed | threat | feeds.beta.example | is_malicious",
    "gamma_feed | threat | feeds.gamma.example | is_malicious",
    "delta_feed | geo_asn | delta.example | as_org",
    "eps_feed | geo_asn | eps.example | as_org",
    "zeta_feed | asset | zeta.example | is_vpn",
    "exempt_src | threat | - | is_malicious",
    "keyless_src | threat | api.keyless.example | is_malicious",
    "notest_src | asset | notest.example | is_vpn",
  ].join("\n");
  fs.writeFileSync(path.join(tmp, "roster.txt"), roster + "\n");
  fs.writeFileSync(path.join(tmp, "exam-rules.json"), JSON.stringify({
    exempt: [{ name: "exempt_src", reason: "fixture 内部派生", reclaim: null }],
  }, null, 2));
  fs.writeFileSync(path.join(tmp, "keyless.json"), JSON.stringify({
    _doc: "fixture",
    keyless: [
      { name: "keyless_src", env: "KEYLESS_SRC_API_KEY", reason: "fixture auth 闸", _why: "禁词引用:fixture 名单载体" },
    ],
  }, null, 2));
  // meta dump fixture:9 源全覆盖(单源纪律:names 必须与 roster 全等)
  const names = ["alpha_feed", "beta_feed", "gamma_feed", "delta_feed", "eps_feed", "zeta_feed",
    "exempt_src", "keyless_src", "notest_src"];
  const metaDump = Object.fromEntries(names.map((n, i) => [n, {
    urls: [`https://${n.replace("_", "-")}.example/feed${i}.txt`],
    archetype: ["iplist", "csv", "source"][i % 3],
  }]));
  fs.writeFileSync(path.join(tmp, "meta.json"), JSON.stringify(metaDump));
  // backend fixture 树:无 key 源文件真读自有 auth env var;其余源文件零 env 读;
  // 逐源测试文件按名字落(考题 6 有,notest_src 无)
  const srcDir = path.join(tmp, "backend", "ipdb", "_sources");
  const testDir = path.join(tmp, "backend", "tests", "sources");
  fs.mkdirSync(srcDir, { recursive: true });
  fs.mkdirSync(testDir, { recursive: true });
  for (const n of names) {
    const body = n === "keyless_src"
      ? "import os\nkey = os.environ.get(\"KEYLESS_SRC_API_KEY\", \"\")\n"
      : "# plain fixture source\nVALUE = 1\n";
    fs.writeFileSync(path.join(srcDir, `${n}.py`), body);
    if (n !== "notest_src") fs.writeFileSync(path.join(testDir, `test_${n}.py`), "def test_fixture():\n    assert True\n");
  }
  return { tmp, rosterPath: path.join(tmp, "roster.txt"), metaPath: path.join(tmp, "meta.json"),
    keylessPath: path.join(tmp, "keyless.json"), rulesPath: path.join(tmp, "exam-rules.json"),
    backendDir: path.join(tmp, "backend") };
}

function buildFromFixture(fx, overrides = {}) {
  return buildUniverse({
    rosterText: fs.readFileSync(fx.rosterPath, "utf8"),
    metaDump: JSON.parse(fs.readFileSync(fx.metaPath, "utf8")),
    examRules: JSON.parse(fs.readFileSync(fx.rulesPath, "utf8")),
    keylessRules: JSON.parse(fs.readFileSync(fx.keylessPath, "utf8")),
    backendDir: fx.backendDir,
    seed: 20261111,
    ...overrides,
  });
}

test("buildUniverse:三类剔除(免考/无key/无逐源测试)+ 列形 + 豁免标记 + 席位可重算", () => {
  const fx = makeFixtureTree();
  const { meta, rows } = buildFromFixture(fx);
  // 6 考题 = 9 − 免考1 − 无key1 − 无测试1
  assert.equal(meta.total, 6);
  assert.equal(meta.rosterTotal, 9);
  assert.equal(meta.exemptTotal, 1);
  assert.equal(meta.keylessTotal, 1);
  assert.equal(meta.noTestTotal, 1);
  const names = rows.map((r) => r.name);
  assert.deepEqual([...names].sort(), ["alpha_feed", "beta_feed", "delta_feed", "eps_feed", "gamma_feed", "zeta_feed"]);
  // 列形:name|url|split|category|archetype(+ _why 豁免标记)
  const metaDump = JSON.parse(fs.readFileSync(fx.metaPath, "utf8"));
  for (const r of rows) {
    assert.ok(["evolve", "heldout"].includes(r.split), `split 值非法:${r.split}`);
    assert.ok(r.url && r.url.startsWith("https://"), `url 面:${r.name}`);
    assert.ok(r._why && r._why.includes(EXEMPT_MARKER), `豁免标记缺失:${r.name}`);
    assert.equal(r.url, metaDump[r.name].urls[0]);
    assert.equal(r.archetype, metaDump[r.name].archetype);
    assert.ok(r.category === "threat" || r.category === "geo_asn" || r.category === "asset");
  }
  // 劈分沿 40/13 形状:heldout = round(N×13/53);6 考题 → 1
  assert.equal(meta.heldout, 1);
  assert.equal(meta.evolve, 5);
  assert.equal(rows.filter((r) => r.split === "heldout").length, 1);
  // 席位经 largestRemainder 可重算复现(出处链)
  const counts = {};
  for (const r of rows) counts[r.category] = (counts[r.category] ?? 0) + 1;
  const seats = Object.fromEntries(largestRemainder(counts, meta.heldout).entries());
  assert.deepEqual(seats, meta.heldoutSeats, "meta.heldoutSeats 不是当前考题计数的分席产物");
  const held = {};
  for (const r of rows.filter((r) => r.split === "heldout")) held[r.category] = (held[r.category] ?? 0) + 1;
  for (const [c, n] of Object.entries(seats)) assert.equal(held[c] ?? 0, n, `类别 ${c} 留出计数 ≠ 分席值`);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("buildUniverse:确定性——同输入双跑字节级同 JSONL(固定种子)", () => {
  const fx = makeFixtureTree();
  const a = renderUniverseJsonl(buildFromFixture(fx));
  const b = renderUniverseJsonl(buildFromFixture(fx));
  assert.equal(a, b);
  // 不同种子 → 名单允许漂移(种子是劈分自由度)
  const c = renderUniverseJsonl(buildFromFixture(fx, { seed: 999 }));
  assert.notEqual(a, c);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("buildUniverse:keyless 名单漂移红——源文件不再读登记的 env var → throw", () => {
  const fx = makeFixtureTree();
  const src = path.join(fx.backendDir, "ipdb", "_sources", "keyless_src.py");
  fs.writeFileSync(src, "import os\nkey = os.environ.get(\"KEYLESS_SRC_V2_TOKEN\", \"\")\n");
  assert.throws(() => buildFromFixture(fx), /keyless_src.*KEYLESS_SRC_API_KEY/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("buildUniverse:完备性反扫——未登记的 auth env(KEY|TOKEN|AUTH)→ throw(fail-closed)", () => {
  const fx = makeFixtureTree();
  const src = path.join(fx.backendDir, "ipdb", "_sources", "alpha_feed.py");
  fs.writeFileSync(src, "import os\nk = os.environ.get(\"ALPHA_FEED_SECRET_TOKEN\", \"\")\n");
  assert.throws(() => buildFromFixture(fx), /alpha_feed.*ALPHA_FEED_SECRET_TOKEN/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("buildUniverse:反扫 os.getenv 习语面同样拦;登记后 getenv 形判据也过(#333 P2a 评审备忘硬化)", () => {
  const fx = makeFixtureTree();
  // os.getenv 形的未登记 auth 读 → 同拦(反扫盲区:习语不同语义同)
  fs.writeFileSync(path.join(fx.backendDir, "ipdb", "_sources", "alpha_feed.py"),
    "import os\nk = os.getenv(\"ALPHA_FEED_SECRET_TOKEN\")\n");
  assert.throws(() => buildFromFixture(fx), /alpha_feed.*ALPHA_FEED_SECRET_TOKEN/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
  // 登记侧:keyless 源改用 os.getenv 形读登记 env → 判据断言同样认(双向习语面对齐)
  const fx2 = makeFixtureTree();
  fs.writeFileSync(path.join(fx2.backendDir, "ipdb", "_sources", "keyless_src.py"),
    "import os\nkey = os.getenv(\"KEYLESS_SRC_API_KEY\")\n");
  const { meta } = buildFromFixture(fx2);
  assert.equal(meta.keylessTotal, 1, "登记过的 getenv 形 auth 闸照常剔出考题(习语不改变无 key 事实)");
  fs.rmSync(fx2.tmp, { recursive: true, force: true });
});

test("buildUniverse:免考判据交叉断言 + meta dump 单源纪律", () => {
  const fx = makeFixtureTree();
  // 免考名单源 host ≠ '-' → throw(gen-split 同律)
  const rosterBad = fs.readFileSync(fx.rosterPath, "utf8").replace("exempt_src | threat | - |", "exempt_src | threat | x.example |");
  assert.throws(() => buildFromFixture(fx, { rosterText: rosterBad }), /exempt_src/);
  // meta dump 缺 roster 源 → throw(禁第二份清单静默漂移)
  const dump = JSON.parse(fs.readFileSync(fx.metaPath, "utf8"));
  delete dump.zeta_feed;
  assert.throws(() => buildFromFixture(fx, { metaDump: dump }), /zeta_feed/);
  // 考题 url 面缺失(url attr 空 + 同 host 字面量零)→ throw(交接单预填前提)
  dump.zeta_feed = { urls: [], archetype: "iplist" };
  assert.throws(() => buildFromFixture(fx, { metaDump: dump }), /zeta_feed.*url/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("gen-universe.mjs CLI:确定性双跑字节级一致;冻结件拒绝覆盖;未冻结件正常覆写", () => {
  const fx = makeFixtureTree();
  const run = (out) => execFileSync(process.execPath, [
    GEN_PATH, "--roster-file", fx.rosterPath, "--meta-file", fx.metaPath,
    "--exam-rules", fx.rulesPath, "--keyless", fx.keylessPath, "--backend", fx.backendDir,
    "--out", out,
  ]);
  const a = path.join(fx.tmp, "a.jsonl");
  const b = path.join(fx.tmp, "b.jsonl");
  run(a); run(b);
  assert.equal(fs.readFileSync(a, "utf8"), fs.readFileSync(b, "utf8"), "CLI 双跑字节级一致");
  const first = JSON.parse(fs.readFileSync(a, "utf8").split("\n")[0]);
  assert.equal(first.frozen, false, "生成器产物未裁决前 frozen=false");
  // 冻结件拒绝覆盖(#325 F2 同律:答案分发面禁静默重写)
  const frozenLines = fs.readFileSync(a, "utf8").split("\n");
  frozenLines[0] = frozenLines[0].replace("\"frozen\":false", "\"frozen\":true");
  fs.writeFileSync(a, frozenLines.join("\n"));
  const before = fs.readFileSync(a, "utf8");
  let rc = 0, stderr = "";
  try { run(a); } catch (e) { rc = e.status ?? 0; stderr = String(e.stderr ?? ""); }
  assert.equal(rc, 1, "冻结件覆盖须 exit 1");
  assert.ok(stderr.includes("拒绝覆盖"));
  assert.equal(fs.readFileSync(a, "utf8"), before, "冻结件不得被改动");
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("heldoutSeatsFor:沿 40/13 形状 N→H 换算(53→13,33→8,6→1)", () => {
  assert.equal(heldoutSeatsFor(53), 13);
  assert.equal(heldoutSeatsFor(33), 8);
  assert.equal(heldoutSeatsFor(6), 1);
});

// ── 真仓件:universe.jsonl 结构不变式(零 python)+ 真 roster 交叉面(条件 skip)──

function loadUniverse() {
  const lines = fs.readFileSync(UNIVERSE_PATH, "utf8").split("\n").filter(Boolean);
  return { meta: JSON.parse(lines[0]), rows: lines.slice(1).map((l) => JSON.parse(l)), nameLines: lines.slice(1) };
}

test("universe.jsonl 结构不变式:冻结钉死 + 计数自洽 + 全行豁免标记 + 席位重算", () => {
  const { meta, rows, nameLines } = loadUniverse();
  assert.equal(meta.kind, "ipradar-add-universe");
  assert.equal(meta.frozen, true, "名单钉死:meta.frozen 必须为真(重生成须先手工改回 false)");
  assert.equal(meta.ticket, "#333");
  assert.equal(rows.length, meta.total);
  assert.equal(meta.total, meta.evolve + meta.heldout);
  assert.equal(rows.filter((r) => r.split === "evolve").length, meta.evolve);
  assert.equal(rows.filter((r) => r.split === "heldout").length, meta.heldout);
  assert.equal(meta.heldout, heldoutSeatsFor(meta.total), "heldout 席位数不是 round(N×13/53) 形状");
  const names = rows.map((r) => r.name);
  assert.equal(new Set(names).size, names.length, "名单无重复");
  for (const line of nameLines) assert.ok(line.includes(EXEMPT_MARKER), `豁免标记缺失:${line.slice(0, 60)}`);
  // 席位重算复现(#325 F2 同律:meta 自称分层分席就必须可重算)
  const counts = {};
  for (const r of rows) counts[r.category] = (counts[r.category] ?? 0) + 1;
  assert.deepEqual(Object.fromEntries(largestRemainder(counts, meta.heldout).entries()), meta.heldoutSeats);
  const held = {};
  for (const r of rows.filter((r) => r.split === "heldout")) held[r.category] = (held[r.category] ?? 0) + 1;
  for (const [c, n] of Object.entries(meta.heldoutSeats)) assert.equal(held[c] ?? 0, n);
  // 劈分双侧类别覆盖(演化/留出各自三类非空——加源轮类别分层同 rrsi 律)
  for (const side of ["evolve", "heldout"]) {
    const cats = new Set(rows.filter((r) => r.split === side).map((r) => r.category));
    for (const c of ["threat", "geo_asn", "asset"]) assert.ok(cats.has(c), `${side} 缺类别 ${c}`);
  }
});

let rosterText = null;
try {
  rosterText = loadRosterText({ env: process.env });
} catch {
  rosterText = null;
}
const SKIP_ROSTER = rosterText ? false : "无 roster 取数面(BENCH_ROSTER_FILE 未设且 spawn 失败)";

test("universe.jsonl 名单 ⊆ 真 roster 考题宇宙(免考/无key/无逐源测试均不得混入),类别一致,域目录过 leak 闸", { skip: SKIP_ROSTER }, () => {
  const { rows } = loadUniverse();
  const roster = parseRoster(rosterText);
  const examRules = JSON.parse(fs.readFileSync(EXAM_RULES_PATH, "utf8"));
  const keylessRules = JSON.parse(fs.readFileSync(KEYLESS_PATH, "utf8"));
  const exempt = new Set((examRules.exempt ?? []).map((e) => e.name));
  const keyless = new Set((keylessRules.keyless ?? []).map((e) => e.name));
  const byName = new Map(roster.map((r) => [r.name, r]));
  for (const e of [...exempt, ...keyless])
    assert.ok(byName.has(e), `剔除名单源不在 roster:${e}`);
  // 独立重导考题宇宙:roster − 免考 − 无key − 无 test_<name>.py(判据独立重述,防生成器自洽谎言)
  const backendDir = path.resolve(DOMAIN_DIR, "..", "..", "..", "..", "backend");
  const eligible = roster.filter((r) => !exempt.has(r.name) && !keyless.has(r.name)
    && fs.existsSync(path.join(backendDir, "tests", "sources", `test_${r.name}.py`)));
  const eligibleNames = new Set(eligible.map((r) => r.name));
  assert.equal(eligibleNames.size, loadUniverse().meta.total,
    `考题宇宙漂移:${eligibleNames.size} ≠ ${loadUniverse().meta.total}——冻结名单须重裁`);
  for (const r of rows) {
    assert.ok(eligibleNames.has(r.name), `名单成员不该在考题宇宙:${r.name}`);
    assert.equal(byName.get(r.name).category, r.category, `类别漂移:${r.name}`);
    assert.ok(r.url, `url 面缺失:${r.name}`);
    assert.ok(["IpListSource", "CsvSource", "Source"].includes(r.archetype), `archetype 非法(须原型族类名):${r.name}`);
  }
  for (const n of eligibleNames)
    assert.ok(rows.some((r) => r.name === n), `考题缺席名单:${n}`);
  // 域目录整体过 leak 闸(真 roster 针集;universe/keyless 名单行靠行级豁免放行)
  const files = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (e.name === "node_modules" || e.name === "__pycache__") continue;
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else files.push(p);
    }
  };
  walk(DOMAIN_DIR);
  const result = runLeakCheck({ rosterText, files });
  assert.deepEqual(result.hits, [], `域目录 leak 命中:${result.hits.map((h) => h.text.slice(0, 60)).join("; ")}`);
  assert.equal(result.scannedFiles.length, files.length, "扫描覆盖不足");
});

// ── #338:url dump 运行时判据面(python 条件面;多行字面量判例 = 真 sw 双题源)──

const BACKEND_DIR = path.resolve(DOMAIN_DIR, "..", "..", "..", "..", "backend");

// dump 取数解释器:IPDB_PYTHON 覆写 → python3 可 import ipdb(worktree backend 作 cwd,-c 模式
// sys.path[0]=cwd;loadRosterText 同律)。不可用 = 条件 skip(CI 供不起真 backend 依赖面)。
function resolveDumpPython() {
  const bin = process.env.IPDB_PYTHON ?? "python3";
  try {
    execFileSync(bin, ["-c", "import ipdb"], { cwd: BACKEND_DIR, stdio: "ignore" });
    return bin;
  } catch {
    return null;
  }
}
const DUMP_PY = resolveDumpPython();
const SKIP_DUMP = DUMP_PY ? false : "无 dump 取数面(python3 无法 import ipdb;CI 判例,同 SKIP_ROSTER 律)";

function dumpMeta() {
  return JSON.parse(execFileSync(DUMP_PY, ["-c", DUMP_META_SCRIPT], { cwd: BACKEND_DIR, encoding: "utf8" }));
}

test("DUMP_META_SCRIPT url 判据 = 运行时类属性(#338):多行字面量源 dump 完整拼接 URL;多端点源 url='' 字面量兜底不回退", { skip: SKIP_DUMP }, () => {
  const dump = dumpMeta();
  // sw 双题 = 多行字符串字面量判例(backend/ipdb/_sources/sw_scanners.py: url=("…/IPs/"
  // "master/Lists/Scanners.csv")):旧判据把同 host 字面量并集进 urls,单行正则在换行处截断
  // → 证据面同折为 …/IPs/ 前缀(F4 路径键保守红,结构性零分,#337 报告复算段);运行时值
  // 已拼接完整,判据取运行时类属性(唯一真值,无截断孪生项)
  assert.deepEqual(dump.sw_scanners.urls,
    ["https://raw.githubusercontent.com/ShadowWhisperer/IPs/master/Lists/Scanners.csv"],
    "sw_scanners:多行字面量 → 完整拼接 URL(单条,无截断孪生)");
  assert.deepEqual(dump.sw_threats.urls,
    ["https://raw.githubusercontent.com/ShadowWhisperer/IPs/master/Lists/Threats.csv"],
    "sw_threats:多行字面量 → 完整拼接 URL(单条,无截断孪生)");
  // 多端点源 url attr 空串(真实地址在模块常量,firehol 同款)→ 字面量兜底扫描仍在:
  // url 面缺失 = buildUniverse 考题 url 面红(fail-closed,禁整支删——malicious_ip 是考题)
  assert.deepEqual(dump.malicious_ip.urls,
    ["https://raw.githubusercontent.com/romainmarcoux/malicious-ip/master"],
    "malicious_ip:url attr 空串 → 字面量兜底面保留");
});

test("universe.jsonl 勘误一致性(#338):修后 dump 重导 = 名序列/劈分序列/全行字节一致;meta 除 frozen 位外全等", { skip: SKIP_DUMP }, () => {
  // 勘误协议(#333):frozen 手改 false → 重导 → 人检 → 手改 true。本测试 = 重导后的
  // 永久机检锚:同 roster/同 dump 判据/同种子重导必须逐字节复现入仓件(名序列+劈分
  // 序列+url 全部钉死;#338 勘误只许 url 变——当日实测变化 8 行:sw_scanners/sw_threats
  // + cloudzy/dns_public/emerging_threats/f3csystems/geolite_city/ziyadnz,均旧值=新值
  // 前缀形,逐行见 dev/p338-report.md 宇宙 diff 段)。
  if (!rosterText) assert.fail("roster 面缺席(与本测试同解器,不应到达)");
  const metaDump = dumpMeta();
  const examRules = JSON.parse(fs.readFileSync(EXAM_RULES_PATH, "utf8"));
  const keylessRules = JSON.parse(fs.readFileSync(KEYLESS_PATH, "utf8"));
  const { meta, rows } = buildUniverse({
    rosterText, metaDump, examRules, keylessRules, backendDir: BACKEND_DIR, seed: 20261111,
  });
  const rendered = renderUniverseJsonl({ meta, rows }).split("\n").filter(Boolean);
  const diskLines = fs.readFileSync(UNIVERSE_PATH, "utf8").split("\n").filter(Boolean);
  assert.equal(rendered.length, diskLines.length, "行数漂移(名序列增减=须重裁)");
  for (let i = 1; i < rendered.length; i++)
    assert.equal(rendered[i], diskLines[i], `第 ${i + 1} 行字节漂移(名/劈分/url 任意面)
  重导:${rendered[i]}
  入仓:${diskLines[i]}`);
  // meta 面:除 frozen(入仓冻结手改 true,生成器恒产 false)外全等
  assert.deepEqual({ ...JSON.parse(rendered[0]), frozen: loadUniverse().meta.frozen }, loadUniverse().meta,
    "meta 漂移:种子/计数/席位面与入仓件不一致(名单钉死,漂移须重裁)");
  assert.equal(loadUniverse().meta.frozen, true, "勘误后 frozen=true 维持(#333 冻结律)");
});
