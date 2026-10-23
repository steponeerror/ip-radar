import { useCallback, useEffect, useState } from "react";
import { useI18n } from "../i18n";
import {
  getOpsItems, readOpsItem, postOpsReview,
  type ApiError, type OpsItem, type OpsItemReviewResult, type OpsReviewVerdict,
} from "../api";
import { opsErrorText } from "./opsErrorText";
import { relTime } from "./opsTable";
import { SectionHead } from "./OpsSectionHead";
import { useArrivalNow } from "./useArrivalNow";

// P1 T4 审阅面(票 #156,spec #152 §4;ADR 0006 术语双层:审阅 = 旧「裁决」
// 的 UI 别名,动作面从旧包(逐字选建议行)迁到结构化条目)。条目列表 =
// GET /api/ops/items,后端已排序(active 先见 → severity 降序 → cause_group
// 升序 → 新条目先见;排序真源 = _ops_items.list_items)——前端不重排,
// 渲染序 = 响应序。每行四键(同意/修改/忽略/稍后)走 POST review:
// - 按钮文案写后果不写是/否(spec #152 §4):同意 = 「同意·执行:{后果}」
//   或集外「同意·立项」;稍后 = 「稍后·明天/下周」直发。
// - 无默认选中(NN/g 铁律):四键零预选,编辑器零 focus/autofill,忽略
//   原因初始为空。
// - 终态条目(done/dismissed)后端拒审(422,T1 状态机「复开 = 新条目链
//   指」)——前端不渲染四键,只留只读详情,不送明知必拒的请求。
// 成功后列表重拉(操作反馈);失败走 opsErrorText 人话化(422/404/500 分诊)。

// 可逆闭集镜像(按钮后果文案分支用):真源 = backend/ipdb/_ops_review.py
// REVERSIBLE_ACTIONS(spec #152 §3),此处对拍镜像不另立第二拼写;闭集外的
// action 一律按「仅立项」呈现,后端响应 proposal_only 恒标(渲染面不重推导
// 闭集语义——响应字段才是裁决真源,此处镜像只服务按钮预写的后果文案)。
const REVERSIBLE_ACTIONS: ReadonlySet<string> =
  new Set(["retry_download", "disable_source", "pause_source"]);
// 终态闭集(四键不渲染):真源 = _ops_items ITEM_STATUSES 的两终态。
const TERMINAL_STATUSES = new Set(["done", "dismissed"]);

// 本地时刻(mono 数据面,YYYY-MM-DD HH:mm);title 挂 ISO 原文由调用方施加。
function fmtLocal(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso; // 不可解析 → 原样(不猜)
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function OpsReviewSection({ onUnauthorized }: {
  onUnauthorized: () => void;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<OpsItem[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  // 相对时间基准 = 列表抵达时刻(useArrivalNow,Date.now 不入 render)
  const [now, markArrived] = useArrivalNow();
  // 展开态:一行一开(openId);详情全文惰性取
  const [openId, setOpenId] = useState<string | null>(null);
  const [detailText, setDetailText] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  // 编辑器态(单实例,随展开行切换而重置;无 focus/autofill——NN/g)
  const [editor, setEditor] = useState<"modify" | "ignore" | null>(null);
  const [argsDraft, setArgsDraft] = useState("");
  const [reason, setReason] = useState("");
  // 提交态与回执
  const [busyId, setBusyId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, OpsItemReviewResult>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const failWith = (set: (s: string) => void, fallback: string) => (e: unknown) => {
    if ((e as ApiError).status === 401) { onUnauthorized(); return; }
    set(opsErrorText(t, e, fallback));
  };

  const load = useCallback(async () => {
    setListError(null);
    try {
      setItems(await getOpsItems());
      markArrived();
    } catch (e) {
      failWith(setListError, t("ops.review.loadFailed"))(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, onUnauthorized, markArrived]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  const openItem = (it: OpsItem) => {
    if (openId === it.id) return; // 已开行重复点击 = 无操作
    setOpenId(it.id);
    setDetailText(null); setDetailError(null);
    setEditor(null); setReason("");
    setActionError(null);
    setArgsDraft(JSON.stringify(it.args, null, 2)); // 修改编辑器预填 = 条目现值
    readOpsItem(it.id)
      .then(setDetailText)
      .catch(failWith(setDetailError, t("ops.review.loadFailed")));
  };

  const submit = (it: OpsItem, verdict: OpsReviewVerdict,
                  extra?: { args?: Record<string, unknown>; reason?: string; wakeAt?: string }) => {
    if (busyId) return;
    setBusyId(it.id); setActionError(null);
    postOpsReview(it.id, verdict, extra)
      .then((r) => {
        setResults((m) => ({ ...m, [it.id]: r }));
        setEditor(null); setReason(""); // 修改编辑器重开时由 openItem 重预填现值
        load(); // 操作反馈:成功后列表重拉
      })
      .catch(failWith(setActionError, t("ops.review.failed")))
      .finally(() => setBusyId(null));
  };

  // 修改载荷:JSON 文本域 → 对象;非法 JSON/非对象 → null(提交禁用 + 提示)
  let parsedArgs: Record<string, unknown> | null = null;
  if (editor === "modify" && argsDraft.trim()) {
    try {
      const v: unknown = JSON.parse(argsDraft);
      if (typeof v === "object" && v !== null && !Array.isArray(v)) parsedArgs = v as Record<string, unknown>;
    } catch { /* 提示走 argsInvalid 分支 */ }
  }

  // 同意按钮后果文案:闭集内 = 执行后果(词条映射三动作);集外 = 仅立项
  const agreeLabel = (it: OpsItem) =>
    REVERSIBLE_ACTIONS.has(it.action)
      ? t("ops.review.agree.execute", { action: t(`ops.review.act.${it.action}`) })
      : t("ops.review.agree.proposal");

  // 回执行(verdict 分面;precedent/queued 只在响应携带时追加——宁少算)
  const resultLine = (it: OpsItem, r: OpsItemReviewResult) => {
    const parts: string[] = [];
    if (r.verdict === "snooze") {
      parts.push(t("ops.review.result.snoozed", { when: fmtLocal(r.wake_at ?? "") }));
    } else if (r.verdict === "ignore") {
      parts.push(t("ops.review.result.ignored", { precedent: r.precedent ?? "" }));
    } else if (r.proposal_only) {
      parts.push(t("ops.review.result.proposal", { precedent: r.precedent ?? "" }));
    } else {
      parts.push(t("ops.review.result.executed", {
        action: t(`ops.review.act.${it.action}`), precedent: r.precedent ?? "",
      }));
    }
    if (r.queue_appended) parts.push(t("ops.review.result.queued"));
    return parts.join(" ");
  };

  return (
    <section aria-label={t("ops.review.title")} className="mt-8">
      <SectionHead title={t("ops.review.title")} count={items?.length ?? null}>
        <button
          type="button"
          onClick={load}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.review.refresh")}
        </button>
      </SectionHead>
      {listError && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {listError}
        </p>
      )}
      {/* 空态:基准「暂无」式居中提示(硬规⑥);加载中 items=null 不显 0 */}
      {items != null && items.length === 0 && !listError && (
        <div className="mt-3 rounded-md border border-zinc-800">
          <p className="px-3 py-6 text-center text-xs text-zinc-500">{t("ops.review.empty")}</p>
        </div>
      )}
      {items != null && items.length > 0 && (
        <ul className="mt-3 divide-y divide-zinc-800 rounded-md border border-zinc-800">
          {/* 行信息 = 严重度点/动作/源/根因组/摘要(impact)/时间;序 = 后端
              响应序(不重排);mono 数据(mono 分轨)与 UI 文案分轨 */}
          {items.map((it) => {
            const rt = relTime(it.modified, now);
            const sev = t(`ops.review.sev.${it.severity}`);
            const sevShown = sev !== `ops.review.sev.${it.severity}` ? sev : it.severity;
            const source = typeof it.args?.source === "string" ? it.args.source : "—";
            const terminal = TERMINAL_STATUSES.has(it.status);
            return (
              <li key={it.id}>
                <button
                  type="button"
                  aria-expanded={openId === it.id}
                  onClick={() => (openId === it.id ? setOpenId(null) : openItem(it))}
                  className="flex w-full items-baseline gap-x-3 px-4 py-2.5 text-left transition-colors hover:bg-zinc-900"
                >
                  {/* 严重度点:红/琥珀仅事件性警示(硬规⑤);title 承载可读名 */}
                  <span
                    aria-label={sevShown}
                    title={sevShown}
                    className={
                      it.severity === "high" ? "text-red-400"
                      : it.severity === "medium" ? "text-amber-400"
                      : "text-zinc-500"
                    }
                  >
                    ●
                  </span>
                  <span className="whitespace-nowrap font-mono text-sm text-emerald-400">{it.action}</span>
                  <span className="whitespace-nowrap font-mono text-xs text-zinc-500">{source}</span>
                  <span className="whitespace-nowrap font-mono text-xs text-zinc-500">{it.cause_group}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-zinc-300" title={it.impact}>
                    {it.impact}
                  </span>
                  {/* 稍后 chip 不带唤醒时刻:列表契约(OpsItemOut 十字段)不含
                      wake_at,时刻在条目全文详情里(宁少算,不为装饰扩契约) */}
                  {it.status === "snoozed" && (
                    <span className="whitespace-nowrap font-mono text-xs text-zinc-500">
                      {t("ops.review.status.snoozed")}
                    </span>
                  )}
                  {it.status === "done" && (
                    <span className="whitespace-nowrap text-xs text-zinc-500">{t("ops.review.status.done")}</span>
                  )}
                  {it.status === "dismissed" && (
                    <span className="whitespace-nowrap text-xs text-zinc-500">{t("ops.review.status.dismissed")}</span>
                  )}
                  <span className="ml-auto whitespace-nowrap font-mono text-xs text-zinc-500" title={rt.title}>
                    {t(rt.key, rt.vars)}
                  </span>
                </button>
                {openId === it.id && (
                  <div className="px-4 pb-4">
                    {/* 详情 = 条目全文逐字(frontmatter+正文,证据不灭失) */}
                    {detailError && (
                      <p role="alert" className="mt-2 text-xs text-red-400">{detailError}</p>
                    )}
                    {detailText != null ? (
                      <pre className="max-h-72 overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-300">
                        {detailText}
                      </pre>
                    ) : (
                      <p className="mt-2 text-xs text-zinc-500">{t("sources.pageLoading")}</p>
                    )}
                    {/* 四键:终态行不渲染(后端 422,不送明知必拒的请求) */}
                    {!terminal && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={busyId === it.id}
                          onClick={() => submit(it, "agree")}
                          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {agreeLabel(it)}
                        </button>
                        <button
                          type="button"
                          disabled={busyId === it.id}
                          onClick={() => { setEditor(editor === "modify" ? null : "modify"); setActionError(null); }}
                          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {t("ops.review.modify")}
                        </button>
                        <button
                          type="button"
                          disabled={busyId === it.id}
                          onClick={() => { setEditor(editor === "ignore" ? null : "ignore"); setActionError(null); }}
                          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {t("ops.review.ignore")}
                        </button>
                        <button
                          type="button"
                          disabled={busyId === it.id}
                          onClick={() => submit(it, "snooze", { wakeAt: new Date(Date.now() + 86_400_000).toISOString() })}
                          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {t("ops.review.snooze.tomorrow")}
                        </button>
                        <button
                          type="button"
                          disabled={busyId === it.id}
                          onClick={() => submit(it, "snooze", { wakeAt: new Date(Date.now() + 7 * 86_400_000).toISOString() })}
                          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {t("ops.review.snooze.nextWeek")}
                        </button>
                      </div>
                    )}
                    {/* 修改编辑器:JSON 文本域(简单优先),预填 = 条目现值;
                        非法 JSON 禁提交(后端 422 之前先拦) */}
                    {editor === "modify" && (
                      <div className="mt-3">
                        <label className="flex flex-col gap-1 text-xs text-zinc-400">
                          {t("ops.review.modify.editorLabel")}
                          <textarea
                            aria-label={t("ops.review.modify.editorLabel")}
                            rows={5}
                            value={argsDraft}
                            onChange={(e) => setArgsDraft(e.target.value)}
                            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
                          />
                        </label>
                        {argsDraft.trim() && !parsedArgs && (
                          <p role="alert" className="mt-1 text-[11px] text-amber-400/90">
                            {t("ops.review.modify.invalid")}
                          </p>
                        )}
                        <button
                          type="button"
                          disabled={!parsedArgs || busyId === it.id}
                          onClick={() => parsedArgs && submit(it, "modify", { args: parsedArgs })}
                          className="mt-2 rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {t("ops.review.modify.send")}
                        </button>
                      </div>
                    )}
                    {/* 忽略编辑器:原因必填(空禁提交),placeholder = 示范风格 */}
                    {editor === "ignore" && (
                      <div className="mt-3">
                        <label className="flex flex-col gap-1 text-xs text-zinc-400">
                          {t("ops.review.ignore.reasonLabel")}
                          <input
                            type="text"
                            aria-label={t("ops.review.ignore.reasonLabel")}
                            placeholder={t("ops.review.ignore.placeholder")}
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
                          />
                        </label>
                        <button
                          type="button"
                          disabled={!reason.trim() || busyId === it.id}
                          onClick={() => submit(it, "ignore", { reason: reason.trim() })}
                          className="mt-2 rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400 disabled:opacity-40"
                        >
                          {t("ops.review.ignore.send")}
                        </button>
                      </div>
                    )}
                    {/* 回执与失败面 */}
                    {results[it.id] && (
                      <p role="status" className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-400">
                        {resultLine(it, results[it.id])}
                      </p>
                    )}
                    {actionError && (
                      <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
                        {actionError}
                      </p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
