import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { DbStatusBar } from "../DbStatusBar";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { getDbStatus } from "../../api";

// Task 9:公开底栏收敛为只读状态(计数/警告/过期,GET /api/db-status 公开);
// 管理控件(Update DB/Retry 与活动面板)移入 /admin 的 BatchPanel。
// 活动面板测试已迁移至 admin/__tests__/BatchPanel.test.tsx(update-not-delete)。

vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getDbStatus: vi.fn().mockResolvedValue({
      last_updated: "2026-09-21T00:00:00Z", total_records: 100,
      scalar_records: 60, threat_records: 30, asset_records: 10,
      is_stale: false, warming_up: false, warnings: [],
    }),
  };
});

describe("DbStatusBar read-only public bar", () => {
  it("renders record counts and updated time, with NO Update button", async () => {
    renderWithI18n(<DbStatusBar />);
    expect(await screen.findByText(/100 records/i)).toBeInTheDocument();
    expect(screen.getByText(/60 scalar/i)).toBeInTheDocument();
    expect(screen.getByText(/30 threat/i)).toBeInTheDocument();
    expect(screen.getByText(/10 asset/i)).toBeInTheDocument();
    // 管理按钮已移入 /admin(POST /api/update-db 超管门)
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders the stale marker when the database is stale", async () => {
    vi.mocked(getDbStatus).mockResolvedValueOnce({
      last_updated: "2026-09-01T00:00:00Z", total_records: 1,
      scalar_records: 1, threat_records: 0, asset_records: 0,
      is_stale: true, warming_up: false, warnings: [],
    });
    renderWithI18n(<DbStatusBar />);
    expect(await screen.findByText(/\(stale\)/i)).toBeInTheDocument();
  });

  it("renders a warning bar (no Retry button) when db-status reports warnings", async () => {
    vi.mocked(getDbStatus).mockResolvedValueOnce({
      last_updated: "2026-09-21T00:00:00Z", total_records: 100,
      scalar_records: 60, threat_records: 30, asset_records: 10,
      is_stale: false, warming_up: false, warnings: ["feodo stale", "tor failed"],
    });
    renderWithI18n(<DbStatusBar />);
    expect(await screen.findByText(/feodo stale; tor failed/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders the error bar (no Retry button) when db-status fails entirely", async () => {
    vi.mocked(getDbStatus).mockRejectedValueOnce(new Error("network down"));
    renderWithI18n(<DbStatusBar />);
    // 错误文案优先信封 message(e.message),与旧行为一致
    expect(await screen.findByText(/network down/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders nothing before the first db-status response lands", () => {
    vi.mocked(getDbStatus).mockReturnValueOnce(new Promise(() => {}));
    const { container } = renderWithI18n(<DbStatusBar />);
    expect(container.textContent).toBe("");
    waitFor(() => {});
  });
});
