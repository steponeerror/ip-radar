import { useState } from "react";
import type { ClassificationDetail } from "../api";
import { verdictLabelKey, VERDICT_STYLE, localizeScannerLabel } from "./threatDisplay";
import { useI18n } from "../i18n";

function fmtRel(r: number): string {
  return String(Math.round(r * 100) / 100);
}

function fmtDate(iso: string): string {
  return iso.slice(0, 10);
}

function extraHref(key: string, v: unknown): string | null {
  if (typeof v === "string" && /^https?:\/\//.test(v)) return v;
  if (key === "sbl_id" && typeof v === "string" && /^SBL\d+$/.test(v))
    return `https://check.spamhaus.org/sbl/query/${v}`;
  if (key === "threatfox_ioc" && typeof v === "string" && /^\d+$/.test(v))
    return `https://threatfox.abuse.ch/ioc/${v}/`;
  return null;
}

// honyport 自建蜜罐观测可读行(#273;spec 2026-11-02 §1 证据语义:只报
// 事实「30 天内观测到攻击,共 X 次」+ 服务列表 + 最后观测,不评 severity)。
// 字段契约 = backend HonyportSource.parse_row(#272,tests/sources/
// test_honyport.py::test_query_evidence_shape):服务 → native_categories
// 列表、last_seen ISO 串、计数 → extra.total_events。按源名点名(该文案
// 的 30 天窗口语义仅此源成立)。
const HONYPORT = "honyport";

// honyport 二期手法明细(#283;spec 2026-11-03 §4):消费 extra.techniques
// 八字段(契约 = backend HonyportSource._TECHNIQUES_FIELDS,票 A 冻结)。
// 主渲染 commands(前 3 + 共 N 条截断计数)、cves 徽标(纯文本,不链接
// 外站 —— 纯本地红线精神,无出站)、user_agents;其余五字段进折叠。值
// 只认非空 string 数组(畸形值按缺席,不渲染不炸行);空字段一律不
// 渲染;文案只报事实,沿用一期「30 天内观测到」口径。
const TECHNIQUES_CMD_MAX = 3;   // 主渲染截断:前 3 条 + 共 N 条(spec §4)
const TECHNIQUES_FOLD_KEYS: ReadonlyArray<readonly [string, string]> = [
  ["protocols", "sourceDetail.honeypotProtocols"],
  ["statuses", "sourceDetail.honeypotStatuses"],
  ["actions", "sourceDetail.honeypotActions"],
  ["stages", "sourceDetail.honeypotStages"],
  ["paths", "sourceDetail.honeypotPaths"],
];

function nonEmptyStrings(v: unknown): string[] | null {
  if (!Array.isArray(v)) return null;
  const items = v.filter((x): x is string => typeof x === "string");
  return items.length > 0 ? items : null;
}

interface TechniquesView {
  commands: string[] | null;
  cves: string[] | null;
  userAgents: string[] | null;
  fold: ReadonlyArray<{ labelKey: string; items: string[] }>;
}

function techniquesView(raw: unknown): TechniquesView | null {
  if (typeof raw !== "object" || raw === null) return null;
  const rec = raw as Record<string, unknown>;
  const fold = TECHNIQUES_FOLD_KEYS
    .map(([key, labelKey]) => ({ labelKey, items: nonEmptyStrings(rec[key]) }))
    .filter((f): f is { labelKey: string; items: string[] } => f.items !== null);
  const view: TechniquesView = {
    commands: nonEmptyStrings(rec["commands"]),
    cves: nonEmptyStrings(rec["cves"]),
    userAgents: nonEmptyStrings(rec["user_agents"]),
    fold,
  };
  return view.commands || view.cves || view.userAgents || fold.length
    ? view
    : null;   // 八字段全空 → 整块不渲染
}

export function SourceDetailRow({ detail: d }: { detail: ClassificationDetail }) {
  const { t } = useI18n();
  const [showExtra, setShowExtra] = useState(false);
  const [showTechniques, setShowTechniques] = useState(false);
  const nativeChips: string[] = d.native_categories ?? [];
  // honyport 行的 techniques 键由下方可读渲染接管,不进通用 extra 原始
  // JSON 折叠 —— 同一事实不双列(宁少算);键数照实少一
  const extraKeys = d.extra
    ? Object.keys(d.extra).filter(
        (k) => !(d.source === HONYPORT && k === "techniques"))
    : [];
  const hasExtra = extraKeys.length > 0;
  const hasTags = !!(d.tags && d.tags.length > 0);
  const honeypotEvents =
    d.source === HONYPORT && typeof d.extra?.total_events === "number"
      ? d.extra.total_events
      : null;
  const techniques =
    d.source === HONYPORT ? techniquesView(d.extra?.["techniques"]) : null;

  return (
    <div className="text-[10px] leading-relaxed">
      <div>
        <span className="text-zinc-600">{d.source}</span>
        <span className="text-zinc-700"> · rel {fmtRel(d.reliability)}</span>
        {d.verdict && (
          <span
            className={`ml-1 rounded px-1 py-px ${VERDICT_STYLE[d.verdict] ?? VERDICT_STYLE.informational}`}
            title={t("sourceDetail.verdictTitle")}
          >
            {t(verdictLabelKey(d.verdict))}
          </span>
        )}
        {nativeChips.map((c, i) => (
          <span key={`nc-${i}`} className="rounded bg-sky-800/40 px-1 py-px mr-0.5 ml-1 text-sky-300" title={t("sourceDetail.nativeTypeTitle")}>[{localizeScannerLabel(c, t)}]</span>
        ))}
        {d.native_confidence != null && (
          <span className="text-zinc-500 ml-1">native {d.native_confidence}</span>
        )}
        {d.first_seen && (
          <span className="text-zinc-700 ml-1">first {fmtDate(d.first_seen)}</span>
        )}
        {d.last_seen && (
          <span className="text-zinc-700 ml-1">last {fmtDate(d.last_seen)}</span>
        )}
      </div>

      {honeypotEvents != null && (
        <div className="ml-3 text-zinc-300">
          <span>{t("sourceDetail.honeypotObserved", { n: honeypotEvents })}</span>
          {nativeChips.length > 0 && (
            <span>
              {" · "}{t("sourceDetail.honeypotServices")}: {nativeChips.join(", ")}
            </span>
          )}
          {d.last_seen && (
            <span>{" · "}{t("sourceDetail.honeypotLastSeen")} {fmtDate(d.last_seen)}</span>
          )}
        </div>
      )}

      {techniques &&
        (techniques.commands || techniques.cves || techniques.userAgents) && (
          <div className="ml-3 text-zinc-300">
            {techniques.commands && (
              <div className="break-all">
                <span>
                  {t("sourceDetail.honeypotCommands")}:{" "}
                  {techniques.commands.slice(0, TECHNIQUES_CMD_MAX).join(", ")}
                </span>
                {techniques.commands.length > TECHNIQUES_CMD_MAX && (
                  <span className="text-zinc-500">
                    {" · "}{t("sourceDetail.honeypotTotal", {
                      n: techniques.commands.length,
                    })}
                  </span>
                )}
              </div>
            )}
            {techniques.cves && (
              <div>
                <span>{t("sourceDetail.honeypotCves")}:{" "}</span>
                {techniques.cves.map((cve) => (
                  <span
                    key={cve}
                    className="rounded bg-rose-900/40 px-1 py-px mr-0.5 text-rose-300"
                  >
                    {cve}
                  </span>
                ))}
              </div>
            )}
            {techniques.userAgents && (
              <div className="break-all">
                <span>
                  {t("sourceDetail.honeypotUserAgents")}:{" "}
                  {techniques.userAgents.join(", ")}
                </span>
              </div>
            )}
          </div>
        )}

      {techniques && techniques.fold.length > 0 && (
        <div className="ml-3">
          <button
            type="button"
            onClick={() => setShowTechniques((v) => !v)}
            className="text-zinc-600 hover:text-zinc-400"
          >
            {showTechniques ? "▾" : "▸"}{" "}
            {t("sourceDetail.honeypotTechniques")}
          </button>
          {showTechniques && (
            <div className="mt-0.5 text-zinc-500">
              {techniques.fold.map(({ labelKey, items }) => (
                <div key={labelKey} className="break-all">
                  <span className="text-zinc-600">{t(labelKey)}:{" "}</span>
                  <span>{items.join(", ")}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {(d.malware_name || d.comment) && (
        <div className="ml-3">
          {d.malware_name && (
            <span className="text-purple-400 font-mono">malware: {d.malware_name} </span>
          )}
          {d.comment && (
            <span className="text-zinc-500" title={d.comment}>
              comment: "{d.comment.length > 40 ? d.comment.slice(0, 40) + "…" : d.comment}"
            </span>
          )}
        </div>
      )}

      {(hasTags || d.reporter_count != null) && (
        <div className="ml-3">
          {hasTags && (
            <span className="mr-2">
              {d.tags!.map((t) => (
                <span key={t} className="rounded bg-zinc-700/40 px-1 py-px mr-0.5 text-zinc-400">[{t}]</span>
              ))}
            </span>
          )}
          {d.reporter_count != null && (
            <span className="text-zinc-500">reporters: {d.reporter_count}</span>
          )}
        </div>
      )}

      {hasExtra && (
        <div className="ml-3">
          <button
            type="button"
            onClick={() => setShowExtra((v) => !v)}
            className="text-zinc-600 hover:text-zinc-400"
          >
            {showExtra ? "▾" : "▸"} {t("sourceDetail.extraKeys", { n: extraKeys.length })}
          </button>
          {showExtra && (
            <div className="mt-0.5 text-zinc-500">
              {extraKeys.map((k) => {
                const href = extraHref(k, d.extra![k]);
                return (
                  <div key={k} className="break-all">
                    <span className="text-zinc-600">{k}: </span>
                    {href ? (
                      <a href={href} target="_blank" rel="noopener" className="text-sky-400 hover:underline">
                        {String(d.extra![k])}
                      </a>
                    ) : (
                      <span>{JSON.stringify(d.extra![k])}</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
