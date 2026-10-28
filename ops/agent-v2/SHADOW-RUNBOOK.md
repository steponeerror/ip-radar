# SHADOW-RUNBOOK.md — shadow 期运行手册(票 #229 T5 任务书④)

spec 定案 2 安全轨的运维面:旧管线原地不动,v2 在 `ops/agent-v2/` shadow 跑满一月轮周期,golden + 新旧产出对拍一致才切流。**切流时点由用户裁决,本手册不自动切。**

## 观察面(每轮 cron 后)

```bash
# 对拍闸门(罐装世界,零网络,~1min):旧 replay vs v2 checkpoint 任务
node ops/agent-v2/shadow-diff.mjs <YYYY-MM-DD-HHMM-health>   # 退出 0=全 SAME
# 全量测试套(38 测,含 parity + cron-launchers + E2E + SIGKILL resume)
cd ops/agent-v2 && node --test 'tests/*.test.mjs'
```

双轨 cron 形态(shadow 期):旧 `pipeline.mjs` cron 照跑(生产真源);v2 侧双轮型——健康轮 `run-health.mjs` 每日一轮、发现轮 `run-discover.mjs` 按旧发现轮节拍(周频/手触),各 `--db` 独库(缺省 `docs/ops/agent-v2.sqlite`),轮 id 独立命名,台账/queue 各自世界——**shadow 期 v2 不写生产台账与 queue、不进生产轮目录**。操作面差异:发现轮 real 面强制 `--model provider/modelId` 显式(旧管线自动 resolve;模型清单见 models.mjs),健康轮缺省自动 resolve 同旧。

## SAME 门槛

- `shadow-diff.mjs` 退出 0(可比工件闭集 + 台账行,归一化窄面见其头注)。
- 全量测试套 40/40 绿。
- **golden 全集新旧逐条一致(票 #232,切流硬门槛)**:当前分支覆盖 1 例(discover full faux)+罐装健康截段(shadow-diff);全集(neg/boundary/health_full_faux 等 ~10 例)补齐前不得切流。
- 连续一个完整月轮周期内:零 infra 信封(v2 侧)、零对拍 DIFF、SIGKILL/断电恢复演练至少一次通过(`tests/resume.test.mjs` + 人工 kill 面板)。

## 已知差异面(声明,非缺陷)

| 差异 | 性质 | 处置 |
|---|---|---|
| v2 健康轮无 state.json(真源=SQLite checkpoint+工件;仅发现轮落 state.json 兼容旧面) | 实现细节 | 不入对拍面 |
| 09-budget.json 仅 v2 落件(CLOSE 步) | v2 专属预算落件 | 不入对拍面 |
| 台账 usage 计数(in/out/total)计量边界差 | 两套 harness 合法差 | 对拍归一;cost 细胞逐字比(ENVELOPE.md §usage) |
| 对拍载具停笔 RETRO(旧 replay 不入 CLOSE) | 载具结构 | CLOSE 面由 `tests/cron-launchers.test.mjs` 钉(G_CLOSE/09-budget/信封) |
| PROBE/VERIFY 不入罐装对拍(真探测面,零网络红线) | 载具结构 | 两侧均为零复制 `steps.runStage` 同码路;生产 v2 轮真跑 |

## 回退

v2 无生产流量 → 回退=停 v2 cron 即可,零数据迁移。SQLite 库/轮目录留在原地供事后审计(证据永不灭失)。

## 切流(用户裁决后)

1. 前置:上表 SAME 门槛全满足,用户明示切流。
2. 切换 cron:旧 `pipeline.mjs` cron 下线,`run-health.mjs` 接同一轮 id 序列与生产台账世界(`DOCS_ROOT`/`LEDGER_FILE` 指生产)。
3. 首两周双观察:v2 信封/台账行抽查 + 月度准入读数对拍(月帽口径 ENVELOPE.md)。
4. 观察期满后旧管线代码退役(单独 PR,先归档后删)。
