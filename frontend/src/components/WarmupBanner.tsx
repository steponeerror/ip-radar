import { useWarming } from "../warming";
import { useI18n } from "../i18n";

// Task 9:公开查询页不再挂 TaskProvider(任务上下文收敛 /admin)——横幅
// 退化为静态冷启动提示。进度数字/当前源/重试按钮依赖任务上下文,数据
// 不可得已移除;消除依赖 WarmingProvider 的 5s db-status 轮询驱动
// (batch done 即清的 SSE 快路径随之让位,清除延迟至多 ~5s)。
// ponytail: 失败去抖+重试已删 —— 匿名无法 enqueue(403);管理员在
// /admin 任务区可见进度并触发刷新,公开页不再需要这条支路。
export function WarmupBanner() {
  const { t } = useI18n();
  const { warming } = useWarming();

  if (!warming) return null;

  return (
    <div data-warmup className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
      <div className="flex items-center gap-2">
        <span className="animate-spin inline-block h-4 w-4 border-2 border-emerald-400 border-t-transparent rounded-full" />
        <span className="text-zinc-200 font-medium">{t("warmup.title")}</span>
      </div>
      <div className="mt-2 text-xs text-zinc-500">{t("warmup.hint")}</div>
    </div>
  );
}
