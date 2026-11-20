// fleet.test.mjs — M5 fleet 加源舰队驱动器纯函数面 + CLI 空转面(票 #366)。
// 覆盖:队列轮询(文件序/去重/完成轮跳过/开放轮跳过/连续败跳过/形状过滤)、完成判据
// (G_CLOSE pass 为主判据,state.status=completed 等价)、fleet 状态推进(失败计数/
// 复位/跳过告警一次性)、lift 文本变换(文档三件计数钉/README 表行/rrsi 劈分钉/
// critic 针数钉/发现冒烟计数钉/roster 快照行幂等)——全部「恰一命中」fail-closed;
// 变换同时拿真仓件做只读回归钉(钉面漂移=先红在此,不是真跑轮时)。
// CLI 面:无源空转 exit 0 零模型调用;队列缺席 exit 3;有源无 --model exit 2。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";
import {
  mintFleetRoundId, roundClosedFace, scanAddRoundSources, pickFleetTarget,
  applyFleetOutcome, blockedSourcesOf, FLEET_SKIP_FAILURES,
  bumpReadmeCount, bumpReadmeZhCount, bumpManualCounts, bumpManualImageAlt, bumpManualZhCounts,
  insertReadmeRow, syncRrsiSplitPins, syncRrsiDomainPin, bumpDiscoverySmokePin, insertSnapshotRow,
  changelogEntries, composePrBody, roundStemOf,
} from "../run-fleet.mjs";

const HERE = import.meta.dirname;
const REPO = path.resolve(HERE, "..", "..", "..");
const read = (p) => fs.readFileSync(path.join(REPO, p), "utf8");

// ── 轮 id / 完成判据 ──
test("mintFleetRoundId:YYYY-MM-DD-HHMM-add 形状(run-add 轮 id 形状律)", () => {
  const id = mintFleetRoundId(new Date(2026, 10, 21, 9, 5));
  assert.equal(id, "2026-11-21-0905-add");
});

test("roundClosedFace:G_CLOSE pass=主判据;state.status=completed 等价;均无=开放", () => {
  assert.equal(roundClosedFace(null, { records: [{ name: "G_CLOSE", pass: true }] }), true, "pilot 2250 实测:state 停 running 而 gates G_CLOSE pass");
  assert.equal(roundClosedFace({ status: "completed" }, null), true);
  assert.equal(roundClosedFace({ status: "running" }, { records: [{ name: "G_VERIFY", pass: true }] }), false, "2245 形:仅 G_VERIFY=开放");
  assert.equal(roundClosedFace(null, null), false);
});

// ── rounds 扫描 ──
test("scanAddRoundSources:closed 优先于 open;非 add 轮忽略;目录缺席=空集", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "fleet-rounds-"));
  try {
    const mk = (name, source, gates, type = "add") => {
      fs.mkdirSync(path.join(tmp, name));
      fs.writeFileSync(path.join(tmp, name, "state.json"), JSON.stringify({ type, source, status: "running" }));
      if (gates) fs.writeFileSync(path.join(tmp, name, "gates.json"), JSON.stringify(gates));
    };
    mk("2026-11-18-2245-add", "gaoyifan_cn_ip", { records: [{ name: "G_VERIFY", pass: false }] }); // 开放(中止试点)
    mk("2026-11-18-2250-add", "gaoyifan_cn_ip", { records: [{ name: "G_CLOSE", pass: true }] }); // 同源完成轮 → closed 胜
    mk("2026-11-20-1219-health", "x", { records: [{ name: "G_CLOSE", pass: true }] }, "health"); // health 轮:type≠add 忽略
    mk("2026-11-21-0900-add", "sgb_blocklist", null); // 无 gates.json=开放
    const { closed, open } = scanAddRoundSources(tmp);
    assert.deepEqual([...closed], ["gaoyifan_cn_ip"]);
    assert.deepEqual([...open], ["sgb_blocklist"]);
    const none = scanAddRoundSources(path.join(tmp, "absent"));
    assert.equal(none.closed.size, 0); assert.equal(none.open.size, 0);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

// ── 队首目标 ──
const Q = (rows) => ["| 日期 | 轮次 | action | source | predicate | evidence | vetoable |", "|---|---|---|---|---|---|---|", ...rows].join("\n");
const approve = (s) => `| 2026-11-18 | owner-2026-11-18 | APPROVE | ${s} | — | human:approved_by="owner" | 是 |`;
const propose = (s) => `| 2026-11-18 | needs-x | PROPOSE | ${s} | — | candidate:name="n";candidate:url="https://e.com" | 是 |`;

test("pickFleetTarget:文件序队首;重复 APPROVE 取首见;closed/open/blocked/形状坏跳过;全空=null", () => {
  const queueText = Q([
    propose("gaoyifan_cn_ip"), approve("gaoyifan_cn_ip"),
    propose("sgb_blocklist"), approve("sgb_blocklist"), approve("sgb_blocklist"),
    approve("insightflare_asn"), approve("Bad-Source!"), approve("metowolf_iplist"),
  ]);
  const t1 = pickFleetTarget({ queueText, closedSources: new Set(["gaoyifan_cn_ip"]), openSources: new Set(["sgb_blocklist"]), blockedSources: new Set(["metowolf_iplist"]) });
  assert.equal(t1.source, "insightflare_asn", "跳过完成轮/开放轮/屏蔽源/形状坏后取队首");
  assert.equal(t1.approve.date, "2026-11-18");
  assert.equal(pickFleetTarget({ queueText: Q([]) }), null, "空队列=null");
  assert.equal(pickFleetTarget({ queueText: Q([propose("x_only")]) }), null, "只有 PROPOSE=null");
  const t2 = pickFleetTarget({ queueText }); // 无跳过面:形状坏行跳过,取 gaoyifan
  assert.equal(t2.source, "gaoyifan_cn_ip");
  const t3 = pickFleetTarget({ queueText: Q([approve("a"), approve("b")]) });
  assert.equal(t3.source, "a", "文件序首个");
});

// ── fleet 状态 ──
test("applyFleetOutcome:失败累加/ok 清零/达线记 skip_alerted;blockedSourcesOf=达线集", () => {
  let s = { schema: 1 };
  s = applyFleetOutcome(s, "sgb_blocklist", false, "2026-11-21T01:00:00Z");
  assert.deepEqual(s.failures, { sgb_blocklist: 1 });
  assert.equal(blockedSourcesOf(s).size, 0);
  s = applyFleetOutcome(s, "sgb_blocklist", false, "2026-11-21T02:00:00Z");
  assert.equal(blockedSourcesOf(s).has("sgb_blocklist"), true, `连续 ${FLEET_SKIP_FAILURES} 败达线`);
  assert.equal(s.skip_alerted["sgb_blocklist"], "2026-11-21T02:00:00Z", "首达线记时(告警一次性判据)");
  const s2 = applyFleetOutcome(s, "sgb_blocklist", true);
  assert.equal(s2.failures["sgb_blocklist"], undefined, "ok 清零");
  assert.equal(s2.skip_alerted["sgb_blocklist"], undefined);
});

// ── lift 文本变换:合成面 ──
test("bump* 计数钉:四文档六面 +1(keyless 条件面);漂移=红", () => {
  assert.equal(bumpReadmeCount("**Pull 63 public sources into your own box.**"), "**Pull 64 public sources into your own box.**");
  assert.equal(bumpReadmeZhCount("把 60 个公开情报源搬回家:查任何 IP"), "把 61 个公开情报源搬回家:查任何 IP");
  const manual = "On first start it downloads and builds every keyless feed (56 of the 63 sources) into millions of records.";
  assert.equal(bumpManualCounts(manual, { keyless: true }), "On first start it downloads and builds every keyless feed (57 of the 64 sources) into millions of records.");
  assert.equal(bumpManualCounts(manual, { keyless: false }), "On first start it downloads and builds every keyless feed (56 of the 64 sources) into millions of records.");
  assert.equal(bumpManualImageAlt("![tab: 64 sources (63 public + 1 private honeypot), health]"), "![tab: 65 sources (64 public + 1 private honeypot), health]");
  const zhManual = "首次启动会把全部无 key 源（60 个源中的 53 个）下载。\n![Sources tab:61 源(60 公开 + 1 私有蜜罐)、健康]";
  const bumped = bumpManualZhCounts(zhManual, { keyless: true });
  assert.ok(bumped.includes("（61 个源中的 54 个）"));
  assert.ok(bumped.includes("62 源(61 公开 + 1 私有蜜罐)"));
  assert.throws(() => bumpReadmeCount("无钉面文本"), /钉面漂移.*期望恰 1/);
});

test("insertReadmeRow:节内表尾插行;节缺席/无表=红", () => {
  const md = ["intro", "", "### Threat Reputation", "", "| Source | Provider | Contributes | 🔑 |", "|---|---|---|---|", "| mirage_feed | [m](u) | desc | |", "", "### Geo & ASN", "", "| Source | Provider | |", "| a | b | |", ""].join("\n");
  const out = insertReadmeRow(md, "Threat Reputation", "| sgb_blocklist | [g](u) | fleet | |");
  assert.ok(out.includes("| mirage_feed | [m](u) | desc | |\n| sgb_blocklist | [g](u) | fleet | |"));
  assert.ok(!out.includes("| a | b | |\n| sgb_blocklist"), "geo 节不动");
  assert.throws(() => insertReadmeRow(md, "No Such Section", "x"), /README 节缺席/);
});

test("syncRrsiSplitPins/syncRrsiDomainPin:八钉一针全同步,注记重写;漂移=红", () => {
  const split = [
    'test("split.jsonl 结构不变式:42 演化 + 13 留出,类别分层覆盖,名单行全带行级豁免标记", () => {',
    "  assert.equal(meta.evolve, 42);",
    "  assert.equal(meta.heldout, 13);",
    '  assert.equal(rows.length, 55, "考题总数 = 55(63 源 − 8 免考;2026-11-18 #359/#360 再冻结)");',
    "  assert.equal(evolve.length, 42);",
    "  assert.equal(heldout.length, 13);",
    '  assert.equal(new Set(names).size, 55, "无重复");',
    "  assert.equal(exam.length, 55, `真 roster 考题数漂移:${exam.length} ≠ 55——冻结名单须重裁(2026-11-18 #359/#360 再冻结 53→55)`);",
  ].join("\n");
  const out = syncRrsiSplitPins(split, { evolve: 42, heldout: 14, total: 56, rosterTotal: 64, exempt: 8, tag: "2026-11-21" });
  assert.ok(out.includes("结构不变式:42 演化 + 14 留出"));
  assert.ok(out.includes("assert.equal(meta.heldout, 14);"));
  assert.ok(out.includes('assert.equal(rows.length, 56, "考题总数 = 56(64 源 − 8 免考;2026-11-21 fleet 再冻结)");'));
  assert.ok(out.includes("assert.equal(new Set(names).size, 56"));
  assert.ok(out.includes("assert.equal(exam.length, 56, `真 roster 考题数漂移:${exam.length} ≠ 56——冻结名单须重裁(2026-11-21 fleet 再冻结)`);"));
  assert.throws(() => syncRrsiSplitPins(split.replace("考题总数", "总数"), { evolve: 42, heldout: 14, total: 56, rosterTotal: 64, exempt: 8, tag: "x" }), /钉面漂移/, "钉面措辞改版=红(数字变化不红——同步语义)");
  const dom = '  assert.equal(criticProbe.total, 55, "每考题一行一针(55 行;2026-11-18 再冻结)");';
  assert.equal(syncRrsiDomainPin(dom, { total: 56, tag: "2026-11-21" }), '  assert.equal(criticProbe.total, 56, "每考题一行一针(56 行;2026-11-21 fleet 再冻结)");');
});

test("bumpDiscoverySmokePin:计数+注记追加;insertSnapshotRow:插入+已在幂等", () => {
  const py = 'def test_discovery_smoke_all_real_sources(tmp_path: Path):\n    assert len(sources) == 63          # 本票时点 roster;增删源时同步(2026-11-18 mirage_feed #359 + honeypot_fyi #360 接入 61→63)\n';
  const out = bumpDiscoverySmokePin(py, { total: 64, source: "sgb_blocklist", tag: "2026-11-21" });
  assert.ok(out.includes("assert len(sources) == 64"));
  assert.ok(out.includes("接入 63→64)"));
  const snap = 'OLD_CATEGORIES = {\n    "mirage_feed": "threat",  # x\n}\nOLD_RELIABILITY = {\n    "mirage_feed": 0.65,  # y\n}\n';
  const s1 = insertSnapshotRow(snap, "OLD_CATEGORIES", '    "sgb_blocklist": "threat",   # 2026-11-21 fleet lift(#366)');
  assert.ok(s1.includes('"mirage_feed": "threat",  # x\n    "sgb_blocklist": "threat"'));
  assert.equal(insertSnapshotRow(s1, "OLD_CATEGORIES", '    "sgb_blocklist": "threat",   # 2026-11-21 fleet lift(#366)'), s1, "已在=幂等");
  assert.throws(() => insertSnapshotRow(snap, "OLD_ABSENT", "x"), /快照块缺席/);
});

test("changelogEntries/composePrBody:双语对+轮四行数入文", () => {
  const dossier = { name: "gorkemgun/sgb-blocklist", url: "https://github.com/gorkemgun/sgb-blocklist", format: "plain text 行式 IP 清单", auth: "无鉴权直下", cadence: "每日更新", samples: ["1.2.3.4"], field_routing: ["每行 IP → CORE_FIELDS"] };
  const stats = { model_calls: 38, totalTokens: 675325, cost: 0.26821784, wall_s: 355.2 };
  const e = changelogEntries({ source: "sgb_blocklist", dossier, roundId: "2026-11-21-0900-add", stats, prNumber: "374" });
  assert.ok(e.zh.includes("威胁源接入:sgb_blocklist"));
  assert.ok(e.zh.includes("模型调用 38 / 总 tokens 675325 / 花费 ¥0.26821784 / 墙钟 355.2s"));
  assert.ok(e.en.includes("Threat-feed add: sgb_blocklist"));
  const body = composePrBody({ source: "sgb_blocklist", roundId: "2026-11-21-0900-add", dossier, stats, gates: [{ name: "backend 全量 pytest", pass: true }], rosterTotal: { before: 63, after: 64 }, universe: { before: 35, after: 36 }, split: { before: 55, after: 56 }, seats: 14 });
  assert.ok(body.includes("# add/sgb_blocklist — M5 fleet 自动 lift(#366)"));
  assert.ok(body.includes("universe 35→36"));
  assert.ok(body.includes("轮四行数"));
});

test("roundStemOf:registry 名真源=a3-implement.json 的 stem(卡 id≠stem 判例 2026-11-20-2210:卡 sgb_blocklist/registry gorkemgun_sgb_blocklist)", () => {
  const mk = (dir, stem) => { fs.mkdirSync(dir, { recursive: true }); if (stem === null) fs.writeFileSync(path.join(dir, "a3-implement.json"), "{}"); else fs.writeFileSync(path.join(dir, "a3-implement.json"), JSON.stringify({ stem })); };
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "fleet-a3-"));
  mk(path.join(tmp, "ok"), "gorkemgun_sgb_blocklist");
  mk(path.join(tmp, "missing"), null);
  mk(path.join(tmp, "bad"), "Bad-Name!");
  assert.equal(roundStemOf(path.join(tmp, "ok")), "gorkemgun_sgb_blocklist");
  assert.equal(roundStemOf(path.join(tmp, "missing")), null);
  assert.equal(roundStemOf(path.join(tmp, "bad")), null);
  assert.equal(roundStemOf(path.join(tmp, "absent")), null);
  // 真轮工件只读回归:2026-11-20-2210-add 实测 stem(轮工件在主检出 docs/ops/rounds/,worktree 无 docs)
  assert.equal(roundStemOf(path.resolve(REPO, "..", "..", "docs", "ops", "rounds", "2026-11-20-2210-add")), "gorkemgun_sgb_blocklist");
});

// ── lift 文本变换:真仓件只读回归钉(钉面漂移先红在此,非真跑轮时)──
test("真仓件钉面:六计数面+劈分八钉+critic 针+冒烟计数,全部恰一命中可变换(只读)", () => {
  assert.match(bumpReadmeCount(read("README.md")), /Pull \d+ public sources/);
  bumpReadmeZhCount(read("README.zh-CN.md"));
  bumpManualCounts(read("MANUAL.md"), { keyless: true });
  bumpManualImageAlt(read("MANUAL.md"));
  bumpManualZhCounts(read("MANUAL.zh-CN.md"), { keyless: true });
  const splitMeta = JSON.parse(read("ops/agent-v2/bench/rrsi-domain/data/split.jsonl").split("\n")[0]);
  syncRrsiSplitPins(read("ops/agent-v2/tests/rrsi-split.test.mjs"), { evolve: splitMeta.evolve, heldout: splitMeta.heldout, total: splitMeta.total, rosterTotal: splitMeta.rosterTotal, exempt: splitMeta.exemptTotal, tag: "test" });
  syncRrsiDomainPin(read("ops/agent-v2/tests/rrsi-domain.test.mjs"), { total: splitMeta.total, tag: "test" });
  const rosterPin = read("backend/tests/sources/test_b_family_url_filename_guard.py").match(/assert len\(sources\) == (\d+)/);
  assert.ok(rosterPin, "发现冒烟计数钉在场");
  bumpDiscoverySmokePin(read("backend/tests/sources/test_b_family_url_filename_guard.py"), { total: Number(rosterPin[1]) + 1, source: "x_test", tag: "test" });
  insertSnapshotRow(read("backend/tests/core/test_metadata_derivation.py"), "OLD_CATEGORIES", '    "fleet_test_never": "threat",   # test');
});

// ── CLI 面(spawn 真入口;世界=临时件,不碰真 docs/dev)──
function cli(args, extraEnv = {}) {
  return new Promise((resolve) => {
    const p = spawn("node", [path.join(HERE, "..", "run-fleet.mjs"), ...args], { env: { ...process.env, ...extraEnv }, cwd: path.resolve(HERE, "..") });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => resolve({ code, out, err }));
  });
}
const lastLine = (s) => s.trimEnd().split("\n").at(-1);

test("CLI 无源空转:exit 0,信封 idle,零模型调用(无 --model 也过)", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "fleet-cli-"));
  try {
    fs.writeFileSync(path.join(tmp, "queue.md"), Q([propose("only_propose")]));
    const r = await cli(["--once", "--queue", path.join(tmp, "queue.md"), "--rounds", path.join(tmp, "rounds"), "--dev-root", path.join(tmp, "dev"), "--sandbox-home", path.join(tmp, "wt")]);
    assert.equal(r.code, 0, `stderr:\n${r.err}`);
    const env = JSON.parse(lastLine(r.out));
    assert.equal(env.ok, true); assert.equal(env.idle, true); assert.equal(env.picked, null);
    assert.match(r.err, /零模型调用/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("CLI 队列缺席:exit 3,信封 infra;有源缺 --model:exit 2", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "fleet-cli-"));
  try {
    const r1 = await cli(["--queue", path.join(tmp, "absent-queue.md"), "--rounds", path.join(tmp, "r"), "--dev-root", path.join(tmp, "d"), "--sandbox-home", path.join(tmp, "w")]);
    assert.equal(r1.code, 3);
    assert.equal(JSON.parse(lastLine(r1.out)).error.code, "infra");
    fs.writeFileSync(path.join(tmp, "queue.md"), Q([approve("sgb_blocklist")]));
    const r2 = await cli(["--queue", path.join(tmp, "queue.md"), "--rounds", path.join(tmp, "r"), "--dev-root", path.join(tmp, "d"), "--sandbox-home", path.join(tmp, "w")]);
    assert.equal(r2.code, 2, `stderr:\n${r2.err}`);
    assert.match(r2.err, /--model\/OPS_MODEL_FLEET/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
