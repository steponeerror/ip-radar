# B-REPORT — #199 交付B(P16 跨轮通道熔断器)

分支 feature/pr3b-b(worktree .worktrees/pr3b-b),基 7ac7c8d8(交付A 已合入)。spec=/tmp/pr3b-spec.md。

## 交付清单

1. **ops/agent/tools/breaker.mjs(新)**:纯核+有态壳。
   - 纯核:`BREAKER_CHANNELS` 恰五员{gh_search,web_read,web_search,rss_parse,fetch_url};`BREAKER_COUNTED_CODES` 恰三员{channel_missing,channel_auth,quota}(宁少算:transient/gh_error/io_error/http_error/network 不计);`parseBreakerState` 坏 JSON/错版本/野通道/野状态词/负 consec→null=fail-closed 重置闭路;`verdictFor`(closed→allow / open 冷却未到→block retryAfterS / open 已到→probe / half_open→block probe_in_flight);`grantProbe`(open→half_open **先落盘再放行**,探活名额持久);`applyResult`(closed 成功 consec=0=零写;半开成功→recovered 清零;半开失败→重开新整窗;半开非计数失败→退回原开断窗防困死;closed 计数失败 consec 累计,达阈→opened);`pushEvent` events 环≤20;`breakerSnapshot` 五员全列。
   - 有态壳 `mkBreaker({file,env,round,ledgerFile,knobs,log})`:态=DOCS_ROOT/ops/breaker.json,tmp+renameSync 原子写(_ops_store 判例);每操作重读文件(跨轮跨壳同文件为真源);转移事件经 lib.sh `ledger_append` 追台账行(flock 同锁域,写败 log 不抛=appendRefusalTrace 判例);旋钮 `readBreakerKnobs` 字面点形读(扫描面即契约面,A 的表驱动回退教训),缺省 3/21600,非负有限否则 `{usage:true}`,threshold=0=禁用。
2. **ops/agent/tools.mjs**:唯一接线点。constructor `mkBreaker({file:opts.breakerFile, env:opts.env, round, ledgerFile:opts.breakerLedgerFile})`;beforeToolCall 守卫序 **dup→breaker→cap**(自决#1),开断拦=结构化 `code=channel_open` 信封(带剩窗秒/探活在飞+下一步合法动作=改用非通道工具或升级人裁;勿轮内重试勿绕行),零 spawn;`finish()` 从结构化信封结算(仅通道工具、`structured.ok` 布尔面)——信封出口单源,注册表/测量/发现面零逐点撒。
3. **ops/agent/error-codes.mjs**:ERROR_CODES 13→14 加 `channel_open`。
4. **ops/agent/agent.mjs**:SPAWN_CONTRACT_ENV 追 OPS_BREAKER_THRESHOLD(default 3)/OPS_BREAKER_COOLDOWN_S(default 21600),phase=call-time。
5. **ops/agent/pipeline.mjs**:mkCtx 轮始校验 breaker 旋钮(budget 判例);恢复重建 ctx 同步。
6. **ops/agent/pipeline/steps.mjs**:CLOSE 快照 `readings.breaker`(mkBreaker 只读 snapshot:五通道态面+生效旋钮;**观察不裁决,G_CLOSE 不加对拍**=自决#3)。
7. 测试:selftest-t4 +5 例(闭集+旋钮/parse 纯核/verdict+grantProbe/applyResult/有态壳跨壳持久+探活+恢复+坏文件 fail-closed+台账留痕/宿主接线拦+非通道放行+跨轮成功清零;全局 host 落 breakerFile TMP 隔离+breakerLedgerFile 台账隔离);selftest-contract(14 词断言/名集断言/SRCS+聚合扩 tools/breaker.mjs);selftest-pipeline B-快照例(09-budget.json readings.breaker 在+轮后无 ops/breaker.json=快照零写)。
8. 典章(见下 commit 41a0c870)+CHANGELOG 交付B 双语条(含部署注记:breaker.json 由首个计数通道结果自动创建,快照/verdict 面永不写)。

## commit 链

- 68a36a09 wip: #199 交付B 开工(占位)
- 0dc92505 交付B 主体(breaker.mjs+接线+ERROR_CODES 14+旋钮表+快照+三面测试)
- 41a0c870 典章收口(A+B 同批:STANDARD P15/P16 翻已有/D-5 措辞+挂点/建议区两行删/DESIGN:74 翻正/GLOSSARY 铸词/CHANGELOG)
- (本报告 commit)

## 各门数字(红期→绿)

| 门 | 基线(A 后) | 红期 | 终态 |
|---|---|---|---|
| selftest-t4 | 58/0 | 55 pass 后模块装载崩(breaker.mjs 缺,exit 1) | **63/0** |
| selftest-contract | 18/0 | 17/1(14 词闭集断言) | **18/0** |
| selftest-pipeline | 77/0 | 77/1(readings.breaker 缺) | **78/0** |
| golden | 9/0 | —(结构断言面,快照增字段不破) | **9/0** |
| standard-check | 48 挂点30 | —(典章未动期不变) | **47/0 挂点31 建议10 原语22(已有12/半缺7/缺3)** |
| selftest.sh | 115/0 | — | **115/0** |
| backend pytest | 未触(backend/frontend 零改动) | — | 未跑(无触面) |

红期采集法:git stash 临时回退实现侧(留测试)真跑三红,再 pop 复绿——红是真红非纸面。

## 自决(spec 未钉处,全部留档)

1. beforeToolCall 守卫序 dup→breaker→cap:A4 注释钉 dup 先于每工具帽;熔断属通道级前置闸,插中间(先拦重复省预算计数,再拦通道级持久证据)。
2. threshold=0=禁用熔断(同 OPS_PIPELINE_DUP_CALL_LIMIT=0 停用判例);非负有限校验沿 mkCtx 判例 exit 2 用法错。
3. G_CLOSE 不加 breaker 对拍:快照是观察面,熔断无「帽可超」语义,回声哨只拍有帽读数(对拍死表项红面代价不值)。
4. 半开非计数失败退回**原**开断窗(非新窗):探活烧掉但证据非部署/账户级,下一窗可再探;新窗会半开死循环困死通道。
5. 探活名额持久化在 grantProbe 落盘时刻(同步):探活在飞中崩溃,重启见 half_open 即知名额已耗,不双探。
6. 计数回喂取 finish() 结构化信封码(=classifyChannelError 分类出口),非 classify 调用点逐处撒——同一数据更单源;spec「调用点回喂」意图=信封码喂计数,实现形如此。
7. pipeline 面不接线:microprobe 三工具(probe_head/reprobe_get/reprobe_ua)不在五通道闭集,通道工具只活 legacy ToolHost 面;spec「两面自动同享」按闭集合同实现=无通道工具面天然无需接线(发现,非偏离)。
8. 台账留痕=lib.sh ledger_append 同锁域行+文件内 events 环(≤20);RETRO 面留痕=09-budget.json readings.breaker 快照(轮终观测件)。spec 只说「台账/RETRO 留痕」,以此两件+快照兑现。
9. GLOSSARY 铸词面:任务书钉两词(预算四界/跨轮熔断一行式)已铸;spec 典章节另列「双点执法/调用哈希/半开探活/通道开断」候选——按任务书收窄,后四者作词条内行文不独立铸词(终审可扩)。
10. 典章 A 行(DESIGN:74 翻正/P15 行注记/预扣结算词条陈句)由 B 批代收:A 的典章面按任务书「A 留给你的」整批移交本批。

## 遗留

- 半开探活=「下一次真实调用即探活」,无独立合成健康检查 spawn(spec 未钉合成探活;零白烧哲学下取真调用形)。
- events 环上限 20(状态文件尺寸上界),溢出即弃最旧——不外发、不持门,完整留痕在台账行。
- 开断态翻转只在调用时评估(verdict 时点),无后台定时器翻转——无调用的通道冷却后首次调用才探活,属惰性语义(零常驻进程)。
- 生产 breaker.json 首现=首个计数通道失败时(成功 consec=0 零写);CHANGELOG 部署注记按此措辞,spec「首轮自动创建」按真实时点收窄。
