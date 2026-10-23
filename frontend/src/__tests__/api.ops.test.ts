import { fetchMock, installFetchMock } from "../test/fetchMock";
import type { ApiError } from "../api";
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  startOpsRound,
  listOpsPackages,
  readOpsPackage,
  readOpsLedger,
  listOpsPrecedents,
  readOpsPrecedent,
  postOpsRuling,
  exportOpsPrecedents,
  getOpsAgentConfig,
  putOpsAgentConfig,
  getOpsItems,
  readOpsItem,
  postOpsReview,
} from "../api";

// P4(票 #136):ops admin 面数据层。契约真源 = backend/main.py 9 条 ops
// 路由(P2/P3 冻结面 + 票 #140 配置 2)+ _api_models.py Ops* 模型——期望值全部对拍该真源,
// 不从被测模块反推。错误面:后端统一信封 {error:{code,message}} 必须以
// ApiError(status+code+message) 抛出(AdminPage 面既有约定)。
describe("api ops functions (P4, #136)", () => {
  beforeEach(() => {
    installFetchMock();
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(() => ({ close: () => {} }));
  });

  it("startOpsRound posts {type,input} to /api/ops/rounds and returns task_id", async () => {
    fetchMock().mockResolvedValue({ ok: true, status: 202, json: async () => ({ task_id: "abc123" }) });
    const r = await startOpsRound("health", "health");
    expect(r.task_id).toBe("abc123");
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/ops/rounds");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ type: "health", input: "health" });
  });

  it("startOpsRound rejects with the error envelope (status+code) on 409 eval_busy", async () => {
    fetchMock().mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ error: { code: "eval_busy", message: "an ops round is already in flight" } }),
    });
    const e = (await startOpsRound("discover", "新候选 x").catch((err) => err)) as ApiError;
    expect(e.status).toBe(409);
    expect(e.code).toBe("eval_busy");
    expect(e.message).toBe("an ops round is already in flight");
  });

  it("listOpsPackages GETs /api/ops/packages", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({
        packages: [{ name: "2026-10-20-discover-1030.md", size: 4096, modified: "2026-10-20T10:30:00+00:00" }],
      }),
    });
    const r = await listOpsPackages();
    expect(r).toEqual([{ name: "2026-10-20-discover-1030.md", size: 4096, modified: "2026-10-20T10:30:00+00:00" }]);
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/packages");
    expect(fetchMock().mock.calls[0][1]).toBeUndefined();
  });

  it("readOpsPackage GETs the encoded package name and returns text", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => ({ text: "# 裁决包\n" }) });
    const r = await readOpsPackage("2026-10-20-discover-1030.md");
    expect(r).toBe("# 裁决包\n");
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/packages/2026-10-20-discover-1030.md");
  });

  it("readOpsLedger GETs /api/ops/ledger and returns text", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => ({ text: "| 日期 |\n" }) });
    const r = await readOpsLedger();
    expect(r).toBe("| 日期 |\n");
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/ledger");
  });

  it("listOpsPrecedents GETs all / with kws query param encoded", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => ({ precedents: ["2026-10-18-a.md"] }) });
    await listOpsPrecedents();
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/precedents");
    await listOpsPrecedents("sunset mirror");
    expect(fetchMock().mock.calls[1][0]).toBe(`/api/ops/precedents?kws=${encodeURIComponent("sunset mirror")}`);
  });

  it("readOpsPrecedent GETs the encoded precedent name and returns text", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => ({ text: "# 判例\n" }) });
    const r = await readOpsPrecedent("2026-10-18-a.md");
    expect(r).toBe("# 判例\n");
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/precedents/2026-10-18-a.md");
  });

  it("postOpsRuling posts {package,suggestion,verdict,amendment} and returns the write result", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({
        created: true, precedent: "2026-10-20-ruling-abc123def0.md",
        superseded: null, queue_appended: true,
      }),
    });
    const r = await postOpsRuling(
      "2026-10-20-discover-1030.md",
      "ENQUEUE threatview_c2 — 排他 57.0%",
      "amended",
      "修正案逐字",
    );
    expect(r).toEqual({
      created: true, precedent: "2026-10-20-ruling-abc123def0.md",
      superseded: null, queue_appended: true,
    });
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/ops/ruling");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      package: "2026-10-20-discover-1030.md",
      suggestion: "ENQUEUE threatview_c2 — 排他 57.0%",
      verdict: "amended",
      amendment: "修正案逐字",
    });
  });

  it("postOpsRuling omits amendment when undefined (agreed/overruled 零修正案)", async () => {
    fetchMock().mockResolvedValue({
      ok: true, json: async () => ({ created: true, precedent: "p.md", superseded: null, queue_appended: false }),
    });
    await postOpsRuling("pkg.md", "建议原文", "agreed");
    expect(JSON.parse(fetchMock().mock.calls[0][1].body)).toEqual({
      package: "pkg.md", suggestion: "建议原文", verdict: "agreed",
    });
  });

  it("exportOpsPrecedents GETs export.zip and resolves a Blob", async () => {
    fetchMock().mockResolvedValue({ ok: true, blob: async () => new Blob(["zip-bytes"]) });
    const b = await exportOpsPrecedents();
    expect(b).toBeInstanceOf(Blob);
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/precedents/export.zip");
  });

  // ── P1 待审条目面(票 #153/#155):列表/全文/四键审阅 ──

  it("getOpsItems GETs /api/ops/items and returns the backend-ordered list", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{
        id: "2026-10-23-item-bbbb000002", action: "retry_download",
        args: { source: "spamhaus_drop" }, evidence: { consecutive_failures: 3 },
        impact: "spamhaus_drop 数据停更", rollback: "重新触发下载即可恢复",
        dedup_key: { source: "spamhaus_drop", probe_class: "download", error_signature: "http_403_anonymous" },
        severity: "high", cause_group: "download_failure", status: "active",
        supersedes: null, modified: "2026-10-23T05:30:00Z",
      }] }),
    });
    const r = await getOpsItems();
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe("2026-10-23-item-bbbb000002");
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/items");
  });

  it("readOpsItem GETs the encoded item id and returns text", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => ({ text: "---\nid: x\n---\n" }) });
    const r = await readOpsItem("2026-10-23-item-bbbb000002");
    expect(r).toBe("---\nid: x\n---\n");
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/items/2026-10-23-item-bbbb000002");
  });

  it("postOpsReview posts the four-key payload per verdict (分键互斥载荷)", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({
        item: "2026-10-23-item-bbbb000002", verdict: "modify", status: "done",
        executed: true, proposal_only: false,
        precedent: "2026-10-23-ruling-2222222222.md", created: true,
        superseded: null, queue_appended: false, wake_at: null,
      }),
    });
    const r = await postOpsReview("2026-10-23-item-bbbb000002", "modify", {
      args: { source: "spamhaus_drop", force: true },
    });
    expect(r.executed).toBe(true);
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/ops/items/2026-10-23-item-bbbb000002/review");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      verdict: "modify", args: { source: "spamhaus_drop", force: true },
    });
    // agree 零参数:body 只带 verdict(分键互斥,不带空字段)
    await postOpsReview("2026-10-23-item-bbbb000002", "agree");
    expect(JSON.parse(fetchMock().mock.calls[1][1].body)).toEqual({ verdict: "agree" });
  });

  it("exportOpsPrecedents rejects with the envelope on failure", async () => {
    fetchMock().mockResolvedValue({
      ok: false, status: 500,
      json: async () => ({ error: { code: "internal", message: "rg failed rc=2" } }),
    });
    const e = (await exportOpsPrecedents().catch((err) => err)) as ApiError;
    expect(e.status).toBe(500);
    expect(e.code).toBe("internal");
  });
});

// 票 #140 立:agent 配置面数据层;票 #143 多供应商形状。契约真源 = backend
// GET/PUT /api/ops/agent-config + _api_models.py OpsAgentConfig*(动态目录/
// qualified 值/逐家 key 永不回显,出参只带 configured+tail4);catalog =
// 后端驱动双下拉的单一真相源(node 子调用 dump,失败兜底闭集并显式
// catalog_source)。
describe("api ops agent config (票 #140/#143)", () => {
  beforeEach(() => {
    installFetchMock();
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(() => ({ close: () => {} }));
  });

  const CFG = {
    model_health: "zai-coding-cn/glm-5.3-flash",
    model_discover: "zai-coding-cn/glm-5.3",
    api_keys: { "zai-coding-cn": { configured: true, tail4: "9988" } },
    catalog: {
      "zai-coding-cn": [{ id: "glm-5.3", name: "GLM-5.3", cost: { input: 1.4, output: 4.4, cacheRead: 0.26, cacheWrite: 0 } }],
      "fake-prov": [{ id: "fake-7b", name: "Fake 7B", cost: null }],
    },
    catalog_source: "dynamic" as const,
  };

  it("getOpsAgentConfig GETs /api/ops/agent-config and returns the status shape", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => CFG });
    const r = await getOpsAgentConfig();
    expect(r).toEqual(CFG);
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/agent-config");
    expect(fetchMock().mock.calls[0][1]).toBeUndefined();
  });

  it("putOpsAgentConfig PUTs qualified models + api_keys and returns the updated status", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => CFG });
    const r = await putOpsAgentConfig({
      model_health: "fake-prov/fake-7b", model_discover: "zai-coding-cn/glm-5.3-highspeed",
      api_keys: { "fake-prov": "sk-ant-new-4321" },
    });
    expect(r).toEqual(CFG);
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/ops/agent-config");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({
      model_health: "fake-prov/fake-7b", model_discover: "zai-coding-cn/glm-5.3-highspeed",
      api_keys: { "fake-prov": "sk-ant-new-4321" },
    });
  });

  it("putOpsAgentConfig omits api_keys when no keys typed (保持不改语义)", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => CFG });
    await putOpsAgentConfig({ model_health: "zai-coding-cn/glm-5.3", model_discover: "zai-coding-cn/glm-5.3" });
    expect(JSON.parse(fetchMock().mock.calls[0][1].body)).toEqual({
      model_health: "zai-coding-cn/glm-5.3", model_discover: "zai-coding-cn/glm-5.3",
    });
  });

  it("putOpsAgentConfig rejects with the envelope on 422 (目录外模型)", async () => {
    fetchMock().mockResolvedValue({
      ok: false, status: 422,
      json: async () => ({ error: { code: "validation_error", message: "model_health 未在 zai-coding-cn 装载目录内(glm-4.6v/…): zai-coding-cn/gpt-4o" } }),
    });
    const e = (await putOpsAgentConfig({ model_health: "bad", model_discover: "zai-coding-cn/glm-5.3" }).catch((err) => err)) as ApiError;
    expect(e.status).toBe(422);
    expect(e.code).toBe("validation_error");
  });
});
