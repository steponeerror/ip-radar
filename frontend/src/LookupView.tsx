import { useEffect, useRef, useState } from "react";
import { IpInput } from "./components/IpInput";
import { FileUpload } from "./components/FileUpload";
import { ResultTable } from "./components/ResultTable";
import { ExportCsv } from "./components/ExportCsv";
import { Modal } from "./components/Modal";
import { WarmupBanner } from "./components/WarmupBanner";
import { WarmingProvider } from "./WarmingProvider";
import { useWarming } from "./warming";
import { queryIpsStream, uploadFileStream, type ApiError } from "./api";
import type { LookupResult, Progress, StreamOutcome } from "./api";
import { errorToBanner, outcomeToBanner, type BannerError } from "./lib/lookupError";
import { useI18n } from "./i18n";

type InputTab = "text" | "file";

// api 层非 2xx 抛错统一带 e.status + e.code(信封语义码,见 api.ts throwApiError);
// code==="warming" 才是 warming 门(no_sources 是另一种 503)。
const isWarming503 = (e: unknown) =>
  (e as ApiError).code === "warming";

export default function LookupView() {
  return (
    <WarmingProvider>
      <LookupViewInner />
    </WarmingProvider>
  );
}

function LookupViewInner() {
  const { t } = useI18n();
  const [tab, setTab] = useState<InputTab>("text");
  const [results, setResults] = useState<LookupResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<BannerError | null>(null);
  const [skipped, setSkipped] = useState<{ invalid: number } | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [csvModal, setCsvModal] = useState<{
    open: boolean;
    count: number;
    invalid: number;
  } | null>(null);
  const { warming, recheck } = useWarming();

  // U1:done.error / done.code 经 outcomeToBanner 映射为 i18n 主行;
  // fallbackKey = 调用方已本地化的 failMsg 键。
  const applyOutcome = (r: StreamOutcome, fallbackKey: string) => {
    if (r.invalidLines > 0) {
      setSkipped({ invalid: r.invalidLines });
    }
    const banner = outcomeToBanner(r, fallbackKey);
    if (r.csvDownloaded) {
      setResults([]);
      setCsvModal({
        open: true,
        count: r.total,
        invalid: r.invalidLines,
      });
    } else {
      setResults(r.results);
    }
    if (banner) setError(banner);
  };

  // 503 自纠:乐观提交漏过初始加载窗口撞上 warming 门时,recheck 确认 —
  // 仍在 warming 则横幅接管(recheck 同时重臂轮询,后端重启亦能恢复);
  // 门已开则原样重试一次(503 在依赖处抛出,服务端零副作用,重试安全)。
  // 第二次仍 503 不再重试(防乒乓)。no-sources 是配置态非瞬时门:本地化
  // 提示、不重试。其余错误主行必为 t() 键(errorToBanner 映射),信封
  // message 降级为次要行(U1)。
  const runLookup = async (fetcher: () => Promise<StreamOutcome>, fallbackKey: string) => {
    setLoading(true);
    setError(null);
    setSkipped(null);
    setProgress(null);
    try {
      for (let attempt = 0; ; attempt++) {
        try {
          applyOutcome(await fetcher(), fallbackKey);
          break;
        } catch (e) {
          if (e instanceof Error && e.name === "AbortError") {
            setError({ key: "lookup.cancelled" });
            break;
          }
          if ((e as ApiError).code === "no_sources") {
            setError({ key: "lookup.noSources" });
            break;
          }
          if (!isWarming503(e)) {
            setError(errorToBanner(e, fallbackKey));
            break;
          }
          if (await recheck()) {
            break;
          }
          if (attempt > 0) {
            setError(errorToBanner(e, fallbackKey));
            break;
          }
          // 503 与重拉之间门恰好开合 — 重试一次
        }
      }
    } finally {
      setLoading(false);
      setProgress(null);
    }
  };

  const handleQuery = (ips: string[]) =>
    runLookup(() => queryIpsStream(ips, setProgress), "lookup.queryFailed");

  // ?ip= 深链:挂载时自动查询一次。仅读一次参数,不随路由变化重复触发。
  // handleQueryRef 持挂载帧闭包(挂载时即最新);effect [] 只跑一次,
  // 无需 render 期写 ref(react-hooks/refs)也无 effect 内同步 setState。
  const deepLinkFiredRef = useRef(false);
  const handleQueryRef = useRef(handleQuery);
  useEffect(() => {
    if (deepLinkFiredRef.current) return;
    deepLinkFiredRef.current = true;
    const q = new URLSearchParams(window.location.search).get("ip");
    const ip = q && q.trim() ? q.trim() : null;
    if (ip != null) handleQueryRef.current([ip]);
  }, []);

  const handleUpload = (file: File) =>
    runLookup(() => uploadFileStream(file, setProgress), "lookup.uploadFailed");

  return (
    <div className="space-y-6">
      {/* Input Section */}
      <section>
        <WarmupBanner />
        <div className="flex items-center gap-3">
          <div className="flex gap-1 rounded-lg bg-zinc-900 p-1">
            {(["text", "file"] as const).map((tabKey) => (
              <button
                key={tabKey}
                onClick={() => setTab(tabKey)}
                className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                  tab === tabKey
                    ? "bg-zinc-800 text-emerald-400"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {tabKey === "text" ? t("lookup.tab.text") : t("lookup.tab.file")}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3">
          {tab === "text" ? (
            <div className="fade-in">
              <IpInput onQuery={handleQuery} loading={loading} progress={progress} disabled={warming} />
            </div>
          ) : (
            <div className="fade-in">
              <FileUpload onUpload={handleUpload} loading={loading} progress={progress} disabled={warming} />
            </div>
          )}
        </div>
      </section>

      {/* Results Section */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-400">
            {results.length > 0
              ? t("lookup.resultsCount", { n: results.length.toLocaleString() })
              : t("lookup.results")}
          </h2>
          <ExportCsv results={results} />
        </div>

        {loading && progress && (
          <div className="mb-3 space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-emerald-400">
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {t("lookup.lookingUp", { done: progress.done.toLocaleString(), total: progress.total.toLocaleString() })}
              </span>
              <span className="text-zinc-500 tabular-nums">
                {progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0}%
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-zinc-800">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-300 ease-out"
                style={{ width: `${progress.total > 0 ? (progress.done / progress.total) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}
        {loading && !progress && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-2 text-sm text-emerald-400">
            <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {t("lookup.connecting")}
          </div>
        )}

        {error && (
          <div className="mb-3 rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-2 text-sm text-red-400">
            <div>
              {t(error.key)}
              {error.retryAfter != null && (
                <span className="ml-2 text-red-300/80">
                  {t("lookup.error.retryAfterHint", { n: error.retryAfter })}
                </span>
              )}
            </div>
            {error.detail && (
              <div className="mt-1 break-all text-xs text-red-300/70">{error.detail}</div>
            )}
          </div>
        )}

        {skipped && skipped.invalid > 0 && (
          <div className="mb-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm text-amber-400">
            {t("csvExport.invalidLines", { n: skipped.invalid })}
          </div>
        )}

        {loading && results.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-lg border border-zinc-800">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
            <span className="text-sm text-zinc-500">{t("lookup.waiting")}</span>
          </div>
        ) : results.length > 0 ? (
          <ResultTable results={results} />
        ) : (
          <div className="flex h-48 items-center justify-center rounded-lg border border-zinc-800 text-sm text-zinc-600">
            {t("lookup.noResults")}
          </div>
        )}
      </section>

      <Modal
        open={csvModal?.open ?? false}
        title={t("csvExport.modalTitle")}
        onClose={() => setCsvModal(null)}
      >
        <p>{t("csvExport.modalBody", { n: csvModal?.count ?? 0 })}</p>
        {csvModal && csvModal.invalid > 0 && (
          <p className="mt-2 text-xs text-amber-400">
            {t("csvExport.invalidLines", { n: csvModal.invalid })}
          </p>
        )}
      </Modal>
    </div>
  );
}
