// bench-shortlist.test.mjs — 重发现基准票 B(票 #319;spec docs/research/
// 2026-11-07-rediscover-bench-spec.md §3.2)测试面:
//   ①bench 模式 span 门第四证据面(G_SHORTLIST:quote 逐字出自 d2-shortlist-transcript.jsonl
//     工具转录行——web 转录逐字命中过/幽灵 URL 拒/改写引文拒/非工具行拒);
//   ②真实模式零漂移(转录指针无 bench 旗标=透传形幽灵指针照拒;needs 三形在 bench 照活);
//   ③基准提示词形状(无回声防线措辞/10 类分类法指导/字段契约齐/三工具/转录指针形);
//   ④接线(bench 轮会话 instructions=shortlist-bench.md;transcript system_sha 哈希基准面)。
// span 门走公共门函数 GATES.G_SHORTLIST(ctx)(门=唯一转移裁判,测试不另起炉灶);
// 真实模式全链零漂移主门=golden-discover-parity/golden-smoke-gated,不在本文件。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { GATES } from "../../agent/pipeline/gates.mjs";
import { runBenchRound } from "../bench/run-bench.mjs";
import { shortlistBenchPromptPath } from "../run-discover.mjs";

const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
const ROUND = "2026-06-01-0500-discover";
const FIXTURES = path.resolve(import.meta.dirname, "..", "..", "agent", "fixtures", "pipeline");
// 转录指针形:call/<call_id>(模型可见面=工具返回 [call_id=…] 前缀;行号面模型不可数,弃)
const TRANSCRIPT_PTR = (id) => `d2-shortlist-transcript.jsonl:call/${id}`;

// 工具转录行(web_search 信封同形:sc.results[].url/title/snippet=可引证据字段)
const seedRow = JSON.stringify({
  type: "registry_seed", call_id: "call-1", tool: "web_search",
  sc: { ok: true, query: "ip blocklist feed", n: 1, truncated: false, provider: "duckduckgo",
    results: [{ url: "https://example.org/blocklist", title: "Example Org IP Blocklist", snippet: "Daily updated list of abusive hosts" }],
    trace: { cmd: "pi-web-access", rc: 0 } },
});
const transcriptLines = [
  JSON.stringify({ type: "input", stage: "SHORTLIST", system_sha: "0".repeat(16), user_sha: "1".repeat(16), meta: null }),
  seedRow,
  JSON.stringify({ type: "message", role: "assistant", content: [{ type: "text", text: "..." }], stopReason: "stop" }),
];

const scanArt = {
  round_id: ROUND,
  candidates: [{ name: "缺口A", url: null, evidence_ptr: "NEEDS.md:L14", source_channel: "needs", status: "open",
    text: "| 缺口A | 某情报缺口 | 备注 | open | 来源 |" }],
};

// 轮工件夹具(d1-scan + 转录;候选按用例注入)
function benchRoundDir(candidates) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-bench-span-"));
  const dir = path.join(tmp, "rounds", ROUND);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "d1-scan.json"), JSON.stringify(scanArt, null, 2) + "\n");
  fs.writeFileSync(path.join(dir, "d2-shortlist-transcript.jsonl"), transcriptLines.join("\n") + "\n");
  fs.writeFileSync(path.join(dir, "d2-shortlist.json"), JSON.stringify({ round_id: ROUND, candidates }, null, 2) + "\n");
  return { tmp, dir };
}

const webCandidate = (over = {}) => ({
  name: "Example Org IP Blocklist", url: "https://example.org/blocklist",
  quote: "Daily updated list of abusive hosts", evidence_ptr: TRANSCRIPT_PTR("call-1"),
  source_channel: "web_search", exclusivity_estimate: null, notes: "bench 第四证据面单测夹具",
  ...over,
});

test("bench span 门第四证据面:web 转录逐字命中过(snippet+URL 双形态)", () => {
  const { tmp, dir } = benchRoundDir([
    webCandidate(), // snippet 文本逐字
    webCandidate({ name: "Example Org(blocklist 直链)", quote: "https://example.org/blocklist" }), // URL token 定界在场
  ]);
  try {
    const r = GATES.G_SHORTLIST({ dir, bench: true });
    assert.equal(r.pass, true, r.reason);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("bench span 门:幽灵 URL 拒(quote 引转录行外 URL=非逐字 span)", () => {
  const { tmp, dir } = benchRoundDir([webCandidate({ quote: "Daily updated list of abusive hosts https://example.org/ghost-entry" })]);
  try {
    const r = GATES.G_SHORTLIST({ dir, bench: true });
    assert.equal(r.pass, false);
    assert.match(r.reason, /逐字 span/);
    assert.match(r.reason, /Example Org IP Blocklist/); // reason 带候选名(可回算)
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("bench span 门:改写引文拒(大小写改写=非逐字)", () => {
  const { tmp, dir } = benchRoundDir([webCandidate({ quote: "Daily Updated List of Abusive Hosts" })]);
  try {
    const r = GATES.G_SHORTLIST({ dir, bench: true });
    assert.equal(r.pass, false);
    assert.match(r.reason, /逐字 span/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("bench span 门:未知 call_id 拒(转录无此工具行)", () => {
  const { tmp, dir } = benchRoundDir([webCandidate({ evidence_ptr: TRANSCRIPT_PTR("call-999") })]);
  try {
    const r = GATES.G_SHORTLIST({ dir, bench: true });
    assert.equal(r.pass, false);
    assert.match(r.reason, /无对应工具转录行/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("bench span 门:非 call 形转录指针回落三形=幽灵指针拒(形律闭)", () => {
  const { tmp, dir } = benchRoundDir([webCandidate({ evidence_ptr: "d2-shortlist-transcript.jsonl:L2" })]); // 行号形非本面指针形
  try {
    const r = GATES.G_SHORTLIST({ dir, bench: true });
    assert.equal(r.pass, false);
    assert.match(r.reason, /幽灵指针/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("真实模式零漂移:转录指针无 bench 旗标照拒(第四面不开;拒绝面=旧三形解析原样路径)", () => {
  const { tmp, dir } = benchRoundDir([webCandidate()]);
  try {
    const r = GATES.G_SHORTLIST({ dir }); // 无 bench 旗标=真实模式:转录指针走旧三形解析
    assert.equal(r.pass, false);
    assert.match(r.reason, /三形外|幽灵指针/); // call 形含冒号=非透传形→三形外(旧路径原样拒绝)
    assert.match(r.reason, /在 d1-scan 候选宇宙不可解析/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("bench 轮 needs 三形照活:NEEDS.md 行锚+text 原文逐字回引过门", () => {
  const { tmp, dir } = benchRoundDir([{
    name: "缺口A", url: null, quote: "某情报缺口", evidence_ptr: "NEEDS.md:L14",
    source_channel: "needs", exclusivity_estimate: null, notes: "考题另一半:靠 NEEDS 提示找到",
  }]);
  try {
    const r = GATES.G_SHORTLIST({ dir, bench: true });
    assert.equal(r.pass, true, r.reason);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

// ── 基准提示词形状(票面:无回声防线措辞、含分类法、字段契约齐)──
test("shortlist-bench.md 形状:搜索+筛选职责/无回声防线/10 类分类法/字段契约/三工具/转录指针", () => {
  const p = fs.readFileSync(shortlistBenchPromptPath(), "utf8");
  assert.ok(p.includes("搜索"), "职责=搜索+筛选(搜索面)");
  assert.ok(p.includes("筛选"), "职责=搜索+筛选(筛选面)");
  for (const banned of ["回声防线", "已接源", "同源重复不是印证"])
    assert.ok(!p.includes(banned), `基准提示词不得含回声防线措辞:${banned}`);
  for (const cat of ["网络定位", "路由与分配", "所有权与联系", "基础设施角色", "隐私与中继", "移动与接入", "通信暴露面", "声誉与恶意", "时间动态", "组织与商业"])
    assert.ok(p.includes(cat), `10 类 IP 信息分类法缺:${cat}`);
  for (const f of ["name", "url", "quote", "evidence_ptr", "source_channel", "exclusivity_estimate", "notes"])
    assert.ok(p.includes(f), `输出契约字段缺:${f}`);
  for (const t of ["web_search", "web_read", "rss_parse"])
    assert.ok(p.includes(t), `三只只读工具指引缺:${t}`);
  assert.ok(p.includes("d2-shortlist-transcript.jsonl:call/"), "转录指针形(evidence_ptr 第四面)未写明");
});

// ── 接线:bench 轮 SHORTLIST 相位用基准提示词(会话 instructions+transcript system_sha 同面)──
test("run-bench 接线:会话 instructions=shortlist-bench.md(transcript system_sha 哈希基准面)", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-bench-wire-"));
  const benchRoot = path.join(tmp, "bench-rediscover");
  try {
    const r = await runBenchRound({
      roundId: ROUND, fixturesDir: FIXTURES, benchRoot,
      dbPath: path.join(tmp, "bench.sqlite"),
      env: { ...process.env, DOCS_ROOT: path.join(tmp, "docs") }, // 真实树替身:bench 后必须零触碰
      stderr: { write: () => true },
    });
    assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
    const dir = path.join(benchRoot, ROUND, "rounds", ROUND);
    const head = fs.readFileSync(path.join(dir, "d2-shortlist-transcript.jsonl"), "utf8")
      .split("\n").filter(Boolean).map((l) => JSON.parse(l)).find((l) => l.type === "input");
    assert.equal(head.system_sha, sha(fs.readFileSync(shortlistBenchPromptPath(), "utf8")),
      "transcript system_sha 须=基准提示词(bench 轮 SHORTLIST 相位换面;哈希真实提示词=接线漂移)");
    // 启动器单源钉:instructions 取数面=shortlistBenchPromptPath(防回退真实提示词)
    const launcher = fs.readFileSync(path.resolve(import.meta.dirname, "..", "bench", "run-bench.mjs"), "utf8");
    assert.ok(launcher.includes("shortlistBenchPromptPath"), "run-bench.mjs 会话 instructions 未走 shortlistBenchPromptPath");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
