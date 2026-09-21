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
  ...over,
});

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
      body: JSON.stringify({ name: "for-curl", expires_days: 30 }),
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
