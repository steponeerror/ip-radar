#!/usr/bin/env node
// selftest-pipeline.mjs — P0 轮次状态机自测(spec #161 P0 验收门;零 API 零网络;P1 增⑦位等价门,#163;
// P2 增⑧-⑪ #164:规则库判例转写命中(R12 形/R7 形)+闭集负例+在飞真读 ops/items+matrix 裸失败负例)。
// 面:①全 faux 轮跑通到 CLOSE(信封 ok+gates.json 落盘+state 终态+stderr 阶段行+stdout 末行单行 JSON)
//    ②工件清单/分区穷尽/消化条目判例(refuted 恒 low)③预算降级(截尾非失败)④失败面(坏 fixture→
//    model_face 终态+工件保留)⑤replay:--dry 全程可跑+段重放,原件 md5 不变 ⑥CLI 契约(exit 0/1/2)
//    ⑦位等价门(P1,#163):同 stub 下 legacy health 轮(agent.mjs runRound→tools.mjs
//    health_snapshot 产 TSV+matrix 工件)与管线 PROBE 工件逐字节 diff 为空+计数两口径对拍。
//    ⑫面选择/真面(#170):selectModelFace 纯函数(fixtures→faux/缺省→real)+真面 fake 传输层
//    (pi-ai fauxProvider 注入 ctx.models,零网络)信封形状+失败面+预算三闸真面同执法。
// fixture:golden 同型(DOCS_ROOT/precedents 指 tmp+curl stub 前置 PATH);canned 模型回合=仓内
// fixtures/pipeline(README 配对契约)。输出 PIPEPASS/PIPEFAIL,任一 FAIL 退出非零。
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFileCb);
const AGENT = path.dirname(fileURLToPath(import.meta.url));
let pass = 0, fail = 0;
const ok = (name) => { pass++; console.log(`PIPEPASS ${name}`); };
const bad = (name, err) => { fail++; console.log(`PIPEFAIL ${name}: ${err}`); };
async function t(name, fn) { try { await fn(); ok(name); } catch (e) { bad(name, e.message); } }

// ── fixture(env 先于 pipeline.mjs/tools.mjs import;golden writePrecedents/stubCurl 同型)──
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "pipeline-selftest-"));
const DOCS = path.join(TMP, "docs");
const PREC = "2026-06-01-golden-aggregator.md"; // 与 fixtures/pipeline/synth.json 的引用配对(README 契约)
fs.mkdirSync(path.join(DOCS, "ops", "precedents"), { recursive: true });
fs.writeFileSync(path.join(DOCS, "ops", "precedents", PREC),
  `---\nid: 2026-06-01-golden-aggregator\ndate: 2026-06-01\nsubject: fixture — 聚合器候选必须实测排他率\ncontext: >\n  聚合器形状候选,上游映射推断重叠不可信。\nhuman_ruling: >\n  实测排他率 50.0%,推翻 REJECT,立项。\nreward:\n  hard_gates:\n    exclusive_rate: "50.0%"\n  ruling_agreement: overruled\n---\n\n正文检索词:聚合器 排他率 回声 冻结 违例。\n`);
fs.writeFileSync(path.join(DOCS, "ops", "precedents", "_schema.md"), "schema 说明(注入排除面)。\n");
fs.mkdirSync(path.join(DOCS, "ops", "rules"), { recursive: true });
fs.writeFileSync(path.join(DOCS, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
  { id: "R1", adopted: "2026-10-24", adopted_via: "item-fixture", match: { bucket: "frozen", url_shape: "*dshield.org*" },
    action: "suppress", note: "fixture:dshield 冻结读数为已知探测伪迹", review_at: "2027-01-24" } ] }, null, 2) + "\n");
const STUBS = path.join(TMP, "stubs");
fs.mkdirSync(STUBS);
fs.writeFileSync(path.join(STUBS, "curl"), `#!/usr/bin/env bash\n# selftest stub:curl 传输层替身(golden stubCurl 同型);三冻结锚点+其余新鲜\nurl="\${@: -1}"\nd=30\ncase "$url" in\n  *cinsscore*) d=220 ;;\n  *binarydefense*) d=210 ;;\n  *dshield*) d=200 ;;\nesac\nprintf 'HTTP/1.1 200 OK\\r\nLast-Modified: %s\\r\nContent-Length: 4\\r\n\\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - d * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"\nexit 0\n`);
fs.chmodSync(path.join(STUBS, "curl"), 0o755);
// matrix stub:OPS_EVAL_PY 替身(golden stubPy 同型);位等价两腿(legacy health_snapshot 腿与
// 管线 PROBE 腿)共用同一罐装矩阵 JSON。curl stub 时间确定性=UTC 日界截断(#163 位等价判例):
// 同 UTC 日内 Last-Modified 字符串恒定且 age_days 恒=d(日内秒数<86400),两腿先后跑字节稳定;
// 跨日界仅两腿间隙窗口(秒级)理论可达。
const MATRIX_CANNED = { exit_code: 0, counts: { violation: 0, pending: 0, agreement: 4 },
  layers: { truth: { status: "OK", members: 4, sampled: 4, notes: [] }, infra: { status: "OK", members: 8, sampled: 8, notes: [] } },
  buckets: { violation: [], pending: [], agreement: [] } };
// 罐装锚巡检(#182 faux 查询面):事故判例形——8.8.8.8=myip_ms 单源指控/114DNS=
// cps+ziyadnz 假印证双 finding(#183 整改前形状,票 #182 明示 fixture 不依赖整改);
// 锚集镜像 anchors.py 扩员后 19 员(形状钉,门只验工件内自洽——锚集真源=python 勿在此改)。
const SWEEP_ANCHORS = [["8.8.8.8", "clean"], ["8.8.4.4", "clean"], ["1.1.1.1", "clean"], ["1.0.0.1", "clean"],
  ["9.9.9.9", "clean"], ["208.67.222.222", "clean"], ["114.114.114.114", "clean"], ["223.5.5.5", "clean"],
  ["9.9.9.4", "clean"], ["10.0.0.1", "reserved"], ["127.0.0.1", "reserved"], ["192.168.1.1", "reserved"],
  ["172.16.0.1", "reserved"], ["185.220.101.1", "tor"], ["171.25.193.78", "tor"], ["185.220.101.34", "tor"],
  ["52.95.116.115", "hosting"], ["20.36.253.52", "hosting"], ["34.64.121.1", "hosting"]];
const sweepIncident = (ip) => ({ ip, expect: "clean", ok: false, reason: "expected clean, got malicious",
  verdict: "malicious", confidence: 55, conflict: false,
  accusers: ip === "8.8.8.8" ? ["myip_ms"] : ["cps_collected_iocs", "ziyadnz"] });
const SWEEP_CANNED = { kind: "anchor_sweep", anchors: SWEEP_ANCHORS, n_total: SWEEP_ANCHORS.length, n_fail: 2,
  failures: ["8.8.8.8", "114.114.114.114"].map((ip) => ({ ip, expect: "clean", reason: "expected clean, got malicious" })),
  results: SWEEP_ANCHORS.map(([ip, expect]) => ip === "8.8.8.8" || ip === "114.114.114.114" ? sweepIncident(ip)
    : { ip, expect, ok: true, reason: null, verdict: "benign", confidence: 0, accusers: [], conflict: false }) };
const SHELL_JSON = (o) => `'${JSON.stringify(o).replace(/'/g, "'\\''")}'`;
fs.writeFileSync(path.join(STUBS, "py-matrix"), `#!/usr/bin/env bash
# selftest stub:OPS_EVAL_PY 替身(golden stubPy 同型);--anchor-sweep→罐装锚巡检 JSON(#182),其余→罐装矩阵 JSON
case " $* " in
  *--anchor-sweep*) printf '%s\n' ${SHELL_JSON(SWEEP_CANNED)} ;;
  *) printf '%s\n' ${SHELL_JSON(MATRIX_CANNED)} ;;
esac
`);
fs.chmodSync(path.join(STUBS, "py-matrix"), 0o755);
process.env.DOCS_ROOT = DOCS;
process.env.PRECEDENTS_DIR = path.join(DOCS, "ops", "precedents");
process.env.LEDGER_FILE = path.join(DOCS, "ops", "ledger.md");
process.env.OPS_EVAL_PY = path.join(STUBS, "py-matrix"); // import-time 面:先于 tools.mjs 装载生效
process.env.OPS_SWEEP_DRY_RUN = "1"; // #184:测试恒 dry-run(gh/webhook 出口零外发,只记 cmd/payload;票面默认关=生产真发)
process.env.PATH = `${STUBS}:${process.env.PATH}`;

const { runPipeline, HEALTH_PIPELINE, DEFAULT_FIXTURES_DIR } = await import("./pipeline.mjs");
const { runModelStep, selectModelFace, STEP_ROUND } = await import("./pipeline/faux.mjs"); // #170 面选择/真面注入缝直调单测面
const { ERROR_CODES } = await import("./agent.mjs");
const steps = await import("./pipeline/steps.mjs"); // P2 #164 直调 VERIFY 步(规则库/在飞面单元例)
const fexit = await import("./pipeline/finding-exit.mjs"); // #184 finding 出口三件套(直调单测面;RED 面应先红)
const R1 = "2026-10-23-2340-health";
const mkIo = () => { const buf = { stdout: "", stderr: "" };
  return { stdout: { write: (s) => { buf.stdout += s; return true; } }, stderr: { write: (s) => { buf.stderr += s; return true; } }, buf }; };
const j = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const roundDir = (id) => path.join(DOCS, "ops", "rounds", id);
const stageOf = (env, name) => env.pipeline.stages.find((s) => s.name === name);
const treeMd5 = (dir) => [...fs.readdirSync(dir).sort().map((f) => {
  const p = path.join(dir, f);
  return fs.statSync(p).isDirectory() ? `${f}/:${treeMd5(p)}` : `${f}:${fs.readFileSync(p).toString("base64").slice(0, 9999)}`;
})].join("|");
const spawnPipe = (args, env = {}) => execFileP(process.execPath, [path.join(AGENT, "pipeline.mjs"), ...args],
  { timeout: 300_000, maxBuffer: 32 * 1024 * 1024, env: { ...process.env, ...env } })
  .then((r) => ({ rc: 0, ...r })).catch((e) => ({ rc: typeof e.code === "number" ? e.code : -1, stdout: e.stdout ?? "", stderr: e.stderr ?? "" }));

// P4 #166:逐轮独立 DOCS 树——条目库真写 ops/items,轮间在飞面须隔离(R1 轮的条目不能抑制
// 后续轮的 VERIFY;每轮一棵树=每轮一个干净世界)。fixtures 克隆+synth 补丁件同批上移。
const cloneFixtures = (name) => { const fx = path.join(TMP, name); fs.mkdirSync(fx, { recursive: true });
  fs.copyFileSync(path.join(AGENT, "fixtures/pipeline/triage.json"), path.join(fx, "triage.json"));
  fs.copyFileSync(path.join(AGENT, "fixtures/pipeline/synth.json"), path.join(fx, "synth.json"));
  fs.cpSync(path.join(AGENT, "fixtures/pipeline/deep"), path.join(fx, "deep"), { recursive: true });
  return fx; };
const writeSynthFx = (fx, reportText) => fs.writeFileSync(path.join(fx, "synth.json"),
  JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: reportText }], stopReason: "stop" }] }));


const mkTree = (name) => { // 逐轮独立 DOCS 树(P4 #166):precedents/rules 同 R1 fixture,轮间零污染
  const root = path.join(TMP, name);
  fs.mkdirSync(path.join(root, "ops", "precedents"), { recursive: true });
  fs.copyFileSync(path.join(DOCS, "ops", "precedents", PREC), path.join(root, "ops", "precedents", PREC));
  fs.copyFileSync(path.join(DOCS, "ops", "precedents", "_schema.md"), path.join(root, "ops", "precedents", "_schema.md"));
  fs.mkdirSync(path.join(root, "ops", "rules"), { recursive: true });
  fs.copyFileSync(path.join(DOCS, "ops", "rules", "suppressions.json"), path.join(root, "ops", "rules", "suppressions.json"));
  return { root, env: { ...process.env, DOCS_ROOT: root, PRECEDENTS_DIR: path.join(root, "ops", "precedents"), LEDGER_FILE: path.join(root, "ops", "ledger.md") } };
};
let run1;
await t("全 faux 轮:十执行态到 CLOSE,信封 ok+形状只增 pipeline 扩展,顶层 usage=模型步之和", async () => {
  const io = mkIo();
  run1 = await runPipeline({ roundId: R1, fixturesDir: DEFAULT_FIXTURES_DIR, ...io }); // 显式 fixtures=faux 面(#170;同缺省路径,行为不变)
  assert.equal(run1.ok, true);
  const env = run1.envelope;
  assert.equal(env.ok, true);
  assert.equal(env.round, "health");
  assert.deepEqual(Object.keys(env).sort(), ["ok", "pipeline", "pkg", "queue_writes", "round", "usage", "verify"]);
  assert.equal(env.pipeline.round_id, R1);
  assert.equal(env.pipeline.replayed_of, null);
  assert.deepEqual(env.pipeline.stages.map((s) => s.name), HEALTH_PIPELINE.filter((d) => d.kind !== "terminal").map((d) => d.name));
  assert.ok(env.pipeline.stages.every((s) => ["done", "skipped", "degraded"].includes(s.status)), "成功轮 stage 状态闭集");
  const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
  for (const s of env.pipeline.stages) { // 脚本步 usage=null;模型步数字;顶层=模型步之和
    if (s.usage === null) continue;
    for (const k of Object.keys(sum)) { assert.equal(typeof s.usage[k], "number", `${s.name}.${k}`); sum[k] += s.usage[k]; }
  }
  assert.equal(env.pipeline.stages.filter((s) => s.usage !== null).length, 3, "恰三个模型步带 usage");
  const deepStage = stageOf(env, "DEEP");
  assert.equal(deepStage.status, "done", "DEEP 真开启 P4 #166(逐假设单发,零降级)");
  assert.equal(deepStage.attempts, 2, "两假设各一发");
  assert.deepEqual(env.usage, sum);
  assert.ok(fs.existsSync(env.pkg), "pkg(07-synth-report.md)存在");
  assert.deepEqual(env.queue_writes, []);
  assert.equal(env.verify.ok, true);
  assert.equal(env.verify.cited, 1, "canned 报告引 1 fixture 判例");
});

await t("工件清单全落盘+gates.json 十记录全 PASS+state.json 终态 done/CLOSE+原子写无 .tmp 残留", async () => {
  const d = roundDir(R1);
  for (const f of ["01-probe-freshness.tsv", "01-probe-matrix.json", "01-probe-summary.json", "02-verify-survivors.json",
    "02-verify-suppressed.json", "03-triage-hypotheses.json", "03-triage-transcript.jsonl", "04-dispatch-bundles.json",
    "05-deep-verdicts.json", "06-itemize-manifest.json", "07-synth-report.md", "07-synth-transcript.jsonl",
    "08-anchor-sweep.json", "08-anchor-sweep-exits.json", "gates.json", "state.json"])
    assert.ok(fs.existsSync(path.join(d, f)), `工件缺:${f}`);
  assert.ok(fs.readdirSync(d).some((f) => /^05-deep-.*\.json$/.test(f) && f !== "05-deep-verdicts.json"), "逐假设工件");
  assert.ok(fs.readdirSync(d).some((f) => /^05-deep-.*-transcript\.jsonl$/.test(f)), "逐假设 transcript");
  const g = j(path.join(d, "gates.json"));
  assert.equal(g.round_id, R1);
  assert.equal(g.records.length, 10, "9 可跑步门(含 #182 ANCHOR_SWEEP)+G_CLOSE");
  assert.ok(g.records.every((r) => r.pass === true), `门败:${g.records.filter((r) => !r.pass).map((r) => r.name).join(",")}`);
  assert.ok(g.records.every((r) => typeof r.reason === "string" && /\d/.test(r.reason)), "reason 带数字可回算");
  assert.deepEqual(g.records.map((r) => r.name), ["G_PROBE", "G_VERIFY", "G_TRIAGE", "G_DISPATCH", "G_DEEP", "G_ITEMIZE", "G_SYNTH", "G_ANCHOR_SWEEP", "G_RETRO", "G_CLOSE"]);
  const st = j(path.join(d, "state.json"));
  assert.equal(st.status, "done");
  assert.equal(st.stage, "CLOSE");
  assert.equal(st.schema, 1);
  assert.ok(Object.keys(st.prompt_hashes).length >= 3, "模型步 prompt hash 入 state(replay 审计面)");
  const walk = (p) => fs.readdirSync(p).flatMap((f) => { const q = path.join(p, f); return fs.statSync(q).isDirectory() ? walk(q) : [q]; });
  assert.ok(!walk(d).some((p) => p.endsWith(".tmp")), "原子写无 .tmp 残留");
  assert.ok(fs.existsSync(path.join(DOCS, "ops", "retro", `${R1}.json`)), "retro 工件(ops/retro/)");
});

await t("ANCHOR_SWEEP 巡检步(#182):事故判例 finding 在场门仍过——工件=全集投影逐锚读数+G 门不持门;步序 SYNTH 后 RETRO 前(finding 先于台账收口)", async () => {
  const d = roundDir(R1);
  const s = j(path.join(d, "08-anchor-sweep.json")); // 工件可查(票验收)
  assert.equal(s.kind, "anchor_sweep");
  assert.equal(s.n_total, SWEEP_ANCHORS.length);
  assert.equal(s.anchors.length, s.results.length, "锚集=结果集同长(全集投影)");
  // 投影穷尽:每锚恰一结果(ip|expect 双键)
  const want = SWEEP_ANCHORS.map(([ip, exp]) => `${ip}|${exp}`).sort().join(",");
  const got = s.results.map((r) => `${r.ip}|${r.expect}`).sort().join(",");
  assert.equal(got, want, "逐锚恰一结果(丢锚/重锚即门败面)");
  for (const r of s.results) {
    assert.equal(typeof r.verdict, "string", `${r.ip} verdict 字符串`);
    assert.equal(typeof r.confidence, "number", `${r.ip} confidence 数字`);
    assert.ok(Array.isArray(r.accusers) && r.accusers.every((a) => typeof a === "string"), `${r.ip} accusers 字符串数组`);
    assert.equal(typeof r.ok, "boolean");
  }
  assert.equal(s.n_fail, 2, "罐装事故判例:8.8.8.8+114DNS 双 finding(#183 整改前形状)");
  assert.equal(s.failures.length, 2, "failures 与 n_fail 回算一致");
  const byIp = new Map(s.results.map((r) => [r.ip, r]));
  assert.deepEqual(byIp.get("8.8.8.8").accusers, ["myip_ms"], "事故面①:myip_ms 单源指控");
  const r114 = byIp.get("114.114.114.114");
  assert.deepEqual(r114.accusers, ["cps_collected_iocs", "ziyadnz"], "事故面②:双聚合器假印证");
  assert.equal(r114.confidence, 55);
  assert.ok(s.results.every((r) => ["8.8.8.8", "114.114.114.114"].includes(r.ip) ? !r.ok : r.ok), "finding/ok 逐锚独立");
  const g = j(path.join(d, "gates.json"));
  const rec = g.records.find((x) => x.name === "G_ANCHOR_SWEEP");
  assert.equal(rec.pass, true, `finding 不持门(票义):${rec.reason}`);
  assert.match(rec.reason, /n_total=\d+ n_fail=2/, "门 reason 带数字可回算");
  // 步序:SYNTH → ANCHOR_SWEEP → RETRO(finding 先于台账收口;C稿 §2.2 加状态经 spec #180/#182 授权)
  const names = j(path.join(d, "state.json")).stages.map((x) => x.name);
  assert.equal(names.indexOf("ANCHOR_SWEEP") - names.indexOf("SYNTH"), 1, "SYNTH 后紧随");
  assert.equal(names.indexOf("RETRO") - names.indexOf("ANCHOR_SWEEP"), 1, "RETRO 前");
  const sw = stageOf(run1.envelope, "ANCHOR_SWEEP");
  assert.equal(sw.status, "done", "finding 在场=正常完成非降级(读数面)");
  assert.equal(sw.usage, null, "脚本步无 token 面");
});

// ── 票 #184(finding 出口三件套)单元例:纯函数面+出口编排(dry-run/skip/失败面;零网络零外发)──
// 真扫活 finding 判例形(#184 票面指针:#182 首扫 n_fail=4 中的两新 finding,2026-10-24;
// 与 #182 罐装事故判例(8.8.8.8/114DNS 整改前形状)分立——本批钉的是「整改后仍活的出口租户」;
// #188 benign② 终态:223.5.5.5=tweetfeed 指控× infra_services 良性断言同场 → conflict=true
// 留痕人裁(锚仍 finding,宁少算不自动压制)
const LIVE_FINDINGS = [
  { ip: "1.1.1.1", expect: "clean", verdict: "malicious", confidence: 55, accusers: ["cps_collected_iocs"], conflict: false },
  { ip: "223.5.5.5", expect: "clean", verdict: "malicious", confidence: 55, accusers: ["tweetfeed"], conflict: true } ];
const liveSweepD = { kind: "anchor_sweep", n_total: 19, n_fail: 2, results: [
  ...LIVE_FINDINGS.map((f) => ({ ...f, ok: false })),
  { ip: "8.8.8.8", expect: "clean", ok: true, verdict: "benign", confidence: 0, accusers: [] }] };
await t("finding 出口:parseFindings——形状自洽才投影(坏行/计数不符=不动作宁少算,门接管)", async () => {
  assert.equal(typeof fexit.parseFindings, "function", "parseFindings 未导出(RED 面应先红)");
  const p = fexit.parseFindings(liveSweepD);
  assert.equal(p.ok, true);
  assert.deepEqual(p.findings, LIVE_FINDINGS, "投影恰指控行(ip/expect/verdict/confidence/accusers/conflict)");
  assert.equal(p.findings.find((f) => f.ip === "223.5.5.5").conflict, true, "#188 终态:良性断言×指控同场 conflict 留痕出海");
  const badRow = { n_fail: 1, results: [{ ip: "1.1.1.1", expect: "clean", ok: false, verdict: "malicious" }] };
  assert.equal(fexit.parseFindings(badRow).ok, false, "finding 行缺 confidence/accusers=形状破,出口不动作");
  const mismatch = { n_fail: 2, results: liveSweepD.results.slice(0, 1) };
  assert.equal(fexit.parseFindings(mismatch).ok, false, "n_fail≠回算=工件自洽破,出口不动作(G_ANCHOR_SWEEP 拦)");
});
await t("finding 出口:issue 模板四件(来源步/锚:期望vs实得/证据指针/needs-triage)——真扫活 finding 判例形", async () => {
  assert.equal(typeof fexit.findingIssueDraft, "function", "findingIssueDraft 未导出(RED 面应先红)");
  const dft = fexit.findingIssueDraft({ roundId: "2026-10-24-0400-health", findings: LIVE_FINDINGS, nTotal: 19 });
  assert.match(dft.title, /^\[anchor-sweep\] 2 finding\(2026-10-24-0400-health\)$/);
  assert.match(dft.body, /## 来源步/, "模板件①来源步");
  assert.match(dft.body, /ANCHOR_SWEEP/);
  assert.match(dft.body, /## 锚:期望 vs 实得/, "模板件②锚:期望vs实得");
  assert.match(dft.body, /1\.1\.1\.1\(expect=clean\):实得 verdict=malicious confidence=55 指控源=cps_collected_iocs\n/, "非对立行不带对立标记(词表律:一处一拼)");
  assert.match(dft.body, /223\.5\.5\.5.*tweetfeed.*对立=verdict_conflict.*留痕人裁.*宁少算不自动压制指控/, "#188 终态:对立标记随行出海(issue=人裁面)");
  assert.match(dft.body, /## 证据指针/, "模板件③证据指针");
  assert.match(dft.body, /08-anchor-sweep\.json/);
  assert.deepEqual(dft.labels, ["needs-triage"], "模板件④标签=needs-triage");
  assert.match(dft.body, /只写不动作/, "处置面自声明:出口只写不动作");
});
await t("G_ANCHOR_SWEEP conflict 形状面单元例(直构工件,#188):conflict 非布尔/缺席=门败;留痕行(conflict=true)不持门照常过", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "ganchor-unit-"));
  const row = (ip, o = {}) => ({ ip, expect: "clean", ok: true, reason: null, verdict: "benign", confidence: 0, accusers: [], ...o });
  const write = (results) => { const fails = results.filter((r) => !r.ok).map((r) => ({ ip: r.ip, expect: r.expect, reason: r.reason }));
    fs.writeFileSync(path.join(d, "08-anchor-sweep.json"),
    JSON.stringify({ kind: "anchor_sweep", anchors: results.map((r) => [r.ip, r.expect]), n_total: results.length, n_fail: fails.length, failures: fails, results })); };
  write([row("8.8.8.8")]);
  assert.equal(GATES.G_ANCHOR_SWEEP({ dir: d }).pass, false, "conflict 缺席(#188 前工件)=门败——形状面严格");
  assert.match(GATES.G_ANCHOR_SWEEP({ dir: d }).reason, /conflict 非布尔/);
  write([row("8.8.8.8", { conflict: 1 })]);
  assert.equal(GATES.G_ANCHOR_SWEEP({ dir: d }).pass, false, "conflict 非布尔=门败");
  write([row("8.8.8.8", { conflict: true }), row("223.5.5.5", { ok: false, reason: "expected clean, got malicious", verdict: "malicious", confidence: 55, accusers: ["tweetfeed"], conflict: true })]);
  const g = GATES.G_ANCHOR_SWEEP({ dir: d });
  assert.equal(g.pass, true, "conflict=true 留痕行不持门照常过(宁少算)");
  assert.match(g.reason, /conflicts=2/, "门 reason 带 conflicts 计数可回算");
});;
await t("finding 出口:runFindingExits——dry-run 双出口零外发只记 cmd/payload;webhook 未配置=skip 留痕;finding=0/降级/replay=不触发", async () => {
  assert.equal(typeof fexit.runFindingExits, "function", "runFindingExits 未导出(RED 面应先红)");
  const calls = [];
  const fakeExec = async (bin, argv) => { calls.push({ bin, argv }); return { stdout: "" }; };
  const d1 = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-1-"));
  const d2 = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-2-"));
  const d3 = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-3-"));
  const d4 = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-4-"));
  const d5 = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-5-"));
  // ①dry-run+webhook 未配置(测试环境缺省面)
  const r1 = await fexit.runFindingExits({ roundId: "2026-10-24-0400-health", sweepD: liveSweepD, dir: d1, env: { OPS_SWEEP_DRY_RUN: "1" } });
  assert.equal(r1.triggered, true, "触发面=finding>0(#184 要点)");
  assert.equal(r1.findings_n, 2);
  assert.equal(r1.dry_run, true);
  assert.equal(r1.gh_issue.status, "dry_run", "dry-run:gh 只记将发命令");
  assert.match(r1.gh_issue.cmd_head, /gh issue create --title/, "cmd 留痕可审计");
  assert.equal(r1.webhook.status, "skip", "IP_RADAR_ALERT_URLS 未配置=降级跳过不报错");
  assert.match(r1.webhook.reason, /IP_RADAR_ALERT_URLS/, "skip 痕点名 env(信封留痕同源)");
  assert.deepEqual(calls, [], "dry-run+未配置=零 spawn 零外发");
  // ①续:出口工件全稿留痕(证据不灭失;含 issue 标题/正文/标签)
  const art1 = j(path.join(d1, "08-anchor-sweep-exits.json"));
  assert.equal(art1.phase, "emitted");
  assert.equal(art1.issue.labels[0], "needs-triage");
  assert.match(art1.issue.body, /## 锚:期望 vs 实得/);
  assert.equal(art1.webhook_payload.title, art1.issue.title, "webhook 与 issue 同稿同源(单一事实)");
  // ②dry-run+webhook 配置(payload 留痕+URL 脱敏)
  const r2 = await fexit.runFindingExits({ roundId: "2026-10-24-0401-health", sweepD: liveSweepD, dir: d2,
    env: { OPS_SWEEP_DRY_RUN: "1", IP_RADAR_ALERT_URLS: "https://hooks.example/x.json lark://1234/abcdef99" } });
  assert.equal(r2.webhook.status, "dry_run");
  assert.equal(r2.webhook.urls_n, 2, "逗号/空白分隔同 _alerts.py apprise 同形");
  assert.ok(r2.webhook.urls_redacted.every((u) => !u.includes("abcdef99")), "URL 脱敏(凭据不入记录;_alerts._redact_url 同律)");
  assert.deepEqual(calls, [], "dry-run 零外发");
  // ③finding=0(金标全绿轮)
  const r3 = await fexit.runFindingExits({ roundId: "2026-10-24-0402-health", sweepD: { n_fail: 0, results: liveSweepD.results.filter((x) => x.ok) }, dir: d3, env: {} });
  assert.equal(r3.triggered, false);
  assert.equal(r3.gh_issue.status, "skip");
  assert.equal(r3.webhook.status, "skip");
  // ④sweep 降级(求值面死→无读数即无 finding)
  const r4 = await fexit.runFindingExits({ roundId: "2026-10-24-0403-health", sweepD: null, dir: d4, env: {} });
  assert.equal(r4.triggered, false);
  assert.match(r4.reason, /degraded/);
  // ⑤replay 零外发(审计重放不改生产出口面;ITEMIZE 回声律同款)
  const r5 = await fexit.runFindingExits({ roundId: "2026-10-24-0400-health-r1", sweepD: liveSweepD, dir: d5, env: {}, replayOf: "2026-10-24-0400-health" });
  assert.equal(r5.triggered, false, "replay 不外发");
  assert.match(r5.reason, /replay/);
  assert.equal(r5.gh_issue.status, "skip");
  assert.match(r5.gh_issue.reason, /replay/);
  assert.equal(r5.webhook.status, "skip");
  assert.deepEqual(calls, [], "全程零 spawn(①-⑤)");
});
await t("finding 出口:gh/apprise 失败=失败信封记入不抛(出口永不败轮);emit 守卫防重发", async () => {
  const fakeExec = async (bin) => {
    if (bin === "gh") throw Object.assign(new Error("spawn"), { code: 1, stderr: "gh: GraphQL: Projects (classic) is being deprecated" });
    if (bin === "apprise") throw Object.assign(new Error("spawn"), { code: 1, stderr: "apprise: Could not load notification (fixture)" });
    throw new Error(`unexpected bin ${bin}`);
  };
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-f-"));
  const r = await fexit.runFindingExits({ roundId: "2026-10-24-0404-health", sweepD: liveSweepD, dir: d,
    env: { OPS_SWEEP_DRY_RUN: "0", IP_RADAR_ALERT_URLS: "https://hooks.example/x.json" }, exec: fakeExec });
  assert.equal(r.triggered, true, "触发面=finding>0(与通道成败分立)");
  assert.equal(r.gh_issue.status, "failed");
  assert.equal(r.gh_issue.code, "gh_error");
  assert.equal(r.webhook.status, "failed");
  assert.ok(!r.webhook.reason.includes("hooks.example/x.json"), "失败 reason 不裸 URL(脱敏)");
  // emit 守卫:同轮同 dir 已 emitted → 重入不再外发(resume 崩溃窗防重发;宁少算交人工核对)
  const calls2 = [];
  const r6 = await fexit.runFindingExits({ roundId: "2026-10-24-0404-health", sweepD: liveSweepD, dir: d,
    env: { OPS_SWEEP_DRY_RUN: "0" }, exec: async (...a) => { calls2.push(a); return { stdout: "" }; } });
  assert.equal(r6.gh_issue.status, "skip");
  assert.match(r6.reason, /emit/);
  assert.deepEqual(calls2, [], "已发轮重入零外发");
  // M4(终审修单第二轮):守卫触发不重写工件——emitted 全稿存活(哲学1 证据永不灭失),且同窗
  // 二次重入仍读 emitted 恒守卫(旧实现写回 phase=skip,二次崩溃窗守卫读 skip 误判首程→重发→重复外发)
  const art6 = j(path.join(d, "08-anchor-sweep-exits.json"));
  assert.equal(art6.phase, "emitted", "守卫不重写工件:phase 仍 emitted(非 skip)");
  assert.match(art6.issue.title, /^\[anchor-sweep\]/, "issue 全稿存活(标题在场)");
  assert.ok(art6.webhook_payload?.title, "webhook_payload 存活");
  assert.equal(art6.gh_issue.status, "failed", "首轮失败信封同存活(证据不灭失)");
  const calls2b = [];
  const r6b = await fexit.runFindingExits({ roundId: "2026-10-24-0404-health", sweepD: liveSweepD, dir: d,
    env: { OPS_SWEEP_DRY_RUN: "0" }, exec: async (...a) => { calls2b.push(a); return { stdout: "" }; } });
  assert.match(r6b.reason, /emit_guard/, "同窗二次重入仍守卫");
  assert.deepEqual(calls2b, [], "同窗二次重入零外发(守卫幂等)");
  assert.equal(j(path.join(d, "08-anchor-sweep-exits.json")).phase, "emitted", "二次重入工件仍 emitted");
  // emit 守卫(中截面):同轮工件停在 emitting(外发中崩溃)→ 同样不重发(状态不可知,宁少算)
  const d7 = fs.mkdtempSync(path.join(os.tmpdir(), "fexit-g-"));
  fs.writeFileSync(path.join(d7, "08-anchor-sweep-exits.json"),
    JSON.stringify({ round_id: "2026-10-24-0405-health", phase: "emitting", findings_n: 2 }) + "\n");
  const calls3 = [];
  const r7 = await fexit.runFindingExits({ roundId: "2026-10-24-0405-health", sweepD: liveSweepD, dir: d7,
    env: { OPS_SWEEP_DRY_RUN: "0" }, exec: async (...a) => { calls3.push(a); return { stdout: "" }; } });
  assert.equal(r7.gh_issue.status, "skip");
  assert.match(r7.reason, /emit_guard/);
  assert.deepEqual(calls3, [], "中崩窗零重发(人工核对,漏发下轮补)");
  const art7 = j(path.join(d7, "08-anchor-sweep-exits.json"));
  assert.equal(art7.phase, "emitting", "中崩截面工件不被守卫重写(原样留证)");
  assert.equal(art7.findings_n, 2, "中崩截面原记录字段存活");
});


await t("finding 出口三件套轮内接线(#184):dry-run faux 轮三出口全绿——信封 pipeline.finding_exits 留痕(gh dry_run/webhook skip)+RETRO 摘要行+出口工件", async () => {
  // 依托 R1 全 faux 轮(罐装事故判例 2 finding;OPS_SWEEP_DRY_RUN=1 fixture 恒 dry-run)
  const env = run1.envelope;
  const fe = env.pipeline.finding_exits;
  assert.ok(fe, "信封 pipeline.finding_exits 在场(只增 pipeline 扩展字段;顶层键面不变)");
  assert.equal(fe.triggered, true, "触发面=ANCHOR_SWEEP finding>0");
  assert.equal(fe.findings_n, 2);
  assert.equal(fe.dry_run, true, "测试恒 dry-run");
  assert.equal(fe.gh_issue.status, "dry_run");
  assert.equal(fe.webhook.status, "skip", "IP_RADAR_ALERT_URLS 未配置=降级跳过不报错,轮仍成功");
  assert.equal(fe.retrospective_summary.status, "counted", "出口③:RETRO 摘要行计入");
  assert.equal(fe.retrospective_summary.n_fail, 2);
  // 出口工件:全稿留痕(证据不灭失)+脱敏面
  const art = j(path.join(roundDir(R1), "08-anchor-sweep-exits.json"));
  assert.equal(art.phase, "emitted");
  assert.deepEqual(art.issue.labels, ["needs-triage"]);
  assert.match(art.issue.body, /## 来源步[\s\S]*## 锚:期望 vs 实得[\s\S]*## 证据指针/, "模板三节齐");
  assert.match(art.issue.body, /8\.8\.8\.8.*myip_ms/, "事故判例形入稿");
  assert.equal(art.webhook_payload.title, art.issue.title);
  // RETRO 摘要工件:finding 计入(出口③真源)
  const retro = j(path.join(DOCS, "ops", "retro", `${R1}.json`));
  assert.equal(retro.anchor_sweep.status, "ok");
  assert.equal(retro.anchor_sweep.n_fail, 2);
  assert.equal(retro.anchor_sweep.findings.length, 2);
  assert.deepEqual(retro.anchor_sweep.findings.map((f) => f.ip).sort(), ["114.114.114.114", "8.8.8.8"]);
  // state 留痕(resume 面不丢)
  const st = j(path.join(roundDir(R1), "state.json"));
  assert.equal(st.finding_exits.findings_n, 2);
});
await t("finding 出口:webhook 配置面轮内 dry-run(IP_RADAR_ALERT_URLS→payload 留痕/URL 脱敏零泄漏)", async () => {
  const t9 = mkTree("tree-exits-webhook");
  const r = await runPipeline({ roundId: "2026-10-24-0406-health", fixturesDir: cloneFixtures("fx-exits-wh"),
    env: { ...t9.env, IP_RADAR_ALERT_URLS: "https://hooks.example/h.json mailto:alerts@example.com" }, ...mkIo() });
  assert.equal(r.ok, true, `轮仍成功:${r.envelope?.error?.message ?? ""}`);
  const fe = r.envelope.pipeline.finding_exits;
  assert.equal(fe.triggered, true);
  assert.equal(fe.webhook.status, "dry_run");
  assert.equal(fe.webhook.urls_n, 2, "逗号/空白分隔多 URL 同 _alerts.py apprise 同形");
  const d = path.join(t9.root, "ops", "rounds", "2026-10-24-0406-health");
  const art = j(path.join(d, "08-anchor-sweep-exits.json"));
  const flat = JSON.stringify(fe) + JSON.stringify(art);
  assert.ok(!flat.includes("hooks.example/h.json") && !flat.includes("mailto:alerts@example.com"), "凭据 URL 零泄漏(信封+工件全脱敏)");
});
await t("出口只写不动作(结构性,#184):finding 出口模块依赖面闭集——spawn 目标恰 apprise(gh 在 tools.mjs,argv 钉 [issue,create])、禁面符号零在场(调权/停源/写数据面/源管理 API)", async () => {
  const srcExit = fs.readFileSync(path.join(AGENT, "pipeline", "finding-exit.mjs"), "utf8");
  // a) 公开面闭集(依赖面测试:export 恰三函数,无隐藏写口)
  assert.deepEqual(Object.keys(fexit).sort(), ["findingIssueDraft", "parseFindings", "runFindingExits"], "export 闭集(新增写口须过 spec)");
  // b) spawn 目标白名单:模块内直接 exec 恰 apprise(webhook 出口;gh 面=tools.mjs ghIssueCreate,t4 argv 捕获钉死)
  const spawnTargets = [...srcExit.matchAll(/[^.\w]exec\w*\(\s*"([a-z0-9_-]+)"/g)].map((m) => m[1]);
  assert.deepEqual(spawnTargets, ["apprise"], `spawn 目标白名单(实测:${spawnTargets.join(",")})`);
  // c) 禁面符号:从 finding 出发不可达的动作面(调权/停源/写数据面/源管理 API/规则库写口)
  const banned = ["/api/sources", "_calibrated", "reliability", "rebuild", "lmdb", "IP_RADAR_DATA_DIR",
    "adopt_rule", "suppressions", "write_ruling", "PATCH /api"];
  for (const b of banned) assert.ok(!srcExit.includes(b), `禁面符号在场:${b}(出口只写不动作红线)`);
  // d) 接线面锚词:步侧出口接线与 RETRO 摘要在案(漂移绊线)
  const stepsSrc = fs.readFileSync(path.join(AGENT, "pipeline", "steps.mjs"), "utf8");
  assert.match(stepsSrc, /runFindingExits/, "ANCHOR_SWEEP 步接线出口");
  assert.match(stepsSrc, /anchor_sweep/, "RETRO 摘要行(出口③)读工件计数");
});
await t("G_RETRO 出口③机检单元例(直构工件):08 工件在场→retro.anchor_sweep 缺席/n_fail 不符=门败;降级工件→须记 degraded", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const d = roundDir(R1);
  const retroPath = path.join(DOCS, "ops", "retro", `${R1}.json`);
  const orig = fs.readFileSync(retroPath, "utf8");
  const ctxLike = { dir: d, opsRoot: path.join(DOCS, "ops"), retroAuditKey: R1,
    rulesFile: path.join(DOCS, "ops", "rules", "suppressions.json"), itemsDir: path.join(DOCS, "ops", "items"),
    ledgerFile: path.join(DOCS, "ops", "ledger.md") };
  try {
    const retro = j(retroPath);
    assert.equal(GATES.G_RETRO(ctxLike).pass, true, "基线(带 anchor_sweep 摘要)过");
    const bad = { ...retro, anchor_sweep: { ...retro.anchor_sweep, n_fail: 0 } };
    fs.writeFileSync(retroPath, JSON.stringify(bad, null, 2) + "\n");
    assert.match(GATES.G_RETRO(ctxLike).reason, /anchor_sweep/, "n_fail 不符=门败(摘要行机检)");
    const noSum = { ...retro };
    delete noSum.anchor_sweep;
    fs.writeFileSync(retroPath, JSON.stringify(noSum, null, 2) + "\n");
    assert.match(GATES.G_RETRO(ctxLike).reason, /anchor_sweep/, "摘要缺席=门败(出口③无验证手段不得称出口)");
  } finally { fs.writeFileSync(retroPath, orig); }
});

await t("stderr 阶段行语法+stdout 末行=信封单行 JSON(恰一行)", async () => {
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2341-health", fixturesDir: DEFAULT_FIXTURES_DIR, env: mkTree("tree-2341").env, ...io });
  assert.equal(r.ok, true);
  const se = io.buf.stderr;
  assert.match(se, /\[stage\] PROBE start\n/, "start 行");
  assert.match(se, /\[stage\] PROBE done gate=PASS dur=\d+s artifact=01-probe-summary\.json\n/, "done 行(gate/dur/artifact)");
  assert.match(se, /\[stage\] CLOSE done gate=PASS dur=\d+s artifact=\(envelope\)\n/, "CLOSE done 行");
  const lines = io.buf.stdout.split("\n");
  assert.equal(lines.length, 2, "stdout 恰一行+末尾换行");
  assert.equal(lines[1], "");
  assert.deepEqual(JSON.parse(lines[0]), r.envelope, "stdout 末行=返回信封逐字");
});

await t("VERIFY 分区穷尽(旗标3=survivors2+suppressed1,R1 抑制 dshield)+DEEP 真开启(A 一律回填)", async () => {
  const d = roundDir(R1);
  const s = j(path.join(d, "01-probe-summary.json"));
  assert.ok(s.urls_n >= 30, `urls_n=${s.urls_n}`);
  assert.equal(s.flags.length, 3);
  assert.equal(s.buckets.frozen, 3);
  assert.equal(s.flags.find((f) => /cinsscore/.test(f.url)).source, "ciarm", "标源名=清单 # 首词(非 host;#164)");
  assert.ok(s.flags.every((f) => !f.error_family), "冻结旗标无 error_family(仅不可达行携带)");
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sv.survivors.length, 2);
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "R1");
  assert.match(sp.suppressed[0].url, /dshield/);
  assert.ok(sv.known_noise_digest.some((r) => r.id === "R1"), "已知误判模式 digest 入幸存工件(C稿 §3.5)");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 2);
  const c = v.verdicts.find((x) => /cinsscore/.test(x.hid));
  const bd = v.verdicts.find((x) => /binarydefense/.test(x.hid));
  assert.equal(c.verdict, "confirmed", "cinsscore 深验确证");
  assert.equal(bd.verdict, "refuted", "binarydefense 深验证伪");
  assert.deepEqual(c.evidence, [{ call_id: "c-cins", field: "age_days", value: 220 }], "A 一律:模型只交选择对,value=宿主回填登记表(220)");
  assert.deepEqual(bd.evidence, [{ call_id: "c-bd", field: "age_days", value: 5 }], "回填 5 ≠ TRIAGE 读数 210——证据腿只认本步实测");
  assert.deepEqual(v.golden_track, [], "真 bundle 轮无金轨迹(不混轮)");
  const bun = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(bun.bundles.length, 2);
  assert.ok(bun.bundles.every((x) => Array.isArray(x.prompt_pkg.precedent_hits) && x.prompt_pkg.precedent_hits.length <= 3), "bundle 带 ≤3 判例命中(C稿 §3.5)");
  assert.ok(bun.bundles.every((x) => typeof x.budget_cny === "number" && x.budget_cny > 0), "bundle 带预算余额");
});

await t("ITEMIZE 真条目(十字段查表零模型):verdict→动作查表+refuted 恒 low 消化+全签 dedup_key+真树落盘", async () => {
  const d = roundDir(R1);
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [2, 0, 0, 1]);
  assert.equal(m.rows.length, 2, "一行一假设(verdicts 全量入清单)");
  const itemsDir = path.join(DOCS, "ops", "items");
  const files = fs.readdirSync(itemsDir).filter((f) => f.endsWith(".md"));
  assert.equal(files.length, 2, "真条目落 ops/items 树(接 _ops_items)");
  const parse = (f) => { const t = fs.readFileSync(path.join(itemsDir, f), "utf8");
    const row = m.rows.find((r) => r.item_id === f.replace(/\.md$/, ""));
    return { t, row }; };
  const ciarmRow = m.rows.find((r) => r.source === "ciarm");
  const bdRow = m.rows.find((r) => r.source === "binarydefense");
  assert.equal(ciarmRow.suggested_action, "human_ruling", "confirmed→human_ruling 建议复核(P4 #166 裁,人裁终局)");
  assert.equal(ciarmRow.severity, "high", "confirmed 承 TRIAGE 原级");
  assert.equal(bdRow.suggested_action, "digest_ignore", "refuted→低危消化条目(三小裁②)");
  assert.equal(bdRow.severity, "low", "refuted 恒 low 默认折叠");
  assert.deepEqual(ciarmRow.dedup_key, { source: "ciarm", probe_class: "staleness", error_signature: "age_gt_2x_refresh" }, "全签与 P1 探测器同空间");
  assert.deepEqual(bdRow.dedup_key, { source: "binarydefense", probe_class: "staleness", error_signature: "age_gt_2x_refresh" });
  for (const f of files) { // 十字段冻结面真形
    const { t, row } = parse(f);
    for (const k of ["id:", "action:", "args:", "evidence:", "impact:", "rollback:", "dedup_key:", "severity:", "cause_group:", "status:"])
      assert.ok(t.includes(`
${k}`) || t.startsWith(`---
id:`), `条目 ${f} 缺字段 ${k}`);
    assert.match(t, /status: "?active"?/, "产条恒 active");
    assert.ok(t.includes(`round_id: "${R1}"`), "evidence.round_id 在场(replay 回声/溯源面)");
    assert.ok(row && row.item_id === f.replace(/\.md$/, ""), "manifest 行 ↔ 树文件对号");
  }
  const ciarmFile = fs.readFileSync(path.join(itemsDir, `${ciarmRow.item_id}.md`), "utf8");
  assert.match(ciarmFile, /action: "?human_ruling"?/, "树面 action=查表值");
  assert.match(ciarmFile, /cause_group: "?staleness"?/, "frozen→staleness 组(_ops_detectors.CAUSE_GROUPS 词表)");
  assert.ok(ciarmFile.includes("deep_evidence:") && ciarmFile.includes('"c-cins"'), "深验证据腿入条目 evidence(证据不灭失)");
});

await t("预算硬拦:0.03¥ 截尾 1 条标 unresolved(budget),DISPATCH degraded,轮仍 ok=true", async () => {
  const fx = cloneFixtures("fixtures-budget");
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n- binarydefense:预算截尾 unresolved · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=0 unresolved=1;预算门 0.03¥ 硬拦截尾 1 条");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2342-health", fixturesDir: fx, env: { ...mkTree("tree-2342").env, OPS_PIPELINE_BUDGET_CNY: "0.03" }, ...io });
  assert.equal(r.ok, true, "降级不是失败(信封 ok=true+stages 标 degraded)");
  const dp = stageOf(r.envelope, "DISPATCH");
  assert.equal(dp.status, "degraded");
  const d = path.join(mkTree("tree-2342").root, "ops", "rounds", "2026-10-23-2342-health");
  const bun = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(bun.bundles.length, 1);
  assert.equal(bun.truncated.length, 1);
  assert.equal(bun.truncated[0].reason, "unresolved(budget)");
  assert.match(bun.truncated[0].hid, /binarydefense/, "低 severity 先截");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 1, "DEEP 只跑幸存 bundle");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.equal(m.created, 2, "截尾假设转 human_ruling 条目,证据不灭失");
  assert.equal(m.rows.find((x) => /binarydefense/.test(x.hid)).verdict, "unresolved");
});

await t("失败面:坏 TRIAGE fixture → model_face 终态(attempts=2),01/02 工件保留(证据不灭失),code∈九词", async () => {
  const badFx = path.join(TMP, "fixtures-bad");
  fs.mkdirSync(badFx, { recursive: true });
  for (const f of ["synth.json"]) fs.copyFileSync(path.join(AGENT, "fixtures/pipeline", f), path.join(badFx, f));
  fs.cpSync(path.join(AGENT, "fixtures/pipeline/deep"), path.join(badFx, "deep"), { recursive: true });
  fs.writeFileSync(path.join(badFx, "triage.json"), JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: "不是 JSON(schema 违例负例)" }], stopReason: "stop" }] }));
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2343-health", fixturesDir: badFx, env: mkTree("tree-2343").env, ...io });
  assert.equal(r.ok, false);
  const env = r.envelope;
  assert.equal(env.error.code, "model_face");
  assert.ok(ERROR_CODES.includes(env.error.code), "错误码 ∈ 九词闭集零新词");
  const tr = stageOf(env, "TRIAGE");
  assert.equal(tr.status, "failed");
  assert.equal(tr.attempts, 2, "schema 违例重试≤1 后终态");
  const d = path.join(mkTree("tree-2343").root, "ops", "rounds", "2026-10-23-2343-health");
  assert.ok(fs.existsSync(path.join(d, "01-probe-summary.json")) && fs.existsSync(path.join(d, "02-verify-survivors.json")), "工件保留");
  assert.equal(j(path.join(d, "state.json")).status, "failed");
  assert.match(io.buf.stderr, /\[stage\] TRIAGE fail gate=- code=model_face reason=/, "fail 行语法");
});

// ── P3 #165 新例:①空转金轨迹轮(#162 审 P2-2 裁定①)②SYNTH 判例闭合违例负例
// ③G_SYNTH 深验三计数抽检负例(#162 审 P2-5)④G_DEEP A 一律单元例(直构工件,不依赖 faux 回合)──
await t("空转金轨迹轮(#162 审 P2-2 裁定①):零 need_deep → DISPATCH skipped,DEEP 仍跑 canned faux 回路留痕 golden_track", async () => {
  const fx = cloneFixtures("fixtures-golden");
  fs.writeFileSync(path.join(fx, "triage.json"), JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", stopReason: "stop",
    text: "{\"hypotheses\":[{\"signal_id\":\"https://cinsscore.com/list/ci-badguys.txt\",\"cause_class\":\"frozen_feed\",\"hypothesis\":\"若冻结读数为探测伪迹,则换 GET 复测可见新鲜 Last-Modified\",\"need_deep\":false,\"probe_hint\":\"none\",\"severity\":\"low\",\"one_line\":\"cinsscore 冻结读数入观察名单\"},{\"signal_id\":\"https://www.binarydefense.com/banlist.txt\",\"cause_class\":\"frozen_feed\",\"hypothesis\":\"若冻结读数为探测伪迹,则换 GET 复测可见新鲜 Last-Modified\",\"need_deep\":false,\"probe_hint\":\"none\",\"severity\":\"low\",\"one_line\":\"binarydefense 冻结读数入观察名单\"}],\"digest\":\"金轨迹轮:2 幸存均入观察,零深验子集。\"}" }] }] }));
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:冻结读数入观察(watch)· severity=low · 建议 watch\n- binarydefense:冻结读数入观察(watch)· severity=low · 建议 watch\n\n抑制 1 条(规则 R1×1——明细见工件)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=0 refuted=0 unresolved=0;零 need_deep,深验未派单\n- 空转金轨迹轮:DEEP 桩仍跑 canned 回路保活性(#162 审 P2-2 裁定①)。");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0102-health", fixturesDir: fx, env: mkTree("tree-0102").env, ...io });
  assert.equal(r.ok, true);
  const env = r.envelope;
  assert.equal(stageOf(env, "DISPATCH").status, "skipped", "零 need_deep → DISPATCH skip(转移图 TRIAGE→ITEMIZE)");
  const deep = stageOf(env, "DEEP");
  assert.equal(deep.status, "done", "金轨迹回路真跑(DEEP 真开启后金轨迹也走真装配)");
  assert.equal(deep.attempts, 1, "金轨迹回路跑了一条 canned 假设");
  assert.notEqual(deep.usage, null, "模型步 usage 在场(faux 零成本)");
  const d = path.join(mkTree("tree-0102").root, "ops", "rounds", "2026-10-24-0102-health");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.deepEqual(v.verdicts, [], "金轨迹 hid 不入 verdicts(不污染条目面)");
  assert.equal(v.golden_track.length, 1);
  assert.equal(v.golden_track[0].hid, "golden-track-canned");
  assert.equal(v.golden_track[0].verdict, "unresolved");
  assert.ok(fs.existsSync(path.join(d, "05-deep-golden-track-canned.json"))
    && fs.existsSync(path.join(d, "05-deep-golden-track-canned-transcript.jsonl")), "金轨迹工件+transcript 留痕");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [2, 0, 0, 1], "watch 条目 2 + 抑制 1(P4:真树落盘)");
  const g = j(path.join(d, "gates.json"));
  assert.equal(g.records.length, 9, "skipped 步无门记录(PROBE..CLOSE 除 DISPATCH;含 #182 G_ANCHOR_SWEEP)");
  assert.ok(g.records.every((x) => x.pass), "G_DEEP 机检金轨迹在场面");
  assert.ok(g.records.find((x) => x.name === "G_DEEP").reason.includes("golden=1"), "门 reason 带数字可回算");
});

await t("SYNTH 判例闭合违例负例:报告引未注入判例 → 重试≤1 后终态 closure_check,条目已落库不回滚", async () => {
  const fx = cloneFixtures("fixtures-closure");
  writeSynthFx(fx, "## 注入判例\n- 2020-01-01-fabricated-precedent.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=0");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0103-health", fixturesDir: fx, env: mkTree("tree-0103").env, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "closure_check", "门指定终态码(九词闭集零新词,C稿 §4.4 映射)");
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.status, "failed");
  assert.equal(sy.attempts, 2, "契约违例重试≤1(同提示词重发)");
  const d = path.join(mkTree("tree-0103").root, "ops", "rounds", "2026-10-24-0103-health");
  assert.ok(fs.existsSync(path.join(d, "06-itemize-manifest.json")), "条目已落库不回滚(证据不灭失)");
  const g = j(path.join(d, "gates.json"));
  const synthGates = g.records.filter((x) => x.name === "G_SYNTH");
  assert.equal(synthGates.length, 2, "门重试圈每评留痕(可审计)");
  assert.ok(synthGates.every((x) => x.pass === false && /闭合违例/.test(x.reason)));
  assert.match(io.buf.stderr, /\[stage\] SYNTH fail gate=G_SYNTH code=closure_check/, "fail 行门名随错误带回");
});

await t("G_SYNTH 深验三计数抽检负例(#162 审 P2-5):unresolved=1 ≠ 回算 2(verdicts∪degraded∪truncated)→ 终态 empty_text", async () => {
  const fx = cloneFixtures("fixtures-verdict");
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=1");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0104-health", fixturesDir: fx, env: mkTree("tree-0104").env, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "empty_text", "计数契约违例=SYNTH 缺省终态码(闭集)");
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.attempts, 2);
  const g = j(path.join(mkTree("tree-0104").root, "ops", "rounds", "2026-10-24-0104-health", "gates.json"));
  assert.match(g.records.filter((x) => x.name === "G_SYNTH")[0].reason, /深验计数不符工件:unresolved/);
});

await t("G_DEEP A 一律单元例(直构工件):选择对回填/复述漂移/未知 call_id/缺证据腿/失败信封/微探针超限/金轨迹混轮 均门败", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "gdeep-unit-"));
  fs.writeFileSync(path.join(d, "04-dispatch-bundles.json"), JSON.stringify({ budget_cny: 0.05, bundles: [{ hid: "https://x/f.txt", budget_cny: 0.016 }] }));
  const seed = { type: "registry_seed", call_id: "c9", tool: "reprobe_get", sc: { ok: true, age_days: 220 } };
  const writeVerdicts = (ev, extra = {}) => fs.writeFileSync(path.join(d, "05-deep-verdicts.json"),
    JSON.stringify({ verdicts: [{ hid: "https://x/f.txt", verdict: "confirmed", evidence: ev, one_line: "u" }], degraded: [], golden_track: [], ...extra }));
  const writeTranscript = (lines) => fs.writeFileSync(path.join(d, "05-deep-https-x-f.txt-transcript.jsonl"), lines.map((l) => JSON.stringify(l)).join("\n") + "\n"); // 真 hidSlug(https://x/f.txt)=https-x-f.txt(审后修 P2-2 逐假设登记表后,手搓假名不再能借全局正则过门)
  writeTranscript([seed]);
  writeVerdicts([{ call_id: "c9", field: "age_days", value: 220 }]);
  assert.equal(GATES.G_DEEP({ dir: d }).pass, true, "宿主回填三元组逐字回引=过");
  writeVerdicts([{ call_id: "c9", field: "age_days", value: 999 }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /回引不符/, "复述漂移(伪造值)=门败(A 一律结构性消灭)");
  writeVerdicts([{ call_id: "c9", field: "age_days" }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /三元组缺值/, "宿主回填缺席/字段不在返回=门败");
  writeVerdicts([{ call_id: "c404", field: "age_days", value: 220 }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /未知 call_id/);
  writeVerdicts([]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /无证据腿/, "confirmed 必带 evidence");
  // 失败信封禁入 evidence:ok:false 是测量故障非读数,引用即门败(shared/envelope.md 纪律)
  writeTranscript([{ type: "registry_seed", call_id: "cf", tool: "reprobe_get", sc: { ok: false, code: "net_fail", reason: "canned" } }, seed]);
  writeVerdicts([{ call_id: "cf", field: "code", value: "net_fail" }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /失败信封禁入 evidence/);
  // 微探针 ≤3/假设(deep.md 预算段机检面):4 seed 行=门败
  writeTranscript([0, 1, 2, 3].map((i) => ({ type: "registry_seed", call_id: `c${i}`, tool: "reprobe_get", sc: { ok: true, i } })));
  writeVerdicts([]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /微探针超 3/, "探针预算段超限=门败");
  // 金轨迹与真假设同轮(#165 落单向门,本例补不混轮负例):need>0 且 golden_track>0=门败
  writeTranscript([seed]);
  writeVerdicts([{ call_id: "c9", field: "age_days", value: 220 }], { golden_track: [{ hid: "golden-track-canned", verdict: "unresolved", evidence: [], one_line: "g" }] });
  assert.match(GATES.G_DEEP({ dir: d }).reason, /金轨迹与真假设同轮/);
  fs.rmSync(d, { recursive: true, force: true });
});

await t("DISPATCH 上限截尾单元例(#166):4 need_deep→bundles 3+truncated 1(unresolved(dispatch_cap));0.02¥ 再截 2(unresolved(budget))", async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "dispatch-unit-"));
  const mkHyp = (id, sev) => ({ signal_id: id, cause_class: "frozen_feed", hypothesis: "若 X 则 Y", need_deep: true, probe_hint: "reprobe_get", severity: sev, one_line: "行" });
  fs.writeFileSync(path.join(d, "03-triage-hypotheses.json"), JSON.stringify({ hypotheses: [mkHyp("h-high", "high"), mkHyp("h-med", "medium"), mkHyp("h-low1", "low"), mkHyp("h-low2", "low")] }));
  fs.writeFileSync(path.join(d, "02-verify-survivors.json"), JSON.stringify({ survivors: [] })); // 锚选零命中面(旗标缺席=零注入,宁少算)
  await steps.runStage({ name: "DISPATCH" }, { dir: d, budgetCny: 0.05, env: process.env });
  let b = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(b.bundles.length, 3, "上限 3(#166:severity 排序保 high/medium/low1)");
  assert.deepEqual(b.truncated, [{ hid: "h-low2", severity: "low", reason: "unresolved(dispatch_cap)" }], "截尾留痕");
  assert.equal(b.degraded, true);
  await steps.runStage({ name: "DISPATCH" }, { dir: d, budgetCny: 0.02, env: process.env });
  b = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(b.bundles.length, 1, "0.02¥ 只容 1 假设(0.016×1≤0.02<0.032)");
  assert.equal(b.truncated.length, 3);
  assert.equal(b.truncated[0].reason, "unresolved(dispatch_cap)", "第 4 条归因上限");
  assert.ok(b.truncated.slice(1).every((t) => t.reason === "unresolved(budget)"), "其余归因预算门");
  assert.match(b.bundles[0].hid, /h-high/, "高 severity 幸存");
  fs.rmSync(d, { recursive: true, force: true });
});

// ── P2 #164 新例:①规则库判例转写真命中(R12 形/R7 形,直调 VERIFY)②在飞真读 + R7 annotate 全链 ──
// ③规则库闭集负例 ④matrix 裸失败负例(#163 review P2-1 顺手件)
await t("规则命中(R12/R7 判例转写形,直调 VERIFY):404 重定向形 suppress+429 annotate 传幸存+review_at 缺省采纳+90天", async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "verify-unit-"));
  const rulesFile = path.join(d, "rules.json");
  // 首批规则同形(docs 仓 docs/ops/rules/suppressions.json;R12 缺 review_at 验缺省,R7 带显式)
  fs.writeFileSync(rulesFile, JSON.stringify({ version: 1, rules: [
    { id: "R12", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-bbe1ad6f0c.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", url_shape: "https://github.com/*/releases/latest/download/", error_family: "http_404" },
      action: "suppress", note: "GitHub releases/latest/download 截断重定向形:HEAD 恒 404 而 GET 实活(GeoLite 假红,2026-10-23 判例)" },
    { id: "R7", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-0db230187f.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", error_family: "http_429" },
      action: "annotate", note: "限流:降 severity 不抑制", review_at: "2027-01-21" } ] }, null, 2));
  const itemsDir = path.join(d, "items");
  fs.mkdirSync(itemsDir);
  fs.writeFileSync(path.join(d, "01-probe-summary.json"), JSON.stringify({ ok: true, round_id: "unit", urls_n: 3, attempted_n: 3,
    buckets: { fresh: 0, frozen: 1, unreachable: 2, token_required: 0, no_lm: 0 },
    flags: [
      { signal_id: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/", url: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/", bucket: "unreachable", source: "geolite_city", error_family: "http_404" },
      { signal_id: "https://raw.githubusercontent.com/duggytuxy/Data-Shield_IPv4_Blocklist/main/prod.txt", url: "https://raw.githubusercontent.com/duggytuxy/Data-Shield_IPv4_Blocklist/main/prod.txt", bucket: "unreachable", source: "data_shield", error_family: "http_429" },
      { signal_id: "https://feeds.dshield.org/block.txt", url: "https://feeds.dshield.org/block.txt", bucket: "frozen", source: "dshield", age_days: 200 } ] }));
  await steps.runStage({ name: "VERIFY" }, { dir: d, rulesFile, itemsDir, roundId: "unit" });
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "R12", "截断重定向 404 形被 R12 压(零 token 花费,C稿 §2.4-2)");
  assert.equal(sp.suppressed[0].error_family, "http_404");
  assert.equal(sv.survivors.length, 2);
  const rl = sv.survivors.find((x) => x.source === "data_shield");
  assert.equal(rl.annotated_rule, "R7", "429 限流形 annotate 传递幸存(降 severity 不抑制)");
  const r12 = sv.known_noise_digest.find((r) => r.id === "R12");
  assert.equal(r12.review_at, "2027-01-21", "review_at 缺省=采纳+90 天(2026-10-23+90)");
  assert.equal(sv.known_noise_digest.find((r) => r.id === "R7").review_at, "2027-01-21");
  // 反面:全 URL 形(带文件名)不落入 R12 截断形——真 404 仍幸存交人
  fs.writeFileSync(path.join(d, "01-probe-summary.json"), JSON.stringify({ ok: true, round_id: "unit2", urls_n: 1, attempted_n: 1,
    buckets: { fresh: 0, frozen: 0, unreachable: 1, token_required: 0, no_lm: 0 },
    flags: [{ signal_id: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb", url: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb", bucket: "unreachable", source: "geolite_city", error_family: "http_404" }] }));
  await steps.runStage({ name: "VERIFY" }, { dir: d, rulesFile, itemsDir, roundId: "unit2" });
  assert.equal(j(path.join(d, "02-verify-survivors.json")).survivors.length, 1, "全资产 URL 404=真信号,不入 R12 截断形");
  assert.equal(j(path.join(d, "02-verify-suppressed.json")).suppressed.length, 0);
  fs.rmSync(d, { recursive: true, force: true });
});

await t("规则库闭集负例:谓词闭集外/动作闭集外/review_at 异形/id 重复/坏 JSON 均以 infra 拒(规则文件坏=终态面)", async () => {
  const base = { id: "RX", adopted: "2026-10-23", adopted_via: "判例 fixture", match: { bucket: "frozen" }, action: "suppress", note: "n" };
  const bad = (r) => assert.throws(() => steps.normalizeRules(r), (e) => e.code === "infra");
  bad({ version: 1, rules: [{ ...base, match: { path: "/x" } }] }, "谓词闭集外");
  bad({ version: 1, rules: [{ ...base, action: "delete" }] }, "动作闭集外");
  bad({ version: 1, rules: [{ ...base, review_at: "2027/01/21" }] }, "review_at 形状");
  bad({ version: 1, rules: [{ ...base, match: {} }] }, "match 空");
  bad({ version: 1, rules: [{ ...base }, { ...base }] }, "id 重复");
  bad(null, "非对象");
  assert.doesNotThrow(() => steps.normalizeRules({ version: 1, rules: [{ ...base }] }), "合规形过");
});

await t("在飞全签不双开+终态重开全链(CLI 轮):bruteforce 同签在飞压制;ciarm 同签终态→重开链指;R7 annotate 幸存", async () => {
  const DOCS2 = mkTree("docs2"); // 独立树:规则只留 R7(429 annotate)
  fs.writeFileSync(path.join(DOCS2.root, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
    { id: "R7", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-0db230187f.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", error_family: "http_429" },
      action: "annotate", note: "限流:降 severity 不抑制", review_at: "2027-01-21" } ] }, null, 2) + "\n");
  // 真形 _ops_items 预置件(Python safe_dump 裸串形,桥解析兼容面):bruteforce 在飞同签(危险页 404 旗标应压制);
  // ciarm 同签终态 done(冻结旗标应重开链指,非就地复活)
  fs.mkdirSync(path.join(DOCS2.root, "ops", "items"), { recursive: true });
  fs.writeFileSync(path.join(DOCS2.root, "ops", "items", "2026-10-20-item-aaaa000001.md"), `---
id: 2026-10-20-item-aaaa000001
action: retry_download
args:
  source: bruteforce
evidence:
  consecutive_failures: 2
impact: bruteforce 数据停更,威胁覆盖面收缩
rollback: 重新触发下载即可恢复
dedup_key:
  source: bruteforce
  probe_class: download
  error_signature: http_4xx
severity: medium
cause_group: download_failure
status: active
---

selftest fixture(在飞:同签 download/http_4xx 不双开)。
`);
  fs.writeFileSync(path.join(DOCS2.root, "ops", "items", "2026-10-20-item-bbbb000002.md"), `---
id: 2026-10-20-item-bbbb000002
action: refresh_source
args:
  source: ciarm
evidence:
  content_age_h: 5280
impact: ciarm 内容超龄
rollback: 刷新成功即自愈
dedup_key:
  source: ciarm
  probe_class: staleness
  error_signature: age_gt_2x_refresh
severity: medium
cause_group: staleness
status: done
---

selftest fixture(终态 done:同签冻结旗标=复开新条目链指,原条目永不删)。
`);
  // curl 替身:cinsscore 冻结 220;binarydefense 429(R7 annotate);danger.rulez.sk 404(不可达→bruteforce 同签在飞压制);其余新鲜
  const STUBS2 = path.join(TMP, "stubs2");
  fs.mkdirSync(STUBS2, { recursive: true });
  fs.writeFileSync(path.join(STUBS2, "curl"), `#!/usr/bin/env bash
url="\${@: -1}"
case "$url" in
  *cinsscore*) printf 'HTTP/1.1 200 OK\\r\nLast-Modified: %s\\r\nContent-Length: 4\\r\n\\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - 220 * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"; exit 0 ;;
  *binarydefense*) printf 'HTTP/1.1 429 Too Many Requests\\r\n\\r\n'; exit 0 ;;
  *danger.rulez.sk*) printf 'HTTP/1.1 404 Not Found\\r\n\\r\n'; exit 0 ;;
esac
printf 'HTTP/1.1 200 OK\\r\nLast-Modified: %s\\r\nContent-Length: 4\\r\n\\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - 30 * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"
exit 0
`);
  fs.chmodSync(path.join(STUBS2, "curl"), 0o755);
  // 计数链定制 synth:ciarm 重开(created=1 reopened=1)+ binarydefense 新建;深验 confirmed=1 refuted=1
  const fx = cloneFixtures("fixtures-casea");
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:冻结深验 confirmed(重开条目,前条已人裁)· 建议 human_ruling\n- binarydefense:429 限流形 R7 annotate,深验 refuted · 建议 digest_ignore\n\n抑制 1 条(in_flight×1——明细见工件)。\n\n## 摘要\n- 计数: created=1 reopened=1 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=0");
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0100-health", "--fixtures", fx],
    { ...DOCS2.env, PATH: `${STUBS2}:${process.env.PATH}` });
  assert.equal(r.rc, 0, `rc=${r.rc} stdout=${JSON.stringify((r.stdout||'').slice(-400))} stderr=${JSON.stringify((r.stderr||'').slice(-200))}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  const d = path.join(DOCS2.root, "ops", "rounds", "2026-10-24-0100-health");
  const s2 = j(path.join(d, "01-probe-summary.json"));
  assert.equal(s2.buckets.unreachable, 2, "binarydefense 429 + danger.rulez.sk 404");
  assert.equal(s2.buckets.frozen, 1);
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sv.survivors.length, 2, "ciarm(终态不算在飞)+binarydefense(R7 annotate)");
  assert.equal(sv.survivors.find((x) => x.source === "binarydefense").annotated_rule, "R7");
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "in_flight");
  assert.equal(sp.suppressed[0].dedup_key, "bruteforce|download|http_4xx", "全签同因(源级→P4 全签,#164 偏离②收口)");
  assert.deepEqual(sp.suppressed[0].in_flight_items, ["2026-10-20-item-aaaa000001"], "溯源到真条目 id");
  const g = j(path.join(d, "gates.json"));
  assert.ok(g.records.every((x) => x.pass), "门全绿(G_VERIFY 真在飞面全签重算)");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [1, 1, 0, 1], "ciarm 重开+binarydefense 新建");
  const ciarmRow = m.rows.find((x) => x.source === "ciarm");
  assert.equal(ciarmRow.outcome, "reopened");
  assert.equal(ciarmRow.supersedes, "2026-10-20-item-bbbb000002", "复开链指最近旧条");
  const newFile = fs.readFileSync(path.join(DOCS2.root, "ops", "items", `${ciarmRow.item_id}.md`), "utf8");
  assert.match(newFile, /supersedes: "?2026-10-20-item-bbbb000002"?/, "链指字段在树面");
  assert.match(newFile, /status: "?active"?/, "复开新条 active");
  const oldFile = fs.readFileSync(path.join(DOCS2.root, "ops", "items", "2026-10-20-item-bbbb000002.md"), "utf8");
  assert.match(oldFile, /status: "?done"?/, "原条目永不改写(证据不灭失)");
  const bdRow = m.rows.find((x) => x.source === "binarydefense");
  assert.deepEqual(bdRow.dedup_key, { source: "binarydefense", probe_class: "download", error_signature: "http_4xx" }, "429→折叠族 http_4xx(#164 偏离①映射)");
});

await t("matrix 裸失败负例(#163 review P2-1):信封件落 01-probe-matrix.json,summary.matrix.ok=false,轮仍 ok=true 不阻轮", async () => {
  const STUBS3 = path.join(TMP, "stubs3");
  fs.mkdirSync(STUBS3);
  fs.writeFileSync(path.join(STUBS3, "py-matrix-fail"), `#!/usr/bin/env bash\necho 'boom: matrix stub bare failure' >&2\nexit 1\n`);
  fs.chmodSync(path.join(STUBS3, "py-matrix-fail"), 0o755);
  const t0101 = mkTree("tree-0101");
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0101-health", "--fixtures", DEFAULT_FIXTURES_DIR], { ...t0101.env, OPS_EVAL_PY: path.join(STUBS3, "py-matrix-fail") }); // 显式 fixtures=faux 面(#170;CLI 契约面非 provider 面)
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-400)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true, "matrix 失败=嵌套信封不阻轮(C稿 §2.2;证据不灭失落件)");
  const d = path.join(t0101.root, "ops", "rounds", "2026-10-24-0101-health");
  const mfile = j(path.join(d, "01-probe-matrix.json"));
  assert.equal(mfile.ok, false, "工件=失败信封件非读数");
  assert.equal(mfile.code, "matrix_failed");
  assert.match(mfile.reason, /boom/);
  const s = j(path.join(d, "01-probe-summary.json"));
  assert.equal(s.matrix.ok, false);
  assert.equal(s.matrix.exit_code, null);
  assert.equal(s.matrix.violation_n, null);
  const g = j(path.join(d, "gates.json"));
  assert.equal(g.records.length, 10);
  assert.ok(g.records.every((x) => x.pass), "门不受 matrix 裸失败牵连(legacy 失败只回嵌套信封,不阻轮语义两侧一致)");
  // 该 stub 无旗标分发→sweep 面同死:#182 降级旁路(stage degraded+门旁路留痕,轮仍成功)
  const envD = JSON.parse(r.stdout.trim().split("\n").pop());
  const sw = stageOf(envD, "ANCHOR_SWEEP");
  assert.equal(sw.status, "degraded", "CLI 面死=降级非终态(RETRO 同款旁路形制)");
  assert.match(g.records.find((x) => x.stage === "ANCHOR_SWEEP").reason, /门旁路/);
  const sweepFail = j(path.join(d, "08-anchor-sweep.json"));
  assert.equal(sweepFail.ok, false, "工件=失败信封件(证据不灭失)");
  assert.match(sweepFail.reason, /matrix stub bare failure|channel|transient|infra/, `四码/infra 兑底信封:${sweepFail.reason}`);
});

await t("ANCHOR_SWEEP 降级旁路孤立例(#182):仅 sweep 面死(error 信封 rc 1)→ stage degraded+门旁路+工件=信封透传,其余步零牵连,轮 ok=true", async () => {
  const STUBS4 = path.join(TMP, "stubs4");
  fs.mkdirSync(STUBS4);
  fs.writeFileSync(path.join(STUBS4, "py-sweep-dead"), `#!/usr/bin/env bash
# 旗标分发死面:--anchor-sweep→error 信封 rc 1(load_db 失败同型);其余→矩阵读数照常
case " $* " in
  *--anchor-sweep*) printf '%s\\n' '{"error":{"code":"internal","message":"load_db failed: fixture","hint":"h"}}'; exit 1 ;;
  *) printf '%s\\n' ${SHELL_JSON(MATRIX_CANNED)} ;;
esac
`);
  fs.chmodSync(path.join(STUBS4, "py-sweep-dead"), 0o755);
  const t0306 = mkTree("tree-sweep-deg");
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0306-health", "--fixtures", cloneFixtures("fx-sweep-deg")],
    { ...t0306.env, OPS_EVAL_PY: path.join(STUBS4, "py-sweep-dead") });
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-400)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true, "巡检面死不阻断轮(不持门票义;失败=finding/信封件落盘)");
  const sw = stageOf(env, "ANCHOR_SWEEP");
  assert.equal(sw.status, "degraded");
  assert.equal(stageOf(env, "PROBE").status, "done", "其余步零牵连(matrix 面照常)");
  assert.equal(stageOf(env, "RETRO").status, "done");
  const d = path.join(t0306.root, "ops", "rounds", "2026-10-24-0306-health");
  const sweepFail = j(path.join(d, "08-anchor-sweep.json"));
  assert.equal(sweepFail.ok, false, "工件=失败信封件非读数");
  assert.equal(sweepFail.code, "internal", "python error 信封 code 透传(--json 面不裸栈)");
  assert.match(sweepFail.reason, /load_db failed: fixture/);
  const g = j(path.join(d, "gates.json"));
  const rec = g.records.find((x) => x.stage === "ANCHOR_SWEEP");
  assert.equal(rec.pass, true, "旁路记录 pass=true(降级非门败)");
  assert.match(rec.reason, /stage degraded.*门旁路/, "RETRO 同款 degrade 旁路留痕");
  assert.ok(g.records.filter((x) => x.name !== "G_ANCHOR_SWEEP").every((x) => x.pass), "其余门全 PASS");
  // #184:求值面死→出口不触发(无读数即无 finding;信封留 skip 痕)+RETRO 摘要记降级态
  const fe = env.pipeline.finding_exits;
  assert.equal(fe.triggered, false, "降级轮零出口(无证据即无话)");
  assert.match(fe.reason, /anchor_sweep_degraded/, "skip 痕点名降级因");
  assert.equal(fe.retrospective_summary.status, "degraded", "出口③:RETRO 摘要记降级态");
  const retroDeg = j(path.join(t0306.root, "ops", "retro", "2026-10-24-0306-health.json"));
  assert.equal(retroDeg.anchor_sweep.status, "degraded");
});


await t("A 一律违例负例(全 faux 轮):深验 fixture 复述伪造值 999 → G_DEEP 回引不符 → model_face 终态工件保留", async () => {
  const fx = cloneFixtures("fixtures-arule");
  const bad = JSON.parse(fs.readFileSync(path.join(fx, "deep", "https-cinsscore.com-list-ci-badguys.txt.json"), "utf8"));
  bad.turns[0].content[0].text = bad.turns[0].content[0].text.replace('"evidence":[{"call_id":"c-cins","field":"age_days"}]',
    '"evidence":[{"call_id":"c-cins","field":"age_days","value":999}]'); // 模型复述伪造值(违 A 一律)
  fs.writeFileSync(path.join(fx, "deep", "https-cinsscore.com-list-ci-badguys.txt.json"), JSON.stringify(bad, null, 1));
  const tree = mkTree("tree-arule");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0105-health", fixturesDir: fx, env: tree.env, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "model_face", "写前语义门败→DEEP 缺省终态码(九词闭集)");
  const d = path.join(tree.root, "ops", "rounds", "2026-10-24-0105-health");
  const g = j(path.join(d, "gates.json"));
  assert.match(g.records.find((x) => x.name === "G_DEEP").reason, /回引不符/, "门 reason 可回算");
  const cFile = j(path.join(d, "05-deep-https-cinsscore.com-list-ci-badguys.txt.json"));
  assert.equal(cFile.evidence[0].value, 999, "伪造值原样透传留痕(宿主不静默纠正,交门裁决)");
  assert.equal(j(path.join(d, "state.json")).status, "failed");
  assert.ok(!fs.existsSync(path.join(d, "06-itemize-manifest.json")), "门败即止:坏证据不得成条(无证据即无话)");
});

await t("DEEP perItem 降级直测(#165 审 P2 遗留):坏 fixture 重试尽→degraded unresolved 折入 ITEMIZE→G_DEEP/G_SYNTH 回算一致", async () => {
  const fx = cloneFixtures("fixtures-degrade");
  fs.writeFileSync(path.join(fx, "deep", "https-www.binarydefense.com-banlist.txt.json"),
    JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: "不是 JSON(model_face 负例)" }], stopReason: "stop" }] }));
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n- binarydefense:重试尽降级 unresolved · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=0 unresolved=1(1 条重试尽降级)");
  const tree = mkTree("tree-degrade");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0106-health", fixturesDir: fx, env: tree.env, ...io });
  assert.equal(r.ok, true, "单假设降级不终态(证据不灭失)");
  const deep = stageOf(r.envelope, "DEEP");
  assert.equal(deep.status, "degraded", "DEEP stages 标降级");
  assert.equal(deep.attempts, 3, "cinsscore 1 发 + binarydefense 重试 2 发");
  const d = path.join(tree.root, "ops", "rounds", "2026-10-24-0106-health");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 1);
  assert.equal(v.degraded.length, 1);
  assert.match(v.degraded[0].one_line, /重试尽降级 unresolved/);
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.equal(m.created, 2, "降级行折入条目(human_ruling 交人)");
  const bdRow = m.rows.find((x) => /binarydefense/.test(x.hid));
  assert.equal(bdRow.verdict, "unresolved");
  assert.equal(bdRow.suggested_action, "human_ruling");
  const g = j(path.join(d, "gates.json"));
  assert.ok(g.records.every((x) => x.pass), "G_DEEP 穷尽(verdicts∪degraded)与 G_SYNTH 回算(confirmed=1 unresolved=1)一致全绿");
});

// ── B 三件装配层(并 #164):_INDEX 生成器/锚域词表/升格检测器 — 单元面(快,不跑整轮)──
await t("B① _INDEX 召回地板:概念判例一行一件、留痕/下划线件排除、再生字节一致、尾部档案汇总", async () => {
  const { buildIndexText, parsePrecedentFm } = await import("./build-index.mjs");
  const pdir = path.join(TMP, "prec-b");
  fs.mkdirSync(pdir, { recursive: true });
  const mk = (name, subject, ctx = "") => fs.writeFileSync(path.join(pdir, name),
    `---\nid: ${name.replace(/\.md$/, "")}\ndate: 2026-10-24\nsubject: ${subject}\ncontext: >\n  ${ctx}\nsuperseded_by: null\n---\n\n正文。\n`);
  mk("2026-10-01-alpha-sunset.md", "源候选判死 — sunset 硬门(URL Last-Modified 冻结)", "threatview.io 冻结 240 天");
  mk("2026-10-02-beta-aggregator.md", "聚合器误判 — 实测排他率立证 ziyadnz");
  fs.writeFileSync(path.join(pdir, "2026-10-24-ruling-deadbeef.md"), "---\nid: r\nsuperseded_by: null\n---\n留痕\n");
  fs.writeFileSync(path.join(pdir, "_schema.md"), "schema\n");
  const files = fs.readdirSync(pdir).filter((f) => f.endsWith(".md") && !f.startsWith("_")).sort()
    .map((name) => ({ name, fm: parsePrecedentFm(fs.readFileSync(path.join(pdir, name), "utf8")) }));
  const concepts = files.filter((f) => !/[\d-]+-ruling-/.test(f.name));
  const text = buildIndexText(concepts);
  assert.equal(concepts.length, 2, "ruling 不进索引(留痕非记忆面)");
  assert.match(text, /2026-10-01-alpha-sunset\.md \| 源候选判死 \|/);
  assert.match(text, /2026-10-02-beta-aggregator\.md.*ziyadnz/);
  assert.doesNotMatch(text, /ruling-deadbeef|_schema/);
  assert.match(text, /superseded: 0 条/);
  assert.equal(buildIndexText(concepts), text, "同库再生字节一致(派生缓存)");
});

await t("B② 锚域词表:闭包校验拒缺件锚;选锚纯函数(域词×旗标命中/空旗标零注入/HIT_CAP)", async () => {
  const anchors = await import("./pipeline/anchors.mjs");
  const { validateAnchors } = await import("./build-index.mjs");
  const loaded = anchors.loadAnchors(path.join(AGENT, "anchors-health.json"));
  assert.ok(loaded.anchors.length >= 5, `锚域 ≥5(${loaded.anchors.length})`);
  const real = ["2026-10-23-ruling-bbe1ad6f0c.md", "2026-10-19-threatview-sunset-dead-feed.md"];
  assert.throws(() => validateAnchors(loaded, real), /锚指向缺件/, "闭包:锚指不在库中的判例 = 编造路径,拒");
  const flags = [{ url: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/", source: "geolite_city", bucket: "unreachable", error_family: "http_404" },
    { url: "https://x/f.txt", source: "dshield", bucket: "frozen" }];
  const picked = anchors.anchorSelect(loaded.anchors, flags);
  assert.ok(picked.includes("2026-10-23-ruling-bbe1ad6f0c.md"), "GitHub 重定向 404 旗标选 GeoLite 判例锚");
  assert.equal(anchors.anchorSelect(loaded.anchors, []).length, 0, "空旗标零注入(宁少算)");
  assert.equal(anchors.anchorSelect(loaded.anchors, flags).length <= anchors.HIT_CAP, true, "铁律⑦ HIT_CAP");
});

await t("B③ 升格检测器:同源留痕≥2 且一致→候选(三门槛 pending);不一致/superseded/单条不立项;候选件幂等", async () => {
  const pd = await import("./promote-detect.mjs");
  const mk = (name, rec, agr, sup = null) => ({ name, recommendation: rec, ruling_agreement: agr, superseded_by: sup });
  const r = [
    mk("r1.md", "retry_download — urlhaus 数据停更,威胁覆盖面收缩(待审条目 2026-10-23-item-aaa)", "agreed"),
    mk("r2.md", "不可达·建议复核: https://urlhaus.abuse.ch/downloads/csv_online/", "agreed"),
    mk("r3.md", "retry_download — threatfox 数据停更,威胁覆盖面收缩(待审条目 2026-10-23-item-bbb)", "amended"),
    mk("r4.md", "retry_download — threatfox 数据停更,威胁覆盖面收缩(待审条目 2026-10-23-item-ccc);忽略理由:410 已确诊", "overruled"),
    mk("r5.md", "同文但已被取代(留痕不计数)", "agreed", "r6.md"),
  ];
  const cands = pd.detectCandidates(r);
  assert.equal(cands.length, 1, "urlhaus 同源一致成组;threatfox 裁决不一致不立项;superseded 不计数");
  assert.equal(cands[0].cause_key, "同源:urlhaus");
  assert.deepEqual(cands[0].rulings, ["r1.md", "r2.md"]);
  const text = pd.candidateText(cands[0], "2026-10-24T00:00:00Z");
  const obj = JSON.parse(text);
  assert.equal(obj.status, "proposed");
  assert.deepEqual(obj.gates.map((g) => g.id), ["machine_checkable", "falsifiable", "non_env_specific"]);
  assert.ok(obj.gates.every((g) => g.verdict === "pending"), "三门槛 pending 起步,人裁逐项核");
});

await t("位等价门(#163):同 stub 下 legacy health 轮工件 = 管线 PROBE 工件,逐字节 diff 空+计数两口径对拍", async () => {
  // 腿一(legacy)= agent.mjs runRound 真 Agent 循环(golden health 例同型):faux 模型点
  // health_snapshot → lib.sh feed_freshness + tools.mjs runMatrixScan 真路径,产出 ts-slug 工件;
  // 腿二(管线)= pipeline.mjs PROBE(同 lib.sh 同 matrixScanCli 单源)。两腿同 curl/OPS_EVAL_PY stub,
  // 同清单(ops/agent/feeds.txt 101 URL 固定 fixture),先后背靠背跑(同 UTC 日,curl stub 日界截断)。
  const { runRound } = await import("./agent.mjs");
  const { fauxProvider, fauxAssistantMessage, fauxToolCall, fauxText, createModels } = await import("@earendil-works/pi-ai");
  const faux = fauxProvider({ models: [{ id: "faux-eq" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("health_snapshot", {}, { id: "call_eq1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage([fauxText("## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- 位等价 fixture 轮:冻结读数 3 条(cinsscore/binarydefense/dshield),其余新鲜;全量逐行读数见工件 TSV。\n\n## 摘要\n位等价门例:本腿(legacy agent.mjs health)工件即管线 PROBE 工件的字节基线;计数与矩阵读数两腿一致。")]),
  ]);
  const legacy = await runRound("health", "位等价门:legacy 腿 health 轮(全量读数落工件)。", [],
    { models: { models, resolve: () => faux.getModel() }, registrySeed: [] });
  const sc = legacy.registry.find((r) => r.tool === "health_snapshot").sc;
  assert.equal(sc.ok, true, `legacy health_snapshot 信封:${sc.code}`);
  const legacyTsv = sc.artifacts.find((a) => a.endsWith("health-freshness.tsv"));
  const legacyMatrix = sc.artifacts.find((a) => a.endsWith("matrix-scan.json"));
  assert.ok(legacyTsv && legacyMatrix, `legacy 工件缺:${sc.artifacts.join(",")}`);
  const io = mkIo();
  const pipe = await runPipeline({ roundId: "2026-10-23-2344-health", fixturesDir: DEFAULT_FIXTURES_DIR, env: mkTree("tree-2344").env, ...io });
  assert.equal(pipe.ok, true);
  const d = path.join(mkTree("tree-2344").root, "ops", "rounds", "2026-10-23-2344-health");
  const tsvA = fs.readFileSync(legacyTsv), tsvB = fs.readFileSync(path.join(d, "01-probe-freshness.tsv"));
  assert.ok(Buffer.compare(tsvA, tsvB) === 0, `TSV 位等价破口:legacy ${tsvA.length}B vs 管线 ${tsvB.length}B`);
  const mA = fs.readFileSync(legacyMatrix), mB = fs.readFileSync(path.join(d, "01-probe-matrix.json"));
  assert.ok(Buffer.compare(mA, mB) === 0, `matrix 位等价破口:legacy ${mA.length}B vs 管线 ${mB.length}B`);
  // 清单事实层钉住:101 URL 固定 fixture(清单变更须同步本例,feedfix #168 基线)
  const manifestN = +(await execFileP("bash", ["-c", `. "${path.join(AGENT, "lib.sh")}"; extract_feed_urls | wc -l`])).stdout.trim();
  assert.equal(manifestN, 101, `feeds.txt 清单 URL 数=${manifestN}(固定 fixture,变更须同步本例)`);
  const summary = j(path.join(d, "01-probe-summary.json"));
  assert.equal(summary.urls_n, manifestN);
  assert.equal(tsvB.toString().trimEnd().split("\n").length, manifestN, "TSV 行数=清单 URL 数");
  // 计数两口径对拍:legacy sc(frozen/near/unreachable/no_lm/token_required)↔ 管线 buckets+matrix
  assert.deepEqual(
    { urls_n: sc.urls_n, frozen: sc.frozen_n, unreachable: sc.unreachable_n, no_lm: sc.no_lm_n, token_required: sc.token_required_n },
    { urls_n: summary.urls_n, frozen: summary.buckets.frozen, unreachable: summary.buckets.unreachable,
      no_lm: summary.buckets.no_lm, token_required: summary.buckets.token_required });
  assert.equal(sc.matrix_ok, summary.matrix.ok);
  assert.equal(sc.matrix_exit_code, summary.matrix.exit_code);
  assert.equal(summary.matrix.exit_code, 0);
});

await t("replay --dry 全程可跑(CLI 子进程):门全重算 PASS,产物写 -r1/,原件逐字不变", async () => {
  const before = treeMd5(roundDir(R1));
  const r = await spawnPipe(["replay", R1, "--dry"]);
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-300)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  assert.equal(env.pipeline.replayed_of, R1);
  assert.equal(env.pipeline.round_id, `${R1}-r1`);
  assert.equal(env.pipeline.stages.length, 9, "dry 段=PROBE..RETRO(CLOSE 不入重放;含 #182 ANCHOR_SWEEP)");
  assert.ok(env.pipeline.stages.every((s) => s.status === "dry"), "dry 状态词");
  const g = j(path.join(roundDir(`${R1}-r1`), "gates.json"));
  assert.equal(g.records.length, 9, "9 可跑步门全重算(含 G_ANCHOR_SWEEP;CLOSE 不入重放)");
  assert.ok(g.records.every((x) => x.pass), "原件工件上全门重算 PASS(自愈:以工件+门为准)");
  assert.equal(treeMd5(roundDir(R1)), before, "原件零改写");
});

await t("replay 段重放(VERIFY..SYNTH,非 dry):前置工件复制+段内再生,原件不变", async () => {
  const before = treeMd5(roundDir(R1));
  const r = await spawnPipe(["replay", R1, "--from", "VERIFY", "--to", "SYNTH"]);
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-300)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["VERIFY", "TRIAGE", "DISPATCH", "DEEP", "ITEMIZE", "SYNTH"]);
  const d = roundDir(`${R1}-r2`);
  assert.ok(fs.existsSync(path.join(d, "01-probe-summary.json")), "前置工件(PROBE 01-*)复制");
  assert.ok(fs.existsSync(path.join(d, "07-synth-report.md")) && fs.existsSync(path.join(d, "06-itemize-manifest.json")), "段内产物再生(P4:manifest=条目面工件)");
  const itemsAfter = fs.readdirSync(path.join(DOCS, "ops", "items")).filter((f) => f.endsWith(".md")).length;
  assert.equal(itemsAfter, 2, "replay 回声零写:生产条目树不增项(审计重放不改条目面)");
  const rm2 = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([rm2.created, rm2.reopened, rm2.deduped], [2, 0, 0], "manifest 回声原轮 outcome");
  assert.ok(rm2.rows.every((x) => x.echo === true), "行级 echo 标记");
  assert.ok(fs.existsSync(path.join(d, "gates.json")));
  assert.equal(treeMd5(roundDir(R1)), before, "原件零改写");
});

await t("finding 出口:replay 零外发(段重放 ANCHOR_SWEEP..RETRO:finding 在场仍 skip 留痕,同 ITEMIZE 回声律)", async () => {
  const before = treeMd5(roundDir(R1));
  const r = await spawnPipe(["replay", R1, "--from", "ANCHOR_SWEEP", "--to", "RETRO"]);
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-300)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  const fe = env.pipeline.finding_exits;
  assert.ok(fe, "信封留痕在场(replay 面也记 skip 痕)");
  assert.equal(fe.triggered, false, "审计重放零外发(不改生产出口面)");
  assert.match(fe.reason, /replay/);
  assert.equal(fe.gh_issue.status, "skip");
  assert.match(fe.gh_issue.reason, /replay/);
  assert.equal(fe.webhook.status, "skip");
  const d = roundDir(`${R1}-r3`);
  const art = j(path.join(d, "08-anchor-sweep-exits.json"));
  assert.equal(art.phase, "skip", "重放侧出口工件=skip 记录(零外发可审计)");
  assert.equal(treeMd5(roundDir(R1)), before, "原件零改写");
});

await t("CLI 契约:用法错/坏 OPS_PIPELINE/replay 不存在轮/--to CLOSE 均 exit 2 纯 stderr 不发 JSON", async () => {
  const noArgs = await spawnPipe([]);
  assert.equal(noArgs.rc, 2);
  assert.equal(noArgs.stdout, "");
  assert.match(noArgs.stderr, /用法:/);
  const badMode = await spawnPipe(["health"], { OPS_PIPELINE: "bogus" });
  assert.equal(badMode.rc, 2);
  assert.match(badMode.stderr, /OPS_PIPELINE 须 legacy\|pipeline/);
  const noRound = await spawnPipe(["replay", "2020-01-01-0000-health", "--dry"]);
  assert.equal(noRound.rc, 2);
  assert.match(noRound.stderr, /无 state\.json/);
  const toClose = await spawnPipe(["replay", R1, "--to", "CLOSE", "--dry"]);
  assert.equal(toClose.rc, 2);
  assert.match(toClose.stderr, /CLOSE 属原轮时序不入重放/);
});

await t("同 id 重跑拒绝(bad_round 信封)——轮次目录不覆盖(证据不灭失)", async () => {
  const io = mkIo();
  const r = await runPipeline({ roundId: R1, fixturesDir: DEFAULT_FIXTURES_DIR, ...io }); // 审后修 P2-2:钉 faux 面——不钉则选 real 面,bad_round 检查若后移即潜伏真打 API
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "bad_round");
});

// 审后修 P1 负例:注入块展示面=闭合集(anchored≥2 且 anchored∪hits>8 时,块外命中行必须滤除)
await t("SYNTH 注入块=闭合集(命中 10/锚 2:块内仅 ∈injected 的 6 命中+锚补行,块外行必滤)", async () => {
  const { synthInjectionBlock } = await import(path.join(AGENT, "pipeline", "steps.mjs"));
  const hits = Array.from({ length: 10 }, (_, i) => `2026-01-${String(i + 1).padStart(2, "0")}-hit-${i}.md`);
  const anchored = ["2026-02-01-anch-a.md", "2026-02-02-anch-b.md"];
  const injected = [...anchored, ...hits].slice(0, 8); // 锚选在前恒⊆injected
  const stdout = hits.map((n) => `- ${n}`).join("\n");
  const extra = anchored.map((n) => `- ${n}\n  - 锚域 test: gist`);
  const block = synthInjectionBlock(stdout, extra, hits, injected);
  for (const n of hits.slice(6)) assert.ok(!block.includes(n), `块外命中行必须滤除(旧实现整块直出=审 P1): ${n}`);
  for (const n of hits.slice(0, 6)) assert.ok(block.includes(n), `∈injected 命中保留: ${n}`);
  for (const n of anchored) assert.ok(block.includes(n), "锚补行恒保留(锚选⊆injected)");
});

// 审后补 P2:装载对拍持久化(transcript system_sha === 提示词文件 sha;文件缺失/装载漂移即红,取代一次性手验)
await t("模型步装载对拍:TRIAGE/SYNTH transcript system_sha=提示词文件 sha 逐字", async () => {
  const { createHash } = await import("node:crypto");
  const sha = (s) => createHash("sha256").update(s).digest("hex").slice(0, 16);
  const deepTf = fs.readdirSync(run1.dir).find((f) => /^05-deep-.*-transcript\.jsonl$/.test(f));
  for (const [tf, pf] of [["03-triage-transcript.jsonl", "triage"], [deepTf, "deep"], ["07-synth-transcript.jsonl", "synth"]]) {
    const head = fs.readFileSync(path.join(run1.dir, tf), "utf8").split("\n")[0];
    const rec = JSON.parse(head);
    assert.equal(rec.type, "input");
    assert.equal(rec.system_sha, sha(fs.readFileSync(path.join(AGENT, "prompts", "health", `${pf}.md`), "utf8")), `${pf} 装载漂移`);
  }
});

await t("DISPATCH 3-bundle 稳态预算回归(审 P1-1):floor 拆分合计≤轮预算过门;toFixed 形必红", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "p4-gdispatch-"));
  const mk = (per) => {
    fs.writeFileSync(path.join(d, "03-triage-hypotheses.json"), JSON.stringify({ hypotheses: [1, 2, 3].map((i) => ({ signal_id: `https://x/${i}.txt`, need_deep: true, severity: "high", cause_class: "unknown", hypothesis: `h${i}`, probe_hint: "reprobe_get", one_line: `l${i}` })), digest: "d" }));
    fs.writeFileSync(path.join(d, "04-dispatch-bundles.json"), JSON.stringify({ budget_cny: 0.05, bundles: [1, 2, 3].map((i) => ({ hid: `https://x/${i}.txt`, budget_cny: per })), truncated: [] }));
  };
  mk(0.0166); // floor(0.05/3×1e4)/1e4
  assert.equal(GATES.G_DISPATCH({ dir: d, budgetCny: 0.05 }).pass, true, "floor 拆分合计 0.0498≤0.05 必过");
  mk(0.0167); // 旧 toFixed 四舍五入形
  assert.match(GATES.G_DISPATCH({ dir: d, budgetCny: 0.05 }).reason, /预算合计/, "toFixed 形合计 0.0501>0.05 必红(原 P1-1 缺陷钉死)");
  fs.rmSync(d, { recursive: true, force: true });
});

// 审后修 P1-2:跨语言镜像钉子——ops-items digest 与 _ops_items.py 语义对拍(backend/.venv Python 预计算金常量;
// pyJson 仅对扁平 {source:str}/空 args 与 Python json.dumps(sort_keys,ensure_ascii=False) 字节同——嵌套/浮点即分叉,
// 现调用面恒扁平(steps.mjs dispatch);Python 侧改拼接收=本断言红,防两语言镜像静默回声)。
await t("条目摘要镜像钉:ops-items digest=Python 侧金常量(flat a052743a5d/empty 1772523325)", async () => {
  const { mirrorDigestForTest } = await import("./pipeline/ops-items.mjs");
  assert.equal(mirrorDigestForTest({ source: "ciarm", probe_class: "staleness", error_signature: "age_gt_2x_refresh", action: "human_ruling", args: { source: "ciarm" }, latest: "" }), "a052743a5d");
  assert.equal(mirrorDigestForTest({ source: "dshield", probe_class: "unreachable", error_signature: "net_fail", action: "human_ruling", args: {}, latest: "" }), "1772523325");
});

// ══ P5 #167 新例:RETRO 候选闭环/超时分腿镜像/resume 三规则/双模开关/cron 草案 ══

const dismissItem = (itemsDir, itemId) => { // 四键 ignore 的树面终态(字面行替换,_ops_items.set_status 同法)
  const p = path.join(itemsDir, `${itemId}.md`);
  const t = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, t.replace(/\nstatus: ("?)(active|snoozed)\1/, "\nstatus: \"dismissed\""));
};
const itemsOf = (root) => path.join(root, "ops", "items");
const readRules = (root) => j(path.join(root, "ops", "rules", "suppressions.json"));

await t("RETRO 闭环实证(#167 验收):dismissed 同签→候选+adopt_rule 立项→采纳(写规则)→下一轮 VERIFY 生效", async () => {
  const T = mkTree("tree-retro-loop");
  const io1 = mkIo();
  const r1 = await runPipeline({ roundId: "2026-10-24-0200-health", fixturesDir: cloneFixtures("fx-loop1"), env: T.env, ...io1 });
  assert.equal(r1.ok, true, `首轮:${io1.buf.stderr.slice(-200)}`);
  let files = fs.readdirSync(itemsOf(T.root)).filter((f) => f.endsWith(".md"));
  assert.equal(files.length, 2, "首轮 2 条目(ciarm/binarydefense)");
  for (const f of files) dismissItem(itemsOf(T.root), f.replace(/\.md$/, "")); // 四键 ignore 模拟(人裁终态)
  // 第二轮:同签信号幸存(items 已终态不在飞)→ RETRO 产候选+至多一条 adopt_rule 待审条目
  const io2 = mkIo();
  const fx2 = cloneFixtures("fx-loop2");
  writeSynthFx(fx2, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:同签复开(前轮被 ignore)· 建议 human_ruling\n- binarydefense:同签复开 · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=0 reopened=2 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=0\n- 次轮:dismissed 同签复开(链指),RETRO 产候选。");
  const r2 = await runPipeline({ roundId: "2026-10-24-0201-health", fixturesDir: fx2, env: T.env, ...io2 });
  assert.equal(r2.ok, true, `次轮:${io2.buf.stderr.slice(-200)}`);
  const retro2 = j(path.join(T.root, "ops", "retro", "2026-10-24-0201-health.json"));
  assert.equal(retro2.candidates.length, 2, "两条同签误判候选全列清单");
  assert.ok(retro2.candidates.every((c) => c.action === "suppress" && Object.keys(c.match).length >= 2), "草案=suppress 且 match 谓词闭集内");
  const withItem = retro2.candidates.filter((c) => c.item?.outcome === "created");
  const skippedCap = retro2.candidates.filter((c) => c.item?.skipped === "cap");
  assert.equal(withItem.length, 1, "每轮至多一条立项(C稿 §2.2「可选一条」)");
  assert.equal(skippedCap.length, 1, "其余候选留清单不入条目");
  assert.deepEqual(retro2.candidates[0].match, { bucket: "frozen", source: "binarydefense" }, "确定性序首条=matchKey 序最小");
  const retroItem = fs.readFileSync(path.join(itemsOf(T.root), `${withItem[0].item.item_id}.md`), "utf8");
  assert.match(retroItem, /action: "?adopt_rule"?/, "树面 action=adopt_rule(四键写口识别词)");
  assert.match(retroItem, /probe_class: "?adopt_rule"?/);
  assert.match(retroItem, /severity: "?low"?/, "候选条目恒 low(#167 任务面)");
  assert.ok(retroItem.includes("match:"), "args 携草案 match(采纳面读 args)");
  // 四键 agree 模拟(写口=backend _ops_review._adopt_rule;selftest 侧镜像同形落规则——闭环的采纳腿)
  const rules = readRules(T.root);
  rules.version += 1;
  for (const c of retro2.candidates) rules.rules.push({ id: `R${rules.rules.length + 1}`, adopted: "2026-10-24",
    adopted_via: `item:${c.item?.item_id ?? "retro-selftest"}`, match: c.match, action: "suppress", note: c.note, review_at: "2027-01-22" });
  fs.writeFileSync(path.join(T.root, "ops", "rules", "suppressions.json"), JSON.stringify(rules, null, 2) + "\n");
  // 采纳后自然处置面:同签复开条目(次轮重开)随人裁 ignore 终态——规则已接管该类,
  // 复开条目不再在飞(否则 RETRO 通道矛盾面会如实报「规则压信号而条目仍开」)。
  for (const f of fs.readdirSync(itemsOf(T.root)).filter((f) => f.endsWith(".md")))
    dismissItem(itemsOf(T.root), f.replace(/\.md$/, "")); // 已终态(dismissed)重跑替换零变化;active→dismissed
  // 第三轮:采纳的规则在 VERIFY 生效——同签信号被压(留痕),幸存集空,RETRO 零候选(闭环合拢)
  const fx3 = cloneFixtures("fx-loop3");
  fs.writeFileSync(path.join(fx3, "triage.json"), JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", stopReason: "stop",
    text: "{\"hypotheses\":[],\"digest\":\"采纳后零幸存:同签信号已被抑制规则压掉。\"}" }] }] }));
  writeSynthFx(fx3, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- (无幸存信号——同签误判已被采纳规则压制,明细见 suppressed 工件)\n\n抑制 3 条(R1×1+采纳 R2/R3×2——明细见工件)。\n\n## 摘要\n- 计数: created=0 reopened=0 deduped=0 suppressed=3\n- 深验: confirmed=0 refuted=0 unresolved=0\n- 闭环合拢:误判一次,规则防一类。");
  const io3 = mkIo();
  const r3 = await runPipeline({ roundId: "2026-10-24-0202-health", fixturesDir: fx3, env: T.env, ...io3 });
  assert.equal(r3.ok, true, `三轮:${io3.buf.stderr.slice(-300)}`);
  const d3 = path.join(T.root, "ops", "rounds", "2026-10-24-0202-health");
  const sp3 = j(path.join(d3, "02-verify-suppressed.json"));
  assert.equal(sp3.suppressed.length, 3, "R1+两条采纳规则全命中");
  assert.deepEqual(sp3.suppressed.map((x) => x.rule_id).sort(), ["R1", "R2", "R3"]);
  const retro3 = j(path.join(T.root, "ops", "retro", "2026-10-24-0202-health.json"));
  assert.equal(retro3.candidates.length, 0, "零幸存→零新候选(规则已防住该类)");
  const hit = new Map(retro3.rule_hits.map((h) => [h.id, h.hits_n]));
  assert.deepEqual([hit.get("R1"), hit.get("R2"), hit.get("R3")], [1, 1, 1], "规则命中统计入 retro(审计面)");
  assert.deepEqual(retro3.rules_due_review, [], "review_at 未到点零复审行");
  assert.deepEqual(retro3.channel_conflicts, [], "无两通道矛盾");
  const items3 = fs.readdirSync(itemsOf(T.root)).filter((f) => f.endsWith(".md"));
  assert.equal(items3.length, 5, "2 dismissed(首轮)+2 dismissed(次轮复开,随采纳终态)+1 adopt_rule——三轮零新增(已裁防重)");
  const retro3Item = j(path.join(T.root, "ops", "retro", "2026-10-24-0202-health.json"));
  assert.equal(retro3Item.candidates.length, 0, "三轮 RETRO 零新候选(已裁键不重立项)");
});

await t("retroDiff 单元:review_at 到点报复审+两通道矛盾(被抑制信号在 P1 探测器通道在飞)+already_ruled 防饿死", async () => {
  const { retroDiff } = await import("./pipeline/steps.mjs");
  const rules = { version: 2, rules: [
    { id: "R9", action: "suppress", review_at: "2020-01-01", match: {}, note: "x" },   // 到点(零命中)
    { id: "R8", action: "annotate", review_at: "2099-01-01", match: {}, note: "y" } ] };
  const survivors = [];
  const suppressed = [{ signal_id: "u1", dedup_key: "ciarm|download|http_4xx", rule_id: "R9" }];
  const items = [
    { id: "i-live", status: "active", dedup_key: { source: "ciarm", probe_class: "download", error_signature: "http_4xx" } }, // P1 探测器独立通道在飞
    { id: "i-old", status: "dismissed", dedup_key: { source: "ciarm", probe_class: "download", error_signature: "http_4xx" } } ];
  const d = retroDiff({ survivors, suppressed, items, rules, today: "2026-10-24" });
  assert.deepEqual(d.rules_due_review.map((r) => r.id), ["R9"], "到点规则报人复审(零命中也在列)");
  assert.equal(d.rules_due_review[0].hits_n, 1);
  assert.deepEqual(d.channel_conflicts, [{ dedup_key: "ciarm|download|http_4xx", rule_id: "R9", in_flight_items: ["i-live"] }],
    "被抑制信号对照探测器通道:在飞即矛盾(仅报不裁)");
  // 候选推导面:幸存旗标 × dismissed 同签条目(人判误报)→ 候选清单(立项节流/already_ruled 让渡在 RETRO 步,闭环例覆盖)
  const mk = (src) => ({ signal_id: `u-${src}`, dedup_key: `${src}|staleness|age_gt_2x_refresh`, source: src, bucket: "frozen" });
  const dd = retroDiff({ survivors: [mk("aa"), mk("bb")], suppressed: [], items: [
    { id: "d-aa", status: "dismissed", dedup_key: { source: "aa", probe_class: "staleness", error_signature: "age_gt_2x_refresh" } } ],
    rules: { version: 0, rules: [] }, today: "2026-10-24" });
  assert.equal(dd.candidates.length, 1, "仅 dismissed 同签的 aa 成候选(bb 无 dismissed 前科不立项)");
  assert.deepEqual(dd.candidates[0].evidence.dismissed_items, ["d-aa"], "候选证据挂 dismissed 条目(可回算)");
});

await t("超时分腿镜像(#166 审 P2-1):fold net_timeout→timeout;lib.sh _ff_probe curl rc=28 → 第4列 net_timeout", async () => {
  const { foldErrorFamily } = await import("./pipeline/ops-items.mjs");
  assert.equal(foldErrorFamily("net_timeout"), "timeout", "对拍 _ops_detectors._error_family timeout 族");
  assert.equal(foldErrorFamily("net_fail"), "network");
  assert.equal(foldErrorFamily("http_404"), "http_4xx");
  const stubDir = fs.mkdtempSync(path.join(os.tmpdir(), "ff-timeout-"));
  fs.writeFileSync(path.join(stubDir, "curl"), "#!/usr/bin/env bash\n# stub:--max-time 到点 → curl rc 28\nexit 28\n");
  fs.chmodSync(path.join(stubDir, "curl"), 0o755);
  const out = await execFileP("bash", ["-c", `. "${path.join(AGENT, "lib.sh")}"; PATH="${stubDir}:$PATH" _ff_probe https://example.net/feed.txt`]);
  assert.equal(out.stdout.trim(), "https://example.net/feed.txt\tUNREACHABLE\tUNREACHABLE\tnet_timeout", "超时单列(net_fail 分腿)");
  const out2 = await execFileP("bash", ["-c", `. "${path.join(AGENT, "lib.sh")}"; PATH="${stubDir}:$PATH" _ff_probe https://example.net/x.txt; true`]);
  assert.ok(out2.stdout.includes("net_timeout"));
  fs.rmSync(stubDir, { recursive: true, force: true });
});

// ── resume 三规则(#167 验收:各一例)+两负例 ──
const crashState = (root, rid, uptoN) => { // 模拟 crash:截断 stages 至 uptoN 条,置回 in_flight
  const p = path.join(root, "ops", "rounds", rid, "state.json");
  const st = j(p);
  st.stages = st.stages.slice(0, uptoN);
  st.status = "in_flight"; st.stage = st.stages.at(-1)?.name ?? null;
  fs.writeFileSync(p, JSON.stringify(st, null, 2) + "\n");
  return st;
};
await t("resume 三规则①(#167):脚本步幂等重入——SYNTH 后崩,RETRO 重入零双记账,CLOSE 收口", async () => {
  const T = mkTree("tree-res1");
  const rid = "2026-10-24-0300-health";
  const io1 = mkIo();
  assert.equal((await runPipeline({ roundId: rid, fixturesDir: cloneFixtures("fx-res1"), env: T.env, ...io1 })).ok, true);
  const ledger1 = fs.readFileSync(path.join(T.root, "ops", "ledger.md"), "utf8");
  crashState(T.root, rid, 7); // 保留 PROBE..SYNTH 七记录,RETRO 未记录=崩溃现场
  const { runResume } = await import("./pipeline.mjs");
  const io2 = mkIo();
  const r = await runResume({ roundId: rid, env: T.env, ...io2 });
  assert.equal(r.ok, true, `resume:${io2.buf.stderr.slice(-300)}`);
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.recovered, undefined, "SYNTH 已记录零重入");
  const rt = stageOf(r.envelope, "RETRO");
  assert.equal(rt.recovered, "rerun", "脚本步幂等重入");
  const st = j(path.join(T.root, "ops", "rounds", rid, "state.json"));
  assert.equal(st.status, "done");
  const ledger2 = fs.readFileSync(path.join(T.root, "ops", "ledger.md"), "utf8");
  assert.equal(ledger2.split(`pipeline:${rid}`).length - 1, 1, "台账幂等:恢复重入 RETRO 不双记行");
  assert.match(io2.buf.stderr, /\[stage\] RESUME start/);
});

await t("resume 三规则②(#167):模型步工件齐 → 只补门不重花 token(attempts=0/usage=null/gate_only)", async () => {
  const T = mkTree("tree-res2");
  const rid = "2026-10-24-0301-health";
  const io1 = mkIo();
  assert.equal((await runPipeline({ roundId: rid, fixturesDir: cloneFixtures("fx-res2"), env: T.env, ...io1 })).ok, true);
  crashState(T.root, rid, 6); // 崩在 SYNTH 前:state 未推进,但 07-* 工件完整(写盘后崩溃)
  const { runResume } = await import("./pipeline.mjs");
  const io2 = mkIo();
  const r = await runResume({ roundId: rid, env: T.env, ...io2 });
  assert.equal(r.ok, true, `resume:${io2.buf.stderr.slice(-300)}`);
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.status, "done");
  assert.equal(sy.attempts, 0, "零模型调用(attempts=0)");
  assert.equal(sy.usage, null, "零 token 花费面");
  assert.equal(sy.recovered, "gate_only", "只补门评估");
  assert.equal(r.envelope.pipeline.resumed_from, "SYNTH", "信封 resumed_from=恢复起点");
  assert.ok(fs.readFileSync(path.join(T.root, "ops", "rounds", rid, "07-synth-transcript.jsonl"), "utf8").length > 0, "transcript 零重写");
});

await t("resume 三规则③(#167):模型步工件缺 → 重跑(attempts=1);DEEP 逐假设粒度=缺谁重跑谁", async () => {
  const T = mkTree("tree-res3");
  const rid = "2026-10-24-0302-health";
  const io1 = mkIo();
  assert.equal((await runPipeline({ roundId: rid, fixturesDir: cloneFixtures("fx-res3"), env: T.env, ...io1 })).ok, true);
  const dir = path.join(T.root, "ops", "rounds", rid);
  crashState(T.root, rid, 4); // 崩在 DEEP 前:DISPATCH 记录在;DEEP 之后工件(SYNTH 07-*)按步序不可能在场,一并清
  fs.rmSync(path.join(dir, "05-deep-verdicts.json"));
  fs.rmSync(path.join(dir, "05-deep-https-cinsscore.com-list-ci-badguys.txt.json")); // 首假设工件也缺(假设级崩溃)
  fs.rmSync(path.join(dir, "07-synth-report.md"));
  fs.rmSync(path.join(dir, "07-synth-transcript.jsonl"));
  // 崩溃现场 fixtures_dir 仍在(state 真源);SYNTH 重跑的计数面=恢复轮 manifest(deduped=2)
  writeSynthFx(path.join(TMP, "fx-res3"), "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:恢复轮重跑 · 建议 human_ruling\n- binarydefense:恢复轮重跑 · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=0 reopened=0 deduped=2 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=0\n- resume 三规则③:SYNTH 工件缺重跑。");
  const { runResume } = await import("./pipeline.mjs");
  const io2 = mkIo();
  const r = await runResume({ roundId: rid, env: T.env, ...io2 });
  assert.equal(r.ok, true, `resume:${io2.buf.stderr.slice(-300)}`);
  const deep = stageOf(r.envelope, "DEEP");
  assert.equal(deep.attempts, 1, "仅缺工件假设重跑(1/2,不重花已齐假设)");
  assert.equal(deep.recovered, "gate_partial");
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.attempts, 1, "SYNTH 工件缺 → 重跑(损失仅该步 token)");
  assert.equal(sy.recovered, "rerun");
  assert.equal(j(path.join(dir, "state.json")).resume_count, 1);
});

await t("resume 负例(#167):二次恢复拒绝(至多一次)+龄>16h 拒绝(stale)——CLI 面兜底(boot 扫描同判)", async () => {
  const T = mkTree("tree-res4");
  const rid = "2026-10-24-0303-health";
  const io1 = mkIo();
  assert.equal((await runPipeline({ roundId: rid, fixturesDir: cloneFixtures("fx-res4"), env: T.env, ...io1 })).ok, true);
  const st = crashState(T.root, rid, 6);
  st.resume_count = 1;
  fs.writeFileSync(path.join(T.root, "ops", "rounds", rid, "state.json"), JSON.stringify(st, null, 2) + "\n");
  const { runResume } = await import("./pipeline.mjs");
  const io2 = mkIo();
  await assert.rejects(() => runResume({ roundId: rid, env: T.env, ...io2 }), /自动恢复已用尽/);
  st.updated_at = new Date(Date.now() - 17 * 3600_000).toISOString();
  st.resume_count = 0;
  fs.writeFileSync(path.join(T.root, "ops", "rounds", rid, "state.json"), JSON.stringify(st, null, 2) + "\n");
  await assert.rejects(() => runResume({ roundId: rid, env: T.env, ...io2 }), /16h/);
  const r2 = await spawnPipe(["resume", rid], T.env);
  assert.equal(r2.rc, 1);
  assert.match(JSON.parse(r2.stdout.trim().split("\n").pop()).error.message, /16h/, "CLI 面:infra 信封(boot 扫描已处置时的兜底)");
});

await t("双模灰度开关(#167 终检):agent.mjs OPS_PIPELINE=pipeline → 委派 pipeline.mjs(信封带 pipeline.stages);legacy 缺省零变化", async () => {
  const { main: agentMain } = await import("./agent.mjs");
  const T = mkTree("tree-switch");
  const ioP = mkIo();
  const rcP = await agentMain(["health", "cron 灰度冒烟", "--fixtures", DEFAULT_FIXTURES_DIR], { env: { ...T.env, OPS_PIPELINE: "pipeline" }, ...ioP }); // --fixtures 透传 argv→pipeline.mjs=faux 面(#170;委派契约面非 provider 面)
  assert.equal(rcP, 0, `pipeline 腿:${ioP.buf.stderr.slice(-300)}`);
  const envP = JSON.parse(ioP.buf.stdout.trim().split("\n").pop());
  assert.equal(envP.ok, true);
  assert.ok(Array.isArray(envP.pipeline?.stages) && envP.pipeline.stages.length >= 9, "委派状态机路径(信封 pipeline 扩展字段)");
  assert.match(ioP.buf.stderr, /\[stage\] PROBE start/, "stderr stage 行族(驾驶舱 SSE 透传面)");
  const T2 = mkTree("tree-switch-legacy");
  const ioL = mkIo();
  const faux2 = (await import("@earendil-works/pi-ai"));
  const faux = faux2.fauxProvider({ models: [{ id: "faux-legacy" }] });
  const models = faux2.createModels();
  models.setProvider(faux.provider);
  faux.setResponses([
    faux2.fauxAssistantMessage([faux2.fauxToolCall("health_snapshot", {}, { id: "call_sw1" })], { stopReason: "toolUse" }),
    faux2.fauxAssistantMessage([faux2.fauxText("## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- legacy 冒烟:冻结读数 3 条,见工件。\n\n## 摘要\nOPS_PIPELINE 缺省 legacy:agent.mjs 现状路径零变化(退出码/信封同形)。")]),
  ]);
  const rcL = await agentMain(["health", "legacy 冒烟"], { env: T2.env, stdout: ioL.stdout, stderr: ioL.stderr, models: { models, resolve: () => faux.getModel() } });
  assert.equal(rcL, 0, `legacy 腿:${ioL.buf.stderr.slice(-300)}`);
  const envL = JSON.parse(ioL.buf.stdout.trim().split("\n").pop());
  assert.equal(envL.ok, true);
  assert.equal(envL.pipeline, undefined, "legacy 信封无 pipeline 扩展(现状零回归)");
});

await t("cron 草案 schema 校验(#167 交付③):错峰 04:00/8h+同 seam POST+鉴权矩阵注记+409 零排队语义", async () => {
  const doc = fs.readFileSync(path.join(AGENT, "..", "..", "deploy", "ops-cron.md"), "utf8");
  assert.match(doc, /0 4-23\/8 \* \* \*/, "crontab 行=04:00 起错峰(三小裁③)");
  assert.ok(doc.includes("POST /api/ops/rounds"), "同 seam 触发(不新开路由)");
  assert.ok(doc.includes("FROZEN 鉴权矩阵"), "鉴权矩阵核对注记在案");
  assert.ok(doc.includes("409") && doc.includes("不排队"), "409=跳过留痕退出码 0(健康快照无回填)");
  assert.ok(doc.includes("OPS_PIPELINE=pipeline"), "灰度开关部署面在案");
  assert.ok(!doc.includes("OPS_CRON_PASSWORD=\"") || !/OPS_CRON_PASSWORD="[^\$<]/.test(doc), "草案不含真实凭据(占位形)");
});

// 审后修 P1:规则文件缺席=合法零规则态(bootstrap 死锁除根:缺席 infra 则首轮必死、adopt_rule 永不可达);坏文件仍终态。
await t("VERIFY 缺席规则库:零抑制照常过+空库形快照(审后修 P1)", async () => {
  const { runStage } = await import("./pipeline/steps.mjs");
  const { GATES } = await import("./pipeline/gates.mjs");
  const { HEALTH_PIPELINE } = await import("./pipeline.mjs");
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "p5-norules-"));
  fs.mkdirSync(path.join(d, "items"), { recursive: true });
  fs.writeFileSync(path.join(d, "01-probe-summary.json"), JSON.stringify({ urls_n: 2, buckets: { fresh: 1, frozen: 1 }, matrix: { ok: true, exit_code: 0, violation_n: 0 }, flags: [{ signal_id: "https://x/a.txt", source: "a", bucket: "frozen" }, { signal_id: "https://x/b.txt", source: "b", bucket: "unreachable" }] }));
  const def = HEALTH_PIPELINE.find((x) => x.name === "VERIFY");
  const ctx = { dir: d, rulesFile: path.join(d, "rules-absent.json"), itemsDir: path.join(d, "items"), state: { replay_of: null }, env: {} };
  await runStage(def, ctx); // 不抛=零抑制照常过
  const snap = j(path.join(d, "02-verify-rules.json"));
  assert.deepEqual(snap, { version: 0, rules: [] }, "缺席时快照落空库形");
  const sv = j(path.join(d, "02-verify-survivors.json"));
  assert.equal(sv.survivors.length, 2, "零规则=全部幸存");
  assert.equal(GATES.G_VERIFY({ ...ctx, dir: d }).pass, true, "门同口径(缺席=零规则,非 infra)");
  fs.rmSync(d, { recursive: true, force: true });
});

// ── ⑫ #170 真接线程:面选择纯函数 + 真面 fake 传输层(零网络;注入缝=ctx.models,agent.mjs opts.models 同型)──
await t("⑫-面选择纯函数:显式 fixtures→faux/继承面优先/缺省→real;STEP_ROUND 映射;state.model_face 落盘", async () => {
  assert.equal(selectModelFace({}), "real", "缺省=运行面真 provider(生产/cron 轮无 --fixtures)");
  assert.equal(selectModelFace({ fixturesExplicit: true }), "faux", "显式 fixtures=faux 面(自测/golden)");
  assert.equal(selectModelFace({ fixturesExplicit: true, inherited: "real" }), "faux", "显式 fixtures 赢过继承面(零成本审计 override)");
  assert.equal(selectModelFace({ inherited: "faux" }), "faux", "继承面(replay 保真)");
  assert.deepEqual(STEP_ROUND, { TRIAGE: "health", SYNTH: "health", DEEP: "discover" }, "步→models.mjs 轮键映射(flash/glm-5.3)");
  const st = j(path.join(roundDir(R1), "state.json"));
  assert.equal(st.model_face, "faux", "显式 fixtures 轮 state.model_face=faux(面入 state 审计面)");
});

await t("⑫-faux 面:真 provider 装载缝零触碰(毒缝哨兵不被调=构造不调用)+ transcript 行型不变", async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "p170-faux-"));
  fs.writeFileSync(path.join(d, "02-verify-survivors.json"), JSON.stringify({ survivors: [], known_noise_digest: [] }));
  let seamTouched = 0;
  const ctx = { dir: d, fixturesDir: cloneFixtures("fx-p170-faux"), modelFace: "faux", state: { replay_of: null }, env: {},
    models: { resolve: () => { seamTouched += 1; throw new Error("faux 面不得触碰 provider 缝"); }, // 毒缝:真面首动作即读 ctx.models(providerBundle),误入真面必炸
      models: { streamSimple: () => { seamTouched += 1; throw new Error("faux 面不得触碰传输层"); } } } };
  const r = await runModelStep(HEALTH_PIPELINE.find((x) => x.name === "TRIAGE"), ctx, null);
  assert.ok(Array.isArray(JSON.parse(r.text).hypotheses), "faux 面 canned 输出走通");
  assert.equal(seamTouched, 0, "毒缝零触碰=真 provider 构造不调用(fixtures 面恒 faux)");
  const tl = fs.readFileSync(path.join(d, "03-triage-transcript.jsonl"), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  assert.equal(tl[0].type, "input");
  assert.equal(tl[0].model, undefined, "faux 面 input 行不带 model 字段(行型逐字节不变)");
  assert.ok(!tl.some((x) => x.type === "registry_seed"), "TRIAGE 单发步零 seed 行");
  fs.rmSync(d, { recursive: true, force: true });
});

await t("⑫-真面信封形状(fake 传输层驱动,零网络):轮键解析+usage 数字回传+transcript model 字段+失败面", async () => {
  const { fauxProvider, createModels } = await import("@earendil-works/pi-ai");
  const fakeIO = (text, stopReason = "stop") => {
    const fx = fauxProvider({ models: [{ id: "fake-transport" }] });
    const m = createModels();
    m.setProvider(fx.provider);
    fx.setResponses([{ role: "assistant", content: [{ type: "text", text }], stopReason }]);
    const resolveCalls = [];
    return { models: { models: m, resolve: (round) => { resolveCalls.push(round); return fx.getModel(); } }, resolveCalls };
  };
  // TRIAGE 真面:轮键=health(flash);usage(传输层实报/估算)数字回传=信封与台账原料;transcript 带 model
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "p170-real-"));
  fs.writeFileSync(path.join(d, "02-verify-survivors.json"), JSON.stringify({ survivors: [], known_noise_digest: [] }));
  const f1 = fakeIO(JSON.stringify({ hypotheses: [] }));
  const ctx1 = { dir: d, modelFace: "real", state: { replay_of: null }, env: {}, log: () => {}, ...f1 };
  const tri = await runModelStep(HEALTH_PIPELINE.find((x) => x.name === "TRIAGE"), ctx1, null);
  assert.deepEqual(f1.resolveCalls, ["health"], "TRIAGE 真面→health 轮键(缺省 glm-5.3-flash)");
  assert.ok(tri.usage.input > 0 && tri.usage.output > 0, `真 usage 数字回传:${JSON.stringify(tri.usage)}`);
  const tl = fs.readFileSync(path.join(d, "03-triage-transcript.jsonl"), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  assert.deepEqual(tl.map((x) => x.type), ["input", "message"], "真面 TRIAGE 行型:input+message,零 registry_seed(单发步无工具面;DEEP 真面见⑬)");
  assert.equal(tl[0].model, "faux/fake-transport", "真面 input 行带 model 字段(provider/id)");
  // DEEP 真面:轮键=discover(glm-5.3)
  const f2 = fakeIO(JSON.stringify({ verdict: "unresolved", one_line: "x", evidence: [] }));
  const ctx2 = { dir: d, modelFace: "real", state: { replay_of: null }, env: {}, log: () => {}, ...f2 };
  await runModelStep(HEALTH_PIPELINE.find((x) => x.name === "DEEP"), ctx2,
    { hid: "h-real", budget_cny: 0.01, prompt_pkg: { hypothesis: "h", cause_class: "frozen_feed", severity: "low", probe_hint: "reprobe_get", url: "(t)", precedent_hits: [] } });
  assert.deepEqual(f2.resolveCalls, ["discover"], "DEEP 真面→discover 轮键(缺省 glm-5.3)");
  assert.ok(fs.existsSync(path.join(d, "05-deep-h-real-transcript.jsonl")), "DEEP 逐假设 transcript 落盘");
  // 失败面:stopReason=error→model_face(同 faux 路径;留痕先于失败面判定)
  const d3 = fs.mkdtempSync(path.join(os.tmpdir(), "p170-real-err-"));
  fs.writeFileSync(path.join(d3, "02-verify-survivors.json"), JSON.stringify({ survivors: [], known_noise_digest: [] }));
  const f3 = fakeIO("", "error");
  const ctx3 = { dir: d3, modelFace: "real", state: { replay_of: null }, env: {}, log: () => {}, ...f3 };
  await assert.rejects(() => runModelStep(HEALTH_PIPELINE.find((x) => x.name === "TRIAGE"), ctx3, null),
    (e) => /模型失败面 stopReason=error/.test(e.message) && e.code === "model_face");
  const errTl = fs.readFileSync(path.join(d3, "03-triage-transcript.jsonl"), "utf8");
  assert.ok(errTl.includes('"type":"input"'), "失败面 transcript 仍留痕(留痕先于失败面判定)");
  fs.rmSync(d, { recursive: true, force: true }); fs.rmSync(d3, { recursive: true, force: true });
});

await t("⑫-预算三闸真面同执法:G_DEEP 对真面工件(unresolved 过门/伪 call_id 拒门;微探针 ≤3 恒过)", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const { fauxProvider, createModels } = await import("@earendil-works/pi-ai");
  const mkRealDeep = async (d, verdictJson) => {
    const fx = fauxProvider({ models: [{ id: "fake-transport" }] });
    const m = createModels(); m.setProvider(fx.provider);
    fx.setResponses([{ role: "assistant", content: [{ type: "text", text: verdictJson }], stopReason: "stop" }]);
    fs.writeFileSync(path.join(d, "04-dispatch-bundles.json"), JSON.stringify({ budget_cny: 0.05, est_per_hyp_cny: 0.016, max_hypotheses: 3,
      bundles: [{ hid: "h1", budget_cny: 0.01, prompt_pkg: { hypothesis: "h", cause_class: "frozen_feed", severity: "low", probe_hint: "reprobe_get", url: "(t)", precedent_hits: [] } }], truncated: [], degraded: false }));
    const def = HEALTH_PIPELINE.find((x) => x.name === "DEEP");
    const ctx = { dir: d, modelFace: "real", state: { replay_of: null }, env: {}, models: { models: m, resolve: () => fx.getModel() } };
    const io = steps.modelIO(def);
    const item = io.items(ctx)[0];
    await io.consume(ctx, item, await runModelStep(def, ctx, item));
    await io.finalize(ctx, { degradedItems: [] });
    return { gate: GATES.G_DEEP({ ...ctx, budgetCny: 0.05 }), transcript: fs.readFileSync(path.join(d, "05-deep-h1-transcript.jsonl"), "utf8") };
  };
  // 正例:真面 unresolved(零探针调用→不裁)零 evidence 过门
  const d1 = fs.mkdtempSync(path.join(os.tmpdir(), "p170-gd-pass-"));
  const g1 = await mkRealDeep(d1, JSON.stringify({ verdict: "unresolved", one_line: "真面零探针调用,不裁", evidence: [] }));
  assert.equal(g1.gate.pass, true, `unresolved 零证据腿合法:${g1.gate.reason}`);
  assert.equal(g1.transcript.split("\n").filter((l) => l.includes('"type":"registry_seed"')).length, 0, "真面零 seed 行(微探针 ≤3/假设恒过)");
  // 负例:confirmed 伪 call_id(无登记表回引)→ G_DEEP 拒(A 一律真面同执法)
  const d2 = fs.mkdtempSync(path.join(os.tmpdir(), "p170-gd-fail-"));
  const g2 = await mkRealDeep(d2, JSON.stringify({ verdict: "confirmed", one_line: "x", evidence: [{ call_id: "call-x", field: "age_days" }] }));
  assert.equal(g2.gate.pass, false, "confirmed 证据腿必须回引登记表(真面无探针=不可 confirmed)");
  assert.match(g2.gate.reason, /未知 call_id|缺值/, `A 一律真面同执法:${g2.gate.reason}`);
  fs.rmSync(d1, { recursive: true, force: true }); fs.rmSync(d2, { recursive: true, force: true });
});

// ── ⑬ #173 微探针真工具:单元面(fake fetch 层注入)+ 真面 DEEP 端到端(fake 传输层+fake fetch)──
await t("⑬-微探针单元(fake fetch 层):三工具读数形状+Range/UA 变体在位+登记行 call_id 唯一", async () => {
  const { mkMicroprobeHost, PROBE_UA_VARIANT, PROBE_RANGE_MAX, PROBE_TIMEOUT_MS } = await import("./pipeline/microprobes.mjs");
  const LM = new Date(Date.now() - 220 * 86_400_000).toUTCString();
  const calls = [];
  const fakeFetch = async (url, opts) => { calls.push({ url, opts });
    if (opts.method === "HEAD") throw Object.assign(new Error("HTTP 405"), { code: "http_error", status: 405 });
    return { finalUrl: url, status: 206, headers: { "last-modified": LM, server: "nginx", "content-type": "text/plain" }, body: Buffer.from("x"), bytes: 1 }; };
  const host = mkMicroprobeHost({ fetchImpl: fakeFetch });
  const byName = (n) => host.tools.find((x) => x.name === n);
  assert.deepEqual(host.tools.map((x) => x.name).sort(), ["reprobe_get", "reprobe_ua", "upstream_check"].sort(), "工具闭集=deep.md 微探针表 3 只");
  const g = await byName("reprobe_get").execute("u1", { url: "https://example.org/feed.txt" });
  assert.equal(calls[0].opts.method, "GET");
  assert.equal(calls[0].opts.headers.range, `bytes=0-${PROBE_RANGE_MAX - 1}`, "GET+Range ≤256KB 在位");
  assert.equal(calls[0].opts.timeoutMs, PROBE_TIMEOUT_MS, "超时硬上限 15s(lib.sh FEED_TIMEOUT_S 判例)");
  assert.deepEqual(g.structuredContent, { ok: true, url: "https://example.org/feed.txt", final_url: "https://example.org/feed.txt",
    method: "GET", status: 206, last_modified: LM, age_days: 220, bytes: 1 }, "结构化读数形状(age_days 从 Last-Modified 实算)");
  assert.match(g.content[0].text, /^\[call_id=u1\]/, "call_id 上翻给模型(evidence 回引原料)");
  const u = await byName("reprobe_ua").execute("u2", { url: "https://example.org/feed.txt" });
  assert.equal(calls[1].opts.headers["user-agent"], PROBE_UA_VARIANT, "换 UA 变体复测(对照探测假象)");
  assert.notEqual(calls[1].opts.headers["user-agent"], "ip-radar-ops-agent/1.0", "≠探测 UA(tools.mjs UA)");
  assert.equal(u.structuredContent.ua, PROBE_UA_VARIANT);
  assert.equal(u.structuredContent.status, 206);
  const up = await byName("upstream_check").execute("u3", { url: "https://example.org/project" });
  assert.equal(calls[2].opts.method, "HEAD");
  assert.equal(calls[3].opts.method, "GET");
  assert.equal(calls[3].opts.headers.range, "bytes=0-0", "HEAD 被拒→GET Range 0-0 降级(lib.sh _ff_probe_once 同型)");
  assert.equal(up.structuredContent.method, "GET");
  assert.equal(up.structuredContent.server, "nginx");
  assert.equal(up.structuredContent.content_type, "text/plain");
  assert.equal(host.seeds.length, 3);
  assert.deepEqual(host.seeds.map((s) => s.call_id), ["u1", "u2", "u3"], "登记行=已执行调用(chronological)");
  assert.ok(host.seeds.every((s) => ["reprobe_get", "reprobe_ua", "upstream_check"].includes(s.tool)), "登记行 tool ∈ 闭集(G_DEEP 执法面)");
  assert.equal(new Set(host.seeds.map((s) => s.call_id)).size, 3, "call_id 唯一");
});

await t("⑬-失败信封形状:网络/超时族 {ok:false,code,reason} 如实落登记行,无读数字段(禁入 evidence 面=G_DEEP 执法)", async () => {
  const { mkMicroprobeHost } = await import("./pipeline/microprobes.mjs");
  const { resolveField } = await import("./tools.mjs");
  const fakeFetch = async () => { throw Object.assign(new Error("fetch failed: Headers Timeout Error"), { code: "timeout" }); };
  const host = mkMicroprobeHost({ fetchImpl: fakeFetch });
  const r = await host.tools.find((x) => x.name === "reprobe_get").execute("f1", { url: "https://example.org/feed.txt" });
  assert.deepEqual(r.structuredContent, { ok: false, code: "timeout", reason: "fetch failed: Headers Timeout Error" }, "失败信封={ok:false,code,reason} 错误族");
  assert.match(r.content[0].text, /失败信封 code=timeout/);
  assert.deepEqual(host.seeds, [{ call_id: "f1", tool: "reprobe_get", sc: { ok: false, code: "timeout", reason: "fetch failed: Headers Timeout Error" } }],
    "失败腿留痕在登记面(deep.md:另记不占 evidence)");
  assert.equal(resolveField(host.seeds[0].sc, "age_days"), undefined, "失败信封无读数字段(无证据即无话)");
});

await t("⑬-预算闸:第 4 次调用=明确拒绝信封(code=budget)零网络零登记(≤3 由轻载端执行,研究 #46)", async () => {
  const { mkMicroprobeHost } = await import("./pipeline/microprobes.mjs");
  const calls = [];
  const fakeFetch = async (url) => { calls.push(url);
    return { finalUrl: url, status: 200, headers: { "last-modified": new Date().toUTCString() }, body: Buffer.alloc(0), bytes: 0 }; };
  const host = mkMicroprobeHost({ fetchImpl: fakeFetch });
  const seq = ["reprobe_get", "reprobe_ua", "upstream_check", "reprobe_get"];
  const rs = [];
  for (let i = 0; i < 4; i++) rs.push(await host.tools.find((x) => x.name === seq[i]).execute(`b${i}`, { url: "https://example.org/feed.txt" }));
  assert.ok(rs.slice(0, 3).every((r) => r.structuredContent.ok === true), "前 3 次正常执行");
  assert.equal(rs[3].structuredContent.ok, false);
  assert.equal(rs[3].structuredContent.code, "budget", "拒绝信封明确 code");
  assert.match(rs[3].content[0].text, /unresolved/, "拒绝信封指明出路(转 unresolved)");
  assert.equal(calls.length, 3, "第 4 次零网络(拒绝先于执行)");
  assert.equal(host.seeds.length, 3, "拒绝不发登记行(G_DEEP seed 计数=已执行探测,拒绝后 unresolved 仍过门=与门双重执法)");
});

await t("⑬-真面 DEEP 端到端(fake 传输层+fake fetch):真工具调用→registry_seed 行→A 一律回填→G_DEEP 过门", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const { fauxProvider, createModels, fauxToolCall, fauxAssistantMessage } = await import("@earendil-works/pi-ai");
  const LM = new Date(Date.now() - 220 * 86_400_000).toUTCString();
  const fetches = [];
  const fakeFetch = async (url, opts) => { fetches.push({ url, opts });
    return { finalUrl: url, status: 206, headers: { "last-modified": LM }, body: Buffer.from("1.2.3.4"), bytes: 7 }; };
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "p173-real-deep-"));
  fs.writeFileSync(path.join(d, "04-dispatch-bundles.json"), JSON.stringify({ budget_cny: 0.05, est_per_hyp_cny: 0.016, max_hypotheses: 3,
    bundles: [{ hid: "h1", budget_cny: 0.01, prompt_pkg: { hypothesis: "若冻结读数为真,GET 复测 age_days 保持高位", cause_class: "frozen_feed", severity: "high", probe_hint: "reprobe_get", url: "https://example.org/feed.txt", precedent_hits: [] } }], truncated: [], degraded: false }));
  const fx = fauxProvider({ models: [{ id: "fake-transport" }] });
  const m = createModels(); m.setProvider(fx.provider);
  fx.setResponses([
    fauxAssistantMessage([fauxToolCall("reprobe_get", { url: "https://example.org/feed.txt" }, { id: "call-t1" })]),
    fauxAssistantMessage(JSON.stringify({ hypothesis_id: "h1", verdict: "confirmed", one_line: "GET 复测 age_days=220,冻结确证", evidence: [{ call_id: "call-t1", field: "age_days" }] })),
  ]);
  const def = HEALTH_PIPELINE.find((x) => x.name === "DEEP");
  const ctx = { dir: d, modelFace: "real", state: { replay_of: null }, env: {}, log: () => {},
    models: { models: m, resolve: () => fx.getModel() }, probeFetch: fakeFetch };
  const io = steps.modelIO(def);
  const item = io.items(ctx)[0];
  await io.consume(ctx, item, await runModelStep(def, ctx, item));
  await io.finalize(ctx, { degradedItems: [] });
  assert.equal(fetches.length, 1, "真面 Agent 真执行微探针工具(fake fetch 层)");
  assert.equal(fetches[0].opts.headers.range, `bytes=0-${256 * 1024 - 1}`, "Range 头经 Agent 真调用在位");
  const tl = fs.readFileSync(path.join(d, "05-deep-h1-transcript.jsonl"), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  const seed = tl.find((x) => x.type === "registry_seed");
  assert.ok(seed, "真面 transcript 有 registry_seed 行");
  assert.deepEqual([seed.call_id, seed.tool, seed.sc.ok, seed.sc.age_days], ["call-t1", "reprobe_get", true, 220],
    "登记行与 faux 面同型 {type,call_id,tool,sc}(#173:真面开箱即用不另起炉灶)");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.deepEqual(v.verdicts[0].evidence, [{ call_id: "call-t1", field: "age_days", value: 220 }], "A 一律:宿主从登记表回填值");
  const gate = GATES.G_DEEP({ ...ctx, budgetCny: 0.05 });
  assert.equal(gate.pass, true, `G_DEEP 真面开箱即用(三元组逐字回引+≤3):${gate.reason}`);
  fs.rmSync(d, { recursive: true, force: true });
});

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`pipeline-selftest: PASS=${pass} FAIL=${fail}`);
process.exit(fail ? 1 : 0);
