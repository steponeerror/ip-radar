import { useState, useCallback, useEffect, useRef, type ReactNode } from "react";
import { getDbStatus } from "./api";
import { WarmingCtx } from "./warming";

export function WarmingProvider({ children }: { children: ReactNode }) {
  const [warming, setWarming] = useState(false);
  const timerRef = useRef<number | undefined>(undefined);
  const aliveRef = useRef(false);
  // poll 重臂轮询时要引用自身(useCallback 值在自身声明完成前不可引用,
  // react-hooks/immutability)——经 ref 间接持有,挂载 effect 里落位。
  const pollRef = useRef<() => Promise<boolean>>(() => Promise.resolve(false));

  const poll = useCallback(async (): Promise<boolean> => {
    const s = await getDbStatus().catch(() => null);
    if (!aliveRef.current || !s) return false;
    setWarming(s.warming_up);
    // warming_up 在后端进程生命周期内只会 true→false,首个 false 即停轮
    // (稳态零轮询);recheck() 发现 warming 重现(后端重启进入新冷启动)
    // 时重新武装轮询 — 否则控件锁死且横幅永不出现。
    if (!s.warming_up && timerRef.current !== undefined) {
      clearInterval(timerRef.current);
      timerRef.current = undefined;
    } else if (s.warming_up && timerRef.current === undefined) {
      timerRef.current = setInterval(() => void pollRef.current(), 5000);
    }
    return s.warming_up;
  }, []);

  useEffect(() => {
    pollRef.current = poll;
    aliveRef.current = true;
    poll();
    timerRef.current = setInterval(poll, 5000);
    return () => {
      aliveRef.current = false;
      if (timerRef.current !== undefined) clearInterval(timerRef.current);
      timerRef.current = undefined;
    };
  }, [poll]);

  return (
    <WarmingCtx.Provider value={{ warming, recheck: poll }}>
      {children}
    </WarmingCtx.Provider>
  );
}
