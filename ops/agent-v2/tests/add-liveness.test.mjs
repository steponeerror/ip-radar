// add-liveness.test.mjs — #339 ①:probeLiveness github 家族活性证据回退(红绿面)。
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

test("probeLiveness github 家族回退:直接探活失败 → commits API 得证(basis=github_commit,age≤30 过门)", async () => {
  const f = stubFetch([{ match: (u) => u.startsWith(`${GH_API}?`), respond: () => res({ json: commitAt(2.5) }) }]);
  const live = await probeLiveness(RAW_URL, f.impl);
  assert.equal(live.basis, "github_commit");
  assert.equal(live.age_days, 2);
  assert.equal(live.last_modified, null);
  assert.equal(freshnessOf(live).ok, true, "家族活性证据面:commits API committer date ≤30d 须过鲜活度门");
  // 证据不灭失:直接探活 4 组合 + API 各留痕;证据面记录 api URL/status/取到的日期
  assert.equal(f.calls.length, 5);
  assert.deepEqual(f.calls.slice(0, 4).map((c) => c.method).sort(), ["GET", "GET", "HEAD", "HEAD"]);
  const api = new URL(f.calls[4].url);
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
    const live = await probeLiveness(RAW_URL, f.impl);
    assert.equal(live.basis, "none", face.label);
    assert.equal(live.age_days, undefined, face.label);
    assert.equal(freshnessOf(live).ok, false, face.label);
    face.trace(live.github_commit, face.label); // #339 评审 P1:失败面留痕也在档(api/status/日期或 error),与未尝试可分诊
  }
});

test("家族外不回退:非 github 家族 URL 直接探活失败 → 不触 api.github.com,none", async () => {
  const f = stubFetch([]);
  const live = await probeLiveness("https://example.com/feed.txt", f.impl);
  assert.equal(live.basis, "none");
  assert.equal(f.calls.length, 4, "只有直接探活 4 组合");
  assert.ok(f.calls.every((c) => !c.url.includes("api.github.com")), "家族外不得回退 commits API");
});

test("证据优先级 last_modified > github_commit:直接探活得证则不触 API", async () => {
  const f = stubFetch([
    { url: RAW_URL, respond: () => res({ lastModified: "Tue, 10 Nov 2026 00:00:00 GMT" }) },
    { match: (u) => u.startsWith(`${GH_API}?`), respond: () => { throw new Error("API 不应被触"); } },
  ]);
  const live = await probeLiveness(RAW_URL, f.impl);
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
