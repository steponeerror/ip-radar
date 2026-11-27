import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useBatchRecentlyDone } from "../useBatchRecentlyDone";
import type { BatchState } from "../../api";

// #486 收编本体测试:5s 停留语义(BatchPanel/BatchMiniBar 组件侧各有
// 行为测试钉住效果,本文件钉转换判据与回调时序)。

const b = (state: BatchState["state"]): BatchState => ({ id: "b1", state, done: 1, total: 2 });

describe("useBatchRecentlyDone(#486:停留 ~5s)", () => {
  it("running→done 触发 linger;onStart/onEnd 按窗口首尾各一次", () => {
    vi.useFakeTimers();
    try {
      const onStart = vi.fn();
      const onEnd = vi.fn();
      const { result, rerender } = renderHook(
        ({ batch }) => useBatchRecentlyDone(batch, { onStart, onEnd }),
        { initialProps: { batch: b("running") as BatchState | null } },
      );
      expect(result.current).toBe(false);
      rerender({ batch: b("done") });
      expect(result.current).toBe(true);
      expect(onStart).toHaveBeenCalledTimes(1);
      expect(onEnd).not.toHaveBeenCalled();

      act(() => { vi.advanceTimersByTime(4999); });
      expect(result.current).toBe(true);
      expect(onEnd).not.toHaveBeenCalled();

      act(() => { vi.advanceTimersByTime(1); });
      expect(result.current).toBe(false);
      expect(onEnd).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("冷加载快照已是 done(无 running/paused 前态)不触发", () => {
    const { result } = renderHook(
      ({ batch }) => useBatchRecentlyDone(batch),
      { initialProps: { batch: b("done") as BatchState | null } },
    );
    expect(result.current).toBe(false);
  });

  it("窗口内 batch 再变(新一批开跑)清定时器,linger 保持 true(与抽取前实现一致)", () => {
    vi.useFakeTimers();
    try {
      const { result, rerender } = renderHook(
        ({ batch }) => useBatchRecentlyDone(batch),
        { initialProps: { batch: b("running") as BatchState | null } },
      );
      rerender({ batch: b("done") });
      expect(result.current).toBe(true);
      rerender({ batch: b("running") });
      act(() => { vi.advanceTimersByTime(10000); });
      expect(result.current).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("paused→done 同样触发(暂停后终止/完成也算会话内转换)", () => {
    const { result, rerender } = renderHook(
      ({ batch }) => useBatchRecentlyDone(batch),
      { initialProps: { batch: b("paused") as BatchState | null } },
    );
    rerender({ batch: b("done") });
    expect(result.current).toBe(true);
  });
});
