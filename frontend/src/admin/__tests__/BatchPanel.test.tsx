import { describe, it, expect, vi } from "vitest";
import { screen, waitFor, fireEvent, act } from "@testing-library/react";
import { BatchPanel } from "../BatchPanel";
import { TaskProvider } from "../../tasks/TaskProvider";
import { renderWithI18n } from "../../test/i18nTestUtils";
import type { TaskEvent, TaskState } from "../../api";
import {
  pauseBatch, cancelBatch, cancelTask, getTasks, resumeBatch,
} from "../../api";

// Task 9:DbStatusBar 的活动面板(批量进度/暂停/恢复/终止/逐任务取消)整体
// 迁入 /admin 任务区(BatchPanel)。本文件 = 原 DbStatusBar 活动面板测试的
// 迁移(update-not-delete),外加「完成后 5s 收起」改为面板自身消失。

// Hoisted holder so the (also hoisted) vi.mock factory can capture the SSE
// callbacks (onEvent / onReconnect / onDisconnect — U8) and tests can drive
// events + connection-state transitions through them.
const sse = vi.hoisted(() => ({
  onEvent: null as ((e: TaskEvent) => void) | null,
  onReconnect: null as (() => void) | null,
  onDisconnect: null as (() => void) | null,
}));

vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...real,
    getDbStatus: vi.fn().mockResolvedValue({
      last_updated: "", record_count: 0, cn_record_count: 0, total_records: 100,
      scalar_records: 60, threat_records: 30, asset_records: 10, is_stale: false,
    }),
    getTasks: vi.fn().mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: "b1" }],
      batch: { id: "b1", state: "running", done: 0, total: 2 },
    }),
    subscribeTasks: vi.fn((
      onEvent: (e: TaskEvent) => void,
      onReconnect?: () => void,
      _onSessionDead?: () => void,
      onDisconnect?: () => void,
    ) => {
      sse.onEvent = onEvent;
      sse.onReconnect = onReconnect ?? null;
      sse.onDisconnect = onDisconnect ?? null;
      return () => {};
    }),
    enqueueBatch: vi.fn().mockResolvedValue({ batch_id: "b1" }),
    cancelTask: vi.fn().mockResolvedValue(undefined),
    cancelBatch: vi.fn().mockResolvedValue(undefined),
    pauseBatch: vi.fn().mockResolvedValue(undefined),
    resumeBatch: vi.fn().mockResolvedValue(undefined),
  };
});

function render(el: React.ReactElement) {
  return renderWithI18n(<TaskProvider>{el}</TaskProvider>);
}

describe("BatchPanel active panel", () => {
  it("shows overall pct and a per-source row when batch active", async () => {
    render(<BatchPanel />);
    expect(await screen.findByText(/feodo/)).toBeInTheDocument();
    expect(screen.getByText(/0\/2/)).toBeInTheDocument();
  });

  it("shows empty-state guidance when idle (no active tasks, no batch)", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({ tasks: [], batch: null });
    render(<BatchPanel />);
    await act(async () => {
      await waitFor(() => expect(getTasks).toHaveBeenCalled());
    });
    // idle → 不再留白:引导文案在场(任务 tab 死页既视感修复)
    expect(screen.getByText(/no background tasks/i)).toBeInTheDocument();
  });

  it("calls pauseBatch when Pause is clicked", async () => {
    render(<BatchPanel />);
    const pauseBtn = await screen.findByRole("button", { name: /Pause/i });
    fireEvent.click(pauseBtn);
    await waitFor(() => expect(pauseBatch).toHaveBeenCalled());
  });

  it("calls resumeBatch when Resume is clicked (paused batch)", async () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: "b1" }],
      batch: { id: "b1", state: "paused", done: 1, total: 2 },
    });
    render(<BatchPanel />);
    const resumeBtn = await screen.findByRole("button", { name: /Resume/i });
    fireEvent.click(resumeBtn);
    await waitFor(() => expect(resumeBatch).toHaveBeenCalled());
  });

  it("calls cancelBatch when Abort is clicked", async () => {
    render(<BatchPanel />);
    const abortBtn = await screen.findByRole("button", { name: /Abort/i });
    fireEvent.click(abortBtn);
    await waitFor(() => expect(cancelBatch).toHaveBeenCalled());
  });

  it("calls cancelTask with id when per-row ✕ is clicked", async () => {
    render(<BatchPanel />);
    const rowCancel = await screen.findByRole("button", { name: /Cancel feodo/i });
    fireEvent.click(rowCancel);
    await waitFor(() => expect(cancelTask).toHaveBeenCalledWith("t1"));
  });
});

// U7:控制端点(暂停/恢复/终止/逐任务取消)非 ok 现 reject;面板必须给反馈
describe("BatchPanel control-action failure feedback (U7)", () => {
  // 模块级 mock 跨测试残留:每个用例显式重置为 running batch(同前述用例惯例)
  const setRunning = () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: "b1" }],
      batch: { id: "b1", state: "running", done: 0, total: 2 },
    });
  };

  it("shows the error when a control action rejects; a later action clears it", async () => {
    setRunning();
    vi.mocked(cancelBatch).mockRejectedValueOnce(new Error("task manager unavailable"));
    render(<BatchPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Abort/i }));
    expect(await screen.findByText(/task manager unavailable/i)).toBeInTheDocument();
    // 第二击走默认 resolved mock → 新动作先清旧错(openCreate 同款语义)
    fireEvent.click(screen.getByRole("button", { name: /Abort/i }));
    await waitFor(() => expect(screen.queryByText(/task manager unavailable/i)).toBeNull());
  });

  it("kicks to login on 401 instead of showing a dead-end banner", async () => {
    setRunning();
    const e = new Error("Not authenticated") as Error & { status?: number };
    e.status = 401;
    vi.mocked(pauseBatch).mockRejectedValueOnce(e);
    const onUnauthorized = vi.fn();
    render(<BatchPanel onUnauthorized={onUnauthorized} />);
    fireEvent.click(await screen.findByRole("button", { name: /Pause/i }));
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/Not authenticated/i)).toBeNull();
  });
});

describe("BatchPanel collapse on done", () => {
  it("lingers ~5s after batch done, then collapses away", async () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: "b1" }],
      batch: { id: "b1", state: "running", done: 0, total: 2 },
    });

    render(<BatchPanel />);
    // Active panel visible — running batch shows 0/2 progress.
    expect(await screen.findByText(/0\/2/)).toBeInTheDocument();

    // Switch to fake timers to control the 5s collapse deterministically.
    vi.useFakeTimers();
    try {
      // Drive SSE: tasks all finished + batch done.
      await act(async () => {
        sse.onEvent!({
          type: "snapshot",
          data: {
            tasks: [{ id: "t1", source: "feodo", host: null, state: "done", error: null, batch_id: "b1" }],
            batch: { id: "b1", state: "done", done: 2, total: 2 },
          },
        });
      });
      // 2/2 visible — panel lingers to show the finished state.
      expect(screen.getByText(/2\/2/)).toBeInTheDocument();

      // Just under the 5s threshold — still lingering.
      await act(async () => { vi.advanceTimersByTime(4999); });
      expect(screen.getByText(/2\/2/)).toBeInTheDocument();

      // Cross the 5s threshold — panel collapses entirely.
      await act(async () => { vi.advanceTimersByTime(2); });
      expect(screen.queryByText(/2\/2/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("BatchPanel cold-load with stale done batch", () => {
  it("does NOT pop the active panel when the snapshot already reports a done batch", async () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    // Backend keeps _active_batch pointing at a finished batch, so the cold
    // snapshot reports batch.state === "done". This must NOT re-trigger the
    // 5s "recently done" celebration on every admin page load.
    mockGetTasks.mockResolvedValue({
      tasks: [],
      batch: { id: "b1", state: "done", done: 2, total: 2 },
    });
    render(<BatchPanel />);
    await act(async () => {
      await waitFor(() => expect(getTasks).toHaveBeenCalled());
      await mockGetTasks.mock.results[0].value;   // resolved snapshot
      await Promise.resolve();                     // flush setBatch + effect
    });
    expect(screen.queryByText(/2\/2/)).not.toBeInTheDocument();
    // idle → 不再留白(任务 tab 死页既视感),给引导文案
    expect(screen.getByText(/no background tasks/i)).toBeInTheDocument();
  });
});

describe("BatchPanel batchless update hides stale tasks", () => {
  it("shows only the active batchless task, not terminal tasks from prior batches", async () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    // After a batch finished, _tasks still holds its terminal tasks. A later
    // single-source update runs batchless (batch_id null, batch null). The panel
    // must show ONLY the active task, not the stale failed/done ones.
    mockGetTasks.mockResolvedValue({
      tasks: [
        { id: "t1", source: "abuseipdb", host: null, state: "failed", error: "429", batch_id: "old" },
        { id: "t2", source: "dataplane", host: null, state: "done", error: null, batch_id: "old" },
        { id: "t3", source: "ip2proxy", host: null, state: "loading", error: null, batch_id: null },
      ],
      batch: null,
    });
    render(<BatchPanel />);
    expect(await screen.findByText(/ip2proxy/)).toBeInTheDocument();
    expect(screen.queryByText(/abuseipdb/)).not.toBeInTheDocument();
    expect(screen.queryByText(/dataplane/)).not.toBeInTheDocument();
  });
});

// U4:状态徽章与 aria-label 全 i18n 化 —— zh 下不得再有英文枚举直出
describe("BatchPanel task-state badge i18n (U4)", () => {
  const setRunning = (states: { id: string; source: string; state: TaskState["state"] }[]) => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({
      tasks: states.map((s) => ({ ...s, host: null, error: null, batch_id: "b1" })),
      batch: { id: "b1", state: "running", done: 0, total: states.length },
    });
  };

  it("renders zh badge copy for loading/failed, never the raw enum", async () => {
    setRunning([
      { id: "t1", source: "otx", state: "loading" },
      { id: "t2", source: "spamhaus", state: "failed" },
    ]);
    renderWithI18n(<TaskProvider><BatchPanel /></TaskProvider>, { locale: "zh-CN" });
    expect(await screen.findByText("载入中")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.queryByText("loading")).not.toBeInTheDocument();
    expect(screen.queryByText("failed")).not.toBeInTheDocument();
  });

  it("localizes the per-row cancel aria-label", async () => {
    setRunning([{ id: "t1", source: "feodo", state: "downloading" }]);
    renderWithI18n(<TaskProvider><BatchPanel /></TaskProvider>, { locale: "zh-CN" });
    expect(await screen.findByRole("button", { name: "取消 feodo" })).toBeInTheDocument();
  });
});

describe("BatchPanel batchless single-task", () => {
  it("shows Updating label without 0/0 when active task has no batch", async () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: null }],
      batch: null,
    });
    render(<BatchPanel />);
    expect(await screen.findByText(/feodo/)).toBeInTheDocument();
    // Batchless header: no misleading 0/0 · 0% suffix.
    expect(screen.queryByText(/0\/0/)).not.toBeInTheDocument();
  });
});

describe("BatchPanel 分段进度渲染", () => {
  it("loading 行显示行数细节与百分比;头部取平均", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({
      tasks: [
        { id: "t1", source: "otx", host: null, state: "loading", error: null,
          batch_id: "b1", received: 2_100_000, total: 3_400_000 },
        { id: "t2", source: "feodo", host: null, state: "done", error: null,
          batch_id: "b1" },
      ],
      batch: { id: "b1", state: "running", done: 1, total: 2 },
    });
    render(<BatchPanel />);
    expect(await screen.findByText(/2\.1M\/3\.4M/)).toBeInTheDocument();
    expect(screen.getByText("81%")).toBeInTheDocument();      // 单任务列(exact:头部是 90%)
    expect(screen.getByText(/90%/)).toBeInTheDocument();      // 头部 mean(1, .8088)
  });

  it("未知 total 的 loading 显示 --% 与行数(无分母)", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({
      tasks: [{ id: "t1", source: "ip2proxy", host: null, state: "loading",
        error: null, batch_id: "b1", received: 1_500_000 }],
      batch: { id: "b1", state: "running", done: 0, total: 1 },
    });
    render(<BatchPanel />);
    expect(await screen.findByText("--%")).toBeInTheDocument();
    expect(screen.getByText(/1\.5M/)).toBeInTheDocument();
  });

  it("downloading→loading 转换序列无倒退(50→50→100)", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({
      tasks: [{ id: "t1", source: "otx", host: null, state: "downloading",
        error: null, batch_id: "b1", received: 100, total: 100 }],
      batch: { id: "b1", state: "running", done: 0, total: 1 },
    });
    render(<BatchPanel />);
    // exact "50%" 只命中行 span(头部全串更长);此后行变 --%,改用 regex 验头部不倒退
    expect(await screen.findByText("50%")).toBeInTheDocument();
    act(() => sse.onEvent!({ type: "task", task: { id: "t1", source: "otx",
      host: null, state: "loading", error: null, batch_id: "b1",
      received: 0, total: 0 } }));
    expect(screen.getByText(/50%/)).toBeInTheDocument();      // 未知窗口=段起点
    expect(screen.queryByText(/75%/)).toBeNull();            // 无中点跳变
    act(() => sse.onEvent!({ type: "task_progress", task_id: "t1",
      received: 3_400_000, total: 3_400_000 }));
    expect(await screen.findByText("100%")).toBeInTheDocument();
  });

  it("failed 行冻结百分比且红条满宽", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({
      tasks: [{ id: "t1", source: "spamhaus", host: null, state: "failed",
        error: "boom", batch_id: "b1", frozenFrac: 0.2 }],
      batch: { id: "b1", state: "running", done: 0, total: 1 },
    });
    render(<BatchPanel />);
    expect(await screen.findByText("20%")).toBeInTheDocument();
    const bar = document.querySelector(".bg-red-500");
    expect(bar?.className).toContain("w-full");
  });

  it("resync 后无 frozenFrac 的 failed 行显示 --% 而非假 0%", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({
      tasks: [{ id: "t1", source: "otx", host: null, state: "failed",
        error: "boom", batch_id: "b1", received: 700, total: 1000 }],
      batch: { id: "b1", state: "running", done: 0, total: 1 },
    });
    render(<BatchPanel />);
    expect(await screen.findByText("--%")).toBeInTheDocument();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("fmtRows 边界:四舍五入达 1000K 晋升为 M", async () => {
    vi.mocked(getTasks).mockResolvedValueOnce({
      tasks: [{ id: "t1", source: "otx", host: null, state: "loading",
        error: null, batch_id: "b1", received: 999_449, total: 999_999 }],
      batch: { id: "b1", state: "running", done: 0, total: 1 },
    });
    render(<BatchPanel />);
    expect(await screen.findByText(/999K\/1\.0M/)).toBeInTheDocument();
  });
});

// U8:SSE 断线指示 —— onerror(既有事件路径)置位 → amber「重连中」横幅;
// onopen 恢复自动清。语义与 U7 红字终态失败区分(瞬态 vs 终态)。
describe("BatchPanel SSE disconnect banner (U8)", () => {
  const setRunning = () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: "b1" }],
      batch: { id: "b1", state: "running", done: 0, total: 2 },
    });
  };

  it("active batch 断线 → 重连横幅出现;恢复 → 自动消失(不再冻结无提示)", async () => {
    setRunning();
    render(<BatchPanel />);
    expect(await screen.findByText(/feodo/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull(); // 断线前无横幅
    await act(async () => { sse.onDisconnect?.(); });   // onerror → reconnecting
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(/reconnecting/i);
    await act(async () => { sse.onReconnect?.(); });    // onopen → connected + resync
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    // 恢复后面板仍在(重拉快照后正常展示),而非整面板消失
    expect(await screen.findByText(/feodo/)).toBeInTheDocument();
  });

  it("断线横幅 zh 文案(双语键在场)", async () => {
    setRunning();
    renderWithI18n(<TaskProvider><BatchPanel /></TaskProvider>, { locale: "zh-CN" });
    expect(await screen.findByText(/feodo/)).toBeInTheDocument();
    await act(async () => { sse.onDisconnect?.(); });
    expect(await screen.findByText("连接中断，重连中…")).toBeInTheDocument();
  });

  it("idle 断线 → 空态引导让位给断线横幅(不再谎报「没有后台任务」)", async () => {
    const mockGetTasks = vi.mocked(getTasks);
    mockGetTasks.mockReset();
    mockGetTasks.mockResolvedValue({ tasks: [], batch: null });
    render(<BatchPanel />);
    expect(await screen.findByText(/no background tasks/i)).toBeInTheDocument();
    await act(async () => { sse.onDisconnect?.(); });
    expect(screen.queryByText(/no background tasks/i)).toBeNull();
    expect(await screen.findByRole("status")).toHaveTextContent(/reconnecting/i);
  });
});
