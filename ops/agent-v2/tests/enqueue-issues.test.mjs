// enqueue-issues.test.mjs — #384 发现轮 ENQUEUE 出口改 GH issue 测试面。
// 三态 stub 测试(票面验收:成功/fail-soft/无 token,零真网——exec 注入替身,不打 gh 二进制)
// + 纯函数 dry(issue 草稿 title/body/label 断言)+ faux 零外发 + emit 守卫 + 相位步集成
// (d4-enqueue.json 与 v1 同形、queue.md 零写口)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { candidateIssueDraft, runEnqueueIssueExit, enqueueStageIssueExit, ENQUEUE_ISSUES_ARTIFACT } from "../tools/enqueue-issues.mjs";
import { ARTIFACTS as A } from "../../pipeline-core/artifacts.mjs";

const ROUND = "2026-06-01-0400-discover";
// 夹具候选(ops/pipeline-core/fixtures/pipeline 全轮例同源形状:rDNS 过三判据;carrier 双面不可算)
const FX_SH = { candidates: [
  { name: "rDNS 主机名", url: "https://ip.thc.org", quote: "ip.thc.org 月度全量 parquet(49.5GB,HF+镜像双源实测活)", evidence_ptr: "NEEDS.md:L14", source_channel: "needs", exclusivity_estimate: 0.42, notes: "缺口:反解析维度无本地源" },
  { name: "carrier / is_isp 出中国段", url: null, quote: "IPinfo carrier 批量库", evidence_ptr: "NEEDS.md:L17", source_channel: "needs", exclusivity_estimate: null, notes: "无 URL" },
] };
const FX_ME = { results: [
  { candidate: "rdns", name: "rDNS 主机名", evidence_local_ok: true, url_read_ok: true, url_read_code: 200, control_executable: true, status: "measured", uncertainty_reason: null, exclusivity_estimate: 0.42 },
  { candidate: "carrier_is_isp", name: "carrier / is_isp 出中国段", evidence_local_ok: false, url_read_ok: null, url_read_code: null, control_executable: false, status: "uncertainty", uncertainty_reason: "无 URL 候选", exclusivity_estimate: null },
] };
const ROWS = [{ candidate: "rdns", name: "rDNS 主机名", reasons: [] }];

function tmpDir() { return fs.mkdtempSync(path.join(os.tmpdir(), "v2-enq-issues-")); }

test("纯函数 dry:夹具候选 → issue 草稿 title/body/label(票面验收「手动 dry」同面;零网络)", () => {
  const d = candidateIssueDraft({ roundId: ROUND, row: ROWS[0], c: FX_SH.candidates[0], m: FX_ME.results[0] });
  assert.equal(d.title, `[source] rdns 发现轮候选(${ROUND})`);
  assert.deepEqual(d.labels, ["needs-triage"]);
  assert.match(d.body, /## 来源步/, "来源步段");
  assert.match(d.body, /- 名称:rDNS 主机名/);
  assert.match(d.body, /- URL:https:\/\/ip\.thc\.org/);
  assert.match(d.body, /- 渠道:needs/);
  assert.match(d.body, /- 排他率估值:0\.42/);
  assert.match(d.body, /- 逐字引用:ip\.thc\.org 月度全量 parquet/);
  assert.match(d.body, /- 证据指针:NEEDS\.md:L14/);
  assert.match(d.body, /ops\/rounds\/2026-06-01-0400-discover\/d2-shortlist\.json/, "证据指针段带轮工件路径");
  assert.match(d.body, /ops\/rounds\/2026-06-01-0400-discover\/enqueue-issues\.json/);
  assert.match(d.body, /needs-triage 人裁终局/);
  assert.ok(!/预估行数/.test(d.body), "管线无此读数,不虚构(无证据即无话)");
});

test("三态①成功:stub exec 零退出码 → created+issue_url 计数;工件 phase=emitted(审计面)", async () => {
  const dir = tmpDir();
  const calls = [];
  const exec = async (cmd, argv) => { calls.push([cmd, ...argv]); return { stdout: "https://github.com/steponeerror/ip-radar/issues/123\n" }; };
  const r = await runEnqueueIssueExit({ roundId: ROUND, dir, rows: ROWS, shortlist: FX_SH, measure: FX_ME,
    modelFace: "real", env: { GH_TOKEN: "ghp_test", OPS_GH_REPO: "steponeerror/ip-radar" }, exec });
  assert.equal(r.status, "emitted");
  assert.equal(r.issues_opened, 1);
  assert.equal(r.issues_failed, 0);
  assert.equal(r.issues[0].issue_url, "https://github.com/steponeerror/ip-radar/issues/123");
  assert.equal(r.issues[0].status, "created");
  assert.deepEqual(calls.map(([c]) => c), ["gh"], "恰一次 gh spawn");
  assert.match(calls[0].join(" "), /--label needs-triage/, "label 面经 gh argv");
  assert.match(calls[0].join(" "), /--repo steponeerror\/ip-radar/, "#348 repo 定向透传");
  const art = JSON.parse(fs.readFileSync(path.join(dir, ENQUEUE_ISSUES_ARTIFACT), "utf8"));
  assert.equal(art.phase, "emitted");
  assert.equal(art.issues_opened, 1);
  assert.ok(art.issues[0].title.includes("[source] rdns"), "全稿存活=证据不灭失");
  fs.rmSync(dir, { recursive: true, force: true });
});

test("三态②fail-soft:gh 非零退出 → failed 留痕不抛(轮不得被打成 fail);分类码透传", async () => {
  const dir = tmpDir();
  const exec = async () => { const e = new Error("gh 失败"); e.code = 1; e.stderr = "gh: Not Found (HTTP 404)"; throw e; };
  const r = await runEnqueueIssueExit({ roundId: ROUND, dir, rows: ROWS, shortlist: FX_SH, measure: FX_ME,
    modelFace: "real", env: { GH_TOKEN: "ghp_test" }, exec });
  assert.equal(r.status, "partial");
  assert.equal(r.issues_opened, 0);
  assert.equal(r.issues_failed, 1);
  assert.equal(r.issues[0].status, "failed");
  assert.equal(r.issues[0].code, "gh_error", "classifyChannelError 兜底码透传");
  assert.match(r.issues[0].reason, /Not Found/);
  const art = JSON.parse(fs.readFileSync(path.join(dir, ENQUEUE_ISSUES_ARTIFACT), "utf8"));
  assert.equal(art.phase, "emitted", "partial 也终记 emitted(留痕完整)");
  fs.rmSync(dir, { recursive: true, force: true });
});

test("三态③无 token:GH_TOKEN/GITHUB_TOKEN 双缺 → skip 留痕零 spawn(降级不炸轮)", async () => {
  const dir = tmpDir();
  let spawned = 0;
  const exec = async () => { spawned += 1; return { stdout: "" }; };
  const r = await runEnqueueIssueExit({ roundId: ROUND, dir, rows: ROWS, shortlist: FX_SH, measure: FX_ME,
    modelFace: "real", env: {}, exec });
  assert.equal(r.status, "skip");
  assert.match(r.reason, /no_token/);
  assert.equal(r.issues_opened, 0);
  assert.equal(spawned, 0, "无 token 不 spawn(本地/缺配置轮零外发)");
  const art = JSON.parse(fs.readFileSync(path.join(dir, ENQUEUE_ISSUES_ARTIFACT), "utf8"));
  assert.equal(art.phase, "skip");
  fs.rmSync(dir, { recursive: true, force: true });
});

test("faux 零外发:modelFace=faux 一律 skip 留痕(罐装轮零网络;token 在场也不 spawn)", async () => {
  const dir = tmpDir();
  let spawned = 0;
  const exec = async () => { spawned += 1; return { stdout: "" }; };
  const r = await runEnqueueIssueExit({ roundId: ROUND, dir, rows: ROWS, shortlist: FX_SH, measure: FX_ME,
    modelFace: "faux", env: { GH_TOKEN: "ghp_test" }, exec });
  assert.equal(r.status, "skip");
  assert.match(r.reason, /faux_zero_emit/);
  assert.equal(spawned, 0);
  fs.rmSync(dir, { recursive: true, force: true });
});

test("emit 守卫(resume 防重开):同轮工件已记 emitting/emitted → 不重开不重写,读数取已落工件", async () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, ENQUEUE_ISSUES_ARTIFACT), JSON.stringify({ round_id: ROUND, phase: "emitted",
    issues_opened: 1, issues_failed: 0, issues: [{ candidate: "rdns", status: "created", issue_url: "https://github.com/steponeerror/ip-radar/issues/1" }] }, null, 2) + "\n");
  let spawned = 0;
  const exec = async () => { spawned += 1; return { stdout: "" }; };
  const r = await runEnqueueIssueExit({ roundId: ROUND, dir, rows: ROWS, shortlist: FX_SH, measure: FX_ME,
    modelFace: "real", env: { GH_TOKEN: "ghp_test" }, exec });
  assert.equal(r.status, "skip");
  assert.match(r.reason, /emit_guard/);
  assert.equal(r.issues_opened, 1, "已开计数从工件回读(崩溃窗不丢计)");
  assert.equal(spawned, 0, "不重开(issue 重复开可人关,漏开可下轮补——宁少算)");
  const art = JSON.parse(fs.readFileSync(path.join(dir, ENQUEUE_ISSUES_ARTIFACT), "utf8"));
  assert.equal(art.issues[0].issue_url, "https://github.com/steponeerror/ip-radar/issues/1", "守卫不重写工件(全稿存活)");
  // 异轮工件不触发守卫(重放/异物面)
  const dir2 = tmpDir();
  fs.writeFileSync(path.join(dir2, ENQUEUE_ISSUES_ARTIFACT), JSON.stringify({ round_id: "2026-06-02-0400-discover", phase: "emitted", issues_opened: 9 }, null, 2) + "\n");
  const r2 = await runEnqueueIssueExit({ roundId: ROUND, dir: dir2, rows: [], shortlist: FX_SH, measure: FX_ME,
    modelFace: "real", env: {}, exec });
  assert.notEqual(r2.reason, undefined);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.rmSync(dir2, { recursive: true, force: true });
});

test("相位步集成:enqueueStageIssueExit 写 d4-enqueue.json(v1 同形:计数+门槛常量+三数组)+零 queue.md 写口", async () => {
  const tmp = tmpDir();
  const opsRoot = path.join(tmp, "docs", "ops");
  const dir = path.join(opsRoot, "rounds", ROUND);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, A.DISCOVER_SHORTLIST), JSON.stringify(FX_SH, null, 2) + "\n");
  fs.writeFileSync(path.join(dir, A.DISCOVER_MEASURE), JSON.stringify(FX_ME, null, 2) + "\n");
  const ctx = { dir, opsRoot, roundId: ROUND, env: {}, modelFace: "faux" };
  const r = await enqueueStageIssueExit(ctx);
  assert.equal(r.status, "skip", "faux 面(本集成测零网络)");
  const d4 = JSON.parse(fs.readFileSync(path.join(dir, A.DISCOVER_ENQUEUE), "utf8"));
  assert.equal(d4.round_id, ROUND);
  assert.equal(d4.gate_exclusivity, 0.25, "门槛常量在场(G_ENQUEUE 判据单源)");
  assert.deepEqual(d4.enqueued.map((x) => x.candidate), ["rdns"]);
  assert.equal(d4.n_enqueued, 1);
  assert.equal(d4.n_skipped, 1);
  assert.equal(d4.n_flagged, 0);
  assert.deepEqual(Object.keys(d4), ["round_id", "generated_at", "gate_exclusivity", "enqueued", "skipped", "flagged", "n_enqueued", "n_skipped", "n_flagged"], "d4 键序与 v1 ENQUEUE 写面逐字段同形");
  assert.ok(!fs.existsSync(path.join(opsRoot, "queue.md")), "#384:PROPOSE 停写,queue.md 不建");
  fs.rmSync(tmp, { recursive: true, force: true });
});
