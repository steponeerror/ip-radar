import { useEffect, useRef, useState } from "react";
import { useTasks } from "../tasks/TaskProvider";
import { useI18n } from "../i18n";
import { stagedFrac, isIndeterminate } from "../tasks/progress";

// Task 9:DbStatusBar 的活动面板原样迁入 /admin 任务区(管理面收敛,
// spec §9)。批量进度/暂停/恢复/终止/逐任务取消全部依赖任务上下文 ——
// 本组件只在 AdminPage 的 TaskProvider 内渲染。行为与迁移前一致:
// 完成后保留 ~5s 展示终态再收起;冷加载见到的 done batch 不庆祝。

const BADGE: Record<string, string> = {
  queued: "text-zinc-400 border-zinc-700 bg-zinc-800/50",
  throttled: "text-zinc-400 border-zinc-700 bg-zinc-800/50",
  downloading: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
  loading: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
  done: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
  failed: "text-red-400 border-red-400/30 bg-red-400/10",
  cancelled: "text-zinc-500 border-zinc-700 bg-zinc-800/50",
};

const ACTIVE_TASK_STATES = ["queued", "throttled", "downloading", "loading"];

// (模块内部使用;原 DbStatusBar 的导出面已随迁移收窄)
const fmtBytes = (n: number): string => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
};

const fmtRows = (n: number): string => {
  const k = Math.round(n / 1e3);
  if (k >= 1000) return `${(n / 1e6).toFixed(1)}M`;
  if (k >= 1) return `${k}K`;
  return `${n}`;
};

export function BatchPanel() {
  const { t } = useI18n();
  const { tasks, batch, cancelTask, cancelBatch, pause, resume } = useTasks();
  const [expanded, setExpanded] = useState(true);
  // Keep the active panel mounted for ~5s after the batch finishes so the
  // user sees the final state before it collapses away.
  const [recentlyDone, setRecentlyDone] = useState(false);
  // Last observed batch state this session. The backend keeps the finished
  // batch referenced after it completes, so a cold snapshot can already report
  // state "done" — that must not re-trigger the celebration on every page load.
  // Only an in-session transition running/paused → done counts as "recent".
  const prevBatchState = useRef<string | undefined>(undefined);

  useEffect(() => {
    const cur = batch?.state;
    const prev = prevBatchState.current;
    prevBatchState.current = cur;
    if (cur === "done" && (prev === "running" || prev === "paused")) {
      setRecentlyDone(true);
      setExpanded(true);
      const id = setTimeout(() => {
        setRecentlyDone(false);
        setExpanded(false);
      }, 5000);
      return () => clearTimeout(id);
    }
  }, [batch?.state]);

  const taskActive = tasks.some((t) => ACTIVE_TASK_STATES.includes(t.state));
  const active = taskActive
    || (batch != null && batch.state !== "done")
    || (recentlyDone && batch?.state === "done");

  if (!active) return null;

  // Show only tasks relevant to the current view: when a batch is active
  // (running/paused, or lingering done via recentlyDone), show that batch's
  // tasks; when batchless (a single-source update), show only currently-active
  // tasks so terminal tasks accumulated from prior batches don't clutter the panel.
  const visibleTasks = batch
    ? tasks.filter((t) => t.batch_id === batch.id)
    : tasks.filter((t) => ACTIVE_TASK_STATES.includes(t.state));

  // Overall progress across visible tasks: averages each task's staged
  // fraction (download 0→0.5, rebuild 0.5→1) so the top bar moves
  // DURING downloads and rebuilds — not only when a whole source completes.
  const overallPct = visibleTasks.length > 0
    ? Math.round((visibleTasks.reduce((s, t) => s + stagedFrac(t), 0) / visibleTasks.length) * 100)
    : 0;
  const headerLabel = batch?.state === "paused" ? t("dbStatus.paused") : t("dbStatus.updating");
  return (
    <div className="rounded-lg border border-emerald-500/30 bg-zinc-950/90">
      <div className="px-4 py-2 text-xs font-mono">
        <div className="flex items-center justify-between text-emerald-400">
          <span>
            {headerLabel}{batch != null && ` · ${batch.done}/${batch.total}`} · {overallPct}%
          </span>
          <span className="flex gap-2">
            {batch?.state === "paused" ? (
              <button
                onClick={() => resume()}
                className="rounded px-2 py-0.5 text-emerald-400 hover:bg-zinc-800 hover:text-emerald-300"
                aria-label={t("dbStatus.resume")}
              >
                ▶ {t("dbStatus.resume")}
              </button>
            ) : (
              <button
                onClick={() => pause()}
                disabled={batch?.state === "done"}
                className="rounded px-2 py-0.5 text-emerald-400 hover:bg-zinc-800 hover:text-emerald-300 disabled:opacity-50"
                aria-label={t("dbStatus.pause")}
              >
                ⏸ {t("dbStatus.pause")}
              </button>
            )}
            <button
              onClick={() => cancelBatch()}
              className="rounded px-2 py-0.5 text-red-400 hover:bg-zinc-800 hover:text-red-300"
              aria-label={t("dbStatus.abort")}
            >
              ✕ {t("dbStatus.abort")}
            </button>
            <button
              onClick={() => setExpanded((e) => !e)}
              className="rounded px-2 py-0.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
              aria-label={expanded ? "Collapse" : "Expand"}
            >
              {expanded ? "▴" : "▾"}
            </button>
          </span>
        </div>
        <div className="mt-1 h-1 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all duration-300"
            style={{ width: `${overallPct}%` }}
          />
        </div>
        {expanded && (
          <div className="mt-1 max-h-40 overflow-y-auto">
            {visibleTasks.map((task) => (
              <div key={task.id} className="flex items-center gap-2 py-0.5">
                <span className="w-32 truncate font-mono text-zinc-300" title={task.source}>
                  {task.source}
                </span>
                <span
                  className={`rounded-md border px-2 text-[10px] ${BADGE[task.state] ?? ""}`}
                >
                  {task.state}
                </span>
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-zinc-800">
                  {(() => {
                    if (task.state === "failed") {
                      return <div className="h-full w-full rounded-full bg-red-500" />;
                    }
                    if (task.state === "cancelled") {
                      const f = stagedFrac(task);
                      return f > 0 ? (
                        <div
                          className="h-full rounded-full bg-zinc-600 transition-all duration-150"
                          style={{ width: `${Math.min(100, Math.round(f * 100))}%` }}
                        />
                      ) : null;
                    }
                    if (isIndeterminate(task)) {
                      return <div className="h-full w-1/3 rounded-full bg-emerald-500 animate-pulse" />;
                    }
                    const f = stagedFrac(task);
                    if (f > 0 || task.state === "done") {
                      return (
                        <div
                          className="h-full rounded-full bg-emerald-500 transition-all duration-150"
                          style={{ width: `${Math.min(100, Math.round(f * 100))}%` }}
                        />
                      );
                    }
                    return null;
                  })()}
                </div>
                <span className="w-10 shrink-0 text-right font-mono text-[10px] tabular-nums text-zinc-500">
                  {/* resync/刷新后 frozenFrac 丢失(后端 to_dict 不携带):终态行
                      显示 --% 而非假 0%;frozenFrac===0(排队即死)是真实值仍显 0% */}
                  {(task.state === "failed" || task.state === "cancelled") && task.frozenFrac === undefined
                    ? "--%"
                    : isIndeterminate(task)
                      ? "--%"
                      : `${Math.round(stagedFrac(task) * 100)}%`}
                </span>
                {(task.state === "downloading" || task.state === "loading") && (task.received ?? 0) > 0 && (
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-zinc-500">
                    {task.state === "downloading"
                      ? `${fmtBytes(task.received!)}${(task.total ?? 0) > 0 ? `/${fmtBytes(task.total!)}` : ""}`
                      : `${fmtRows(task.received!)}${(task.total ?? 0) > 0 ? `/${fmtRows(task.total!)}` : ""} ${t("dbStatus.rows")}`}
                  </span>
                )}
                {task.error && (
                  <span className="truncate text-red-400/80" title={task.error}>
                    {task.error}
                  </span>
                )}
                <button
                  className="text-zinc-500 hover:text-red-400 disabled:opacity-30"
                  onClick={() => cancelTask(task.id)}
                  disabled={!ACTIVE_TASK_STATES.includes(task.state)}
                  aria-label={`Cancel ${task.source}`}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
