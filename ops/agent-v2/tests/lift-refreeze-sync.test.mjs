// lift-refreeze-sync.test.mjs — #440:lift 重冻之后自动同步基准说明纯数字(裁定 2026-11-24「lift 自动同步纯数字」)。
// 面三条:add-lift.mjs 新增 syncGenSplitDefaults(gen-split.mjs 缺省席位 + --help 文案 + 头注用法行)与
// syncRrsiDocFirstSentence(rrsi.json _doc 首句「N 题 = M 源 − K 免考,E 演化 / H 留出」);runLift 在重冻
// (第 4 步)之后、三道门之前经 4b 步接线。钉:_doc 首句(首个「。」)之后一个字不动——粒度数字与
// 「约 2 题增益才算真增益」理由句是人写的说明,#440 留人工(lift 输出明写提醒);同步面全部 sub1 恰一命中
// fail-closed,形状不对=红停下不静默。写文件次序由 edit() 保证(fn 先算、抛错则 writeFileSync 不达),
// 源码文本钉见 runLift 接线条。写法照 rrsi-split.test.mjs / rrsi-domain.test.mjs(合成面钉行为 +
// 真仓件只读回归钉钉面在场:钉面漂移=先红在此,不是真跑轮时)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { syncGenSplitDefaults, syncRrsiDocFirstSentence } from "../add-lift.mjs";

const REPO = fs.realpathSync(new URL("../../..", import.meta.url).pathname);
const read = (p) => fs.readFileSync(`${REPO}/${p}`, "utf8");

// ── 合成面:数字跟新冻结件 meta 走;_doc 首句之后逐字不变;钉面漂移=红 ──
test("syncGenSplitDefaults(#440):缺省席位/--help 文案/头注用法行三处跟新 meta 走;钉面漂移=红", () => {
  const gen = [
    "// gen-split.mjs — fixture(用法注释行)",
    "function parseArgs(argv) {",
    "  const out = { rosterFile: null, examRules: null, out: null, evolve: 48, heldout: 15, seed: DEFAULT_SEED };",
    '    console.error("用法:node gen-split.mjs --roster-file <dump> [--exam-rules PATH] [--out PATH] [--evolve 48] [--heldout 15] [--seed 20261108]");',
    "}",
    "//                      [--evolve 48] [--heldout 15] [--seed 20261108](缺省=现冻结件 meta,#437)",
  ].join("\n");
  const out = syncGenSplitDefaults(gen, { evolve: 49, heldout: 15 });
  assert.ok(out.includes("evolve: 49, heldout: 15, seed: DEFAULT_SEED"), "缺省席位跟新 meta");
  assert.ok(out.includes("用法:node gen-split.mjs --roster-file <dump> [--exam-rules PATH] [--out PATH] [--evolve 49] [--heldout 15] [--seed 20261108]"), "--help 文案跟新 meta");
  assert.ok(out.includes("//                      [--evolve 49] [--heldout 15] [--seed 20261108]"), "头注用法行跟新 meta(「缺省=现冻结件 meta」的说法不许留旧数)");
  assert.ok(!out.includes("48"), "旧席位数清零");
  // 钉面漂移:锚点缺席(0 命中)与多命中都红(fail-closed,不静默跳过、不乱改)
  assert.throws(() => syncGenSplitDefaults(gen.replace("seed: DEFAULT_SEED", "seed: OTHER"), { evolve: 49, heldout: 15 }), /钉面漂移.*gen-split\.mjs 缺省席位/, "缺省席位行改版=红");
  assert.throws(() => syncGenSplitDefaults(gen.replace("--out PATH] [--evolve", "--out FILE] [--evolve"), { evolve: 49, heldout: 15 }), /钉面漂移.*--help/, "--help 文案改版=红");
  assert.throws(() => syncGenSplitDefaults(gen.replace("//                      [--evolve", "#                      [--evolve"), { evolve: 49, heldout: 15 }), /钉面漂移.*头注用法行/, "头注用法行改版=红");
  assert.throws(() => syncGenSplitDefaults(`${gen}\n${gen.split("\n")[2]}`, { evolve: 49, heldout: 15 }), /钉面漂移.*期望恰 1 处命中,实 2/, "缺省席位行多命中=红");
});

test("syncRrsiDocFirstSentence(#440):_doc 首句数字串跟新 meta 走,首句之后逐字不变;句式改版=红", () => {
  const docHead = "ipradar 域:#322 RRSI 盲测演化(64 题 = 72 源 − 8 免考,49 演化 / 15 留出,冻结在 data/split.jsonl;2099-01-01 按冻结件核对)。";
  const docTail = "S = 逐源 0/1 召回率(四层匹配,score.mjs 机械派生)。delta 手设 0.05。现冻结件下:64 题全幅 1 题≈0.016、49 题演化集 1 题≈0.020,0.05≈演化面 2.4 题的召回粒度——口径不变:约 2 题增益才算真增益。";
  const doc = `{\n  "_doc": "${docHead}${docTail}",\n  "T": 25\n}\n`;
  const out = syncRrsiDocFirstSentence(doc, { total: 65, rosterTotal: 73, exempt: 8, evolve: 50, heldout: 15 });
  assert.ok(out.includes("65 题 = 73 源 − 8 免考,50 演化 / 15 留出"), "首句「N 题 = M 源 − K 免考,E 演化 / H 留出」跟新 meta(免考后逗号=ASCII 半角,同 rrsi.json 现形)");
  assert.ok(!out.includes("64 题 = 72 源"), "旧数字串清零");
  // 首句边界=首个「。」(tests/rrsi-domain.test.mjs「超参钉死」同口径):之后粒度数字与理由句逐字不变
  assert.equal(out.slice(out.indexOf("。")), doc.slice(doc.indexOf("。")), "_doc 首句之后逐字不变(粒度数字与理由句是人写的说明,#440 留人工)");
  assert.equal(out.slice(0, out.indexOf("。")), doc.slice(0, doc.indexOf("。")).replace("64 题 = 72 源 − 8 免考,49 演化 / 15 留出", "65 题 = 73 源 − 8 免考,50 演化 / 15 留出"), "首句内除数字串外其余文字(含核对日期)也不动");
  assert.throws(() => syncRrsiDocFirstSentence(doc.replace("64 题 = 72 源 − 8 免考,49 演化 / 15 留出", "共 64 题"), { total: 65, rosterTotal: 73, exempt: 8, evolve: 50, heldout: 15 }), /钉面漂移.*_doc 首句/, "首句句式改版=红(不静默跳过)");
});

// ── 真仓件只读回归钉(钉面漂移先红在此,非真跑轮时)──
test("真仓件钉面(#440):gen-split.mjs 三处席位面与 rrsi.json _doc 首句在现冻结件 meta 下可同步;同值幂等(只读)", () => {
  const meta = JSON.parse(read("ops/agent-v2/bench/rrsi-domain/data/split.jsonl").split("\n")[0]);
  const genSrc = read("ops/agent-v2/bench/rrsi-domain/gen-split.mjs");
  const genOut = syncGenSplitDefaults(genSrc, { evolve: meta.evolve + 1, heldout: meta.heldout });
  assert.ok(genOut.includes(`evolve: ${meta.evolve + 1}, heldout: ${meta.heldout}, seed: DEFAULT_SEED`), "真 gen-split 缺省席位面在场");
  assert.ok(genOut.includes(`[--evolve ${meta.evolve + 1}] [--heldout ${meta.heldout}]`), "真 gen-split --help/头注面在场");
  const docSrc = read("ops/agent-v2/bench/rrsi-domain/rrsi.json");
  const docOut = syncRrsiDocFirstSentence(docSrc, { total: meta.total + 1, rosterTotal: meta.rosterTotal + 1, exempt: meta.exemptTotal, evolve: meta.evolve + 1, heldout: meta.heldout });
  assert.ok(docOut.includes(`${meta.total + 1} 题 = ${meta.rosterTotal + 1} 源 − ${meta.exemptTotal} 免考,${meta.evolve + 1} 演化 / ${meta.heldout} 留出`), "真 rrsi.json _doc 首句面在场");
  assert.equal(docOut.slice(docOut.indexOf("。")), docSrc.slice(docSrc.indexOf("。")), "真文件同样首句之后逐字不变");
  // 同值幂等:现值喂回=字节原样(重冻后同值重跑不产生噪声 diff)
  assert.equal(syncGenSplitDefaults(genSrc, { evolve: meta.evolve, heldout: meta.heldout }), genSrc);
  assert.equal(syncRrsiDocFirstSentence(docSrc, { total: meta.total, rosterTotal: meta.rosterTotal, exempt: meta.exemptTotal, evolve: meta.evolve, heldout: meta.heldout }), docSrc);
});

// ── runLift 接线源码文本钉(同步步骤内联在 runLift,无纯函数面,#437「内联模板钉源码文本」同律)──
test("runLift 接线(#440):4b 步两处 edit + 人工项提醒在场;第 7 步注释按新行为改写;edit 抛错不落盘", () => {
  const src = read("ops/agent-v2/add-lift.mjs");
  assert.ok(src.includes('edit("ops/agent-v2/bench/rrsi-domain/gen-split.mjs", (t) => syncGenSplitDefaults(t,'), "gen-split 缺省席位同步接线(第 4b 步)");
  assert.ok(src.includes('edit("ops/agent-v2/bench/rrsi-domain/rrsi.json", (t) => syncRrsiDocFirstSentence(t,'), "rrsi.json 说明首句同步接线(第 4b 步)");
  assert.ok(src.includes("4b. 基准说明纯数字同步"), "接线在重冻(第 4 步)之后");
  assert.ok(src.includes("[lift] 人工项:rrsi.json _doc 首句之后粒度和理由句请人工核对(#440)"), "人工项提醒(lift 输出明写)");
  assert.ok(!src.includes("要不要让 lift 自动同步这两处"), "第 7 步旧注释(待决问题)已删");
  assert.ok(src.includes("已由第 4b 步机械同步"), "第 7 步注释写明纯数字已自动同步,人工项只剩理由句");
  // edit() 的写文件次序(fn 先算完才 writeFileSync)保证同步函数抛错时文件不写=「报错并停下(不写文件)」
  assert.ok(src.includes('fs.writeFileSync(p, fn(fs.readFileSync(p, "utf8")));'), "edit() 先变换后落盘:抛错=不写");
});
