import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactElement } from "react";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import OpsPage from "../OpsPage";
import { TasksContext, type TasksCtxValue } from "../../tasks/useTasks";
import type { TaskState } from "../../api";
import { renderWithI18n } from "../../test/i18nTestUtils";
import {
  startOpsRound, readOpsLedger, listOpsPrecedents, readOpsPrecedent, exportOpsPrecedents,
} from "../../api";

// P4 admin 第四 tab「运营」(票 #136):渲染面 + 轮次触发 + 台账/判例只读 +
// 导出 + 错误信封可读呈现(不裸抛 code)。裁决包区交互面见
// OpsPackagesSection.test.tsx。任务链面(tasks/logs)经 TasksContext 直供
// ——SSE 装配归 TaskProvider 自有测试。
vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...real,
    startOpsRound: vi.fn(),
    listOpsPackages: vi.fn().mockResolvedValue([]),
    readOpsPackage: vi.fn(),
    readOpsLedger: vi.fn().mockResolvedValue(""),
    listOpsPrecedents: vi.fn().mockResolvedValue([]),
    readOpsPrecedent: vi.fn(),
    postOpsRuling: vi.fn(),
    exportOpsPrecedents: vi.fn(),
  };
});

const LEDGER_MD = [
  "# 运营轮次台账",
  "",
  "| 日期 | 轮次 | model | 用量 | 备注 |",
  "|---|---|---|---|---|",
  "| 2026-10-20 | discover | glm-4.7 | in=1 out=2 | ok |",
].join("\n");

function wrapCtx(overrides: Partial<TasksCtxValue>, ui: ReactElement): ReactElement {
  const ctx: TasksCtxValue = {
    tasks: [], batch: null, connection: "connected",
    enqueueSingle: vi.fn(), enqueueBatch: vi.fn(), cancelTask: vi.fn(),
    cancelBatch: vi.fn(), pause: vi.fn(), resume: vi.fn(),
    logs: {}, ...overrides,
  };
  return <TasksContext.Provider value={ctx}>{ui}</TasksContext.Provider>;
}

function renderOps(overrides: Partial<TasksCtxValue> = {}) {
  const { rerender, ...rest } = renderWithI18n(
    wrapCtx(overrides, <OpsPage onUnauthorized={vi.fn()} />),
  );
  return {
    ...rest,
    rerenderOps: (next: Partial<TasksCtxValue>) =>
      rerender(wrapCtx(next, <OpsPage onUnauthorized={vi.fn()} />)),
  };
}

const opsTask = (state: TaskState["state"]): TaskState => ({
  id: "t1", source: "ops", host: null, state, error: null, batch_id: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(readOpsLedger).mockResolvedValue(LEDGER_MD);
  vi.mocked(listOpsPrecedents).mockResolvedValue(["2026-10-18-a-case.md"]);
});

describe("OpsPage — sections & read-only faces", () => {
  it("renders all five deliverables + 裁⑦ 仅立项 disclaimer", async () => {
    renderOps();
    expect(screen.getByRole("heading", { name: "Rounds" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Ruling packages" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Ledger (read-only)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Precedents (read-only)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export precedents (.zip)" })).toBeTruthy();
    expect(screen.getByText(/Proposals only/i)).toBeTruthy();
  });

  it("ledger renders as a read-only table (header + rows, no markdown separators)", async () => {
    renderOps();
    await waitFor(() => expect(screen.getByRole("cell", { name: "2026-10-20" })).toBeTruthy());
    expect(screen.getByRole("cell", { name: "discover" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "轮次" })).toBeTruthy();
    expect(screen.queryByText(/^-{3,}$/)).toBeNull();
  });

  it("precedent list renders names; search box drives kws query; detail opens read-only", async () => {
    vi.mocked(readOpsPrecedent).mockResolvedValue("# 判例:人裁同意\n\nfrontmatter…\n");
    renderOps();
    const item = await screen.findByRole("button", { name: "2026-10-18-a-case.md" });
    fireEvent.click(item);
    expect(vi.mocked(readOpsPrecedent)).toHaveBeenCalledWith("2026-10-18-a-case.md");
    expect(await screen.findByText(/# 判例:人裁同意/)).toBeTruthy();
    // 关弹窗(Base UI 对话框会把背景置 inert,不关则背景不可查)
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    // 检索:kws 输入 → listOpsPrecedents(kws)
    fireEvent.change(screen.getByRole("searchbox", { name: /keywords/i }), {
      target: { value: "sunset mirror" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(vi.mocked(listOpsPrecedents)).toHaveBeenCalledWith("sunset mirror"));
  });

  it("export button downloads the zip blob", async () => {
    const createObjectURL = vi.fn(() => "blob:mock");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    vi.mocked(exportOpsPrecedents).mockResolvedValue(new Blob(["zip"]));
    renderOps();
    fireEvent.click(await screen.findByRole("button", { name: "Export precedents (.zip)" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(vi.mocked(exportOpsPrecedents)).toHaveBeenCalled();
  });
});

describe("OpsPage — round trigger panel", () => {
  it("health is one click → startOpsRound('health', non-empty input)", async () => {
    vi.mocked(startOpsRound).mockResolvedValue({ task_id: "t1" });
    renderOps();
    fireEvent.click(screen.getByRole("button", { name: "Run health round" }));
    await waitFor(() => expect(vi.mocked(startOpsRound)).toHaveBeenCalledWith("health", expect.any(String)));
    const input = vi.mocked(startOpsRound).mock.calls[0][1];
    expect(input.trim().length).toBeGreaterThan(0);
  });

  it("discover sends the typed input; empty input → readable hint, no call", async () => {
    vi.mocked(startOpsRound).mockResolvedValue({ task_id: "t2" });
    renderOps();
    fireEvent.click(screen.getByRole("button", { name: "Run discover round" }));
    expect(screen.getByText(/Round input must not be empty/i)).toBeTruthy();
    expect(vi.mocked(startOpsRound)).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("searchbox", { name: /discover input/i }), {
      target: { value: "threatview_c2 直连候选" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run discover round" }));
    await waitFor(() => expect(vi.mocked(startOpsRound)).toHaveBeenCalledWith("discover", "threatview_c2 直连候选"));
  });

  it("409 eval_busy envelope → readable lane-busy text, raw code never shown", async () => {
    vi.mocked(startOpsRound).mockRejectedValue(Object.assign(new Error("an ops round is already in flight"), {
      status: 409, code: "eval_busy",
    }));
    renderOps();
    fireEvent.click(screen.getByRole("button", { name: "Run health round" }));
    await waitFor(() => expect(screen.getByText(/serial lane is busy/i)).toBeTruthy());
    expect(screen.queryByText(/eval_busy/)).toBeNull();
  });

  it("running round: state badge + task_log lines; failed round: readable envelope-code text + message", async () => {
    const { rerenderOps } = renderOps({
      tasks: [opsTask("running")],
      logs: { t1: ["[turn 1] stopReason=end", "[tool] search_precedents"] },
    });
    expect(screen.getByText("Running")).toBeTruthy();
    expect(screen.getByText("[turn 1] stopReason=end")).toBeTruthy();

    const failed = {
      ...opsTask("failed"), error: "模型失败面 stopReason=error", error_code: "model_face",
    } as TaskState;
    rerenderOps({ tasks: [failed], logs: {} });
    expect(screen.getByText(/Model provider failed/i)).toBeTruthy();
    expect(screen.getByText(/模型失败面 stopReason=error/)).toBeTruthy();
  });
});
