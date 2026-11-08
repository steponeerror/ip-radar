# PATTERNS — ipradar 域提案者宪法(红线与判例)

不可补偿的硬红线:触线即作废,分数再高也不接受(与三护栏同罚则)。

## 开放面(只许改这里)

- `ops/agent/`(发现管线 v1:提示词、工具、fixtures;v1 已记弃用意向,但被 v2
  复用的面——models.mjs re-export、prompts、fixtures——仍是有效演化面)
- `ops/agent-v2/`(durable 底座与基准全套:entry/registry/tasks/bench)

## 免碰面(一概不碰)

- `backend/`(存储与源注册表;答案真源,动它=污染考题)
- `dev/`(沙箱与 RRSI 克隆所在;动它=污染基准世界)
- `docs/`(嵌套私有仓;运营面)
- `.worktrees/`、`scripts/`、`frontend/`、根配置(Dockerfile/compose 等)
- `ops/agent-v2/bench/rrsi-domain/data/split.jsonl`(冻结劈分件,重劈须人裁)
- `NEEDS.md`(考题宇宙输入面:bench SCAN 真面读它;对 incumbent 冻结——候选增改一行
  即红,改它=往宇宙注入考题提示)

## 零漂移红线(真实轮路径行为字节不变)

基准演化**不得改变真实运营轮的行为**:生产 discover/health 轮的路径
(run-discover/run-health 及其 tasks 全相位)输出必须与演化前字节级一致;
golden(`ops/agent/golden/run-golden.mjs`)与 v2 全套(`npm test`)钉住这一点。
改基准面(bench/ 下)必须在真实轮路径零 diff 的前提下做——评测器、答案、劈分、
leak 闸自身(score.mjs/leak-check.mjs/split/aliases/exam-rules)视为**冻结基础设施**,
提案不得改;发现评测器缺陷,报告,不修。

## 泄漏红线(盲测纪律)

- 考题源的名字(任何归一化形式)、下载域名,禁入提示词、代码、注释、检索词表。
  考题即答案;把答案写进检索面=作弊,leak gate(`bench/leak-check.mjs`)与
  审查者(critic_patterns 考题针)双面拦截。
- 禁止对具体源名/域名打补丁(benchmark 专属拟合):编辑必须表述为可泛化机制
  (检索策略、聚合、归一、去重),不得列举考题成员。

## 豁免判例(行级)

需要引用禁词本体(如匹配器判据、判例说明)时,行尾加「禁词引用:原因」——
pre-commit 禁词钩子与 leak gate 同款放行(#308 判例);无标记行不豁免。

## 沙箱纪律

- 基准轮一切落件在沙箱 opsRoot(`dev/bench-rediscover/<roundId>/`);不得写真实
  docs/ops 台账、不得读真实运营面数据当考题提示。
- 模型面:候选不得自带 API key(走 env,零入仓);faux 冒烟轮零网络。

## 编辑律

- 每编辑一假设:预期救回哪些落空源、为什么;不可归因的大扫除式重构=拒绝。
- 被拒机制是负证据;已被接受的机制带着它的增益, refinement 优先于重画。
- 单候选 ≤b_t 编辑(预算退火);修审查意见时只修意见所及,不夹带。
