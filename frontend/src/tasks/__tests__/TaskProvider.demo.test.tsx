import { describe, it, expect, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getPublicDemo: vi.fn(),
    subscribeTasks: vi.fn(() => () => {}),
    getTasks: vi.fn().mockResolvedValue({ tasks: [], batch: null }),
  };
});

import { TaskProvider } from "../TaskProvider";
import { getPublicDemo, subscribeTasks, getTasks } from "../../api";

describe("TaskProvider in demo mode", () => {
  it("does not subscribe to SSE or fetch snapshot when demo", async () => {
    (getPublicDemo as any).mockResolvedValue(true);
    render(<TaskProvider>{null}</TaskProvider>);
    await waitFor(() => expect(getPublicDemo).toHaveBeenCalled());
    // 给 Promise 微任务一轮落地
    await new Promise((r) => setTimeout(r, 0));
    expect(subscribeTasks).not.toHaveBeenCalled();
    expect(getTasks).not.toHaveBeenCalled();
  });

  it("subscribes normally when not demo", async () => {
    (getPublicDemo as any).mockResolvedValue(false);
    render(<TaskProvider>{null}</TaskProvider>);
    await waitFor(() => expect(subscribeTasks).toHaveBeenCalled());
    expect(getTasks).toHaveBeenCalled();
  });
});
