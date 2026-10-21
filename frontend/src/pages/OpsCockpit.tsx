import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { useTasks } from "../tasks/useTasks";
import {
  startOpsRound, readOpsLedger, listOpsPackages,
  type ApiError, type OpsPackageInfo, type OpsRoundType, type TaskState,
} from "../api";
import { opsErrorText, roundErrorText, humanizeRoundMessage } from "./opsErrorText";
import { OpsSearchInput } from "./OpsSearchInput";
import { ledgerRows, splitUsage, pkgMatchesRow, type LedgerRow } from "./opsLedger";
import { LEDGER_CELL, LEDGER_COL_KEYS, PAST_EXTRA_COL_KEYS, relTime, noteText, thClass, tdNumClass, tdTimeClass, usageText } from "./opsTable";
import { SectionHead } from "./OpsSectionHead";
import { useArrivalNow } from "./useArrivalNow";

// OpsCockpit.tsx — 驾驶舱(GLOSSARY 词条「驾驶舱」锚点;票 #142 起)。
// 票 #148 单卡化:状态 chip 内联节头 + 上一轮结果(人话化错误 + 可展开原始
// 信封,证据不灭失)+ 健康/发现触发动作,三者同卡;过往轮次表独立成节。
// 只观察不裁决(裁决动作面在「裁决」子 tab)。数据源链:任务链内存态
// (tasks+logs)优先 → readOpsLedger 末行兜底;耗时无后端创建时间戳可读
// (任务面零改),自本页首见该轮起计——宁少算不伪造。

// 健康轮一键的非空输入(P2 路由 422 门:input 恒非空;健康轮指令面自含于
// prompts/health-system.md,输入仅占位——钉常量防 i18n 漂移)。
const HEALTH_ROUND_INPUT = "health";

const RUNNING_BADGE = "text-emerald-400 border-emerald-500/20 bg-emerald-500/5";
const IDLE_BADGE = "text-zinc-400 border-zinc-700 bg-zinc-800/50";

// 已耗时走字:mm:ss(不足一小时)/ h:mm:ss
function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const p = (x: number) => String(x).padStart(2, "0");
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}:${p(m)}:${p(s % 60)}` : `${p(m)}:${p(s % 60)}`;
}

// 上一轮摘要(内存面):从终态任务 + 其 stderr 行取证据。
// ok 轮 = main 的 `round: <type> 完成 → <pkg>` + `usage: …` 行逐字;
// 缺行 = 内存面不完整 → 交台账兜底(不伪造读数)。failed/cancelled 恒可摘要
// (状态本身即证据;失败轮 usage 无单行汇总面,不在卡上估读——宁少算)。
type LastRoundSummary =
  | { kind: "ok"; round: string; pkg: string; usage: string; cost: string }
  | { kind: "failed"; code: string | null; message: string | null }
  | { kind: "cancelled" };

function buildFromMemory(task: TaskState, lines: string[]): LastRoundSummary | null {
  if (task.state === "running") return null;
  if (task.state === "failed") return { kind: "failed", code: task.error_code ?? null, message: task.error };
  if (task.state === "cancelled") return { kind: "cancelled" };
  const pkgLine = [...lines].reverse().find((l) => /^round: (health|discover) 完成 → /.test(l));
  const usageLine = [...lines].reverse().find((l) => /^usage: in=\d+ out=\d+ total=\d+ cost=/.test(l));
  if (!pkgLine || !usageLine) return null;
  const m = pkgLine.match(/^round: (health|discover) 完成 → (.+)$/);
  const u = usageLine.match(/^usage: (in=\d+ out=\d+) total=\d+ cost=([\d.]+)$/);
  if (!m || !u) return null;
  const pkgName = m[2].split("/").pop() ?? m[2];
  return { kind: "ok", round: m[1], pkg: pkgName, usage: u[1], cost: u[2] };
}

// 台账末行 → 兜底摘要(宽形:cells 全行,缺读数如实缺省)
type LedgerSummary = { kind: "ledger"; cells: LedgerRow; usage: string; cost: string | null };
function ledgerCardRow(cells: LedgerRow): LedgerSummary {
  const { usage, cost } = splitUsage(cells[LEDGER_CELL.usage] ?? "");
  return { kind: "ledger", cells, usage, cost };
}

// 统一件表格类已收编 opsTable.ts(#149:两表同一处施加,防右对齐漂移)

export function OpsCockpit({ onGoRulings, onUnauthorized }: {
  onGoRulings: () => void;
  onUnauthorized: () => void;
}) {
  const { t } = useI18n();
  const { tasks, logs } = useTasks();
  const opsTask = tasks.find((tk) => tk.source === "ops");
  const running = opsTask?.state === "running";
  const logLines = opsTask ? logs[opsTask.id] ?? [] : [];
  const logLen = logLines.length;

  // 上一轮摘要快照:终态 ops 任务在下一轮起跑时会被任务存储清扫(start_ops_round
  // 镜像清扫),先把内存面证据定格进 state——「上一轮」跨轮存活。render-time
  // adjust(React 官方「外部输入变化调 state」模式,同 ResultTable prevResults,
  // 替代 reset effect);键含 logLen → 终态后日志尾行落齐会重建一次。
  const terminal = opsTask && opsTask.state !== "running" ? opsTask : null;
  const terminalKey = terminal ? `${terminal.id}:${terminal.state}:${logLen}` : null;
  const [snapKey, setSnapKey] = useState<string | null>(null);
  const [summary, setSummary] = useState<LastRoundSummary | null>(null);
  if (terminal && terminalKey !== snapKey) {
    setSnapKey(terminalKey);
    const s = buildFromMemory(terminal, logLines);
    if (s) setSummary(s); // 空读数(日志缺行)不覆盖既有快照,交台账兜底
  }

  // 台账兜底(冷加载/跨页刷新无内存面):fetch-once(ref 闸);setState 全在异步回调
  const [ledgerLast, setLedgerLast] = useState<LedgerRow | null>(null);
  const [ledgerDone, setLedgerDone] = useState(false);
  const ledgerFiredRef = useRef(false);
  const hasSummary = summary != null;
  useEffect(() => {
    if (hasSummary || ledgerFiredRef.current) return;
    ledgerFiredRef.current = true;
    readOpsLedger()
      .then((text) => {
        const rows = ledgerRows(text);
        if (rows.length > 0) setLedgerLast(rows[rows.length - 1]);
      })
      .catch((e) => { if ((e as ApiError).status === 401) onUnauthorized(); })
      .finally(() => setLedgerDone(true));
  }, [hasSummary, onUnauthorized]);

  // 已耗时:任务面无创建时间戳(桥零改),自本页首见 running 起计(ref 写读均限
  // effect/回调,Date.now 不入 render);每秒走字。running 翻转时归零显 00:00
  // (纯 state 的 render-time adjust),真值由首个 tick 接管。
  const startedRef = useRef<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [prevRunning, setPrevRunning] = useState<boolean | null>(null);
  if (prevRunning !== running) {
    setPrevRunning(running);
    setElapsedMs(0);
  }
  useEffect(() => {
    if (!running) { startedRef.current = null; return; }
    startedRef.current = startedRef.current ?? Date.now();
    const iv = setInterval(() => {
      const s = startedRef.current;
      if (s != null) setElapsedMs(Date.now() - s);
    }, 1000);
    return () => clearInterval(iv);
  }, [running]);

  // 可折叠全量日志:展开时自动滚底(新行落底即视)
  const [expanded, setExpanded] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const el = logRef.current;
    if (el && expanded) el.scrollTop = el.scrollHeight;
  }, [logLen, expanded]);

  // 触发面(票 #148 入卡;原独立「轮次」节撤除):健康/发现是主操作非次级,
  // 不入节头——节头只挂描边次级动作(硬规④)
  const [discoverInput, setDiscoverInput] = useState("");
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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

  const lastLine = logLen > 0 ? logLines[logLen - 1] : null;
  const last = summary ?? (ledgerLast ? ledgerCardRow(ledgerLast) : null);

  // 失败主行人话化:信封可判 → 人话短语;不可判 → 可读 code 名(不带原始
  // message 尾巴——细节在下方可展开原始信封,不灭失)
  const failedPrimary = (f: Extract<LastRoundSummary, { kind: "failed" }>) => {
    const h = humanizeRoundMessage(f.message);
    return h ? t(h.key, h.vars) : roundErrorText(t, f.code, null);
  };

  // 状态 chip:内联节头左簇(进行中/空闲),不占动作位
  const chip = (
    <span className={`rounded border px-2 py-0.5 font-mono text-[11px] ${running ? RUNNING_BADGE : IDLE_BADGE}`}>
      {running ? t("ops.round.state.running") : t("ops.cockpit.idle")}
    </span>
  );

  return (
    <section aria-label={t("ops.cockpit.title")}>
      <SectionHead title={t("ops.cockpit.title")} lead={chip} />
      <div className="mt-3 rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
        {running && (
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-[11px] text-zinc-400">
                {t("ops.cockpit.elapsed")}{" "}
                <span>{fmtElapsed(elapsedMs)}</span>
                <span className="ml-2 text-zinc-600">{t("ops.cockpit.observedStart")}</span>
              </span>
            </div>
            <div className="mt-2">
              <p className="text-[11px] text-zinc-500">{t("ops.cockpit.lastActivity")}</p>
              {!expanded && (
                <pre className="mt-1 overflow-hidden rounded border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-[11px] leading-relaxed text-zinc-400 whitespace-nowrap text-ellipsis">
                  {lastLine ?? t("ops.cockpit.noActivity")}
                </pre>
              )}
              {logLen > 0 && (
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="mt-1 rounded-md border border-zinc-700 px-3 py-1 text-[11px] text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
                >
                  {expanded ? t("ops.cockpit.logHide") : t("ops.cockpit.logShow")}
                </button>
              )}
              {expanded && (
                <pre
                  ref={logRef}
                  className="mt-1 max-h-64 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-2 font-mono text-[11px] leading-relaxed text-zinc-400"
                >
                  {logLines.map((l, i) => (<div key={i}>{l}</div>))}
                </pre>
              )}
            </div>
          </div>
        )}
        {/* 上一轮结果:内存态优先,台账末行兜底;空闲不留白(缺证据显空态,无证据≠清白) */}
        <div className={running ? "mt-3" : ""}>
          {last ? (
            <div>
              <p className="text-[11px] text-zinc-500">
                {t("ops.cockpit.lastRound")}
                {summary == null && <span className="ml-1 text-zinc-600">({t("ops.cockpit.lastRound.ledger")})</span>}
              </p>
              {last.kind === "failed" ? (
                <>
                  <p role="alert" className="mt-1 text-xs text-red-400">{failedPrimary(last)}</p>
                  {last.message && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-[11px] text-zinc-500 transition-colors hover:text-zinc-300">
                        {t("ops.cockpit.rawEnvelope")}
                      </summary>
                      <pre className="mt-1 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-zinc-400">
                        {last.message}
                      </pre>
                    </details>
                  )}
                </>
              ) : last.kind === "cancelled" ? (
                <p className="mt-1 text-xs text-zinc-400">{t("ops.round.state.cancelled")}</p>
              ) : last.kind === "ok" ? (
                <p className="mt-1 text-xs text-zinc-300">
                  <span className="mr-2 rounded border border-emerald-500/20 bg-emerald-500/5 px-1.5 py-0.5 font-mono text-[10px] text-emerald-400">
                    {t("ops.cockpit.lastRound.ok")}
                  </span>
                  {last.round} · <span className="font-mono">{last.pkg}</span>
                  <span className="ml-2 font-mono text-zinc-500">{last.usage} · cost={last.cost}</span>
                </p>
              ) : (
                <p className="mt-1 text-xs text-zinc-300">
                  <span className="font-mono">{last.cells[LEDGER_CELL.time]}</span> · {last.cells[LEDGER_CELL.round]} · <span className="font-mono">{last.cells[LEDGER_CELL.model]}</span>
                  <span className="ml-2 font-mono text-zinc-500">{last.usage} · cost={last.cost ?? "—"}</span>
                </p>
              )}
              <button
                type="button"
                onClick={onGoRulings}
                className="mt-2 rounded-md border border-zinc-700 px-3 py-1 text-[11px] text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
              >
                {t("ops.cockpit.goRulings")}
              </button>
            </div>
          ) : (
            !running && ledgerDone && <p className="px-1 text-xs text-zinc-500">{t("ops.cockpit.lastRound.none")}</p>
          )}
        </div>
        {/* 触发动作:健康(实心主 CTA)+ 发现输入 + 发现(描边)——主操作同排 */}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-800/60 pt-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => start("health")}
            className="rounded-md bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-transform hover:scale-[1.02] disabled:opacity-40"
          >
            {t("ops.round.health")}
          </button>
          {/* 视觉门 2026-10-21 同根因补收口:原生蓝清除钮 → 搜索输入统一件
              (OpsSearchInput);行内弹性尺寸经 wrapperClass 落容器 */}
          <OpsSearchInput
            label={t("ops.round.discoverPlaceholder")}
            placeholder={t("ops.round.discoverPlaceholder")}
            value={discoverInput}
            onChange={setDiscoverInput}
            wrapperClass="min-w-64 flex-1"
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
      </div>
    </section>
  );
}

// 过去轮次区(GLOSSARY「驾驶舱」词条内的过去轮次面;票 #142):
// 台账末 N 行(usage/cost 拆列)+ 包目录合并只读列表。零新后端存储——
// readOpsLedger + 既有包列表 API 两读合成。结果码宁德少算:仅最新行在内存
// 证据(终态任务+完成行包名)与行(日期+轮型)对上时标 ok;失败/旧行无证据
// 恒 —(台账行不载成败;无证据≠清白,不伪造)。无台账行的包(失败先于
// 记账等)不灭失:并入孤行,缺列显 —。
// 票 #148:表格统一件落地——ops.col.* 中文列名(+备注)、用量/成本右对齐、
// 时间相对 + title 完整戳、备注人话化(title 留原文)、「—」附宁少算 title。
// 视觉门 2026-10-21:低2 用量人话化(title 挂台账原始串,证据不灭失);
// 低3 表头/时间零折行(thClass whitespace-nowrap + tdTimeClass)。
const PAST_N = 10;

export function OpsPastRounds({ onGoRulings, onUnauthorized }: {
  onGoRulings: () => void;
  onUnauthorized: () => void;
}) {
  const { t } = useI18n();
  const { tasks, logs } = useTasks();
  const opsTask = tasks.find((tk) => tk.source === "ops");
  const [text, setText] = useState<string | null>(null);
  const [packages, setPackages] = useState<OpsPackageInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 相对时间基准 = 数据抵达时刻(useArrivalNow,Date.now 不入 render);行
  // 渲染晚于两回调置位,不闪初值
  const [now, markArrived] = useArrivalNow();

  const failWith = (fallback: string) => (e: unknown) => {
    if ((e as ApiError).status === 401) { onUnauthorized(); return; }
    setError(opsErrorText(t, e, fallback));
  };

  useEffect(() => {
    readOpsLedger().then((v) => { setText(v); markArrived(); }).catch(failWith(t("ops.ledger.loadFailed")));
    listOpsPackages().then((v) => { setPackages(v); markArrived(); }).catch(() => { /* 包列缺不阻台账面 */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rows = text != null ? ledgerRows(text) : [];
  const dataRows = rows.length > 0 ? rows.slice(-PAST_N).reverse() : []; // 末 N 行,新在前
  const pkgs = packages ?? [];

  // 行↔包关联先算后渲染(纯函数):匹配包记录在集合,未匹配包(失败先于
  // 记账等)不灭失——入孤行置顶,缺列显 —
  const matchedPkgs = new Set<string>();
  const rowsWithPkgs = dataRows.map((cells) => {
    const hit = pkgs.filter((p) => pkgMatchesRow(p.name, cells[LEDGER_CELL.time] ?? "", cells[LEDGER_CELL.round] ?? ""));
    hit.forEach((p) => matchedPkgs.add(p.name));
    return { cells, pkgs: hit };
  });
  const orphans = pkgs.filter((p) => !matchedPkgs.has(p.name));
  // 节头计数(票 #147):渲染行 = 台账行 + 孤儿包;空表显 (0)(视觉门
  // 2026-10-21 微5);台账未到 text=null → 计数 null 不显(无证据不显 0)
  const pastCount = text != null ? dataRows.length + orphans.length : null;

  // 最新行结果码:终态任务的完成行包名与行(日期+轮型)对上 → ok(唯一可证关联);
  // 失败/旧行无证据恒 —(台账行不载成败;无证据≠清白,不伪造)
  const terminal = opsTask && opsTask.state !== "running" ? opsTask : null;
  const okPkg = (() => {
    if (!terminal || terminal.state !== "done") return null;
    const lines = logs[terminal.id] ?? [];
    const m = [...lines].reverse().find((l) => /^round: (health|discover) 完成 → /.test(l))?.match(/^round: (health|discover) 完成 → (.+)$/);
    return m ? (m[2].split("/").pop() ?? null) : null;
  })();
  const newest = rowsWithPkgs[0];
  const resultFor = (cells: LedgerRow): string | null =>
    okPkg && newest && cells === newest.cells && pkgMatchesRow(okPkg, cells[LEDGER_CELL.time] ?? "", cells[LEDGER_CELL.round] ?? "")
      ? t("ops.cockpit.lastRound.ok")
      : null;

  // 统一件列集:台账基列 + 结果码/包;数字列右对齐(硬规②)
  const cols = [...LEDGER_COL_KEYS, ...PAST_EXTRA_COL_KEYS];
  const dash = <span title={t("ops.result.dashTitle")}>—</span>;

  return (
    <section aria-label={t("ops.past.title")} className="mt-8">
      <SectionHead title={t("ops.past.title")} count={pastCount} />
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}
      {text != null && dataRows.length === 0 && !error && (
        <p className="mt-3 text-sm text-zinc-500">{t("ops.past.empty")}</p>
      )}
      {(dataRows.length > 0 || orphans.length > 0) && (
        <div className="mt-3 overflow-auto rounded-md border border-zinc-800">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-zinc-900 font-mono text-[11px] text-zinc-500">
              <tr>
                {cols.map((k) => (
                  <th key={k} scope="col" className={thClass(k)}>{t(`ops.col.${k}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 font-mono text-zinc-400">
              {orphans.map((p) => {
                const rt = relTime(p.modified, now);
                return (
                  <tr key={p.name}>
                    <td className={tdTimeClass} title={rt.title}>{t(rt.key, rt.vars)}</td>
                    <td className="px-3 py-1.5">{p.name.split("-")[3] ?? "—"}</td>
                    <td className="px-3 py-1.5">—</td>
                    <td className={tdNumClass}>—</td>
                    <td className={tdNumClass}>—</td>
                    <td className="px-3 py-1.5">—</td>
                    <td className="px-3 py-1.5">{dash}</td>
                    <td className="px-3 py-1.5">
                      <button type="button" onClick={onGoRulings} className="text-emerald-400 transition-colors hover:text-emerald-300">
                        {p.name}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {rowsWithPkgs.map(({ cells, pkgs: hit }, r) => {
                const { usage, cost } = splitUsage(cells[LEDGER_CELL.usage] ?? "");
                const rt = relTime(cells[LEDGER_CELL.time] ?? "", now);
                const note = cells[LEDGER_CELL.note] ?? "";
                const humanNote = noteText(t, note);
                const res = resultFor(cells);
                return (
                  <tr key={r}>
                    <td className={tdTimeClass} title={rt.title}>{t(rt.key, rt.vars)}</td>
                    <td className="px-3 py-1.5">{cells[LEDGER_CELL.round]}</td>
                    <td className="px-3 py-1.5">{cells[LEDGER_CELL.model]}</td>
                    <td className={tdNumClass} title={usage}>{usageText(t, usage)}</td>
                    <td className={tdNumClass}>{cost ?? "—"}</td>
                    <td className="px-3 py-1.5" title={note || undefined}>
                      {humanNote ?? (note || "—")}
                    </td>
                    <td className="px-3 py-1.5">{res ?? dash}</td>
                    <td className="px-3 py-1.5">
                      {hit.length > 0 ? hit.map((p) => (
                        <button
                          key={p.name}
                          type="button"
                          onClick={onGoRulings}
                          className="mr-2 text-emerald-400 transition-colors hover:text-emerald-300"
                        >
                          {p.name}
                        </button>
                      )) : "—"}
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
