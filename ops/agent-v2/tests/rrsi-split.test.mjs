// rrsi-split.test.mjs — RRSI 劈分不变式(票 #325;裁决 #322 R1:53 考题劈 40 演化/13 留出,
// 类别分层、固定种子、名单钉死)。劈分是盲测的答案分发面:名单一旦漂移,演化集成绩与
// 留出集验收就不再可比——本测试把结构不变式钉进 v2 套件(CI 恒跑,零 python 零网络),
// roster 交叉面(需要真 roster dump)按 smoke-glm.test.mjs 判例条件 skip。
//
// 生成器 gen-split.mjs 的确定性(同种子同输入 → 字节级同输出)用 fixture roster 双跑
// 比对钉住——答案名单可复算 = 「证据永不灭失」在劈分层的落点。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { parseRoster } from "../bench/roster.mjs";
import { runLeakCheck, loadRosterText, EXEMPT_MARKER } from "../bench/leak-check.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOMAIN_DIR = path.resolve(HERE, "..", "bench", "rrsi-domain");
const SPLIT_PATH = path.join(DOMAIN_DIR, "data", "split.jsonl");
const GEN_PATH = path.join(DOMAIN_DIR, "gen-split.mjs");
const EXAM_RULES_PATH = path.resolve(HERE, "..", "bench", "exam-rules.json");
const EXEMPTION = EXEMPT_MARKER;

function loadSplit() {
  const lines = fs.readFileSync(SPLIT_PATH, "utf8").split("\n").filter(Boolean);
  const meta = JSON.parse(lines[0]);
  const rows = lines.slice(1).map((l) => JSON.parse(l));
  return { meta, rows, nameLines: lines.slice(1) };
}

function countsBy(rows, key) {
  const m = new Map();
  for (const r of rows) m.set(r[key], (m.get(r[key]) ?? 0) + 1);
  return m;
}

test("split.jsonl 结构不变式:40 演化 + 13 留出,类别分层覆盖,名单行全带行级豁免标记", () => {
  const { meta, rows, nameLines } = loadSplit();
  assert.equal(meta.kind, "ipradar-rrsi-split");
  assert.equal(meta.frozen, true, "名单钉死:meta.frozen 必须为真(重生成须重走裁决)");
  assert.equal(meta.evolve, 40);
  assert.equal(meta.heldout, 13);

  assert.equal(rows.length, 53, "考题总数 = 53(61 源 − 8 免考)");
  const evolve = rows.filter((r) => r.set === "evolve");
  const heldout = rows.filter((r) => r.set === "heldout");
  assert.equal(evolve.length, 40);
  assert.equal(heldout.length, 13);
  for (const r of rows) assert.ok(r.set === "evolve" || r.set === "heldout");

  const names = rows.map((r) => r.name);
  assert.equal(new Set(names).size, 53, "无重复");
  const evoSet = new Set(evolve.map((r) => r.name));
  const heldSet = new Set(heldout.map((r) => r.name));
  for (const n of evoSet) assert.ok(!heldSet.has(n), `跨集重复:${n}`);

  // 类别分层:两个集合内 threat/geo_asn/asset 三类都非空(类别覆盖率双侧成立)
  for (const [label, subset] of [["evolve", evolve], ["heldout", heldout]]) {
    const cats = countsBy(subset, "category");
    for (const c of ["threat", "geo_asn", "asset"]) assert.ok(cats.get(c) >= 1, `${label} 缺类别 ${c}`);
  }

  // 行级豁免标记(#308 判例):答案键载体文件,名字行逐行带「禁词引用」豁免,leak 闸放行
  for (const line of nameLines) assert.ok(line.includes(EXEMPTION), `豁免标记缺失:${line.slice(0, 60)}`);
});

test("gen-split.mjs 确定性:同种子同输入双跑字节级一致;最大余数法分层与豁免标记正确", () => {
  // fixture roster:3 类共 10 行 + 2 行免考(download_host '-' → exam-rules exempt 形状),
  // 与真 roster 同列形(name | category | download_host | fields)
  const fixtureRoster = [
    "za1 | threat | z1.example | f",
    "zb2 | threat | z2.example | f",
    "zc3 | threat | z3.example | f",
    "zd4 | threat | z4.example | f",
    "ze5 | threat | z5.example | f",
    "zf6 | geo_asn | z6.example | f",
    "zg7 | geo_asn | z7.example | f",
    "zh8 | asset | z8.example | f",
    "zi9 | asset | z9.example | f",
    "zj0 | asset | z0.example | f",
    "exempt1 | threat | - | f",
    "exempt2 | asset | - | f",
  ].join("\n");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rrsi-split-"));
  const rosterPath = path.join(tmp, "roster.txt");
  const rulesPath = path.join(tmp, "exam-rules.json");
  fs.writeFileSync(rosterPath, fixtureRoster + "\n");
  fs.writeFileSync(
    rulesPath,
    JSON.stringify({ exempt: [
      { name: "exempt1", reason: "fixture 免考形状" },
      { name: "exempt2", reason: "fixture 免考形状" },
    ] }, null, 2),
  );

  // 双跑同种子:heldout=3(threat 2 + geo_asn 1 或按余数),evolve=7
  const run = (out) =>
    execFileSync(process.execPath, [
      GEN_PATH,
      "--roster-file", rosterPath,
      "--exam-rules", rulesPath,
      "--out", out,
      "--evolve", "7",
      "--heldout", "3",
      "--seed", "20261108",
    ]);
  const a = path.join(tmp, "a.jsonl");
  const b = path.join(tmp, "b.jsonl");
  run(a);
  run(b);
  const aText = fs.readFileSync(a, "utf8");
  const bText = fs.readFileSync(b, "utf8");
  assert.equal(aText, bText, "同种子双跑必须字节级一致");

  const { meta, rows, nameLines } = {
    meta: JSON.parse(aText.split("\n")[0]),
    rows: aText.split("\n").slice(1).filter(Boolean).map((l) => JSON.parse(l)),
    nameLines: aText.split("\n").slice(1).filter(Boolean),
  };
  assert.equal(meta.frozen, false, "生成器产物未裁决前 frozen=false;入仓冻结件由人改写 meta");
  assert.equal(rows.length, 10);
  assert.equal(rows.filter((r) => r.set === "heldout").length, 3);
  // 免考剔除:download_host '-' 的 fixture 行不得出现在任何集合
  for (const r of rows) assert.notEqual(r.host, "-");
  // 分层数断言总数与上界(逐类手算勿抄——实现以生成器为准,这里只钉总量与不越界)
  const hc = countsBy(rows.filter((r) => r.set === "heldout"), "category");
  let hsum = 0;
  for (const [c, n] of hc) {
    hsum += n;
    const total = fixtureRoster.split("\n").filter((l) => l.includes(`| ${c} |`) && !l.includes("| - |")).length;
    assert.ok(n <= total, `类别 ${c} 留出数超类内考题数`);
  }
  assert.equal(hsum, 3);
  for (const line of nameLines) assert.ok(line.includes(EXEMPTION), "生成行必须带豁免标记(冻结件同律)");
  fs.rmSync(tmp, { recursive: true, force: true });
});

// roster 交叉面:考题宇宙随 roster 演进而漂移时,冻结名单必须红——CI 无 roster 取数面
// (无 python 解释器/无 BENCH_ROSTER_FILE)按 smoke-glm 判例 skip;本地/验收跑必绿。
let rosterText = null;
try {
  // loadRosterText 单源取数面(优先 env BENCH_ROSTER_FILE,退 spawn python)——失败
  // (无解释器/无 ipdb)= 环境 frontier,skip 而非红(smoke-glm.test.mjs 判例)
  rosterText = loadRosterText({ env: process.env });
} catch {
  rosterText = null;
}
const SKIP_ROSTER = rosterText ? false : "无 roster 取数面(BENCH_ROSTER_FILE 未设且 spawn 失败)";

test("split.jsonl 名单 ⊆ 真 roster 考题集,类别一致,且域目录过 leak 闸", { skip: SKIP_ROSTER }, () => {
  const { meta, rows } = loadSplit();
  const examRules = JSON.parse(fs.readFileSync(EXAM_RULES_PATH, "utf8"));
  const roster = parseRoster(rosterText);
  // 免考面单源:exam-rules.json exempt[].name(票面 8 内部/派生源免考;判据=download_host '-')
  const exemptNames = new Set((examRules.exempt ?? []).map((e) => e.name));
  const exam = roster.filter((r) => !exemptNames.has(r.name));
  assert.equal(exam.length, 53, `真 roster 考题数漂移:${exam.length} ≠ 53——冻结名单须重裁`);
  const byName = new Map(exam.map((r) => [r.name, r]));
  for (const r of rows) {
    const src = byName.get(r.name);
    assert.ok(src, `名单成员不在考题宇宙:${r.name}`);
    assert.equal(src.category, r.category, `类别漂移:${r.name}`);
    assert.notEqual(src.host, "-", `免考源混入:${r.name}`);
  }
  const members = new Set(rows.map((r) => r.name));
  for (const src of exam) assert.ok(members.has(src.name), `考题缺席劈分:${src.name}`);
  assert.equal(meta.ticket, "#325");

  // 域目录整体过 leak 闸(缺省面之外把域文件全量点名:adapter/SKILL/PATTERNS/rrsi.json
  // 不在 leak 缺省面 bench/** 的载体豁免名单里,split.jsonl 靠行级豁免标记放行)
  const files = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (e.name === "node_modules") continue;
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else files.push(p);
    }
  };
  walk(DOMAIN_DIR);
  const result = runLeakCheck({ rosterText, files });
  assert.deepEqual(result.hits, [], `域目录 leak 命中:${result.hits.map((h) => h.text.slice(0, 60)).join("; ")}`);
  assert.equal(result.scannedFiles.length, files.length, "扫描覆盖不足:域文件必须全量入面");
});
