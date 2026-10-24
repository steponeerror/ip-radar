---
id: 2026-10-18-ziyadnz-aggregator-misjudge
date: 2026-10-18
subject: discover 轮 REJECT 决策 — 聚合器外观候选的系统性误判(翻案)
context: >
  2026-10-10 蜜罐批候选 ziyadnz/threat-intel-ip-feeds(120,510 键,日更)
  按「池内源聚合器全已注册」映射推断 REJECT。同批 rtbh(接受侧)跑了探针,
  拒绝侧没跑——纪律不对称。
recommendation: REJECT(池内聚合器外观,映射推断)。
human_ruling: >
  重审实测 = 44.7% Uniq(134/300,seed 20261018,对照 20/20),带逐 IP 出处列
  (sources/source_count/confidence,谱系可逐行声明)。翻案,波 1 立项
  (PR #125:CsvSource,r=0.55,derived+tier C,波 1 物化 123,107 键)。
  同批 EndlessFractal REJECT 理由同款错误但结论碰巧对(实为安全新闻 RSS 非 IP 清单)。
reward:
  hard_gates:
    exclusive_rate: "44.7%"
    exclusive_n: "134/300"
    probe_seed: 20261018
    control_gate: "20/20"
    keys_judgement_day: 120510
  ruling_agreement: overruled
  production_delta: null
lineage:
  - "PR #124"
  - "PR #125"
  - docs/research/2026-10-18-blocklist-sweep.md
superseded_by: null
---

# 判例:聚合器外观候选 = 映射直觉最强处恰最不可靠

malicious-ip 案(82.7%)之后重审历史档案发现本条同款错误。失败模式集中在
「聚合器外观」候选——映射直觉最强处恰最不可靠;接受侧跑探针、拒绝侧不跑,
是纪律不对称。修复:重叠 REJECT 必须带实测排他数(PR #124 门表硬性化)。
