# WORKER 报告 — 票 #166(P2-P4:DISPATCH+DEEP+ITEMIZE 真开启,含 A 一律进 G_DEEP)

分支 feature/ops-p2-p4(基=集成分支 89d22bd4,merge feature/p2-health-pipeline = Already up to date);
4 commits:dd5e6cd8(核心)/4be3b234(selftest)/438ada49(golden+README)/前置 de440a53(桥 WIP)。全程只碰 ops/agent/。

## 交付(对照任务书 7 项)

1. **prompts/health/deep.md**:C 稿 §3.3 草案落地(角色/工具闭集表/预算段/输出契约 JSON/硬约束+tell);附录 A 九项对照见下表。
2. **DISPATCH 真实现**:severity 排序 + 假设数 ≤3 截尾(reason=`unresolved(dispatch_cap)` 留痕)+ 预算门 0.05¥ 硬拦(超=截尾降级不终态,归因 `unresolved(budget)`);每假设 bundle 新上下文 = hid/假设全文/≤3 相关判例命中(锚域词表×该假设旗标确定性选锚,onDisk 缺件宁少算)/预算余额(budget_cny)。
3. **DEEP 真装配(P4 仍 faux 零 API)**:逐假设单发(deep/<slug>.json 恢复,_stub.json 退役);微探针闭集 reprobe_get/reprobe_ua/upstream_check = faux 工具(registry_seed 登记表),≤3/假设由 G_DEEP 机检;**A 一律**:输出契约 evidence 只收 call_id+field 选择对,deepConsume 宿主回填值(登记表=transcript registry_seed,单一解析语义 deepSeeds 与门同源),模型复述值原样透传不静默纠正——G_DEEP 写前语义门验三元组逐字=工具结构化返回,不符即门败;verdict 闭集机检;失败信封(ok:false)禁入 evidence=门败(留痕在 transcript 另记)。
4. **ITEMIZE 真实现**:verdict→suggested_action 查表(confirmed→human_ruling 建议复核 / refuted→digest_ignore severity=low 默认折叠·三小裁② / unresolved→human_ruling / watch);十字段查表产出零模型;**条目经 pipeline/ops-items.mjs 桥落真 ops/items 树**(_ops_items.create_item 语义 JS 镜像:在飞零写/终态复开 supersedes 链指/sha1[:10] 内容寻址同 pyJson 拼接/写前校验/原子写);dedup_key 全签(source|probe_class|error_signature)与 P1 探测器同空间——**VERIFY 在飞压制同步换全签**(#164 偏离②收口),折叠族映射 http_401/403 单列→http_4xx→http_5xx→network→download 兜底钉死在 ops-items.mjs(#164 偏离①收口,注释引 _ops_detectors._error_family);frozen→staleness/age_gt_2x_refresh(冻结恒 >2× 刷新周期,与超龄探测器同因同键);**reopened 计数真实现**(同 dedup_key 终态条目重开链指,manifest 四计数=rows 对账)。
5. **金轨迹与真 bundle 不混轮自测**:G_DEEP 既落单向门(need>0 ∧ golden>0=败),selftest 补直构负例(P3 遗留单向)。
6. **DEEP perItem 重试尽降级直测**(#165 审 P2 遗留):坏 fixture→degradedItems unresolved→ITEMIZE 折入 human_ruling 条目→G_DEEP 穷尽(verdicts∪degraded)与 G_SYNTH 回算(confirmed=1 unresolved=1)一致全绿,轮 ok。
7. **共享纪律件指针**:deep.md 末行引用 shared/redaction.md+shared/envelope.md(#165 已建,一行指针不内联)。

## 四门验收(merge 后复跑,先 commit 后跑)

`node ops/agent/selftest-pipeline.mjs` → **PASS=28 FAIL=0**(21→28,新增 7:A 一律违例负例全 faux 轮/DISPATCH 上限截尾单元/在飞全签+终态重开全链 CLI 轮/perItem 降级直测/微探针≤3 负例/失败信封禁入负例/金轨迹混轮负例;五必含面=伪造复述值门败✓截尾降级✓refuted 消化条目✓重开计数✓预算硬拦✓);
`node ops/agent/selftest-contract.mjs` → **PASS=15 FAIL=0**;`bash ops/agent/selftest.sh` → **PASS=101 FAIL=0**;`node ops/agent/golden/run-golden.mjs` → **PASS=9 FAIL=0**(pipeline 用例断言 P4 化:DEEP done+confirmed=1 refuted=1 unresolved=0)。
端到端全 faux 轮三模型步带 DEEP 真 bundle(cinsscore confirmed evidence 回填 220 / binarydefense refuted 回填 5),真条目 2 件落 ops/items 十字段形。

## 附录 A 对照(deep.md 过九项)

| # | 项 | 落点 |
|---|---|---|
| 1 | 角色动词开头/判断编排分离 | 「你是调查员;唯一任务证实或证伪;不裁决不入库不执行」 |
| 2 | 阶段 done-when 机检 | 输出契约段「完成判据(门机检,不信自报)」=G_DEEP 四面 |
| 3 | 反模式带 tell | 「复述读数/想填看起来对的值——停,正是本提示词要消灭的失败模式」 |
| 4 | 信息阶梯 | shared/ 两件按需读;precedent_hits 背景参考;环境可查物不复述 |
| 5 | 结论挂信号选择制 | evidence=call_id+field,宿主回填(A 一律正身) |
| 6 | 工具白名单+只读+预算 | 三微探针闭集表 + 预算段(≤3 次;宿主门拦不算模型失败) |
| 7 | 脱敏+失败信封 | 两 shared 指针 + 「失败信封禁入 evidence,留痕 transcript 另记」 |
| 8 | 判例引用闭合/推荐非阻塞 | DEEP 输出无判例引用面(bundle 注入=DISPATCH 闭合装配);一行结论交人裁,永不自动执行 |
| 9 | AI 声明宿主渲染 | 头注声明,不占模型 token |

## 偏离(相对 C 稿 §3.3 草案/任务书,均已注释钉死)

1. 工具闭集=微探针三只(reprobe_get/reprobe_ua/upstream_check,与 probe_hint 同词表)替换草案四工具(fetch_url/probe_variant/read_file/search_precedents)——任务书明令「闭集 reprobe_get/reprobe_ua/upstream_check,faux 工具」;CLOSED_SETS.deep_tool 同步换轨(新闭集值=本票 spec 变更)。
2. 输出契约 evidence=选择对无 value 键(草案示例含 value)——A 一律终裁「宿主回填值」压过草案示例。
3. confirmed→human_ruling 建议复核替换 P0 占位 review_freeze(任务书明令;动作闭集删该词)。
4. create_item 为 JS 语义镜像非 Python 调用(纪律=只碰 ops/agent/);digest 已字节对齐 json.dumps(sort_keys+ensure_ascii=False)拼接,YAML 渲染=受控子集(PyYAML 可往返),非跨语言字节镜像。
5. OPS_ROOT 从模块常量改为按调用 env 派生(opsRootOf)——C 稿 §5.2「全部从 DOCS_ROOT 派生」的忠实化,兼作自测逐轮树隔离缝。

## 残留与风险

- feeds.txt 6 行无 `#` 注解:回落 host(含点)撞 dedup_key.source 形状正则 → 该源旗标 ITEMIZE=verify_failed 终态宁响亮(P5 部署面补注解即可)。
- replay 边缘:原轮 manifest 缺席(ITEMIZE 半程崩溃重放)走桥内文件回声;原轮 manifest 在场则行级回声零写(审计重放不改生产条目面);canned fixtures 对演化中的树天然陈旧(C 稿 §4.5 模型步不保证位等价的既定语义)。
- dry replay 的 G_ITEMIZE 对「人裁后终态的同签条目」理论上会假阳性(树演化 vs 原件 manifest)——现行门只查文件在场+同签,不查 status,已避开主面。
- 生产段验收(人为停真源→条目经四键走查,票 #166 验收剧本)= 部署后动作(P5),不在 faux 面。

推荐下一步:reviewer 终审(重点=ops-items.mjs 与 _ops_items.py 语义对拍、G_DEEP 门集、deep.md 附录 A 执审)→ 并回集成分支 → P5(#167 RETRO+cron+恢复)。
