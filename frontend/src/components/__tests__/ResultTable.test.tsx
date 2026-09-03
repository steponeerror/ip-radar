import { describe, it, expect } from "vitest";
import { screen, fireEvent, within } from "@testing-library/react";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { ResultTable } from "../ResultTable";
import type { ClassificationAssessment, LookupResult } from "../../api";

const mf = <T,>(value: T, confidence = 95) => ({
  value, confidence, algorithm: "cascade" as const,
  sources: [{ source: "geo", value, reliability: 0.9, authoritative: true }],
});

const reserved: LookupResult = {
  ip: "10.0.0.1",
  country: mf("N/A", 0), city: mf("N/A", 0), asn: mf(0, 0), as_name: mf("N/A", 0),
  ip_range: mf("N/A", 0), is_isp: false, classifications: {},
  is_reserved: true,
};

describe("ResultTable reserved rows", () => {
  it("renders 保留地址 verdict for a reserved IP", () => {
    renderWithI18n(<ResultTable results={[reserved]} />);
    expect(screen.getAllByText("Reserved").length).toBeGreaterThanOrEqual(1);
  });
});

const lowConf: LookupResult = {
  ip: "203.0.113.5", country: mf("US", 50), city: mf("Mountain View", 50), asn: mf(64500, 50),
  as_name: mf("Example", 50), ip_range: mf("203.0.113.0/24", 50),
  is_isp: false, classifications: {},
};

describe("Expand disagreements toggle", () => {
  it("expands on first click, collapses on second", async () => {
    renderWithI18n(<ResultTable results={[lowConf]} />);
    // collapsed initially – detail panel not shown
    expect(screen.queryByText("Threat details")).not.toBeInTheDocument();

    const expand = screen.getByRole("button", { name: /expand disagreements/i });
    fireEvent.click(expand);
    expect(await screen.findByText("Threat details")).toBeInTheDocument();

    // button flipped to Collapse; clicking it collapses
    const collapse = screen.getByRole("button", { name: /collapse disagreements/i });
    fireEvent.click(collapse);
    expect(screen.getByRole("button", { name: /expand disagreements/i })).toBeInTheDocument();
  });
});

describe("ResultTable city column", () => {
  it("shows city value directly in the table without expanding", () => {
    renderWithI18n(<ResultTable results={[lowConf]} />);
    expect(screen.getByRole("columnheader", { name: "City" })).toBeInTheDocument();
    expect(screen.getByText("Mountain View")).toBeInTheDocument();
    // still collapsed — city visible without the detail panel
    expect(screen.queryByText("Threat details")).not.toBeInTheDocument();
  });

  it("renders '-' for a row without city data", () => {
    const noCity: LookupResult = {
      ip: "198.51.100.7", country: mf("DE"), city: mf("N/A", 0), asn: mf(3320, 90),
      as_name: mf("DTAG", 90), ip_range: mf("198.51.100.0/24", 90),
      is_isp: false, classifications: {},
    };
    renderWithI18n(<ResultTable results={[noCity]} />);
    const row = screen.getByText("198.51.100.7").closest("tr")!;
    expect(within(row).getAllByText("-").length).toBeGreaterThanOrEqual(1);
    expect(within(row).queryByText("N/A")).not.toBeInTheDocument();
  });
});

describe("ResultTable service badge", () => {
  it("renders one '<role>·<provider>' chip per service statement", () => {
    const dns: LookupResult = {
      ip: "8.8.8.8",
      country: mf("US"), city: mf("Mountain View"), asn: mf(15169), as_name: mf("Google"),
      ip_range: mf("8.8.8.0/24"), is_isp: true, classifications: {},
      attributes: { service: [
        { source: "infra_services", value: "dns", native_type: "Google Public DNS" },
        { source: "gcp_ranges", value: "cloud", native_type: "Google" },
      ] },
    };
    renderWithI18n(<ResultTable results={[dns]} />);
    // every statement renders — the old first-only chip hid all but one
    expect(screen.getByText("dns·Google Public DNS")).toBeInTheDocument();
    expect(screen.getByText("cloud·Google")).toBeInTheDocument();
  });
});

// --- spec §3 richness display ---

const baseResult: LookupResult = {
  ip: "203.0.113.10", country: mf("US", 90), city: mf("Anytown", 90), asn: mf(64500, 90),
  as_name: mf("Example Net", 90), ip_range: mf("203.0.113.0/24", 90),
  is_isp: false, classifications: {},
};

const caProxy: ClassificationAssessment = {
  type: "proxy", verdict: "informational", detected: true, confidence: 60,
  algorithm: "voting", corroborated: false, reporter_total: 1,
  verdict_conflict: false, malware_names: [], details: [], sources: [],
};

describe("ResultTable richness display", () => {
  it("renders CDN edge badge when threat.is_cdn", () => {
    renderWithI18n(<ResultTable results={[{ ...baseResult, ip: "104.16.132.229",
      threat: { verdict: "benign", confidence: 0, types: [], is_cdn: true } }]} />);
    expect(screen.getByText("CDN edge")).toBeInTheDocument();
  });

  it("renders invalid badge when row error", () => {
    renderWithI18n(<ResultTable results={[{ ...baseResult, ip: "not-an-ip", error: "invalid IP format" }]} />);
    expect(screen.getByText("Invalid")).toBeInTheDocument();
  });

  it("shows VPN badge alongside proxy classification", () => {
    const r = { ...baseResult, ip: "216.24.217.1",
      classifications: { proxy: { ...caProxy, detected: true, confidence: 60 } },
      attributes: { is_vpn: [{ source: "x4bnet_vpn", value: true, native_type: "VPN" }] } };
    renderWithI18n(<ResultTable results={[r]} />);
    const row = screen.getByText("216.24.217.1").closest("tr")!;
    expect(within(row).getByText("VPN")).toBeInTheDocument();
    expect(within(row).getByText("Proxy")).toBeInTheDocument(); // classification tag still shown
  });

  it("operator column shows as_domain subtitle and carrier badge; threat column has no carrier badge", () => {
    const r = { ...baseResult, ip: "39.144.0.1",
      attributes: { carrier: [{ source: "cn_isp", value: "中国移动" }],
                   as_domain: [{ source: "ipinfo_lite", value: "chinamobile.com" }] } };
    renderWithI18n(<ResultTable results={[r]} />);
    expect(screen.getByRole("columnheader", { name: "Operator" })).toBeInTheDocument();
    const tds = screen.getByText("39.144.0.1").closest("tr")!.querySelectorAll("td");
    expect(within(tds[4]).getByText(/Carrier: 中国移动/)).toBeInTheDocument();
    expect(within(tds[4]).getByText("chinamobile.com")).toBeInTheDocument();
    expect(within(tds[6]).queryByText(/中国移动/)).not.toBeInTheDocument();
  });
});

// --- C1: score-semantics legend + per-field hover (Task 6) ---

describe("score-semantics legend", () => {
  it("renders the score-semantics legend", () => {
    renderWithI18n(<ResultTable results={[baseResult]} />);
    expect(screen.getByText(/posterior probability/i)).toBeInTheDocument();
    expect(screen.getByText(/consensus/i)).toBeInTheDocument();
  });

  it("hover titles carry the algorithm semantics", () => {
    renderWithI18n(<ResultTable results={[baseResult]} />);
    const cell = screen.getAllByTitle(/posterior probability/i)[0];
    expect(cell).toBeInTheDocument();
  });

  it("expanded field rows carry the per-algorithm hover title", () => {
    const r: LookupResult = {
      ...baseResult,
      asn: {
        value: 64500, confidence: 90, algorithm: "logodds",
        sources: [{ source: "iptoasn", value: 64500, reliability: 0.9, authoritative: false }],
      },
    };
    renderWithI18n(<ResultTable results={[r]} />);
    fireEvent.click(screen.getByText("203.0.113.10"));
    // 1 = legend entry; >1 means the expanded field's algorithm glyph got one too
    expect(screen.getAllByTitle(/posterior probability/i).length).toBeGreaterThan(1);
  });
});
