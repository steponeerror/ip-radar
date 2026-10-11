import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { IpDetailPanel } from "../IpDetailPanel";
import type { LookupResult } from "../../api";

const mf = <T,>(value: T, confidence = 95) => ({
  value, confidence, algorithm: "cascade" as const,
  sources: [{ source: "geo", value, reliability: 0.9, authoritative: true }],
});

const r: LookupResult = {
  ip: "8.8.8.8",
  country: mf("US"),
  city: mf("Mountain View"),
  asn: mf(15169),
  as_name: mf("Google"),
  ip_range: mf("8.8.8.0/24"),
  is_isp: true,
  classifications: {
    c2_server: {
      type: "c2_server", verdict: "malicious", detected: true, confidence: 92,
      algorithm: "corroboration", corroborated: true, reporter_total: 3,
      verdict_conflict: false, has_archive: false, malware_names: ["win.vidar"],
      details: [{ source: "otx", verdict: "malicious", reliability: 0.9 }], sources: [],
    },
  },
  attributes: {},
};

describe("IpDetailPanel", () => {
  it("renders Z1 identity fields", () => {
    renderWithI18n(<IpDetailPanel r={r} />);
    expect(screen.getByText("Country")).toBeInTheDocument();
    // FieldDetail renders the value both in the header row and in each source row;
    // the mf() fixture reuses the same value for both, so use getAllByText here.
    expect(screen.getAllByText("US")[0]).toBeInTheDocument();
    expect(screen.getByText("ASN")).toBeInTheDocument();
    expect(screen.getByText("Operator")).toBeInTheDocument();
    expect(screen.getByText("Range")).toBeInTheDocument();
  });

  it("renders the 威胁明细 section with the classification block", () => {
    renderWithI18n(<IpDetailPanel r={r} />);
    expect(screen.getByText("Threat details")).toBeInTheDocument();
    expect(screen.getByText("C2")).toBeInTheDocument();
    expect(screen.getByText(/3 reporters/)).toBeInTheDocument();
  });

  it("shows 未命中 when there are no classifications", () => {
    const clean = { ...r, classifications: {} };
    renderWithI18n(<IpDetailPanel r={clean} />);
    expect(screen.getByText("No hits")).toBeInTheDocument();
  });

  it("renders city row between country and ASN with zh suffix", () => {
    const withCity: LookupResult = {
      ...r,
      city: mf("Mountain View"),
      city_zh: "山景城",
    };
    renderWithI18n(<IpDetailPanel r={withCity} />);
    expect(screen.getByText("City")).toBeInTheDocument();
    expect(screen.getAllByText("Mountain View").length).toBeGreaterThan(0);
    expect(screen.getByText("· 山景城")).toBeInTheDocument();
    const rows = screen.getAllByText(/Mountain View/);
    const countryIdx = screen.getByText("Country").compareDocumentPosition(
      screen.getByText("City"),
    ) & Node.DOCUMENT_POSITION_FOLLOWING;
    expect(countryIdx).toBeTruthy();
    expect(rows.length).toBeGreaterThan(0);
  });

  it("groups divergent answers with counts, winner first (single row asserts)", () => {
    const grouped: LookupResult = {
      ...r,
      country: {
        value: "CN", confidence: 75, algorithm: "voting",
        sources: [
          { source: "cn_isp", value: "CN", reliability: 0.85, authoritative: false },
          { source: "geolite", value: "CN", reliability: 0.85, authoritative: false },
          { source: "iptoasn", value: "CN", reliability: 0.8, authoritative: false },
          { source: "other", value: "US", reliability: 0.4, authoritative: false },
        ],
      },
    };
    renderWithI18n(<IpDetailPanel r={grouped} />);
    expect(screen.getByText("CN (3)")).toBeInTheDocument();
    expect(screen.getByText("US (1)")).toBeInTheDocument();
  });

  it("renders logodds alternatives posteriors next to each group", () => {
    const logodds: LookupResult = {
      ...r,
      country: {
        value: "HK", confidence: 46, algorithm: "logodds",
        sources: [
          { source: "s1", value: "HK", reliability: 0.66, authoritative: false },
          { source: "s2", value: "HK", reliability: 0.66, authoritative: false },
          { source: "s3", value: "US", reliability: 0.66, authoritative: false },
          { source: "s4", value: "US", reliability: 0.66, authoritative: false },
        ],
        alternatives: [
          { value: "HK", probability: 45.8 },
          { value: "US", probability: 45.8 },
        ],
      },
    };
    renderWithI18n(<IpDetailPanel r={logodds} />);
    expect(screen.getByText("HK (2)")).toBeInTheDocument();
    expect(screen.getByText("US (2)")).toBeInTheDocument();
    expect(screen.getAllByText("45.8%").length).toBe(2);
  });

  it("does not group when single valid source", () => {
    renderWithI18n(<IpDetailPanel r={r} />);
    expect(screen.queryByText(/\(\d\)/)).toBeNull();
  });
});

describe("as_domain org suffix", () => {
  it("appends the registrar domain after the org value when present", () => {
    const withDomain: LookupResult = {
      ...r,
      attributes: {
        as_domain: [{ source: "ipinfo_lite", value: "google.com" }],
      } as LookupResult["attributes"],
    };
    renderWithI18n(<IpDetailPanel r={withDomain} />);
    expect(screen.getByText("· google.com")).toBeInTheDocument();
  });
  it("renders no suffix element when as_domain is absent", () => {
    renderWithI18n(<IpDetailPanel r={r} />);
    expect(screen.queryByText("google.com")).not.toBeInTheDocument();
  });
});

describe("as_org display dedupe + registration styling (2026-10-11 user report)", () => {
  const asOrg = (value: string): NonNullable<LookupResult["as_org"]> => ({
    value, confidence: 80, algorithm: "authority",
    sources: [{ source: "caida_asorg", value, reliability: 0.8, authoritative: true }],
  });

  it("folds an equal as_org into the Operator row instead of a duplicate block", () => {
    renderWithI18n(<IpDetailPanel r={{ ...r, as_org: asOrg("Google") }} />);
    expect(screen.queryByText("AS organization")).not.toBeInTheDocument();
    // 证据不灭失:caida 证人折进行内 chips,只是不再单开一块
    expect(screen.getByText("caida_asorg")).toBeInTheDocument();
  });

  it("keeps a separate AS organization block when the value differs", () => {
    renderWithI18n(<IpDetailPanel r={{ ...r, as_org: asOrg("Google LLC") }} />);
    expect(screen.getByText("AS organization")).toBeInTheDocument();
  });

  it("renders the registry allocation row inside the shared SECTION styling", () => {
    renderWithI18n(<IpDetailPanel
      r={{ ...r, registration: { registry: "apnic", alloc_date: "2008-05-20", status: "allocated", reg_country: "CN" } }} />);
    expect(screen.getByText(/apnic · 2008-05-20 · allocated · CN/)).toBeInTheDocument();
    // demo 吸收后 SECTION 上岸 master:registration 与其余区块同底(左色条+渐变),
    // 不再是裸 flex 行——2026-10-11 用户报的样式茬终验
    expect(screen.getByText("Registry allocation").closest(".border-l-2")).not.toBeNull();
  });
});
