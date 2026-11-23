---
id: 2026-10-18-doh-ipv4-dual-flag
date: 2026-10-18
subject: 语义槽 FLAG — 排他率过门线但语义面+许可双 FLAG 待裁
context: >
  dibdot/DoH-IP-blocklists doh-ipv4 排他 98.7%(296/300,seed 20261018,
  对照 20/20)过 25% 门线,但双 FLAG:①语义槽——DoH = 策略封锁的合法 DNS
  基建,非威胁指控;②许可 GPL-3.0。doh-ipv6 1,387 键未测
  (探针 CLI 提取 v4-only 已知限)。
recommendation: 另行报裁,不入本批(硬门数字过线 ≠ 语义面合法)。
human_ruling: 待用户裁决(截至 2026-10-19 未裁)。
reward:
  hard_gates:
    exclusive_rate: "98.7%"
    exclusive_n: "296/300"
  ruling_agreement: pending
  production_delta: null
lineage:
  - "PR #124"
  - docs/research/2026-10-18-blocklist-sweep.md
superseded_by: null
---

# 判例:过门线的硬数字不等于语义合法

高排他率只证「池内没有」,不证「该收」:合法基建段(DNS over HTTPS 解析器)
在威胁轴上是语义错位——这是资产/基建属性陈述,不是威胁指控;叠加 GPL-3.0
签核面 = 升级人裁,discover 轮不得自动入队(自动入队三条件含「无 FLAG」)。
