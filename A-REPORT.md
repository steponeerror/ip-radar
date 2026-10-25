# PR3b 交付 A 实现报告 — 票 #199「P15 预算四界」(#199 交付A)

- 工作树:`.worktrees/pr3b-a`,分支 `feature/pr3b-a`,基 `master=e952c584`
- 实现者:SDD fresh implementer(交付 B/熔断器 P16 不在本任务,未触碰)
- 收口时间:2026-10-25

## 交付清单(A1–A5 全落)

| 交付物 | 内容 | commit |
|---|---|---|
| A1 四界环内执法 | 新模块 `ops/agent/pipeline/budget.mjs`(六旋钮单源+纯函数);`runModelStage` ①调用数帽/③墙钟逐假设前查、②token/④花费结算后查;`runStages` 步边界③墙钟;违界 `fatalBudget` 直穿不重试不降级(宁少算);ERROR_CODES 9→13 词 | `172b74c7` |
| A2 月度 kill switch 准入 | `monthNow`/`monthSpendOfLedgerText`/`admitMonthly` 纯函数;pipeline.mjs(mkCtx 后、建目录前)与 agent.mjs runRound(legacy 面)双面共享 budget.mjs 准入;拒跑=`code=budget_monthly` 信封+exit 1+`appendRefusalTrace` 台账留痕行(锁内);无台账=0 起步;缺 cost 行跳过不猜 | `0f074717` |
| A3 台账双写面加锁 | `_ops_store.append_ledger` 持 `_ledger_lock()`(fcntl LOCK_EX,#139 判例,锁文件常驻不删);lib.sh `ledger_append` 头建+追加整段进 `flock "$LEDGER_FILE.lock"`;月度读面共享同锁;契约第 18 哨跨语言锁路径对拍;backend 并发测试 2×40=80 行零丢 | `2ba20582` |
| A4 重复调用哈希 | `canonicalJson`/`dupKey`(sha256 前 16 hex)/`dupRecord`/`dupTop` 纯函数;ToolHost.beforeToolCall 与 mkMicroprobeHost(微探针)双注入;第 3 次同参拦=`code=repeat_storm` 结构化信封(引 01:59 同参白烧判例;合法≤2 次重试不受影响;`limit=0` 停用) | `b4e6994c` |
| A5 09-budget.json 工件+G_CLOSE 扩展 | CLOSE 步先于 pkg 早退写工件(七旋钮生效值+usage/model_calls/wall_s/dup_top3/monthly 读数);G_CLOSE inputs+=09-budget.json,形状+读数≤帽回声哨(防工件漂移,非二次执法);golden 桩同步(cases.json 钉七旋钮+model_calls=4+monthly.ok);工件清单测试收录 | `6bb2836f` |

## Commit 链

```
b4113bb2  wip: #199 交付A 开工(占位防超时丢工)
172b74c7  feat(#199 A1): 预算四界环内执法
0f074717  feat(#199 A2): 月度 kill switch 双面准入
2ba20582  feat(#199 A3): 台账双写面加锁(双侧)
b4e6994c  feat(#199 A4): 重复调用哈希双面注入
6bb2836f  feat(#199 A5): 09-budget.json 工件+G_CLOSE 回声哨
<CHANGELOG commit>(本报告+CHANGELOG 同批)
```

## 各门数字(红期→绿期)

| 门 | 红期(真红) | 绿期 |
|---|---|---|
| selftest-pipeline(node) | A1: 63/5;A2: 68/4;A3: 见 backend 红行;A4: 72/3;A5: 74/3 | **77/0** |
| selftest-contract | —(新哨随批落地) | **18/0** |
| selftest-t4 | — | **58/0** |
| golden(run-golden) | — | **9/0** |
| standard-check | — | **OK=48 FAIL=0**(条文14 金标3 建议12 挂点30 原语22 已有10/半缺9/缺3) |
| selftest.sh 全量 | — | **115/0** |
| backend pytest(相关子集:test_ops_store/test_ops_read/core/test_api_update/core/test_startup) | A3 并发红:2×40 追加实得 40 行(丢行近半) | **65 passed**(含新并发零丢例) |

红测真红记录:每交付物均先写测→跑红→实现→绿。A3 红期为 backend 并发探针实测丢行(期望 80 实得 40);A1 红期 5 例(budget.mjs 不存在+执法缺位);A2 红期 4 例(monthNow 未落);A4 红期 3 例(canonicalJson 未落/拦截面缺);A5 红期 3 例(工件缺+inputs 缺+复评缺)。

## 偏离与理由

1. **ERROR_CODES 一次性 9→13 词(A1 批,非逐交付物)**:闭集扩展是交付A 一体的契约面(spec 验收门 3 明示 A 增四码);生产者分批落地,单源闭集一次成形避免三次改同一断言。channel_open 属交付 B,未加。
2. **BUDGET_KNOBS 六旋钮 A1 一次全录**:单一旋钮面(消费方逐批接线),契约扫描器面 24→30 一次对拍,测试 A1 即钉全默认值。
3. **golden 桩同步=cases.json 钉工件断言,无 GOLDENFAUX 常量**:现场核实仓内不存在 GOLDENFAUX 常量(grep 零命中),golden 桩的真实现状=run-golden.mjs 读 cases.json 断言;已按 #189 conflict 字段判例同形落 cases.json(pipeline_health_full_faux += 09-budget.json,七旋钮值+model_calls=4+monthly.ok=true+三读数面 matches)。spec 词汇以现场为准。
4. **P15 典章面(STANDARD.md:29/:103/:154-155、DESIGN.md:74、GLOSSARY 三词)未在本批**:spec「典章流程」节写明该面为 A+B 共享收口;任务令明确要求的典章面仅 CHANGELOG。留待 B 落地后一次收口(P15 半缺→在 + P16 同批),避免 B 未实现时翻正 P16 语境。**遗留项,见下。**
5. **t4 内进程 runRound 读工作树 docs/ops/ledger.md**(A2 起读月度面):文件缺席=0 起步,与生产语义一致;golden/contract 已显式重定向 LEDGER_FILE,无跨测试污染。
6. **A2 准入语义「等号放行」**:`projected=spend+est ≤ cap` 即跑(admitMonthly ok=projected<=cap)。spec 未钉等号归属;取等号放行与 G_DISPATCH `≤ cap+1e-9` 先例一致(宁少算不拦边界内)。

## 遗留

- **P15 典章翻正 + P16 典章面 + GLOSSARY「预算四界/双点执法/调用哈希」铸词**:交付 B 落地后同批收口(spec 典章流程节;偏离 4)。
- **CHANGELOG 已写双语条**(本批 commit);若合并方要求 CHANGELOG 与典章同批,可摘出。
- 生产激活注记:六旋钮经 `_ops_rounds._SPAWN_ENV_PREFIXES=("OPS_","PI_")` 自动进 spawn 白名单(C4 面零改动);`OPS_PIPELINE_MONTHLY_CAP_CNY` 默认 30 即生效,拒跑面留痕行经 lib.sh flock 同锁域。
- 冒烟建议(合并后):真跑一轮 health 确认 09-budget.json 落盘 + 台账 memory_peak_bytes 行(下轮自然落)同场。

## 环境注记

- worktree 无 venv/node_modules;node 测试用 symlink `ops/agent/node_modules → 主仓`(未提交,.git/info/exclude 已忽略);backend 测试用主仓 venv。
- **判例:worktree 内 sandbox_assert 跑 `git status --porcelain -- backend/ frontend/`,backend 未提交改动会让全部全轮测试假红(8!==10 门)——跑 node 自测前 backend/front 必须干净**(A3 期间实踩,~30min)。
