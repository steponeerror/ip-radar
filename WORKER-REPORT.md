# WORKER REPORT — 票 #165(P2-P3 TRIAGE+SYNTH 上线+DEEP 桩)

分支 feature/ops-p2-p3(base=8c4e03d4,集成分支 tip 未动,merge no-op)。主仓 5 commit(ae4f1932→8e27faa8);docs 仓 1 commit(68f4202)。

## 交付(票面 1-8 项)

1. **提示词落地**:`prompts/health/triage.md`(§3.2 草案)+`synth.md`(§3.4)——输出契约 JSON 形状/字段闭集逐字未动;附录 A 九项对照见下表。
2. **TRIAGE 模型步**:真提示词装载(steps.mjs promptFile);吃 survivors+known_noise_digest;schema 门+重试≤1(门评估入重试圈,见偏离⑤)。
3. **SYNTH 模型步**:三节报告;判例注入=anchors-health.json 域词表×幸存旗标 anchorSelect(锚选目标须在真源库在场)+ 同词表 rg 检索(_INDEX 召回),并集截 HIT_CAP=8;闭合校验 allowed=预注入(transcript meta.injected);输入增条目明细(items/ 直读,ADR 0006 渲染面)。
4. **DEEP 桩**:定义表 `stub:"deep_stub"` 数据标记,faux 吃 `deep/_stub.json`;全部 verdict=unresolved/evidence 空;stages status=degraded+note 注桩;P0 逐假设 fixture 退役,A 一律机制改 G_DEEP 单元例钉住。
5. **空转金轨迹**(#162 审 P2-2 裁定①):零 need_deep 轮 DEEP 跑 GOLDEN_BUNDLE(hid=golden-track-canned)canned faux 回路;deepFinalize 单收 golden_track(不污染 verdicts/条目);G_DEEP 机检「零 bundle⇒金轨迹在场,有 bundle⇒不混轮」。
6. **门增强**:G_TRIAGE=signal_id 全覆盖(eqSet)+闭集值+need_deep 布尔/one_line/digest 必填;G_SYNTH=四计数+深验三计数抽检(verdicts∪degraded∪truncated 回算,#162 审 P2-5)+闭合校验(违例 code=closure_check 门指定码)。
7. **共享纪律件**:`prompts/shared/redaction.md`(1113 制度化)+`envelope.md`(禁补数);triage/synth 各一行指针引用(deep.md P4 落地时同律)。
8. **顺手件**(#164 审 P2):docs 仓 R7 adopted_via 补注 C 稿 §4.2 出处(68f4202);selftest.sh 挂 build-index --check+promote-detect --dry(--docs-root 显式+PRECEDENTS_DIR 内联指真源,docs 缺席 skipok SKIP——worktree 本跑 SKIP 属守卫设计,主 checkout 真跑,已手动对真源验证双 rc=0)。

## DESIGN.md 附录 A 对照(新提示词两件)

| # | 项 | triage.md | synth.md |
|---|---|---|---|
| 1 | 角色句动词开头/判断编排分离 | 「为每条…写一条可证伪假设」动词开头+不裁决不执行不写文件 | 「把机器产物渲染成人读报告」+不新增判断不替人裁决 |
| 2 | done-when 机检 | 完成判据段:signal_id 全覆盖+闭集+JSON 可解析(门机检) | 三节齐+计数逐字+闭合+≤10 行(门机检) |
| 3 | 反模式 tell | 「复述读数而没写预测——停」 | 「给 unresolved 写倾向词——停,渲染员没有判断面」 |
| 4 | 信息阶梯 | 必读内联;shared/ 指针;源清单/工具零复述 | 同左 |
| 5 | 结论挂信号 | signal_id 逐字回引+读数逐字来自输入 JSON | 每个数字可在输入 JSON 找到(门抽检含深验三计数) |
| 6 | 工具白名单+预算 | 「你没有工具、没有调用预算」显式 | 同左(只读闭集=DEEP P4 面) |
| 7 | 脱敏+信封处置 | 一行指针 shared/ 两件+缺字段写 null | 指针+matrix.ok=false 禁补数条款 |
| 8 | 判例闭合+➡️非阻塞 | 不裁决,产物交人 | 禁编路径+闭合校验+「悬而未决·待人裁」 |
| 9 | AI 声明宿主渲染 | 头注声明,提示词不要求产出 | 同左 |

## 偏离 C 稿草案(微调,契约未变)

①triage 输入节补 known_noise_digest 一句(§3.5 要求 digest 进 TRIAGE,草案输入节漏写);②synth 摘要把深验三计数写成显式必填行 `confirmed=N refuted=N unresolved=N`(P2-5 抽检需机器可解析;草案只说「各几条」);③金轨迹 hid 不入 verdicts 单收 golden_track(05-deep-verdicts.json 增量字段);④DEEP 桩=定义表 stub 数据标记非步名硬编码,P4 删标记即真开启;⑤单发步门评估从「步后一次」移入重试圈(§2.2「契约违例重试≤1」诚实实现,P0 引擎只对 consume 异常重试);⑥门可指定终态码(closure_check),缺省仍 fail.terminal。

## 验收数字(先 commit 后跑)

- **四门全绿**:selftest.sh 伞面 `PASS=101 FAIL=0`(t4 30 例/golden faux 9 例/contract 15 例/pipeline 23 例)。
- **selftest-pipeline 新增 ≥4 例**:实增 4(空转金轨迹轮/SYNTH 闭合违例负例/verdict 抽检负例/G_DEEP A 一律单元例)+桩语义断言更新 3 处,23/0。
- **全 faux 轮端到端**:R1 轮 TRIAGE/DEEP 桩/SYNTH 三模型步 usage 在场,DEEP=degraded+note;CLI 子进程轮 rc=0(docs2 例);提示词装载直验 systemPrompt===triage.md 全文。
- 真源面:build-index --check FRESH(概念 12/档案 8/锚域 6);promote-detect --dry 留痕 8(live 7)→候选 1。
- golden pipeline 用例随桩语义对齐(DEEP=degraded+note_matches 断言面新增)。

## 风险/待办

- ITEMIZE degraded 行折入(重试尽 unresolved 同入清单)是 P3 顺手修的既有缺口;reopened 计数仍 P4。
- DEEP 桩轮的 SYNTH canned 深验行依赖「桩 unresolved=全数」巧合一致(2342 降级轮 1+1=2 同值);P4 真开启后 canned 件整体退役,不构成契约。
- anchors-health.json 锚选在运行时对缺件锚过滤(build-index --check 在 CI/主 checkout 面兜底闭包)。
