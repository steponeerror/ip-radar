import type { LookupResult, MergedField } from "../api";
import { confColor, confTextColor, ALGORITHM_ICONS, SCORE_SEMANTICS } from "./threatDisplay";
import { useI18n } from "../i18n";
import { ClassificationBlock } from "./ClassificationBlock";

function answerGroups(field: MergedField): { value: any; count: number; weight: number }[] {
  const valid = field.sources.filter(
    (s) => s.value !== null && s.value !== "" && s.value !== "N/A" && s.value !== 0,
  );
  const groups = new Map<any, { value: any; count: number; weight: number }>();
  for (const s of valid) {
    const g = groups.get(s.value) ?? { value: s.value, count: 0, weight: 0 };
    g.count += 1;
    g.weight += s.reliability;
    groups.set(s.value, g);
  }
  const win = (g: { value: any }) => (g.value === field.value ? 1 : 0);
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
  const prob = (g: { value: any }) =>
    field.alternatives?.find((a) => a.value === g.value)?.probability;
  return (
    <div>
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
            {suffix && <span className="ml-1 text-zinc-600">{suffix}</span>}
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
  const classTypes = new Set(classKeys);
  // Service identity: all asset statements, one chip each (role + provider,
  // boolean assets, carrier). is_tor/is_proxy suppressed when a matching
  // classification already renders in the threat section.
  const identityChips: { text: string; detail: string; key: string }[] = [];
  for (const [key, stmts] of Object.entries(r.attributes ?? {})) {
    if (key === "as_domain") continue; // rendered as org suffix above
    if ((key === "is_tor" && classTypes.has("tor")) ||
        (key === "is_proxy" && classTypes.has("proxy"))) continue;
    const labelKey = {
      is_hosting: "asset.is_hosting", is_tor: "asset.is_tor",
      is_vpn: "asset.is_vpn", is_proxy: "asset.is_proxy",
      carrier: "asset.carrier",
    }[key];
    if (key === "service") {
      stmts.forEach((s, i) => {
        identityChips.push({
          text: `${s.value} · ${s.native_type ?? s.value}`,
          detail: s.source,
          key: `service-${i}`,
        });
      });
    } else if (labelKey && stmts[0]) {
      const s = stmts[0];
      identityChips.push({
        text: key === "carrier" ? `${t(labelKey)} · ${s.value}` : t(labelKey),
        detail: `${s.native_type ? s.native_type + " · " : ""}${s.source}`,
        key,
      });
    }
  }
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
        </div>
      )}
      <FieldDetail label="ASN" field={r.asn} format={(v) => String(v)} grouped />
      <FieldDetail
        label={t("ipDetail.org")}
        field={r.as_name}
        format={String}
        suffix={r.attributes?.as_domain?.[0]?.value as string | undefined}
      />
      {identityChips.length > 0 && (
        <div>
          <span className="text-xs font-medium text-zinc-300">{t("ipDetail.serviceIdentity")}</span>
          <div className="ml-3 mt-1 flex flex-wrap gap-1.5">
            {identityChips.map((c) => (
              <span key={c.key} title={c.detail}
                className="rounded bg-sky-500/12 px-1.5 py-0.5 text-[11px] text-sky-400 ring-1 ring-sky-500/20">
                {c.text}
              </span>
            ))}
          </div>
        </div>
      )}
      <div>
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
