import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { TaskProvider } from "../TaskProvider";
import { useTasks } from "../useTasks";

// P2 新 SSE 面(票 #134 产、P4 票 #136 消费):任务态 running(ops 轮相位)
// 与事件 task_log(stderr [turn]/[tool] 行透传)。期望形状 = backend
// ipdb/_tasks.py:start_ops_round(state="running", source="ops")与
// ops_log(emit {"type":"task_log","task_id","line"})。
function Probe() {
  const t = useTasks();
  const lines = Object.values(t.logs).flat();
  return (
    <div>
      <span data-testid="count">{t.tasks.length}</span>
      <span data-testid="state">{t.tasks[0]?.state ?? "-"}</span>
      <span data-testid="logs">{lines.join("|")}</span>
    </div>
  );
}

function makeFakeEventSource() {
  let onMessage: ((m: { data: string }) => void) | null = null;
  function FakeEventSource(this: { close: () => void }) {
    this.close = () => {};
    Object.defineProperty(this, "onmessage", {
      get: () => onMessage,
      set: (v) => { onMessage = v; },
      configurable: true,
    });
  }
  return {
    FakeEventSource,
    fireMessage: (data: unknown) => {
      onMessage?.({ data: JSON.stringify(data) });
    },
  };
}

describe("TaskProvider ops SSE face (running state + task_log)", () => {
  beforeEach(() => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ tasks: [], batch: null }),
    });
    (globalThis as { fetch?: unknown }).fetch = fetchMock;
  });

  it("keeps a running-state ops task (source='ops') in tasks", async () => {
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    render(<TaskProvider><Probe /></TaskProvider>);
    await screen.findByText("0");
    await act(async () => {
      es.fireMessage({
        type: "task",
        task: { id: "t1", source: "ops", host: null, state: "running", error: null, batch_id: null },
      });
    });
    expect(screen.getByTestId("count").textContent).toBe("1");
    expect(screen.getByTestId("state").textContent).toBe("running");
  });

  it("appends task_log lines per task id", async () => {
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    render(<TaskProvider><Probe /></TaskProvider>);
    await screen.findByText("0");
    await act(async () => {
      es.fireMessage({
        type: "task",
        task: { id: "t1", source: "ops", host: null, state: "running", error: null, batch_id: null },
      });
    });
    await act(async () => {
      es.fireMessage({ type: "task_log", task_id: "t1", line: "[turn 1] stopReason=end usage(in=10 out=2)" });
      es.fireMessage({ type: "task_log", task_id: "t1", line: "[tool] search_precedents 命中 3" });
    });
    expect(screen.getByTestId("logs").textContent)
      .toBe("[turn 1] stopReason=end usage(in=10 out=2)|[tool] search_precedents 命中 3");
  });

  it("caps retained log lines per task (progress stream, not an archive)", async () => {
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    render(<TaskProvider><Probe /></TaskProvider>);
    await screen.findByText("0");
    await act(async () => {
      for (let i = 0; i < 205; i++) {
        es.fireMessage({ type: "task_log", task_id: "t1", line: `line-${i}` });
      }
    });
    const text = screen.getByTestId("logs").textContent ?? "";
    expect(text).toContain("line-204");
    expect(text).not.toContain("line-0|");
    expect(text.split("|")).toHaveLength(200);
  });

  it("seeds log lines from a snapshot's logs face (mid-round page open, 2026-10-26 fix)", async () => {
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    render(<TaskProvider><Probe /></TaskProvider>);
    await screen.findByText("0");
    await act(async () => {
      es.fireMessage({
        type: "snapshot",
        data: {
          tasks: [{ id: "t1", source: "ops", host: null, state: "running", error: null, batch_id: null }],
          batch: null,
          logs: { t1: ["[stage] PROBE start", "[stage] TRIAGE start"] },
        },
      });
    });
    expect(screen.getByTestId("logs").textContent)
      .toBe("[stage] PROBE start|[stage] TRIAGE start");
    // 播种后后续 task_log 照常追加在尾之后(同一条 append-only 流)
    await act(async () => {
      es.fireMessage({ type: "task_log", task_id: "t1", line: "[stage] TRIAGE done gate=PASS" });
    });
    expect(screen.getByTestId("logs").textContent)
      .toBe("[stage] PROBE start|[stage] TRIAGE start|[stage] TRIAGE done gate=PASS");
  });

  it("snapshot seeding never shrinks already-received lines (fetch/SSE race)", async () => {
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    render(<TaskProvider><Probe /></TaskProvider>);
    await screen.findByText("0");
    await act(async () => {
      es.fireMessage({
        type: "snapshot",
        data: {
          tasks: [{ id: "t1", source: "ops", host: null, state: "running", error: null, batch_id: null }],
          batch: null,
          logs: { t1: ["only-one-stale-line"] },
        },
      });
      es.fireMessage({ type: "task_log", task_id: "t1", line: "l0" });
      es.fireMessage({ type: "task_log", task_id: "t1", line: "l1" });
      es.fireMessage({ type: "task_log", task_id: "t1", line: "l2" });
      // 竞态回放:更短的旧快照尾再来 → 已收 3 行不缩水
      es.fireMessage({
        type: "snapshot",
        data: {
          tasks: [{ id: "t1", source: "ops", host: null, state: "running", error: null, batch_id: null }],
          batch: null,
          logs: { t1: ["stale-again"] },
        },
      });
    });
    expect(screen.getByTestId("logs").textContent).toBe("only-one-stale-line|l0|l1|l2");
  });
});
