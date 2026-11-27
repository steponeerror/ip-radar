import type { LookupResult } from "../api";
import { foldServiceStatements, serviceChipKey } from "./serviceFold";

// 资产标签唯一构造器(#486 收编:此前 ResultTable.assetBadges 与
// IpDetailPanel.identityChips 各持一份「挑键、压制、文案映射、取首条证词、
// 悬停明细拼法」,悬停明细顺序两边相反)。service 那条支线 2026-10 已并入
// serviceFold.ts,本模块照其做法把布尔/运营商这条支线也收成一份;调用方
// (ResultTable 标签列 / IpDetailPanel 服务身份区)只留「放在页面哪个位置、
// 用什么样式」。
// csvExport.ts 的机器格式不折并不压制,有意不同构,不收编(证据不灭失)。

export interface AssetChip {
  /** 稳定 React key;service chip = serviceChipKey(前缀协议,ResultTable 的 cdn 压制判据派生自此)。 */
  key: string;
  /** chip 正文(i18n 已展开;carrier 拼值为 `文案: 值`,service 为裸角色词)。 */
  label: string;
  /** 悬停明细:证人 `来源 · 原始类型`(两处统一序;service 为折并逐行)。 */
  detail: string;
}

type TFn = (key: string, vars?: Record<string, string | number>) => string;

// 资产键 → 文案键白名单。as_domain 不在表内:它走 as_org 后缀呈现
// (IpDetailPanel),不成 chip。
const ASSET_LABEL_KEYS: Record<string, string> = {
  is_proxy: "asset.is_proxy",
  is_hosting: "asset.is_hosting",
  is_tor: "asset.is_tor",
  is_vpn: "asset.is_vpn",
  carrier: "asset.carrier",
  is_anycast: "asset.is_anycast",
};

// Classification keys that ALSO appear as asset keys — when a classification
// of this type exists, the asset chip is suppressed to avoid duplication
// (值 → classification 键映射;is_tor↔tor、is_proxy↔proxy)。
const ASSET_DUPLICATES_CLASSIFICATION: Record<string, string> = {
  is_tor: "tor",
  is_proxy: "proxy",
};

export function assetChips(r: LookupResult, t: TFn): AssetChip[] {
  const out: AssetChip[] = [];
  const classTypes = new Set(Object.keys(r.classifications));
  for (const [key, stmts] of Object.entries(r.attributes ?? {})) {
    if (key === "service") {
      // 折并(2026-10-11 五裁,规则与出处见 serviceFold.ts):chip 正文只显
      // 角色,证人 source · native 逐行进悬停;key 前缀常量保住 ThreatTags
      // 的 cdn 压制判据(SERVICE_CHIP_KEY_PREFIX && label === "cdn")。
      for (const { value, detail } of foldServiceStatements(stmts)) {
        out.push({ key: serviceChipKey(value), label: value, detail });
      }
      continue;
    }
    const labelKey = ASSET_LABEL_KEYS[key];
    if (!labelKey) continue;
    // 压制:同型 classification 徽章已覆盖(is_tor/is_proxy)则不再重复出 chip
    const covers = ASSET_DUPLICATES_CLASSIFICATION[key];
    if (covers && classTypes.has(covers)) continue;
    const first = stmts[0];
    if (!first) continue;
    let detail = first.source;
    if (first.native_type) detail += ` · ${first.native_type}`;
    const label = key === "carrier" ? `${t(labelKey)}: ${first.value}` : t(labelKey);
    out.push({ key, label, detail });
  }
  return out;
}
