// add-exam-cards.test.mjs — #334 交付面 2 红绿面:考题卡预填生成器(add-domain/gen-exam-cards.mjs)。
// 契约 = spec §重实现基准协议「考题卡预填生成」:从宇宙行 + 真源实抓样本生成交接单形考题卡
// (URL/样本 3-5 行/格式/auth/cadence/字段路由草案)——样本构建考题时抓一次冻结进卡,
// trial 内不联网;端点覆写表可配(#331 人裁点:多端点源前缀 URL,P3 前用户裁,生成器不替裁)。
// 测试面零网络:fetchImpl 注入 stub(genExamCards 程序面缝);卡形状单源 = dossierShape
// (tasks/add-round.mjs,禁第二份形状清单)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  pickSamples,
  sniffFormat,
  cadenceOf,
  routingDraftOf,
  endpointFace,
  buildCard,
  genExamCards,
} from "../bench/add-domain/gen-exam-cards.mjs";
import { dossierShape } from "../tasks/add-round.mjs";
import { DUMP_META_SCRIPT } from "../bench/add-domain/gen-universe.mjs";
import { loadUniverse } from "../bench/add-domain/score.mjs";

// ── fixture:2 题宇宙(qone=plain ip list,qtwo=csv)+ roster + meta dump ──
function makeFixture() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "add-cards-"));
  const universePath = path.join(tmp, "universe.jsonl");
  fs.writeFileSync(universePath, [
    JSON.stringify({ kind: "ipradar-add-universe", frozen: true }),
    JSON.stringify({ split: "evolve", name: "qone", url: "https://qone.example/feed.txt", category: "threat", archetype: "IpListSource", _why: "禁词引用:fixture 答案键载体" }),
    JSON.stringify({ split: "heldout", name: "qtwo", url: "https://qtwo.example/rows.csv", category: "asset", archetype: "CsvSource", _why: "禁词引用:fixture 答案键载体" }),
  ].join("\n") + "\n");
  const rosterText = [
    "qone | threat | qone.example | ip",
    "qtwo | asset | qtwo.example | is_proxy",
  ].join("\n");
  const metaDump = {
    qone: { urls: ["https://qone.example/feed.txt"], archetype: "IpListSource", stale_days: 1 },
    qtwo: { urls: ["https://qtwo.example/rows.csv"], archetype: "CsvSource", stale_days: 30 },
  };
  return { tmp, universePath, rosterText, metaDump };
}

test("pickSamples:非空行取 3-5 行;空行/注释行跳过;不足 3 行=空集(调用方红)", () => {
  assert.deepEqual(pickSamples("\n1.2.3.4\n\n5.6.7.8\n9.10.11.12\n"), ["1.2.3.4", "5.6.7.8", "9.10.11.12"]);
  assert.deepEqual(pickSamples("# banner\n1.2.3.4\n5.6.7.8\n9.10.11.12\n"), ["1.2.3.4", "5.6.7.8", "9.10.11.12"], "注释行优先跳(样本要展示数据面)");
  assert.deepEqual(pickSamples(["# a", "# b", "# c"].join("\n")), ["# a", "# b", "# c"], "全注释面回退原始行(如实不造)");
  assert.deepEqual(pickSamples(["a", "b", "c", "d", "e", "f", "g"].join("\n")), ["a", "b", "c", "d", "e"], "封顶 5 行");
  assert.deepEqual(pickSamples("only-one\n"), []);
});

test("sniffFormat:ip 列表/csv/tsv/json/text 五形机械判", () => {
  assert.equal(sniffFormat(["1.2.3.4", "5.6.7.8/24"]), "plain-ip-list");
  assert.equal(sniffFormat(["ip,reason", "1.2.3.4,abuse"]), "csv");
  assert.equal(sniffFormat(["ip\tcountry", "1.2.3.4\tCN"]), "tsv");
  assert.equal(sniffFormat(['{"ip": "1.2.3.4"}', '{"ip": "5.6.7.8"}']), "json");
  assert.equal(sniffFormat(["some opaque banner line"]), "text");
});

test("cadenceOf:stale_days → daily/weekly 级/低频;无声明=如实未知", () => {
  assert.match(cadenceOf(1), /daily/);
  assert.match(cadenceOf(3), /weekly/);
  assert.match(cadenceOf(30), /低频/);
  assert.match(cadenceOf(null), /未知/);
});

test("routingDraftOf:ip 面 → rebuild 键;语义字段 → 分类/属性面草案行", () => {
  assert.deepEqual(routingDraftOf(["ip"], "threat"), ["行内 IP/CIDR → rebuild 键(cidr)"]);
  const d = routingDraftOf(["is_malicious", "dnsrd", "smtpgreet"], "threat");
  assert.ok(d.some((l) => l.includes("is_malicious")));
  assert.ok(d.some((l) => l.includes("dnsrd")), "子列信号入路由草案");
});

test("endpointFace:端点覆写表优先;前缀 URL(尾斜杠)未覆写 = pending 点名;完整多端点 URL 不 pending", () => {
  const row = { name: "qmulti", url: "https://raw.example/SomeRepo/" };
  const clean = endpointFace({ row, metaEntry: { urls: ["https://raw.example/SomeRepo/a.txt"] }, endpoints: {} });
  assert.equal(clean.url, row.url);
  assert.equal(clean.endpoint_pending, true, "前缀 URL(尾斜杠)未覆写=pending(不可直接下载,须人裁)");
  assert.match(clean.endpoint_note, /人裁/);
  const multi = endpointFace({ row: { name: "q2", url: "https://x.example/a" }, metaEntry: { urls: ["https://x.example/a", "https://x.example/b"] }, endpoints: {} });
  assert.equal(multi.endpoint_pending, false, "完整端点的多 URL 源不 pending(卡钉宇宙行 URL 即可考,无需裁决)");
  const overridden = endpointFace({ row, metaEntry: { urls: [] }, endpoints: { qmulti: "https://raw.example/SomeRepo/feeds/a.txt" } });
  assert.equal(overridden.url, "https://raw.example/SomeRepo/feeds/a.txt");
  assert.equal(overridden.endpoint_pending, false, "已覆写=不再 pending(人已裁)");
  const plain = endpointFace({ row: { name: "qone", url: "https://qone.example/feed.txt" }, metaEntry: { urls: ["https://qone.example/feed.txt"] }, endpoints: {} });
  assert.equal(plain.endpoint_pending, false, "单端点真 URL=干净");
});

test("buildCard:交接单形过 dossierShape(单源形状律)+ _provenance 冻结面;stem 契约/样本不足=红", () => {
  const fx = makeFixture();
  const row = loadUniverse(fx.universePath).find((r) => r.name === "qone");
  const card = buildCard({
    row,
    rosterEntry: { name: "qone", category: "threat", host: "qone.example", fields: ["ip"] },
    metaEntry: fx.metaDump.qone,
    sampleText: "# banner\n1.2.3.4\n5.6.7.8\n9.10.11.12\n",
    endpoints: {},
    fetchedAt: "2026-11-11T00:00:00Z",
  });
  assert.equal(dossierShape(card).ok, true, "生成卡须过交接单形状(与轮/DOSSIER 同门)");
  assert.equal(card.name, "qone", "卡名=宇宙行名(stem 契约:slugify(name)===题名)");
  assert.equal(card.auth, "none", "宇宙面无 auth env 读(gen-universe keyless 反扫钉死)");
  assert.deepEqual(card.samples, ["1.2.3.4", "5.6.7.8", "9.10.11.12"]);
  assert.equal(card._provenance.fetched_at, "2026-11-11T00:00:00Z");
  assert.equal(card._provenance.endpoint_pending, false);
  assert.match(card._provenance.note, /冻结/);
  // stem 契约红:宇宙行名非 slug 形 → 生成即红,不留给 trial
  assert.throws(() => buildCard({
    row: { ...row, name: "Not A Slug" },
    rosterEntry: { name: "Not A Slug", category: "threat", host: "x", fields: ["ip"] },
    metaEntry: fx.metaDump.qone,
    sampleText: "1.2.3.4\n5.6.7.8\n9.10.11.12\n",
    endpoints: {}, fetchedAt: "now",
  }), /slug|stem/i);
  // 样本不足红
  assert.throws(() => buildCard({
    row, rosterEntry: { name: "qone", category: "threat", host: "x", fields: ["ip"] }, metaEntry: fx.metaDump.qone,
    sampleText: "1.2.3.4\n", endpoints: {}, fetchedAt: "now",
  }), /样本/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("genExamCards:注入 fetchImpl 全绿写卡(每题一件 json);单题抓取失败=failed 记账不吞;only 收窄", async () => {
  const fx = makeFixture();
  const outDir = path.join(fx.tmp, "cards");
  const serve = {
    "https://qone.example/feed.txt": "1.2.3.4\n5.6.7.8\n9.10.11.12\n",
    "https://qtwo.example/rows.csv": "ip,tag\n1.2.3.4,proxy\n5.6.7.8,proxy\n",
  };
  const r = await genExamCards({
    universePath: fx.universePath, rosterText: fx.rosterText, metaDump: fx.metaDump,
    endpoints: {}, fetchImpl: async (u) => serve[u], outDir,
  });
  assert.deepEqual(r.written.sort(), ["qone", "qtwo"]);
  assert.deepEqual(r.failed, []);
  for (const n of ["qone", "qtwo"]) {
    const card = JSON.parse(fs.readFileSync(path.join(outDir, `${n}.json`), "utf8"));
    assert.equal(dossierShape(card).ok, true);
  }
  // 单题红:qtwo 抓取失败 → failed 记账,qone 照写(部分产物保真,退出码交 CLI)
  const out2 = path.join(fx.tmp, "cards2");
  const r2 = await genExamCards({
    universePath: fx.universePath, rosterText: fx.rosterText, metaDump: fx.metaDump,
    endpoints: {}, fetchImpl: async (u) => (u.includes("qtwo") ? Promise.reject(new Error("HTTP 503")) : serve[u]),
    outDir: out2, only: undefined,
  });
  assert.deepEqual(r2.written, ["qone"]);
  assert.equal(r2.failed.length, 1);
  assert.equal(r2.failed[0].name, "qtwo");
  assert.match(r2.failed[0].error, /503/);
  // only 收窄
  const r3 = await genExamCards({
    universePath: fx.universePath, rosterText: fx.rosterText, metaDump: fx.metaDump,
    endpoints: {}, fetchImpl: async (u) => serve[u], outDir: path.join(fx.tmp, "cards3"), only: ["qtwo"],
  });
  assert.deepEqual(r3.written, ["qtwo"]);
  // 未冻结宇宙 → 拒(frozen 闸与沙箱/打分器同律)
  const unfrozen = path.join(fx.tmp, "unfrozen.jsonl");
  fs.writeFileSync(unfrozen, fs.readFileSync(fx.universePath, "utf8").replace('"frozen":true', '"frozen":false'));
  await assert.rejects(() => genExamCards({
    universePath: unfrozen, rosterText: fx.rosterText, metaDump: fx.metaDump,
    endpoints: {}, fetchImpl: async () => "x\ny\nz\n", outDir: path.join(fx.tmp, "cards4"),
  }), /frozen|钉死/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("DUMP_META_SCRIPT:含 stale_days 面(生成卡 cadence 派生源,meta dump 单源不另立)", () => {
  assert.ok(DUMP_META_SCRIPT.includes("stale_days"), "dump 面须带 stale_days(cadence 派生)");
  assert.ok(DUMP_META_SCRIPT.includes("urls"), "urls 面(gen-universe 同源)在");
});
