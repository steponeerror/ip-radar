import { useState } from "react";
import { useI18n } from "../i18n";

const KEY = "ipradar-theme";

export function ThemeToggle() {
  const { t } = useI18n();
  // main.tsx 在首帧渲染前已根据 localStorage 设好 .light,这里读真值即可
  const [light, setLight] = useState(
    () => document.documentElement.classList.contains("light")
  );

  const toggle = () => {
    const next = !light;
    setLight(next);
    document.documentElement.classList.toggle("light", next);
    localStorage.setItem(KEY, next ? "light" : "dark");
  };

  return (
    <div role="group" aria-label="theme" className="flex rounded-lg bg-zinc-900 p-1">
      <button
        type="button"
        aria-pressed={light}
        title={light ? t("layout.theme.dark") : t("layout.theme.light")}
        aria-label={light ? t("layout.theme.dark") : t("layout.theme.light")}
        onClick={toggle}
        className="rounded-md px-2.5 py-1 text-xs font-medium text-zinc-500 transition-colors hover:text-zinc-300"
      >
        {light ? "☾" : "☀"}
      </button>
    </div>
  );
}
