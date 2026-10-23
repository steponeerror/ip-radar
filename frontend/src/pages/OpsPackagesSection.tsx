import { useCallback, useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { Modal } from "../components/Modal";
import {
  listOpsPackages, readOpsPackage, readOpsPrecedent,
  type ApiError, type OpsPackageInfo,
} from "../api";
import { opsErrorText } from "./opsErrorText";
import { relTime } from "./opsTable";
import { SectionHead } from "./OpsSectionHead";
import { useArrivalNow } from "./useArrivalNow";

// 旧包报告档案(P1 T4,票 #156,spec #152 §4;ADR 0006):markdown 包降级为
// 条目集的只读渲染视图——列表 → 详情(报告文逐字:证据三元组/trace 原样
// 保留,判例引用可点开全文),不再承载审阅。人裁交互面(旧「逐字选建议行
// + 三动作」)已移除:四键审阅在「审阅」子 tab(OpsReviewSection),本节
// 驻「档案」子 tab(只读审计面:历史/规则/报告)。mono 数据/文件名分轨
// 不变(文件名仍 packages/ 下的原词)。

// 判例引用文件名(注入判例节引用 YYYY-MM-DD-<slug>.md;人裁落判例
// YYYY-MM-DD-ruling-<hex>.md 同形)——只做「可点开」识别,存在性由读取端点
// 判(404 → 可读文案,不伪装空)。
const PRECEDENT_REF_RE = /(\d{4}-\d{2}-\d{2}-[A-Za-z0-9._-]+\.md)/;

// 报告文逐字渲染(证据三元组/trace 原样保留);判例文件名替换为可点按钮。
function PackageText({ text, onOpenPrecedent }: {
  text: string;
  onOpenPrecedent: (name: string) => void;
}) {
  const parts = text.split(PRECEDENT_REF_RE);
  return (
    <pre className="max-h-[28rem] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-300">
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <button
            key={i}
            type="button"
            onClick={() => onOpenPrecedent(p)}
            className="text-emerald-400 underline decoration-emerald-500/40 underline-offset-2 transition-colors hover:text-emerald-300"
          >
            {p}
          </button>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </pre>
  );
}

export default function OpsPackagesSection({ onUnauthorized, roundTick }: {
  onUnauthorized: () => void;
  roundTick: number; // 轮次收口(done/failed/cancelled)时 +1 → 重拉列表
}) {
  const { t } = useI18n();
  const [packages, setPackages] = useState<OpsPackageInfo[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  // 相对时间基准 = 列表抵达时刻(#149;useArrivalNow,Date.now 不入 render)
  const [now, markArrived] = useArrivalNow();
  const [detailName, setDetailName] = useState<string | null>(null);
  const [detailText, setDetailText] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  // 判例全文弹窗
  const [precName, setPrecName] = useState<string | null>(null);
  const [precText, setPrecText] = useState<string | null>(null);
  const [precError, setPrecError] = useState<string | null>(null);

  const failWith = (set: (s: string) => void, fallback: string) => (e: unknown) => {
    if ((e as ApiError).status === 401) { onUnauthorized(); return; }
    set(opsErrorText(t, e, fallback));
  };

  const load = useCallback(async () => {
    setListError(null);
    try {
      setPackages(await listOpsPackages());
      markArrived();
    } catch (e) {
      failWith(setListError, t("ops.pkgs.loadFailed"))(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, onUnauthorized, markArrived]);

  // 挂载 + 轮次收口(roundTick)重拉
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load, roundTick]);

  const openDetail = (name: string) => {
    setDetailName(name); setDetailText(null); setDetailError(null);
    readOpsPackage(name)
      .then(setDetailText)
      .catch(failWith(setDetailError, t("ops.pkgs.loadFailed")));
  };

  const openPrecedent = (name: string) => {
    setPrecName(name); setPrecText(null); setPrecError(null);
    readOpsPrecedent(name)
      .then(setPrecText)
      .catch(failWith(setPrecError, t("ops.prec.loadFailed")));
  };

  const title = (
    // 票 #149:节头计数(报告 N 个)属列表面;详情态无行集可数,不带计数
    <SectionHead title={t("ops.pkgs.title")} count={detailName ? null : (packages?.length ?? null)}>
      {/* 裸文字链接 → 描边按钮(票 #147;硬规④) */}
      {detailName && (
        <button
          type="button"
          onClick={() => { setDetailName(null); setDetailText(null); setDetailError(null); }}
          className="rounded-md border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 transition-colors hover:border-emerald-500/50 hover:text-emerald-400"
        >
          {t("ops.pkgs.back")}
        </button>
      )}
    </SectionHead>
  );

  if (detailName) {
    return (
      <section aria-label={t("ops.pkgs.title")} className="mt-8">
        {title}
        {detailError && (
          <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
            {detailError}
          </p>
        )}
        {/* 只读渲染:报告文逐字,零审阅交互(人裁面已迁「审阅」子 tab) */}
        {detailText != null && <PackageText text={detailText} onOpenPrecedent={openPrecedent} />}
        <Modal
          open={precName != null}
          title={precName ?? ""}
          onClose={() => { setPrecName(null); setPrecText(null); setPrecError(null); }}
          closeLabel={t("ops.prec.close")}
        >
          {precError ? (
            <p role="alert" className="text-xs text-red-400">{precError}</p>
          ) : precText != null ? (
            <pre className="max-h-[60vh] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-300">
              {precText}
            </pre>
          ) : (
            <p className="text-xs text-zinc-500">{t("sources.pageLoading")}</p>
          )}
        </Modal>
      </section>
    );
  }

  // 列表态
  return (
    <section aria-label={t("ops.pkgs.title")} className="mt-8">
      {title}
      {listError && (
        <p role="alert" className="mt-3 rounded-md border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-400">
          {listError}
        </p>
      )}
      {/* 票 #149:空列表显基准「暂无」式居中空态(硬规⑥),不留纯空白 */}
      {packages != null && packages.length === 0 && !listError && (
        <div className="mt-3 rounded-md border border-zinc-800">
          <p className="px-3 py-6 text-center text-xs text-zinc-500">{t("ops.pkgs.empty")}</p>
        </div>
      )}
      {packages != null && packages.length > 0 && (
        <ul className="mt-3 divide-y divide-zinc-800 rounded-md border border-zinc-800">
          {/* 票 #149:行元数据 = 大小 KB + 相对时间(title=ISO 原文,证据
              不灭失);密度向源管理列表看齐(px-4 py-2.5,文件名 text-sm) */}
          {packages.map((p) => {
            const rt = relTime(p.modified, now);
            return (
              <li key={p.name}>
                <button
                  type="button"
                  onClick={() => openDetail(p.name)}
                  className="flex w-full items-baseline gap-x-3 px-4 py-2.5 text-left transition-colors hover:bg-zinc-900"
                >
                  <span className="font-mono text-sm text-emerald-400">{p.name}</span>
                  <span className="ml-auto whitespace-nowrap font-mono text-xs text-zinc-500">
                    {(p.size / 1024).toFixed(1)} KB
                  </span>
                  <span
                    className="whitespace-nowrap font-mono text-xs text-zinc-500"
                    title={rt.title}
                  >
                    {t(rt.key, rt.vars)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {/* 判例全文弹窗:仅详情态(报告内引用可点)可开 */}
    </section>
  );
}
