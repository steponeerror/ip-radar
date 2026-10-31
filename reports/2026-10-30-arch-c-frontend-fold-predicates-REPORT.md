# #245 前端折并抽取 + 任务状态谓词收编 — 实现报告

- 分支:`ticket/arch-frontend-fold-predicates`(基于 origin/master @ 34021685)
- 票:[#245](https://github.com/steponeerror/ip-radar/issues/245)(架构评审 2026-10-30 候选 5+6,同批)
- 日期:2026-10-30

## 一、抽了什么(候选 5:折并逻辑两份内联拷贝)

**新建 `frontend/src/components/serviceFold.ts`**(共享模块,~40 行含出处注释):

- `foldServiceStatements(stmts: AssetStatement[]): { value, detail }[]` — service 角色词折并核心:按源侧写死的归一角色词(dns/ntp/cdn/cloud)分组,**Map 首见序**(不重排、不按可靠性挑赢家,零选择算法),证人 `source · native_type ?? value` 逐行拼悬停串。此前 `IpDetailPanel.tsx:125-149` 与 `ResultTable.tsx:47-66` 各持一份逐行同构的内联拷贝,现两组件各留 2 行调用(`IpDetailPanel` 推 `{text, detail, key}`,`ResultTable` 推 `{label, detail, key}`,仅字段名差异,属两组件既有 chip 形状,不强行统一)。
- 模块命名 `serviceFold` 对齐 GLOSSARY「折并」词条(fold=折并英文面;避开 merge/fusion——那是后端融合的词,不铸新词、不撞旧词)。

**常量化(暗协议拆除):**

- `SERVICE_CHIP_KEY_PREFIX = "service-"`(导出常量)+ `serviceChipKey(role)` 派生函数。
- 此前两组件靠 `` `service-${value}` `` 字符串模板暗协议耦合,`ResultTable` 的 cdn 压制判据 `startsWith("service-")` 悬在上面;现 key 生成与判据(`ResultTable.tsx:190/233` 两处 `startsWith(SERVICE_CHIP_KEY_PREFIX)`)同源派生,值不变。
- 抽取后 `frontend/src` 里 `service-` 字面量仅存于 serviceFold.ts 定义处(grep 验证零残留)。

**未动**:orgDup 折并(`IpDetailPanel.tsx:155-162`)单消费方、非复制件,不属共享面,留在原地;GLOSSARY 折并词条锚点仍指 IpDetailPanel(orgDup/service 分支),service 腿实现现于 serviceFold.ts(词条本体未改,锚点措辞见「遗留」)。

## 二、谓词收编清单(候选 6:任务状态谓词三处散推)

**收进 `frontend/src/tasks/progress.ts` 并导出**(与既有 stagedFrac/isIndeterminate 同居):

| 谓词 | 判定 | 收编来源(原内联处) |
|---|---|---|
| `isTaskTerminal(t)` | done / failed / cancelled | SourcesPage.tsx:226-228(防抖重拉 doneCount) |
| `isTaskActive(t)` | queued / throttled / downloading / loading | BatchPanel.tsx:21 私有 `ACTIVE_TASK_STATES`(三用点:taskActive / visibleTasks 过滤 / 取消按钮 disabled)+ SourcesPage.tsx:428-431 行内 busy(同集四态) |
| `isBatchLive(b)` | batch running / paused | BatchMiniBar.tsx:28 |

- BatchPanel 的 `ACTIVE_TASK_STATES` 常量本体收编为 progress.ts 模块私有(集名与四态注释随迁,含「throttled 必须读作忙碌」的 backend `_enqueue_one` 出处);导出面为谓词函数(等价导出)。
- 三消费方改调用:SourcesPage 两处、BatchPanel 三处、BatchMiniBar 一处;**TaskProvider 零改动**(票面红线)。
- 语义边界保留:isTaskActive 不含 ops 轮 `running` 相位(source="ops",轮次不阻查询门),与原三处内联逐位同集。

## 三、行为零变化论证(哲学 6「一切声明可证伪」)

- 两组件渲染路径等价:foldServiceStatements 的分组序=Map 首见序(与原内联 `for...of byRole` 同序),detail 串拼接式逐字符相同,key 生成值相同;组件推入对象逐字段同构。既有渲染测试全绿作位等价回放。
- 谓词:三处内联与收编后的谓词在各自类型域(TaskState 8 态 = 源任务 7 态 + ops running / BatchState 三态)上真值表一致;tsc 严格模式通过。

## 四、测试结果

| 命令(frontend/) | 结果 |
|---|---|
| `npm test`(vitest run) | **43 文件 / 451 测试全绿**(基线 444,新增 7) |
| `npx tsc -b` | 0 错误 |
| `npm run lint` | 0 errors / 3 warnings——均为既有(KeysSection/UpdateOverlay/TaskProvider,stash 对照干净树确认,非本次引入) |

新增测试(断言级,不改既有断言):

- `frontend/src/components/__tests__/serviceFold.test.ts`(4 例):同角色多源折并+证人序、异角色 Map 首见序、native_type 缺席回退归一值、key 常量派生(cdn 压制判据同源)。
- `frontend/src/tasks/__tests__/progress.test.ts` 增 describe(3 例):三谓词真值表(含 running 反例、null batch 反例)。

既有 IpDetailPanel/ResultTable service 折并渲染测试与 BatchPanel/BatchMiniBar 相关测试全部原断言通过,未改任何测试断言(导入路径无敏感——组件测试走渲染面,不触内部路径)。

## 五、遗留/风险

- **无行为风险**:纯重构,后端零动;渲染对照以测试钉住(位等价),未做手工视觉 diff。
- GLOSSARY.md 折并词条锚点「frontend/src/components/IpDetailPanel.tsx(orgDup/service 分支)」可顺手补 serviceFold.ts,但改 GLOSSARY 超票面范围,未动,留终审裁。
