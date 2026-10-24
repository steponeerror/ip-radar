# 判例库 schema(docs/ops/precedents/)

经验四元组判例库真相源。机制来源:JitRL 移植(检索注入,无优势值数学;grill 九裁决 2026-10-19)。检索只用 rg 词法匹配,禁止 embedding;**无界不删**——修正 = 新条目 + 旧条目 `superseded_by` 指链,就地改历史一律禁止。

## 文件与命名

- 文件名:`YYYY-MM-DD-<slug>.md`(日期 = 判例发生日,非写入库日)。
- 本文件(`_schema.md`)是 schema 说明,不是判例,测试排除之。
- frontmatter 用 `---` 围栏 YAML,正文是给人和 rg 看的叙事(判例教训写在正文,检索靠全文词法命中)。

## frontmatter 字段(九字段全部必填)

| 字段 | 类型 | 语义 |
|---|---|---|
| `id` | str | 唯一标识,与文件名 stem 一致 |
| `date` | date | 判例发生日 |
| `subject` | str | 一行主题(决策面 + 对象) |
| `context` | str | 情境:决策时看到的事实面,含实测数字 |
| `recommendation` | str | 建议:agent/会话当时给出的建议 |
| `human_ruling` | str | 人裁:用户裁决逐字或忠实转述;未裁 = 「待用户裁决(截至 X 未裁)」 |
| `reward` | mapping | 回报,复合三列,见下;**永不合成标量**(学习信号灭失 = 红线) |
| `lineage` | list[str] | 出处:PR 号 / dossier 路径;数字必须有可回查出处,抄不到出处的在正文标「出处待核」 |
| `superseded_by` | str\|null | 被哪条判例取代(该目录下文件名);未被取代 = null |

## reward 子 schema(恰含三键)

```yaml
reward:
  hard_gates:            # 映射:硬门实测数字(排他率/OC/键数/冻结天数…),键名自释,逐字抄在案值
    exclusive_rate: "82.7%"
    exclusive_n: "248/300"
  ruling_agreement: overruled   # agreed | overruled | amended | pending
  production_delta: null       # 一律 null;30 天生产增量写回是独立后续批,未结案不补
```

- `hard_gates`:必须是映射且非空——硬门数字不带 = 数字编造风险(Review Focus 4)。
- `ruling_agreement`:人裁与建议的关系四态。
- `production_delta`:判例入库时恒 null;写回属后续批次,永不自行估算或合成。

## 完整示例(真实种子副本:`2026-10-18-malicious-ip-mapping-vs-key-overlap.md`)

```yaml
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
  推翻 REJECT,波 1 立项(PR #125:r=0.50 地板,derived+tier C)。
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
```

校验测试:`backend/tests/test_precedent_schema.py`(pytest,断言字段齐全 / reward 三键映射 / production_delta 恒 null / superseded_by 指向存在文件)。
