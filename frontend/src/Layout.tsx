import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { DbStatusBar } from "./components/DbStatusBar";
import { LocaleSwitcher } from "./components/LocaleSwitcher";
import { Modal } from "./components/Modal";
import { UpdateOverlay, TOKEN_KEY } from "./components/UpdateOverlay";
import { VersionBanner } from "./components/VersionBanner";
import { getDbStatus, getVersion, postUpdate } from "./api";
import { useI18n } from "./i18n";
import { TaskProvider } from "./tasks/TaskProvider";

// ponytail: 开闸后不再重臂——中途 backend 重启进新冷启动时横幅可能与 warmup 横幅
// 短暂并存(罕见;更新触发的重启由 UpdateOverlay 全屏盖住)。要严格 D9 再加轮询重臂。
function useWarmupGate(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const poll = async () => {
      // WarmingProvider 挂在 LookupView(Layout 之下),这里够不到 context——
      // D9 让位只能自带最小轮询:见首个非 warming 即永久开闸(api 挂了也开,
      // 横幅自身的 getVersion 失败会静默不渲染)。
      const s = await getDbStatus().catch(() => null);
      if (!alive) return;
      if (!s || !s.warming_up) { setOpen(true); return; }
      timer = window.setTimeout(poll, 5000);
    };
    poll();
    return () => { alive = false; if (timer !== undefined) clearTimeout(timer); };
  }, []);
  return open;
}

export default function Layout() {
  const { t } = useI18n();
  const warmGate = useWarmupGate();
  const [selfUpdateEnabled, setSelfUpdateEnabled] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [token, setToken] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [overlayActive, setOverlayActive] = useState(false);
  const versionSnapshot = useRef("");

  useEffect(() => {
    // 横幅按钮可见性所需的 self_update_enabled;L2 解锁需改 compose+重启(整页重载),挂载拉一次即够
    getVersion().then((v) => setSelfUpdateEnabled(v.self_update_enabled)).catch(() => {});
  }, []);

  const openConfirm = () => {
    setToken(localStorage.getItem(TOKEN_KEY) ?? "");
    setTokenError(null);
    setConfirmOpen(true);
  };

  const beginOverlay = async () => {
    setConfirmOpen(false);
    try { versionSnapshot.current = (await getVersion()).current; } catch { /* 快照失败置空:首个成功的 current !== "" 即判成功 */ }
    setOverlayActive(true);
  };

  const startUpdate = async () => {
    const tk = token.trim();
    if (!tk) { setTokenError(t("update.tokenMissing")); return; }
    try {
      const r = await postUpdate(tk);
      if (r.status === 202 || r.status === 409) {  // 已接受 / 已在更新中,都进全屏态
        localStorage.setItem(TOKEN_KEY, tk);
        await beginOverlay();
      } else {
        setTokenError(t("update.tokenInvalid"));  // 403:令牌错(未配 token 时后端恒 403,同文案覆盖)
      }
    } catch {
      setTokenError(t("update.failed"));
    }
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-4 py-2 text-sm font-medium transition-colors ${
      isActive ? "bg-zinc-800 text-emerald-400" : "text-zinc-500 hover:text-zinc-300"
    }`;

  return (
    <TaskProvider>
      <div className="dot-grid min-h-screen pb-14">
        <div className="mx-auto max-w-7xl px-4 py-8 lg:px-8">
          <header className="mb-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
                  {t("layout.title")}
                </h1>
                <p className="mt-1 text-sm text-zinc-500">{t("layout.subtitle")}</p>
              </div>
              <LocaleSwitcher />
            </div>
            <nav className="mt-4">
              <div className="flex gap-1 rounded-lg bg-zinc-900 p-1 sm:inline-flex">
                <NavLink to="/" end className={linkClass}>{t("layout.nav.lookup")}</NavLink>
                <NavLink to="/sources" className={linkClass}>{t("layout.nav.sources")}</NavLink>
              </div>
            </nav>
          </header>
          {warmGate && (
            <VersionBanner
              selfUpdateEnabled={selfUpdateEnabled}
              onStartUpdate={openConfirm}
            />
          )}
          <Outlet />
          <footer className="mt-10 flex items-center justify-center gap-2 text-xs text-zinc-600">
            <span>© 2026 steponeerror</span>
            <a
              href="https://github.com/steponeerror/ip-radar"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="GitHub"
              className="text-zinc-600 transition-colors hover:text-zinc-300"
            >
              <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
              </svg>
            </a>
          </footer>
        </div>
        <DbStatusBar />
      </div>

      <Modal
        open={confirmOpen}
        title={t("update.confirmTitle")}
        onClose={() => setConfirmOpen(false)}
      >
        <label className="block text-xs text-zinc-500" htmlFor="update-token">
          {t("update.tokenLabel")}
        </label>
        <input
          id="update-token"
          type="password"
          value={token}
          onChange={(e) => { setToken(e.target.value); setTokenError(null); }}
          className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-emerald-600 focus:outline-none"
        />
        {tokenError && <p className="mt-2 text-xs text-red-400">{tokenError}</p>}
        <button
          type="button"
          onClick={startUpdate}
          className="mt-3 rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-zinc-950 transition-transform hover:scale-[1.02] active:scale-[0.98]"
        >
          {t("update.start")}
        </button>
      </Modal>

      <UpdateOverlay
        active={overlayActive}
        startedVersion={versionSnapshot.current}
        reload={() => location.reload()}
      />
    </TaskProvider>
  );
}
