import type { ReactNode } from "react";

// OpsSectionHead.tsx — 节头行规范(票 #147,spec #146)。运营面全部节的头行 =
// 标题(+计数,有数据时)+ 右排动作同排;基准范式 = 源管理页
// 「数据源(60) | 全部刷新」。次级动作一律描边按钮(硬规④),裸文字链接
// 动作清零;节级主操作(如 #150「保存全部」)可实心——硬规④辖次级动作。
// 计数只显非零——空表不谎报数量。台账/判例/裁决包三节计数与空态
// 由 #149 在此组件上补齐。
// 票 #148:lead = 左簇内联件(标题右邻),非动作类(如驾驶舱状态 chip)——
// 与右簇动作区分,状态不入动作位。
export function SectionHead({ title, count, lead, children }: {
  title: string;
  count?: number | null;
  lead?: ReactNode;
  children?: ReactNode; // 右排动作(描边次级为主;节级主操作可实心)
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-medium text-zinc-400">
          {title}
          {count != null && count > 0 ? ` (${count})` : ""}
        </h2>
        {lead}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}
