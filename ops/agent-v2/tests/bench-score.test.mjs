// bench-score.test.mjs — 重发现基准打分器(#320,规格 §3.3)单测:合成 fixture,零网络零 python。
// 面:①答案表机械派生(roster 行解析 × 免考规则 × URL 声明合并)②四层匹配器各路径
// (完整 URL→发布者/域名→名字归一化→别名;otx 同发布者双记;github 家族按 repo 路径段区分)
// ③报表分栏形状 ④确定性:同工件目录重跑字节级同分。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import {
  D2_SHORTLIST, normalizeName, normalizeUrl, parseRoster, buildAnswerTable, matchLayer,
  scoreRound, renderMarkdown, runScoring,
} from "../bench/score.mjs";

const BENCH_DIR = path.resolve(import.meta.dirname, "..", "bench");

// ── 合成 roster/urlDump fixture(形状 = 真实 `python -m ipdb._registry --roster` 输出)──
const ROSTER = [
  "otx | threat | otx.alienvault.com | is_malicious",
  "otx_subscribed | threat | otx.alienvault.com | is_malicious",
  "blocklist_de | threat | lists.blocklist.de | is_malicious | mail,ssh",
  "firehol | threat | raw.githubusercontent.com | is_malicious",
  "thespeedx | asset | raw.githubusercontent.com | is_proxy",
  "missing_one | threat | example.org | is_malicious",
  "cn_isp | geo_asn | - | country_code,carrier",
].join("\n");

const URL_DUMP = JSON.stringify({
  otx: { host: "otx.alienvault.com", urls: ["https://otx.alienvault.com/api/v1/pulses/activity"] },
  otx_subscribed: { host: "otx.alienvault.com", urls: ["https://otx.alienvault.com/api/v1/pulses/subscribed"] },
  blocklist_de: { host: "lists.blocklist.de", urls: ["https://lists.blocklist.de/lists"] },
  firehol: { host: "raw.githubusercontent.com", urls: ["https://raw.githubusercontent.com/firehol/blocklist-ipsets/master"] },
  thespeedx: { host: "raw.githubusercontent.com", urls: ["https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"] },
  missing_one: { host: "example.org", urls: ["https://example.org/feed.txt"] },
  cn_isp: { host: "-", urls: [] },
});

const RULES = { version: 1, exempt: [{ name: "cn_isp", reason: "内部派生,无外部下载源", reclaim: null }] };
const ALIASES = { version: 1, aliases: { "alienvault otx": "otx" } };

test("normalizeName:小写去点去下划线去连字符(规格 Q3)", () => {
  assert.equal(normalizeName("Blocklist.de"), "blocklistde");
  assert.equal(normalizeName("blocklist_de"), "blocklistde");
  assert.equal(normalizeName("FireHOL-Level1"), "firehollevel1");
});

test("parseRoster:name|category|host|fields[|subs] 四/五列;空行跳过", () => {
  const rows = parseRoster(ROSTER + "\n\n");
  assert.equal(rows.length, 7);
  assert.deepEqual(rows[2], { name: "blocklist_de", category: "threat", host: "lists.blocklist.de", fields: ["is_malicious", "mail", "ssh"] });
  assert.equal(rows[6].host, "-");
});

test("buildAnswerTable:免考按 exam-rules 名单切栏,不入考题;URL 声明按名合并;别名按归一名挂答案", () => {
  const t = buildAnswerTable({ rosterText: ROSTER, urlDumpJson: URL_DUMP, examRules: RULES, aliases: ALIASES });
  assert.equal(t.rosterTotal, 7);
  assert.deepEqual(t.exam.map((a) => a.name), ["otx", "otx_subscribed", "blocklist_de", "firehol", "thespeedx", "missing_one"]);
  assert.deepEqual(t.exempt.map((a) => a.name), ["cn_isp"]);
  const firehol = t.exam.find((a) => a.name === "firehol");
  assert.ok(firehol.urls.includes("https://raw.githubusercontent.com/firehol/blocklist-ipsets/master"));
  assert.deepEqual(firehol.repos, ["firehol/blocklist-ipsets"]);
  const otx = t.exam.find((a) => a.name === "otx");
  assert.deepEqual(otx.aliasNames, ["alienvault otx"]); // 归一化后挂靠(冻结字符集 [._-],空格保留)
});

test("buildAnswerTable:urlDump 与 roster 名单/host 不一致即红(roster 单源纪律)", () => {
  const badHost = URL_DUMP.replace("lists.blocklist.de", "other.example");
  assert.throws(() => buildAnswerTable({ rosterText: ROSTER, urlDumpJson: badHost, examRules: RULES, aliases: ALIASES }), /host/);
  const missingName = JSON.parse(URL_DUMP);
  delete missingName.cn_isp;
  assert.throws(() => buildAnswerTable({ rosterText: ROSTER, urlDumpJson: JSON.stringify(missingName), examRules: RULES, aliases: ALIASES }), /roster/);
});

test("buildAnswerTable:免考名单里的名字不在 roster = 红(冻结名单对不上现实);条目缺 name = 红", () => {
  assert.throws(() => buildAnswerTable({ rosterText: ROSTER, urlDumpJson: URL_DUMP, examRules: { version: 1, exempt: [{ name: "no_such_source", reason: "x", reclaim: null }] }, aliases: ALIASES }), /no_such_source/);
  assert.throws(() => buildAnswerTable({ rosterText: ROSTER, urlDumpJson: URL_DUMP, examRules: { version: 1, exempt: ["cn_isp"] }, aliases: ALIASES }), /name/); // 裸字符串旧形状拒绝
});

test("reclaim 语义:reclaim 非空 = 用户已裁决捞回 → 进考题分母参与召回;null = 免考不入分母(D 版 _doc 口径)", () => {
  const roster = ["exempt_a | threat | - | is_malicious", "reclaimed_b | threat | feed.example.org | is_malicious", "plain_c | threat | other.example.org | is_malicious"].join("\n");
  const dump = JSON.stringify({
    exempt_a: { host: "-", urls: [] },
    reclaimed_b: { host: "feed.example.org", urls: ["https://feed.example.org/b.txt"] },
    plain_c: { host: "other.example.org", urls: ["https://other.example.org/c.txt"] },
  });
  const rules = {
    version: 1,
    exempt: [
      { name: "exempt_a", reason: "内部派生", reclaim: null },
      { name: "reclaimed_b", reason: "内部派生", reclaim: { date: "2026-11-07", ruling: "用户裁决捞回" } },
    ],
  };
  const t = buildAnswerTable({ rosterText: roster, urlDumpJson: dump, examRules: rules, aliases: { version: 1, aliases: {} } });
  assert.deepEqual(t.exam.map((a) => a.name), ["reclaimed_b", "plain_c"]); // 捞回进考题
  assert.deepEqual(t.exempt.map((a) => a.name), ["exempt_a"]);
  const r = scoreRound(t, [{ name: "plain_c", url: "https://other.example.org/c.txt", source_channel: "web" }]);
  assert.deepEqual(r.recall, { found: 1, total: 2, pct: 50 }); // reclaimed_b 在分母且未搜到 → 扣分
  assert.deepEqual(r.unfound, [{ name: "reclaimed_b", host: "feed.example.org" }]);
});

test("免考名单文件 = 规格冻结 8 名,不得增删(Q8);形状 = D 版对象条目", () => {
  const rules = JSON.parse(fs.readFileSync(path.join(BENCH_DIR, "exam-rules.json"), "utf8"));
  assert.ok(Array.isArray(rules.exempt));
  assert.deepEqual([...rules.exempt.map((e) => e.name)].sort(), [
    "cdn_edges", "cloud_ranges", "cn_isp", "honyport",
    "infra_services", "rir_abuse", "rir_delegated", "scanner_ranges",
  ]);
});

test("别名表文件:版本化,初始空(人工裁决一次入一条)", () => {
  const a = JSON.parse(fs.readFileSync(path.join(BENCH_DIR, "aliases.json"), "utf8"));
  assert.equal(a.version, 1);
  assert.deepEqual(a.aliases, {});
});

// ── 四层匹配器(规格 Q3)──

function table() {
  return buildAnswerTable({ rosterText: ROSTER, urlDumpJson: URL_DUMP, examRules: RULES, aliases: ALIASES });
}

function answerOf(t, name) {
  return [...t.exam, ...t.exempt].find((a) => a.name === name);
}

test("L1 完整 URL:与声明 URL 全等(尾斜杠/大小写/fragment 归一后)", () => {
  const t = table();
  const cand = { name: "x", url: "HTTPS://raw.githubusercontent.com/firehol/blocklist-ipsets/master/#frag" };
  assert.equal(matchLayer(answerOf(t, "firehol"), cand), 1);
  // 大小写不在归一面(归一只动 host/path/query 小写化——此处全串已小写化,等价);全等外不算 L1
  assert.equal(matchLayer(answerOf(t, "thespeedx"), cand), null);
});

test("L2 发布者/域名:otx 与 otx_subscribed 同发布者双记(一条候选两源都中)", () => {
  const t = table();
  const cand = { name: "OTX", url: "https://otx.alienvault.com/api/v1/pulses/activity" };
  assert.equal(matchLayer(answerOf(t, "otx"), cand), 1); // 完整 URL 恰与声明全等
  assert.equal(matchLayer(answerOf(t, "otx_subscribed"), cand), 2); // 同发布者域名 → 双记
  const root = { name: "OTX", url: "https://otx.alienvault.com/" };
  assert.equal(matchLayer(answerOf(t, "otx"), root), 2);
  assert.equal(matchLayer(answerOf(t, "otx_subscribed"), root), 2);
});

test("L2 github 家族:按 repo 路径段区分,不同 repo 不误并;仓页 URL 与 raw 直链同 repo 相认", () => {
  const t = table();
  const speedx = { name: "SpeedX", url: "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt" };
  assert.equal(matchLayer(answerOf(t, "thespeedx"), speedx), 1);
  assert.equal(matchLayer(answerOf(t, "firehol"), speedx), null); // 同 raw 主机不同 repo → 不并
  const repoPage = { name: "FireHOL", url: "https://github.com/firehol/blocklist-ipsets" };
  assert.equal(matchLayer(answerOf(t, "firehol"), repoPage), 2);
  assert.equal(matchLayer(answerOf(t, "thespeedx"), repoPage), null);
});

test("L3 名字归一化:「Blocklist.de」对 blocklist_de;L4 别名表:「AlienVault OTX」→ otx", () => {
  const t = table();
  assert.equal(matchLayer(answerOf(t, "blocklist_de"), { name: "Blocklist.de", url: null }), 3);
  assert.equal(matchLayer(answerOf(t, "otx"), { name: "AlienVault OTX", url: null }), 4);
  assert.equal(matchLayer(answerOf(t, "otx_subscribed"), { name: "AlienVault OTX", url: null }), null); // 别名只挂 otx
});

test("逐答案独立匹配:一候选 URL 中 firehol(L1)同时名字中 thespeedx(L3),互不挤占", () => {
  const t = table();
  const cand = { name: "thespeedx", url: "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master" };
  assert.equal(matchLayer(answerOf(t, "firehol"), cand), 1);
  assert.equal(matchLayer(answerOf(t, "thespeedx"), cand), 3);
});

test("未中:无 URL 无名匹配时返 null;免考源可被名字命中(供免考栏留痕)", () => {
  const t = table();
  assert.equal(matchLayer(answerOf(t, "missing_one"), { name: "zzz", url: null }), null);
  assert.equal(matchLayer(answerOf(t, "cn_isp"), { name: "CN_ISP", url: null }), 3);
});

// ── 评分与报表(合成 candidates,形状契约 = d2-shortlist.json 的 candidates 数组七键)──

const CANDS = [
  { name: "AlienVault OTX", url: "https://otx.alienvault.com/api/v1/pulses/activity", quote: "q", evidence_ptr: "d2-shortlist-transcript.jsonl:L3", source_channel: "web", exclusivity_estimate: null, notes: "OTX activity feed" },
  { name: "Blocklist.de", url: "https://lists.blocklist.de/lists/ssh.txt", quote: "q", evidence_ptr: "NEEDS.md:L14", source_channel: "needs", exclusivity_estimate: null, notes: "blocklist.de ssh list" },
  { name: "FireHOL", url: "https://github.com/firehol/blocklist-ipsets", quote: "q", evidence_ptr: "d2-shortlist-transcript.jsonl:L9", source_channel: "web", exclusivity_estimate: null, notes: "firehol repo" },
  { name: "SpeedX Proxy", url: "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", quote: "q", evidence_ptr: "d2-shortlist-transcript.jsonl:L12", source_channel: "web", exclusivity_estimate: null, notes: "speedx http proxy list" },
  { name: "BrandNew Feed", url: "https://brandnew.example.net/feed.csv", quote: "q", evidence_ptr: "d2-shortlist-transcript.jsonl:L15", source_channel: "web", exclusivity_estimate: null, notes: "表外新候选样例" },
];

test("scoreRound:总召回/分类分栏/needs vs web/未搜到/表外新候选/免考不入分母", () => {
  const t = table();
  const r = scoreRound(t, CANDS);
  assert.equal(r.rosterTotal, 7);
  assert.equal(r.examCount, 6);
  assert.deepEqual(r.recall, { found: 5, total: 6, pct: 83.33 }); // 唯一未中 = missing_one
  assert.deepEqual(r.byCategory, [
    { category: "threat", found: 4, total: 5 },
    { category: "geo_asn", found: 0, total: 0 },
    { category: "asset", found: 1, total: 1 },
  ]);
  assert.deepEqual(r.byChannel, { needsAssisted: 1, pureWeb: 4 }); // blocklist_de 走 needs 渠道命中
  assert.deepEqual(r.unfound, [{ name: "missing_one", host: "example.org" }]);
  assert.deepEqual(r.newCandidates.map((c) => c.name), ["BrandNew Feed"]);
  assert.deepEqual(r.exempt, ["cn_isp"]);
  assert.deepEqual(r.exemptHits, []);
  // 命中明细:源/层/候选/渠道 —— 双记可见(otx@L1 与 otx_subscribed@L2 同一候选)
  const otx = r.found.find((f) => f.answer === "otx");
  const otxSub = r.found.find((f) => f.answer === "otx_subscribed");
  assert.equal(otx.layer, 1);
  assert.equal(otxSub.layer, 2);
  assert.equal(otx.via.name, "AlienVault OTX");
  assert.equal(otxSub.via.name, "AlienVault OTX");
  assert.equal(otx.via.source_channel, "web");
  assert.equal(r.found.find((f) => f.answer === "blocklist_de").via.source_channel, "needs");
});

test("renderMarkdown:六栏齐(总召回/按 category/needs vs web/免考/表外新候选/未搜到)+命中明细", () => {
  const md = renderMarkdown(scoreRound(table(), CANDS));
  assert.match(md, /# 重发现基准打分报告/);
  assert.match(md, /5\/6\(83\.33%\)/);
  assert.match(md, /threat: 4\/5/);
  assert.match(md, /geo_asn: 0\/0/);
  assert.match(md, /靠 NEEDS 提示:1/);
  assert.match(md, /纯 web:4/);
  assert.match(md, /免考\(1,不入分母\)/);
  assert.match(md, /cn_isp/);
  assert.match(md, /BrandNew Feed \| https:\/\/brandnew\.example\.net\/feed\.csv/);
  assert.match(md, /未搜到\(1\)/);
  assert.match(md, /missing_one\(example\.org\)/);
});

test("renderMarkdown P2-3:表格单元格内 | 转义为 \\|(命中明细候选名 + 表外新候选名/URL/备注)", () => {
  const cands = [
    { name: "Weird|Name", url: "https://otx.alienvault.com/api/v1/pulses/activity", quote: "q", evidence_ptr: "t.jsonl:L1", source_channel: "web", exclusivity_estimate: null, notes: "" },
    { name: "Out|Side", url: "https://x.example.org/a|b.csv", quote: "q", evidence_ptr: "t.jsonl:L2", source_channel: "web", exclusivity_estimate: null, notes: "note|pipe" },
  ];
  const md = renderMarkdown(scoreRound(table(), cands));
  const hit = md.split("\n").find((l) => l.includes("| otx |"));
  assert.ok(hit, "命中明细缺 otx 行");
  assert.match(hit, /\| otx \| L1 \| Weird\\\|Name \| web \|/, "命中明细候选名列竖线未转义");
  const row = md.split("\n").find((l) => l.includes("Out"));
  assert.ok(row, "表外新候选行缺失");
  assert.match(row, /\| Out\\\|Side \| https:\/\/x\.example\.org\/a\\\|b\.csv \| note\\\|pipe \|/, "表外新候选行竖线未转义");
});

test("runScoring:读 d2-shortlist.json 打分落盘 report.md/report.json;重跑字节级同分(确定性门)", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-bench-score-"));
  try {
    fs.writeFileSync(path.join(tmp, D2_SHORTLIST), JSON.stringify({ candidates: CANDS }, null, 1));
    const opts = { rosterText: ROSTER, urlDumpJson: URL_DUMP, examRules: RULES, aliases: ALIASES };
    runScoring(tmp, opts);
    const md1 = fs.readFileSync(path.join(tmp, "report.md"), "utf8");
    const json1 = fs.readFileSync(path.join(tmp, "report.json"), "utf8");
    assert.ok(md1.length > 0 && json1.length > 0);
    const parsed = JSON.parse(json1);
    assert.equal(parsed.recall.found, 5);
    assert.equal(parsed.round, path.basename(tmp));
    runScoring(tmp, opts); // 同工件目录重跑
    const md2 = fs.readFileSync(path.join(tmp, "report.md"), "utf8");
    const json2 = fs.readFileSync(path.join(tmp, "report.json"), "utf8");
    assert.equal(createHash("sha256").update(md2).digest("hex"), createHash("sha256").update(md1).digest("hex"), "report.md 重跑不同分");
    assert.equal(json2, json1, "report.json 重跑不同分");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("runScoring:工件缺 d2-shortlist.json 或 candidates 非数组 = 红(诚实报错不硬凑)", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-bench-score-bad-"));
  try {
    const opts = { rosterText: ROSTER, urlDumpJson: URL_DUMP, examRules: RULES, aliases: ALIASES };
    assert.throws(() => runScoring(tmp, opts), /d2-shortlist\.json/);
    fs.writeFileSync(path.join(tmp, D2_SHORTLIST), JSON.stringify({ candidates: "not-array" }));
    assert.throws(() => runScoring(tmp, opts), /candidates/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
