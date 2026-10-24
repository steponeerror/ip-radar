---
id: 2026-10-19-cps-snapshot-paradox
date: 2026-10-19
subject: 排他率判读 — 快照源高排他与新鲜度反相关(死键证据)
context: >
  CPS 镜像类子清单批量探针(N=300,seed 20261018):排他率与新鲜度反相关。
  活镜像 binarydefense 0.7%(2/300)、tor-exit 0.3%(1/300)≈0;
  陈旧快照 alienvault 97.7%(293/300)、abuse-ch-ipblocklist 95.3%(286/300)、
  log4j 88.7%(266/300)超高。
recommendation: >
  对快照源,高排他率 ≠ 增益证据,反而是死键证据(键被活源换手淘死后,
  池内无人再指认)。排他率只在两类对象上是真增益:段/标签清单(cloudzy 98.0%,
  键不换手)与自有活跃采集(cps-collected-iocs 70.3%)。
human_ruling: >
  用户波次裁决采用该判读器:log4j 88.7% 读作死键嫌疑不入池,除非两日 diff 证
  CPS 仍在追加;threatview.io 直连判死同判读器复刻。
reward:
  hard_gates:
    live_mirror_binarydefense: "0.7% (2/300)"
    live_mirror_tor_exit: "0.3% (1/300)"
    stale_snapshot_alienvault: "97.7% (293/300)"
    stale_snapshot_abusech: "95.3% (286/300)"
    stale_snapshot_log4j: "88.7% (266/300)"
    segment_label_cloudzy: "98.0% (294/300)"
    own_collection_cps_iocs: "70.3% (211/300)"
  ruling_agreement: agreed
  production_delta: null
lineage:
  - docs/research/2026-10-19-tails-discover.md
  - "PR #128"
  - "PR #130"
superseded_by: null
---

# 判例:CPS 快照悖论 — 排他率判读器

「威胁轴条款:新键≠真阳性」从纪律变成可复用判读器:快照源(镜像/陈年波遗产)
的高排他 = 死键证据。真增益仅两类:段/标签清单(键不换手,排他不随时间衰减)
与自有活跃采集。应用实例:log4j(88.7% 不收)、threatview(57% 镜像判死)、
alienvault(97.7% = 上游 reputation.data 已废弃的死键快照)。
