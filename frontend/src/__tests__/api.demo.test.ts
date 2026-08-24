import { describe, it, expect, vi, beforeEach } from "vitest";

const fetchSpy = vi.fn();
vi.stubGlobal("fetch", fetchSpy);

import { getPublicDemo, getDbStatus } from "../api";

describe("public demo client", () => {
  beforeEach(() => {
    fetchSpy.mockReset();
  });

  it("getDbStatus sends x-ipradar-client header", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 200 }),
    );
    await getDbStatus();
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["x-ipradar-client"]).toBe("web");
  });

  it("getPublicDemo caches version result and defaults false on error", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ public_demo: true }), { status: 200 }),
    );
    await expect(getPublicDemo()).resolves.toBe(true);
    // 第二次调用走缓存,不再发请求
    fetchSpy.mockClear();
    await expect(getPublicDemo()).resolves.toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("getPublicDemo error fallback", () => {
  it("resolves false when /api/version fails", async () => {
    vi.resetModules();
    fetchSpy.mockReset();
    fetchSpy.mockRejectedValueOnce(new Error("offline"));
    const mod = await import("../api");
    await expect(mod.getPublicDemo()).resolves.toBe(false);
  });
});
