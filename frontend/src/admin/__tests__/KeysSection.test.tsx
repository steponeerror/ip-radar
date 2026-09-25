import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import KeysSection from "../KeysSection";
import { renderWithI18n } from "../../test/i18nTestUtils";

// 契约 = Task 5 FROZEN:POST 201 {key, meta}(snake_case,完整 key 仅此一次);
// GET → [meta...] desc;PATCH {disabled:true} → 200 meta;DELETE → 204。
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);
beforeEach(() => mockFetch.mockReset());

const META = (over: Partial<Record<string, unknown>> = {}) => ({
  sub: "abc123def4567890",
  name: "old",
  created_at: "2026-09-01T00:00:00Z",
  last_used_at: null,
  disabled: false,
  sources: null,
  web: false,
  ...over,
});

// 源目录(/api/sources)最小形状 —— 选择器只用 name + category。
const SRC = (name: string, category: string) => ({ name, category });

describe("KeysSection", () => {
  it("lists keys, creates one, and shows the full key exactly once", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => [META()] }) // GET list
      .mockResolvedValueOnce({
        ok: true, status: 201,
        json: async () => ({
          key: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJuZXcifQ.sig",
          meta: META({ sub: "new", name: "for-curl", created_at: "2026-09-21T00:00:00Z" }),
        }),
      }); // POST create
    renderWithI18n(<KeysSection />);
    await waitFor(() => expect(screen.getByText("old")).toBeTruthy());
    expect(screen.getByText("never")).toBeTruthy(); // last_used_at: null

    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "for-curl" } });
    fireEvent.change(screen.getByLabelText("Expires in days (optional)"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    // 完整 key 一次性展示 + 警示
    await waitFor(() => expect(screen.getByText(/eyJhbGciOiJIUzI1NiJ9\.eyJzdWIiOiJuZXcifQ\.sig/)).toBeTruthy());
    expect(screen.getByText(/will not be shown again/i)).toBeTruthy();
    expect(mockFetch).toHaveBeenNthCalledWith(2, "/api/admin/keys", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ name: "for-curl", expires_days: 30, sources: null }),
    }));
  });

  it("revokes a key via PATCH and shows the disabled badge", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => [META({ sub: "s1", name: "k" })] })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => META({ sub: "s1", name: "k", disabled: true }),
      });
    renderWithI18n(<KeysSection />);
    await waitFor(() => screen.getByText("k"));
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(screen.getByText("Disabled")).toBeTruthy());
    expect(mockFetch).toHaveBeenNthCalledWith(2, "/api/admin/keys/s1", expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ disabled: true }),
    }));
  });

  it("deletes a key only after a second confirming click (two-click confirm)", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => [META({ sub: "s1", name: "k" })] })
      .mockResolvedValueOnce({ ok: true, status: 204 });
    renderWithI18n(<KeysSection />);
    await waitFor(() => screen.getByText("k"));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    // 第一击只换文案,不删除
    expect(mockFetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(screen.queryByText("k")).toBeNull());
    expect(mockFetch).toHaveBeenNthCalledWith(2, "/api/admin/keys/s1", { method: "DELETE" });
  });

  it("create modal submit carries the picked sources (toggle-off reveals multiselect)", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => [] }) // GET list (empty)
      .mockResolvedValueOnce({ // GET source catalog (lazy: revealed on toggle-off)
        ok: true,
        json: async () => [SRC("dbip", "geo_asn"), SRC("dshield", "threat")],
      })
      .mockResolvedValueOnce({ // POST create
        ok: true, status: 201,
        json: async () => ({
          key: "eyJkIjoiNyJ9.sig",
          meta: META({ sub: "new", name: "t", sources: ["dbip"] }),
        }),
      });
    renderWithI18n(<KeysSection />);
    await waitFor(() => expect(screen.getByText("No API keys yet")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "t" } });
    // 关掉"全部源"开关 → 懒加载目录并出现分组多选
    fireEvent.click(screen.getByLabelText("All sources"));
    fireEvent.click(await waitFor(() => screen.getByLabelText("dbip")));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(screen.getByText(/eyJkIjoiNyJ9\.sig/)).toBeTruthy());
    expect(mockFetch).toHaveBeenNthCalledWith(3, "/api/admin/keys", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ name: "t", sources: ["dbip"] }),
    }));
  });

  it("web badge renders and the web row has no key actions", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [META({ sub: "demoweb", name: "demo-web", web: true })],
    });
    renderWithI18n(<KeysSection />);
    expect(await screen.findByText("Web")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit sources" })).toBeNull();
  });

  it("row edit saves picked sources via PATCH setAdminKeySources", async () => {
    mockFetch
      .mockResolvedValueOnce({ // GET list
        ok: true,
        json: async () => [META({ sub: "s1", name: "k", sources: ["dbip"] })],
      })
      .mockResolvedValueOnce({ // GET source catalog (edit modal opens with explicit set)
        ok: true,
        json: async () => [SRC("dbip", "geo_asn"), SRC("dshield", "threat")],
      })
      .mockResolvedValueOnce({ // PATCH sources
        ok: true, status: 200,
        json: async () => META({ sub: "s1", name: "k", sources: ["dshield"] }),
      });
    renderWithI18n(<KeysSection />);
    await waitFor(() => screen.getByText("k"));

    fireEvent.click(screen.getByRole("button", { name: "Edit sources" }));
    // 初始集合预填:dbip 勾、dshield 空;换成 dshield 后保存
    const dbip = await waitFor(() => screen.getByLabelText("dbip"));
    expect((dbip as HTMLInputElement).checked).toBe(true);
    fireEvent.click(dbip);
    fireEvent.click(screen.getByLabelText("dshield"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mockFetch).toHaveBeenNthCalledWith(3, "/api/admin/keys/s1", expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ sources: ["dshield"] }),
    })));
  });

  it("localizes the Status column header (no hard-coded English, zh-CN)", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [META({ sub: "s1", name: "k" })] });
    renderWithI18n(<KeysSection />, { locale: "zh-CN" });
    await waitFor(() => screen.getByText("k"));
    expect(screen.getByRole("columnheader", { name: "状态" })).toBeInTheDocument();
  });

  it("401 on list kicks to login via onUnauthorized (spec §9)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false, status: 401,
      json: async () => ({ error: { code: "unauthorized", message: "Not authenticated" } }),
    });
    const onUnauthorized = vi.fn();
    renderWithI18n(<KeysSection onUnauthorized={onUnauthorized} />);
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
  });
});
