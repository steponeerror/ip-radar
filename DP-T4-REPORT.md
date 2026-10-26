# DP-T4 交卷报告(#210 典章+北星+CHANGELOG)

工位:.worktrees/dp-t4,分支 feature/dp-t4,基 4b1c8720(feature/discover-pipeline-v0 = T1 bfe9bc62 + T3 4b1c8720 已合流;T2 #208 未合流——citation.mjs 不在本树,挂点决策见 §自决③)。未 push、未动集成分支、未关票。

## 五件交付

### ① action 词统一 PROPOSE(0e34a57f)

- `ops/agent/pipeline/steps.mjs` ENQUEUE 步:字面量 `action: "ENQUEUE"` → `CANDIDATE_ACTION`(自 discover-candidate.mjs 导入,单源一词一拼,与 T3 appendCandidateCard 同词)。T1 面 MEASURE 恒写 `control_executable:null` → 全 skip,appendQueueRowLocked 是死路——仍先对齐,防 T2/T3 活化后拼写分叉。
- python 面(**零改**,T3 merger 已核实读面兼容):`_ops_store.py` QUEUE_ACTIONS=("ENQUEUE","REJECT") 是**人裁动作闭集**(python 写面),PROPOSE=提案非动作,分立不合并。
- `selftest-pipeline.mjs` ENQUEUE 写路钉面同步断言 `\| PROPOSE \| rdns_hf_parquet \|`。
- 红证:sed 回改 ENQUEUE → PASS=95 FAIL=1(候选行断言真红);还原 → 96/0。

### ② STANDARD.md D-7 + GLOSSARY(7f55c7f8)

- 新条文 **D-7 发现与运营同律**(判例链出处 ADR 0010):第六轮型同宿主/同台账/同工件树;六步 SCAN→SHORTLIST→MEASURE→ENQUEUE→RETRO→CLOSE;四门全机检(G_SCAN 形状/G_SHORTLIST span 级逐字回引/G_MEASURE 数字复算/G_ENQUEUE 对账);**模型零裁决**(入队判据=代码常量不在 prompt);**ENQUEUE 只写不动作**(#139 双边 flock,开票/接源全人裁);**PROPOSE 词**(与 ENQUEUE/REJECT 人裁闭集分立);北星两腿同 E-5 零持门。
- 原语组成:状态机骨架;阶段门;三层职责线;工具白名单(全部既有原语,零新词入原语表——22 词冻结不动)。
- 门挂点 8 条新增(挂点 31→39,全机检 existsSync+fragment):pipeline.mjs#DISCOVER_PIPELINE;gates.mjs#G_SCAN/#G_SHORTLIST/#G_MEASURE/#G_ENQUEUE;discovery-host.mjs#mkDiscoveryHost;discover-candidate.mjs#CANDIDATE_ACTION;monthly.py#load_discover_proposals。
- **序言计数零硬编码**(#187 判例:计数以原语表为准,不重复计数)。
- GLOSSARY.md 铸词 **PROPOSE(提案动作词)** 一行式(发现轮/发现管线已在伞 charter 铸,未重复)。
- 红证:删 D-7 门挂点行 → FAIL=1「D-7 缺门挂点字段(条文五件套不全=伪标准形态)」挂点回落 31;复原 → OK=55 FAIL=0 挂点=39。

### ③ monthly.py 北星两腿(2d71cc1f)

- `backend/ipdb/_eval/monthly.py` 新纯函数:`discover_conversion(proposed, landed)`(queue.md PROPOSE 去重行 vs 注册表源名逐字匹配;宁少算:候选名≠模块名=漏匹配不算落地;无提案→None 不虚构 0%)+`exclusivity_distribution(values)`(四桶 [0,0.25)/[0.25,0.5)/[0.5,0.75)/[0.75,1],0.25 桶界=ENQUEUE 门槛,ge_gate 计数;零读数→None)。
- loader:`load_discover_proposals(ops_dir)`(queue.md PROPOSE 行去重 slug,缺文件/零行→None)+`load_discover_exclusivity(ops_dir)`(rounds/*-discover*/d3-measure.json 聚合 results[].exclusivity_estimate,坏件跳过)。
- `northstar_record` 扩三注入 kwarg(proposed/landed/exclusivity),record 增 `discover` 节;`render_northstar` 第二行「发现轨北星(ADR 0010, 只观测不持门)」N/A 哨兵三态分立(无 PROPOSE 记录/零排他读数/全量两腿)。
- 接线 `__main__.py` run_readout:ops_root() 单源(_ops_store),registry 源名集合=landed;生产 P2 桥(node DOCS_ROOT/ops)与 python ops_root 同址同文件。
- 月报行:monthly-*.md 头块发现轨行 + northstar-*.json discover 节。
- **零持门三重实证**:①零 exit(monthly.py 全文无 exit 调用)②不进回归族(fusion_replay_gate.py/monthly_eval.sh 零 discover 消费;gates.mjs 排他率命中=T1 环内四门,非北星持门)③CI 零改(.github/ 无 diff)。
- 测试:`tests/eval/test_eval_northstar.py` 12 新例(纯函数手算真值:3 distinct/2 landed/2÷3;n=5 mean=0.43 桶 1/2/1/1 ge_gate=4;loader 只收 -discover 轮、ENQUEUE 行不入、缺件→None)。红先:实现前 ImportError 真红。

### ④ CHANGELOG 伞条(17ae289b)

Unreleased/新增 一条双语伞(#206-#210):T1 六步骨架+OPS_DISCOVER_*(月帽共享 admitOrRefuse)/T3 校验器+discovery-host+PROPOSE 候选卡+配额通道计数/T2 span 三面(spanMatcher+数字复算+对账,注明落笔时未合流)/T4 PROPOSE 统一+北星两腿+D-7 八挂点+GLOSSARY+DESIGN。门数字=各工位已证数,终数留合流终审(dispatcher 更新)。

### ⑤ DESIGN.md §6 翻正(dd012d77)

预算四界(OPS_DISCOVER_* 30/3600s/¥5,月帽共享 ¥30)/北极星(发现侧两腿零持门)/实绩回流(discover 找源已升格发现轮管线,ENQUEUE 只写+PROPOSE+全人裁)三处措辞滞后翻正,一词一拼。

## 自决记录(超出票面字面、需 merger 知悉)

1. **spanMatcher 挂点不挂 citation.mjs**(T2 未合流,挂了即死锚=伪标准 FAIL):D-7 挂活面四门+discovery-host+CANDIDATE_ACTION+load_discover_proposals;判例链注「spanMatcher 挂点随 #208 合流补挂」——**合流 merger 动作项**:T2 合入后补 `ops/agent/pipeline/citation.mjs#spanMatcher` 入 D-7 门挂点行(挂点 39→40)。
2. **PROPOSE↔落地匹配口径**:候选 slug(≤32 snake)vs 注册表模块名逐字相等=落地;宁少算,名不符=漏报不虚增。真实转化率下界。
3. **排他率桶界取 0.25**:ENQUEUE_EXCLUSIVITY_GATE 常量同值;桶界即门槛语义,不改门槛。
4. 北星接线 dev 面:worktree 无 docs/ 仓,loaders 自然 miss→None(N/A 哨兵),不虚构。

## 验收门(全绿)

| 门 | 数字 | 基线 | 结果 |
|---|---|---|---|
| selftest-pipeline | **PASS=96 FAIL=0** | 96/0 不降 | ✅ |
| standard-check | **OK=55 FAIL=0(挂点 39/条文 15)** | 挂点增+FAIL=0 | ✅(31→39) |
| pytest(tests/core+tests/eval 超集,主仓 venv) | **1224 passed, 8 skipped** | 全绿 | ✅(含 northstar 26/26,12 新) |
| selftest.sh 全伞 | **PASS=115 FAIL=0** | 全绿 | ✅ |
| node --check | steps.mjs/selftest-pipeline.mjs | — | ✅(运行即装载面) |

## commit 链(worktree,未 push)

```
17ae289b docs(#210 T4): CHANGELOG 双语伞条
dd012d77 docs(#210 T4): DESIGN.md §6 三处翻正
7f55c7f8 feat(#210 T4): STANDARD D-7+八挂点+GLOSSARY PROPOSE(红证 FAIL=1→复原)
2d71cc1f feat(#210 T4): 北星两腿+零持门三重实证(红证 ImportError→26 passed)
0e34a57f feat(#210 T4): ENQUEUE 步 action 词统一 PROPOSE(红证 95/1→96/0)
01b3c6b2 chore(#210 T4): 占位 commit
```
