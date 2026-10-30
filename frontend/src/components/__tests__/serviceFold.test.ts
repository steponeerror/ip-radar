import { describe, it, expect } from "vitest";
import {
  foldServiceStatements, serviceChipKey, SERVICE_CHIP_KEY_PREFIX,
} from "../serviceFold";

// #245 折并抽取:此处钉模块自身契约(首见序/证人悬停串/key 常量派生);
// 两组件的渲染面由 IpDetailPanel/ResultTable 既有测试钉住(位等价)。

describe("foldServiceStatements(service 角色词折并)", () => {
  const svc = (source: string, value: string, native?: string) =>
    ({ source, value, native_type: native });

  it("同角色多源折并为一组,证人逐行进 detail,证人序保留", () => {
    const out = foldServiceStatements([
      svc("dns_public", "dns", "google"),
      svc("infra_services", "dns", "Google Public DNS"),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].value).toBe("dns");
    expect(out[0].detail).toBe("dns_public · google\ninfra_services · Google Public DNS");
  });

  it("异角色各立一组,组序 = Map 首见序(不重排、不挑赢家)", () => {
    const out = foldServiceStatements([
      svc("infra_services", "ntp", "Google NTP"),
      svc("cdn_edges", "cdn", "CloudFront"),
      svc("infra_services", "dns", "Google Public DNS"),
    ]);
    expect(out.map((g) => g.value)).toEqual(["ntp", "cdn", "dns"]);
  });

  it("native_type 缺席回退归一值本身", () => {
    const out = foldServiceStatements([svc("a", "vpn")]);
    expect(out[0].detail).toBe("a · vpn");
  });
});

describe("service chip key 常量", () => {
  it("serviceChipKey 派生自 SERVICE_CHIP_KEY_PREFIX(cdn 压制判据同源)", () => {
    expect(SERVICE_CHIP_KEY_PREFIX).toBe("service-");
    expect(serviceChipKey("cdn")).toBe("service-cdn");
    expect(serviceChipKey("cdn").startsWith(SERVICE_CHIP_KEY_PREFIX)).toBe(true);
  });
});
