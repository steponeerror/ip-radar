import { createContext, useContext } from "react";

export type WarmingStatus = {
  warming: boolean;
  /** 立即拉取 db-status;warming 重现为 true 时重新武装轮询。 */
  recheck: () => Promise<boolean>;
};

// 组件(WarmingProvider)拆到 ./WarmingProvider.tsx:本文件只留 context +
// hook,避免 react-refresh/only-export-components(组件与 hook 混导出会破
// 该文件粒度的 fast refresh 边界)。
export const WarmingCtx = createContext<WarmingStatus | null>(null);

export function useWarming(): WarmingStatus {
  const c = useContext(WarmingCtx);
  if (!c) throw new Error("useWarming must be used within WarmingProvider");
  return c;
}
