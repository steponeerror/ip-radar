import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { getVersion, type VersionInfo } from "../api";
import { copyText } from "../lib/utils";

const DISMISS_KEY = "dismissed_version";
const UPDATE_CMD = "git pull && docker compose up -d --build";

export function VersionBanner({ selfUpdateEnabled, onStartUpdate }: {
  selfUpdateEnabled: boolean;
  onStartUpdate: () => void;
}) {
  const { t } = useI18n();
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [copied, setCopied] = useState(false);
  // dismiss 必须进 state:只写 localStorage 不触发 re-render,横幅不会消失
  const [dismissed, setDismissed] = useState<string | null>(
    () => localStorage.getItem(DISMISS_KEY),
  );

  const load = async (refresh = false) => {
    try { setInfo(await getVersion(refresh)); } catch { /* 静默:版本检查失败不打扰 */ }
  };
  // 挂载拉一次:回调式 setState(.then)是 effect 内合法形态;直接调用含
  // setState 的 async 函数会触发 react-hooks/set-state-in-effect。
  useEffect(() => {
    getVersion().then(setInfo).catch(() => { /* 静默:版本检查失败不打扰 */ });
  }, []);

  if (!info?.update_available) return null;
  if (dismissed === info.latest) return null;

  const copyCmd = async () => {
    if (await copyText(UPDATE_CMD)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="mx-auto mt-4 flex max-w-7xl items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-900/60 px-4 py-3 text-sm">
      <span className="text-emerald-400">🔄</span>
      <div className="min-w-0 flex-1">
        <span className="text-zinc-200">
          {t("update.bannerTitle", { latest: info.latest!, current: info.current })}
        </span>
        {info.summary && <p className="truncate text-xs text-zinc-500">{info.summary}</p>}
        <p className="text-xs text-zinc-600">{t("update.cmdHint")}</p>
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
      <button onClick={() => {
          localStorage.setItem(DISMISS_KEY, info.latest!);
          setDismissed(info.latest!);
        }}
        aria-label={t("update.dismiss")}
        className="px-2 text-zinc-500 hover:text-zinc-300">✕</button>
    </div>
  );
}
