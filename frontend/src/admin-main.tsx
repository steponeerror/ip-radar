import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import AdminPage from "./pages/AdminPage";
import { I18nProvider } from "./i18n";

// 首帧渲染前恢复用户主题选择(默认暗色,无记录不做任何事)
if (localStorage.getItem("ipradar-theme") === "light") {
  document.documentElement.classList.add("light");
}

// 独立管理文档(admin.html 入口):无 Layout/导航/DbStatusBar/横幅,
// 自带最小全屏框 + 一行品牌头。与 main.tsx 共享 I18n/主题恢复。
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <div className="dot-grid min-h-screen">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <h1 className="mb-6 text-xl font-bold tracking-tight text-zinc-100">IP Radar Admin</h1>
          <AdminPage />
        </div>
      </div>
    </I18nProvider>
  </StrictMode>
);
