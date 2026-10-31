import { describe, it, expect } from "vitest";
import { stagedFrac, isIndeterminate, isTaskTerminal, isTaskActive, isBatchLive } from "../progress";
import type { BatchState, TaskState } from "../../api";

const t = (over: Partial<TaskState>): TaskState => ({
  id: "t1", source: "s", host: null, state: "queued",
  error: null, batch_id: null, ...over,
});

describe("stagedFrac 分段加权", () => {
  it("queued/throttled → 0", () => {
    expect(stagedFrac(t({}))).toBe(0);
    expect(stagedFrac(t({ state: "throttled" }))).toBe(0);
  });

  it("downloading 已知 total → 0.5×比例,含 clamp", () => {
    expect(stagedFrac(t({ state: "downloading", received: 40, total: 100 }))).toBeCloseTo(0.2);
    expect(stagedFrac(t({ state: "downloading", received: 120, total: 100 }))).toBe(0.5);
  });

  it("downloading 未知 total → 0.25", () => {
    expect(stagedFrac(t({ state: "downloading", received: 40, total: 0 }))).toBe(0.25);
    expect(stagedFrac(t({ state: "downloading" }))).toBe(0.25);
  });

  it("loading 已知 total → 0.5+0.5×比例", () => {
    expect(stagedFrac(t({ state: "loading", received: 0, total: 100 }))).toBe(0.5);
    expect(stagedFrac(t({ state: "loading", received: 100, total: 100 }))).toBe(1);
  });

  it("loading 未知 total → 0.5(段起点,单调关键)", () => {
    expect(stagedFrac(t({ state: "loading", received: 50, total: 0 }))).toBe(0.5);
  });

  it("done → 1;终态读 frozenFrac,缺省 0", () => {
    expect(stagedFrac(t({ state: "done" }))).toBe(1);
    expect(stagedFrac(t({ state: "failed", frozenFrac: 0.2 }))).toBe(0.2);
    expect(stagedFrac(t({ state: "cancelled" }))).toBe(0);
  });

  it("downloading 完成→loading 起点无下跳", () => {
    const dl = stagedFrac(t({ state: "downloading", received: 100, total: 100 }));
    const ldUnknown = stagedFrac(t({ state: "loading", total: 0 }));
    const ldZero = stagedFrac(t({ state: "loading", received: 0, total: 100 }));
    expect(dl).toBe(0.5);
    expect(ldUnknown).toBe(0.5);
    expect(ldZero).toBe(0.5);
  });
});

describe("isIndeterminate", () => {
  it("活跃相位且无 total 才是不确定", () => {
    expect(isIndeterminate(t({ state: "downloading" }))).toBe(true);
    expect(isIndeterminate(t({ state: "loading", received: 5 }))).toBe(true);
    expect(isIndeterminate(t({ state: "downloading", total: 100 }))).toBe(false);
    expect(isIndeterminate(t({ state: "done" }))).toBe(false);
    expect(isIndeterminate(t({ state: "queued" }))).toBe(false);
  });
});

describe("任务状态谓词(#245 收编,原三处内联散推)", () => {
  it("isTaskTerminal:仅 done/failed/cancelled", () => {
    for (const s of ["done", "failed", "cancelled"] as const)
      expect(isTaskTerminal(t({ state: s }))).toBe(true);
    for (const s of ["queued", "throttled", "downloading", "loading", "running"] as const)
      expect(isTaskTerminal(t({ state: s }))).toBe(false);
  });

  it("isTaskActive:四幂等入队相位;不含 ops 轮 running 与终态", () => {
    for (const s of ["queued", "throttled", "downloading", "loading"] as const)
      expect(isTaskActive(t({ state: s }))).toBe(true);
    for (const s of ["running", "done", "failed", "cancelled"] as const)
      expect(isTaskActive(t({ state: s }))).toBe(false);
  });

  it("isBatchLive:running/paused;done 与 null 不 live", () => {
    const b = (state: BatchState["state"]): BatchState =>
      ({ id: "b1", state, done: 0, total: 3 });
    expect(isBatchLive(b("running"))).toBe(true);
    expect(isBatchLive(b("paused"))).toBe(true);
    expect(isBatchLive(b("done"))).toBe(false);
    expect(isBatchLive(null)).toBe(false);
  });
});
