---
id: 2026-10-18-malicious-ip-mapping-vs-key-overlap
date: 2026-10-18
subject: discover 轮 REJECT 决策 — 上游映射推断 ≠ 键级重叠
context: >
  候选 romainmarcoux/malicious-ip(1,003,608 IP,小时更,MIT)按 README 上游映射
  推断「它聚合的出版方我们都有 → ~100% 重叠」判 REJECT。
recommendation: REJECT(依据 = 上游映射推断重叠,未做键级实测)。
human_ruling: >
  用户质疑后实测键级排他率:联合体排他 82.7%(248/300,seed 20261018,
  binarydefense 对照 20/20);头部 40k 片排他仅 20.7%(多源印证段池内已覆盖),
  尾部单源片 89.7%(增量真身);排他样本云/CDN/DNS warninglist 命中 0%。
  推翻 REJECT,波 1 立项(PR #125:Source 子类 5 片联合体,r=0.50 地板,
  derived+tier C,波 1 物化 1,021,274 键)。
reward:
  hard_gates:
    union_exclusive_rate: "82.7%"
    union_exclusive_n: "248/300"
    probe_seed: 20261018
    control_gate: "20/20"
    keys_judgement_day: 1003608
    head_40k_exclusive_rate: "20.7%"
    tail_single_source_exclusive_rate: "89.7%"
  ruling_agreement: overruled
  production_delta: null
lineage:
  - "PR #124"
  - "PR #125"
  - docs/research/2026-10-18-blocklist-sweep.md
superseded_by: null
---

# 判例:README 上游映射 ≠ 键级重叠

「它聚合的出版方我们都有」推不出「~100% 重叠 REJECT」,必须先跑键级排他率探针
(`python -m ipdb._eval --exclusive`)再上门判。覆盖梯度反向于印证度:多源段 = 回声段,
单源段 = 增量段。

执法:PR #124 将门表硬性化——重叠类 REJECT 必附实测排他数,上游映射推断不得替代,
无实测数最多 FLAG。
