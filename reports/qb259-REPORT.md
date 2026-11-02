# #259 交付报告——术语改名延后批(ops/agent+CODEMAP 中文面)

> 收口注:实施工于合并树全量测试通过后 30min 超时(判例:超时≠未完成);本报告由收口人(supervisor)代笔,scope 内剩两处 STANDARD.md 残留由收口人补改(见「收口补刀」),其余全部改动均为实施工提交。评审请以树内最终态为准。

## 票面 scope 与完成度

| 面 | 处理 | commit |
|---|---|---|
| ops/agent STANDARD.md 典章面 | 旧词→新词(改名对照真源)+ 机检挂点同步 | 2af7b060 |
| ops/agent DESIGN.md | 旧词→新词 | 0f8bda5a |
| agent-v2/ENVELOPE.md | 轮次信封契约→轮次结果单契约 | dce6221c |
| agent-v2/SHADOW-RUNBOOK.md | 字节级一致(原名位等价,已退役)、信封→结果单 | 806429d1 |
| agent-v2 代码注释位 | 等价→字节级一致、金轨迹→保活任务、兑底→兜底 | 94c5918b |
| prompts 六件 + selftest.sh 钉子 | 旧词→新词 + 提示词钉子同步 | c825846d |
| deploy/ops-cron.md 等 7 处 | 失败信封→失败结果单等 | 4ae71d48 |
| .github/workflows/ci.yml:37 | 金轨迹集注释→标准答案集回归探针 | 73c4c133 |
| docs/CODEMAP.md(主检出绝对路径) | 中文面旧词清零(收口人复核 rg 零命中) | 同批(主检出文件) |

## 验证(收口人代跑;覆盖面以实测为准)

- 合并树(queue-batch 已并入)四套 selftest:**pipeline 105/0、contract 19/0、standard 15/0、t4 63/0**。
- 旧词扫描(诚实口径):本批扫描面 = ops/agent 典章 md 面(STANDARD/DESIGN/ENVELOPE/SHADOW-RUNBOOK/prompts/deploy/ci.yml)+selftest.sh 标签,终扫归零;docs/CODEMAP.md 经评审补改 5 处后归零(见下)。收口人首扫词表偏窄(漏语料/背景质量/裸θ),被评审员宽词表证伪后已补——教训:扫旧词必须以 GLOSSARY「改名对照」全表为准。
- 主检出 docs/CODEMAP.md 旧词(嵌套 docs 仓,单独提交):评审抓出 5 处漏网(:20/:133 裸θ、:47 背景质量、:132/:137 语料、:143 「锚:」过期引用),已补改并复扫。

## 真实延后面(未被本批收编,记录在案供后续票接手)

- agent v1 代码注释 ~20 处旧词(agent.mjs/artifacts.mjs/promote-detect.mjs/gates.mjs 等)。
- agent-v2「信封」族 ~65 处/19 文件:纯注释可改,输出字符串面(probes.mjs:52、discovery-tools.mjs:88/99)因与 v1 字节级一致冻结不能改——ENVELOPE.md 已加术语注声明切流退役时一并清。
- selftest.sh 钉子 grep 模式外的标签面已随本批复改;ops/agent/fixtures/pipeline/README.md:50「DEEP 金轨迹」仍存(拒用闸扩面前置清理项)。
- fixtures/precedents/2026-10-24 历史判例中的「信封纪律」按历史引文保留。
- deploy/ops-shadow-cron.sh:19/:30/:72 注释仍存旧称。
- 拒用闸 LIVING_DOCS 尚未纳入 ops/*.md 扫描面(test_glossary_anchors.py:162 注释已同步本批状态);扩面前先清 fixtures/pipeline/README.md:50。

> #269 评审环(B/C 角)延后账补录(2026-11-01,五项):

- selftest-*.mjs 标签/测名面旧词(selftest-t4.mjs ~26 行、selftest-contract.mjs ~10 行、selftest-pipeline.mjs 各测名/断言文案;部分与冻结输出串耦合,清理须连重跑对拍)。
- 后端基线既有注释 backend/ipdb/_alerts.py:75/:191/:256/:259「位等价」×4(基线预存,非本批引入)。
- scripts/fusion_replay_gate.py「语料」~20 处(回放数据义)、scripts/monthly_eval.sh:16/:223 模块自称「真值语料 v2」。
- v1 旧词计数修正:上录「agent v1 代码注释 ~20 处」不止——含 selftest-pipeline.mjs 标签 ~13、golden/cases.json ~20、steps/gates/anchors.mjs,合计 50+。
- fixtures/pipeline/README.md 除 :50 外再补两处已知答案义漂变形::14「罐装锚巡检」、:22「锚集镜像/锚集真源」。

## 收口补刀(STANDARD.md :103/:106)

- :103 主张行活面用词:轮内=步前检查实报累计 → **预扣结算实报累计**(GLOSSARY:65 旧词「轮内预算步前检查」并入 P7「预扣结算」)。
- :106 判例链引对撞表历史句:轮内已核=步前检查实报 → **预扣结算实报(旧称步前检查,已并入 P7)**——保留旧称注记,免于伪造历史引文。

## 票外缓办(记录不动)

- agent-v2 对拍测试墙钟月键竞态:#267 评审环已裁票外,缝已备(#268 已注),将来批可低收。
- ops/agent 内英文面与代码标识符:票面本就中文面限定,英文面仍留待后续批。
