---
id: 2026-10-19-cloudzy-asset-axis-hosting
date: 2026-10-19
subject: asset 轴槽位决策 — 云商段标签的 is_hosting 票与 verdict 弃权
context: >
  Cloudzy(伊朗 VPS 商,RouterHosting 系)地址段标签,asset 轴候选:
  排他 98.0%(294/300,段级真空白,键不换手不衰减),3,578 键,MIT(随 CPS 仓),
  池内零覆盖(nordvpn/x4bnet_vpn 同构先例)。
recommendation: >
  PASS:is_hosting ∈ ASSET_SLOTS 现有槽,native_types={"is_hosting": "Cloudzy"}
  承 ip2proxy DCH 先例;弃 service="hosting"(service 值域为公共基建角色,
  不发明新词表值);r=0.90,verdict 弃权拼写 ""(R17A-1,信息位不指控)。
human_ruling: >
  波 3 裁决入池(PR #128:gate N/A-ASSET,0 旗标,asset 段标签无威胁语义,
  ②全零位移)。
reward:
  hard_gates:
    exclusive_rate: "98.0%"
    exclusive_n: "294/300"
    keys: 3578
    r: 0.90
  ruling_agreement: agreed
  production_delta: null
lineage:
  - "PR #128"
  - docs/research/2026-10-19-tails-discover.md
superseded_by: null
---

# 判例:asset 轴属性陈述与威胁轴正交

云商/基建段标签走 asset 轴现有槽(is_hosting),不发明新 service 词表值;
verdict 弃权(信息位不指控,ADR「不产 STIX」限指控 Indicator 同源逻辑)。
段级清单键不换手,排他率不随时间衰减——98% 排他在段标签类是真空白,
与快照源的高排他(死键假象)判读方向相反。
