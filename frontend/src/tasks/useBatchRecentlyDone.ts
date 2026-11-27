import { useEffect, useRef, useState } from "react";
import type { BatchState } from "../api";

// 停留(linger)#486 收编:此前「刚完成的批量停留 ~5s 展示终态再收起」在
// BatchPanel(展开停留)与 BatchMiniBar(条停留)各抄一份。本钩子收编
// 同一份语义:
// - 仅会话内 running/paused → done 转换触发;冷加载快照已是 done 不庆祝
//   (否则每次整页加载都闪一次终态 —— 后端完成后仍引用该 batch);
// - 5s 窗口结束 linger 翻回 false;窗口内 batch 状态再变(新一批开跑)则
//   清理定时器,linger 保持 true(与抽取前两处实现一致)。
// opts.onStart/onEnd 供 BatchPanel 挂「完成时展开、窗口结束收起」的耦合;
// 回调走 latest-ref,定时器闭包永远拿到最新回调,effect 只依赖 batch.state。
const LINGER_MS = 5000;

export function useBatchRecentlyDone(
  batch: BatchState | null | undefined,
  opts?: { onStart?: () => void; onEnd?: () => void },
): boolean {
  const [linger, setLinger] = useState(false);
  const prevBatchState = useRef<string | undefined>(undefined);
  const cbRef = useRef(opts);
  useEffect(() => { cbRef.current = opts; });

  useEffect(() => {
    const cur = batch?.state;
    const prev = prevBatchState.current;
    prevBatchState.current = cur;
    if (cur === "done" && (prev === "running" || prev === "paused")) {
      setLinger(true);
      cbRef.current?.onStart?.();
      const id = setTimeout(() => {
        setLinger(false);
        cbRef.current?.onEnd?.();
      }, LINGER_MS);
      return () => clearTimeout(id);
    }
  }, [batch?.state]);

  return linger;
}
