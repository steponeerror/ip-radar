import { useI18n } from "../i18n";

/** 公共演示站常驻横幅:告知 demo 限制 + 指路自部署。自部署不渲染(父层判定)。 */
export function DemoBanner() {
  const { t } = useI18n();
  return (
    <div className="border-b border-zinc-800 bg-zinc-900/60 px-4 py-2 text-center text-xs text-emerald-400">
      {t("demo.banner")}{" "}
      <a
        className="underline hover:text-emerald-500"
        href="https://github.com/steponeerror/ip-radar"
        target="_blank"
        rel="noreferrer"
      >
        GitHub
      </a>
    </div>
  );
}
