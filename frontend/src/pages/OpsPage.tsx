import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { useTasks } from "../tasks/useTasks";
import { Modal } from "../components/Modal";
import {
  readOpsLedger, listOpsPrecedents, readOpsPrecedent, exportOpsPrecedents,
  getOpsAgentConfig, putOpsAgentConfig,
  type ApiError, type OpsAgentConfig, type TaskState,
} from "../api";
import OpsPackagesSection from "./OpsPackagesSection";
import { OpsCockpit, OpsPastRounds } from "./OpsCockpit";
import { SectionHead } from "./OpsSectionHead";
import { ledgerRows, splitUsage } from "./opsLedger";
import { LEDGER_COL_KEYS, relTime, noteText } from "./opsTable";
import { opsErrorText } from "./opsErrorText";

// P4 admin 第四 tab「运营」(票 #136):①轮次触发 ②裁决包区(OpsPackagesSection)
// ③台账只读 ④判例浏览+检索只读 ⑤导出。裁⑦:顶部恒挂「仅立项」注记;无在线
// 编辑、无重复面板。进度面 = 任务链徽章/mini bar 形态复用(BatchMiniBar 同款
// 视觉),数据源 = TaskProvider 的 ops 任务(source="ops",running 相位 +
// task_log 行)。
// 票 #142 子 tab 重组:轮次(默认)/裁决(OpsPackagesSection)/档案(台账+
// 判例,只读审计面)/设置(#140 配置)。票 #148:轮次 tab = 驾驶舱单卡
// (触发入卡,OpsCockpit)+ 过往轮次表;原独立「轮次」触发节撤除。

// 票 #140「agent 配置」子区(票 #142 起驻「设置」子 tab;票 #143 多供应商):
// 两轮次 {provider, model} 双下拉(目录由后端 GET catalog 驱动,单一真相源;
// 缺 key 的 provider 在下拉内标「需先填 key」——零硬闸只标注不阻断,ADR 0005
// 裁③)+ 模型行参考成本提示(cost 来自目录数据,无价即隐)+ 逐 provider key
// write-only 输入(状态只显 configured+tail4,永不回填;保存成功后清空)。
// 改完即生效由后端每次 spawn 现读保证;catalog_source=fallback 显式提示
// (不伪装动态)。
function ConfigSection({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<OpsAgentConfig | null>(null);
  const [modelHealth, setModelHealth] = useState("");
  const [modelDiscover, setModelDiscover] = useState("");
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
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
    const api_keys: Record<string, string> = {};
    for (const [pid, raw] of Object.entries(keyInputs)) {
      const key = raw.trim();
      if (key) api_keys[pid] = key; // 空串 = 该家保持不改(无清除面)
    }
    setBusy(true);
    setSaved(false);
    setError(null);
    putOpsAgentConfig({
      model_health: modelHealth,
      model_discover: modelDiscover,
      ...(Object.keys(api_keys).length ? { api_keys } : {}),
    })
      .then((c) => {
        apply(c);
        setKeyInputs({}); // write-only:保存后即清,后端永不回填
        setSaved(true);
      })
      .catch((e) => {
        if ((e as ApiError).status === 401) { onUnauthorized(); return; }
        setError(opsErrorText(t, e, t("ops.cfg.saveFailed")));
      })
      .finally(() => setBusy(false));
  };

  // 轮次双下拉(渲染助手非组件,避免重挂我):现值 qualified 拆
  // {provider, model};provider 切换级联模型落该家首项;现值家/型不在目录
  // (如兜底闭集期存了别家)时补现值选项防空选。
  const renderRound = (kind: "health" | "discover") => {
    if (!cfg) return null;
    const value = kind === "health" ? modelHealth : modelDiscover;
    const onChange = kind === "health" ? setModelHealth : setModelDiscover;
    const slash = value.indexOf("/");
    const pid = slash >= 0 ? value.slice(0, slash) : "";
    const mid = slash >= 0 ? value.slice(slash + 1) : value;
    const inCatalog = (p: string) => Object.prototype.hasOwnProperty.call(cfg.catalog, p);
    const providers = pid && !inCatalog(pid)
      ? [...Object.keys(cfg.catalog), pid] : Object.keys(cfg.catalog);
    const rawEntries = cfg.catalog[pid] ?? [];
    const entries = rawEntries.some((e) => e.id === mid)
      ? rawEntries : [{ id: mid, name: mid, cost: null }, ...rawEntries];
    const cost = entries.find((e) => e.id === mid)?.cost;
    const showCost = cost && cost.input != null && cost.output != null;
    const needsKey = (p: string) => !cfg.api_keys[p]?.configured;
    return (
      <div key={kind} className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-zinc-400">
          {kind === "health" ? t("ops.cfg.providerHealth") : t("ops.cfg.providerDiscover")}
          <select
            value={pid}
            onChange={(e) => {
              const next = e.target.value;
              const nextEntries = cfg.catalog[next] ?? entries;
              onChange(`${next}/${nextEntries[0]?.id ?? mid}`); // 级联落首家
            }}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
          >
            {providers.map((p) => (
              <option key={p} value={p}>
                {needsKey(p) ? `${p} ${t("ops.cfg.needsKey")}` : p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-zinc-400">
          {kind === "health" ? t("ops.cfg.modelHealth") : t("ops.cfg.modelDiscover")}
          <select
            value={mid}
            onChange={(e) => onChange(`${pid}/${e.target.value}`)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
          >
            {entries.map((m) => <option key={m.id} value={m.id}>{m.id}</option>)}
          </select>
          {showCost && (
            <span className="text-[11px] text-zinc-500">
              {t("ops.cfg.costHint", {
                input: String(cost!.input),
                output: String(cost!.output),
              })}
            </span>
          )}
        </label>
      </div>
    );
  };

  // key 面行序 = 目录家 ∪ 已配置家(别家 key 在目录消失时状态仍可见,诚实呈现)
  const keyProviders = cfg
    ? [...new Set([...Object.keys(cfg.catalog), ...Object.keys(cfg.api_keys)])]
    : [];

  return (
    <section aria-label={t("ops.cfg.title")}>
      {/* 票 #147 节头行规范;设置面重做(基线/保存全部/key 搜索)归 #150 */}
      <SectionHead title={t("ops.cfg.title")} />
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}
      {cfg && (
        <div className="mt-3 flex flex-col gap-3">
          {cfg.catalog_source === "fallback" && (
            <p className="text-[11px] text-amber-400/90">{t("ops.cfg.fallbackNote")}</p>
          )}
          <div className="flex flex-wrap items-end gap-4">
            {renderRound("health")}
            {renderRound("discover")}
            <button
              type="button"
              disabled={busy}
              onClick={save}
              className="rounded-md bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-transform hover:scale-[1.02] disabled:opacity-40"
            >
              {t("ops.cfg.save")}
            </button>
          </div>
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">
              {t("ops.cfg.keysTitle")}
            </h3>
            <div className="mt-2 flex flex-wrap items-start gap-4">
              {keyProviders.map((pid) => {
                const st = cfg.api_keys[pid];
                return (
                  <label key={pid} className="flex flex-col gap-1 text-xs text-zinc-400">
                    <span className="font-mono">{pid}</span>
                    <input
                      type="password"
                      autoComplete="off"
                      aria-label={pid}
                      placeholder={t("ops.cfg.keyPlaceholder")}
                      value={keyInputs[pid] ?? ""}
                      onChange={(e) =>
                        setKeyInputs((v) => ({ ...v, [pid]: e.target.value }))}
                      className="min-w-56 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
                    />
                    <span className="text-[11px] text-zinc-500">
                      {st?.configured
                        ? t("ops.cfg.keyConfigured", { tail4: st.tail4 ?? "" })
                        : t("ops.cfg.keyMissing")}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}
      {saved && (
        <p className="mt-2 text-xs text-emerald-400">{t("ops.cfg.saved")}</p>
      )}
    </section>
  );
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

  const rows = text != null ? ledgerRows(text) : []; // 纯数据行(表头已在解析跳过)

  return (
    <section aria-label={t("ops.ledger.title")}>
      <SectionHead title={t("ops.ledger.title")}>
        {/* 裸文字链接 → 描边按钮(票 #147;硬规④次级动作一律描边) */}
        <button
          type="button"
          onClick={load}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.ledger.refresh")}
        </button>
      </SectionHead>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}
      {rows.length > 0 && (
        <div className="mt-3 max-h-72 overflow-auto rounded-md border border-zinc-800">
          {/* 票 #148:台账表走表格统一件——ops.col.* 中文列名(与轮次表同集,
              T4 冻结表头不再入 DOM)+ 用量/成本右对齐 + 相对时间 title +
              备注人话化(title 留原文,证据不灭失) */}
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-zinc-900 font-mono text-[11px] text-zinc-500">
              <tr>
                {LEDGER_COL_KEYS.map((k) => (
                  <th
                    key={k}
                    scope="col"
                    className={`px-3 py-1.5 font-medium${k === "usage" || k === "cost" ? " text-right" : ""}`}
                  >
                    {t(`ops.col.${k}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 font-mono text-zinc-400">
              {rows.map((cells, r) => {
                const { usage, cost } = splitUsage(cells[3] ?? "");
                const rt = relTime(cells[0] ?? "", Date.now());
                const note = cells[4] ?? "";
                const humanNote = noteText(t, note);
                return (
                  <tr key={r}>
                    <td className="px-3 py-1.5" title={rt.title}>{t(rt.key, rt.vars)}</td>
                    <td className="px-3 py-1.5">{cells[1]}</td>
                    <td className="px-3 py-1.5">{cells[2]}</td>
                    <td className="px-3 py-1.5 text-right">{usage}</td>
                    <td className="px-3 py-1.5 text-right">{cost ?? "—"}</td>
                    <td className="px-3 py-1.5" title={note || undefined}>
                      {humanNote ?? note ?? "—"}
                    </td>
                  </tr>
                );
              })}
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
      <SectionHead title={t("ops.prec.title")}>
        <button
          type="button"
          onClick={onExport}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.export")}
        </button>
      </SectionHead>
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

// 二级子 tab(票 #142):轮次(默认)/裁决/档案/设置。裁决子 tab 的待裁亮点
// 降级未做——包列表 API({name,size,modified})不含裁决态,判未裁须逐包全文
// 读取,非廉价来源(票面明许降级);PR 记录。
type OpsSubTab = "rounds" | "rulings" | "archive" | "settings";

export default function OpsPage({ onUnauthorized }: { onUnauthorized: () => void }) {
  const { t } = useI18n();
  const { tasks } = useTasks();
  const opsTask = tasks.find((tk) => tk.source === "ops");
  const [subTab, setSubTab] = useState<OpsSubTab>("rounds");
  const goRulings = useCallback(() => setSubTab("rulings"), []);

  // 轮次收口(running → done/failed/cancelled)→ 裁决包列表重拉(新包先见)
  const prevRef = useRef<string | undefined>(undefined);
  const [roundTick, setRoundTick] = useState(0);
  useEffect(() => {
    const cur = opsTask?.state as TaskState["state"] | undefined;
    const prev = prevRef.current;
    prevRef.current = cur;
    if (prev === "running" && cur && cur !== "running") setRoundTick((n) => n + 1);
  }, [opsTask?.state]);

  const subTabs: Array<{ id: OpsSubTab; key: "ops.tab.rounds" | "ops.tab.rulings" | "ops.tab.archive" | "ops.tab.settings" }> = [
    { id: "rounds", key: "ops.tab.rounds" },
    { id: "rulings", key: "ops.tab.rulings" },
    { id: "archive", key: "ops.tab.archive" },
    { id: "settings", key: "ops.tab.settings" },
  ];

  return (
    <div>
      {/* 裁⑦ 恒挂:全部建议仅立项,零自动执行。票 #147:彩色横幅降级为一行
          无底色小字注记——文案语义不变;恒挂声明非事件,琥珀只留给事件性
          警示(硬规⑤)。位置在子 tab 上方,四个子 tab 恒见。 */}
      <p className="text-[11px] text-zinc-500">{t("ops.disclaimer")}</p>
      {/* 票 #147:二级子 tab underline 式——去 chip 容器、字号较一级 tab
          (text-sm)降一级、与内容列左对齐;与一级 tab 的容器形态拉开两级
          视觉。role=tab / aria-selected 语义不弱化(underline 只换皮肤)。 */}
      <div role="tablist" aria-label={t("ops.cockpit.title")} className="mt-4 flex gap-5 border-b border-zinc-800">
        {subTabs.map(({ id, key }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={subTab === id}
            className={`border-b-2 px-1 pb-2 pt-1 text-xs font-medium transition-colors ${
              subTab === id
                ? "border-emerald-500 text-emerald-400"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
            onClick={() => setSubTab(id)}
          >
            {t(key)}
          </button>
        ))}
      </div>
      <div className="mt-6">
        {subTab === "rounds" && (
          <>
            {/* 票 #148:驾驶舱单卡(状态 chip 内联节头/上一轮结果人话化+原始
                信封/触发动作同卡)+ 过往轮次表;原独立触发节已并入卡 */}
            <OpsCockpit onGoRulings={goRulings} onUnauthorized={onUnauthorized} />
            <OpsPastRounds onGoRulings={goRulings} onUnauthorized={onUnauthorized} />
          </>
        )}
        {subTab === "rulings" && (
          <OpsPackagesSection onUnauthorized={onUnauthorized} roundTick={roundTick} />
        )}
        {subTab === "archive" && (
          <>
            <LedgerSection onUnauthorized={onUnauthorized} />
            <PrecedentsSection onUnauthorized={onUnauthorized} />
          </>
        )}
        {subTab === "settings" && <ConfigSection onUnauthorized={onUnauthorized} />}
      </div>
    </div>
  );
}
