# WORKER REPORT — #170 模型步真 provider 接线(灰度开关硬前置)

分支 feature/ops-p170-provider(基 6cd98cb3),3 commits:638a2ebd(接线)/ 8a7575b8(测试)/ e42341cc(文档)。
改动面:ops/agent/{pipeline/faux.mjs,pipeline.mjs,pipeline/steps.mjs,agent.mjs,selftest-pipeline.mjs,golden/run-golden.mjs,fixtures/pipeline/README.md} + GLOSSARY.md + deploy/ops-cron.md。backend 零改动。

## 选择机制(faux.mjs = 唯一替换点,选择逻辑纯函数零网络)

- `selectModelFace({fixturesExplicit, inherited})`:显式 fixtures(--fixtures/opts.fixturesDir:自测、golden、零成本审计)→ **faux**;否则继承面优先(replay 保真)→ 缺省 **real**(运行面:生产/cron 轮无 --fixtures)。
- 判据 = 「显式 fixtures」而非「fixtures 在场」:仓内缺省 fixtures 目录在生产容器同样在场,在场判定会把生产轮判成 faux(正是 ops-cron.md 原禁令警告的罐装假设死法)。
- `STEP_ROUND = {TRIAGE: health, SYNTH: health, DEEP: discover}` → models.mjs `resolve()`:TRIAGE/SYNTH=OPS_MODEL_HEALTH(缺省 glm-5.3-flash),DEEP=OPS_MODEL_DISCOVER(缺省 glm-5.3)。**models.mjs 零改动**,复用 legacy 轮既有 env 旋钮与三层装载。
- 面入 `state.model_face`(additive,backend boot 扫描只读特字段零敏感):replay 继承原件面(pre-#170 轮恒 faux);resume 复原 state 面;手搓 ctx/pre-#170 state 缺省 faux(零网络安全缺省)。

## 真路径(经 pi-agent-core Agent 真调用,同 legacy)

- `ctx.models` 注入缝(agent.mjs opts.models 同型金轨迹缝)优先;缺省 `loadModels()` 轮内缓存(目录一次)。resolve 失败=infra(配置面)。
- 留痕不减:transcript 同行型(input/message);真面 input 行增 `model: "provider/id"` 字段(门不读该行,faux 面行型逐字节不变);**真实 usage 数字**经 runModelStep 返回→引擎 addUsage→信封 usage + RETRO 台账(真面标签 `pipeline-real`,faux 面不变 `faux-pipeline`)。
- 预算三闸真面同执法:微探针 ≤3(G_DEEP 逐 transcript seed 计数)、假设 ≤3(DISPATCH 截尾)、轮预算(G_DISPATCH 合计门)——门全工件面,面无关;⑫测试钉住真面正/负例。
- 失败语义同 faux:stopReason error/aborted→model_face;重试 ≤1/逐假设降级 unresolved/终态归引擎(零改动)。真面另加 `[model]` turn 观测行(stderr,legacy [turn] 同型,SSE 透传不解析)。

## 微探针缺口(票面注记,设计内,留下票)

真面 DEEP **tools=[]**(本票只接模型 provider):模型无探针可调→零 registry_seed 行→confirmed/refuted 证据腿无登记表可回引,**必被 G_DEEP 拒**(⑫负例实测:伪 call_id→「引用未知 call_id」)。真面深验合法输出=unresolved(零证据腿过门,⑫正例)。真探针工具接线=下票;GLOSSARY「微探针」已改写记档。附带:零 need_deep 轮金轨迹在真面=一次真 glm 调用(裁定①保活语义自然延伸,~0.008-0.016¥/轮,轮预算内)。

## 偏离

1. **引擎非字面零改动**:mkCtx/runReplay/runResume 增面选择管道(各 1-3 行);「唯一替换点」承诺保持——引擎只记录面,provider 逻辑全在 faux.mjs。
2. **自测/golden 调用点显式化**:原依赖缺省 fixtures 路径的 6 处(runPipeline×3/golden/spawnPipe matrix 负例/agentMain 委派腿)改传 `DEFAULT_FIXTURES_DIR`(同路径同行为,面=faux);非 dry replay 由面继承自动安全。
3. **首跑事故如实报**:两处旧测试(双模灰度开关/matrix 负例)改前不传 fixtures,首跑真面真打了 API(TRIAGE flash×2 + DEEP glm×1,约 3 次调用,费用分厘级)后暴露并修复——也实测验证了真面链路装载/调用/门执法真实可达(模型无工具时确实伪造 call_id 被 G_DEEP 拒)。
4. STEP_ROUND 复用 health/discover 轮键而非新增 env:语义注记在两文件头;agent.mjs env 表 consumer 描述同步(零行为变化)。
5. selftest.sh 计数 101(记忆台账 102)= worktree 缺嵌套 docs 仓的 SKIP 计数差,基线同值,非本次改动。

## 验收(先 commit 后跑,四门全绿 + 新增 4 例绿)

- pipeline 44/0(新增⑫×4:面选择纯函数/faux 面毒缝哨兵/真面 fake 传输层信封形状+失败面/G_DEEP 真面同执法正负例)
- contract 15/0(env 双向对拍:零新增 env 读取)| selftest.sh 101/0 | golden 9/0(pipeline 例显式 fixtures 同路径)

剩余(部署段,不在本票):生产真 provider 冒烟一轮(A 一律/门全过+预算实测数字入台账)→ 用户裁 OPS_PIPELINE=pipeline 灰度(deploy/ops-cron.md 第 3 项已更新前置)。
