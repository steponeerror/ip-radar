import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import AdminPage from "../AdminPage";
import { renderWithI18n } from "../../test/i18nTestUtils";

// Controller-amended mock sequence (Task 2 backend contract):
//   me(401) → login(204, NO body — cookie session) → me(200 {email})
// Task 9:登录后的壳内挂 TaskProvider(SSE)+ SourcesPage(manage)+
// KeysSection + BatchPanel —— 数据层函数在模块 mock 中接管,fetch 只服务会话流。
// Task:admin 控制台改顶 tab 壳(tab 范式):Sources 默认 / API Keys / Tasks,
// 品牌行 h1 + email/登出,sticky tab bar;eval 区已删(从未存在)。
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
  it("shows brand heading + login form when logged out, then enters the tabbed admin shell on success", async () => {
    mockFetch
      .mockResolvedValueOnce(me401)        // /api/users/me — anonymous
      .mockResolvedValueOnce({ ok: true, status: 204 }) // login: cookie session, no body
      .mockResolvedValueOnce(me200);       // re-fetch me after login
    renderWithI18n(<AdminPage />);
    const email = await screen.findByLabelText("Email");
    // 品牌行落在 AdminPage 登录态(admin-main.tsx 不再渲染 h1)
    expect(screen.getByRole("heading", { level: 1, name: "IP Radar Admin" })).toBeTruthy();
    expect(email).toHaveValue("admin@ipradar.local"); // prefilled
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "x".repeat(12) } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy());
    expect(screen.getByRole("tab", { name: "Sources" })).toBeTruthy();
    expect(mockFetch).toHaveBeenNthCalledWith(2, "/api/auth/jwt/login", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }));
  });

  it("enters the shell directly when the session cookie is valid", async () => {
    mockFetch.mockResolvedValueOnce(me200);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy());
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("logged-in shell: header row (brand/email/sign-out) + tabs; default = Sources only, Keys tab swaps", async () => {
    mockFetch.mockResolvedValueOnce(me200);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy());
    // 头排:h1 品牌 + email + Sign out 同排
    expect(screen.getByRole("heading", { level: 1, name: "IP Radar Admin" })).toBeTruthy();
    expect(screen.getByText("admin@ipradar.local")).toBeTruthy();
    // 三个 tab(Sources → API Keys → Tasks),默认选中 sources
    const tabSources = screen.getByRole("tab", { name: "Sources" });
    const tabKeys = screen.getByRole("tab", { name: "API Keys" });
    expect(screen.getByRole("tab", { name: "Tasks" })).toBeTruthy();
    expect(tabSources).toHaveAttribute("aria-selected", "true");
    expect(tabKeys).toHaveAttribute("aria-selected", "false");
    // 默认 tab 内容:SourcesPage manage 挂载(空列表 → 无源文案),
    // keys 内容(Create key)不在 DOM —— 非活动 tab 不渲染
    await screen.findByText(/no sources discovered/i);
    expect(screen.queryByRole("button", { name: "Create key" })).toBeNull();
    // eval 从未存在,任何 tab 态都不得出现
    expect(screen.queryByText("Eval")).toBeNull();
    // 切到 API Keys:Create key 出现,sources 内容消失
    fireEvent.click(tabKeys);
    expect(await screen.findByRole("button", { name: "Create key" })).toBeTruthy();
    expect(screen.queryByText(/no sources discovered/i)).toBeNull();
    expect(screen.getByRole("tab", { name: "API Keys" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("Eval")).toBeNull();
    // 切到 Tasks:其余 tab 内容全部让位
    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));
    expect(screen.queryByRole("button", { name: "Create key" })).toBeNull();
    expect(screen.queryByText(/no sources discovered/i)).toBeNull();
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
