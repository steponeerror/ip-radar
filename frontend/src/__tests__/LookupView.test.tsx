import { describe, it, expect, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import LookupView from "../LookupView";
import { renderWithI18n } from "../test/i18nTestUtils";
import { getDbStatus, queryIpsStream, type DbStatus } from "../api";

// Task 9:公开查询页不再包 TaskProvider(任务上下文收敛到 /admin)
vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...real,
    getDbStatus: vi.fn(),
    queryIpsStream: vi.fn(),
    uploadFileStream: vi.fn(),
  };
});

function renderLookup() {
  return renderWithI18n(<LookupView />);
}

describe("LookupView warmup integration", () => {
  it("renders WarmupBanner above the query controls while warming", async () => {
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: true, total_records: 0 } as DbStatus);
    const { container } = renderLookup();
    await waitFor(() => expect(container.querySelector("[data-warmup]")).not.toBeNull());
    const banner = container.querySelector("[data-warmup]")!;
    const textarea = container.querySelector("textarea")!;
    // 横幅在查询控件之前(文档顺序)
    expect(
      banner.compareDocumentPosition(textarea) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("disables IP input, file upload and query button while warming", async () => {
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: true, total_records: 0 } as DbStatus);
    const { container } = renderLookup();
    // text tab: textarea + 查询按钮置灰
    await waitFor(() => expect((container.querySelector("textarea") as HTMLTextAreaElement).disabled).toBe(true));
    expect(screen.getByRole("button", { name: "Query" })).toBeDisabled();
    // file tab: 文件选择置灰
    fireEvent.click(screen.getByRole("button", { name: "File Upload" }));
    const fileInput = await screen.findByLabelText("Choose File");
    expect(fileInput).toBeDisabled();
  });

  it("keeps controls enabled and hides banner when not warming", async () => {
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    const { container } = renderLookup();
    await waitFor(() => expect(container.querySelector("textarea")).not.toBeNull());
    expect((container.querySelector("textarea") as HTMLTextAreaElement).disabled).toBe(false);
    expect(screen.getByRole("button", { name: "Query" })).toBeEnabled();
    expect(container.querySelector("[data-warmup]")).toBeNull();
  });
});

describe("LookupView 503 self-correction", () => {
  it("a warming 503 from a query suppresses the generic error and reveals the banner + disables controls", async () => {
    // 所有 getDbStatus 调用共享一个 deferred:挂载期轮询保持 pending
    // (控件可用);查询撞 503 后 resolve warming_up=true,LookupView 的
    // 重拉与 WarmupBanner 的轮询拿到同一份结果(横幅不必等 5s 轮询)。
    vi.mocked(queryIpsStream).mockClear();
    let resolveStatus!: (v: DbStatus) => void;
    const pending = new Promise<DbStatus>(r => { resolveStatus = r; });
    vi.mocked(getDbStatus).mockReturnValue(pending);
    const err503 = Object.assign(new Error("database is warming up"), { status: 503, code: "warming" });
    vi.mocked(queryIpsStream).mockRejectedValue(err503);

    const { container } = renderLookup();
    const textarea = await waitFor(() => {
      const el = container.querySelector("textarea") as HTMLTextAreaElement;
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(textarea, { target: { value: "1.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    resolveStatus({ warming_up: true, total_records: 0 } as DbStatus);

    await waitFor(() => expect(container.querySelector("[data-warmup]")).not.toBeNull());
    expect(screen.queryByText("database is warming up")).toBeNull();
    expect(screen.getByRole("button", { name: "Query" })).toBeDisabled();
    // 仍在 warming → 不重试(横幅接管,查询就此打住)
    expect(queryIpsStream).toHaveBeenCalledTimes(1);
  });

  it("retries the query once when the gate closed between the 503 and the db-status refetch", async () => {
    // review #4: 重拉说 warming 已结束(503 与重拉之间的竞态窗口)时,
    // 旧实现只 setWarming(false) 静默丢弃查询;现在原样重试一次成功。
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    const err503 = Object.assign(new Error("database is warming up"), { status: 503, code: "warming" });
    const mf = <T,>(value: T, confidence = 95) => ({
      value, confidence, algorithm: "cascade", sources: [],
    });
    const outcome = {
      results: [{
        ip: "1.1.1.1",
        country: mf("US"), city: mf("N/A", 0), asn: mf(13335, 90),
        as_name: mf("Cloudflare", 90), ip_range: mf("1.1.1.0/24", 90),
        is_isp: false, classifications: {},
      }],
      csvDownloaded: false, invalidLines: 0, total: 1,
    };
    vi.mocked(queryIpsStream).mockRejectedValueOnce(err503).mockResolvedValueOnce(outcome);

    const { container } = renderLookup();
    const textarea = await waitFor(() => {
      const el = container.querySelector("textarea") as HTMLTextAreaElement;
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(textarea, { target: { value: "1.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    await waitFor(() => expect(screen.getByText("1.1.1.1")).not.toBeNull());
    expect(queryIpsStream).toHaveBeenCalledTimes(2);   // 一次 503 + 一次重试
    expect(screen.queryByText("database is warming up")).toBeNull();
    expect(container.querySelector("[data-warmup]")).toBeNull();
  });

  it("gives up with the generic error when the retried attempt 503s again (no ping-pong)", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    const err503 = Object.assign(new Error("database is warming up"), { status: 503, code: "warming" });
    vi.mocked(queryIpsStream).mockRejectedValue(err503);   // 每次都 503

    const { container } = renderLookup();
    const textarea = await waitFor(() => {
      const el = container.querySelector("textarea") as HTMLTextAreaElement;
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(textarea, { target: { value: "1.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    await waitFor(() => expect(screen.getByText("database is warming up")).not.toBeNull());
    expect(queryIpsStream).toHaveBeenCalledTimes(2);   // 恰好重试一次,不再多
    expect(container.querySelector("[data-warmup]")).toBeNull();
  });

  it("a no-sources 503 shows the localized message once, without retrying (F3)", async () => {
    // 全源禁用的 503 是配置态而非瞬时门:不重试(50MB 上传不再重发),
    // 用户看到本地化文案而非后端裸英文串。
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 0 } as DbStatus);
    const errNoSources = Object.assign(
      new Error("no data sources enabled"), { status: 503, code: "no_sources" });
    vi.mocked(queryIpsStream).mockRejectedValue(errNoSources);

    const { container } = renderLookup();
    const textarea = await waitFor(() => {
      const el = container.querySelector("textarea") as HTMLTextAreaElement;
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(textarea, { target: { value: "1.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    await waitFor(() => expect(screen.getByText(/No data sources enabled/)).not.toBeNull());
    expect(screen.queryByText("no data sources enabled")).toBeNull();  // 非裸串
    expect(queryIpsStream).toHaveBeenCalledTimes(1);   // 不重试
    expect(container.querySelector("[data-warmup]")).toBeNull();
  });

  it("a non-warming error still shows the generic error box without the banner", async () => {
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockRejectedValue(new Error("boom"));

    const { container } = renderLookup();
    const textarea = await waitFor(() => {
      const el = container.querySelector("textarea") as HTMLTextAreaElement;
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(textarea, { target: { value: "1.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    await waitFor(() => expect(screen.getByText("boom")).not.toBeNull());
    expect(container.querySelector("[data-warmup]")).toBeNull();
    expect(screen.getByRole("button", { name: "Query" })).toBeEnabled();
  });

  it("a 400 invalid_ip from a single query surfaces the backend message (信封迁移)", async () => {
    // 单查询无前端 IP 校验,非法 IP 直接打到后端:400 invalid_ip 走通用
    // 错误分支展示后端 message,不触发 warming 自纠。
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockRejectedValue(
      Object.assign(new Error("not a valid IP: 999.1.1.1"), { status: 400, code: "invalid_ip" }));

    const { container } = renderLookup();
    const textarea = await waitFor(() => {
      const el = container.querySelector("textarea") as HTMLTextAreaElement;
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(textarea, { target: { value: "999.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    await waitFor(() => expect(screen.getByText("not a valid IP: 999.1.1.1")).not.toBeNull());
    expect(container.querySelector("[data-warmup]")).toBeNull();
    expect(queryIpsStream).toHaveBeenCalledTimes(1);   // 非瞬时门,不重试
  });
});

describe("LookupView stream done.error", () => {
  it("shows error banner when queryIpsStream resolves with error (no throw)", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockResolvedValue({
      results: [], csvDownloaded: false, invalidLines: 0,
      total: 1, error: "boom",
    });
    renderLookup();

    const textarea = screen.getByPlaceholderText(/1\.1\.1\.1/i);
    fireEvent.change(textarea, { target: { value: "8.8.8.8" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(queryIpsStream).toHaveBeenCalledWith(["8.8.8.8"], expect.anything());
  });

  it("shows error banner alongside CSV modal in csv mode (csvDownloaded + error)", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockResolvedValue({
      results: [], csvDownloaded: true, invalidLines: 0,
      total: 60000, error: "boom",
    });
    renderLookup();

    const textarea = screen.getByPlaceholderText(/1\.1\.1\.1/i);
    fireEvent.change(textarea, { target: { value: "8.8.8.8" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Results exported as CSV")).toBeInTheDocument();
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});

describe("LookupView error banner i18n (U1)", () => {
  // 主行必为 t() 键,信封 message 不再裸上屏;retry_after 追加「约 Ns 后可重试」
  it("429 rate_limited renders localized main line + retry-after hint, not the raw envelope message", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockRejectedValue(Object.assign(
      new Error("rate limit exceeded"),
      { status: 429, code: "rate_limited", retry_after: 30 }));

    renderWithI18n(<LookupView />, { locale: "zh-CN" });
    const textarea = screen.getByPlaceholderText(/1\.1\.1\.1/i);
    fireEvent.change(textarea, { target: { value: "8.8.8.8" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(await screen.findByText("查询过于频繁，请稍后重试")).toBeInTheDocument();
    expect(screen.getByText("约 30 秒后可重试")).toBeInTheDocument();
    expect(screen.queryByText("rate limit exceeded")).toBeNull();   // 非裸 e.message
  });

  it("truncated stream outcome renders the localized truncation line, not the frontend sentinel", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockResolvedValue({
      results: [], csvDownloaded: false, invalidLines: 0, total: 2,
      error: "stream ended before done", error_code: "stream_truncated",
    });

    renderWithI18n(<LookupView />, { locale: "zh-CN" });
    const textarea = screen.getByPlaceholderText(/1\.1\.1\.1/i);
    fireEvent.change(textarea, { target: { value: "8.8.8.8" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(await screen.findByText("响应流意外中断，结果可能不完整，请重试")).toBeInTheDocument();
    expect(screen.queryByText("stream ended before done")).toBeNull();
  });

  it("422 validation_error renders the localized line, not the backend message", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockRejectedValue(Object.assign(
      new Error("request validation failed"),
      { status: 422, code: "validation_error" }));

    renderWithI18n(<LookupView />, { locale: "zh-CN" });
    const textarea = screen.getByPlaceholderText(/1\.1\.1\.1/i);
    fireEvent.change(textarea, { target: { value: "8.8.8.8" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(await screen.findByText("请求参数无效")).toBeInTheDocument();
    expect(screen.queryByText("request validation failed")).toBeNull();
  });

  it("400 invalid_ip keeps the envelope message as the secondary detail line (en)", async () => {
    vi.mocked(queryIpsStream).mockClear();
    vi.mocked(getDbStatus).mockResolvedValue({ warming_up: false, total_records: 100 } as DbStatus);
    vi.mocked(queryIpsStream).mockRejectedValue(Object.assign(
      new Error("not a valid IP: 999.1.1.1"),
      { status: 400, code: "invalid_ip" }));

    renderLookup();
    const textarea = screen.getByPlaceholderText(/1\.1\.1\.1/i);
    fireEvent.change(textarea, { target: { value: "999.1.1.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Query" }));

    expect(await screen.findByText("The input contains an invalid IP address")).toBeInTheDocument();
    expect(screen.getByText("not a valid IP: 999.1.1.1")).toBeInTheDocument();
  });
});
