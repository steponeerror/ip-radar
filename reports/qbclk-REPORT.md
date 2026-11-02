# qbclk 分支报告:ops 月帽守卫时钟注入口,五处月翻页竞态收口(#268)

- 分支:`qbclk`(基线 queue-batch 805c0d59,开工已验 `git merge-base --is-ancestor queue-batch HEAD`,worktree 干净)
- 来源:#267 独立评审环双角一致缓办项(#266 同向事故:月帽 fixture 月 ≠ 准入月 → 花费归零假红,毫秒~秒跨月末午夜窗)
- 性质:最小产品缝 + 测试;`git diff --stat` = 4 files,+44/−15

## 改动(照票)

产品缝(三处,注释均带出处 #268 / #267 评审环):

1. `ops/agent/pipeline/budget.mjs:146` — `admitOrRefuse` 开 `now = new Date()` 注入参数(缺省=纯缝零行为变化),`:147` 透传 `monthlyAdmission({..., now})`(月键 `monthNow(now)`)。`monthlyAdmission`/`monthNow` 的 now 参数基线已有,本票补的是外壳 admitOrRefuse 这一缺口。
2. `ops/agent/pipeline.mjs:394` — runPipeline 准入调用透传 `now: opts.now`(缺省 undefined → budget 缺省 `new Date()`)。
3. `ops/agent/agent.mjs:163` — runRound 准入调用同形透传 `now: opts.now`。

测试(`ops/agent/selftest-pipeline.mjs`,票面五处 fixture+准入成对墙钟读全收):

- 五处月帽用例(原 :1786/:1804/:1815/:1830/:2010)统一改「冻结 now + 月键单次取定」:`const now = new Date(); const m = monthNow(now);`,同一 now 经 runPipeline/runRound opts 或 admitOrRefuse 直参透传准入侧——fixture 月与准入月恒同,跨月末午夜零竞态。五处 = A2 超帽拒跑 / A2 帽内放行 / A2 legacy runRound / A2 拒跑块单源 / 发现轮月帽共享执法(#207 T1,注释在 #266 历史上补 #268 口径)。
- 新增负例 `A2-now 注入缝(#268)`(:1850):固定史前月 2024-05(本地时区构造,与 monthNow 的 getMonth 同口径,跨时区确定)做证——①注入 now=fixture 月 → spend 计入 → 拒跑 + `[admission] log` 行 `month=2024-05`(月键确来自注入 now 的直接证据);②注入 now=次月(恰跨月末午夜形)→ 台账行不计入 → spend=0 → 等号放行(0+0.05≤0.05),#266「花费归零」机制在注入面可复现。两向合证缝真生效非摆设。

## 红证:注入错位负例修复前后对照(TDD 先测后缝)

同一命令 `cd ops/agent && node selftest-pipeline.mjs`:

| 时点 | 结果 |
|---|---|
| 修复前(仅测试改完,产品未动) | `PIPEFAIL A2-now 注入缝(#268,#267 评审环缓办收口)…: 月对上(注入 now=fixture 月)→ spend 计入 → 拒跑(缝没生效则 spend=0 放行,此断言红)` → `pipeline-selftest: PASS=104 FAIL=1`(唯一红=新负例:admitOrRefuse 不认注入 now,月键回退墙钟月 ≠2024-05 → spend=0 → 放行) |
| 修复后(三处缝落地) | `PIPEPASS A2-now 注入缝…` → `pipeline-selftest: PASS=105 FAIL=0`(基线 104 例全平 + 新例 1) |

修复前五处既有月帽用例照绿(extra opts 键被忽略,行为同旧)——红仅归因于缝缺失,非测试自伤。

## 验收面(全绿)

四套 selftest(先 `ops/agent` 内 `npm ci`,worktree 无 node_modules 起步):

- `selftest-pipeline.mjs`:PASS=105 FAIL=0(基线 104 + 新 1)
- `selftest-contract.mjs`:PASS=19 FAIL=0
- `selftest-standard.mjs`:PASS=15 FAIL=0
- `selftest-t4.mjs`:PASS=63 FAIL=0
- 加跑伞面 `bash selftest.sh`:PASS=118 FAIL=0(docs 符号链接缺席部分按守卫 SKIP 计 PASS,判例如常)

产品调用面等价(票面第二臂「缺省路径行为逐字等价」):

- 全库调用面清点(grep admitOrRefuse/monthlyAdmission):生产 CLI(pipeline.mjs :520/:525)、golden runner(run-golden.mjs:110)、agent main(agent.mjs:335)、agent-v2 步前准入(tasks/budget-guard.mjs:49)全部不传 now → 缺省 `new Date()` → 与基线逐字同路径。
- agent-v2 零复制 re-export 自动带上新参数(op/agent 零改动红线未碰,v2 文件零改动);`ops/agent-v2` 内 `npm ci`(v2 自有 lock,worktree 首跑装 chord 等依赖)后 `node --test tests/budget-parity.test.mjs`:**11 pass / 0 fail**——旧 admitOrRefuse 对 v2 admitRound 的裁决/文案/留痕对拍全平,即缺省路径字节等价的独立旁证。
- 既有逐字钉死用例(A2 拒跑块单源:文案 + [admission] log 行逐字)在缝落地后照绿。

## 备注

- agent-v2 测试不在 CI 面也不在四套验收面;本次加跑纯为等价性旁证,其首跑 ERR_MODULE_NOT_FOUND(@earendil-works/chord)为 worktree 依赖未装之环境事,`npm ci` 后即绿,与本批改动无关。
- 只 commit 本分支 qbclk;基线 queue-batch 为 HEAD 祖先,收尾 `git merge queue-batch` 预期 Already up to date(留痕见下)。
