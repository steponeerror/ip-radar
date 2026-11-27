import type { LookupResult, MergedField } from "../api";
import { confColor, confTextColor, ALGORITHM_ICONS, SCORE_SEMANTICS } from "./threatDisplay";
import { useI18n } from "../i18n";
import { ClassificationBlock } from "./ClassificationBlock";
import { assetChips } from "./assetChips";

// 每个信息区块统一的淡色渐变底 + 左侧色条:用同一种颜色过渡划清各信息边界
// (客户反馈区块间无边界不清晰;统一色,不做分色分组)。
const SECTION =
  "rounded-md border-l-2 border-emerald-500/30 bg-gradient-to-r from-emerald-500/5 to-transparent px-3 py-2";

// abuse_contact 下挂行白名单(与后端 _registry context_fields 同名单;CONTEXT.md「下挂行」:
// 单证人融合块内的非融合登记声明,不进 conf)。date=true 的键取 ISO 串日期段呈现
// (「登记新鲜度」:纯日期不表态,判断权归 analyst)。
const ABUSE_CTX: { key: string; label: string; date?: boolean }[] = [
  { key: "contact_name", label: "ipDetail.abuseCtx.name" },
  { key: "notify", label: "ipDetail.abuseCtx.notify" },
  { key: "created", label: "ipDetail.abuseCtx.created", date: true },
  { key: "last_modified", label: "ipDetail.abuseCtx.modified", date: true },
];

function answerGroups<T>(
  field: MergedField<T>,
): { value: T; count: number; weight: number }[] {
  const valid = field.sources.filter(
    (s) => s.value !== null && s.value !== "" && s.value !== "N/A" && s.value !== 0,
  );
  const groups = new Map<T, { value: T; count: number; weight: number }>();
  for (const s of valid) {
    const g = groups.get(s.value) ?? { value: s.value, count: 0, weight: 0 };
    g.count += 1;
    g.weight += s.reliability;
    groups.set(s.value, g);
  }
  const win = (g: { value: T }) => (g.value === field.value ? 1 : 0);
  return [...groups.values()].sort(
    (a, b) =>
      win(b) - win(a) ||
      b.count - a.count ||
      b.weight - a.weight ||
      String(a.value).localeCompare(String(b.value)),
  );
}

function FieldDetail<T>({
  label,
  field,
  format,
  grouped = false,
  suffix,
}: {
  label: string;
  field: MergedField<T>;
  format: (v: T) => string;
  grouped?: boolean;
  suffix?: string;
}) {
  const { t } = useI18n();
  const entries = field.sources;
  if (entries.length === 0) return null;
  const groups = answerGroups(field);
  const showGroups = grouped && groups.length >= 2;
  const prob = (g: { value: T }) =>
    field.alternatives?.find((a) => a.value === g.value)?.probability;
  return (
    <div className={SECTION}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-medium text-zinc-300">{label}</span>
        {showGroups ? (
          <span className="text-[10px] flex items-center gap-1">
            {groups.map((g, i) => (
              <span key={String(g.value)} className="flex items-center gap-0.5">
                {i > 0 && <span className="text-zinc-700">·</span>}
                <span className={g.value === field.value ? "text-zinc-500" : "text-zinc-600"}>
                  {format(g.value)} ({g.count})
                </span>
                {prob(g) !== undefined && (
                  <span className="text-[10px] text-zinc-500" title="posterior">{prob(g)}%</span>
                )}
              </span>
            ))}
          </span>
        ) : (
          <span className="text-[10px] text-zinc-500">
            {format(field.value)}
            {suffix && <span className="ml-1.5 text-zinc-600">· {suffix}</span>}
          </span>
        )}
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${confColor(field.confidence)}`} />
        <span className={`text-[10px] ${confTextColor(field.confidence)}`}>{field.confidence}</span>
        <span className="text-[10px] text-zinc-600" title={SCORE_SEMANTICS[field.algorithm] ? t(SCORE_SEMANTICS[field.algorithm].key) : undefined}>{ALGORITHM_ICONS[field.algorithm] ?? field.algorithm}</span>
      </div>
      <div className="ml-3 flex flex-wrap gap-x-4 gap-y-0.5">
        {entries.map((s) => (
          <span key={s.source} className="text-[11px]">
            <span className="text-zinc-500">{s.source}</span>
            {s.authoritative && (
              <span className="text-amber-400 ml-0.5" title="authoritative">★</span>
            )}
            <span className="text-zinc-700 mx-1">:</span>
            <span className="text-zinc-400">{format(s.value)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function IpDetailPanel({ r }: { r: LookupResult }) {
  const { t } = useI18n();
  const classKeys = Object.keys(r.classifications);
  // Service identity 区的资产 chips:挑键/压制/文案映射/取首条证词/悬停明细
  // 拼法唯一构造器在 assetChips.ts(#486 收编:此前本处持一份 identityChips
  // 手拼,悬停明细顺序与结果表相反;统一为 来源 · 原始类型,carrier 正文
  // 拼值统一为 `文案: 值`);这里只留「放在服务身份区、用什么样式」。
  const identityChips = assetChips(r, t);
  // 展示层去重(2026-10-11 用户反馈"重复展示"):as_org 判定值与 as_name 一致时,把
  // caida 证人折进 Operator 行 chips,不再单开一块(证据不灭失;仅展示合并,不动
  // 置信度/算法——宁少算);值不同时两块分立,两轴本就独立。
  const orgDup =
    r.as_org && String(r.as_org.value) === String(r.as_name.value) ? r.as_org : null;
  const orgField = orgDup
    ? { ...r.as_name, sources: [...r.as_name.sources, ...orgDup.sources] }
    : r.as_name;
  return (
    <div className="grid gap-2.5">
      <FieldDetail label={t("ipDetail.country")} field={r.country} format={String} grouped />
      <FieldDetail
        label={t("ipDetail.city")}
        field={r.city}
        format={String}
        grouped
        suffix={r.city_zh ?? undefined}
      />
      {r.location && (
        <div className="text-[10px] text-zinc-600"
          title={r.location.accuracy_radius ? `±${r.location.accuracy_radius} km` : undefined}>
          📍 {r.location.lat.toFixed(2)}, {r.location.lon.toFixed(2)}
          {r.location.time_zone && <span className="ml-1.5">🕒 {r.location.time_zone}</span>}
        </div>
      )}
      <FieldDetail label="ASN" field={r.asn} format={(v) => String(v)} grouped />
      <FieldDetail
        label={t("ipDetail.org")}
        field={orgField}
        format={String}
        suffix={r.attributes?.as_domain?.[0]?.value as string | undefined}
      />
      {r.as_org && !orgDup && (
        <FieldDetail
          label={t("ipDetail.asOrg")}
          field={r.as_org}
          format={String}
        />
      )}
      {r.abuse_contact && (
        <FieldDetail
          label={t("ipDetail.abuseContact")}
          field={r.abuse_contact}
          format={String}
        />
      )}
      {/* 下挂行:视觉层级小一号、灰(text-[10px] zinc-600),不与融合值/来源芯片混淆 */}
      {r.abuse_contact?.context && (
        <div className="ml-3 -mt-1 space-y-px">
          {ABUSE_CTX.map(({ key, label, date }) => {
            const v = r.abuse_contact?.context?.[key];
            if (!v) return null;   // 缺席键不造(宁少算)
            return (
              <div key={key} className="text-[10px] text-zinc-600">
                {t(label)}: {date ? v.slice(0, 10) : v}
              </div>
            );
          })}
        </div>
      )}
      {r.org_name && (
        <FieldDetail
          label={t("ipDetail.orgName")}
          field={r.org_name}
          format={String}
        />
      )}
      {r.registration && (
        <div className={SECTION}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-zinc-300">{t("ipDetail.registration")}</span>
            <span className="text-[10px] text-zinc-500">
              {r.registration.registry}
              {r.registration.alloc_date && ` · ${r.registration.alloc_date}`}
              {r.registration.status && ` · ${r.registration.status}`}
              {r.registration.reg_country && ` · ${r.registration.reg_country}`}
            </span>
          </div>
        </div>
      )}
      {identityChips.length > 0 && (
        <div className={SECTION}>
          <span className="text-xs font-medium text-zinc-300">{t("ipDetail.serviceIdentity")}</span>
          <div className="ml-3 mt-1 flex flex-wrap gap-1.5">
            {identityChips.map((c) => (
              <span key={c.key} title={c.detail}
                className="rounded bg-sky-500/12 px-1.5 py-0.5 text-[11px] text-sky-400 ring-1 ring-sky-500/20">
                {c.label}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className={SECTION}>
        <span className="text-xs font-medium text-zinc-300">{t("ipDetail.threatDetails")}</span>
        {classKeys.length === 0 ? (
          <div className="ml-3 mt-1 text-[11px] text-zinc-600">{t("ipDetail.noHits")}</div>
        ) : (
          <div className="ml-3 mt-1 space-y-2.5">
            {classKeys.map((type) => (
              <ClassificationBlock key={type} type={type} ca={r.classifications[type]} />
            ))}
          </div>
        )}
      </div>
      <FieldDetail label={t("ipDetail.range")} field={r.ip_range} format={String} />
    </div>
  );
}
