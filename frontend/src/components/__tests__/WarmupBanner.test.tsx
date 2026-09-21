import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, act } from "@testing-library/react";
import { WarmupBanner } from "../WarmupBanner";
import { WarmingProvider } from "../../warming";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { getDbStatus } from "../../api";

// Task 9:公开查询页不再挂 TaskProvider(管理面收敛 /admin)——横幅退化为
// 静态冷启动提示:标题+提示语,消除依赖任务上下文的进度/重试/失败去抖
// (数据不可得;清除由 WarmingProvider 的 db-status 轮询驱动,~5s 延迟)。

// fake timers 若因断言失败泄漏(afterEach 兜底恢复,防污染后续测试)
afterEach(() => { vi.useRealTimers(); });

vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getDbStatus: vi.fn(),
  };
});

function render(el: React.ReactElement) {
  return renderWithI18n(<WarmingProvider>{el}</WarmingProvider>);
}

describe("WarmupBanner (static public degrade)", () => {
  it("renders nothing when not warming up", async () => {
    (getDbStatus as any).mockResolvedValue({ warming_up: false, total_records: 0 });
    const { container } = render(<WarmupBanner />);
    await act(async () => {});   // flush 挂载首轮 poll 微任务
    expect(container.querySelector("[data-warmup]")).toBeNull();
  });

  it("shows the warming title and hint, with no buttons or progress numbers", async () => {
    (getDbStatus as any).mockResolvedValue({ warming_up: true, total_records: 0 });
    render(<WarmupBanner />);
    expect(await screen.findByText(/building database for the first time/i)).toBeInTheDocument();
    expect(screen.getByText(/keep this page open/i)).toBeInTheDocument();
    // 无任何控件(重试已随任务上下文移除;进度数字不可得)
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/\/\d+ sources/i)).toBeNull();
  });

  it("disappears when the 5s db-status poll flips warming_up to false", async () => {
    vi.useFakeTimers();
    let warming = true;
    (getDbStatus as any).mockImplementation(() =>
      Promise.resolve({ warming_up: warming, total_records: 100 }));
    const { container } = render(<WarmupBanner />);
    // 挂载首查:warming=true → 横幅出现
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(container.querySelector("[data-warmup]")).not.toBeNull();
    // 后端构建完成 → 下一轮轮询(5s)翻 false → 横幅消失
    warming = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(5100); });
    expect(container.querySelector("[data-warmup]")).toBeNull();
  });
});
