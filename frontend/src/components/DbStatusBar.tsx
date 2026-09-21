import { useEffect, useState } from "react";
import { getDbStatus, type DbStatus } from "../api";
import { useI18n } from "../i18n";

// Task 9:公开底栏只读化(管理面收敛 /admin,spec §9)。计数/警告/过期来自
// 公开的 GET /api/db-status;原 Update/Retry 按钮与活动任务面板
// (依赖 /api/tasks + /api/events,Task 3 起超管门)移至 admin/BatchPanel。
export function DbStatusBar() {
  const { t } = useI18n();
  const [status, setStatus] = useState<DbStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDbStatus()
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : t("dbStatus.statusUnavailable")));
  }, [t]);

  if (!status && !error) return null;

  const hasWarnings = status?.warnings && status.warnings.length > 0;

  // Full failure: no status, only error
  if (!status) {
    return (
      <div className="fixed bottom-0 inset-x-0 border-t border-red-500/30 bg-zinc-950/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2 text-xs font-mono">
          <div className="flex items-center gap-3 text-red-400">
            <span className="inline-flex h-2 w-2 rounded-full bg-red-500" />
            <span>{error}</span>
          </div>
        </div>
      </div>
    );
  }

  // Partial failure: status + warnings
  if (hasWarnings) {
    return (
      <div className="fixed bottom-0 inset-x-0 border-t border-amber-500/30 bg-zinc-950/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2 text-xs font-mono text-amber-400">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-2 w-2 rounded-full bg-amber-500" />
            <span>{status.warnings!.join("; ")}</span>
            <span className="text-zinc-700">|</span>
            <span className="text-zinc-500">
              {t("dbStatus.records", { n: status.total_records.toLocaleString() })}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Success
  return (
    <div className="fixed bottom-0 inset-x-0 border-t border-zinc-800 bg-zinc-950/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2 text-xs font-mono text-zinc-500">
        <div className="flex items-center gap-3">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          <span>{t("dbStatus.records", { n: status.total_records.toLocaleString() })}</span>
          <span className="text-zinc-700">|</span>
          <span className="text-zinc-500 tabular-nums">
            {status.scalar_records.toLocaleString()} {t("dbStatus.scalar")}
          </span>
          <span className="text-zinc-600">·</span>
          <span className="text-zinc-500 tabular-nums">
            {status.threat_records.toLocaleString()} {t("dbStatus.threat")}
          </span>
          <span className="text-zinc-600">·</span>
          <span className="text-zinc-500 tabular-nums">
            {status.asset_records.toLocaleString()} {t("dbStatus.asset")}
          </span>
          <span className="text-zinc-700">|</span>
          <span>{t("dbStatus.updated", { time: status.last_updated })}</span>
          {status.is_stale && (
            <span className="text-yellow-500">({t("dbStatus.stale")})</span>
          )}
        </div>
      </div>
    </div>
  );
}
