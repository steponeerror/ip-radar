import type { LookupResult } from "../api";

export function confColor(conf: number): string {
  if (conf >= 70) return "bg-emerald-500";
  if (conf >= 30) return "bg-amber-500";
  return "bg-red-500";
}

export function confTextColor(conf: number): string {
  if (conf >= 70) return "text-emerald-400";
  if (conf >= 30) return "text-amber-400";
  return "text-red-400";
}

export const VERDICT_STYLE: Record<string, string> = {
  malicious: "bg-red-500/15 text-red-300 ring-1 ring-red-500/30",
  suspicious: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30",
  benign: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30",
  informational: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/25",
  clean: "bg-zinc-700/40 text-zinc-500 ring-1 ring-zinc-600/40",
  reserved: "bg-zinc-600/30 text-zinc-300 ring-1 ring-zinc-500/40",
};

export const VERDICT_RANK: Record<string, number> = {
  malicious: 3, suspicious: 2, benign: 1, informational: 0, clean: 0, reserved: 0,
};

export const ALGORITHM_ICONS: Record<string, string> = {
  cascade: "🔑",
  voting: "📊",
  logodds: "σ",
  authority: "🏛️",
  specificity: "🎯",
  corroboration: "🤝",
};

// C1 legend-grade semantics: what each merge algorithm's confidence number
// MEANS. cascade/pcr6 are legacy values from the retired three-stage threat
// merge (any-authoritative-wins / PCR6 belief fusion, removed 2026-07);
// today's backend emits voting/logodds/authority/specificity only — kept so
// every algorithm string still resolves to honest semantics.
export const SCORE_SEMANTICS: Record<string, { badge: string; key: string }> = {
  logodds:     { badge: "σ P",       key: "semantics.posterior" },
  voting:      { badge: "▮ share",   key: "semantics.consensus" },
  authority:   { badge: "★ r",       key: "semantics.calibration" },
  specificity: { badge: "◇ fixed",   key: "semantics.anchor" },
  cascade:     { badge: "🔑 cascade", key: "semantics.cascade" },
  pcr6:        { badge: "∑ pcr6",    key: "semantics.pcr6" },
};

const CLASS_KEYS: Record<string, string> = {
  "c2_server": "class.c2_server",
  botnet_cc: "class.botnet_cc",
  scanner: "class.scanner",
  brute_force: "class.brute_force",
  malware: "class.malware",
  malware_distribution: "class.malware_distribution",
  botnet: "class.botnet",
  exploit: "class.exploit",
  phishing: "class.phishing",
  ddos: "class.ddos",
  blacklist: "class.blacklist",
  abuse_reports: "class.abuse_reports",
  spam: "class.spam",
  other: "class.other",
  tor: "class.tor",
  proxy: "class.proxy",
  hosting: "class.hosting",
  vpn: "class.vpn",
};

export function normType(type: string): string {
  return type.replace(/-/g, "_");
}

export function verdictLabelKey(code: string): string {
  return `verdict.${code}`;
}

export function classLabel(type: string, t: (key: string, vars?: Record<string, string | number>) => string): string {
  const key = CLASS_KEYS[normType(type)];
  return key ? t(key) : normType(type).replace(/_/g, " ");
}

export function familyShort(name: string): string {
  return name.replace(/^(win|linux|mac|osx|android|ios|trojan|worm|backdoor)[._-]/i, "");
}

export function threatSummary(r: LookupResult): {
  verdict: string;
  confidence: number;
  sourceCount: number;
  corroborated: boolean;
  conflict: boolean;
  hasThreats: boolean;
} {
  if (r.is_reserved) {
    return { verdict: "reserved", confidence: 0, sourceCount: 0,
      corroborated: false, conflict: false, hasThreats: false };
  }
  const cas = Object.values(r.classifications).filter((c) => c.detected && c.confidence > 0);
  if (cas.length === 0) {
    return { verdict: "clean", confidence: 0, sourceCount: 0, corroborated: false, conflict: false, hasThreats: false };
  }
  let worst = cas[0];
  for (const c of cas) {
    if ((VERDICT_RANK[c.verdict] ?? 0) > (VERDICT_RANK[worst.verdict] ?? 0)) worst = c;
  }
  const worstVerdict = worst.verdict;
  const confidence = Math.max(...cas.filter((c) => c.verdict === worstVerdict).map((c) => c.confidence));
  const sources = new Set<string>();
  for (const c of cas) for (const s of c.sources) sources.add(s.source);
  return {
    verdict: worstVerdict,
    confidence,
    sourceCount: sources.size,
    corroborated: cas.some((c) => c.corroborated),
    conflict: cas.some((c) => c.verdict_conflict),
    hasThreats: true,
  };
}
