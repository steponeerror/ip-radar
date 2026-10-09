import { fetchMock, installFetchMock } from "../test/fetchMock";
import type { ApiError, LookupResult } from "../api";
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  enqueueBatch,
  enqueueSingle,
  getTasks,
  getDbStatus,
  cancelTask,
  cancelBatch,
  pauseBatch,
  resumeBatch,
  subscribeTasks,
  queryIpsStream,
  TABLE_THRESHOLD,
} from "../api";

describe("api task functions", () => {
  beforeEach(() => {
    installFetchMock();
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(() => ({ close: () => {} }));
  });

  it("enqueueBatch posts /api/update-db", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({ batch_id: "b1" }),
    });
    const r = await enqueueBatch();
    expect(r.batch_id).toBe("b1");
    expect(fetchMock().mock.calls[0][0]).toBe("/api/update-db");
    expect(fetchMock().mock.calls[0][1].method).toBe("POST");
  });

  it("enqueueSingle posts to source update", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({ task_id: "t1" }),
    });
    const r = await enqueueSingle("feodo");
    expect(r.task_id).toBe("t1");
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/sources/feodo/update");
    expect(init.method).toBe("POST");
  });

  it("enqueueSingle encodes the source name", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({ task_id: "t2" }),
    });
    await enqueueSingle("weird name");
    expect(fetchMock().mock.calls[0][0]).toBe(
      "/api/sources/weird%20name/update",
    );
  });

  it("getTasks returns snapshot", async () => {
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({ tasks: [], batch: null }),
    });
    const s = await getTasks();
    expect(s.tasks).toEqual([]);
    expect(s.batch).toBeNull();
    expect(fetchMock().mock.calls[0][0]).toBe("/api/tasks");
  });

  it("getTasks throws on non-ok response", async () => {
    fetchMock().mockResolvedValue({
      ok: false,
      statusText: "Server Error",
    });
    await expect(getTasks()).rejects.toThrow();
  });

  it("enqueueBatch throws on non-ok response", async () => {
    fetchMock().mockResolvedValue({
      ok: false,
      statusText: "Boom",
    });
    await expect(enqueueBatch()).rejects.toThrow();
  });

  it("cancelTask posts to /api/tasks/:id/cancel", async () => {
    fetchMock().mockResolvedValue({ ok: true });
    await cancelTask("t9");
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/tasks/t9/cancel");
    expect(init.method).toBe("POST");
  });

  it("cancelBatch posts to /api/update-db/cancel", async () => {
    fetchMock().mockResolvedValue({ ok: true });
    await cancelBatch();
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/update-db/cancel");
    expect(init.method).toBe("POST");
  });

  it("pauseBatch posts to /api/update-db/pause", async () => {
    fetchMock().mockResolvedValue({ ok: true });
    await pauseBatch();
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/update-db/pause");
    expect(init.method).toBe("POST");
  });

  it("resumeBatch posts to /api/update-db/resume", async () => {
    fetchMock().mockResolvedValue({ ok: true });
    await resumeBatch();
    const [url, init] = fetchMock().mock.calls[0];
    expect(url).toBe("/api/update-db/resume");
    expect(init.method).toBe("POST");
  });

  // U7:控制类端点非 ok 必须 reject(带 status+code 信封),不再静默吞掉
  it("control endpoints reject with envelope error on non-ok (U7)", async () => {
    fetchMock().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "task_not_found", message: "no such task" } }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      ),
    );
    const err = (await cancelTask("t9").then(() => null, (e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
    expect(err.code).toBe("task_not_found");
    expect(err.message).toBe("no such task");
  });

  it("cancelBatch / pauseBatch / resumeBatch all reject on non-ok (U7)", async () => {
    for (const fn of [cancelBatch, pauseBatch, resumeBatch]) {
      fetchMock().mockResolvedValue({ ok: false, statusText: "Boom" });
      await expect(fn()).rejects.toThrow();
    }
  });
});

describe("subscribeTasks", () => {
  beforeEach(() => {
    installFetchMock();
  });

  it("opens EventSource on /api/events, parses JSON, returns unsub that closes", () => {
    const close = vi.fn();
    let msgHandler: ((m: { data: string }) => void) | null = null;
    let openHandler: (() => void) | null = null;
    type MockEventSource = {
      onmessage: ((m: { data: string }) => void) | null;
      onopen: (() => void) | null;
      close: () => void;
    };
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(function (this: MockEventSource, url: string) {
      expect(url).toBe("/api/events");
      this.onmessage = null;
      this.onopen = null;
      Object.defineProperty(this, "onmessage", {
        set(f: (m: { data: string }) => void) { msgHandler = f; },
        get() { return msgHandler; },
      });
      Object.defineProperty(this, "onopen", {
        set(f: () => void) { openHandler = f; },
        get() { return openHandler; },
      });
      this.close = close;
    });

    const events: unknown[] = [];
    const onReconnect = vi.fn();
    const unsub = subscribeTasks((e) => events.push(e), onReconnect);

    // onopen fires → onReconnect
    openHandler!();
    expect(onReconnect).toHaveBeenCalledTimes(1);

    // valid JSON payload is parsed & forwarded
    msgHandler!({ data: JSON.stringify({ tasks: [], batch: null }) });
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ tasks: [], batch: null });

    // invalid JSON is swallowed (no throw, no push)
    expect(() => msgHandler!({ data: "not-json" })).not.toThrow();
    expect(events).toHaveLength(1);

    // unsub closes the EventSource
    unsub();
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("onReconnect is optional", () => {
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(function (this: {
      onmessage: unknown; onopen: unknown; close: () => void;
    }) {
      this.onmessage = null;
      this.onopen = null;
      this.close = () => {};
    });
    const unsub = subscribeTasks(() => {});
    expect(() => unsub()).not.toThrow();
  });
});

describe("queryIpsStream (row protocol v2)", () => {
  beforeEach(() => {
    installFetchMock();
    (globalThis as { EventSource?: unknown }).EventSource = vi.fn(() => ({ close: () => {} }));
  });

  it("table mode: total ≤ threshold → results sorted by idx", async () => {
    const ndjson = [
      `{"type":"start","total":2}`,
      `{"type":"row","idx":1,"result":{"ip":"1.1.1.1"}}`,
      `{"type":"row","idx":0,"result":{"ip":"8.8.8.8"}}`,
      `{"type":"progress","done":2,"total":2}`,
      `{"type":"done","invalid_lines":0,"ipv6_unsupported":0}`,
    ].join("\n");
    const reader = (async function* () {
      for (const line of ndjson.split("\n")) yield new TextEncoder().encode(line + "\n");
    })();
    fetchMock().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: () => reader.next() }) },
    });

    const out = await queryIpsStream(["8.8.8.8", "1.1.1.1"], () => {});
    expect(out.csvDownloaded).toBe(false);
    expect(out.results.map((r) => r.ip)).toEqual(["8.8.8.8", "1.1.1.1"]); // idx order
  });

  it("csv mode: total > threshold → csvDownloaded=true, results empty", async () => {
    // build N=threshold+1 fake rows; minimal valid LookupResult (buildCsvRow traverses
    // classifications/merged fields, so the fixture must satisfy that shape)
    const n = TABLE_THRESHOLD + 1;
    const fakeRow = (i: number) => {
      const r: LookupResult = {
        ip: `10.0.0.${i}`,
        country: { value: "", confidence: 0, algorithm: "", sources: [] },
        city: { value: "", confidence: 0, algorithm: "", sources: [] },
        asn: { value: 0, confidence: 0, algorithm: "", sources: [] },
        as_name: { value: "", confidence: 0, algorithm: "", sources: [] },
        ip_range: { value: "", confidence: 0, algorithm: "", sources: [] },
        is_isp: false,
        classifications: {},
      };
      return `{"type":"row","idx":${i},"result":${JSON.stringify(r)}}`;
    };
    const lines = [`{"type":"start","total":${n}}`];
    for (let i = 0; i < n; i++) lines.push(fakeRow(i));
    lines.push(`{"type":"done","invalid_lines":0,"ipv6_unsupported":0}`);
    const ndjson = lines.join("\n");
    const reader = (async function* () {
      yield new TextEncoder().encode(ndjson + "\n");
    })();
    fetchMock().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: () => reader.next() }) },
    });

    const URL_CREATE = globalThis.URL.createObjectURL;
    const REVOKE = globalThis.URL.revokeObjectURL;
    globalThis.URL.createObjectURL = () => "blob:x";
    globalThis.URL.revokeObjectURL = () => {};
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const out = await queryIpsStream(["10.0.0.0/20"], () => {});
    expect(out.csvDownloaded).toBe(true);
    expect(out.results).toEqual([]);
    expect(clickSpy).toHaveBeenCalledTimes(1);

    globalThis.URL.createObjectURL = URL_CREATE;
    globalThis.URL.revokeObjectURL = REVOKE;
    clickSpy.mockRestore();
  });

  it("done surfaces invalid_lines and ignores ipv6_unsupported (v6 supported)", async () => {
    const ndjson = [
      `{"type":"start","total":1}`,
      `{"type":"row","idx":0,"result":{"ip":"8.8.8.8"}}`,
      `{"type":"done","invalid_lines":2,"ipv6_unsupported":1}`,
    ].join("\n");
    const reader = (async function* () {
      yield new TextEncoder().encode(ndjson + "\n");
    })();
    fetchMock().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: () => reader.next() }) },
    });
    const out = await queryIpsStream(["8.8.8.8"], () => {});
    expect(out.invalidLines).toBe(2);
    expect(out).not.toHaveProperty("ipv6Unsupported");
  });

  it("done surfaces error into outcome", async () => {
    const ndjson = [
      `{"type":"start","total":2}`,
      `{"type":"row","idx":0,"result":{"ip":"8.8.8.8"}}`,
      `{"type":"done","invalid_lines":0,"ipv6_unsupported":0,"error":"boom"}`,
    ].join("\n");
    const reader = (async function* () {
      yield new TextEncoder().encode(ndjson + "\n");
    })();
    fetchMock().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: () => reader.next() }) },
    });

    const out = await queryIpsStream(["8.8.8.8"], () => {});
    expect(out.error).toBe("boom");
  });

  // U1:backend done 事件带 code(internal)时透传 error_code 供视图层 i18n
  it("done.error + code → outcome.error_code passthrough (U1)", async () => {
    const ndjson = [
      `{"type":"start","total":2}`,
      `{"type":"row","idx":0,"result":{"ip":"8.8.8.8"}}`,
      `{"type":"done","invalid_lines":0,"ipv6_unsupported":0,"error":"boom","code":"internal"}`,
    ].join("\n");
    const reader = (async function* () {
      yield new TextEncoder().encode(ndjson + "\n");
    })();
    fetchMock().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: () => reader.next() }) },
    });

    const out = await queryIpsStream(["8.8.8.8"], () => {});
    expect(out.error).toBe("boom");
    expect(out.error_code).toBe("internal");
  });

  it("clean EOF without done → error 'stream ended before done'", async () => {
    // 代理截断/进程被杀的干净关闭: start+row 已到但 done 永不到来
    const ndjson = [
      `{"type":"start","total":2}`,
      `{"type":"row","idx":0,"result":{"ip":"8.8.8.8"}}`,
    ].join("\n");
    const reader = (async function* () {
      yield new TextEncoder().encode(ndjson + "\n");
    })();
    fetchMock().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: () => reader.next() }) },
    });

    const out = await queryIpsStream(["8.8.8.8", "1.1.1.1"], () => {});
    expect(out.error).toBe("stream ended before done");
    expect(out.error_code).toBe("stream_truncated");   // U1:哨兵码供视图层 i18n
  });

  // U1:连接守卫超时的 AbortError 转结构化 ApiError(code=timeout),供横幅 i18n
  it("connect timeout abort → structured code 'timeout' (U1)", async () => {
    vi.useFakeTimers();
    try {
      fetchMock().mockImplementation((_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")));
        }),
      );
      const p = queryIpsStream(["8.8.8.8"], () => {});
      const assertion = p.then(
        () => { throw new Error("expected rejection"); },
        (e: unknown) => {
          const err = e as ApiError;
          expect(err).toBeInstanceOf(Error);
          expect(err.code).toBe("timeout");
          expect(err.status).toBe(0);
        },
      );
      await vi.advanceTimersByTimeAsync(30_000);   // streamFetchTimeout connectMs
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("apiError status attachment (review #10)", () => {
  beforeEach(() => {
    installFetchMock();
  });

  it("getDbStatus throws an error carrying status + envelope code (信封即真相,无 reason 头)", async () => {
    fetchMock().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "warming", message: "database is warming up", retry_after: 30 } }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      ),
    );
    const err = (await getDbStatus().then(() => null, (e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(503);
    expect(err.code).toBe("warming");
    expect(err.reason).toBe("warming");   // 过渡兼容:reason 同 code
    expect(err.message).toBe("database is warming up");
  });

  it("400 invalid_ip envelope → code/status/message 齐上", async () => {
    fetchMock().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "invalid_ip", message: "not a valid IP: foo" } }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      ),
    );
    const err = (await getDbStatus().then(() => null, (e: unknown) => e)) as ApiError;
    expect(err.status).toBe(400);
    expect(err.code).toBe("invalid_ip");
    expect(err.message).toBe("not a valid IP: foo");
  });

  it("falls back and still carries status when the body is not JSON", async () => {
    fetchMock().mockResolvedValue(
      new Response("gateway hiccup", { status: 502 }),
    );
    const err = (await getDbStatus().then(() => null, (e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(502);
  });
});
