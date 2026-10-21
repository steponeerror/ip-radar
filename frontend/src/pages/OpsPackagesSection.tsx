import { useCallback, useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { Modal } from "../components/Modal";
import {
  listOpsPackages, readOpsPackage, readOpsPrecedent, postOpsRuling,
  type ApiError, type OpsPackageInfo, type OpsRulingResult, type OpsRulingVerdict,
} from "../api";
import { opsErrorText } from "./opsErrorText";
import { relTime } from "./opsTable";
import { SectionHead } from "./OpsSectionHead";

// P4 裁决包区(票 #136):列表 → 详情(包文逐字:建议/证据 call_id+field+value/
// trace;判例引用可点开全文)→ 人裁三动作(同意/否决/修正)。裁⑦:全部建议
// 恒标「仅立项」,同意只落判例+待集成清单,零执行。

// 判例引用文件名(注入判例节引用 YYYY-MM-DD-<slug>.md;人裁落判例
// YYYY-MM-DD-ruling-<hex>.md 同形)——只做「可点开」识别,存在性由读取端点
// 判(404 → 可读文案,不伪装空)。
const PRECEDENT_REF_RE = /(\d{4}-\d{2}-\d{2}-[A-Za-z0-9._-]+\.md)/;

// 建议候选 = 包文本固定节的列表项(逐字,去列表标记):discover 包「## 建议」
// + 健康包「## 异常清单」(「建议复核」条目 = 留人裁面,health-system 输出
// 契约)。逐字纪律:suggestion 只从包内原文选取,不提供自由输入发明建议。
function parseSuggestions(text: string): string[] {
  const out: string[] = [];
  let inSection = false;
  for (const line of text.split("\n")) {
    if (line.startsWith("## ")) {
      inSection = line === "## 建议" || line.startsWith("## 异常清单");
      continue;
    }
    if (inSection && /^\s*[-*] /.test(line)) {
      const item = line.replace(/^\s*[-*] /, "").trim();
      if (item) out.push(item);
    }
  }
  return out;
}

// 包文逐字渲染(证据三元组/trace 原样保留);判例文件名替换为可点按钮。
function PackageText({ text, onOpenPrecedent }: {
  text: string;
  onOpenPrecedent: (name: string) => void;
}) {
  const parts = text.split(PRECEDENT_REF_RE);
  return (
    <pre className="max-h-[28rem] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-300">
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <button
            key={i}
            type="button"
            onClick={() => onOpenPrecedent(p)}
            className="text-emerald-400 underline decoration-emerald-500/40 underline-offset-2 transition-colors hover:text-emerald-300"
          >
            {p}
          </button>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </pre>
  );
}

export default function OpsPackagesSection({ onUnauthorized, roundTick }: {
  onUnauthorized: () => void;
  roundTick: number; // 轮次收口(done/failed/cancelled)时 +1 → 重拉列表
}) {
  const { t } = useI18n();
  const [packages, setPackages] = useState<OpsPackageInfo[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  // 相对时间基准 = 列表抵达时刻(#149;Date.now 不入 render,同台账纪律)
  const [now, setNow] = useState(0);
  const [detailName, setDetailName] = useState<string | null>(null);
  const [detailText, setDetailText] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  // 人裁面
  const [selected, setSelected] = useState<string | null>(null);
  const [amending, setAmending] = useState(false);
  const [amendment, setAmendment] = useState("");
  const [rulingBusy, setRulingBusy] = useState(false);
  const [result, setResult] = useState<OpsRulingResult | null>(null);
  const [rulingError, setRulingError] = useState<string | null>(null);
  // 判例全文弹窗
  const [precName, setPrecName] = useState<string | null>(null);
  const [precText, setPrecText] = useState<string | null>(null);
  const [precError, setPrecError] = useState<string | null>(null);

  const failWith = (set: (s: string) => void, fallback: string) => (e: unknown) => {
    if ((e as ApiError).status === 401) { onUnauthorized(); return; }
    set(opsErrorText(t, e, fallback));
  };

  const load = useCallback(async () => {
    setListError(null);
    try {
      setPackages(await listOpsPackages());
      setNow(Date.now());
    } catch (e) {
      failWith(setListError, t("ops.pkgs.loadFailed"))(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, onUnauthorized]);

  // 挂载 + 轮次收口(roundTick)重拉
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load, roundTick]);

  const openDetail = (name: string) => {
    setDetailName(name); setDetailText(null); setDetailError(null);
    setSelected(null); setAmending(false); setAmendment("");
    setResult(null); setRulingError(null);
    readOpsPackage(name)
      .then(setDetailText)
      .catch(failWith(setDetailError, t("ops.pkgs.loadFailed")));
  };

  const openPrecedent = (name: string) => {
    setPrecName(name); setPrecText(null); setPrecError(null);
    readOpsPrecedent(name)
      .then(setPrecText)
      .catch(failWith(setPrecError, t("ops.prec.loadFailed")));
  };

  const rule = (verdict: OpsRulingVerdict, amendmentText?: string) => {
    if (!selected || rulingBusy) return;
    setRulingBusy(true); setRulingError(null);
    postOpsRuling(detailName as string, selected, verdict, amendmentText)
      .then((r) => {
        setResult(r);
        setAmending(false); setAmendment("");
      })
      .catch(failWith(setRulingError, t("ops.pkgs.ruling.failed")))
      .finally(() => setRulingBusy(false));
  };

  const title = (
    // 票 #149:节头计数(裁决包 N 个)属列表面;详情态无行集可数,不带计数
    <SectionHead title={t("ops.pkgs.title")} count={detailName ? null : (packages?.length ?? null)}>
      {/* 裸文字链接 → 描边按钮(票 #147;硬规④) */}
      {detailName && (
        <button
          type="button"
          onClick={() => { setDetailName(null); setSelected(null); setAmending(false); setAmendment(""); setResult(null); setRulingError(null); }}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.pkgs.back")}
        </button>
      )}
    </SectionHead>
  );

  if (detailName) {
    const suggestions = detailText != null ? parseSuggestions(detailText) : [];
    return (
      <section aria-label={t("ops.pkgs.title")} className="mt-8">
        {title}
        {detailError && (
          <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
            {detailError}
          </p>
        )}
        {detailText != null && (
          <>
            <PackageText text={detailText} onOpenPrecedent={openPrecedent} />
            {/* 人裁面:建议候选(逐字)+ 三动作;裁⑦ 恒标仅立项 */}
            <div className="mt-4 rounded-md border border-zinc-800 bg-zinc-900/60 p-4">
              <p className="text-xs text-zinc-500">{t("ops.pkgs.ruling.selectHint")}</p>
              {suggestions.length === 0 ? null : (
                <ul className="mt-2 space-y-1">
                  {suggestions.map((s) => (
                    <li key={s}>
                      <button
                        type="button"
                        aria-pressed={selected === s}
                        onClick={() => { setSelected(s); setAmending(false); setAmendment(""); setRulingError(null); }}
                        className={`w-full rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                          selected === s
                            ? "border-emerald-500/50 bg-emerald-500/5 text-zinc-200"
                            : "border-zinc-800 bg-zinc-950/60 text-zinc-400 hover:border-zinc-700"
                        }`}
                      >
                        <span className="mr-2 inline-block rounded border border-amber-500/30 bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400 align-middle">
                          {t("ops.pkgs.onlyProposal")}
                        </span>
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {!amending && (
                <div className="mt-3 flex gap-2">
                  <button type="button" disabled={!selected || rulingBusy} onClick={() => rule("agreed")}
                    className="rounded-md bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-transform hover:scale-[1.02] disabled:opacity-40 disabled:hover:scale-100">
                    {t("ops.pkgs.ruling.agree")}
                  </button>
                  <button type="button" disabled={!selected || rulingBusy} onClick={() => rule("overruled")}
                    className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-red-500/50 hover:text-red-400 disabled:opacity-40">
                    {t("ops.pkgs.ruling.overrule")}
                  </button>
                  <button type="button" disabled={!selected || rulingBusy} onClick={() => setAmending(true)}
                    className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-amber-500/50 hover:text-amber-400 disabled:opacity-40">
                    {t("ops.pkgs.ruling.amend")}
                  </button>
                </div>
              )}
              {amending && (
                <div className="mt-3">
                  <textarea
                    aria-label={t("ops.pkgs.ruling.amendPlaceholder")}
                    placeholder={t("ops.pkgs.ruling.amendPlaceholder")}
                    rows={3}
                    value={amendment}
                    onChange={(e) => setAmendment(e.target.value)}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 focus:border-amber-600 focus:outline-none"
                  />
                  <button
                    type="button"
                    disabled={!amendment.trim() || rulingBusy}
                    onClick={() => rule("amended", amendment)}
                    className="mt-2 rounded-md bg-amber-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-transform hover:scale-[1.02] disabled:opacity-40 disabled:hover:scale-100"
                  >
                    {t("ops.pkgs.ruling.amendSend")}
                  </button>
                </div>
              )}
              {result && (
                <div role="status" className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-400">
                  <p>
                    {result.created
                      ? t("ops.pkgs.ruling.ok", { precedent: result.precedent })
                      : t("ops.pkgs.ruling.idempotent", { precedent: result.precedent })}
                  </p>
                  {result.superseded && (
                    <p className="mt-1 text-zinc-400">
                      {t("ops.pkgs.ruling.superseded", { superseded: result.superseded })}
                    </p>
                  )}
                  {result.queue_appended && (
                    <p className="mt-1 text-zinc-400">{t("ops.pkgs.ruling.queued")}</p>
                  )}
                </div>
              )}
              {rulingError && (
                <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
                  {rulingError}
                </p>
              )}
            </div>
          </>
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

  // 列表态
  return (
    <section aria-label={t("ops.pkgs.title")} className="mt-8">
      {title}
      {listError && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {listError}
        </p>
      )}
      {/* 票 #149:空列表显基准「暂无」式居中空态(硬规⑥),不留纯空白 */}
      {packages != null && packages.length === 0 && !listError && (
        <div className="mt-3 rounded-md border border-zinc-800">
          <p className="px-3 py-6 text-center text-xs text-zinc-500">{t("ops.pkgs.empty")}</p>
        </div>
      )}
      {packages != null && packages.length > 0 && (
        <ul className="mt-3 divide-y divide-zinc-800 rounded-md border border-zinc-800">
          {/* 票 #149:行元数据 = 大小 KB + 相对时间(title=ISO 原文,证据
              不灭失);密度向源管理列表看齐(px-4 py-2.5,文件名 text-sm) */}
          {packages.map((p) => {
            const rt = relTime(p.modified, now);
            return (
              <li key={p.name}>
                <button
                  type="button"
                  onClick={() => openDetail(p.name)}
                  className="flex w-full items-baseline gap-x-3 px-4 py-2.5 text-left transition-colors hover:bg-zinc-900"
                >
                  <span className="font-mono text-sm text-emerald-400">{p.name}</span>
                  <span className="ml-auto whitespace-nowrap font-mono text-xs text-zinc-500">
                    {(p.size / 1024).toFixed(1)} KB
                  </span>
                  <span
                    className="whitespace-nowrap font-mono text-xs text-zinc-500"
                    title={rt.title}
                  >
                    {t(rt.key, rt.vars)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {/* 判例全文弹窗:仅详情态(包内引用可点)可开 */}
    </section>
  );
}
