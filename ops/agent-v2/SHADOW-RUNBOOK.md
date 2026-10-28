# SHADOW-RUNBOOK.md — shadow 期运行手册(票 #229 T5 任务书④)

spec 定案 2 安全轨的运维面:旧管线原地不动,v2 在 `ops/agent-v2/` shadow 跑满一月轮周期,golden + 新旧产出对拍一致才切流。**切流时点由用户裁决,本手册不自动切。**

## 观察面(每轮 cron 后)

```bash
# 对拍闸门(罐装世界,零网络,~1min):旧 replay vs v2 checkpoint 任务
node ops/agent-v2/shadow-diff.mjs <YYYY-MM-DD-HHMM-health>   # 退出 0=全 SAME
# 全量测试套(52 测/51 绿+1 设计 SKIP,含 parity + cron-launchers + E2E + SIGKILL resume + 重试/跨库/exit 码面 + golden 三面)
cd ops/agent-v2 && node --test 'tests/*.test.mjs'
```

双轨 cron 形态(shadow 期):旧 `pipeline.mjs` cron 照跑(生产真源);v2 侧双轮型——健康轮 `run-health.mjs` 每日一轮、发现轮 `run-discover.mjs` 按旧发现轮节拍(周频/手触),各 `--db` 独库(缺省 `docs/ops/agent-v2.sqlite`),轮 id 独立命名,台账/queue 各自世界——**shadow 期 v2 不写生产台账与 queue、不进生产轮目录**。操作面差异:发现轮 real 面强制 `--model provider/modelId` 显式(旧管线自动 resolve;模型清单见 models.mjs),健康轮缺省自动 resolve 同旧。

## SAME 门槛

- `shadow-diff.mjs` 退出 0(可比工件闭集 + 台账行,归一化窄面见其头注)。
- 全量测试套 52 测 51 绿 + 1 设计 SKIP(smoke 凭证门)。
- **golden 对拍(#232 已收口,切流硬门槛)**:管线面 2/2 位等价对拍(`pipeline_health_full_faux`+`pipeline_discover_full_faux`,tests/golden-health-parity/golden-discover-parity,归一化窄面同 shadow-diff)+ legacy 判断器 8 例回归钉(golden-judge-regression:判断器例驱动 legacy agent.mjs runRound 面,spec T3 明示不迁 v2——钉的是 v2 依赖世界保持 GOLDENPASS,非管线对拍;切流删旧时随 legacy 面退役)+ smoke 例凭证门(golden-smoke-gated:选层门恒钉,OLD 面双门手跑,NEW=N/A)。
- 连续一个完整月轮周期内:零 infra 信封(v2 侧)、零对拍 DIFF、SIGKILL/断电恢复演练至少一次通过(`tests/resume.test.mjs` + 人工 kill 面板)。

## 已知差异面(声明,非缺陷)

| 差异 | 性质 | 处置 |
|---|---|---|
| v2 健康轮无 state.json(真源=SQLite checkpoint+工件;仅发现轮落 state.json 兼容旧面) | 实现细节 | 不入对拍面 |
| `.v2-claim.json`(v2 健康轮轮目录认领件;跨库撞轮守卫) | v2 专属守卫落件 | 不入对拍面(shadow-diff NEW 侧白名单已列入) |
| 09-budget.json 旧 CLOSE 也落件(非 v2 专属);真实差异=对拍载具双侧停笔 RETRO 故均不落 | 载具结构 | CLOSE 面落件由 `tests/cron-launchers.test.mjs` 钉(09-budget 存在性断言) |
| 台账 usage 计数(in/out/total)计量边界差 | 两套 harness 合法差 | 对拍归一;cost 细胞逐字比(ENVELOPE.md §usage) |
| 对拍载具停笔 RETRO(旧 replay 不入 CLOSE) | 载具结构 | CLOSE 面由 `tests/cron-launchers.test.mjs` 钉(G_CLOSE/09-budget/信封) |
| PROBE/VERIFY 不入罐装对拍(真探测面,零网络红线) | 载具结构 | 两侧均为零复制 `steps.runStage` 同码路;生产 v2 轮真跑 |

## 影子世界置备(shadow 期轮跑前置)

shadow 期 v2 侧 `DOCS_ROOT` 指影子根(与生产 `docs/ops` 分置),防误指生产写脏。置备=从生产 rsync 一份再清轮次状态:

```bash
mkdir -p <影子根>/docs && rsync -a docs/ops/ <影子根>/docs/ops/
rm -rf <影子根>/docs/ops/rounds/ <影子根>/docs/ops/ledger.md <影子根>/docs/ops/queue.md  # 轮次目录/台账/队列清空——v2 侧从零起卷
# precedents/ rules/ items/ 保留(判例/规则/条目库是轮次输入面,随卷携带)
```

v2 侧 cron 起轮时显式带 `DOCS_ROOT=<影子根>/docs`(与 `--db` 影子库同理);指向生产根属配置事故——认领件/台账/queue 会写脏生产树。

## 回退

v2 无生产流量 → 回退=停 v2 cron 即可,零数据迁移。SQLite 库/轮目录留在原地供事后审计(证据永不灭失)。

## 切流(用户裁决后)

1. 前置:上表 SAME 门槛全满足,用户明示切流。
2. 切换 cron:旧 `pipeline.mjs` cron 下线,`run-health.mjs` 接同一轮 id 序列与生产台账世界(`DOCS_ROOT`/`LEDGER_FILE` 指生产)。
3. 首两周双观察:v2 信封/台账行抽查 + 月度准入读数对拍(月帽口径 ENVELOPE.md)。
4. 观察期满后旧管线代码退役(单独 PR,先归档后删)。
