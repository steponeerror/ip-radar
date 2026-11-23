---
id: 2026-10-18-sw-threats-s2-suspiciously-good
date: 2026-10-18
subject: 接入关 S2 强制人裁 — 「好得可疑」旗标(独有命中 92%,OC 0.08)
context: >
  sw_threats(ShadowWhisperer Threats,自采策展,r=0.55,tier A,非 derived,
  排他 58.7%)接入关 POSITIVE-VERIFIED 但旗标 1 强制人裁 S2
  (spec §3.1,PR #125 逐字):独有命中份额=0.9224806201550387,
  OC=0.08<0.7,真值层 rate Δ=NA。truth 层 NO-LAYER(月轮 truth assets 未建,
  S2 判据残缺,读数按现有层解读)。
recommendation: 处置留用户(PR #125 描述逐字在案)。
human_ruling: 待用户裁决(截至 2026-10-19 未裁)。
reward:
  hard_gates:
    unique_hit_share: 0.9224806201550387
    oc: 0.08
    exclusive_rate: "58.7%"
  ruling_agreement: pending
  production_delta: null
lineage:
  - "PR #125"
  - docs/research/2026-10-18-blocklist-sweep.md
superseded_by: null
---

# 判例:「好得可疑」= 独有命中畸高 + OC 低 + truth 层缺证

独有命中份额 92% 与 OC 0.08 并存 = 池内从未指认过它的键,但探针集也证实不了
它们是好键——真值层建成前不自动销旗,月度 eval 盯独有命中质量
(误报冒头 → 单文件回滚)。与 CPS 快照悖论同向:高独有≠高价值,
需分真空白 / 死键 / 探针盲区三种成因。
