import { NavLink, Outlet } from "react-router-dom";
import { DbStatusBar } from "./components/DbStatusBar";
import { LocaleSwitcher } from "./components/LocaleSwitcher";
import { useI18n } from "./i18n";
import { TaskProvider } from "./tasks/TaskProvider";

export default function Layout() {
  const { t } = useI18n();
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
    </TaskProvider>
  );
}
