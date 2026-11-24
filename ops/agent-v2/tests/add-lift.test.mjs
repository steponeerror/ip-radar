// add-lift.test.mjs — 手动加源 lift 工具链纯函数面 + CLI 用法面(#375 封存件;lift 测试自
// fleet.test.mjs 逐字节迁移,驱动器单测——队列轮询/完成判据/状态机/CLI 空转/lark 稿——随
// run-fleet.mjs 退役删除)。
// 覆盖:lift 文本变换(文档三件计数钉/README 表行/rrsi 劈分钉/critic 针数钉/发现冒烟计数钉/
// roster 快照行幂等)——全部「恰一命中」fail-closed;变换同时拿真仓件做只读回归钉(钉面漂移=
// 先红在此,不是真跑轮时)。#437 两条:①钉注同步保留原出处注、只追加「<日期> 再冻结」;②lift 是
// 手动流程(#375 起 fleet 驱动器退役),模板措辞不写退役词与「自动 lift」——纯函数面钉输出,
// runLift 内联模板(无纯函数面)钉源码文本。CLI 面:无参 usage 退出码 2;--help 可跑(usage() 律:
// 同 run-fleet 惯例 --help 与用法错同码);--source/--round-id 形状执法。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";
import {
  bumpReadmeCount, bumpReadmeZhCount, bumpManualCounts, bumpManualImageAlt, bumpManualZhCounts,
  insertReadmeRow, syncRrsiSplitPins, syncRrsiDomainPin, bumpDiscoverySmokePin, insertSnapshotRow,
  changelogEntries, composePrBody, roundStemOf, setFrozenFlag,
} from "../add-lift.mjs";
import { mainCheckoutRoot } from "../bench/leak-check.mjs";

const HERE = import.meta.dirname;
const REPO = path.resolve(HERE, "..", "..", "..");
const read = (p) => fs.readFileSync(path.join(REPO, p), "utf8");

// ── lift 文本变换:合成面 ──
test("bump* 计数钉:四文档六面 +1(keyless 条件面);漂移=红", () => {
  assert.equal(bumpReadmeCount("**Pull 63 public sources into your own box.**"), "**Pull 64 public sources into your own box.**");
  assert.equal(bumpReadmeZhCount("把 60 个公开情报源搬回家:查任何 IP"), "把 61 个公开情报源搬回家:查任何 IP");
  const manual = "On first start it downloads and builds every keyless feed (56 of the 63 sources) into millions of records.";
  assert.equal(bumpManualCounts(manual, { keyless: true }), "On first start it downloads and builds every keyless feed (57 of the 64 sources) into millions of records.");
  assert.equal(bumpManualCounts(manual, { keyless: false }), "On first start it downloads and builds every keyless feed (56 of the 64 sources) into millions of records.");
  assert.equal(bumpManualImageAlt("![tab: 64 sources (63 public + 1 private honeypot), health]"), "![tab: 65 sources (64 public + 1 private honeypot), health]");
  const zhManual = "首次启动会把全部无 key 源（60 个源中的 53 个）下载。\n![Sources tab:61 源（60 公开 + 1 私有蜜罐）、健康]";
  const bumped = bumpManualZhCounts(zhManual, { keyless: true });
  assert.ok(bumped.includes("（61 个源中的 54 个）"));
  assert.ok(bumped.includes("62 源（61 公开 + 1 私有蜜罐）"), "frost 面全角括号形(e6e2ac96)后钉随全角");
  assert.throws(() => bumpReadmeCount("无钉面文本"), /钉面漂移.*期望恰 1/);
});

test("insertReadmeRow:节内表尾插行;节缺席/无表=红", () => {
  const md = ["intro", "", "### Threat Reputation", "", "| Source | Provider | Contributes | 🔑 |", "|---|---|---|---|", "| mirage_feed | [m](u) | desc | |", "", "### Geo & ASN", "", "| Source | Provider | |", "| a | b | |", ""].join("\n");
  const out = insertReadmeRow(md, "Threat Reputation", "| sgb_blocklist | [g](u) | fleet | |");
  assert.ok(out.includes("| mirage_feed | [m](u) | desc | |\n| sgb_blocklist | [g](u) | fleet | |"));
  assert.ok(!out.includes("| a | b | |\n| sgb_blocklist"), "geo 节不动");
  assert.throws(() => insertReadmeRow(md, "No Such Section", "x"), /README 节缺席/);
});

test("syncRrsiSplitPins/syncRrsiDomainPin:八钉一针全同步,注记保留+追加;漂移=红", () => {
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
  assert.ok(out.includes('assert.equal(rows.length, 56, "考题总数 = 56(64 源 − 8 免考;2026-11-18 #359/#360 再冻结;2026-11-21 再冻结)");'), "rows.length 钉:原注记留,新「<日期> 再冻结」追加其后(#437)");
  assert.ok(out.includes("assert.equal(new Set(names).size, 56"));
  assert.ok(out.includes("assert.equal(exam.length, 56, `真 roster 考题数漂移:${exam.length} ≠ 56——冻结名单须重裁(2026-11-18 #359/#360 再冻结 53→55;2026-11-21 再冻结)`);"), "exam.length 钉:原注记留(含 53→55 的出处尾巴),新日期追加其后(#437)");
  assert.throws(() => syncRrsiSplitPins(split.replace("考题总数", "总数"), { evolve: 42, heldout: 14, total: 56, rosterTotal: 64, exempt: 8, tag: "x" }), /钉面漂移/, "钉面措辞改版=红(数字变化不红——同步语义)");
  const dom = '  assert.equal(criticProbe.total, 55, "每考题一行一针(55 行;2026-11-18 再冻结)");';
  assert.equal(syncRrsiDomainPin(dom, { total: 56, tag: "2026-11-21" }), '  assert.equal(criticProbe.total, 56, "每考题一行一针(56 行;2026-11-18 再冻结;2026-11-21 再冻结)");');
});

// #437:三条注记正则原为整段重写(「免考;」「行;」之后的 [^"]* / [^`]* 全换成「<日期> 再冻结」),
// 下次 lift 会把 #414 留在钉注里的出处(撤源/进源明细)吃掉——出处是「冻结为什么变成这个数」的
// 仅存记录。改后=原注记原样留、新「<tag> 再冻结」追加其后。拿真仓件只读回归:真钉注里的 #414
// 出处原文从文件里现取(测试里不抄源名),过一遍变换仍在;再过一遍=两条日期注记按先后序并存。
test("syncRrsiSplitPins/syncRrsiDomainPin 保留出处注(#437):真钉注里的 #414 出处过一遍变换仍在,新日期追加其后;连冻两次按序并存", () => {
  const src = read("ops/agent-v2/tests/rrsi-split.test.mjs");
  const domSrc = read("ops/agent-v2/tests/rrsi-domain.test.mjs");
  const meta = JSON.parse(read("ops/agent-v2/bench/rrsi-domain/data/split.jsonl").split("\n")[0]);
  const grab = (text, re, what) => { const m = text.match(re); assert.ok(m, `钉注缺席:${what}`); return m[1]; };
  const oldRows = grab(src, /考题总数 = \d+\(\d+ 源 − \d+ 免考;([^")]*)\)"\);/, "rows.length 钉");
  const oldExam = grab(src, /冻结名单须重裁\(([^`]*)([)])`\);/, "exam.length 钉");
  const oldCritic = grab(domSrc, /每考题一行一针\(\d+ 行;([^")]*)\)"\);/, "critic 针数钉");
  assert.ok(!/再冻结;/.test(oldRows + oldExam + oldCritic), "前提:现钉注尚无追加形(否则本测前提漂移,须重读夹具)");
  const lift = (text, tag, d) => syncRrsiSplitPins(text, { evolve: meta.evolve + d, heldout: meta.heldout, total: meta.total + d, rosterTotal: meta.rosterTotal + d, exempt: meta.exemptTotal, tag });
  const out = lift(src, "2099-01-01", 1);
  assert.ok(out.includes(`免考;${oldRows};2099-01-01 再冻结)`), "rows.length 钉:原出处注须保留,新日期追加其后");
  assert.ok(out.includes(`冻结名单须重裁(${oldExam};2099-01-01 再冻结)`), "exam.length 钉:原注记须保留,新日期追加其后");
  const out2 = lift(out, "2099-01-02", 2);
  assert.ok(out2.includes(`免考;${oldRows};2099-01-01 再冻结;2099-01-02 再冻结)`), "连冻两次:两条日期注记按先后序并存");
  const dom = syncRrsiDomainPin(domSrc, { total: meta.total + 1, tag: "2099-01-01" });
  assert.ok(dom.includes(`每考题一行一针(${meta.total + 1} 行;${oldCritic};2099-01-01 再冻结)`), "critic 针数钉:原注记须保留,新日期追加其后");
});

test("bumpDiscoverySmokePin:计数+注记追加;insertSnapshotRow:插入+已在幂等", () => {
  const py = 'def test_discovery_smoke_all_real_sources(tmp_path: Path):\n    assert len(sources) == 63          # 本票时点 roster;增删源时同步(2026-11-18 mirage_feed #359 + honeypot_fyi #360 接入 61→63)\n';
  const out = bumpDiscoverySmokePin(py, { total: 64, source: "sgb_blocklist", tag: "2026-11-21" });
  assert.ok(out.includes("assert len(sources) == 64"));
  assert.ok(out.includes("接入 63→64)"));
  assert.ok(out.includes("接入 61→63 + 2026-11-21 手动 lift sgb_blocklist 接入 63→64)"), "注记:原注记留,追加段落在同一对括号内「<日期> 手动 lift <源> 接入 n→N」(#437)");
  assert.ok(!out.includes("fleet"), "手动 lift 的钉注不写退役词 fleet(#437)");
  const snap = 'OLD_CATEGORIES = {\n    "mirage_feed": "threat",  # x\n}\nOLD_RELIABILITY = {\n    "mirage_feed": 0.65,  # y\n}\n';
  const s1 = insertSnapshotRow(snap, "OLD_CATEGORIES", '    "sgb_blocklist": "threat",   # 2026-11-21 手动 lift'); // 行形照 runLift 快照行模板(#437)
  assert.ok(s1.includes('"mirage_feed": "threat",  # x\n    "sgb_blocklist": "threat"'));
  assert.equal(insertSnapshotRow(s1, "OLD_CATEGORIES", '    "sgb_blocklist": "threat",   # 2026-11-21 手动 lift'), s1, "已在=幂等");
  assert.throws(() => insertSnapshotRow(snap, "OLD_ABSENT", "x"), /快照块缺席/);
});

test("changelogEntries/composePrBody:双语对+轮四行数入文;手动 lift 措辞不写退役词与「自动」(#437)", () => {
  const dossier = { name: "gorkemgun/sgb-blocklist", url: "https://github.com/gorkemgun/sgb-blocklist", format: "plain text 行式 IP 清单", auth: "无鉴权直下", cadence: "每日更新", samples: ["1.2.3.4"], field_routing: ["每行 IP → CORE_FIELDS"] };
  const stats = { model_calls: 38, totalTokens: 675325, cost: 0.26821784, wall_s: 355.2 };
  const e = changelogEntries({ source: "sgb_blocklist", dossier, roundId: "2026-11-21-0900-add", stats, prNumber: "374" });
  assert.ok(e.zh.includes("威胁源接入:sgb_blocklist(gorkemgun/sgb-blocklist;手动 lift,加源轮 2026-11-21-0900-add,draft PR #374)"), "zh 条目标题:手动 lift + 加源轮 id");
  assert.ok(e.zh.includes("模型调用 38 / 总 tokens 675325 / 花费 ¥0.26821784 / 墙钟 355.2s"));
  assert.ok(e.zh.includes("加源轮全相位绿后手动 lift(#375 起 fleet 驱动器退役,由人跑 add-lift.mjs)"), "zh 正文:谁触发如实(#375 起驱动器退役,由人跑)");
  assert.ok(e.zh.includes("合并人裁(加源轮产出永不自并入 master)。本条目由脚本生成,合并前人面可润色。"), "合并人裁不变;「脚本生成,可润色」之意保留");
  assert.ok(!/自动/.test(e.zh), "zh 条目不得再写「自动 lift」(手动流程)");
  assert.ok(e.en.includes("Threat-feed add: sgb_blocklist (gorkemgun/sgb-blocklist; manual lift, add-round 2026-11-21-0900-add, draft PR #374)"), "en 条目标题:manual lift + add-round");
  assert.ok(e.en.includes("lifted manually after a fully green add-round (the fleet driver was retired in #375; a human runs add-lift.mjs)"), "en 正文:谁触发如实");
  assert.ok(e.en.includes("merge is a human ruling (add-round output never self-merges into master). This entry is script-generated; polish before merging is welcome."), "合并人裁不变;「脚本生成,可润色」之意保留");
  assert.ok(!/automatically|auto-lift/.test(e.en), "en 条目不得再写「自动 lift」(手动流程)");
  const body = composePrBody({ source: "sgb_blocklist", roundId: "2026-11-21-0900-add", dossier, stats, gates: [{ name: "backend 全量 pytest", pass: true }], rosterTotal: { before: 63, after: 64 }, universe: { before: 35, after: 36 }, split: { before: 55, after: 56 }, seats: 14 });
  assert.ok(body.includes("# add/sgb_blocklist — 手动 lift(加源轮 2026-11-21-0900-add;#375 起 fleet 驱动器退役,由人跑 add-lift.mjs)"), "PR 标题行:手动 lift");
  assert.ok(body.includes("合并人裁(加源轮产出永不自并入 master;#366 语义)。"), "合并人裁不变");
  assert.ok(body.includes("_本 PR 由人跑 add-lift.mjs 手动开出;CHANGELOG 条目由脚本生成,合并前可润色。_"), "PR 脚注:谁开出如实;「脚本生成,可润色」之意保留");
  assert.ok(!/自动|M5 fleet/.test(body), "PR 正文不得再写「自动 lift」");
  assert.ok(body.includes("universe 35→36"));
  assert.ok(body.includes("轮四行数"));
});

// #437:runLift 内联模板没有纯函数面(README 源表行 Contributes 列/快照行注/提交身份与说明/日志前缀),
// 以源码文本钉:#375 起 lift 是手动流程,下列退役写法任一回潮=下次手动 lift 把退役词或「自动 lift」的
// 不实说法写回仓。标识符(fleetRoot/FLEET_DEV_ROOT/.fleet-roster-dump.txt/dev/fleet)与史述注释不在表内。
test("lift 内联模板不写退役词(#437):README 行只写格式/快照行注「手动 lift」/提交身份=执行者/日志前缀 [lift]", () => {
  const src = read("ops/agent-v2/add-lift.mjs");
  for (const stale of ["(fleet-lifted #366)", "fleet lift(#366)", "fleet #366 lift", "[fleet-lift]", "fleet@ipradar.local", "fleet-driver", ";fleet ${roundId}"]) {
    assert.ok(!src.includes(stale), `退役写法仍在 add-lift.mjs:${stale}`);
  }
  assert.ok(src.includes("const contributes = clip(dossier.format, 90);"), "README 源表行 Contributes 列只写格式,不带来源标签");
  assert.ok(src.includes('`    "${stem}": "${meta.category}",   # ${tag} 手动 lift`'), "快照行注=「<日期> 手动 lift」(OLD_CATEGORIES)");
  assert.ok(src.includes('`    "${stem}": ${meta.reliability},   # ${tag} 手动 lift`'), "快照行注=「<日期> 手动 lift」(OLD_RELIABILITY)");
  assert.ok(src.includes("[lift]"), "日志前缀=[lift]");
  assert.ok(src.includes('"-c", "commit.gpgsign=false"'), "commit.gpgsign=false 保留");
  assert.ok(!src.includes("user.email=") && !src.includes("user.name="), "提交身份=执行者自己的 git 身份,不写死驱动器身份");
  assert.ok(src.includes(";加源轮 ${roundId})`"), "提交说明:轮 id 以「加源轮」引出");
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
});

// 真轮工件只读回归(合成面之外的第二条腿):2026-11-20-2210-add 实测 stem。轮工件在主检出的嵌套
// docs 仓 docs/ops/rounds/;CI checkout 没有 → 显式 skip(rrsi-split 的 SKIP_ROSTER、
// test_precedent_schema.py 同口径:供给缺席不假红,也不算绿)。
// 锚=mainCheckoutRoot(#337 判例,同 add-liveness.test.mjs 算式):REPO/../../ 只在 .worktrees/<名>
// 布局成立,主检出自身=退化同根。
const REAL_ADD_ROUND = path.resolve(mainCheckoutRoot(REPO) ?? REPO, "docs", "ops", "rounds", "2026-11-20-2210-add");
test("roundStemOf 真轮工件只读回归:2026-11-20-2210-add 的 a3-implement.json stem = gorkemgun_sgb_blocklist", {
  skip: fs.existsSync(path.join(REAL_ADD_ROUND, "a3-implement.json")) ? false : `嵌套 docs 仓缺席:${REAL_ADD_ROUND} 无 a3-implement.json`,
}, () => {
  assert.equal(roundStemOf(REAL_ADD_ROUND), "gorkemgun_sgb_blocklist");
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

test("setFrozenFlag:入仓带空格形与生成器紧凑形都认;幂等;缺键时冻结=插键(2026-11-20-2210 轮判例:gen-universe 重生成件是紧凑形 \"frozen\":false,带空格搜索扑空)", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "fleet-frozen-"));
  const mk = (first) => { const f = path.join(tmp, `u${Math.random().toString(36).slice(2)}.jsonl`); fs.writeFileSync(f, first + "\nrow1\nrow2\n"); return f; };
  // 入仓形(带空格):解冻→复冻
  const spaced = mk('{"kind": "ipradar-add-universe", "total": 35, "frozen": true}');
  setFrozenFlag(spaced, false);
  assert.ok(fs.readFileSync(spaced, "utf8").split("\n")[0].includes('"frozen": false'));
  setFrozenFlag(spaced, true);
  assert.ok(fs.readFileSync(spaced, "utf8").split("\n")[0].includes('"frozen": true'));
  // 生成器形(紧凑):冻结
  const compact = mk('{"kind":"ipradar-add-universe","total":36,"frozen":false}');
  setFrozenFlag(compact, true);
  const head = fs.readFileSync(compact, "utf8").split("\n")[0];
  assert.ok(head.includes('"frozen": true') && JSON.parse(head).frozen === true);
  assert.ok(!head.includes('"frozen":false'));
  // 幂等:同值再调不变
  const before = fs.readFileSync(compact, "utf8");
  setFrozenFlag(compact, true);
  assert.equal(fs.readFileSync(compact, "utf8"), before);
  // 缺键:value=false 无操作;value=true 插键
  const nokey = mk('{"kind":"ipradar-add-universe","total":36}');
  setFrozenFlag(nokey, false);
  assert.equal(fs.readFileSync(nokey, "utf8").split("\n")[0], '{"kind":"ipradar-add-universe","total":36}');
  setFrozenFlag(nokey, true);
  assert.equal(JSON.parse(fs.readFileSync(nokey, "utf8").split("\n")[0]).frozen, true);
});

// ── CLI 面(spawn 真入口;只打用法执法面,真 lift 链冒烟由 #375 收口人跑)──
function cli(args) {
  return new Promise((resolve) => {
    const p = spawn("node", [path.join(HERE, "..", "add-lift.mjs"), ...args], { cwd: path.resolve(HERE, "..") });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => resolve({ code, out, err }));
  });
}

test("CLI 用法面:无参/--help=usage 退出码 2;--source/--round-id 形状执法;缺参必填执法", async () => {
  const r0 = await cli([]);
  assert.equal(r0.code, 2, `stderr:\n${r0.err}`);
  assert.match(r0.err, /用法:node add-lift\.mjs --sandbox <dir> --source <slug>/);
  assert.match(r0.err, /--sandbox\/--source 与 --round-id\(或 --round-dir\)必填/);
  const r1 = await cli(["--help"]);
  assert.equal(r1.code, 2, "usage() 律随迁:--help 与用法错同码(run-fleet 惯例)");
  assert.match(r1.err, /用法:node add-lift\.mjs/);
  const r2 = await cli(["--sandbox", "/tmp/x", "--source", "Bad-Name!", "--round-id", "2026-11-21-0900-add"]);
  assert.equal(r2.code, 2);
  assert.match(r2.err, /--source 形状坏/);
  const r3 = await cli(["--sandbox", "/tmp/x", "--source", "x_feed", "--round-id", "bad-id"]);
  assert.equal(r3.code, 2);
  assert.match(r3.err, /--round-id 形状坏/);
  const r4 = await cli(["--sandbox", "/tmp/x", "--source", "x_feed"]);
  assert.equal(r4.code, 2, "--round-id/--round-dir 二选一必填");
  assert.match(r4.err, /必填/);
});
