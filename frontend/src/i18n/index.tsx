import { createContext, useContext } from "react";
import type { Locale } from "./translate";

type Vars = Record<string, string | number>;
export type TFn = (key: string, vars?: Vars) => string;

export interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: TFn;
}

// 组件(I18nProvider)拆到 ./I18nProvider.tsx:本文件只留 context + hook,
// 避免 react-refresh/only-export-components(组件与 hook 混导出)。
export const I18nContext = createContext<I18nContextValue | null>(null);

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within an I18nProvider");
  return ctx;
}

export type { Locale };
