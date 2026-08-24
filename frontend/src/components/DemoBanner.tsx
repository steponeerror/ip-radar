import { useI18n } from "../i18n";

/** 公共演示站常驻横幅:告知 demo 限制 + 指路自部署。自部署不渲染(父层判定)。 */
export function DemoBanner() {
  const { t } = useI18n();
  return (
    <div className="border-b border-emerald-900/50 bg-emerald-950/40 px-4 py-2 text-center text-xs text-emerald-300">
      {t("demo.banner")}{" "}
      <a
        className="underline hover:text-emerald-200"
        href="https://github.com/steponeerror/ip-radar"
        target="_blank"
        rel="noreferrer"
      >
        GitHub
      </a>
    </div>
  );
}
