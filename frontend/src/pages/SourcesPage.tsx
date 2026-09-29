import { useCallback, useEffect, useState } from "react";
import {
  enqueueBatch,
  enqueueSingle,
  fetchEvalModel,
  getSources,
  setSourceEnabled,
} from "../api";
import type { BatchState, EvalModelScore, SourceInfo, TaskState } from "../api";
import { useI18n } from "../i18n";

// Task 9:任务/批量态由 AdminPage 在其 TaskProvider 内取好下传;
// 公开页(<SourcesPage /> 无 props)纯只读 —— useTasks 已移出本组件。
export interface SourcesPageProps {
  manage?: boolean;
  tasks?: TaskState[];
  batch?: BatchState | null;
  // 会话中 401 → 踢回登录页(仅 manage 模式传入;公开页无此语义)
  onUnauthorized?: () => void;
}

const CATEGORY_ORDER = ["geo_asn", "threat", "asset", "other"];

// R1/R2/R3:表头行与数据行共用同一套三档 grid 模板 —— 基础档 名称/字段/
// 覆盖IP/更新/状态/r(+manage 的操作),lg(≥1024)加评估列,xl(≥1280)再加
// θ 列;公开页(manage=false)模板随之少操作列一档。固定轨道沿用原列宽
// 语义(w-32/16/24/28/36 → 8/4/6/7/9rem),末列 1fr 供操作列右贴。模板档位
// 必须与单元格 hidden lg:block / hidden xl:block 断点逐档一致。
const GRID_TEMPLATE_MANAGE =
  "grid-cols-[8rem_4rem_4rem_6rem_6rem_4rem_1fr] lg:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem_1fr] xl:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem_9rem_1fr]";
const GRID_TEMPLATE_PUBLIC =
  "grid-cols-[8rem_4rem_4rem_6rem_6rem_4rem] lg:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem] xl:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem_9rem]";

function formatCount(n: number): string {
  if (n <= 0) return "-";
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1).replace(/\.0$/, "") + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return Math.round(n / 1_000) + "K";
  return String(n);
}

function timeAgo(iso: string | null): { key: string; vars?: Record<string, string | number> } {
  if (!iso) return { key: "sources.timeAgo.noData" };
  const ms = Date.now() - Date.parse(iso);
  if (Number.isNaN(ms)) return { key: "sources.timeAgo.unknown" };
  const min = Math.floor(ms / 60000);
  if (min < 1) return { key: "sources.timeAgo.justNow" };
  if (min < 60) return { key: "sources.timeAgo.minutes", vars: { n: min } };
  const hr = Math.floor(min / 60);
  if (hr < 24) return { key: "sources.timeAgo.hours", vars: { n: hr } };
  return { key: "sources.timeAgo.days", vars: { n: Math.floor(hr / 24) } };
}

// 行内按钮相位文案:downloading/loading 带 received/total 百分比(计划钉死
// N = Math.floor(received/total*100),终审 P2 补 Math.min(100,·) clamp 对齐
// progress.ts stagedFrac 既有规范;total 缺失/≤0 退回纯文案),queued/throttled
// 共用"排队中"。translate() 对未替换占位符原样保留,故"纯文案回退"由 pct 后缀
// 传空串实现,而非不传 vars。
function phaseLabel(tk: TaskState): { key: string; vars?: Record<string, string | number> } {
  if (tk.state !== "downloading" && tk.state !== "loading") return { key: "sources.queued" };
  const total = tk.total ?? 0;
  const suffix = total > 0 ? ` ${Math.min(100, Math.floor(((tk.received ?? 0) / total) * 100))}%` : "";
  return {
    key: tk.state === "downloading" ? "sources.downloading" : "sources.loading",
    vars: { pct: suffix },
  };
}

function statusOf(s: SourceInfo): { key: string; className: string } {
  if (s.health.error) return { key: "sources.status.error", className: "text-red-400 border-red-400/30 bg-red-400/10" };
  if (!s.enabled) return { key: "sources.status.off", className: "text-zinc-500 border-zinc-700 bg-zinc-800/50" };
  if (!s.health.loaded) return { key: "sources.status.notLoaded", className: "text-amber-400 border-amber-400/30 bg-amber-400/10" };
  if (s.health.is_stale) return { key: "sources.status.stale", className: "text-amber-400 border-amber-400/30 bg-amber-400/10" };
  return { key: "sources.status.fresh", className: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5" };
}

// eval verdict 徽章色:W4 "NO-DATA" 精确串(backend verdict.py 钉死,reason
// empty/collapsed)→ 灰底红字 —— 死源告警,与 NEGATIVE 的全红区分。
function evalBadgeClass(verdict: string): string {
  if (verdict === "NO-DATA") return "text-red-400 border-zinc-700 bg-zinc-800/50";
  if (verdict.startsWith("POSITIVE-VERIFIED")) return "text-emerald-400 border-emerald-400/30 bg-emerald-400/10";
  if (verdict.startsWith("POSITIVE")) return "text-sky-400 border-sky-400/30 bg-sky-400/10";
  if (verdict.startsWith("NEGATIVE")) return "text-red-400 border-red-400/30 bg-red-400/10";
  return "text-zinc-500 border-zinc-700 bg-zinc-800/50";
}

function Toggle({ on, disabled, onChange, label }: {
  on: boolean; disabled: boolean; onChange: (v: boolean) => void; label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${
        on ? "bg-emerald-500" : "bg-zinc-700"
      } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <span className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
        on ? "translate-x-4" : "translate-x-0"
      }`} />
    </button>
  );
}

export default function SourcesPage({ manage = false, tasks = [], batch = null, onUnauthorized }: SourcesPageProps) {
  const { t } = useI18n();
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  // A2 双轨:每源实测 θ(印证率,advisory)。拉不到/无报告 → 空表,θ 列全 —。
  const [thetaBySource, setThetaBySource] = useState<Map<string, EvalModelScore>>(new Map());

  // 401 = 会话失效 → 踢回登录页;其余错误走原错误文案路径。
  const failWith = (e: unknown, fallback: string) => {
    if ((e as { status?: number }).status === 401) { onUnauthorized?.(); return; }
    setError(e instanceof Error ? e.message : fallback);
  };

  const fmtTime = (s: SourceInfo) => {
    const ta = timeAgo(s.health.last_updated);
    return t(ta.key, ta.vars);
  };

  const fetchSources = useCallback(async () => {
    setError(null);
    try {
      setSources(await getSources());
    } catch (e) {
      failWith(e, t("sources.loadFailed"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, onUnauthorized]);

  // Initial fetch: setState is reached only after `await getSources()` inside the
  // async callback, but react-hooks/set-state-in-effect is a heuristic flag.
  // Same idiom as ResultTable.tsx (pre-existing); pattern mandated by task brief.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchSources(); }, [fetchSources]);

  // A2:拉一次最新评估模型报告,按源名建 θ 索引。失败静默降级 ——
  // θ 是 advisory 展示,不得拖垮主列表(与主 fetch 的容错语义一致)。
  useEffect(() => {
    fetchEvalModel()
      .then((m) => {
        if (m?.scores) setThetaBySource(new Map(m.scores.map((sc) => [sc.source, sc])));
      })
      .catch(() => { /* 无报告/接口失败:θ 列保持 — */ });
  }, []);

  // Debounce-refetch: when the count of finished tasks (done/failed/cancelled)
  // changes, re-sync the source list after 500ms so health/record_count updates.
  // 公开页 tasks 恒空 → doneCount 恒 0,自然 no-op。
  const doneCount = tasks.filter(
    (tk) => tk.state === "done" || tk.state === "failed" || tk.state === "cancelled",
  ).length;
  useEffect(() => {
    if (doneCount === 0) return;
    const id = setTimeout(() => { void fetchSources(); }, 500);
    return () => clearTimeout(id);
  }, [doneCount, fetchSources]);

  const patch = (name: string, change: Partial<SourceInfo>) => {
    setSources((prev) => prev.map((s) => (s.name === name ? { ...s, ...change } : s)));
  };

  const handleToggle = async (s: SourceInfo, next: boolean) => {
    patch(s.name, { enabled: next });
    try {
      const updated = await setSourceEnabled(s.name, next);
      patch(s.name, { enabled: updated.enabled, health: updated.health });
    } catch (e) {
      patch(s.name, { enabled: s.enabled });  // rollback
      failWith(e, t("sources.toggleFailed", { name: s.name }));
    }
  };

  const handleUpdate = async (name: string) => {
    try {
      await enqueueSingle(name);
    } catch (e) {
      failWith(e, t("sources.updateOneFailed", { name }));
    }
  };

  const handleRefreshAll = async () => {
    setInfo(null);
    try {
      const { refreshed } = await enqueueBatch();
      if (refreshed === 0) setInfo(t("sources.allFresh"));
    } catch (e) {
      failWith(e, t("sources.refreshAllFailed"));
    }
  };

  // Batch active → global "refreshing" indicator (disables per-row Update + the
  // Refresh-all button). Derived from the batch prop, no local state.
  const refreshingAll = batch?.state === "running";

  const grouped = CATEGORY_ORDER
    .map((cat) => ({ cat, items: sources.filter((s) => s.category === cat) }))
    .filter((g) => g.items.length > 0);

  // tasks arrive oldest-first and a source accumulates terminal tasks across
  // batches; the last task seen per source is the current one (whole TaskState:
  // the row needs received/total for the phase percentage). Index once so
  // re-updating a previously-updated source still reflects its live phase
  // (regression: `find()` returned the stale first task and hid the progress).
  const phaseBySource = new Map<string, TaskState>();
  for (const tk of tasks) phaseBySource.set(tk.source, tk);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-400">
          {sources.length > 0 ? t("sources.titleCount", { n: sources.length }) : t("sources.title")}
        </h2>
        {manage && (
          <button
            onClick={handleRefreshAll}
            disabled={refreshingAll || loading}
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshingAll ? t("sources.refreshingAll") : t("sources.refreshAll")}
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-2 text-sm text-red-400">
          {error}
        </div>
      )}

      {info && !error && (
        <div className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-400">
          {info}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-zinc-900" />
          ))}
        </div>
      ) : grouped.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded-lg border border-zinc-800 text-sm text-zinc-600">
          {t("sources.none")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          {/* 修复轮 P1:单一外层 overflow-x-auto 滚动容器把全局表头行与全部分组
              (grouped.map 整块)包在一起 —— 表头与所有数据行同层锁步横滚,不再
              逐分组各自滚动(窄屏表头/数据错位 + 页面级双横滚条)。内层 min-w-max:
              窄视口下表头与各分组卡片(ul 圆角边框)随行内容整体取宽,行不溢出
              卡片边框,圆角裁剪等视觉不回归。 */}
          <div className="min-w-max">
            {/* R1 全局单表头:置于所有分组之上(组头仍在各自分组处),与数据行
                同模板同断点;纯 div/span 无 role(修复轮 P2a:无 table 上下文的
                role="row"/"columnheader" 属孤儿 role,违反 ARIA 上下文规则),
                不做 table 化(R8)。R3:公开页同步省略操作列。评估/θ 表头单元格
                与数据单元格同 hidden 断点(R2)。 */}
            <div
              className={`grid gap-x-4 px-4 pb-2 text-xs font-medium text-zinc-500 ${
                manage ? GRID_TEMPLATE_MANAGE : GRID_TEMPLATE_PUBLIC
              }`}
            >
              <span className="truncate">{t("sources.col.name")}</span>
              <span className="truncate">{t("sources.col.field")}</span>
              <span className="truncate text-right">{t("sources.col.covered")}</span>
              <span className="truncate">{t("sources.col.updated")}</span>
              <span className="truncate text-center">{t("sources.col.status")}</span>
              <span className="hidden truncate text-center lg:block">{t("sources.col.eval")}</span>
              <span className="truncate text-center">{t("sources.col.r")}</span>
              <span className="hidden truncate text-center xl:block">{t("sources.col.theta")}</span>
              {manage && (
                <span className="truncate text-right">{t("sources.col.action")}</span>
              )}
            </div>
            <div className="space-y-6">
              {grouped.map(({ cat, items }) => (
                <div key={cat}>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-600">
                    {t(`sources.cat.${cat}`)}
                  </h3>
                  <ul
                    className="fade-in divide-y divide-zinc-900 rounded-lg border border-zinc-800"
                  >
                    {items.map((s) => {
                      const st = statusOf(s);
                      const ms = thetaBySource.get(s.name);
                      // Per-row phase comes from the tasks prop (AdminPage passes
                      // the SSE-driven context state down; public pages pass none).
                      // A row is "busy" when a task for this source is in any of
                      // the four idempotent enqueue states (backend _enqueue_one:
                      // re-clicking during throttled is a silent no-op, hence
                      // throttled must read as busy too).
                      const phase = phaseBySource.get(s.name);
                      const busy =
                        phase?.state === "queued" ||
                        phase?.state === "throttled" ||
                        phase?.state === "downloading" ||
                        phase?.state === "loading";
                      const label = busy && phase ? phaseLabel(phase) : null;
                      return (
                        <li
                          key={s.name}
                          className={`grid items-center gap-x-4 px-4 py-3 ${
                            manage ? GRID_TEMPLATE_MANAGE : GRID_TEMPLATE_PUBLIC
                          }`}
                        >
                          {/* 轨道宽度由模板控制;truncate+title 防长名/长字段溢出邻列 */}
                          <span className="truncate font-mono text-sm text-zinc-200" title={s.name}>
                            {s.name}
                          </span>
                          <span
                            className="truncate text-xs text-zinc-500"
                            title={s.fields[0] ?? s.archetype}
                          >
                            {s.fields[0] ?? s.archetype}
                          </span>
                          <span className="text-right font-mono text-sm tabular-nums text-zinc-300">
                            {formatCount(s.health.covered_ips)}
                          </span>
                          <span className="truncate text-xs text-zinc-500">{fmtTime(s)}</span>
                          <span className={`rounded-md border px-2 py-0.5 text-center text-xs ${st.className}`}>
                            {t(st.key)}
                          </span>
                          {s.eval ? (
                            <span
                              className={`hidden rounded-md border px-2 py-0.5 text-center text-xs lg:block ${evalBadgeClass(s.eval.verdict)}`}
                              // NO-DATA:说明性 title(数据为空/坍塌)替代评估日期
                              title={s.eval.verdict === "NO-DATA"
                                ? t("sources.eval.noDataTitle")
                                : s.eval.at}
                            >
                              {t("sources.eval." + s.eval.verdict.toLowerCase().replace(/-/g, "_"))}
                            </span>
                          ) : (
                            <span className="hidden text-center text-xs text-zinc-600 lg:block">-</span>
                          )}
                          {/* A2 双轨:声明 r(生产权重)+ 实测 θ(印证率,advisory)。 */}
                          <span className="text-center font-mono text-xs tabular-nums text-zinc-400">
                            r {s.reliability.toFixed(2)}
                          </span>
                          {ms && ms.theta != null ? (
                            <span
                              className="hidden whitespace-nowrap text-center font-mono text-xs tabular-nums text-sky-400 xl:block"
                              title={t("sources.thetaTooltip")}
                            >
                              θ {ms.theta.toFixed(2)}
                              {ms.ci_lo != null &&
                                ` [${ms.ci_lo.toFixed(2)}–${ms.ci_hi!.toFixed(2)}]`}
                            </span>
                          ) : (
                            <span className="hidden text-center text-xs text-zinc-600 xl:block">—</span>
                          )}
                          {manage && (
                            <div className="flex items-center gap-3 justify-self-end">
                              <Toggle
                                on={s.enabled}
                                disabled={busy}
                                onChange={(v) => handleToggle(s, v)}
                                label={t("sources.toggleAria", { name: s.name })}
                              />
                              <button
                                onClick={() => handleUpdate(s.name)}
                                disabled={busy || refreshingAll}
                                className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-200 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {label ? t(label.key, label.vars) : t("sources.update")}
                              </button>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && grouped.length > 0 && (
        <p className="mt-2 text-xs text-zinc-600">
          <span className="font-mono">{t("sources.thetaCol")}</span> — {t("sources.thetaFootnote")}
        </p>
      )}
    </section>
  );
}
