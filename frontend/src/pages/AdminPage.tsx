import { useState, type FormEvent } from "react";
import { useI18n } from "../i18n";
import { useAdminSession, type LoginOutcome } from "../admin/AdminSession";

const SECTIONS = ["sources", "keys", "tasks", "eval"] as const;

// 错误文案优先信封 message;429 换限流文案(retry_after 秒数)。
// 503 admin_disabled 的 message 自带"未配置"提示,走通用分支即可。
function loginErrorText(t: (k: string, v?: Record<string, string | number>) => string, r: LoginOutcome): string {
  if (r.ok) return "";
  if (r.code === "rate_limited") {
    return r.retryAfter != null
      ? t("admin.loginRateLimited", { seconds: r.retryAfter })
      : t("admin.loginFailed");
  }
  return r.message ? `${t("admin.loginFailed")}: ${r.message}` : t("admin.loginFailed");
}

export default function AdminPage() {
  const { t } = useI18n();
  const { user, loading, login, logout } = useAdminSession();
  const [email, setEmail] = useState("admin@ipradar.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <div className="py-20 text-center text-sm text-zinc-500">{t("sources.loading")}</div>;

  if (user) {
    // 四区占位壳(内容 Task 9 填)。TaskProvider 仍挂在 Layout(Task 8 裁决:
    // 公开页 SourcesPage 依赖未断,勿在 AdminPage 叠第二个 SSE 订阅)。
    return (
      <div>
        <div className="mb-6 flex items-center justify-between gap-4">
          <h2 className="text-xl font-bold tracking-tight text-zinc-100">{t("admin.shellTitle")}</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-zinc-500">{user.email}</span>
            <button
              type="button"
              onClick={() => { logout(); }}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-red-500/50 hover:text-red-400"
            >
              {t("admin.logout")}
            </button>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {SECTIONS.map((s) => (
            <section key={s} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5">
              <h3 className="text-sm font-semibold text-zinc-300">{t(`admin.section.${s}`)}</h3>
            </section>
          ))}
        </div>
      </div>
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
  );
}
