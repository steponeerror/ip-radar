# DP-T1-REPORT — 发现轮管线骨架+旋钮族+台账(#207 T1)

工位:worktree `.worktrees/dp-t1`(分支 `feature/dp-t1`,基=集成分支 `feature/discover-pipeline-v0` @ b8825774)。
spec:/tmp/discover-pipeline-spec.md T1 节(权威);ADR 0010;票 #207(伞 #206)。
状态:**全部 T1 交付物落地,验收门全绿;禁 push 已遵守(未 push)。**

## 交付物清单(spec T1 节逐条)

1. **DISCOVER_PIPELINE 六步表**(`ops/agent/pipeline.mjs`):SCAN→SHORTLIST→MEASURE→ENQUEUE→RETRO→CLOSE(+FAILED 终态书挡),数据驱动同 HEALTH_PIPELINE 形制。`PIPELINES={health,discover}` 单源;byName/runnable/STAGE_PREFIX 一律 per-type 派生(`byNameOf`/`runnableOf`/`STAGE_PREFIXES`)。
   - SCAN(script,零模型零网络):候选宇宙快照 `d1-scan.json`=**源注册表面**(backend/ipdb/_sources/*.py 非_前缀,evidence_ptr=repo 相对路径)+**NEEDS.md 缺口行面**(状态∈{open,候选},evidence_ptr=`NEEDS.md:L<n>`)+web 面占位(`channels.web.status="placeholder"`,T3 接线)。
   - SHORTLIST(model `discover/shortlist`,fail retry1/terminal model_face):结构化候选解析,**失败=降级空清单留痕不炸轮**(`d2-shortlist.json={candidates:[],degraded:"shortlist_parse:…"}`,步仍 done,零候选合法,同 TRIAGE 零假设判例)。
   - MEASURE(script):T1=本地确定性存在性面(候选 evidence_ptr ∈ d1-scan 指针集 → evidence_local_ok);未测/超时=`status:"uncertainty"` hold 行留痕(T3 接探针后消除)。工件 `d3-measure.json`。
   - ENQUEUE(script):**只写不动作**——经 `ops/agent/tools/queue-lock.mjs appendQueueRowLocked`(#139 flock 真路径,node/python 同锁同址)写 `ops/queue.md`;入队三判据=证据存在性全过+排他率预估≥`ENQUEUE_EXCLUSIVITY_GATE`(0.25,常量)+阳性对照可执行,**判据在代码不在 prompt(模型无权改,ADR 0010)**;不过=skipped 留痕;queue 写败=fail-closed infra。工件 `d4-enqueue.json`。
   - RETRO/CLOSE:同 health 律(台账幂等/sandbox 红线/09-budget.json 同形快照)。
2. **round-id 形制**:`^\d{4}-\d{2}-\d{2}-\d{4}-discover(-r\d+)?$`——mkCtx 正则 per-type 构造(后缀集=轮型集);`typeOfRoundId(id)` 后缀推断(显式 type 优先,不符即拦);resume/replay 正则同步双后缀;replay 前缀复制 discover=d1-d4。**selftest 既有 faux 面同构新增**(见红测/绿测节)。
3. **旋钮族**(`ops/agent/pipeline/budget.mjs`):`readDiscoverKnobs`={OPS_DISCOVER_MAX_MODEL_CALLS=30, OPS_DISCOVER_WALL_CLOCK_S=3600, OPS_DISCOVER_SPEND_CAP_CNY=5, **monthlyCapCny=OPS_PIPELINE_MONTHLY_CAP_CNY(共享同键同缺省 ¥30)**};mkCtx 入口校验(非法=usage 错);**月帽共享=admitOrRefuse 同一函数**(runPipeline 传 `round:ctx.type`,只影响留痕轮次列,裁决真源 admitMonthly 不变);dup 哈希沿用(canonicalJson/dupKey/dupRecord 原样)。引擎四界 per-type:发现轮报错文案指认 OPS_DISCOVER_*;**token 界=发现轮跳过**(tokenBudget undefined 判)。
4. **artifacts.mjs 名表扩容**:DISCOVER_SCAN/DISCOVER_SHORTLIST/DISCOVER_MEASURE/DISCOVER_ENQUEUE 四名入 ARTIFACTS(总 22);新增派生导出 `HEALTH_ARTIFACT_NAMES`(原 18)与 `discoverArtifactNames()`(7:四名+09-budget/gates/state);d2 transcript 由步面管不入名表(任务明令四名;发现轮闭包断言=固定面∪transcript 字面)。闭包哨三层自动覆盖。
5. **台账标签**:`LEDGER_TAGS={health:"pipeline",discover:"pipeline-discover"}` 单源(steps.mjs 导出,steps 写面+gates 读回检查同源消费)。
6. **接线点占位(T3 填)**:SHORTLIST 真面经 runModelStep 通用机零工具注入;MEASURE 本地面;web 渠道 placeholder;prompt `prompts/discover/shortlist.md`(输出契约/span 逐字回引 T2 强化/回声防线/模型无权改判据);canned fixture `fixtures/pipeline/shortlist.json`(两真候选:L14 rDNS parquet+L17 carrier,queue 零入队=排他率未测故 skip,设计使然)+faux.mjs STEP_ROUND/transcriptName SHORTLIST 接线+README 行。
7. **CLI**:`node ops/agent/pipeline.mjs discover [--round-id ID] [--fixtures DIR]`(main usage/emitInfra 轮名 per-type)。

## 验收门数字

| 门 | 数字 | 基线 | 判 |
|---|---|---|---|
| selftest-pipeline | **PASS=89 FAIL=0** | 81/0 不降 | ✅(81 基线全绿+8 新例) |
| selftest-t4 | **63/0** | 63/0 | ✅ |
| selftest-contract | **18/0** | 18/0 | ✅(OPS_DISCOVER_* 三名入 SPAWN_CONTRACT_ENV+测试名集) |
| golden | **9/0** | 9/0 | ✅(health 罐装位等价;run-golden.mjs 门数改 HEALTH_PIPELINE 派生单源) |
| standard-check | **OK=47 FAIL=0(挂点 31)** | 47 | ✅ |
| pytest ops 子集(backend venv) | **276 passed, 1 skipped** | — | ✅(82.9s) |
| health 轮罐装面位等价 | golden 9/0+基线 81 全绿+pytest 全绿 | 零变 | ✅:health 可见面零变(门序 10 门/门记录/台账行/env 7 键/报错文案同字符串),仅内部派生单源化 |

## commit 链(worktree,未 push)

1. `174aa199` chore(#207) 开工占位(空)
2. `41662317` 旋钮族单源+月帽共享+SPAWN_CONTRACT_ENV 三名
3. `615a648c` 步/门/faux 面+四门+canned fixture+prompt+台账标签
4. `f52669fc` DISCOVER_PIPELINE 六步表+引擎 per-type 化+selftest 8 新例+健康轮断言 per-type 化
5. `0a1b1e4c` golden 门数 per-type 派生+本报告

## 红测真红记载(实现前捕获,PASS=81 FAIL=8)

| 例 | 红证(逐字) | 注 |
|---|---|---|
| ①旋钮族(含负值拒) | `TypeError: readDiscoverKnobs is not a function` | 结构红:负值/非数字拒行为由 readKnob 单源既有合同测试钉死(#199 判例);绿面新增断言(负值/非数字/env 覆盖/缺省/月帽共享同值)全绿 |
| ②台账标签 | 断言败:留痕行轮次列=discover(实际落成 health) | appendRefusalTrace 硬编码 round="health" 时期 |
| ③月帽共享拒 discover | wiring 红:`round_id 形状须 YYYY-MM-DD-HHMM-health:…-discover`(mkCtx bad_round 先于 admission 面) | 接线后真行为绿:¥30 植入→拒 budget_monthly+留痕 round=discover+轮目录不建 |
| ④round-id 后缀双面 | wiring 红:rejects 消息不匹配(/形状须…-discover/ 不中,P0 拦截面) | 绿后双面真拒 |
| ⑤全 faux 六步 | 同③ wiring 红(轮未起) | 绿后六步/信封/09-budget env 面 5 键/台账行/门序全验 |
| ⑥工件闭包+SCAN 确定性 | `Cannot read properties of undefined`(runD 未成) | 绿后含独立树重扫逐字节同 |
| ⑦SHORTLIST 降级 | 同③ wiring 红(降级断言不可达) | 绿后坏 fixture 真跑解析失败路径:candidates[]+degraded+d3 零行+d4 零入队 |
| ⑧ENQUEUE 写路 | `The "path" argument must be of type string`(ENQUEUE 步未实现) | 绿后含 flock 真写+幂等去重 |

**四例法定红对应**:旋钮负值拒=①(结构红+readKnob 合同注)/月帽共享=③/round-id 后缀=④/SHORTLIST 降级=⑦——各一例真红在案。

## 自决清单(实现者拍板项,评审可翻)

1. **轮型推断**:typeOfRoundId 由 round-id 后缀推断(显式 type 优先)——测试/agent 侧可只给 id;两者不符由 per-type 正则拦。
2. **LEDGER_TAGS 与 ENQUEUE_EXCLUSIVITY_GATE 放 steps.mjs 导出**(步写面/门读面同源单源),gates.mjs import 消费。
3. **SCAN 不加 NEEDS_FILE env 缝**(repo 相对路径直读):避免 OPS_* 表闭包噪音;T2/T3 需要时再加。
4. **d2 transcript 不入名表**(任务明令四名);发现轮闭包=discoverArtifactNames()∪transcript 字面。
5. **健康轮既有断言 per-type 化**:门契约=GATE_SEQUENCE↔双管线执行序**并集**双射;健康轮门数/门序从 HEALTH_PIPELINE 派生(HEALTH_GATES_SEQ/HEALTH_GATE_COUNT);golden/run-golden.mjs 同判例(GATE_COUNT→HEALTH_PIPELINE.filter)。
6. **faux canned 两候选=queue 零入队**(排他率 null→skip):罐装轮不写 queue(测试树内也无 queue 副作用),ENQUEUE 真写路由独立例⑧直调步验证。
7. **replay 末步工件 per-type**(health=07-synth-report.md/discover=d4-enqueue.json);resume 正则/旋钮回退读面/pending 步序 per-type。
8. mkCtx 的「P0 仅健康轮管线」throw 由 PIPELINES 闭集校验替代(历史使命完成)。

## 给 T2(#208)/T3(#209)的接线点说明

**T3 已交卷(0cc76b1d),按其接线协议对接**(DP-T3-REPORT):
- SHORTLIST:模型步真面工具注入=`discovery-host.mjs mkDiscoveryHost() → {tools,seeds,channelCounts,call}` 直装(runRealStep 的 DEEP 判例位:mkDiscoveryHost 替代 mkMicroprobeHost);ctx 级 dupRegistry 沿用(旋钮族 dupCallLimit 同读);轮级 breaker 同面。
- MEASURE:探针调用=`host.call`(T1 的 uncertainty hold 行在 T3 后由真实读数替换,超时面仍 hold)。
- CLOSE:`readings.discover_channels=discoverChannelReadings(host.channelCounts)`(09-budget.json 增读数面;G_CLOSE 的 BUDGET_ENV_KEYS per-type 已就位)。
- 候选 schema 校验=`discover-candidate.mjs`(12 导出面)——G_SHORTLIST/G_MEASURE 行形状校验升级时消费(T1 最小形状版由 gates.mjs 内联,T2 #208 强化时收口)。
- SCAN web 面:`channels.web` 从 placeholder 升真读(host.tools 的 web 三工具=候选宇宙第三渠道),渠道闭集 `[source_registry,needs,web]`。
- T2 #208 四门强化:G_SHORTLIST span 逐字回引(spanMatcher)、G_MEASURE 数字复算、G_ENQUEUE 对账;T1 已把四门名+序+最小形状钉进 GATE_SEQUENCE 双射面(单侧改门即红)。

## 余项(非 T1 面)

- T2 #208:四门强化+spanMatcher+selftest 罐装篡改红。
- T4:STANDARD/GLOSSARY/北星/CHANGELOG(本票未动 CHANGELOG——伞 #206 收口批处理)。
- 生产激活面:OPS_DISCOVER_* 三旋钮缺省值(30/3600/¥5)即生效,无需 env;与 #199 判例同(agent.mjs SPAWN_CONTRACT_ENV 已含三名)。

*报告人:T1 实现者(worker);2026-10-26;40min 顶内完成,无撞墙。*
