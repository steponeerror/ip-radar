import { describe, it, expect } from "vitest";
import { assetChips, type AssetChip } from "../assetChips";
import type { LookupResult } from "../../api";

// #486 收编:资产 chips(挑键/压制/文案/取首条证词/悬停明细)唯一构造器。
// ResultTable(标签列)与 IpDetailPanel(服务身份区)都消费它 —— 组件两侧
// 的行为测试另有镜像断言(两边明细顺序相同);本文件钉构造器本体。

// 文案映射用真 en 词表值,断言读得懂;词表键集钉在 i18n parity 测试。
const LABELS: Record<string, string> = {
  "asset.is_tor": "Tor",
  "asset.is_proxy": "Proxy",
  "asset.is_hosting": "Hosting",
  "asset.is_vpn": "VPN",
  "asset.is_anycast": "Anycast",
  "asset.carrier": "Carrier",
};
const t = (k: string) => LABELS[k] ?? k;

const stmt = (source: string, value: boolean | string, native_type?: string) =>
  ({ source, value, ...(native_type !== undefined ? { native_type } : {}) });

// assetChips 只读 classifications 的键集与 attributes,其余字段不触 —— 最小形状
// (classification 值用 unknown 占位:本模块只取键集)。
const chipsOf = (
  attributes?: LookupResult["attributes"],
  classifications: Record<string, unknown> = {},
): AssetChip[] => assetChips({ classifications, attributes } as unknown as LookupResult, t);

const keys = (chips: AssetChip[]) => chips.map((c) => c.key);

describe("assetChips(#486 收编:两处各一份的资产标签)", () => {
  it("压制:is_tor/is_proxy 在同型 classification 已覆盖时不出 chip", () => {
    const attr = { is_tor: [stmt("peerdb", true, "tor")], is_proxy: [stmt("x4bnet", true, "proxy")] };
    expect(keys(chipsOf(attr, { tor: {}, proxy: {} }))).toEqual([]);
    // 各自独立:只压同型,另一键不受牵连
    expect(keys(chipsOf(attr, { tor: {} }))).toEqual(["is_proxy"]);
  });

  it("不压制:无同型 classification 时 tor/proxy chip 照常出", () => {
    const got = chipsOf({ is_tor: [stmt("peerdb", true, "tor")] });
    expect(keys(got)).toEqual(["is_tor"]);
    expect(got[0].label).toBe("Tor");
    expect(got[0].detail).toBe("peerdb · tor");
  });

  it("文案映射:布尔/任播键逐键对到词表值", () => {
    const attr = {
      is_hosting: [stmt("ipinfo_hosting", true, "hosting")],
      is_vpn: [stmt("x4bnet_vpn", true, "VPN")],
      is_anycast: [stmt("bgp_tools", true, "anycast")],
      is_proxy: [stmt("x4bnet", true, "proxy")],
      is_tor: [stmt("peerdb", true, "tor")],
    };
    const got = chipsOf(attr);
    expect(got.map((c) => c.label)).toEqual(["Hosting", "VPN", "Anycast", "Proxy", "Tor"]);
  });

  it("carrier:正文拼值 `文案: 值`(结果表既有拼写),明细 = 证人", () => {
    const got = chipsOf({ carrier: [stmt("cn_isp", "中国移动", "isp")] });
    expect(got[0].label).toBe("Carrier: 中国移动");
    expect(got[0].detail).toBe("cn_isp · isp");
  });

  it("悬停明细统一 `来源 · 原始类型` 顺序;缺 native_type 只出来源", () => {
    const got = chipsOf({
      is_hosting: [stmt("ipinfo_hosting", true, "hosting")],
      is_anycast: [stmt("bgp_tools", true)],
    });
    expect(got[0].detail).toBe("ipinfo_hosting · hosting");
    expect(got[1].detail).toBe("bgp_tools");
  });

  it("取首条证词:多证人只取 stmts[0](其余证据在后端载荷,不灭失)", () => {
    const got = chipsOf({
      is_vpn: [stmt("first_src", true, "VPN"), stmt("second_src", true, "VPN")],
    });
    expect(got[0].detail).toBe("first_src · VPN");
  });

  it("service 支线:折并走 serviceFold,key 前缀协议保住 cdn 压制判据", () => {
    const got = chipsOf({
      service: [stmt("dns_public", "dns", "google"), stmt("infra_services", "dns", "Google Public DNS")],
    });
    expect(keys(got)).toEqual(["service-dns"]);
    expect(got[0].label).toBe("dns");
    expect(got[0].detail).toContain("dns_public · google");
    expect(got[0].detail).toContain("infra_services · Google Public DNS");
  });

  it("白名单外键不成 chip(as_domain 走 as_org 后缀;未知键不猜)", () => {
    expect(chipsOf({
      as_domain: [stmt("ipinfo_lite", "example.com")],
      as_org: [stmt("caida", "Example Org")],
      future_key: [stmt("new_src", true, "new")],
    })).toEqual([]);
  });

  it("空 statements / 空 attributes → 不出 chip", () => {
    expect(chipsOf({ is_tor: [] })).toEqual([]);
    expect(chipsOf(undefined)).toEqual([]);
  });
});
