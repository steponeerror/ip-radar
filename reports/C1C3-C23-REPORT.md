# C1C3-C23-REPORT — C2(#203)+C3(#204) 实现者交卷报告

工位:`.worktrees/c1c3-c2c3`(分支 `feature/c1c3-c2c3`,基 = 集成分支 `feature/c1c3-artifacts-ctx` @ a7c0f150)。零 push。

## 交付 C2(#203):月度准入拒跑块单源化 ✅

**收口前现状**:拒跑块在 `agent.mjs runRound`(legacy 面)与 `pipeline.mjs runPipeline`(管线面)逐字复制——文案/`[admission]` log 行/台账留痕行三件全同(#200 Spec 轴已核),漂移只靠人记。

**落地**(`ops/agent/pipeline/budget.mjs`):
- `export const refusalOf(a)` — 纯文案面,单源产出 `code="budget_monthly"` + 拒跑 message(counted/skipped 读数嵌文)。
- `export async function admitOrRefuse({ledgerFile, capCny, estCny, env, log})` — 留痕外壳:`monthlyAdmission` 读 → 放行返回 `{refused:false, admission}`(读数对象原样回传,`state.monthly_admission`/09-budget.json 观察面字节不变);拒跑则 `[admission] budget_monthly refused month=… spend=… est=… cap=… skipped=…` log + `appendRefusalTrace` 台账行(写败只 log 不翻转裁决,宁拒不跑)→ `{refused:true, ...refusalOf(admission)}`。
- 双面改调用,只映射各自出口:agent.mjs `throw Object.assign(new Error(msg), {code})`(main 兜底信封 exit 1);pipeline.mjs `emitFail(code, message)`(信封 exit 1)。**两面行为/日志/台账行/exit code 逐字不变**。
- 容差口径(spec P2 附注项):`admitMonthly` 上方集中单点注释——精确比较无 ε(`spend+est>cap` 才拒,等号放行);gates.mjs/steps.mjs 轮预算面的 +1e-9 灰尘容差先例不入本面;将来若加月帽 ε,admitMonthly 是唯一合法落点。

**哨**(selftest-pipeline.mjs 新增 1 条,"A2-拒跑块单源"):真台账树(mkTree)断言 message 逐字=收口前文案、logs 逐字=[admission] 行、台账含 `budget_monthly refused est=0.05 cap=0.05`、放行面 `refused:false + admission.spend=0.04` 原样回传+零日志。

**红证**(真红,已录):①未实现期 `admitOrRefuse is not a function` → 78/1;②容差翻转 `<=`→`<` → 恰「A2-纯函数…等号(0.04+0.06=0.10=帽)放行」真红 78/1,还原后绿。

## 交付 C3(#204):ctx 形状单源化 ✅

**收口前现状**:`runResume`(pipeline.mjs ~:435-444)手工重建 ctx,与 `mkCtx`(~:101-125)字段清单两处维护,形状漂移靠人记(终审 smell)。

**落地**(`ops/agent/pipeline.mjs`):
- 新增 `export const ctxShape({type, roundId, opsRoot, env, log, fixturesDir, modelFace, budgetCny, budgetKnobs, breakerKnobs, state})` — ctx 字段清单唯一构造点(模块内函数,择浅):dir 自算 `path.join(opsRoot,"rounds",String(roundId))`、展开 `ctxPaths`(四键含 retroAuditKey)、ledgerFile 公式、`modelCalls:0 / dupRegistry:new Map() / usage:{input:0,output:0,totalTokens:0,cost:0}` 每次新建、state 传引用不克隆。
- `mkCtx` 尾部改 `return ctxShape({...})` — **旋钮校验(budgetCny 非负有限/budgetKnobs/breakerKnobs)全部留在 mkCtx 进 ctxShape 前,不前移不放松**;ctxShape 刻意零校验零补齐。
- `runResume` 改 `const ctx = ctxShape({...})` — 值面 = state 复原 + 缺旋钮补 env 读取(`state.budget_knobs ?? readBudgetKnobs(io.env)`、`state.model_face ?? "faux"` 不变;`budgetCny = state.budget_cny` 不校验不补,旧轮 undefined 原样保持)。前置读 state.json 的局部 dir 保留(ctxShape 自算等值)。runReplay 走 mkCtx 自动获益(未动)。

**哨**(selftest-pipeline.mjs 新增 2 条):
- "C3-ctx 形状单源:ctxShape 闭集键钉死" — 构造后 `Object.keys().sort()` deepEqual 23 键金集(含 ctxPaths 四键 rulesFile/itemsDir/retroFile/retroAuditKey;= gates/steps 两消费面所读闭集);附 dir 自算、usage/dupRegistry/modelCalls 新建、state 引用不克隆断言。
- "C3-ctx 唯一构造点" — 读 pipeline.mjs 源文本,`dupRegistry: new Map()`、`modelCalls: 0`、`usage: { input: 0` 各恰出现 1 次(手抄字段清单回潮=第 2 处出现即红)。

**红证**(真红,已录):临时删 ctxShape 返回体的 `breakerKnobs,` 字段 → 闭集哨真红 80/1,还原后绿。(期间自修一例:哨金键集手写序 "envelope"/"env" 与 JS 字典序相反致哨假红——两侧同 .sort() 修复,属测试自bug非产品面。)

## 验收门(全绿;除注明外均为 C3 完成态实测)

| 门 | 数字 | 判定 |
|---|---|---|
| selftest-pipeline | **81/0**(基线 78/0,+1 C2 哨+2 C3 哨) | ✅ 基线不降 |
| selftest-t4 | **63/0**(任务文 58/0 系旧数;改动前基线实测 63/0,不降) | ✅ |
| selftest-contract | **18/0** | ✅ |
| golden | **9/0**(罐装面 = 验收门④ 位等价抽验:工件集合与文件名不变) | ✅ |
| standard-check | **47 OK**(条文14/金标3/建议10/挂点31/原语22,已有12/半缺7/缺3) | ✅ |
| backend pytest ops 子集 | **271 passed, 1 skipped**(主仓 venv;`-k "ops or store"`) | ✅ |
| legacy smoke | `node agent.mjs` 无参 exit 2;`OPS_PIPELINE_BUDGET_CNY=abc node agent.mjs health x` exit 2 | ✅ 不炸 |

注:上表数字在 C3 代码完成态实测;其后仅改 markdown(CHANGELOG.md、本报告),零代码面重叠,门不受影响。基线对照(改动前,/tmp/c23-baseline.log):pipeline 78/0 · t4 63/0 · contract 18/0 · golden 9/0 · standard-check 47。

## 自决清单

1. CHANGELOG 双语条只写 C2+C3(本工位两票);C1(工件名表)词条留给其工位自落——不代写未验证工作。
2. C2 哨放 selftest-pipeline(A2 系旁,同台账树 fixture 复用);C3 择浅=模块内函数(pipeline.mjs export),未开独立模块。
3. t4 门数字以实测基线 63/0 为准(任务文 58/0 为旧基线,PR3b 后已 63),不降不追旧数。
4. C3 哨金键集手写序初版与 JS 字典序冲突("env"<"envelope")致假红——两侧同 .sort() 收口(哨自身修复,非放松)。

## Commit 链

```
f89fd08b refactor(#204): C3 ctx 形状收口 pipeline.mjs ctxShape——mkCtx/runResume 共用单一形状构造…(门:81/0 等)
326fd2ff refactor(#203): C2 月度准入拒跑块收口 budget.mjs admitOrRefuse——双面文案/log/台账行单源…(门:79/0 等)
6e50476b chore(c2c3): placeholder — 40min wall guard, resume anchor (tickets #203 #204)
```

## 残留风险

- resume 面行为等价靠既有 resume 测试组(三规则+负例)+ 全 faux 轮钉住;旧轮 `state.budget_cny === undefined` 字面路径无专属历史 fixture(行为「不补不校验」由 ctxShape 零校验设计+注释钉死),如需可后续补历史形状 fixture。
- `runModelStage` 的防御补 `ctx.budgetKnobs ??= …` 保留未动(非本次票面)。
