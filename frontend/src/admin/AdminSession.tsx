import { useCallback, useEffect, useState } from "react";
import { adminLogin, adminLogout, adminMe, type AdminUserRead } from "../api";

// login 的错误信息保持原始(信封 message/code/retry_after),i18n 渲染留在视图层
// —— hook 是 Task 9 的消费面,只做传输态。
export type LoginOutcome =
  | { ok: true }
  | { ok: false; message: string; code?: string; retryAfter?: number };

// admin 会话态(spec 2026-09-21 §9):会话在 HttpOnly cookie ipradar_admin,
// 客户端不持有 token;user 为 null 即回登录表单(401 踢回同路径)。
export function useAdminSession(): {
  user: AdminUserRead | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginOutcome>;
  logout: () => Promise<void>;
  handleUnauthorized: () => void;
} {
  const [user, setUser] = useState<AdminUserRead | null>(null);
  const [loading, setLoading] = useState(true); // 首次 adminMe 探测中

  useEffect(() => {
    let alive = true;
    adminMe()
      .then((u) => { if (alive) setUser(u); })
      .catch(() => {}) // 网络失败按未登录处理,不阻塞表单
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<LoginOutcome> => {
    try {
      await adminLogin(email, password);
      // 登录 204 无 body — 会态以 me 复核为准(cookie 未生效即视为未登录)
      const me = await adminMe();
      if (!me) return { ok: false, message: "Login failed" };
      setUser(me);
      return { ok: true };
    } catch (e) {
      return {
        ok: false,
        message: (e as Error).message,
        code: (e as { code?: string }).code,
        retryAfter: (e as { retry_after?: number }).retry_after,
      };
    }
  }, []);

  const logout = useCallback(async () => {
    await adminLogout().catch(() => {}); // 后端清 cookie;网络失败也本地登出
    setUser(null);
  }, []);

  // 会话中 401(7 天 cookie 过期/服务端重启/auth.db 重建):只清本地态,
  // 不打登出网络请求(spec §9 踢回登录页;AdminPage 卸壳即断 SSE)。
  const handleUnauthorized = useCallback(() => setUser(null), []);

  return { user, loading, login, logout, handleUnauthorized };
}
