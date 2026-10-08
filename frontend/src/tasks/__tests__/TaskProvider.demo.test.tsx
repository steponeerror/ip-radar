import { describe, it, expect, vi } from "vitest";
import { render, act, waitFor } from "@testing-library/react";
import { TaskProvider } from "../TaskProvider";

// 三面(D3):①demo=true 挂载也订阅(钉本 bug:public_demo 只认 ADMIN_IPS
// peer 不认 admin cookie,曾误闸管理员);②onerror 探测 adminMe=null →
// 关流 + onUnauthorized;③adminMe 正常 → 不关不踢(交原生重连)。
// 不 mock api 模块 —— 真 subscribeTasks 跑通 onerror → adminMe 链路,
// fetch 按 URL 路由控制各端点行为。

// 仿 EventSource(TaskProvider.test 的 makeFakeEventSource 无 onerror,
// 这里就地扩一版):close/构造可断言,onerror 可从测试侧触发。
function makeFakeEventSource() {
  let onError: (() => void) | null = null;
  const close = vi.fn();
  const constructed = vi.fn();
  function FakeEventSource(this: { close: () => void }) {
    constructed();
    this.close = close;
    Object.defineProperty(this, "onmessage", {
      get: () => null, set: () => {}, configurable: true,
    });
    Object.defineProperty(this, "onopen", {
      get: () => null, set: () => {}, configurable: true,
    });
    Object.defineProperty(this, "onerror", {
      get: () => onError, set: (v) => { onError = v; }, configurable: true,
    });
  }
  return { FakeEventSource, close, constructed, fireError: () => { onError?.(); } };
}

// 按 URL 路由的 fetch stub;未列出的端点兜底返回空快照(getTasks 用)。
function routeFetch(routes: Record<string, () => unknown>) {
  return vi.fn((url: string) => {
    const hit = Object.entries(routes).find(([p]) => String(url).startsWith(p));
    return Promise.resolve(hit ? hit[1]() : { ok: true, json: async () => ({ tasks: [], batch: null }) });
  });
}

describe("TaskProvider on public-demo deployments", () => {
  it("① demo=true 挂载仍 resync + 订阅(public_demo 闸不得误杀管理员)", async () => {
    const fetchMock = routeFetch({
      // 部署形态 = 公开 demo(version 报 public_demo:true);组件已不再
      // 询此端点 —— 订阅必须无条件发生,该 mock 钉住部署上下文。
      "/api/version": () => ({ ok: true, json: async () => ({ public_demo: true }) }),
    });
    (globalThis as { fetch?: unknown }).fetch = fetchMock;
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    render(<TaskProvider>{null}</TaskProvider>);
    await waitFor(() => expect(es.constructed).toHaveBeenCalledTimes(1)); // 已订阅
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/tasks")); // 已 resync
  });

  it("② onerror 探测 adminMe=null → 关 EventSource + onUnauthorized 踢出", async () => {
    const fetchMock = routeFetch({
      "/api/users/me": () => ({ ok: false, status: 401 }), // adminMe → null
    });
    (globalThis as { fetch?: unknown }).fetch = fetchMock;
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    const onUnauthorized = vi.fn();
    render(<TaskProvider onUnauthorized={onUnauthorized}>{null}</TaskProvider>);
    await waitFor(() => expect(es.constructed).toHaveBeenCalled());
    await act(async () => { es.fireError(); });
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
    expect(es.close).toHaveBeenCalledTimes(1); // 断原生重连风暴
  });

  it("③ onerror 探测 adminMe 正常 → 不关不踢(交浏览器原生重连)", async () => {
    const fetchMock = routeFetch({
      "/api/users/me": () => ({ ok: true, json: async () => ({ id: "u1", email: "a@b.c" }) }),
    });
    (globalThis as { fetch?: unknown }).fetch = fetchMock;
    const es = makeFakeEventSource();
    (globalThis as { EventSource?: unknown }).EventSource = es.FakeEventSource;
    const onUnauthorized = vi.fn();
    render(<TaskProvider onUnauthorized={onUnauthorized}>{null}</TaskProvider>);
    await waitFor(() => expect(es.constructed).toHaveBeenCalled());
    await act(async () => { es.fireError(); });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/users/me")); // 探测已发出
    await act(async () => {}); // flush adminMe resolve
    expect(es.close).not.toHaveBeenCalled();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
