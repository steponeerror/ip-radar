import { describe, it, expect, vi } from "vitest";
import { screen, act } from "@testing-library/react";
import { BatchMiniBar } from "../BatchMiniBar";
import { TaskProvider } from "../../tasks/TaskProvider";
import { renderWithI18n } from "../../test/i18nTestUtils";
import type { TaskEvent } from "../../api";
import { getTasks } from "../../api";

// #486:迷你条的「刚完成停留 5s」此前无专测(逻辑与 BatchPanel 各抄一份,
// 现收编在 useBatchRecentlyDone);写法照 BatchPanel.test.tsx 那两条。

// Hoisted holder so the (also hoisted) vi.mock factory can capture the SSE
// onEvent callback (同 BatchPanel.test.tsx 的驱动方式)。
const sse = vi.hoisted(() => ({
  onEvent: null as ((e: TaskEvent) => void) | null,
}));

vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...real,
    getTasks: vi.fn().mockResolvedValue({
      tasks: [{ id: "t1", source: "feodo", host: null, state: "downloading", error: null, batch_id: "b1" }],
      batch: { id: "b1", state: "running", done: 0, total: 2 },
    }),
    subscribeTasks: vi.fn((onEvent: (e: TaskEvent) => void) => {
      sse.onEvent = onEvent;
      return () => {};
    }),
  };
});

function render(el: React.ReactElement) {
  return renderWithI18n(<TaskProvider>{el}</TaskProvider>);
}

describe("BatchMiniBar linger(#486:停留收编后仍要钉住)", () => {
  it("lingers ~5s after running→done, then disappears", async () => {
    render(<BatchMiniBar onOpen={() => {}} />);
    // running:bar 常驻(live)
    expect(await screen.findByText(/Updating 0\/2/)).toBeInTheDocument();

    vi.useFakeTimers();
    try {
      // Drive SSE:任务全部完成 + batch done。
      await act(async () => {
        sse.onEvent!({
          type: "snapshot",
          data: {
            tasks: [{ id: "t1", source: "feodo", host: null, state: "done", error: null, batch_id: "b1" }],
            batch: { id: "b1", state: "done", done: 2, total: 2 },
          },
        });
      });
      // done 不 live,但 linger 窗口内 bar 仍在(终态可见)
      expect(screen.getByText(/Done 2\/2/)).toBeInTheDocument();

      // 刚差一点到 5s:仍在
      await act(async () => { vi.advanceTimersByTime(4999); });
      expect(screen.getByText(/Done 2\/2/)).toBeInTheDocument();

      // 过 5s:bar 整体消失(live=false 且 linger=false)
      await act(async () => { vi.advanceTimersByTime(2); });
      expect(screen.queryByText(/Done 2\/2/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does NOT show the bar when the cold snapshot already reports a done batch", async () => {
    vi.mocked(getTasks).mockReset();
    // 后端完成后仍引用该 batch:冷快照直接是 done —— 无 running/paused→done
    // 会话内转换,不得庆祝(每次整页加载都闪终态)。
    vi.mocked(getTasks).mockResolvedValue({
      tasks: [],
      batch: { id: "b1", state: "done", done: 2, total: 2 },
    });
    render(<BatchMiniBar onOpen={() => {}} />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText(/Done 2\/2/)).not.toBeInTheDocument();
  });
});
