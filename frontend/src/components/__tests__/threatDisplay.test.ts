import { describe, it, expect } from "vitest";
import {
  classLabel, familyShort, threatSummary, confTextColor, normType,
} from "../threatDisplay";
import { translate } from "../../i18n/translate";
import type { LookupResult } from "../../api";

const enT = (k: string) => translate("en", k);

const mf = (value: string, confidence = 95) => ({
  value, confidence, algorithm: "cascade" as const,
  sources: [{ source: "geo", value, reliability: 0.9, authoritative: true }],
});

const dirty: LookupResult = {
  ip: "1.1.1.1",
  country: mf("US"), city: mf("Mountain View"), asn: mf("1"), as_name: mf("X"), ip_range: mf("1.0.0.0/24"),
  is_isp: false,
  classifications: {
    scanner: { type: "scanner", verdict: "suspicious", detected: true, confidence: 50,
      algorithm: "corroboration", corroborated: false, reporter_total: 0,
      verdict_conflict: false, has_archive: false, malware_names: [], details: [],
      sources: [{ source: "a", value: true, reliability: 0.5, authoritative: false }] },
    // spec 2026-09-06: verdict_conflict 只在 benign×指控真对立时为真 — benign 明细在场才语义成立
    c2_server: { type: "c2_server", verdict: "malicious", detected: true, confidence: 90,
      algorithm: "corroboration", corroborated: true, reporter_total: 2,
      verdict_conflict: true, has_archive: false, malware_names: ["win.x"],
      details: [{ source: "vouch", reliability: 0.6, verdict: "benign" }],
      sources: [{ source: "b", value: true, reliability: 0.8, authoritative: false }] },
  },
  attributes: {},
};

describe("threatDisplay", () => {
  it("classLabel maps known types and normalizes hyphens", () => {
    expect(classLabel("c2_server", enT)).toBe("C2");
    expect(classLabel("brute-force", enT)).toBe("Brute force");
    expect(classLabel("novel_thing", enT)).toBe("novel thing");
  });
  it("normType replaces hyphens with underscores", () => {
    expect(normType("brute-force")).toBe("brute_force");
  });
  it("familyShort strips os prefix", () => {
    expect(familyShort("win.vidar")).toBe("vidar");
    expect(familyShort("remcos")).toBe("remcos");
  });
  it("confTextColor thresholds", () => {
    expect(confTextColor(95)).toBe("text-emerald-400");
    expect(confTextColor(50)).toBe("text-amber-400");
    expect(confTextColor(10)).toBe("text-red-400");
  });
  it("threatSummary picks worst verdict, counts sources, flags corroborated+conflict", () => {
    const s = threatSummary(dirty);
    expect(s.verdict).toBe("malicious");
    expect(s.confidence).toBe(90);
    expect(s.sourceCount).toBe(2);
    expect(s.corroborated).toBe(true);
    expect(s.conflict).toBe(true);
    expect(s.archive).toBe(false);
    expect(s.hasThreats).toBe(true);
  });
  it("threat 在场时消费后端单一真相:confidence 取后端融合分而非本地最坏组选角", () => {
    // 回归 66.132.186.179:本地组内 max=90,后端证据级重融合=94
    const withThreat: LookupResult = {
      ...dirty,
      threat: { verdict: "malicious", confidence: 94, types: ["c2_server", "scanner"], is_cdn: false },
    };
    const s = threatSummary(withThreat);
    expect(s.verdict).toBe("malicious");
    expect(s.confidence).toBe(94);
    expect(s.hasThreats).toBe(true);
  });
  it("threat 在场时 verdict 也以后端为准(即便与本地最坏组选角不同)", () => {
    const backendSaysSuspicious: LookupResult = {
      ...dirty,
      threat: { verdict: "suspicious", confidence: 77, types: ["scanner"], is_cdn: false },
    };
    const s = threatSummary(backendSaysSuspicious);
    expect(s.verdict).toBe("suspicious");
    expect(s.confidence).toBe(77);
  });
  it("旗标不受 threat 在场影响,继续本地推导", () => {
    const withThreat: LookupResult = {
      ...dirty,
      threat: { verdict: "malicious", confidence: 94, types: ["c2_server"], is_cdn: false },
    };
    const s = threatSummary(withThreat);
    expect(s.sourceCount).toBe(2);
    expect(s.corroborated).toBe(true);
    expect(s.conflict).toBe(true);
    expect(s.archive).toBe(false);
  });
  it("无指控组但 threat 在场:verdict/confidence 同样取后端,旗标照旧本地", () => {
    const cleanWithThreat: LookupResult = {
      ...dirty,
      classifications: {},
      threat: { verdict: "benign", confidence: 0, types: [], is_cdn: false },
    };
    const s = threatSummary(cleanWithThreat);
    expect(s.verdict).toBe("benign");
    expect(s.confidence).toBe(0);
    expect(s.hasThreats).toBe(false);
  });
  it("threat 缺失时原样回退本地推导(旧缓存 payload 兼容)", () => {
    const s = threatSummary(dirty);
    expect(s.verdict).toBe("malicious");
    expect(s.confidence).toBe(90);
  });
  it("archive flag reflects has_archive across classifications", () => {
    const withArchive = {
      ...dirty,
      classifications: {
        ...dirty.classifications,
        scanner: { ...dirty.classifications.scanner, has_archive: true },
      },
    };
    expect(threatSummary(withArchive).archive).toBe(true);
    expect(threatSummary(dirty).archive).toBe(false);
  });
  it("threatSummary reports clean when nothing detected", () => {
    const clean = { ...dirty, classifications: {} };
    const s = threatSummary(clean);
    expect(s.hasThreats).toBe(false);
    expect(s.verdict).toBe("clean");
    expect(s.archive).toBe(false);
  });
  it("threatSummary reports reserved when is_reserved", () => {
    const reserved = { ...dirty, is_reserved: true, classifications: {} };
    const s = threatSummary(reserved);
    expect(s.verdict).toBe("reserved");
    expect(s.hasThreats).toBe(false);
    expect(s.archive).toBe(false);
  });
});

  it("classLabel covers every classification type the backend can emit", async () => {
    // 後端 normalize+源聲明的實際輸出全集(backend/ipdb/_classification.py 各 _MAP 值 ∪ 源 classification_type);缺鍵 = 界面顯示原始字串(本次 bug)
    const emitted = ["abuse-reports", "blacklist", "brute-force", "c2-server",
      "ddos", "exploit", "infected-system", "malware", "malware-distribution",
      "other", "phishing", "proxy", "scanner", "spam", "tor"];
    const enT = (k: string) => translate("en", k);
    for (const ty of emitted) {
      expect(classLabel(ty, enT), `missing class label for ${ty}`)
        .not.toBe(ty.replace(/-/g, " "));
    }
  });
