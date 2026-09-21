import { useState, type FormEvent } from "react";
import { useI18n } from "../i18n";
import { useAdminSession, type LoginOutcome } from "../admin/AdminSession";
import { TaskProvider, useTasks } from "../tasks/TaskProvider";
import { BatchPanel } from "../admin/BatchPanel";
import { BatchMiniBar } from "../admin/BatchMiniBar";
import KeysSection from "../admin/KeysSection";
import SourcesPage from "./SourcesPage";
import { ThemeToggle } from "../components/ThemeToggle";
import { LocaleSwitcher } from "../components/LocaleSwitcher";
import type { AdminUserRead } from "../api";

// 错误文案优先信封 message;429 换限流文案(retry_after 秒数);
// fastapi-users 的 detail 是库枚举(如 LOGIN_BAD_CREDENTIALS),不进 UI。
const FASTAPI_USERS_ENUM = /^LOGIN_[A-Z_]+$/;

function loginErrorText(t: (k: string, v?: Record<string, string | number>) => string, r: LoginOutcome): string {
  if (r.ok) return "";
  if (r.code === "rate_limited") {
    return r.retryAfter != null
      ? t("admin.loginRateLimited", { seconds: r.retryAfter })
      : t("admin.loginFailed");
  }
  if (r.message && FASTAPI_USERS_ENUM.test(r.message)) return t("admin.loginFailed");
  return r.message ? `${t("admin.loginFailed")}: ${r.message}` : t("admin.loginFailed");
}

// 登录后的顶 tab 壳：品牌行(h1 + email/登出)→ sticky tab bar →
// 当前 tab 内容直出(无包裹 section/h3，各组件自带标题)。
// TaskProvider 包在整壳外层(见 AdminPage)：tasks tab 与 SourcesPage 的
// 进度徽章共用任务上下文，切 tab 不卸载 provider。
// tab 顺序 = 使用频率：Sources → API Keys → Tasks，默认 Sources。
type AdminTab = "sources" | "keys" | "tasks";

function AdminShell({ user, onLogout, onUnauthorized }: {
  user: AdminUserRead;
  onLogout: () => void;
  onUnauthorized: () => void;
}) {
  const { t } = useI18n();
  const { tasks, batch } = useTasks();
  const [tab, setTab] = useState<AdminTab>("sources");

  const tabBtn = (id: AdminTab) =>
    `rounded-md px-4 py-2 text-sm font-medium transition-colors ${
      tab === id ? "bg-zinc-800 text-emerald-400" : "text-zinc-500 hover:text-zinc-300"
    }`;

  const tabs: Array<{ id: AdminTab; key: "admin.tab.sources" | "admin.tab.keys" | "admin.tab.tasks" }> = [
    { id: "sources", key: "admin.tab.sources" },
    { id: "keys", key: "admin.tab.keys" },
    { id: "tasks", key: "admin.tab.tasks" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold tracking-tight text-zinc-100">IP Radar Admin</h1>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <LocaleSwitcher />
          </div>
          <span className="text-sm text-zinc-500">{user.email}</span>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-red-500/50 hover:text-red-400"
          >
            {t("admin.logout")}
          </button>
        </div>
      </div>
      {/* sticky 长源列表滚动时 tab 常驻；样式镜像公开页导航 pill */}
      <nav className="sticky top-0 z-10 mt-6 bg-zinc-950/90 backdrop-blur">
        <div role="tablist" className="flex gap-1 rounded-lg bg-zinc-900 p-1 sm:inline-flex">
          {tabs.map(({ id, key }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={tabBtn(id)}
              onClick={() => setTab(id)}
            >
              {t(key)}
            </button>
          ))}
        </div>
        <BatchMiniBar onOpen={() => setTab("tasks")} />
      </nav>
      <div className="mt-6">
        {tab === "sources" && (
          <SourcesPage manage tasks={tasks} batch={batch} onUnauthorized={onUnauthorized} />
        )}
        {tab === "keys" && <KeysSection onUnauthorized={onUnauthorized} />}
        {tab === "tasks" && <BatchPanel />}
        {/* eval UI 从未存在，将来作为第四 tab 回归 */}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { t } = useI18n();
  const { user, loading, login, logout, handleUnauthorized } = useAdminSession();
  const [email, setEmail] = useState("admin@ipradar.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <div className="py-20 text-center text-sm text-zinc-500">{t("sources.loading")}</div>;

  if (user) {
    return (
      <TaskProvider onUnauthorized={handleUnauthorized}>
        <AdminShell user={user} onLogout={() => { logout(); }} onUnauthorized={handleUnauthorized} />
      </TaskProvider>
    );
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const r = await login(email.trim(), password);
    if (!r.ok) setError(loginErrorText(t, r));
    setBusy(false);
  };

  return (
    <div>
      {/* 品牌行落在 AdminPage(admin-main.tsx 只留框)——登录态与登录后壳同头;
          右缘常驻主题/语言切换器(独立文档无公开页导航可借,恢复/写入共享 localStorage) */}
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold tracking-tight text-zinc-100">IP Radar Admin</h1>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <LocaleSwitcher />
        </div>
      </div>
      <div className="mx-auto mt-10 max-w-sm">
        <form onSubmit={onSubmit} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6">
          <label className="block text-xs text-zinc-500" htmlFor="admin-email">{t("admin.email")}</label>
          <input
            id="admin-email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-emerald-600 focus:outline-none"
          />
          <label className="mt-4 block text-xs text-zinc-500" htmlFor="admin-password">{t("admin.password")}</label>
          <input
            id="admin-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(null); }}
            className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-emerald-600 focus:outline-none"
          />
          {error && <p role="alert" className="mt-3 text-xs text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="mt-4 w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-zinc-950 transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
          >
            {t("admin.login")}
          </button>
        </form>
      </div>
    </div>
  );
}
