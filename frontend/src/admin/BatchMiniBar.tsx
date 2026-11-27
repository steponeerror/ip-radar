import { useTasks } from "../tasks/useTasks";
import { useI18n } from "../i18n";
import { batchOverallPct, isBatchLive } from "../tasks/progress";
import { useBatchRecentlyDone } from "../tasks/useBatchRecentlyDone";

// 全局迷你进度条(修复:tab 化把「源管理」的动作与「任务」的反馈拆到两个
// tab,更新时无任何可见进度)。batch 运行/暂停时常驻 sticky 区,任何 tab
// 可见,点击跳任务 tab;完成态沿用 5s 停留(仅会话内 running/paused→done
// 转换,冷加载 done 不触发 —— 语义收编在 useBatchRecentlyDone,#486 同
// BatchPanel)。百分比与 BatchPanel 同源:batchOverallPct(各任务
// stagedFrac 均值,下载中也会走)。
export function BatchMiniBar({ onOpen }: { onOpen: () => void }) {
  const { t } = useI18n();
  const { tasks, batch } = useTasks();
  const linger = useBatchRecentlyDone(batch);

  const live = isBatchLive(batch);
  if (!batch || (!live && !linger)) return null;

  const pct = batchOverallPct(tasks, batch);

  const label = batch.state === "paused" ? t("admin.mini.paused", { done: batch.done, total: batch.total })
    : batch.state === "done" ? t("admin.mini.done", { done: batch.done, total: batch.total })
    : t("admin.mini.updating", { done: batch.done, total: batch.total });

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t("admin.mini.open")}
      className="mt-2 flex w-full items-center gap-3 rounded-lg border border-emerald-500/30 bg-zinc-950/90 px-3 py-1.5 text-left font-mono text-xs text-emerald-400 transition-colors hover:border-emerald-400/60"
    >
      <span className="whitespace-nowrap">{label}</span>
      <span className="h-1 flex-1 overflow-hidden rounded-full bg-zinc-800">
        <span
          className="block h-full rounded-full bg-emerald-500 transition-all duration-300"
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </span>
      <span className="whitespace-nowrap">{pct}%</span>
    </button>
  );
}
