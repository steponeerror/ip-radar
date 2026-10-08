import { vi, type Mock } from "vitest";

/** 用全新 vi.fn() 替换 globalThis.fetch(配套 fetchMock() 取类型化句柄)。 */
export function installFetchMock(): void {
  globalThis.fetch = vi.fn();
}

/** 取 globalThis.fetch 上 vi.fn() mock 的类型化句柄(免 as any)。 */
export function fetchMock(): Mock {
  return globalThis.fetch as unknown as Mock;
}
