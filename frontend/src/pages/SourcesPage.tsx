import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  clearAdminToken,
  enqueueBatch,
  enqueueSingle,
  fetchEvalModel,
  getAdminTokens,
  getSources,
  putAdminToken,
  setSourceEnabled,
} from "../api";
import type { BatchState, EvalModelScore, SourceInfo, TaskState, TokenStatus } from "../api";
import { isTaskActive, isTaskTerminal } from "../tasks/progress";
import { useI18n } from "../i18n";

// 源页重设计(2026-10-17 grill 裁决)三级扫读结构:组头(可收起 button)→
// 主行(单行 6 元素)→ 详情层(点行非控件区展开的 region)。页面第一用途 =
// 扫一眼发现异常源:正常源安静成行,诊断数据(r/θ/评估/年龄·周期/feeds/
// 最近错误)按需下沉详情层。任务/批量态由 AdminPage 在其 TaskProvider 内
// 取好下传;manage=false 公开变体已删(唯一调用方恒传全套 props)。
export interface SourcesPageProps {
  tasks: TaskState[];
  batch: BatchState | null;
  // 会话中 401 → 踢回登录页
  onUnauthorized: () => void;
}

const CATEGORY_ORDER = ["geo_asn", "threat", "asset", "other"];

// 组展开态持久化键:localStorage 记 {cat: expanded},缺省(无键/坏 JSON)
// = 全收起 —— 扫读优先,异常从组头计数进,不靠铺开全表。
const GROUPS_LS_KEY = "ipradar.sources.groups";

// 详情层「从不」阈值:≥1000d 的内容年龄/刷新周期数字无信息量(如
// infra_services 周期 36500h),裁决以「从不」替显。
const NEVER_H = 24_000;

// 主行单行 grid 五轨(状态点/源名/字段/覆盖/更新)在行按钮内;源名
// minmax(0,1fr) 弹性吸收剩余宽(旧 8rem 固定轨曾截断源名)。操作区
// (Toggle+更新)是行按钮的兄弟节点 —— 控件点击永不触发行展开。
const ROW_TEMPLATE = "grid-cols-[1rem_minmax(0,1fr)_6rem_6rem_6rem]";

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

// 与后端推送 _fmt_hours 同规(约束 6):<48h → ceil 整数 + "h";≥48h →
// 一位小数 + "d"。终审 P2-1:时钟回拨/未来 mtime 可致负时长,展示层
// clamp 0;null(无文件/旧 payload 无键)→ "—"。≥1000d「从不」由调用侧
// 裁决(需 i18n,fmtHours 保持纯函数)。
function fmtHours(h: number | null): string {
  if (h == null) return "—";
  const v = Math.max(0, h);
  return v < 48 ? `${Math.ceil(v)}h` : `${(v / 24).toFixed(1)}d`;
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

// 四态主行呈现:id 供 data-status 测试定位与 dot title 键拼接;dot = 行首
// 状态点(fresh 近隐形 bg-zinc-800,error 红,stale/notLoaded 琥珀,off 灰蓝);
// tint = 异常行轻微底色(随异常类着色);rank = 组内排序(异常置顶,内部序
// error>stale/notLoaded>off,健康按 name 字母序 —— rank 3 = fresh)。
type RowStatus = { id: string; dot: string; tint: string; rank: number };

function statusOf(s: SourceInfo): RowStatus {
  if (s.health.error) return { id: "error", dot: "bg-red-400", tint: "bg-red-400/5", rank: 0 };
  if (!s.enabled) return { id: "off", dot: "bg-sky-700", tint: "bg-sky-700/5", rank: 2 };
  if (!s.health.loaded) return { id: "notLoaded", dot: "bg-amber-400", tint: "bg-amber-400/5", rank: 1 };
  if (s.health.is_stale) return { id: "stale", dot: "bg-amber-400", tint: "bg-amber-400/5", rank: 1 };
  return { id: "fresh", dot: "bg-zinc-800", tint: "", rank: 3 };
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

function loadExpandedGroups(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(GROUPS_LS_KEY);
    const v = raw ? JSON.parse(raw) : null;
    return v && typeof v === "object" ? (v as Record<string, boolean>) : {};
  } catch { /* localStorage 可能不可用 / 坏 JSON → 全收起 */ }
  return {};
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

// 详情层标签/值行:标签固定宽对齐扫读,值区右延
function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="w-44 shrink-0 text-zinc-600">{label}</span>
      <span className="min-w-0 text-zinc-300">{children}</span>
    </div>
  );
}

export default function SourcesPage({ tasks, batch, onUnauthorized }: SourcesPageProps) {
  const { t } = useI18n();
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  // A2 双轨:每源实测 θ(印证率,advisory)。拉不到/无报告 → 空表,详情层 —。
  const [thetaBySource, setThetaBySource] = useState<Map<string, EvalModelScore>>(new Map());
  // 三级结构状态:组展开态(持久化 localStorage)+ 行详情展开态(会话内,
  // 同组多行可同时展开,不持久化)
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(loadExpandedGroups);
  const [openDetails, setOpenDetails] = useState<Set<string>>(() => new Set());
  // token 状态(T3):null = 未拉到(失败静默/未返回)→ 全视为已配置,入口全隐。
  // 裁决:不新增轮询,挂载一次性拉取;写/清除成功只翻本地态,不重拉。
  const [tokens, setTokens] = useState<TokenStatus[] | null>(null);
  // 行内简易对话框:记源名(非 env_var —— OTX 双源共享一 var,按 var 记会两行同开)
  const [tokenDialogFor, setTokenDialogFor] = useState<string | null>(null);
  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenBusy, setTokenBusy] = useState(false);

  // 401 = 会话失效 → 踢回登录页;其余错误走原错误文案路径。
  const failWith = (e: unknown, fallback: string) => {
    if ((e as { status?: number }).status === 401) { onUnauthorized(); return; }
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
      .catch(() => { /* 无报告/接口失败:详情层 θ 保持 — */ });
  }, []);

  // token 状态挂载一次性拉取;失败静默保持 null(grill 冻结:拉取失败 →
  // 全部视为已配置,入口隐藏,不得拖垮主列表/不出错误横幅)。
  useEffect(() => {
    getAdminTokens().then(setTokens).catch(() => { /* 静默降级 */ });
  }, []);

  // 源名 → token 状态索引(OTX 一 key 双源:两行取同一 status,配置一次双双消失)。
  const tokenBySource = new Map<string, TokenStatus>();
  for (const tk of tokens ?? []) {
    for (const sn of tk.sources) tokenBySource.set(sn, tk);
  }

  // Debounce-refetch: when the count of finished tasks (done/failed/cancelled,
  // isTaskTerminal) changes, re-sync the source list after 500ms so health/
  // record_count updates.
  const doneCount = tasks.filter(isTaskTerminal).length;
  useEffect(() => {
    if (doneCount === 0) return;
    const id = setTimeout(() => { void fetchSources(); }, 500);
    return () => clearTimeout(id);
  }, [doneCount, fetchSources]);

  const toggleGroup = (cat: string) => {
    setExpandedGroups((prev) => {
      const next = { ...prev, [cat]: !prev[cat] };
      try { localStorage.setItem(GROUPS_LS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };

  const toggleDetail = (name: string) => {
    setOpenDetails((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

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

  // 保存即 PUT,成功即关;本地翻 configured + 尾 4 位(与后端 status 同源算
  // 法:value.slice(-4)),不重拉。空值/重复提交在按钮 disabled + guard 双挡
  // (后端 422 兕底)。
  const handleTokenSave = async (envVar: string) => {
    const value = tokenDraft;
    if (!value.trim() || tokenBusy) return;
    setTokenBusy(true);
    try {
      await putAdminToken(envVar, value);
      setTokens((prev) => prev!.map((x) =>
        x.env_var === envVar ? { ...x, configured: true, tail4: value.slice(-4) } : x,
      ));
      setTokenDialogFor(null);
    } catch (e) {
      failWith(e, t("sources.token.saveFailed"));
    } finally {
      setTokenBusy(false);
    }
  };

  const handleTokenClear = async (envVar: string) => {
    try {
      await clearAdminToken(envVar);
      setTokens((prev) => prev!.map((x) =>
        x.env_var === envVar ? { ...x, configured: false, tail4: null } : x,
      ));
    } catch (e) {
      failWith(e, t("sources.token.clearFailed"));
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
    .map((cat) => {
      // 组内序:异常(状态≠fresh)置顶,内部序 error>stale/notLoaded>off;
      // 健康按 name 字母序(filter 产新数组,原地排序不动 sources state)
      const items = sources
        .filter((s) => s.category === cat)
        .sort((a, b) => statusOf(a).rank - statusOf(b).rank || a.name.localeCompare(b.name));
      return { cat, items };
    })
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
        <button
          onClick={handleRefreshAll}
          disabled={refreshingAll || loading}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {refreshingAll ? t("sources.refreshingAll") : t("sources.refreshAll")}
        </button>
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
        <div className="space-y-4">
          {grouped.map(({ cat, items }) => {
            const expanded = !!expandedGroups[cat];
            const anomalies = items.filter((s) => statusOf(s).rank < 3);
            const hasError = anomalies.some((s) => statusOf(s).rank === 0);
            return (
              <div key={cat}>
                {/* 组头:类别 · N 源 · M 异常(琥珀;含 error 源时红)。
                    可收起 button + aria-expanded;默认全收起,展开态记
                    localStorage。 */}
                <button
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={`sources-group-${cat}`}
                  onClick={() => toggleGroup(cat)}
                  className="flex w-full items-baseline gap-2 rounded px-1 py-1.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500 transition-colors hover:text-zinc-300"
                >
                  <span aria-hidden="true" className="w-3 shrink-0">{expanded ? "▾" : "▸"}</span>
                  <span className="text-zinc-400">{t(`sources.cat.${cat}`)}</span>
                  <span className="font-normal normal-case tracking-normal text-zinc-600">
                    {`· ${items.length} ${t("sources.group.sourcesUnit")}`}
                  </span>
                  {anomalies.length > 0 && (
                    <span
                      className={`font-normal normal-case tracking-normal ${
                        hasError ? "text-red-400" : "text-amber-400"
                      }`}
                    >
                      {`· ${anomalies.length} ${t("sources.group.anomalyUnit")}`}
                    </span>
                  )}
                </button>
                {expanded && (
                  <ul
                    id={`sources-group-${cat}`}
                    className="fade-in divide-y divide-zinc-900 overflow-hidden rounded-lg border border-zinc-800"
                  >
                    {items.map((s) => {
                      const st = statusOf(s);
                      const open = openDetails.has(s.name);
                      const detailId = `sources-detail-${s.name}`;
                      const ms = thetaBySource.get(s.name);
                      const tokenSt = tokenBySource.get(s.name);
                      // Per-row phase comes from the tasks prop (AdminPage passes
                      // the SSE-driven context state down). A row is "busy" when
                      // a task for this source is in any of the four idempotent
                      // enqueue states (isTaskActive; rationale in progress.ts:
                      // re-clicking during throttled is a silent no-op, hence
                      // throttled must read as busy too).
                      const phase = phaseBySource.get(s.name);
                      const busy = phase != null && isTaskActive(phase);
                      const label = busy && phase ? phaseLabel(phase) : null;
                      // 详情层诊断值:fmtHours 档位 + ≥1000d「从不」裁决;
                      // cadence 为 null 时直出 "—",不套 cadence 模板
                      const fmtDetailHours = (h: number | null | undefined) =>
                        h == null ? "—" : h >= NEVER_H ? t("sources.detail.never") : fmtHours(h);
                      const ageStr = fmtDetailHours(s.health.content_age_h);
                      const periodStr = s.health.refresh_period_h == null
                        ? "—"
                        : s.health.refresh_period_h >= NEVER_H
                          ? t("sources.detail.never")
                          : t("sources.health.cadence", {
                              v: fmtHours(s.health.refresh_period_h),
                            });
                      return (
                        <li key={s.name} className={st.tint}>
                          {/* 主行 = 行按钮(点非控件区展开详情)+ 兄弟操作区。
                              行按钮承载五轨 grid;aria-label 用 expandAria 而
                              非拼单元格文本(读屏听整行噪声)。 */}
                          <div className="flex items-center gap-4 px-4 py-2.5">
                            <button
                              type="button"
                              id={`sources-row-${s.name}`}
                              aria-expanded={open}
                              aria-controls={detailId}
                              aria-label={t("sources.row.expandAria", { name: s.name })}
                              onClick={() => toggleDetail(s.name)}
                              className={`grid flex-1 items-center gap-x-3 rounded text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-zinc-600 ${ROW_TEMPLATE}`}
                            >
                              <span
                                data-status={st.id}
                                title={t(`sources.status.${st.id}`)}
                                className={`h-2 w-2 rounded-full ${st.dot}`}
                              />
                              <span
                                className="truncate font-mono text-sm text-zinc-200"
                                title={s.name}
                              >
                                {s.name}
                              </span>
                              <span
                                className="truncate text-xs text-zinc-600"
                                title={s.fields[0] ?? s.archetype}
                              >
                                {s.fields[0] ?? s.archetype}
                              </span>
                              <span className="truncate text-right font-mono text-sm tabular-nums text-zinc-300">
                                {formatCount(s.health.covered_ips)}
                              </span>
                              <span className="truncate text-xs text-zinc-500">{fmtTime(s)}</span>
                            </button>
                            <div className="flex shrink-0 items-center gap-3">
                              {/* 未配置 token 源的入口(琥珀边);已配置/拉取失败均隐 */}
                              {tokenSt && !tokenSt.configured && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setTokenDraft("");   // 不回显既有值(API 也不出值)
                                    setTokenDialogFor(s.name);
                                  }}
                                  aria-label={t("sources.token.fillAria", { name: s.name })}
                                  className="rounded-md border border-amber-400/40 px-2.5 py-1 text-xs text-amber-400 transition-colors hover:bg-amber-400/10"
                                >
                                  {t("sources.token.fill")}
                                </button>
                              )}
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
                          </div>
                          {/* 行内简易对话框:密码型输入,保存即 PUT,成功即关;
                              不设 role=dialog(无焦点陷阱,伪语义) */}
                          {tokenSt && !tokenSt.configured && tokenDialogFor === s.name && (
                            <form
                              onSubmit={(e) => { e.preventDefault(); void handleTokenSave(tokenSt.env_var); }}
                              className="flex flex-wrap items-center gap-2 border-t border-zinc-900 bg-zinc-950/60 px-4 py-3 text-xs"
                            >
                              <span className="font-mono text-zinc-400">{tokenSt.env_var}</span>
                              <input
                                type="password"
                                // new-password:防浏览器把 token 存进站点密码管理器
                                autoComplete="new-password"
                                autoFocus
                                value={tokenDraft}
                                onChange={(e) => setTokenDraft(e.target.value)}
                                aria-label={t("sources.token.inputAria")}
                                className="w-56 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-zinc-200 focus:border-emerald-400 focus:outline-none"
                              />
                              <button
                                type="submit"
                                disabled={tokenBusy || !tokenDraft.trim()}
                                className="rounded-md border border-emerald-400/40 px-2 py-1 text-emerald-400 transition-colors hover:bg-emerald-400/10 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {t("sources.token.save")}
                              </button>
                              <button
                                type="button"
                                onClick={() => setTokenDialogFor(null)}
                                className="rounded-md border border-zinc-700 px-2 py-1 text-zinc-400 transition-colors hover:bg-zinc-800"
                              >
                                {t("sources.token.cancel")}
                              </button>
                            </form>
                          )}
                          {/* 详情层:r(声明)/θ+CI(实测)/评估 verdict/内容年龄·
                              刷新周期/feeds 芯片/最近错误 —— 按需查看 */}
                          {open && (
                            <div
                              role="region"
                              id={detailId}
                              aria-labelledby={`sources-row-${s.name}`}
                              className="space-y-1.5 border-t border-zinc-900 bg-zinc-950/60 px-4 py-3 text-xs"
                            >
                              <DetailRow label={t("sources.detail.r")}>
                                <span data-detail="r" className="font-mono">
                                  r {s.reliability.toFixed(2)}
                                </span>
                              </DetailRow>
                              {tokenSt?.configured && (
                                <DetailRow label={tokenSt.env_var}>
                                  <span data-detail="token" className="flex items-center gap-2">
                                    <span className="font-mono text-zinc-300">
                                      {t("sources.token.configured")}
                                      {tokenSt.tail4 ? ` ····${tokenSt.tail4}` : ""}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => void handleTokenClear(tokenSt.env_var)}
                                      aria-label={t("sources.token.clearAria", { name: tokenSt.env_var })}
                                      className="rounded border border-zinc-700 px-1.5 py-0.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
                                    >
                                      {t("sources.token.clear")}
                                    </button>
                                  </span>
                                </DetailRow>
                              )}
                              <DetailRow label={t("sources.detail.theta")}>
                                {ms && ms.theta != null ? (
                                  <span
                                    data-detail="theta"
                                    className="font-mono text-sky-400"
                                    title={t("sources.thetaTooltip")}
                                  >
                                    θ {ms.theta.toFixed(2)}
                                    {ms.ci_lo != null &&
                                      ` [${ms.ci_lo.toFixed(2)}–${ms.ci_hi!.toFixed(2)}]`}
                                  </span>
                                ) : (
                                  <span data-detail="theta" className="text-zinc-600">—</span>
                                )}
                              </DetailRow>
                              <DetailRow label={t("sources.detail.eval")}>
                                {s.eval ? (
                                  <span
                                    data-detail="eval"
                                    className={`rounded-md border px-2 py-0.5 ${evalBadgeClass(s.eval.verdict)}`}
                                    // NO-DATA:说明性 title(数据为空/坍塌)替代评估日期
                                    title={s.eval.verdict === "NO-DATA"
                                      ? t("sources.eval.noDataTitle")
                                      : s.eval.at}
                                  >
                                    {t("sources.eval." + s.eval.verdict.toLowerCase().replace(/-/g, "_"))}
                                  </span>
                                ) : (
                                  <span data-detail="eval" className="text-zinc-600">
                                    {t("sources.detail.evalNone")}
                                  </span>
                                )}
                              </DetailRow>
                              <DetailRow label={t("sources.detail.contentAge")}>
                                <span data-detail="age" className="font-mono tabular-nums">
                                  {ageStr}
                                </span>
                              </DetailRow>
                              <DetailRow label={t("sources.detail.refreshPeriod")}>
                                <span data-detail="period" className="font-mono tabular-nums">
                                  {periodStr}
                                </span>
                              </DetailRow>
                              {/* 取源地址(wave-2 task 3):有 url → 新窗口链接,>64 字符截断 +
                                  title 全文;null → —。break-all 防长 URL 撑破详情层 */}
                              <DetailRow label={t("sources.detail.url")}>
                                {s.url ? (
                                  <a
                                    href={s.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    data-detail="url"
                                    title={s.url}
                                    className="break-all text-zinc-400 transition-colors hover:text-zinc-200"
                                  >
                                    {s.url.length > 64 ? s.url.slice(0, 64) + "…" : s.url}
                                  </a>
                                ) : (
                                  <span data-detail="url" className="text-zinc-600">—</span>
                                )}
                              </DetailRow>
                              {s.health.feeds && s.health.feeds.length > 0 && (
                                <DetailRow label={t("sources.detail.feeds")}>
                                  <span className="flex flex-wrap gap-x-3 gap-y-0.5">
                                    {s.health.feeds.map((f) => (
                                      <span
                                        key={f.name}
                                        data-feed={f.name}
                                        data-stale={f.is_stale}
                                        className={f.is_stale ? "text-red-400" : "text-zinc-400"}
                                      >
                                        {f.name}
                                      </span>
                                    ))}
                                  </span>
                                </DetailRow>
                              )}
                              {s.health.error && (
                                <DetailRow label={t("sources.detail.lastError")}>
                                  <span data-detail="error" className="text-red-400">
                                    {s.health.error}
                                  </span>
                                </DetailRow>
                              )}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
