# DP-T2 交卷报告 — #208 四门强化 + span 级回引 + 哨

工位:`.worktrees/dp-t2`(分支 `feature/dp-t2`,基 = 集成分支 `feature/discover-pipeline-v0` @ `4b1c8720`,无 merge 需求)
纪律:40min 墙两段(原跑被截断→续作存量入库 `ae96a298`);禁 push 已守;dp-t1/dp-t3 worktree 零触碰。

## 交付件(对照任务书 1-5)

1. **spanMatcher 纯函数**(新 `ops/agent/pipeline/citation.mjs`):`(quote, evidenceText)→bool`,
   基律=朴素 `String.includes` 逐字律(零归一化零 trim)+ **URL 边界律**(自铸判例):quote 中
   URL 记号须在 evidence 中**定界在场**(相邻字符∉ URL 字符集,逗/分号=散文定界符)——杀前缀子串
   (`https://ip.thc` ⊂ `https://ip.thc.org`)而恰等仍收。
   三负例判例全钉:**幽灵 URL**(引不存在的 URL)/ **半真 URL**(前缀子串+超集串两侧)/ **改写引文**
   (大小写/标点改写)全 must-reject;恰等+真 span must-accept;空串/非串拒。
   同文件:`scanEvidenceFace(scan, ptr)` 三形解析(见自决③)、`ptrForm` 本地分类器、
   `canonicalJson` 稳定序列化;`containsExactString` 同律复刻(T3 未导出,单源判例注记)。
2. **G_SHORTLIST 升格**:T1 形状检查→span 级语义门。7 键闭集形状(name/quote/evidence_ptr/source_channel
   串;url null|http(s);exclusivity null|[0,1];未知键拒)→ `scanEvidenceFace` 解析 → `spanMatcher`
   逐字对账;门败 reason 带候选名+证据指针;degraded 串合法(span 面 N/A,零候选合法)。
3. **G_MEASURE 强化**:宿主重算三面——排他率透传(d3 行值 ≡ shortlist 候选值 ?? null)、存在性计数
   (`evidence_local_ok` 经 `scanEvidenceFace` 重算,不一致=FAIL 带两值)、hold_n(原有)。行须按名映射到
   shortlist 候选(无源读数=FAIL)。
4. **G_SCAN/G_ENQUEUE 查漏**:G_SCAN += 条目自洽(needs 指针 `^NEEDS\.md:L\d+$` + text 非空;
   registry 指针 `^backend/ipdb/_sources/<stem>\.py$` + name≡stem)。G_ENQUEUE += 入队行三判据复算
   (evidence_local_ok===true ∧ exclusivity≥0.25 ∧ control_executable===true,违者 FAIL 带数字)
   + **穷尽哨**(每 shortlist 候选必在 enqueued∪skipped——证据永不灭失)。GATE_SEQUENCE 派生注册面
   零手抄(selftest-pipeline ~L176 双表并集双射哨既有,已核在场)。
5. **selftest/golden 扩例**:selftest-pipeline 四门篡改红期例(每门一例真红:G_SCAN 指针自洽/
   G_SHORTLIST 标点改写 U+FF08 半角(→全角(/G_MEASURE 数字漂移/G_ENQUEUE 幽灵入队;未篡改原轮四门
   全绿对照)+ spanMatcher 三负例例 + scanEvidenceFace 三形例 + SCAN 真面直调例(registry≥40 +
   needs text 面 + 真面工件过 G_SCAN);golden 新例 `pipeline_discover_full_faux`(真跑),run-golden
   轮型/roundId/门数从用例+轮型定义表派生(缺省=健康,位等价);standard-check 挂点行=T4 未动。

## 自决(裁定记录)

- **①SCAN faux 缝**:`steps.mjs` SCAN 增罐装宇宙缝(modelFace==="faux" ∧ fixturesDir 有
  `d1-scan.json` → 轮工件候选宇宙=fixture 钉死)。理由:span 门把罐装 quote 与真仓 NEEDS.md 文本
  耦合,仓文演进会破门 CI 假红;faux=罐装 I/O 判例(#170);真轮(缺省)零影响。真面由「SCAN 真面
  直调」例独立钉。
- **②needs 条目 text 面**:真面 SCAN needs 行增 `text`=原文行快照(registry 行结构性无 text)。
  理由=证据永不灭失:门重放从轮工件回算,quote span 对账面必须入轮工件(G_VERIFY 快照判例同律);
  现薄形(name/url/ptr)无引文可引。
- **③T3 文件不动 + 双协议分立**(父会话裁定确认):`discover-candidate.mjs` 的
  validateCandidate 保严律(url 必填/exclusivity 必填/两形指针)——那是独立候选面(PROPose 卡)的必填律;
  发现轮回引面(needs 行合法无 URL/null 排他率/透传指针)在 G_SHORTLIST 门面自检 + citation.mjs
  `ptrForm` 本地三形分类器(url/artifact=复用 T3 导出面,scan 形=透传 repo 路径/行锚)收口。两闭集
  分立非冲突;selftest T3 钉例(url:null 拒等)未动,加注记。
- **④URL 边界律自铸**:纯 includes 律下半真 URL 前缀子串会假绿,定界判(邻字符∉URL 字符集)杀之;
  判例注记在 citation.mjs 头注。
- **⑤T1 工件闭包例改指罐装计数**(registry 1/needs 2 + text 面),原真面断言(≥40)移至「SCAN
  真面直调」例——职责分立:闭包例钉 faux 轮固定面,直调例钉真面扫描。
- **⑥golden 09 断言初值 2/1/900 为我臆写,首跑红(实际缺省 30/5/3600/0.05)即改钉真缺省面**——
  golden 钉缺省值不动旋钮,红即纠。

## 验收门(全绿)

| 门 | 数字 | 基线 |
|---|---|---|
| selftest-pipeline | **100/0** | 96 不降 + Δ4 新例(spanMatcher 三负例/scanEvidenceFace 三形/四门篡改红期/SCAN 真面直调) |
| selftest-t4 | **63/0** | 63 ✓ |
| selftest-contract | **18/0** | 18 ✓ |
| golden(真跑 run-golden) | **10/0** | 9+Δ1(`pipeline_discover_full_faux`)✓ |
| standard-check | **47/0**(挂点 31) | 47 不降 ✓ |
| node --check | 全过(citation/gates/steps/selftest-pipeline/run-golden) | ✓ |

红测真红记录:实现前首跑 94/6(citation 缺失/闭包计数/真面 text/GATES 作用域)+ 95/5(透传形三形外
主根因)→ 修复后 100/0;四门篡改例在无强化门实现期即红(gates.mjs 改前 G_SHORTLIST 篡改例真红已录)。

## commit 链(基 4b1c8720)

- `afff7252` 占位(#208 开工)
- `ae96a298` 续作存量入库:citation.mjs + gates.mjs 四门 + steps.mjs 三件 + fixture + selftest 新例
- `3d1ab1f5` golden 扩发现轮用例(run-golden 轮型派生)
- `b042de51` shortlist prompt span 律名面(幽灵/半真/改写三门败——faux 不读 prompt,真轮模型需此告知)

## 与 T1/T3 接线对拍

- **T1**(dp-t1-report 接线协议):①d1 形状微扩(text 键新增)——G_SCAN 自洽门兼容两代工件
  (text 非空串才查,结构性 registry 行无 text 合法);②T1 自测「全 faux 六步」原断言未破(计数面
  改指罐装已在自决⑤注记);③**回放注意**:T1 时代已存的发现轮工件(若 d1 无 text、d2 quote 非逐字)
  过不了新 G_SHORTLIST/G_SCAN——生产尚无发现轮(T1 #207 起未跑真轮),无回放损失。
- **T3**(dp-t3-report 接线协议):①discovery-host 的 `filterCandidatesByEvidence`(T3 纯函数面)
  与本轮 `scanEvidenceFace` 分工——前者=web 三工具读数的证据存在性(独立候选面),后者=发现轮
  d1 宇宙回引面(轮工件重放律);②T3 validator 严律保留,双协议分立(自决③);③T3 web 渠道接线
  (channels.web placeholder)留 PR3a,本轮零动;④T3 的 `candidateSourceSlug`/queue 卡行在 G_ENQUEUE
  穷尽哨语义下兼容(enqueued 行 source=slug ↔ shortlist name 小写化映射已核)。

## 残留/移交

- T4(STANDARD.md 挂点行典章)未动——四门注册面 GATE_SEQUENCE 派生零手抄已核,挂点行由 T4 录。
- 真轮首跑时 prompts/discover/shortlist.md span 律已名面落字;模型实测改写率待冷启动验收面。
- golden `pipeline_discover_full_faux` 的 09 断言钉的是**缺省旋钮面**(30/5/3600/0.05),旋钮改缺省
  须同步此例(与 health 例同维护律)。
