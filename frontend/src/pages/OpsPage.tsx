import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { useTasks } from "../tasks/useTasks";
import { Modal } from "../components/Modal";
import {
  startOpsRound, readOpsLedger, listOpsPrecedents, readOpsPrecedent, exportOpsPrecedents,
  getOpsAgentConfig, putOpsAgentConfig,
  type ApiError, type OpsAgentConfig, type OpsRoundType, type TaskState,
} from "../api";
import OpsPackagesSection from "./OpsPackagesSection";
import { opsErrorText, roundErrorText } from "./opsErrorText";

// P4 admin 第四 tab「运营」(票 #136):①轮次触发 ②裁决包区(OpsPackagesSection)
// ③台账只读 ④判例浏览+检索只读 ⑤导出。裁⑦:顶部恒挂「仅立项」横幅;无在线
// 编辑、无重复面板。进度面 = 任务链徽章/mini bar 形态复用(BatchMiniBar 同款
// 视觉),数据源 = TaskProvider 的 ops 任务(source="ops",running 相位 +
// task_log 行)。

// 健康轮一键的非空输入(P2 路由 422 门:input 恒非空;健康轮指令面自含于
// prompts/health-system.md,输入仅占位——钉常量防 i18n 漂移)。
const HEALTH_ROUND_INPUT = "health";

const STATE_BADGE: Record<string, string> = {
  running: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
  done: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
  failed: "text-red-400 border-red-400/30 bg-red-400/10",
  cancelled: "text-zinc-500 border-zinc-700 bg-zinc-800/50",
};

const STATE_KEY: Record<string, string> = {
  running: "ops.round.state.running",
  done: "ops.round.state.done",
  failed: "ops.round.state.failed",
  cancelled: "ops.round.state.cancelled",
};

function RoundPanel({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const { tasks, logs } = useTasks();
  const [discoverInput, setDiscoverInput] = useState("");
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const opsTask = tasks.find((tk) => tk.source === "ops");
  const logLines = opsTask ? logs[opsTask.id] ?? [] : [];

  const start = (type: OpsRoundType) => {
    if (busy) return;
    const input = type === "health" ? HEALTH_ROUND_INPUT : discoverInput.trim();
    if (!input) { setTriggerError(t("ops.round.inputRequired")); return; }
    setTriggerError(null);
    setBusy(true);
    startOpsRound(type, input)
      .catch((e) => {
        if ((e as ApiError).status === 401) { onUnauthorized(); return; }
        setTriggerError(opsErrorText(t, e, t("ops.round.triggerFailed")));
      })
      .finally(() => setBusy(false));
  };

  return (
    <section aria-label={t("ops.round.title")}>
      <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">
        {t("ops.round.title")}
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => start("health")}
          className="rounded-md bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-transform hover:scale-[1.02] disabled:opacity-40"
        >
          {t("ops.round.health")}
        </button>
        <input
          type="search"
          aria-label={t("ops.round.discoverPlaceholder")}
          placeholder={t("ops.round.discoverPlaceholder")}
          value={discoverInput}
          onChange={(e) => setDiscoverInput(e.target.value)}
          className="min-w-64 flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => start("discover")}
          className="rounded-md border border-emerald-600/50 px-4 py-1.5 text-xs text-emerald-400 transition-colors hover:border-emerald-500 disabled:opacity-40"
        >
          {t("ops.round.discover")}
        </button>
      </div>
      {triggerError && (
        <p role="alert" className="mt-2 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {triggerError}
        </p>
      )}
      {/* 进度面:任务链徽章 + mini bar(运行中不定长脉冲)+ task_log 行尾 */}
      {opsTask && (
        <div className="mt-3 rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
          <div className="flex items-center gap-3">
            <span className={`rounded border px-2 py-0.5 font-mono text-[11px] ${STATE_BADGE[opsTask.state] ?? STATE_BADGE.cancelled}`}>
              {t(STATE_KEY[opsTask.state] ?? "ops.round.state.running")}
            </span>
            {opsTask.state === "running" && (
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-zinc-800">
                <span className="block h-full w-full animate-pulse rounded-full bg-emerald-500" />
              </span>
            )}
          </div>
          {opsTask.state === "failed" && (
            <p role="alert" className="mt-2 text-xs text-red-400">
              {roundErrorText(t, opsTask.error_code, opsTask.error)}
            </p>
          )}
          {logLines.length > 0 && (
            <div className="mt-2">
              <p className="text-[11px] text-zinc-500">{t("ops.round.log")}</p>
              <pre className="mt-1 max-h-40 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-2 font-mono text-[11px] leading-relaxed text-zinc-400">
                {logLines.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </pre>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// 票 #140「agent 配置」子区:两轮次模型下拉(闭集由后端 GET allowed_models
// 驱动,单一真相源)+ zai key write-only 输入(状态只显 configured+tail4,
// 永不回填;保存成功后清空)。改完即生效由后端每次 spawn 现读保证。
function ConfigSection({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<OpsAgentConfig | null>(null);
  const [modelHealth, setModelHealth] = useState("");
  const [modelDiscover, setModelDiscover] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const apply = (c: OpsAgentConfig) => {
    setCfg(c);
    setModelHealth(c.model_health);
    setModelDiscover(c.model_discover);
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      apply(await getOpsAgentConfig());
    } catch (e) {
      if ((e as ApiError).status === 401) { onUnauthorized(); return; }
      setError(opsErrorText(t, e, t("ops.cfg.loadFailed")));
    }
  }, [t, onUnauthorized]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  const save = () => {
    if (busy || !modelHealth || !modelDiscover) return;
    setBusy(true);
    setSaved(false);
    setError(null);
    putOpsAgentConfig({
      model_health: modelHealth,
      model_discover: modelDiscover,
      ...(keyInput.trim() ? { zai_api_key: keyInput.trim() } : {}),
    })
      .then((c) => {
        apply(c);
        setKeyInput(""); // write-only:保存后即清,后端永不回填
        setSaved(true);
      })
      .catch((e) => {
        if ((e as ApiError).status === 401) { onUnauthorized(); return; }
        setError(opsErrorText(t, e, t("ops.cfg.saveFailed")));
      })
      .finally(() => setBusy(false));
  };

  return (
    <section aria-label={t("ops.cfg.title")} className="mt-8">
      <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">
        {t("ops.cfg.title")}
      </h2>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}
      {cfg && (
        <div className="mt-3 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            {t("ops.cfg.modelHealth")}
            <select
              value={modelHealth}
              onChange={(e) => setModelHealth(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
            >
              {cfg.allowed_models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            {t("ops.cfg.modelDiscover")}
            <select
              value={modelDiscover}
              onChange={(e) => setModelDiscover(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
            >
              {cfg.allowed_models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            {t("ops.cfg.keyLabel")}
            <input
              type="password"
              autoComplete="off"
              placeholder={t("ops.cfg.keyPlaceholder")}
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              className="min-w-56 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
            />
            <span className="text-[11px] text-zinc-500">
              {cfg.zai_api_key.configured
                ? t("ops.cfg.keyConfigured", { tail4: cfg.zai_api_key.tail4 ?? "" })
                : t("ops.cfg.keyMissing")}
            </span>
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={save}
            className="rounded-md bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-transform hover:scale-[1.02] disabled:opacity-40"
          >
            {t("ops.cfg.save")}
          </button>
        </div>
      )}
      {saved && (
        <p className="mt-2 text-xs text-emerald-400">{t("ops.cfg.saved")}</p>
      )}
    </section>
  );
}

// 台账 markdown 表(| 日期 | 轮次 | model | 用量 | 备注 |)→ 只读表；
// 分隔行(|---|)跳过；表外行(标题等)不渲染(节标题已在面内)。
function ledgerRows(text: string): string[][] {
  return text
    .split("\n")
    .filter((l) => l.trim().startsWith("|"))
    .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
    .filter((cells) => !cells.every((c) => /^:?-{3,}:?$/.test(c)));
}

function LedgerSection({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setText(await readOpsLedger());
    } catch (e) {
      if ((e as ApiError).status === 401) { onUnauthorized(); return; }
      setError(opsErrorText(t, e, t("ops.ledger.loadFailed")));
    }
  }, [t, onUnauthorized]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  const rows = text != null ? ledgerRows(text) : [];

  return (
    <section aria-label={t("ops.ledger.title")} className="mt-8">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">
          {t("ops.ledger.title")}
        </h2>
        <button type="button" onClick={load} className="text-xs text-zinc-500 transition-colors hover:text-zinc-300">
          {t("ops.ledger.refresh")}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}
      {rows.length > 0 && (
        <div className="mt-3 max-h-72 overflow-auto rounded-md border border-zinc-800">
          <table className="w-full text-left text-xs">
            {rows[0] && (
              <thead className="sticky top-0 bg-zinc-900 font-mono text-[11px] text-zinc-500">
                <tr>
                  {rows[0].map((h, i) => (
                    <th key={i} scope="col" className="px-3 py-1.5 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody className="divide-y divide-zinc-800/60 font-mono text-zinc-400">
              {rows.slice(1).map((cells, r) => (
                <tr key={r}>
                  {cells.map((c, i) => (
                    <td key={i} className="px-3 py-1.5">{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function PrecedentsSection({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const [kws, setKws] = useState("");
  const [names, setNames] = useState<string[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [precName, setPrecName] = useState<string | null>(null);
  const [precText, setPrecText] = useState<string | null>(null);
  const [precError, setPrecError] = useState<string | null>(null);

  const failWith = (set: (s: string) => void, fallback: string) => (e: unknown) => {
    if ((e as ApiError).status === 401) { onUnauthorized(); return; }
    set(opsErrorText(t, e, fallback));
  };

  const load = useCallback(async (q: string) => {
    setListError(null);
    try {
      setNames(await listOpsPrecedents(q));
    } catch (e) {
      failWith(setListError, t("ops.prec.loadFailed"))(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, onUnauthorized]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(""); }, [load]);

  const openPrecedent = (name: string) => {
    setPrecName(name); setPrecText(null); setPrecError(null);
    readOpsPrecedent(name)
      .then(setPrecText)
      .catch(failWith(setPrecError, t("ops.prec.loadFailed")));
  };

  const onExport = () => {
    setExportError(null);
    exportOpsPrecedents()
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "ops-precedents-export.zip";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(failWith(setExportError, t("ops.export.failed")));
  };

  return (
    <section aria-label={t("ops.prec.title")} className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">
          {t("ops.prec.title")}
        </h2>
        <button
          type="button"
          onClick={onExport}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.export")}
        </button>
      </div>
      <div className="mt-3 flex gap-2">
        <input
          type="search"
          aria-label={t("ops.prec.searchPlaceholder")}
          placeholder={t("ops.prec.searchPlaceholder")}
          value={kws}
          onChange={(e) => setKws(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") load(kws.trim()); }}
          className="min-w-48 flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => load(kws.trim())}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.prec.search")}
        </button>
      </div>
      {listError && (
        <p role="alert" className="mt-2 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {listError}
        </p>
      )}
      {names != null && names.length === 0 && !listError && (
        <p className="mt-3 text-sm text-zinc-500">{t("ops.prec.empty")}</p>
      )}
      {names != null && names.length > 0 && (
        <ul className="mt-3 max-h-72 divide-y divide-zinc-800 overflow-auto rounded-md border border-zinc-800">
          {names.map((n) => (
            <li key={n}>
              <button
                type="button"
                onClick={() => openPrecedent(n)}
                className="w-full px-3 py-1.5 text-left font-mono text-xs text-emerald-400 transition-colors hover:bg-zinc-900"
              >
                {n}
              </button>
            </li>
          ))}
        </ul>
      )}
      {exportError && (
        <p role="alert" className="mt-2 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {exportError}
        </p>
      )}
      <Modal
        open={precName != null}
        title={precName ?? ""}
        onClose={() => { setPrecName(null); setPrecText(null); setPrecError(null); }}
        closeLabel={t("ops.prec.close")}
      >
        {precError ? (
          <p role="alert" className="text-xs text-red-400">{precError}</p>
        ) : precText != null ? (
          <pre className="max-h-[60vh] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-300">
            {precText}
          </pre>
        ) : (
          <p className="text-xs text-zinc-500">{t("sources.pageLoading")}</p>
        )}
      </Modal>
    </section>
  );
}

export default function OpsPage({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const { tasks } = useTasks();
  const opsTask = tasks.find((tk) => tk.source === "ops");
  // 轮次收口(running → done/failed/cancelled)→ 裁决包列表重拉(新包先见)
  const prevRef = useRef<string | undefined>(undefined);
  const [roundTick, setRoundTick] = useState(0);
  useEffect(() => {
    const cur = opsTask?.state as TaskState["state"] | undefined;
    const prev = prevRef.current;
    prevRef.current = cur;
    if (prev === "running" && cur && cur !== "running") setRoundTick((n) => n + 1);
  }, [opsTask?.state]);

  return (
    <div>
      {/* 裁⑦ 恒挂:全部建议仅立项,零自动执行 */}
      <p className="rounded-md border border-amber-500/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-400">
        {t("ops.disclaimer")}
      </p>
      <div className="mt-6">
        <RoundPanel onUnauthorized={onUnauthorized} />
        <ConfigSection onUnauthorized={onUnauthorized} />
        <OpsPackagesSection onUnauthorized={onUnauthorized} roundTick={roundTick} />
        <LedgerSection onUnauthorized={onUnauthorized} />
        <PrecedentsSection onUnauthorized={onUnauthorized} />
      </div>
    </div>
  );
}
