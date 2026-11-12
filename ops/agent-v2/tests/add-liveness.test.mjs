// add-liveness.test.mjs — #339 ①:probeLiveness github 家族活性证据回退(红绿面);
// #341 ②:同 host 高频 4 组合疑似限流(feeds.dshield.org 实测 last-modified 缺席→fail-closed
// 误红)——组合间短退避 + 失败组合一次重试(opts 参数面可测:sleepImpl/comboDelayMs/
// retryDelayMs 注入零真实等待);
// #340:github commits API 限流记忆化(api.github.com 匿名配额 60 req/h/按 IP,优化环
// 几十上百次 trial 必撞 403)——进程内 Map + 跨进程文件缓存两层(命中=cache:hit 零网络,
// age 用取得时刻算)+ Conditional GET(If-None-Match,304 不占配额视为新鲜)+ 坏缓存
// 弃用重探不红轮;注入面 githubCacheMem/githubCacheFile/githubCacheTtlMs(同风格缝)。
// 背景(P3 前置阻断件):真实 trial VERIFY 鲜活度门 freshness.ok≠true 即红(G_VERIFY);
// 本机 raw.githubusercontent.com TCP 被墙,宇宙 12 题端点在 raw.*——直接探活(4 组合
// GET/HEAD×UA)拿不到 last-modified 时,github 家族 URL 回退 api.github.com commits API
// (发布方活性证据=最新 commit committer date,主会话裁定;api.github.com 本机可达,
// stamparm/ipsum 2026-11-11 实测)。测试面零网络:probeLiveness(url, fetchImpl) 注入
// stub(genExamCards fetchImpl 同缝);双面=回退得证绿/无 commit 红+家族外不回退。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { runAddRound as _runAddCycleGuard } from "../run-add.mjs"; // 先入 run-add 再入 add-round(循环 import 求值序:add-round 直接先入会在 TDZ 上炸,add-round.test.mjs 同序)
import { probeLiveness, githubCommitsQuery, freshnessOf } from "../tasks/add-round.mjs";

const RAW_URL = "https://raw.githubusercontent.com/stamparm/ipsum/master/ipsum.txt";
const GH_API = "https://api.github.com/repos/stamparm/ipsum/commits";

// Response 形 stub(直接探活面只读 status/headers;API 面另读 json;#340 再读 etag;
// #342 A2 再读 content-disposition)
const res = (over = {}) => ({
  status: over.status ?? 200,
  headers: { get: (k) => {
    const kk = String(k).toLowerCase();
    if (kk === "last-modified") return over.lastModified ?? null;
    if (kk === "etag") return over.etag ?? null; // #340:Conditional GET 的 etag 面
    if (kk === "content-disposition") return over.contentDisposition ?? null; // #342 A2:第三基证据面(响应头)
    return null;
  } },
  ...(over.json !== undefined ? { json: async () => over.json } : {}),
});

// fetch stub:无路由=连接失败(本机 raw.* 被墙即此态);calls 记录全请求面(含 headers,#340 If-None-Match 断言)
function stubFetch(routes) {
  const calls = [];
  const impl = async (url, opts = {}) => {
    const u = String(url);
    calls.push({ url: u, method: opts.method ?? "GET", headers: opts.headers ?? {} });
    const hit = routes.find((r) => (r.match ? r.match(u) : r.url === u));
    if (!hit) throw new TypeError(`fetch failed: ${u}`);
    return typeof hit.respond === "function" ? hit.respond(u, opts) : hit.respond;
  };
  return { impl, calls };
}
const commitAt = (daysAgo) => [{ commit: { committer: { date: new Date(Date.now() - daysAgo * 86_400_000).toISOString() } } }];

// #341 ② 退避/重试参数注入面:sleepImpl 记录延迟零真实等待;既有测试同步注入(不注入则真实 setTimeout 退避会拖慢测试面)
const sleepRecorder = () => { const slept = []; return { slept, sleepImpl: async (ms) => { slept.push(ms); } }; };
// #340 隔离面:每测新开进程内缓存 Map + 关文件层(缺省缝指向真实主检出 dev/add-bench,测试零真实读写)
const iso = () => ({ sleepImpl: async () => {}, githubCacheMem: new Map(), githubCacheFile: null });

test("probeLiveness github 家族回退:直接探活失败 → commits API 得证(basis=github_commit,age≤30 过门)", async () => {
  const f = stubFetch([{ match: (u) => u.startsWith(`${GH_API}?`), respond: () => res({ json: commitAt(2.5) }) }]);
  const live = await probeLiveness(RAW_URL, f.impl, iso());
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
    const live = await probeLiveness(RAW_URL, f.impl, iso());
    assert.equal(live.basis, "none", face.label);
    assert.equal(live.age_days, undefined, face.label);
    assert.equal(freshnessOf(live).ok, false, face.label);
    face.trace(live.github_commit, face.label); // #339 评审 P1:失败面留痕也在档(api/status/日期或 error),与未尝试可分诊
  }
});

test("家族外不回退:非 github 家族 URL 直接探活失败 → 不触 api.github.com,none", async () => {
  const f = stubFetch([]);
  const live = await probeLiveness("https://example.com/feed.txt", f.impl, iso());
  assert.equal(live.basis, "none");
  assert.equal(f.calls.length, 8, "只有直接探活 4 组合 + 各一次重试(全连接失败面)");
  assert.ok(f.calls.every((c) => !c.url.includes("api.github.com")), "家族外不得回退 commits API");
});

test("证据优先级 last_modified > github_commit:直接探活得证则不触 API", async () => {
  const f = stubFetch([
    { url: RAW_URL, respond: () => res({ lastModified: "Tue, 10 Nov 2026 00:00:00 GMT" }) },
    { match: (u) => u.startsWith(`${GH_API}?`), respond: () => { throw new Error("API 不应被触"); } },
  ]);
  const live = await probeLiveness(RAW_URL, f.impl, iso());
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

test("githubCommitsQuery releases 两形(#342 B):latest/download 与 download/<tag> 都剥段取文件名进 path", () => {
  const q = (u) => { const r = githubCommitsQuery(u); return r ? { path: r.path, query: new URL(r.api).searchParams.get("path") } : null; };
  assert.deepEqual(q("https://github.com/o/r/releases/latest/download/anycast_census.csv.gz"),
    { path: "anycast_census.csv.gz", query: "anycast_census.csv.gz" }, "latest 形:剥 releases/latest/download 三段,文件名=path");
  assert.deepEqual(q("https://github.com/o/r/releases/download/v1.2/anycast_census.csv.gz"),
    { path: "anycast_census.csv.gz", query: "anycast_census.csv.gz" }, "tag 形:剥 releases/download/<tag> 三段,文件名=path");
  // 非 releases 形不受扰(既有三形回归面同测钉住):
  assert.deepEqual(q("https://github.com/o/r/blob/main/a/b.txt"), { path: "a/b.txt", query: "a/b.txt" }, "blob 形不受扰");
  assert.deepEqual(q("https://github.com/o/r/releases/download/"), { path: "", query: null }, "无文件段=repo 级最新 commit(仓根同律)");
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
  assert.equal(retried[0].error, undefined, "重试成功后陈旧 error 键清除(#341 评审 P2-2:不得 error+200 并存)");
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

// ── #340 github commits API 限流记忆化(进程内+文件两层 + Conditional GET)──
// api.github.com 匿名配额 60 req/h/按 IP(#340):优化环几十上百次 trial,12 题/轮
// VERIFY 必发回退调用,确定撞 403→fail-closed→G_VERIFY 系统性红。修件=两层记忆化
// + Conditional GET;注入面 githubCacheMem/githubCacheFile/githubCacheTtlMs(opts 同风格缝,
// undefined=走缺省:模块 Map + 主检出 dev/add-bench/github-freshness-cache.json + 6h)。

// 文件一层测试面:tmp 缓存文件(缺省缝指向真实主检出 dev/add-bench——测试零真实读写)
const tmpCacheFile = () => path.join(fs.mkdtempSync(path.join(os.tmpdir(), "gh-fresh-")), "github-freshness-cache.json");
const GH_KEY = () => githubCommitsQuery(RAW_URL).api; // 缓存键=commits API URL(owner/repo+path 的确定性函数)
const apiRoute = (respond) => ({ match: (u) => u.startsWith(`${GH_API}?`), respond });
const dayMs = 86_400_000;

test("#340 进程内一层:同 owner/repo+path 二次探活零 API 调用(命中回放 cache=hit,cached_at 在档;status=null 与失败面可分诊)", async () => {
  const mem = new Map();
  const f1 = stubFetch([apiRoute(() => res({ json: commitAt(2.5), etag: '"v1"' }))]);
  const live1 = await probeLiveness(RAW_URL, f1.impl, { ...iso(), githubCacheMem: mem });
  assert.equal(live1.basis, "github_commit");
  assert.equal(live1.github_commit.cache, "miss", "首探=触网面 miss");
  const f2 = stubFetch([]); // API 路由缺席:一旦触网即连接失败(命中则零触网)
  const live2 = await probeLiveness(RAW_URL, f2.impl, { ...iso(), githubCacheMem: mem });
  assert.equal(live2.basis, "github_commit", "进程内命中:配额零消耗");
  assert.equal(f2.calls.filter((c) => c.url.includes("api.github.com")).length, 0, "零 commits API 调用");
  assert.equal(live2.github_commit.cache, "hit");
  assert.equal(live2.github_commit.status, null, "命中面零 HTTP——status null 与 403/连接失败可分诊(#339 ③ 留痕律)");
  assert.equal(live2.github_commit.committer_date, live1.github_commit.committer_date, "回放记忆化答案");
  assert.equal(typeof live2.github_commit.cached_at, "string", "取得时刻在档(证据不灭失)");
  assert.equal(live2.age_days, live1.age_days, "age 用取得时刻算:命中=记忆化答案原样回放");
});

test("#340 命中面 age 用取得时刻算:回放记忆化答案(cached_at 口径),不按 now 重算", async () => {
  // 手种条目:commit 3d 前、取得时刻(cached_at)2d 前、TTL 放宽 7d → 命中;
  // age=cached_at−committer_date=1d(now 口径会算 3d——钉死取得时刻语义;TTL=两口径误差上界)
  const file = tmpCacheFile();
  fs.writeFileSync(file, JSON.stringify({ version: 1, entries: { [GH_KEY()]: {
    etag: null,
    committer_date: new Date(Date.now() - 3 * dayMs).toISOString(),
    cached_at: new Date(Date.now() - 2 * dayMs).toISOString(),
  } } }));
  const f = stubFetch([]); // 触网即失败——只有命中才可能得证
  const live = await probeLiveness(RAW_URL, f.impl, { ...iso(), githubCacheFile: file, githubCacheTtlMs: 7 * dayMs });
  assert.equal(live.basis, "github_commit");
  assert.equal(live.age_days, 1, "age=cached_at−committer_date(取得时刻算);now 口径=3 会把缓存证据凭空算陈");
  assert.equal(live.github_commit.cache, "hit");
});

test("#340 文件一层(跨进程):另一进程(新 Map)读同一文件命中零 API;条目 etag+committer_date+cached_at 落盘", async () => {
  const file = tmpCacheFile();
  const f1 = stubFetch([apiRoute(() => res({ json: commitAt(1.5), etag: '"etag-1"' }))]);
  const live1 = await probeLiveness(RAW_URL, f1.impl, { ...iso(), githubCacheFile: file });
  assert.equal(live1.github_commit.cache, "miss");
  const disk = JSON.parse(fs.readFileSync(file, "utf8"));
  const e = disk.entries[GH_KEY()];
  assert.ok(e, "条目按 commits API URL 键(owner/repo+path 确定性函数)落盘");
  assert.equal(e.etag, '"etag-1"');
  assert.equal(e.committer_date, live1.github_commit.committer_date);
  assert.equal(e.cached_at, live1.github_commit.cached_at, "取得时刻与证据同档落盘");
  // 跨进程面=新 Map + 触网即失败的 fetch:只能靠文件层命中
  const f2 = stubFetch([]);
  const live2 = await probeLiveness(RAW_URL, f2.impl, { ...iso(), githubCacheFile: file });
  assert.equal(live2.basis, "github_commit");
  assert.equal(live2.github_commit.cache, "hit");
  assert.equal(live2.age_days, 1);
});

test("#340 TTL 过期:过期条目不回放 → 重探得新证据;条目覆盖+cached_at 刷新", async () => {
  const file = tmpCacheFile();
  await probeLiveness(RAW_URL, stubFetch([apiRoute(() => res({ json: commitAt(10), etag: '"e0"' }))]).impl, { ...iso(), githubCacheFile: file });
  const disk = JSON.parse(fs.readFileSync(file, "utf8"));
  disk.entries[GH_KEY()].cached_at = new Date(Date.now() - 7 * 3600_000).toISOString(); // 拨回 7h 前(> 缺省 6h TTL)
  fs.writeFileSync(file, JSON.stringify(disk));
  const f2 = stubFetch([apiRoute(() => res({ json: commitAt(3), etag: '"e1"' }))]);
  const live = await probeLiveness(RAW_URL, f2.impl, { ...iso(), githubCacheFile: file });
  assert.equal(live.github_commit.cache, "miss", "过期条目不得回放");
  assert.equal(live.age_days, 3, "新答案得证");
  const disk2 = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.equal(disk2.entries[GH_KEY()].etag, '"e1"', "条目覆盖");
  assert.ok(Date.now() - Date.parse(disk2.entries[GH_KEY()].cached_at) < 60_000, "cached_at 刷新为本次取得时刻");
});

test("#340 Conditional GET:过期条目带 etag → If-None-Match;304=新鲜证据不占配额(committer_date 沿缓存,cached_at 更新)", async () => {
  const file = tmpCacheFile();
  fs.writeFileSync(file, JSON.stringify({ version: 1, entries: { [GH_KEY()]: {
    etag: '"e0"',
    committer_date: new Date(Date.now() - 5 * dayMs).toISOString(),
    cached_at: new Date(Date.now() - 7 * 3600_000).toISOString(), // 过期(>6h)但 etag 在场
  } } }));
  let seenHeaders = null;
  const f = stubFetch([apiRoute((_u, opts) => { seenHeaders = opts.headers ?? {}; return res({ status: 304, etag: '"e0"' }); })]);
  const live = await probeLiveness(RAW_URL, f.impl, { ...iso(), githubCacheFile: file });
  assert.equal(seenHeaders?.["if-none-match"], '"e0"', "过期重探须带 If-None-Match(304 不占配额的前提)");
  assert.equal(live.basis, "github_commit", "304 无 body 照常出 github_commit 证据(日期沿缓存)");
  assert.equal(live.github_commit.cache, "revalidated");
  assert.equal(live.github_commit.status, 304);
  assert.equal(live.age_days, 5, "再验证=新鲜:age 按新取得时刻算");
  const disk = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.ok(Date.now() - Date.parse(disk.entries[GH_KEY()].cached_at) < 60_000, "304 更新 cached_at(视为新鲜)");
});

test("#340 坏文件缓存=弃=未命中重探(不红不阻跑):弃用留痕 cache_note;写回自愈", async () => {
  for (const face of [
    { label: "非 JSON", text: "{ not json" },
    { label: "entries 非对象", text: JSON.stringify({ entries: [] }) },
  ]) {
    const file = tmpCacheFile();
    fs.writeFileSync(file, face.text);
    const f = stubFetch([apiRoute(() => res({ json: commitAt(4), etag: '"ok"' }))]);
    const live = await probeLiveness(RAW_URL, f.impl, { ...iso(), githubCacheFile: file });
    assert.equal(live.basis, "github_commit", `${face.label}:坏缓存不得红轮`);
    assert.equal(live.github_commit.cache_note, "cache_file_corrupt", `${face.label}:弃缓存留痕可分诊`);
    const disk = JSON.parse(fs.readFileSync(file, "utf8")); // 写回=自愈
    assert.equal(disk.entries[GH_KEY()].etag, '"ok"', `${face.label}:下进程见好缓存`);
  }
});

test("#340 失败面分诊与不落缓存:403 触网败 cache=miss(与 hit/未尝试三分);探败不写缓存条目", async () => {
  const file = tmpCacheFile();
  const f = stubFetch([apiRoute(() => res({ status: 403, json: { message: "rate limit" } }))]);
  const live = await probeLiveness(RAW_URL, f.impl, { ...iso(), githubCacheFile: file });
  assert.equal(live.basis, "none");
  assert.equal(live.github_commit.cache, "miss", "触网面=miss;hit=缓存命中;github_commit=null=未尝试——三面可分诊(#339 ③)");
  assert.equal(fs.existsSync(file), false, "失败不落缓存(fail-closed 答案不记忆化)");
});

test("#340 缺省缓存面:主检出锚 git-common-dir 下 dev/add-bench/github-freshness-cache.json(worktree 完删树不灭缓存)", async () => {
  const mod = await import("../tasks/add-round.mjs"); // 动态 import:实现未落时本测独红不连坐全文件
  assert.equal(typeof mod.githubFreshnessCacheDefaultPath, "function", "导出=测试单源面");
  const p = mod.githubFreshnessCacheDefaultPath();
  assert.ok(p.endsWith(path.join("dev", "add-bench", "github-freshness-cache.json")), "票面钉死路径");
  const { mainCheckoutRoot, ROOT } = await import("../bench/leak-check.mjs");
  assert.equal(path.dirname(path.dirname(path.dirname(p))), mainCheckoutRoot(ROOT) ?? ROOT, "锚主检出(spend.json #337 同算式;主检出自身=退化同根)");
});

// ── #342 A2:第三证据基 embedded_date(响应头 content-disposition 文件名内嵌日期)──
// #339 勘误预告的第二证据形「数据内时间戳(未实现)」补齐·响应头面(体面另议):
// 直接探活无 last-modified 且非 github 家族时,disposition filename 里的日期
// (YYYY-MM-DD 或 yyyymmdd 紧排;实例 anycast_census manycast.net
// `attachment; filename="IPv4-2026-11-12.csv.gz"`——URL 恒 latest 形,真日期只在
// 文件名里)采信为 basis=embedded_date,age 按该日期算;解析失败=无证据
// fail-closed(裸 200 不算数,A1 拒);优先级 last_modified > github_commit >
// embedded_date,github 家族不吃第三基(仍走 commits 回退)。

// 内嵌日期造料:N 天前的 UTC 午夜戳 + 两形文件名段(Date.UTC 月 0 起,文件名用日历月 1 起)
const embStamp = (daysAgo) => {
  const d = new Date(Date.now() - daysAgo * dayMs);
  const ymd = [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()];
  const pad = ymd.map((n) => String(n).padStart(2, "0"));
  return { ms: Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()), iso: pad.join("-"), compact: pad.join("") };
};

test("#342 A2 绿面:非家族无 last-modified + disposition 文件名带 YYYY-MM-DD → basis=embedded_date,≤30 过门;留痕 date_source+filename+date,combos 带 header 原文", async () => {
  const s = embStamp(2.5);
  const url = "https://example.com/api/v1/export/IPv4-latest.csv.gz"; // anycast_census 同形(latest 形 URL + 日期在文件名)
  const cd = `attachment; filename="IPv4-${s.iso}.csv.gz"`;
  const f = stubFetch([{ url, respond: () => res({ contentDisposition: cd }) }]);
  const live = await probeLiveness(url, f.impl, iso());
  assert.equal(live.basis, "embedded_date");
  assert.equal(live.age_days, Math.floor((Date.now() - s.ms) / dayMs), "age 按文件名内日期(UTC 午夜)算");
  assert.ok(live.age_days >= 2 && live.age_days <= 30, "2.5 天前日期→age∈{2,3},过门");
  assert.equal(freshnessOf(live).ok, true);
  assert.equal(live.last_modified, null);
  assert.equal(live.github_commit, null, "非家族=commits 回退未尝试(三面可分诊)");
  assert.deepEqual(live.embedded_date, { date_source: "content_disposition_filename", filename: `IPv4-${s.iso}.csv.gz`, date: new Date(s.ms).toISOString() }, "留痕律:date_source=content_disposition_filename + 文件名 + 日期");
  assert.ok(live.combos.every((c) => c.content_disposition === cd), "header 原文逐组合留痕(证据不灭失)");
});

test("#342 A2 紧排形:yyyymmdd(恰 8 位数字串)同认;9 位长数字串不认(fail-closed)", async () => {
  const s = embStamp(2.5);
  const url = "https://example.com/dump-latest.txt";
  const f = stubFetch([{ url, respond: () => res({ contentDisposition: `attachment; filename=dump-${s.compact}.txt` }) }]);
  const live = await probeLiveness(url, f.impl, iso());
  assert.equal(live.basis, "embedded_date", "裸 filename(无引号)+ yyyymmdd 紧排形同认");
  assert.equal(live.embedded_date.filename, `dump-${s.compact}.txt`);
  assert.equal(live.embedded_date.date, new Date(s.ms).toISOString());
  // 9 位长数字串:恰 8 位边界钉死,不得按前 8 位误读日期
  const f9 = stubFetch([{ url, respond: () => res({ contentDisposition: `attachment; filename="dump-${s.compact}9.txt"` }) }]);
  assert.equal((await probeLiveness(url, f9.impl, iso())).basis, "none", "9 位长数字串不认");
});

test("#342 A2 红面:文件名带老日期 → 证据在场但 age>30 门红;解析失败族 = 无证据 none(裸 200 不算数,A1 拒)", async () => {
  const url = "https://example.com/feed.csv";
  const fOld = stubFetch([{ url, respond: () => res({ contentDisposition: `attachment; filename="feed-2020-01-15.csv"` }) }]);
  const old = await probeLiveness(url, fOld.impl, iso());
  assert.equal(old.basis, "embedded_date", "老日期可解析=证据在场(不是 none——有证据但陈)");
  assert.ok(old.age_days > 30);
  const gate = freshnessOf(old);
  assert.equal(gate.ok, false);
  assert.match(gate.reason, /age_days=\d+>30/, "同 aging 红面,不因基不同而宽纵");
  for (const face of [
    { label: "无 header", over: {} },
    { label: "裸 attachment 无文件名", over: { contentDisposition: "attachment" } },
    { label: "文件名无日期", over: { contentDisposition: `attachment; filename="feed-latest.csv"` } },
    { label: "非真实日历日(2 月 30)", over: { contentDisposition: `attachment; filename="feed-2026-02-30.csv"` } },
  ]) {
    const f = stubFetch([{ url, respond: () => res(face.over) }]);
    const live = await probeLiveness(url, f.impl, iso());
    assert.equal(live.basis, "none", face.label);
    assert.equal(live.age_days, undefined, face.label);
    assert.equal(live.embedded_date, null, face.label + " 无证据面不得出 embedded_date 记录");
    assert.equal(freshnessOf(live).ok, false, face.label);
  }
});

test("#342 A2 优先级:last_modified 在场不吃第三基;github 家族 commits 失败也不吃(家族面仍走 commits 回退)", async () => {
  const url = "https://example.com/feed.csv";
  const f1 = stubFetch([{ url, respond: () => res({ lastModified: "Tue, 10 Nov 2026 00:00:00 GMT", contentDisposition: `attachment; filename="feed-2020-01-15.csv"` }) }]);
  const lm = await probeLiveness(url, f1.impl, iso());
  assert.equal(lm.basis, "last_modified", "last_modified 在场=最高优先");
  assert.equal(lm.embedded_date, null, "第三基不被看");
  const f2 = stubFetch([
    { url: RAW_URL, respond: () => res({ contentDisposition: `attachment; filename="ipsum-2026-11-12.txt"` }) },
    apiRoute(() => res({ status: 403, json: { message: "rate limit" } })),
  ]);
  const fam = await probeLiveness(RAW_URL, f2.impl, iso());
  assert.equal(fam.basis, "none", "github 家族不吃第三基:commits 失败=fail-closed,不退回 embedded_date");
  assert.equal(fam.embedded_date, null);
  assert.equal(fam.github_commit.status, 403, "家族失败面留痕仍在(与未尝试可分诊)");
});

test("#342 A2 解析单测 embeddedDateFromDisposition:实测实例串/两形/边界/非真实日历日", async () => {
  const { embeddedDateFromDisposition } = await import("../tasks/add-round.mjs");
  // 实测实例串(anycast_census manycast.net 2026-11-12 实测形):
  assert.deepEqual(
    embeddedDateFromDisposition(`attachment; filename="IPv4-2026-11-12.csv.gz"`),
    { ms: Date.UTC(2026, 10, 12), filename: "IPv4-2026-11-12.csv.gz" });
  assert.equal(embeddedDateFromDisposition(`attachment; filename=IPv4-20261112.csv.gz`)?.ms, Date.UTC(2026, 10, 12), "紧排形");
  assert.equal(embeddedDateFromDisposition(`attachment`), null, "无 filename 参数");
  assert.equal(embeddedDateFromDisposition(null), null, "非字符串");
  assert.equal(embeddedDateFromDisposition(`attachment; filename="202611123.txt"`), null, "9 位不认");
  assert.equal(embeddedDateFromDisposition(`attachment; filename="2026-13-01.txt"`), null, "13 月不认(真实日历日校验)");
  const two = embeddedDateFromDisposition(`attachment; filename="v2026-11-12-2026-11-13.csv"`);
  assert.equal(two?.ms, Date.UTC(2026, 10, 13), "双日期取最新(同 last_modified newest 律)");
  assert.equal(two?.filename, "v2026-11-12-2026-11-13.csv");
});

test("#342 评审 P2-2:embedded 未来日期拒采——age < −1 fail-closed 留痕;−1≤age≤0 放行(时区吸收)", async () => {
  const mk = (daysAhead) => {
    const d = new Date(Date.now() + daysAhead * 86_400_000);
    const stamp = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
    return `attachment; filename="feed-${stamp}.csv.gz"`;
  };
  const fFar = stubFetch([{ url: "https://example.com/feed.csv", respond: () => res({ contentDisposition: mk(3) }) }]);
  const far = await probeLiveness("https://example.com/feed.csv", fFar.impl, { ...iso() });
  assert.equal(far.basis, "none", "未来 3 天=拒采,无证据 fail-closed");
  assert.ok(far.embedded_date?.rejected_reason?.includes("embedded_future_date"), "拒采面留痕可分诊");
  const fEdge = stubFetch([{ url: "https://example.com/feed.csv", respond: () => res({ contentDisposition: mk(0.5) }) }]);
  const edge = await probeLiveness("https://example.com/feed.csv", fEdge.impl, { ...iso() });
  assert.equal(edge.basis, "embedded_date", "半天超前(时区面)放行");
  assert.ok(!edge.embedded_date?.rejected_reason, "放行面无拒采痕");
});
