// add-liveness.test.mjs — #339 ①:probeLiveness github 家族活性证据回退(红绿面);
// #341 ②:同 host 高频 4 组合疑似限流(feeds.dshield.org 实测 last-modified 缺席→fail-closed
// 误红)——组合间短退避 + 失败组合一次重试(opts 参数面可测:sleepImpl/comboDelayMs/
// retryDelayMs 注入零真实等待)。
// 背景(P3 前置阻断件):真实 trial VERIFY 鲜活度门 freshness.ok≠true 即红(G_VERIFY);
// 本机 raw.githubusercontent.com TCP 被墙,宇宙 12 题端点在 raw.*——直接探活(4 组合
// GET/HEAD×UA)拿不到 last-modified 时,github 家族 URL 回退 api.github.com commits API
// (发布方活性证据=最新 commit committer date,主会话裁定;api.github.com 本机可达,
// stamparm/ipsum 2026-11-11 实测)。测试面零网络:probeLiveness(url, fetchImpl) 注入
// stub(genExamCards fetchImpl 同缝);双面=回退得证绿/无 commit 红+家族外不回退。
import test from "node:test";
import assert from "node:assert/strict";
import { runAddRound as _runAddCycleGuard } from "../run-add.mjs"; // 先入 run-add 再入 add-round(循环 import 求值序:add-round 直接先入会在 TDZ 上炸,add-round.test.mjs 同序)
import { probeLiveness, githubCommitsQuery, freshnessOf } from "../tasks/add-round.mjs";

const RAW_URL = "https://raw.githubusercontent.com/stamparm/ipsum/master/ipsum.txt";
const GH_API = "https://api.github.com/repos/stamparm/ipsum/commits";

// Response 形 stub(直接探活面只读 status/headers;API 面另读 json)
const res = (over = {}) => ({
  status: over.status ?? 200,
  headers: { get: (k) => (String(k).toLowerCase() === "last-modified" ? over.lastModified ?? null : null) },
  ...(over.json !== undefined ? { json: async () => over.json } : {}),
});

// fetch stub:无路由=连接失败(本机 raw.* 被墙即此态);calls 记录全请求面
function stubFetch(routes) {
  const calls = [];
  const impl = async (url, opts = {}) => {
    const u = String(url);
    calls.push({ url: u, method: opts.method ?? "GET" });
    const hit = routes.find((r) => (r.match ? r.match(u) : r.url === u));
    if (!hit) throw new TypeError(`fetch failed: ${u}`);
    return typeof hit.respond === "function" ? hit.respond(u, opts) : hit.respond;
  };
  return { impl, calls };
}
const commitAt = (daysAgo) => [{ commit: { committer: { date: new Date(Date.now() - daysAgo * 86_400_000).toISOString() } } }];

// #341 ② 退避/重试参数注入面:sleepImpl 记录延迟零真实等待;既有测试同步注入(不注入则真实 setTimeout 退避会拖慢测试面)
const sleepRecorder = () => { const slept = []; return { slept, sleepImpl: async (ms) => { slept.push(ms); } }; };
const nosleep = { sleepImpl: async () => {} };

test("probeLiveness github 家族回退:直接探活失败 → commits API 得证(basis=github_commit,age≤30 过门)", async () => {
  const f = stubFetch([{ match: (u) => u.startsWith(`${GH_API}?`), respond: () => res({ json: commitAt(2.5) }) }]);
  const live = await probeLiveness(RAW_URL, f.impl, nosleep);
  assert.equal(live.basis, "github_commit");
  assert.equal(live.age_days, 2);
  assert.equal(live.last_modified, null);
  assert.equal(freshnessOf(live).ok, true, "家族活性证据面:commits API committer date ≤30d 须过鲜活度门");
  // 证据不灭失:直接探活 4 组合(失败面各重试一次)+ API 各留痕;证据面记录 api URL/status/取到的日期
  assert.equal(f.calls.length, 9, "4 组合首轮 + 4 组合各一次重试(全连接失败面)+ commits API 1");
  assert.deepEqual(f.calls.slice(0, 8).map((c) => c.method).sort(), ["GET", "GET", "GET", "GET", "HEAD", "HEAD", "HEAD", "HEAD"], "首轮 4 + 重试 4 同方法面");
  const api = new URL(f.calls[8].url);
  assert.equal(api.pathname, "/repos/stamparm/ipsum/commits");
  assert.equal(api.searchParams.get("path"), "ipsum.txt", "path=剥 ref 后的文件路径");
  assert.equal(api.searchParams.get("per_page"), "1");
  assert.equal(live.github_commit.status, 200);
  assert.equal(typeof live.github_commit.committer_date, "string");
});

test("回退红面:API 无 commit(空数组/非 200)/连接失败 = fail-closed none(无证据即无话)", async () => {
  for (const face of [
    { label: "空 commits(路径不在仓)", respond: () => res({ json: [] }), trace: (g, lbl) => { assert.equal(g.status, 200, lbl + " 留痕"); assert.equal(g.committer_date, null, lbl + " 留痕"); } },
    { label: "非 200(限流 403)", respond: () => res({ status: 403, json: { message: "rate limit" } }), trace: (g, lbl) => { assert.equal(g.status, 403, lbl + " 留痕"); } },
    { label: "API 连接失败", respond: undefined, trace: (g, lbl) => { assert.ok(g.error, lbl + " 留痕 error"); } },
  ]) {
    const f = stubFetch(face.respond ? [{ match: (u) => u.startsWith(`${GH_API}?`), respond: face.respond }] : []);
    const live = await probeLiveness(RAW_URL, f.impl, nosleep);
    assert.equal(live.basis, "none", face.label);
    assert.equal(live.age_days, undefined, face.label);
    assert.equal(freshnessOf(live).ok, false, face.label);
    face.trace(live.github_commit, face.label); // #339 评审 P1:失败面留痕也在档(api/status/日期或 error),与未尝试可分诊
  }
});

test("家族外不回退:非 github 家族 URL 直接探活失败 → 不触 api.github.com,none", async () => {
  const f = stubFetch([]);
  const live = await probeLiveness("https://example.com/feed.txt", f.impl, nosleep);
  assert.equal(live.basis, "none");
  assert.equal(f.calls.length, 8, "只有直接探活 4 组合 + 各一次重试(全连接失败面)");
  assert.ok(f.calls.every((c) => !c.url.includes("api.github.com")), "家族外不得回退 commits API");
});

test("证据优先级 last_modified > github_commit:直接探活得证则不触 API", async () => {
  const f = stubFetch([
    { url: RAW_URL, respond: () => res({ lastModified: "Tue, 10 Nov 2026 00:00:00 GMT" }) },
    { match: (u) => u.startsWith(`${GH_API}?`), respond: () => { throw new Error("API 不应被触"); } },
  ]);
  const live = await probeLiveness(RAW_URL, f.impl, nosleep);
  assert.equal(live.basis, "last_modified");
  assert.ok(f.calls.every((c) => !c.url.includes("api.github.com")), "last_modified 在场=最高优先,回退零调用");
});

test("githubCommitsQuery:家族三形剥 ref 段取文件路径;家族外/缺 owner-repo = null", () => {
  const q = (u) => { const r = githubCommitsQuery(u); return r ? { path: r.path, apiPath: new URL(r.api).pathname } : null; };
  assert.deepEqual(q("https://raw.githubusercontent.com/o/r/main/a/b.txt"), { path: "a/b.txt", apiPath: "/repos/o/r/commits" }, "raw 形:<owner>/<repo>/<ref>/<路径…>");
  assert.deepEqual(q("https://github.com/o/r/blob/main/a/b.txt"), { path: "a/b.txt", apiPath: "/repos/o/r/commits" }, "blob 形:剥 blob/<ref>");
  assert.deepEqual(q("https://github.com/o/r/raw/main/a/b.txt"), { path: "a/b.txt", apiPath: "/repos/o/r/commits" }, "raw 形(github.com)");
  assert.deepEqual(q("https://www.github.com/o2/r2"), { path: "", apiPath: "/repos/o2/r2/commits" }, "www 前缀剥除;仓根=无文件路径(repo 级最新 commit)");
  assert.deepEqual(q("https://codeload.github.com/o/r/zip/main"), { path: "", apiPath: "/repos/o/r/commits" }, "codeload 归档形:无文件粒度");
  assert.equal(q("https://example.com/a/b"), null, "家族外");
  assert.equal(q("https://github.com/onlyowner"), null, "缺 owner/repo 对=fail-closed 不回退");
  assert.equal(q("not a url"), null, "非 URL 形");
});

// ── #341 ② 退避与重试(参数面:opts.sleepImpl/comboDelayMs/retryDelayMs)──

test("退避节奏:组合间短退避(首组合零等待,后续 3 间隙×comboDelayMs);全绿面零重试零额外退避", async () => {
  const rec = sleepRecorder();
  const f = stubFetch([{ url: "https://example.com/feed.txt", respond: () => res({ lastModified: "Tue, 10 Nov 2026 00:00:00 GMT" }) }]);
  const live = await probeLiveness("https://example.com/feed.txt", f.impl, { ...rec, comboDelayMs: 5 });
  assert.equal(f.calls.length, 4, "全绿零重试");
  assert.deepEqual(rec.slept, [5, 5, 5], "4 组合 = 3 个组合间间隙;重试面零触发(无 retryDelayMs 记录)");
  assert.equal(live.basis, "last_modified");
  assert.ok(live.combos.every((c) => !c.retried), "全绿组合不得带 retried 面");
});

test("失败组合一次重试:首轮传输错 → 重试得 last-modified → 终面留痕(retried+first_error),basis=last_modified", async () => {
  let fails = true;
  const f = stubFetch([{
    url: "https://example.com/feed.txt",
    respond: () => {
      if (fails) { fails = false; throw new TypeError("fetch failed"); }
      return res({ lastModified: "Tue, 10 Nov 2026 00:00:00 GMT" });
    },
  }]);
  const rec = sleepRecorder();
  const live = await probeLiveness("https://example.com/feed.txt", f.impl, { ...rec, comboDelayMs: 1, retryDelayMs: 9 });
  assert.equal(live.basis, "last_modified", "重试得证=鲜活度证据修复(误红主修复面)");
  assert.equal(f.calls.length, 5, "首轮 4 + 失败组合重试 1");
  const retried = live.combos.filter((c) => c.retried);
  assert.equal(retried.length, 1);
  assert.equal(retried[0].status, 200);
  assert.equal(retried[0].last_modified, "Tue, 10 Nov 2026 00:00:00 GMT");
  assert.match(retried[0].first_error, /fetch failed/, "首轮失败面留痕不灭失");
  assert.ok(rec.slept.includes(9), "重试前有 retryDelayMs 缓隔");
});

test("限流签名(429/503)也重试;200-无 header 是稳定答案不重试(防对无 header 源双倍打)", async () => {
  let throttledOnce = true;
  const f = stubFetch([{
    url: "https://example.com/feed.txt",
    respond: (_u, opts) => {
      // 只让首个组合吃到一次 429(限流签名),其余全部 200-无 header(真实无 header 源常态)
      if (throttledOnce) { throttledOnce = false; return res({ status: opts.method === "HEAD" ? 200 : 429 }); }
      return res({});
    },
  }]);
  const rec = sleepRecorder();
  const live = await probeLiveness("https://example.com/feed.txt", f.impl, { ...rec, comboDelayMs: 1, retryDelayMs: 2 });
  assert.equal(f.calls.length, 5, "只有吃到 429 的组合被重试一次;200-无 header 组合零重试");
  assert.equal(live.combos.filter((c) => c.retried).length, 1);
  const c429 = live.combos.find((c) => c.first_error?.includes("429"));
  assert.ok(c429, "429 首轮面以 first_error=HTTP 429 留痕");
  assert.ok(live.combos.filter((c) => !c.retried).every((c) => c.first_error === undefined), "未重试组合不得带失败面");
  assert.equal(live.basis, "none", "重试后仍无 header + 非家族 = fail-closed none(无证据即无话)");
});

test("重试仍失败:终面留 retried+first_error,证据面不灭失;非家族无回退 = none", async () => {
  const f = stubFetch([]); // 全路由缺席 = 连接失败
  const rec = sleepRecorder();
  const live = await probeLiveness("https://example.com/feed.txt", f.impl, { ...rec, comboDelayMs: 1, retryDelayMs: 3 });
  assert.equal(f.calls.length, 8, "4 首轮 + 4 重试(仅一次,不得无限)");
  assert.ok(live.combos.every((c) => c.retried && c.first_error && c.error), "每组合留 retried+首轮痕+终面错");
  assert.equal(live.basis, "none");
  assert.equal(rec.slept.filter((ms) => ms === 3).length, 4, "每次重试前各一次 retryDelayMs 缓隔");
});
