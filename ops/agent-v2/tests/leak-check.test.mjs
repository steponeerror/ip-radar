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
