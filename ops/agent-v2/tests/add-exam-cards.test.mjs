// add-exam-cards.test.mjs — #334 交付面 2 红绿面:考题卡预填生成器(add-domain/gen-exam-cards.mjs)。
// 契约 = spec §重实现基准协议「考题卡预填生成」:从宇宙行 + 真源实抓样本生成交接单形考题卡
// (URL/样本 3-5 行/格式/auth/cadence/字段路由草案)——样本构建考题时抓一次冻结进卡,
// trial 内不联网;端点覆写表可配(#331 人裁点:多端点源前缀 URL,P3 前用户裁,生成器不替裁)。
// #341 ① 输入面增厚:field_routing 按沙箱内**兄弟源同名列/同形列**的既有映射机械推导
// (列名/列形匹配→Evidence 槽位惯例表;答案无关纪律=排除考题自身源文件,不读任何答案测试);
// format 嗅探同法借列形(csv 表头识别/空白分列)。
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
  parseSiblingUsage,
  buildSiblingIndex,
  columnShapeOf,
  splitColumns,
  routingLines,
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

test("sniffFormat:ip 列表/csv/tsv/json/text 五形机械判(#341 ①:csv 借列形识别表头;空白分列双列形入 format 面)", () => {
  assert.equal(sniffFormat(["1.2.3.4", "5.6.7.8/24"]), "plain-ip-list");
  assert.equal(sniffFormat(["ip,reason", "1.2.3.4,abuse", "5.6.7.8,bot"]), "csv(表头)", "首行全名列形+后续数据形=表头面入 format(列名供路由同名列匹配)");
  assert.equal(sniffFormat(["1.2.3.4,abuse", "5.6.7.8,bot"]), "csv", "无表头=裸 csv");
  assert.equal(sniffFormat(["ip\tcountry", "1.2.3.4\tCN"]), "tsv");
  assert.equal(sniffFormat(['{"ip": "1.2.3.4"}', '{"ip": "5.6.7.8"}']), "json");
  assert.equal(sniffFormat(["some opaque banner line"]), "text");
  assert.equal(sniffFormat(["1.2.3.4 11", "5.6.7.8 3"]), "text(空白分列)", "空白双列 ip+计数形(ipsum 形)——计数语义面的格式预告");
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

// ── #341 ① 兄弟源惯例路由推断(答案无关:沙箱内既有源同名列/同形列→Evidence 槽位惯例表)──

// 合成兄弟源(机械面与真源同形:fields 元组 / Evidence( kwargs / parse_row 返回字典键 / 占位符转换)
const SIB_BRUTE = `
class BruteforceSource(Source):
    fields = ("is_malicious",)
    def harvest(self):
        yield ip, Evidence(
            classification_type="scanner",
            verdict="malicious",
            reporter_count=count,
        )
`;
const SIB_DP = `
class DataplaneSource(Source):
    fields = ("is_malicious",)
    def harvest(self):
        yield ip, Evidence(
            as_name=as_name or None,
            country_code=cc,
            abuse_contact=mail,
        )
`;
const SIB_F3 = `
class F3cSystemsSource(CsvSource):
    fields = ("is_malicious",)
    def parse_row(self, row):
        return {
            "_ip": row[0],
            "first_seen": row[1],
            "last_seen": row[2],
            "extra": extra,
        }
`;
const SIB_DASH = `
class DashSource(Source):
    fields = ("is_malicious",)
    def harvest(self):
        as_name = as_name if as_name != "-" else None
`;
const SIB_FILES = [
  { name: "bruteforce", text: SIB_BRUTE },
  { name: "dataplane", text: SIB_DP },
  { name: "f3csystems", text: SIB_F3 },
  { name: "dashsrc", text: SIB_DASH },
  { name: "_base", text: 'class Base:\n    fields = ("is_malicious",)\n' }, // _ 前缀=基建面,不入惯例表
];

test("parseSiblingUsage:fields 元组/Evidence kwargs/parse_row 字典键/占位符面机械抽取", () => {
  const u = parseSiblingUsage("bruteforce", SIB_BRUTE);
  assert.deepEqual(u.fields, ["is_malicious"]);
  for (const k of ["classification_type", "verdict", "reporter_count"]) assert.ok(u.slots.includes(k), `Evidence kwargs 抽 ${k}`);
  const f3 = parseSiblingUsage("f3csystems", SIB_F3);
  assert.deepEqual(f3.slots.sort(), ["extra", "first_seen", "last_seen"], "parse_row 字典键入槽位面;_ip 内部键排除");
  assert.equal(parseSiblingUsage("dashsrc", SIB_DASH).placeholderDash, true, "「-」占位符转换面在");
  assert.equal(parseSiblingUsage("bruteforce", SIB_BRUTE).placeholderDash, false);
});

test("buildSiblingIndex:槽位/字段→兄弟源名惯例表;考题自身源文件排除(答案无关纪律);_ 前缀基建不入表", () => {
  const idx = buildSiblingIndex(SIB_FILES, "dshield");
  assert.deepEqual(idx.slots.get("reporter_count"), ["bruteforce"]);
  assert.deepEqual(idx.slots.get("as_name"), ["dataplane"]);
  assert.deepEqual(idx.slots.get("first_seen"), ["f3csystems"]);
  assert.deepEqual(idx.fields.get("is_malicious").sort(), ["bruteforce", "dashsrc", "dataplane", "f3csystems"], "fields 声明面;_base 不在");
  assert.deepEqual(idx.placeholderDash, ["dashsrc"]);
  assert.equal(idx.scanned, 4, "5 件中 _base 排除");
  // 答案无关纪律:考题自身排除——dshield 自带独有槽也不得入表
  const selfIdx = buildSiblingIndex([...SIB_FILES, { name: "dshield", text: SIB_BRUTE }], "dshield");
  assert.equal(selfIdx.scanned, 4, "考题自身源文件(=答案)不入惯例表");
  assert.ok(!selfIdx.slots.get("reporter_count")?.includes("dshield"));
});

test("columnShapeOf:ip/cidr/int/两位国码/AS 前缀名/邮箱/时间戳/占位符;混合或单值=null(不过拟合)", () => {
  assert.equal(columnShapeOf(["1.2.3.4", "5.6.7.8"]), "ip");
  assert.equal(columnShapeOf(["1.2.3.0/24", "5.6.7.0/24"]), "cidr");
  assert.equal(columnShapeOf(["5307", "931"]), "int");
  assert.equal(columnShapeOf(["CN", "US"]), "cc");
  assert.equal(columnShapeOf(["AS00000 Foo Telecom", "AS11111 Bar Inc"]), "asn-name");
  assert.equal(columnShapeOf(["abuse@example.org", "abuse@bar.net"]), "email");
  assert.equal(columnShapeOf(["2026-11-10", "2026-11-11"]), "timestamp");
  assert.equal(columnShapeOf(["20261110", "20261111"]), "timestamp", "yyyymmdd 8 位形=日期非计数");
  assert.equal(columnShapeOf(["-", "-"]), "dash");
  assert.equal(columnShapeOf(["CN", "5307"]), null, "混合列不判形(宁少算)");
  assert.equal(columnShapeOf(["CN"]), null, "单值不判形");
  assert.equal(columnShapeOf(["CN", "-", "US"]), "cc", "占位符「-」不破形(其惯例另行成行)");
});

test("splitColumns:tab/逗号(表头识别)/空白双列;不一致或单列=null", () => {
  const tab = splitColumns(["1.2.3.0\t24\tCN", "5.6.7.0\t24\tUS"]);
  assert.equal(tab.delim, "tab");
  assert.equal(tab.rows[0].length, 3);
  assert.equal(tab.header, null);
  const csvH = splitColumns(["ip,first_seen,scan_count", "1.2.3.4,2026-11-10,7", "5.6.7.8,2026-11-11,3"]);
  assert.equal(csvH.delim, "comma");
  assert.deepEqual(csvH.header, ["ip", "first_seen", "scan_count"], "首行全名列形+后续数据形=表头");
  assert.equal(csvH.rows.length, 2, "表头不入数据行");
  assert.equal(splitColumns(["1.2.3.4,x", "5.6.7.8"]), null, "列数不一致=null");
  const ws = splitColumns(["1.2.3.4 11", "5.6.7.8 3"]);
  assert.equal(ws.delim, "space", "空白分列双列 ip+计数(ipsum 形)");
  assert.equal(splitColumns(["foo bar", "baz qux"]), null, "空白分列须首列 ip 形");
});

test("routingLines(dshield 形 tsv):start+前缀长合成 cidr 键/计数→reporter_count/AS 名→as_name/国码→country_code/邮箱→abuse_contact;占位符惯例行", () => {
  const idx = buildSiblingIndex(SIB_FILES, "dshield");
  const lines = routingLines({
    sampleLines: [
      "1.2.3.0\t1.2.3.255\t24\t5307\tAS00000 Foo Telecom\tCN\tabuse@example.org",
      "5.6.7.0\t5.6.7.255\t24\t931\tAS11111 Bar Inc\tUS\tabuse@bar.net",
      "9.9.9.0\t9.9.9.255\t24\t480\tAS22222 Baz Ltd\tDE\t-",
    ],
    format: "tsv", rosterFields: ["is_malicious"], category: "threat", index: idx,
  });
  assert.ok(lines.some((l) => /列1\+列3.*起点\+前缀长/.test(l) && /rebuild/.test(l)), "双 IP 列夹 8-32 数值列=start/prefix 记法→cidr 键");
  assert.ok(lines.some((l) => /列4.*计数形/.test(l) && /reporter_count/.test(l) && /bruteforce/.test(l)), "计数形→reporter_count 槽位并引兄弟源");
  assert.ok(lines.some((l) => /列5.*as_name/.test(l) && /dataplane/.test(l)), "AS 前缀名形→as_name 槽位");
  assert.ok(lines.some((l) => /列6.*country_code/.test(l) && /dataplane/.test(l)), "两位国码形→country_code");
  assert.ok(lines.some((l) => /列7.*abuse_contact/.test(l) && /dataplane/.test(l)), "邮箱形→abuse_contact");
  assert.ok(lines.some((l) => /占位符「-」/.test(l) && /dashsrc/.test(l) && /None/.test(l)), "占位符惯例行(转 None 不入槽)");
  assert.ok(lines.some((l) => /is_malicious/.test(l) && /兄弟源同名字段/.test(l)), "roster 字段声明面惯例化");
  assert.ok(lines.every((l) => typeof l === "string" && l.trim()));
});

test("routingLines 宁少算:无兄弟源在用的槽不得冒称惯例(降级为草案行)", () => {
  const idx = buildSiblingIndex([SIB_FILES[0]], "x"); // 只有 bruteforce:reporter_count 在用,无 as_name/country_code/abuse_contact/first_seen
  const lines = routingLines({
    sampleLines: ["1.2.3.0\t24\t5307\tAS9 Foo\tCN\tabuse@x.org", "5.6.7.0\t24\t931\tAS8 Bar\tUS\tabuse@y.org", "9.9.9.0\t24\t480\tAS7 Baz\tDE\t-"],
    format: "tsv", rosterFields: [], category: "threat", index: idx,
  });
  assert.ok(lines.some((l) => /列3.*计数形/.test(l) && /reporter_count/.test(l) && /bruteforce/.test(l)), "有兄弟源在用→惯例行");
  for (const l of lines) {
    if (/as_name|country_code|abuse_contact/.test(l)) assert.match(l, /草案/, `无兄弟源在用的槽只许草案行:${l}`);
    assert.ok(!/同形惯例/.test(l) || !/as_name|country_code|abuse_contact/.test(l), `无兄弟源在用不得冒称惯例:${l}`);
  }
  assert.ok(lines.length > 0, "roster 空+惯例面仍非空(dossierShape 门)");
});

test("routingLines(csv 表头):同名列→同名槽位(f3csystems 形 first_seen/last_seen);非槽位列名不冒称", () => {
  const idx = buildSiblingIndex(SIB_FILES, "qcsv");
  const lines = routingLines({
    sampleLines: [
      "ip,first_seen,last_seen,scan_count,country,scanner_types",
      "1.2.3.4,2026-11-10 01:02:03,2026-11-11 04:05:06,7,FR,ssh",
      "5.6.7.8,2026-11-10 11:22:33,2026-11-11 05:06:07,3,DE,censys",
    ],
    format: "csv(表头)", rosterFields: ["is_malicious"], category: "threat", index: idx,
  });
  assert.ok(lines.some((l) => /列2「first_seen」.*first_seen 槽位/.test(l) && /f3csystems/.test(l)), "同名列→同名槽位并引兄弟源");
  assert.ok(lines.some((l) => /列3「last_seen」.*last_seen/.test(l)));
  assert.ok(!lines.some((l) => /scan_count 槽位|「scan_count」→ Evidence/.test(l)), "scan_count 非槽位列名不得冒称槽位");
  assert.ok(!lines.some((l) => /country_code 槽位/.test(l) && /同名列/.test(l)), "列名 country≠槽名 country_code:同名列面不命中(宁少算)");
});

test("routingLines ip 键豁免(#341 评审 P2-1):同名列/键名 ip 是 rebuild 键,不得被同名分支吞成 Evidence 槽位行", () => {
  const SIB_IPKEY = 'class Ipsrc(Source):\n    fields = ("is_malicious",)\n\n    def parse_row(self, row):\n        return {"ip": row[0], "reporter_count": row[1]}\n';
  const idx = buildSiblingIndex([...SIB_FILES, { name: "ipsrc", text: SIB_IPKEY }], "qcsv");
  assert.ok(idx.slots.get("ip"), "fixture 前提:ip 键入槽位表(真实仓当前无此面,防未来)");
  const lines = routingLines({
    sampleLines: ["ip,reporter_count", "1.2.3.4,7", "5.6.7.8,3"],
    format: "csv(表头)", rosterFields: [], category: "threat", index: idx,
  });
  assert.ok(lines.some((l) => /列1.*IP/.test(l) && /rebuild 键/.test(l)), `ip 列仍走 rebuild 键行:${lines[0]}`);
  assert.ok(!lines.some((l) => /「ip」→ Evidence/.test(l)), "同名列 ip 不得出槽位惯例行");
  const jsonLines = routingLines({
    sampleLines: ['{"ip": "1.2.3.4", "reporter_count": 7}', '{"ip": "5.6.7.8", "reporter_count": 3}'],
    format: "json", rosterFields: [], category: "threat", index: idx,
  });
  assert.ok(!jsonLines.some((l) => /「ip」→ Evidence/.test(l)), "json 面 ip 键同样豁免槽位行");
  assert.ok(jsonLines.some((l) => /「reporter_count」→ Evidence reporter_count 槽位/.test(l)), "非 ip 键照常路由");
});

test("routingLines(空白双列 ip+计数,ipsum 形):计数列→reporter_count;无列结构回退草案行", () => {
  const idx = buildSiblingIndex(SIB_FILES, "ipsum");
  const lines = routingLines({ sampleLines: ["1.2.3.4 11", "5.6.7.8 3", "9.9.9.9 2"], format: "text(空白分列)", rosterFields: ["is_malicious"], category: "threat", index: idx });
  assert.ok(lines.some((l) => /列2.*计数形/.test(l) && /reporter_count/.test(l) && /bruteforce/.test(l)));
  assert.ok(lines.some((l) => /列1.*IP/.test(l) && /rebuild/.test(l)));
  // 无列结构(裸 ip 列表):回退既有草案面
  const fallback = routingLines({ sampleLines: ["1.2.3.4", "5.6.7.8", "9.9.9.9"], format: "plain-ip-list", rosterFields: ["is_malicious"], category: "threat", index: idx });
  assert.deepEqual(fallback, routingDraftOf(["is_malicious"], "threat"), "裸 ip 列表无列面=原草案行为不变(向后兼容)");
});

test("routingLines(json):首对象键同名列惯例;解析失败/无命中回退草案面", () => {
  const idx = buildSiblingIndex(SIB_FILES, "qjson");
  const lines = routingLines({
    sampleLines: ['{"ip": "1.2.3.4", "first_seen": "2026-11-10", "conf": 80}', '{"ip": "5.6.7.8", "first_seen": "2026-11-11", "conf": 90}'],
    format: "json", rosterFields: ["is_malicious"], category: "threat", index: idx,
  });
  assert.ok(lines.some((l) => /「first_seen」.*first_seen 槽位/.test(l) && /f3csystems/.test(l)), "json 首对象键同名列→槽位惯例");
  assert.ok(!lines.some((l) => /conf 槽位|「conf」→ Evidence/.test(l)), "非槽位键不冒称");
  const bad = routingLines({ sampleLines: ["{not json", "{also not"], format: "json", rosterFields: ["is_malicious"], category: "threat", index: idx });
  assert.deepEqual(bad, routingDraftOf(["is_malicious"], "threat"), "json 解析失败=回退草案面(向后兼容)");
});

test("buildCard/genExamCards 惯例面接线:siblingFiles 注入→卡 field_routing 带惯例行+_provenance.siblings_scanned;考题自身源排除(答案无关)", async () => {
  const idx = buildSiblingIndex(SIB_FILES, "qone");
  const card = buildCard({
    row: { name: "qone", url: "https://qone.example/feed.txt", split: "evolve" },
    rosterEntry: { name: "qone", category: "threat", host: "qone.example", fields: ["is_malicious"] },
    metaEntry: { stale_days: 1 },
    sampleText: "1.2.3.0\t1.2.3.255\t24\t5307\tAS00000 Foo Telecom\tCN\tabuse@example.org\n5.6.7.0\t5.6.7.255\t24\t931\tAS11111 Bar Inc\tUS\tabuse@bar.net\n9.9.9.0\t9.9.9.255\t24\t480\tAS22222 Baz Ltd\tDE\tabuse@baz.io\n",
    endpoints: {}, fetchedAt: "now", siblingIndex: idx,
  });
  assert.equal(dossierShape(card).ok, true);
  assert.ok(card.field_routing.some((l) => /reporter_count/.test(l) && /bruteforce/.test(l)));
  assert.equal(card._provenance.siblings_scanned, 4, "扫描面(排考题自身与 _ 前缀)入档");
  assert.equal(card._provenance.endpoint_pending, false);
  // 程序面:考题自身源文件注入也不得被引用(答案无关纪律);另一题可引
  const fx = makeFixture();
  const outDir = path.join(fx.tmp, "cards-conv");
  const siblingFiles = [...SIB_FILES, { name: "qone", text: SIB_DP }]; // qone 自身=答案面
  const r = await genExamCards({
    universePath: fx.universePath, rosterText: fx.rosterText, metaDump: fx.metaDump,
    endpoints: {}, fetchImpl: async (u) => (u.includes("qone")
      ? "1.2.3.0\t1.2.3.255\t24\t5307\tAS00000 Foo\tCN\ta@b.c\n5.6.7.0\t5.6.7.255\t24\t931\tAS1 Bar\tUS\tc@d.e\n9.9.9.0\t9.9.9.255\t24\t480\tAS2 Baz\tDE\tf@g.h\n"
      : "1.2.3.4 11\n5.6.7.8 3\n9.9.9.9 2\n"),
    outDir, siblingFiles,
  });
  assert.deepEqual(r.failed, []);
  const qone = JSON.parse(fs.readFileSync(path.join(outDir, "qone.json"), "utf8"));
  assert.ok(!qone.field_routing.some((l) => l.includes("qone")), "考题自身源不得入惯例表(答案无关纪律)");
  assert.ok(qone.field_routing.some((l) => /reporter_count/.test(l) && /bruteforce/.test(l)), "兄弟源惯例行入卡");
  assert.equal(qone._provenance.siblings_scanned, 4);
  const qtwo = JSON.parse(fs.readFileSync(path.join(outDir, "qtwo.json"), "utf8"));
  assert.ok(qtwo.field_routing.some((l) => /reporter_count/.test(l)), "空白分列计数面也走惯例路由");
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});
