import type { ReactNode } from "react";

// OpsSectionHead.tsx — 节头行规范(票 #147,spec #146)。运营面全部节的头行 =
// 标题(+计数,有数据时)+ 次级动作(描边按钮)同排;基准范式 = 源管理页
// 「数据源(60) | 全部刷新」。次级动作一律描边按钮(硬规④),裸文字链接
// 动作清零;计数只显非零——空表不谎报数量。
// 票 #148:lead = 左簇内联件(标题右邻),非动作类(如驾驶舱状态 chip)——
// 与右簇次级动作区分,状态不入动作位。
export function SectionHead({ title, count, lead, children }: {
  title: string;
  count?: number | null;
  lead?: ReactNode;
  children?: ReactNode; // 右排次级动作(描边按钮)
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
