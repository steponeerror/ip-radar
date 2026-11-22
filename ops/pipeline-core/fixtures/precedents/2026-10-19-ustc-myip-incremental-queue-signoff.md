---
id: 2026-10-19-ustc-myip-incremental-queue-signoff
date: 2026-10-19
subject: 许可签核裁决 — 「有增量价值的都入队」,用户签核覆盖许可 FLAG
context: >
  ustc blackip(中科大校园自保黑名单)排他 47.0%(141/300,纯单 IP 口径;
  混合 CIDR 口径 31.3% 失真判例),无许可声明;myip.ms(自有爬虫 htaccess
  黑名单)排他 46.0%(138/300),© 头无再分发授权 + 已知限流封禁。
  两源均卡许可签核项(tails 轮留档)。
recommendation: >
  tails 轮:PASS 但许可签核留用户(ustc = rtbh 判例同款;myip = FLAG
  模糊商用许可 gate + 下载限流运营风险,建议下轮补查 API 条款原文)。
human_ruling: >
  2026-10-19 用户裁决「有增量价值的都入队」——许可签核由本裁决覆盖,
  两源进波 4(PR #130 已合并:gate 双 POSITIVE-VERIFIED 0 旗标,
  ustc OC 0.7814/fp 0,myip OC 0.5941/fp 1/41/infra Δ+0.0021 不显著)。
reward:
  hard_gates:
    ustc_exclusive_rate: "47.0%"
    ustc_exclusive_n: "141/300"
    myip_exclusive_rate: "46.0%"
    myip_exclusive_n: "138/300"
    ustc_gate_oc: 0.7814
    myip_gate_oc: 0.5941
  ruling_agreement: agreed
  production_delta: null
lineage:
  - docs/research/2026-10-19-tails-discover.md
  - "PR #130"
superseded_by: null
---

# 判例:「无许可声明」本身不判死,增量价值 + 用户签核可入队

许可歧义是升级人裁的 FLAG,不是自动出局:用户签核裁决逐字留痕后即可入队
(docstring 逐字留痕,myip_ms 同款)。配套运营防线:myip 限流页 → 零条目 →
空载荷守卫 + 原子写不动旧证据;stale 留限流余量(4D)。
对照:borestad(ToS 转贴)是「有直采还吃转贴」的另一回事,不适用本判例。
