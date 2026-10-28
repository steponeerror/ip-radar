# T5 报告 — cron 入口冻结 + 台账兼容 + shadow 对拍 harness + RUNBOOK(票 #229)

分支 `ticket/229-shadow`(worktree `.worktrees/t229`),四 commit:`f70fc03e`① `cc10892d`② `0c70715a`③ `2ead9bbf`④。全量 `node --test 'tests/*.test.mjs'` **38/38 绿**(新增 cron-launchers 5 测 + shadow-parity 1 测)。

执行背景:T5 首派 worker 30min 内死于 bigmodel 账户级 429(5h 窗上限,21:01 重置),worktree 零损失;父会话直收完成(用户明示「继续任务」)。

## ① cron 入口 + CLI 冻结(`run-health.mjs` 新 + `run-discover.mjs` 改 + `tasks/health-round.mjs` toPhase + `tools/discovery-tools.mjs` stderr)

- `run-health.mjs`:健康轮启动器。admitRound 准入(拒跑→`{ok:false,round:"health",error:{code:"budget_monthly"}}` exit 1)→ openHarness → root 会话 commit 建 `ops-health-round` 任务(input 含 fromPhase/toPhase/modelFace/fixturesDir/monthlyAdmission)→ waitForTask → stdout 末行=旧形信封;幂等:同库同轮复用任务(HealthRoundsDoc session 单例索引)。
- exit 码表冻结:0=completed / 1=failed·refused·parked / 2=用法 / 3=运行期异常。
- `toPhase`(旧 replay `--to` 镜像):任务相位机停笔书挡 `stopAtPhase`——停在 toPhase 完成后(含门与台账),终态 completed + 信封 stages 止于该相位;CLI 层(from/to 顺序)与任务 initial(闭集)双校验。载具必需:shadow 对拍两侧同停 RETRO。
- `discovery-tools.mjs` execute 补 `[tool]`/`[tool-result]` stderr 留痕行(票 #142 语法)。
- discover 侧测试断言迁到冻结信封面(stdout 末行=旧形信封,completed ⟺ ok:true)。

## ② 台账兼容 + usage 口径(ENVELOPE.md)

- 信封/台账 usage=**轮累计事件流口径**(harness.usage() 差分);UsageDoc 仅 harness 内部观察。
- 台账兼容行由 RETRO 步写,与旧管线同点同形;月度准入与前端解析零改动(cron-launchers + parity 双测试钉)。
- 已知计量边界差:v2 `in` 含 cache_read 且 `total` 再计缓存面 → 对拍中 in/out/total 归一、**cost 细胞逐字比**(faux 恒 0;真实轮 cost 独立求和不失真)。

## ③ shadow 对拍 harness(`shadow-diff.mjs` + `tests/shadow-health-parity.test.mjs`)

- 双面同种子罐装世界(判例+R1 规则+01/02 前置工件+永败 eval stub,seedWorld 导出复用):OLD=`pipeline.mjs replay --from TRIAGE`(旧契约缺省停 RETRO);NEW=`run-health.mjs --from-phase TRIAGE --to-phase RETRO`。
- **实测 15/15 SAME**:03-triage(假设+transcript)/04-dispatch/05-deep×5/06-itemize/07-synth×2/08-anchor×2/gates.json/ledger.md,退出 0。
- 归一化窄面:ISO 时间戳/dur_ms/tmp 路径/replay `-rN` 后缀/台账 usage 三计数;语义字段逐字比(收口 T3「归一化宽缝」遗留)。
- 载具判例两条:全链载具不可行(旧 PROBE 天生联网,golden 亦断点进;shadow 恒零网络红线)→ 只能断点进;轮 id 形状律 `YYYY-MM-DD-HHMM-health` 硬约束(bad_round)。

## ④ SHADOW-RUNBOOK.md

观察面(每轮 shadow-diff + 全量套)/SAME 门槛(一月轮周期零 DIFF 零 infra+SIGKILL 演练)/cron 双轨(shadow 期 v2 独库不写生产台账)/已知差异面五条(声明非缺陷)/回退(停 cron 即可,库留审计)/切流四步(**用户裁决后**才动)。

## 风险与移交

- PROBE/VERIFY 不入罐装对拍(真探测面):两侧均零复制 `steps.runStage` 同码路,生产 v2 真跑;若要罐装面需旧侧先提供 probe fixture 机制(现状无)。
- T0 遗留 #1-#6(月轮↔conversation 粒度/UsageDoc 口径已裁/逐工具 replay 裁定/SQLite NORMAL 断电/node≥22.19/attribution 头)不随本票收口,归切流前清单。
