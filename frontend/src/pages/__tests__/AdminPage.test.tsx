import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import AdminPage from "../AdminPage";
import { renderWithI18n } from "../../test/i18nTestUtils";

// Controller-amended mock sequence (Task 2 backend contract):
//   me(401) → login(204, NO body — cookie session) → me(200 {email})
// Task 9:登录后的壳内挂 TaskProvider(SSE)+ SourcesPage(manage)+
// KeysSection + BatchPanel —— 数据层函数在模块 mock 中接管,fetch 只服务会话流。
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getTasks: vi.fn().mockResolvedValue({ tasks: [], batch: null }),
    subscribeTasks: vi.fn(() => () => {}),
    getSources: vi.fn().mockResolvedValue([]),
    fetchEvalModel: vi.fn().mockResolvedValue(null),
    listAdminKeys: vi.fn().mockResolvedValue([]),
  };
});

beforeEach(() => { mockFetch.mockReset(); });

const me401 = { ok: false, status: 401 };
const me200 = { ok: true, status: 200, json: async () => ({ id: "u1", email: "admin@ipradar.local" }) };

describe("AdminPage", () => {
  it("shows the login form when logged out, then enters the admin shell on success", async () => {
    mockFetch
      .mockResolvedValueOnce(me401)        // /api/users/me — anonymous
      .mockResolvedValueOnce({ ok: true, status: 204 }) // login: cookie session, no body
      .mockResolvedValueOnce(me200);       // re-fetch me after login
    renderWithI18n(<AdminPage />);
    const email = await screen.findByLabelText("Email");
    expect(email).toHaveValue("admin@ipradar.local"); // prefilled
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "x".repeat(12) } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByText("Admin Console")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(mockFetch).toHaveBeenNthCalledWith(2, "/api/auth/jwt/login", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }));
  });

  it("enters the shell directly when the session cookie is valid", async () => {
    mockFetch.mockResolvedValueOnce(me200);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText("Admin Console")).toBeTruthy());
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("logged-in shell fills all four sections (sources manage / keys / tasks / eval)", async () => {
    mockFetch.mockResolvedValueOnce(me200);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText("Admin Console")).toBeTruthy());
    // 四区标题齐备(Sources 同名出现在 SourcesPage 内部标题 → getAllByText)
    expect(screen.getAllByText("Sources").length).toBeGreaterThan(0);
    expect(screen.getAllByText("API Keys").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Tasks").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Eval").length).toBeGreaterThan(0);
    // KeysSection 已挂载(创建按钮);SourcesPage manage(空列表 → 无源文案)
    expect(await screen.findByRole("button", { name: "Create key" })).toBeTruthy();
    await screen.findByText(/no sources discovered/i);
  });

  it("shows the login-failed message from the error envelope", async () => {
    mockFetch
      .mockResolvedValueOnce(me401)
      .mockResolvedValueOnce({
        ok: false, status: 400,
        json: async () => ({ error: { code: "bad_request", message: "Bad credentials" } }),
      });
    renderWithI18n(<AdminPage />);
    await screen.findByLabelText("Email");
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByText(/Login failed/)).toBeTruthy());
    expect(screen.getByText(/Bad credentials/)).toBeTruthy();
  });

  it("hides the raw fastapi-users enum on wrong password (plain loginFailed text)", async () => {
    mockFetch
      .mockResolvedValueOnce(me401)
      .mockResolvedValueOnce({
        ok: false, status: 400,
        json: async () => ({ error: { code: "bad_request", message: "LOGIN_BAD_CREDENTIALS" } }),
      });
    renderWithI18n(<AdminPage />);
    await screen.findByLabelText("Email");
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByText(/Login failed/)).toBeTruthy());
    // 库枚举不得泄漏到 UI(fastapi-users detail = LOGIN_BAD_CREDENTIALS)
    expect(screen.queryByText(/LOGIN_BAD_CREDENTIALS/)).toBeNull();
  });

  it("shows the rate-limit message with retry seconds on 429", async () => {
    mockFetch
      .mockResolvedValueOnce(me401)
      .mockResolvedValueOnce({
        ok: false, status: 429,
        json: async () => ({ error: { code: "rate_limited", message: "rate limit exceeded", retry_after: 42 } }),
      });
    renderWithI18n(<AdminPage />);
    await screen.findByLabelText("Email");
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByText(/Too many attempts/)).toBeTruthy());
    expect(screen.getByText(/42/)).toBeTruthy();
  });
});
