---
id: 2026-10-18-borestad-tos-default-reject
date: 2026-10-18
subject: 许可门 — AbuseIPDB 转贴默认不收(ToS + NO-LIC 双险)
context: >
  borestad/blocklist-abuseipdb · s100-30d = AbuseIPDB s100 数据转贴,
  128,084 键,排他 54.7%,NO-LIC(无许可文件),AbuseIPDB ToS 约束存疑。
  池内已有 abuseipdb 直采(token 配置面)。
recommendation: >
  默认不收——池已有 abuseipdb 直采;吃转贴 = 超自有权重的数据面 +
  ToS/NO-LIC 双险。
human_ruling: >
  用户简报将 borestad 列入 tails 轮预出局名单,未再翻案(2026-10-19)。
reward:
  hard_gates:
    keys: 128084
    exclusive_rate: "54.7%"
  ruling_agreement: agreed
  production_delta: null
lineage:
  - docs/research/2026-10-18-blocklist-sweep.md
  - docs/research/2026-10-19-tails-discover.md
superseded_by: null
---

# 判例:有直采的出版方不再吃转贴

转贴源的双重问题:①数据面——出版方自有权重的数据经二手进来,池内已有
一手时纯属回声;②许可面——转贴者无权再分发(ToS/NO-LIC),与一手直采的
授权基础不同。排他率过门线也救不了这类候选。
