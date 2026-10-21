import { useCallback, useState } from "react";

// useArrivalNow — 相对时间基准 hook(终审 standards 重构):「now = 数据抵达
// 时刻」纪律的四份同款复制(OpsPastRounds/LedgerSection/PrecedentsSection/
// OpsPackagesSection,票 #148/#149)收编于此。基准取数据回调抵达时刻而非
// render 时刻——Date.now 不入 render(react-hooks/purity,同驾驶舱已耗时
// 纪律);初值 0 = 未抵达,行渲染晚于置位不闪初值;多源先后抵达时后到者
// 刷新基准(取最后抵达,不猜更早的真值——宁少算)。
export function useArrivalNow(): [number, () => void] {
  const [now, setNow] = useState(0);
  const markArrived = useCallback(() => setNow(Date.now()), []); // 稳定引用,入 deps 不churn
  return [now, markArrived];
}
