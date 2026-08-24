import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { DbStatusBar } from "../DbStatusBar";
import { TaskProvider } from "../../tasks/TaskProvider";
import { renderWithI18n } from "../../test/i18nTestUtils";

vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getDbStatus: vi.fn().mockResolvedValue({
      last_updated: "", record_count: 0, cn_record_count: 0, total_records: 1,
      asset_records: 0, scalar_records: 0, threat_records: 0, is_stale: false,
    }),
    getPublicDemo: vi.fn().mockResolvedValue(true),
    getTasks: vi.fn().mockResolvedValue({ tasks: [], batch: null }),
    subscribeTasks: vi.fn(() => () => {}),
  };
});

describe("DbStatusBar in demo mode", () => {
  it("hides the update button", async () => {
    renderWithI18n(
      <TaskProvider>
        <DbStatusBar />
      </TaskProvider>,
    );
    // 等待状态条渲染完成——实际 i18n 文案为 "Updated {time}"(brief 预授权的查询方式调整)
    await waitFor(() =>
      expect(screen.getByText(/updated/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
