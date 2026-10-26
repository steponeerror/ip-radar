# DP-T35-REPORT — T3.5 发现轮工具面真接线(#217)实现交卷

- 工位:`.worktrees/dp-t35`,分支 `feature/dp-t35`,基 8611e82b(feature/discover-pipeline-v0 tip),**未 push**。
- 补票来源:双轴终审 Spec 轴 P1——mkDiscoveryHost/discoverChannelReadings/appendCandidateCard 生产消费方仅 selftest;SHORTLIST 零工具注入、MEASURE 恒 uncertainty+control_executable:null、CLOSE 无 discover_channels 读数;净效应=真面发现轮永不过 ENQUEUE 三判据、零候选行。

## 一、commit 链(逐件)

| commit | 内容 |
|---|---|
| 620720b6 | chore(#217) 占位 commit |
| 6e306c1a | D1:readDiscoverKnobs 追 dupCallLimit 键(OPS_PIPELINE_DUP_CALL_LIMIT 同键同缺省 3,其 header 本就预留此处为消费点);selftest 旋钮族例扩断言红先绿 |
| 6683c2f5 | D2+D3 三点接线:faux.mjs SHORTLIST 注入 ensureDiscoverHost / steps.mjs MEASURE 重写 host.call("web_read") 真证据面 / CLOSE readings.discover_channels 纯增量键;ctxShape 增 discoverHost 键;fixtures shortlist.json rDNS 排他率 0.42 + 新 measure.json 罐装;selftest 全轮 E2E 正例 + 新四例;接线回退红证 100/4 |
| 87bc10c3 | 表头三写口翻正:queue-lock.mjs/_ops_store.py QUEUE_HEADER + 两件 python 测试 fixture(northstar fixture 预存 rationale 子句漂移顺手对齐)+tools.mjs/discover-candidate.mjs 注记;新 contract 表头对拍哨(python 字面↔node 字面↔首建实写串逐字同+三写词语义哨) |
| 0b0804b2 | wip(#217 续作入库防丢):golden pipeline_discover_full_faux 扩端到端正例 + prompts/discover/shortlist.md 工具面句翻正(截断现场存量,续作验证后收口) |
| (本次) | CHANGELOG 双语条 #217 + DP-T35-REPORT.md |

## 二、四条任务逐项

### ① 三点接线(照 discovery-host.mjs 顶部接线协议)

- **SHORTLIST**(模型步):faux.mjs runRealStep probes 三元扩展——`def.name === "SHORTLIST" ? ensureDiscoverHost(ctx) : (DEEP 原路)`,host.tools 直装 initialState.tools;dupRegistry=ctx 级(与模型调用同注册表,#199 A4 判例);breaker=轮级 mkBreaker 实例(ops/breaker.json,ctx.breakerKnobs 优先)。faux 面 tools 保持 [](罐装宇宙,零网络律不变)。
- **MEASURE**(确定性零模型):逐候选 host.call("web_read",{url}) 补发实测探测,同守卫链(dup→breaker→cap)、measure-N call-id、tool_seeds 落 d3 工件留痕。判据语义:
  - evidence_local_ok=scanEvidenceFace 宿主重算(原样);
  - url_read_ok 三态:true(结构面 ok)/false(探测执行且明确失败,code 透传)/null(守卫拒绝或无结构面——被拒≠清白,不充当证据);
  - control_executable=url_read_ok——阳性对照=探测自身可执行且读到结果;无 URL 候选=「控制面不可算」显式 uncertainty;
  - exclusivity_estimate=SHORTLIST 值透传(测量面无改估权,勿虚构;G_MEASURE 钉 passthrough);
  - 三面全解=measured;任一不可算=uncertainty+显式原因串(url_read_code 留痕)。
- **CLOSE**:readings.discover_channels=discoverChannelReadings(活宿主 channelCounts 优先含 blocked;宿主缺席(resume/重放)=aggregateChannelCalls(replayDiscoverSeeds(ctx)) 从 d2 transcript registry_seed 行+d3 tool_seeds 重算,宁少算——被拒调用零种子不回放);健康轮零改动字节面不变(键仅 isDiscover 分支展开)。
- **接线消费点**:readDiscoverKnobs.dupCallLimit(OPS_PIPELINE_DUP_CALL_LIMIT,缺省 3)→ensureDiscoverHost dupLimit;fixtureDiscoveryMethods(fixtures/pipeline/measure.json 罐装 web_read 表;未罐装=诚实 io_error 信封)。

### ② 端到端候选行正例(不再只钉零入队)

- fixture:rDNS 主机名候选 exclusivity_estimate null→0.42 + measure.json 罐装 ok web_read(https://ip.thc.org)。
- selftest-pipeline 全轮 E2E:faux 六步全绿,d3 rDNS 行 measured/evidence_local_ok true/url_read_ok true/control_executable true/exclusivity 0.42/hold_n 1/tool_seeds[0]=measure-1;d4 n_enqueued 1/n_skipped 1;queue.md 实写 `| <RD> | PROPOSE | rdns |` 行;09-budget readings.discover_channels.channels.web_read.calls=1。
- golden pipeline_discover_full_faux 同钉:d3 pins+matches(measure-1)/d4 {1,1}/queue_file state:row PROPOSE rdns 行/09-budget discover_channels 读数。
- 新四例:罐装方法三态(ok/罐装失败 code 透传/未罐装 io_error)、MEASURE 三态(4 同 URL dupLimit 3:第 3 次起 repeat_storm 显式 uncertainty 宁少算)、CLOSE 读数面(活宿主优先↔回放重算↔健康轮无此键位等价)、接线挂点哨(源面 grep 挂点在位)。

### ③ queue.md 表头句翻正(一词一拼)

- 新句:`# 源生命周期动作队列(三写口:ops 轮 queue_action · 发现轮 ENQUEUE 候选行 · 发现轮候选卡 appendCandidateCard;后两路 action=PROPOSE 一词一拼;行由 host 模板渲染,rationale 只落工件)`
- 落点:ops/agent/tools/queue-lock.mjs QUEUE_HEADER、backend/ipdb/_ops_store.py QUEUE_HEADER、backend/tests/test_ops_store.py fixture、backend/tests/eval/test_eval_northstar.py fixture(预存缺 rationale 子句漂移顺手对齐)、ops/agent/tools.mjs:8 注记、discover-candidate.mjs 注记。
- 新 contract 哨(§14 同形):python 字面↔node 字面(JSON.parse 逐字面)逐字同 + 三写词语义正则 + appendQueueRowLocked 首建实写串 startsWith 断言(18→19)。
- 刻意不动:prompts/discover-system.md:2「唯一写口」(模型写动作面语境仍真)、DESIGN.md:39(异语境)。

### ④ 门全绿不降 + 红测真红

见下节。

## 三、门数字(worktree 实跑,续作收口后终跑)

| 门 | 结果 |
|---|---|
| node ops/agent/selftest-pipeline.mjs | **PASS=104 FAIL=0**(基线 100 全在 + 新 4 例) |
| 红证(接线回退) | git show 6683c2f5^ 的 steps.mjs+faux.mjs 覆盖 → **PASS=100 FAIL=4**(恰全轮 E2E 扩钉+MEASURE 三态+CLOSE 读数面+挂点哨四例红,基线零损)→ 还原回 104/0 |
| node ops/agent/golden/run-golden.mjs | **PASS=10 FAIL=0**(discover 例扩正例断言) |
| node ops/agent/selftest-contract.mjs | **PASS=19 FAIL=0**(18 基线 + 新表头对拍哨) |
| node ops/agent/selftest-t4.mjs | **PASS=63 FAIL=0** |
| node ops/agent/standard-check.mjs | **OK=56 FAIL=0 条文=15 金标=3 建议=10 挂点=40 原语=22** RC=0 |
| backend 触面 pytest(判例命令) | tests/test_ops_store.py + tests/eval/test_eval_northstar.py **48 passed** |
| node --check | 全部 11 个触面 mjs OK;python ast.parse 三件 OK |

## 四、自决与依据(代码内注释已落)

1. **control_executable 语义**=测量通道阳性对照(url_read_ok):探测自身执行且拿到结构面结果才 true;无 URL 候选=null+「控制面不可算」。未采「上一轮通道历史」(那是熔断面,不是本轮控制面)。
2. **被拒≠清白**:守卫拒绝(repeat_storm/channel_open/budget)→ url_read_ok=null + code 留痕 + uncertainty,绝不把拒绝当成失败证据(fail≠missing)。
3. **CLOSE 回放重算宁少算**:活宿主优先(含 blocked 面);resume/重放无宿主时从工件回放,被拒调用零种子不可回放——读数少计不多计(回声不是印证)。
4. **健康轮位等价**:discover_channels 键仅 isDiscover 分支展开,健康轮 09-budget 字节面不变(CLOSE 例直钉健康轮无此键)。
5. **faux 面零网络律**:fixtureDiscoveryMethods 未罐装工具=io_error 信封,不降级为真网络调用。
6. **northstar fixture 漂移顺手对齐**:test_eval_northstar.py 的 queue 头 fixture 原缺「rationale 只落工件」子句(预存漂移),本批统一为完整新句——同一冻结串三抄一致是哨的存在前提。
7. **表头哨形式**沿 §14 既有锁名对拍哨形制(python 正则抽字面↔node 正则抽字面↔首建实写),不新造哨形。

## 五、余项/风险

- **真面(MeASURE 真网络)未在本机实跑**:接线面与守卫链由罐装/三态/挂点例钉死,真面 web_read=r.jina.ai 网络路径与 #199 交付 B 熔断同代码路,离线不可验;首真轮观察点=d3 tool_seeds+09-budget discover_channels 读数。
- appendCandidateCard(候选卡第三写口)仍无管线内调用方(T3 遗面):本票范围=表头如实+哨钉死,不伪造消费方;接线留 #206 后续票裁。
- prompts/discover/shortlist.md 句已翻正(web_read/web_search/rss_parse 三只读工具可调),属文案面无门。
- breaker.json 在本批所有绿门下不产生新写路径(罐装/回放均零计数码),B-snapshot 健康例(breaker.json 不创建)仍绿。

## 六、交割

- 未 push;worktree 留待 merger 独立复算(SDD 纪律:不信自报,merger 重跑全门+红证重放)。
