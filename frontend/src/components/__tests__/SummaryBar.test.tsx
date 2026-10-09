import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { SummaryBar } from "../ResultTable";
import type { LookupResult } from "../../api";

const mf = <T,>(value: T, confidence = 95) => ({
  value, confidence, algorithm: "cascade" as const,
  sources: [{ source: "geo", value, reliability: 0.9, authoritative: true }],
});

const reserved: LookupResult = {
  ip: "10.0.0.1", country: mf("N/A", 0), city: mf("N/A", 0), asn: mf(0, 0),
  as_name: mf("N/A", 0), ip_range: mf("N/A", 0), is_isp: false,
  classifications: {}, is_reserved: true,
};

// U6:allHigh 绿点=geo/ASN 字段置信面(中性语义,禁「全部安全」暗示);
// title 说明统计面。city 不计入 lowestConfidence,置信 0 不影响分支。
const clean: LookupResult = {
  ip: "1.2.3.4", country: mf("US", 95), city: mf("N/A", 0), asn: mf(15169, 95),
  as_name: mf("Google LLC", 95), ip_range: mf("1.2.3.0/24", 95), is_isp: false,
  classifications: {}, is_reserved: false,
};

describe("SummaryBar all-high green dot (U6)", () => {
  it("en: chip carries neutral geo/ASN wording and a title explaining the stat face", () => {
    renderWithI18n(<SummaryBar results={[clean]} />);
    expect(screen.getByText("All 1 geo/ASN high conf")).toBeInTheDocument();
    const chip = screen.getByTitle(/high-confidence for all 1 results\. Describes data confidence only/i);
    expect(chip.textContent).toBe("All 1 geo/ASN high conf");
  });

  it("zh:文案与 title 双语中性,不断言「全部安全」", () => {
    renderWithI18n(<SummaryBar results={[clean, clean]} />, { locale: "zh-CN" });
    expect(screen.getByText("全部 2 条 geo/ASN 高置信")).toBeInTheDocument();
    expect(screen.getByTitle(/不代表威胁判定结论/)).toBeInTheDocument();
  });
});

describe("SummaryBar reserved bucket", () => {
  it("counts reserved IPs as 保留地址, not as 低置信", () => {
    renderWithI18n(<SummaryBar results={[reserved]} />);
    expect(screen.getByText("Reserved")).toBeInTheDocument();
    expect(screen.queryByText(/low conf/i)).not.toBeInTheDocument();
  });
});
