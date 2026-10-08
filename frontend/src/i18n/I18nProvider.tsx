import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { Locale } from "./translate";
import { detectLocale, persistLocale } from "./detect";
import { ensureOpenCC } from "./opencc";
import { I18nContext, type TFn } from "./index";
import { translate } from "./translate";

export function I18nProvider({ children, defaultLocale }: { children: ReactNode; defaultLocale?: Locale }) {
  const [locale, setLocaleState] = useState<Locale>(() => defaultLocale ?? detectLocale());
  const [openccReady, setOpenccReady] = useState(false);

  useEffect(() => {
    if (locale !== "zh-TW") return;
    let cancelled = false;
    ensureOpenCC().then(() => { if (!cancelled) setOpenccReady(true); });
    return () => { cancelled = true; };
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    persistLocale(l);
    document.documentElement.lang = l;
  }, []);

  const t = useCallback<TFn>(
    (key, vars) => translate(locale, key, vars),
    // openccReady is read indirectly via translate()/toTraditional when locale === "zh-TW";
    // including it forces consumers to re-render once the converter is loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [locale, openccReady],
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}
