import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { getVersion, getUpdateStatus } from "../api";

export const TOKEN_KEY = "update_token";

const POLL_MS = 3000;
const GIVE_UP_MS = 660_000; // 11 分钟兜底:后端 subprocess 上限 600s+余量,仍无进展 → 失败态(N1 对齐)

/**
 * 全屏"更新中"态:容器重建期间服务不可达,前端只能靠轮询感知。
 * 成功判据:getVersion().current !== startedVersion(新容器新版本)→ reload。
 * 失败早浮现:每轮顺带查 /api/update/status,state=failed 立即显示错误
 * (git 冲突等快速失败 ~3-6s 可见,不必等 11 分钟兜底超时)。
 */
export function UpdateOverlay({ active, startedVersion, reload }: {
  active: boolean;
  startedVersion: string;
  reload: () => void;
}) {
  const { t } = useI18n();
  const [failed, setFailed] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!active) return;
    const began = Date.now();
    let alive = true;
    const poll = async () => {
      if (!alive) return;
      try {
        const v = await getVersion();
        if (v.current !== startedVersion) {  // 版本已变 → 更新成功
          reload();
          return;
        }
      } catch { /* 服务不可达 = 容器重建中,继续轮 */ }
      const s = await getUpdateStatus().catch(() => null);
      if (!alive) return;
      if (s?.state === "failed") {
        setFailed(s.error ?? t("update.failed"));
        return;
      }
      if (Date.now() - began > GIVE_UP_MS) {  // 兜底:compose 挂死等
        setFailed(s?.error ?? t("update.failed"));
        return;
      }
      timer.current = window.setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      alive = false;
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, [active]);

  if (!active) return null;
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-zinc-950/95 text-center">
      {failed ? (
        <>
          <p className="text-lg font-semibold text-red-400">{t("update.failed")}</p>
          <pre className="max-w-xl overflow-auto rounded-lg bg-zinc-900 p-4 text-left text-xs text-zinc-400">{failed}</pre>
          <button onClick={() => location.reload()}
            className="rounded-md bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700">
            {t("update.retry")}
          </button>
        </>
      ) : (
        <>
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
          <p className="text-lg font-semibold text-zinc-100">{t("update.overlayTitle")}</p>
          <p className="text-sm text-zinc-500">{t("update.overlayBody")}</p>
          <p className="text-xs text-zinc-600">{t("update.overlayHint")}</p>
        </>
      )}
    </div>
  );
}
