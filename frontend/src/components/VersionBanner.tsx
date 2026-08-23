import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { getVersion, type VersionInfo } from "../api";

const DISMISS_KEY = "dismissed_version";

export function VersionBanner({ selfUpdateEnabled, onStartUpdate }: {
  selfUpdateEnabled: boolean;
  onStartUpdate: () => void;
}) {
  const { t } = useI18n();
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [copied, setCopied] = useState(false);

  const load = async (refresh = false) => {
    try { setInfo(await getVersion(refresh)); } catch { /* 静默:版本检查失败不打扰 */ }
  };
  useEffect(() => { load(); }, []);

  if (!info?.update_available) return null;
  if (localStorage.getItem(DISMISS_KEY) === info.latest) return null;

  const copyCmd = async () => {
    await navigator.clipboard.writeText("git pull && docker compose up -d --build");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mx-auto mt-4 flex max-w-7xl items-center gap-3 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm">
      <span className="text-emerald-300">🔄</span>
      <div className="min-w-0 flex-1">
        <span className="text-zinc-200">
          {t("update.bannerTitle", { latest: info.latest!, current: info.current })}
        </span>
        {info.summary && <p className="truncate text-xs text-zinc-500">{info.summary}</p>}
      </div>
      {selfUpdateEnabled ? (
        <button onClick={onStartUpdate}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500">
          {t("update.now")}
        </button>
      ) : null}
      <button onClick={() => copyCmd()}
        className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
        {copied ? t("update.copied") : t("update.copyCmd")}
      </button>
      <a href={info.release_url} target="_blank" rel="noopener noreferrer"
        className="text-xs text-zinc-400 underline-offset-2 hover:underline">
        {t("update.changelog")}
      </a>
      <button onClick={() => load(true)}
        className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
        {t("update.check")}
      </button>
      <button onClick={() => localStorage.setItem(DISMISS_KEY, info.latest!)}
        aria-label={t("update.dismiss")}
        className="px-2 text-zinc-500 hover:text-zinc-300">✕</button>
    </div>
  );
}
