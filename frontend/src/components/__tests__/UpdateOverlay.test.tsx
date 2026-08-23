import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, act } from "@testing-library/react";
import { UpdateOverlay } from "../UpdateOverlay";
import { renderWithI18n } from "../../test/i18nTestUtils";
import * as api from "../../api";

// renderWithI18n 默认 en locale;沿用 VersionBanner.test 的 importActual mock 风格
vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getVersion: vi.fn(),
    postUpdate: vi.fn(),
    getUpdateStatus: vi.fn(),
  };
});

const info = (current: string): api.VersionInfo => ({
  current, latest: "v1.2.0", update_available: true,
  summary: null, release_url: "u", self_update_enabled: true,
});

describe("UpdateOverlay flow", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.getVersion).mockReset();
    vi.mocked(api.postUpdate).mockReset();
    vi.mocked(api.getUpdateStatus).mockReset();
  });
  afterEach(() => { vi.useRealTimers(); });

  it("polls until version changes then reloads", async () => {
    let n = 0;
    vi.mocked(api.getVersion).mockImplementation(async () => info(n++ >= 1 ? "v1.2.0" : "v1.1.0"));
    vi.mocked(api.getUpdateStatus).mockResolvedValue({ state: "updating", error: null, at: null });
    const reload = vi.fn();
    renderWithI18n(<UpdateOverlay active startedVersion="v1.1.0" reload={reload} />);
    // t=0 → current 仍 v1.1.0;t=3s → v1.2.0 → reload。真定时器,留足余量。
    await vi.waitFor(() => expect(reload).toHaveBeenCalled(), { timeout: 5000 });
  });

  it("shows failure + retry after backend reports failed", async () => {
    // 服务死了(getVersion 拒绝)且后端状态 failed → 失败早浮现(~3-6s),不等 5 分钟超时
    vi.mocked(api.getVersion).mockRejectedValue(new Error("down"));
    vi.mocked(api.getUpdateStatus).mockResolvedValue({ state: "failed", error: "git conflict", at: "T" });
    renderWithI18n(<UpdateOverlay active startedVersion="v1.1.0" reload={vi.fn()} />);
    await vi.waitFor(() =>
      expect(screen.getByText(/git conflict/)).toBeTruthy(), { timeout: 8000 });
    expect(screen.getByRole("button", { name: /Retry/i })).toBeTruthy();
  });

  it("keeps polling while service down and status=updating", async () => {
    vi.useFakeTimers();
    vi.mocked(api.getVersion).mockRejectedValue(new Error("down"));
    vi.mocked(api.getUpdateStatus).mockResolvedValue({ state: "updating", error: null, at: null });
    renderWithI18n(<UpdateOverlay active startedVersion="v1.1.0" reload={vi.fn()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    // t=0,3s,6s,9s 共 4 轮;无失败文案,spinner 态持续
    expect(api.getVersion).toHaveBeenCalledTimes(4);
    expect(screen.queryByText(/may have failed/i)).toBeNull();
    expect(screen.getByText(/Updating IP Radar/i)).toBeTruthy();
  });
});
