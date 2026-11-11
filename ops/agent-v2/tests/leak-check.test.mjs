// leak-check.test.mjs — 票 #321(重发现基准票 D):leak gate 红绿面(spec §3.4/Q5/Q8)。
// 门语义:基准面文本出现 roster 源名(名字归一化形式)或其下载域名即红;行级豁免标记
// 「禁词引用:…」放行该行(同主仓 pre-commit 禁词钩子 #308 判例);免考(download_host='-')
// 源名同样红——免考≠可以写进提示词(票面明示)。fixture 全走临时目录;roster 经
// rosterFile 注入,测试面零 python 依赖(CI 供不起解释器与 backend 依赖)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { runLeakCheck } from "../bench/leak-check.mjs";

// fixture roster:6 源 = 名字归一化对(blocklist_de)+ 共享 host 双记(otx/otx_subscribed)
// + 三段域名去 www(binarydefense)+ 免考一员(honyport,host='-')。
const FIXTURE_ROSTER = [
  "blocklist_de | threat | lists.blocklist.de | is_malicious",
  "binarydefense | threat | www.binarydefense.com | is_malicious",
  "danmeuk_tor | asset | www.dan.me.uk | is_tor",
  "otx | threat | otx.alienvault.com | is_malicious",
  "otx_subscribed | threat | otx.alienvault.com | is_malicious",
  "honyport | threat | - | is_malicious",
].join("\n");

function tmpFixture(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "leak-check-"));
  for (const [name, content] of Object.entries(files))
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true }),
      fs.writeFileSync(path.join(dir, name), content);
  return dir;
}

function check(files, rosterText = FIXTURE_ROSTER) {
  const dir = tmpFixture(files);
  const rosterFile = path.join(dir, "roster.txt");
  fs.writeFileSync(rosterFile, rosterText);
  return { ...runLeakCheck({ rosterFile, files: Object.keys(files).map((f) => path.join(dir, f)) }), dir };
}

test("红:源名归一化变体全命中(Blocklist.de/blocklist_de/BLOCKLIST-DE/融写/中文夹写)", () => {
  const variants = ["Blocklist.de", "blocklist_de", "BLOCKLIST-DE", "blocklistde", "名单里出现 blocklist de 源"];
  const r = check({ "prompt.md": variants.join("\n") + "\n" });
  assert.equal(r.ok, false);
  for (let i = 0; i < variants.length; i++) {
    const hit = r.hits.find((h) => h.line === i + 1 && h.source === "blocklist_de" && h.kind === "name");
    assert.ok(hit, `第 ${i + 1} 行(${variants[i]})须以 name 命中 blocklist_de`);
  }
});

test("红:下载域名命中(全域名/去 www 父域);共享 host 双源都报", () => {
  const r = check({ "prompt.md": "see lists.blocklist.de\nmirror at binarydefense.com\nfrom dan.me.uk feeds\npull otx.alienvault.com\n" });
  assert.equal(r.ok, false);
  const at = (ln, src) => r.hits.find((h) => h.line === ln && h.source === src && h.kind === "domain");
  assert.ok(at(1, "blocklist_de"), "lists.blocklist.de 全域名命中");
  assert.ok(at(2, "binarydefense"), "www.binarydefense.com 去 www 父域命中");
  assert.ok(at(3, "danmeuk_tor"), "www.dan.me.uk 去 www 父域命中");
  assert.ok(at(4, "otx") && at(4, "otx_subscribed"), "共享 host 双记(同发布者两源都报)");
});

test("红:免考源名同样红(免考≠可以写进提示词)", () => {
  const r = check({ "prompt.md": "internally we also have honyport data\n" });
  assert.equal(r.ok, false);
  assert.ok(r.hits.some((h) => h.source === "honyport" && h.kind === "name"));
});

test("绿:净版零命中;命中行带「禁词引用:原因」标记放行该行", () => {
  const clean = check({ "prompt.md": "search the web for threat feeds and rank them\n" });
  assert.equal(clean.ok, true);
  assert.deepEqual(clean.hits, []);
  const mixed = check({
    "prompt.md": "示例:blocklist_de 禁词引用:gate fixture 行级豁免判例\nsearch for scanner lists\nalso blocklist_de here without marker\n",
  });
  assert.equal(mixed.ok, false);
  assert.equal(mixed.hits.length, 1);
  assert.equal(mixed.hits[0].line, 3, "带标记的第 1 行放行,第 3 行裸源名照红");
});

test("绿:空文件/空行零误报;扫描面文件清单如实回报", () => {
  const r = check({ "empty.md": "", "notes.txt": "\n\n" });
  assert.equal(r.ok, true);
  assert.equal(r.scannedFiles.length, 2);
});

// ── 缺省扫描面(spec §3.4:基准提示词 + bench 目录除名单载体外全部;票 B 产物不在=空集放行)──
test("defaultScanSurface:基准提示词在才扫;bench/ 下 exam-rules/aliases 剔除,子目录递归,排序确定", async () => {
  const { defaultScanSurface } = await import("../bench/leak-check.mjs");
  const root = tmpFixture({
    "ops/agent/prompts/discover/shortlist-bench.md": "# bench prompt\n",
    "ops/agent-v2/bench/leak-check.mjs": "// self\n",
    "ops/agent-v2/bench/exam-rules.json": "{}\n",
    "ops/agent-v2/bench/aliases.json": "{}\n",
    "ops/agent-v2/bench/notes.md": "note\n",
    "ops/agent-v2/bench/sub/deep.md": "deep\n",
  });
  const got = defaultScanSurface(root).map((p) => path.relative(root, p));
  assert.deepEqual(got, [
    "ops/agent-v2/bench/leak-check.mjs",
    "ops/agent-v2/bench/notes.md",
    "ops/agent-v2/bench/sub/deep.md",
    "ops/agent/prompts/discover/shortlist-bench.md",
  ].sort());
  const bare = tmpFixture({ "ops/agent-v2/bench/README.md": "empty bench\n" }); // 无基准提示词
  assert.deepEqual(defaultScanSurface(bare).map((p) => path.relative(bare, p)), ["ops/agent-v2/bench/README.md"]);
});

// ── 加源域扫描面(#334 交付面 3:轮提示词不得含考题名单)──
// 缺省面扩收 ops/agent/prompts/add/(加源轮提示词,bench 形态装载 system+implement,
// 生产形态另装载 dossier——三件全收);目录在才扫(同基准提示词律),真仓在场由
// 下方单源钉死测试把门(改名/移位→钉死测试红,不静默装绿——终审 P2-1 同款防线)。
test("加源域缺省面:prompts/add/ 在才扫递归;含考题名的提示词被拦(红绿自证红端)", async () => {
  const { defaultScanSurface } = await import("../bench/leak-check.mjs");
  const root = tmpFixture({
    "ops/agent/prompts/add/system.md": "实现候选源;参考既有源(如 binarydefense)风格\n", // 裸考题名=红
    "ops/agent/prompts/add/implement.md": "TDD 硬序:先写测试亲眼看红\n",
  });
  const files = defaultScanSurface(root);
  assert.deepEqual(files.map((p) => path.relative(root, p)).sort(), ["ops/agent/prompts/add/implement.md", "ops/agent/prompts/add/system.md"]);
  const r = runLeakCheck({ rosterText: FIXTURE_ROSTER, files });
  assert.equal(r.ok, false, "含考题名(binarydefense)的提示词必须被拦");
  assert.ok(r.hits.some((h) => h.source === "binarydefense" && h.file.endsWith("system.md")));
  const clean = tmpFixture({ "ops/agent/prompts/add/system.md": "通用提示词,零考题名\n" });
  assert.equal(runLeakCheck({ rosterText: FIXTURE_ROSTER, files: defaultScanSurface(clean) }).ok, true);
});

test("加源域提示词路径单源钉死:真仓 add 三件在缺省面(P1 改名/移位→本测试红,不静默装绿)", async () => {
  const { defaultScanSurface, addPromptsDir } = await import("../bench/leak-check.mjs");
  const files = defaultScanSurface().map((p) => p.replaceAll("\\", "/"));
  for (const f of ["system.md", "dossier.md", "implement.md"])
    assert.ok(files.some((p) => p === `${addPromptsDir().replaceAll("\\", "/")}/${f}`), `缺省面须含 ops/agent/prompts/add/${f}`);
  assert.ok(fs.existsSync(addPromptsDir()), "真仓 prompts/add 在(P1 #332 产物)");
});

// ── 轮产出 diff 泄漏针(#334 交付面 3:diff 不得引用被剥路径)──
// 被剥路径 = 答案树在主检出侧的绝对路径面(backend/ipdb、backend/tests、主检 .git);
// 沙箱内相对路径是轮的合法工作面(IMPLEMENT 就该写 backend/tests/...),不红;
// venv 解释器绝对路径合法入提示词,不红(它是测试跑法,不是答案树)。
test("checkRoundDiffLeak:引用主检出答案树绝对路径=红;沙箱相对路径/venv 路径=绿", async () => {
  const { checkRoundDiffLeak } = await import("../bench/leak-check.mjs");
  const repoRoot = "/home/x/main-checkout";
  const name = "some_question";
  const red = checkRoundDiffLeak({
    repoRoot, name,
    files: [
      { path: "notes.md", text: `答案在这: ${repoRoot}/backend/tests/sources/test_${name}.py 抄之\n` },
      { path: "backend/ipdb/_sources/other.py", text: "干净实现\n" },
    ],
  });
  assert.equal(red.ok, false);
  assert.equal(red.hits.length, 1);
  assert.equal(red.hits[0].file, "notes.md");
  assert.equal(red.hits[0].line, 1);
  const green = checkRoundDiffLeak({
    repoRoot, name,
    files: [
      { path: `backend/tests/sources/test_${name}.py`, text: "def test_x():\n    assert True\n" }, // 沙箱相对路径=轮的合法产出
      { path: "backend/ipdb/_sources/x.py", text: "from .._base import Source\n" },
      { path: "run.md", text: `pytest 解释器(绝对路径):${repoRoot}/backend/.venv/bin/python\n` }, // venv=非答案树
    ],
  });
  assert.equal(green.ok, true);
  assert.deepEqual(green.hits, []);
});

// ── 真仓默认面(终审 P1:leak gate 对自家默认面恒红)──
// 根因:score.mjs 匹配器判据行(源名/域名针字面量)在缺省扫描面内、未带行级豁免标记 →
// 跑默认面必 exit 1。本测试用真仓文件(defaultScanSurface() 缺省面)+ 模拟真 roster 针集
// 的 fixture(行形取自真实 roster dump:otx/otx_subscribed 共享 host、firehol raw 直链、
// binarydefense 三段域名、geolite_city 仓页 host、blocklist_de 名字归一),钉死「豁免标记
// 完整,真仓面不再恒红」。匹配语义零削弱:针生成逻辑不动,免考名照样红/合成红夹具照红
// 由上文测试钉,本测试只加不减。
test("真仓默认面:fixture roster(otx/firehol/binarydefense/github 家族)对 defaultScanSurface 零命中", async () => {
  const { defaultScanSurface } = await import("../bench/leak-check.mjs");
  const files = defaultScanSurface();
  assert.ok(files.length > 0, "真仓默认面非空(基准提示词 + bench 目录)");
  const fixtureRoster = [
    "otx | threat | otx.alienvault.com | is_malicious",
    "otx_subscribed | threat | otx.alienvault.com | is_malicious",
    "blocklist_de | threat | lists.blocklist.de | is_malicious",
    "binarydefense | threat | www.binarydefense.com | is_malicious",
    "firehol | threat | raw.githubusercontent.com | is_malicious",
    "geolite_city | geo_asn | github.com | city,country_code",
  ].join("\n");
  const r = runLeakCheck({ rosterText: fixtureRoster, files });
  assert.deepEqual(r.hits.map((h) => `${h.file}:${h.line} [${h.source}/${h.kind}]`), [], "真仓默认面有未豁免的针命中(豁免标记缺/漏)");
  assert.equal(r.ok, true);
});

// ── roster 解析单源(终审 P2-2:两解析器失败语义分叉——旧 leak-check 版 3 列宽容/坏行静默跳,
// score 版 ≥4 列/坏行 throw;同一 --roster 输入格式漂移时打分器红、漏题闸静默少针)──
test("roster 坏行(列数<4)= throw(fail-closed):格式漂移时漏题闸同样红,不静默少针", () => {
  const noPipe = FIXTURE_ROSTER + "\nbroken line without pipes\n";
  assert.throws(() => runLeakCheck({ rosterText: noPipe, files: [] }), /列数不足/);
  const threeCol = FIXTURE_ROSTER + "\nname | category | hostonly\n"; // 旧 leak-check 版宽容收的 3 列形
  assert.throws(() => runLeakCheck({ rosterText: threeCol, files: [] }), /列数不足/);
});

// 单源钉:score.mjs 暴露的解析器与 bench/roster.mjs 同一函数(任一侧重新手抄解析器即红)
test("roster 解析器单源:score.mjs 的 parseRoster === bench/roster.mjs 的 parseRoster", async () => {
  const { parseRoster: fromScore } = await import("../bench/score.mjs");
  const rosterMod = await import("../bench/roster.mjs");
  assert.equal(fromScore, rosterMod.parseRoster);
});

// ── 基准提示词路径单源(终审 P2-1:leak-check 与 run-discover 双处手抄漂移 → 提示词改名后
// 缺省面 existsSync 空集放行、漏题闸静默装绿)──
test("基准提示词路径单源:leak-check 缺省面取的路径 = run-discover shortlistBenchPromptPath,且真仓在", async () => {
  const { shortlistBenchPromptPath: leakPath, defaultScanSurface } = await import("../bench/leak-check.mjs");
  const { shortlistBenchPromptPath: runnerPath } = await import("../run-discover.mjs");
  assert.equal(leakPath(), runnerPath(), "两处基准提示词路径不同源(改名后漏题闸缺省面会空集放行)");
  assert.ok(fs.existsSync(runnerPath()), "基准提示词在真仓(票 #319 产物)");
  assert.ok(defaultScanSurface().includes(leakPath()), "缺省扫描面含基准提示词");
});

// ── exam-rules.json 初始文件(票面:免考 8 冻结值;理由字段可空;捞回裁决留位)──
test("exam-rules.json:免考 8 与冻结值一致;每条含 reason(可空串)与 reclaim 留位(null)", async () => {
  const frozen8 = ["cdn_edges", "cloud_ranges", "cn_isp", "honyport", "infra_services", "rir_abuse", "rir_delegated", "scanner_ranges"]; // 票 #321 冻结值(= roster download_host '-' 集,spec Q8)
  const rules = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, "..", "bench", "exam-rules.json"), "utf8"));
  assert.deepEqual(rules.exempt.map((e) => e.name).sort(), [...frozen8].sort(), "免考名单=冻结 8,多一名少一名都是漂移");
  for (const e of rules.exempt) {
    assert.equal(typeof e.reason, "string", `${e.name}:reason 字段在(可空串)`);
    assert.equal(e.reclaim, null, `${e.name}:reclaim 捞回裁决留位初始 null`);
  }
});

// ── CLI 面(退出码契约同 run-discover.mjs 风格:0 绿/1 红/2 用法或取数失败)──
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const execFileP = promisify(execFile);

test("CLI:红文件 exit 1 且报 文件:行+源名;净文件 exit 0;roster 取不到 exit 2", async () => {
  const dir = tmpFixture({ "red.md": "one more feed: Blocklist.de\n", "clean.md": "nothing here\n" });
  const rosterFile = path.join(dir, "roster.txt");
  fs.writeFileSync(rosterFile, FIXTURE_ROSTER);
  // promisify execFile 非零退出会 reject:折成 {code, stdout} 不抛,退出码才是断言面
  const cli = (args) =>
    execFileP(process.execPath, [path.resolve(import.meta.dirname, "..", "bench", "leak-check.mjs"), ...args], { cwd: dir })
      .then((r) => ({ code: 0, stdout: r.stdout }), (e) => ({ code: e.code ?? -1, stdout: e.stdout ?? "" }));
  const red = await cli([path.join(dir, "red.md"), "--roster-file", rosterFile]);
  assert.equal(red.code, 1, "红文件 exit 1");
  assert.ok(red.stdout.includes("red.md:1") && red.stdout.includes("blocklist_de"), "stdout 报 文件:行 与源名");
  // #334 红绿自证红端:构造一个含考题名的加源轮提示词 → 必被拦(exit≠0)
  fs.writeFileSync(path.join(dir, "add-prompt.md"), "# 加源轮提示词\n实现候选源,风格参考 binarydefense 即可\n");
  const evilPrompt = await cli([path.join(dir, "add-prompt.md"), "--roster-file", rosterFile]);
  assert.notEqual(evilPrompt.code, 0, "含考题名的提示词必须被拦");
  assert.equal(evilPrompt.code, 1);
  assert.ok(evilPrompt.stdout.includes("binarydefense"), "命中报源名");
  const clean = await cli([path.join(dir, "clean.md"), "--roster-file", rosterFile]);
  assert.equal(clean.code, 0, "净文件 exit 0");
  const bad = await cli([path.join(dir, "clean.md"), "--roster-file", path.join(dir, "nope.txt")]);
  assert.equal(bad.code, 2, "roster 取不到 exit 2");
  const dirArg = await cli([dir, "--roster-file", rosterFile]); // 显式传目录→递归扫全(不剔除名单载体)
  assert.equal(dirArg.code, 1, "目录参数递归扫描,内含红文件与 roster 本体均命中");
  const empty = path.join(dir, "empty-roster.txt");
  fs.writeFileSync(empty, ""); // 评审 P2:空 roster fail-open——空件/空输出都不得零针扫零命中装绿
  const failClosed = await cli([path.join(dir, "clean.md"), "--roster-file", empty]);
  assert.equal(failClosed.code, 2, "空 roster 文件 exit 2(fail-closed,不带病开闸)");
});
