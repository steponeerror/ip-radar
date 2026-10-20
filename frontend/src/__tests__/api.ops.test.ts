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
} from "../api";

// P4(票 #136):ops admin 面数据层。契约真源 = backend/main.py 7 条 ops
// 路由 + _api_models.py Ops* 模型(P2/P3 冻结面)——期望值全部对拍该真源,
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

// 票 #140:agent 配置面数据层。契约真源 = backend GET/PUT /api/ops/agent-config
// + _api_models.py OpsAgentConfig*(闭集/优先级链/永不回显 key,出参只带
// configured+tail4);allowed_models = 后端驱动下拉的单一真相源(实测 pi-ai
// 装载目录五值,裁决 2026-10-20)。
describe("api ops agent config (票 #140)", () => {
  beforeEach(() => {
    installFetchMock();
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(() => ({ close: () => {} }));
  });

  const CFG = {
    model_health: "glm-5.3-flash",
    model_discover: "glm-5.3",
    zai_api_key: { configured: true, tail4: "9988" },
    allowed_models: ["glm-4.6v", "glm-5.3", "glm-5.3-flash", "glm-5.3-highspeed", "glm-5.3-flashx"],
  };

  it("getOpsAgentConfig GETs /api/ops/agent-config and returns the status shape", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => CFG });
    const r = await getOpsAgentConfig();
    expect(r).toEqual(CFG);
    expect(fetchMock().mock.calls[0][0]).toBe("/api/ops/agent-config");
    expect(fetchMock().mock.calls[0][1]).toBeUndefined();
  });

  it("putOpsAgentConfig PUTs models + key and returns the updated status", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => CFG });
    const r = await putOpsAgentConfig({
      model_health: "glm-4.6v", model_discover: "glm-5.3-highspeed", zai_api_key: "sk-new-9988",
    });
    expect(r).toEqual(CFG);
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/ops/agent-config");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({
      model_health: "glm-4.6v", model_discover: "glm-5.3-highspeed", zai_api_key: "sk-new-9988",
    });
  });

  it("putOpsAgentConfig omits zai_api_key when blank (保持不改语义)", async () => {
    fetchMock().mockResolvedValue({ ok: true, json: async () => CFG });
    await putOpsAgentConfig({ model_health: "glm-5.3", model_discover: "glm-5.3" });
    expect(JSON.parse(fetchMock().mock.calls[0][1].body)).toEqual({
      model_health: "glm-5.3", model_discover: "glm-5.3",
    });
  });

  it("putOpsAgentConfig rejects with the envelope on 422 (闭集外模型)", async () => {
    fetchMock().mockResolvedValue({
      ok: false, status: 422,
      json: async () => ({ error: { code: "validation_error", message: "model_health 必须在闭集内" } }),
    });
    const e = (await putOpsAgentConfig({ model_health: "bad", model_discover: "glm-5.3" }).catch((err) => err)) as ApiError;
    expect(e.status).toBe(422);
    expect(e.code).toBe("validation_error");
  });
});
