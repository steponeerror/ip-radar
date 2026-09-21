import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { I18nProvider } from "./i18n";

// 首帧渲染前恢复用户主题选择(默认暗色,无记录不做任何事)
if (localStorage.getItem("ipradar-theme") === "light") {
  document.documentElement.classList.add("light");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
