---
id: 2026-10-19-threatview-sunset-dead-feed
date: 2026-10-19
subject: 源候选判死 — sunset 硬门(URL Last-Modified 冻结)
context: >
  tails-discover 轮将 threatview.io 直连列为下批 discover 首选(C2 轴第二证人):
  其 CPS 镜像 cobaltstrike_ips 57.0% 排他(171/300),池内 threatfox 仅盖 1/3,
  快照多一手陈化(2,087 行仅 804 唯一)。
recommendation: 下批 discover 单独立项 threatview.io 直连(tails 轮裁决)。
human_ruling: >
  直连核查判死:两条已知 URL Last-Modified 均 2026-02-08(8 个月冻结),
  sunset 硬门;CPS 镜像 57% 排他 = 死键假象(快照悖论直连复刻)。
  复活触发器 = Last-Modified 前进或两日 diff 显追加。
reward:
  hard_gates:
    last_modified: "2026-02-08"
    frozen_months: 8
    mirror_exclusive_rate: "57.0%"
    mirror_exclusive_n: "171/300"
  ruling_agreement: overruled
  production_delta: null
lineage:
  - docs/research/2026-10-19-tails-discover.md
  - "PR #130"
superseded_by: null
---

# 判例:高排他镜像先查上游活性,冻结 = sunset 判死

镜像排他率再高,上游 URL 冻结即判死——高排他是死键假象而非增益证据
(与 CPS 快照悖论判读器同构)。判死带复活触发器,不是永久封杀;
自动 REJECT 谓词「sunset」的阈值 = 全部已知 URL 冻结 ≥180 天,任一 URL 活跃即不命中。
