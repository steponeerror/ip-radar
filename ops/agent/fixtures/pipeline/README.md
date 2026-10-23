# fixtures/pipeline — P0 模型步 canned 回合集(spec #161 P0;复用律:golden 与 selftest 共用同一份)

P0 模型步(TRIAGE/DEEP/SYNTH)经 `pipeline/faux.mjs` 用 pi-ai fauxProvider 跑真 Agent 循环,
回合资次脚本化于本目录(`turns` = AssistantMessage 形 JSON;DEEP 逐假设 `deep/<slug>.json`,
slug = `hidSlug(signal_id)`)。需网络的测量腿走 `seed`(registrySeed 判例:预登记结构化返回,
G_DEEP 从 transcript 的 `registry_seed` 行重建登记表逐字回引——golden exclusive_probe 同型)。

PROBE(P1,#163 起)不再消费本目录:feed_freshness=lib.sh 真执行(curl stub),matrix=
tools.mjs `matrixScanCli` 真扫描(OPS_EVAL_PY stub;旧 `matrix.json` 罐装件已删,回放基线
=轮次目录里已产的 `01-probe-matrix.json` 前置复制件)。

## 本 fixture 集的配对契约(改一处须同步另一处)

- **curl stub 规则**(golden `stubs.curl_age_days` / selftest-pipeline 同款):
  `cinsscore→220 天` `binarydefense→210 天` `dshield→200 天` `其余→30 天`。
  由此:旗标 = 冻结 3(cinsscore/binarydefense/dshield)。
- **抑制规则 fixture**(`$DOCS_ROOT/ops/rules/suppressions.json`):R1 = suppress
  `{bucket:"frozen", url_shape:"*dshield.org*"}` → 幸存 = 2(cinsscore 高危 + binarydefense 中危),
  抑制 = 1(R1×dshield)。
- **判例树 fixture**:`2026-06-01-golden-aggregator.md`(golden `writePrecedents` 同款,正文含
  health 检索词)→ SYNTH 注入命中 1 条,canned 报告引用它过闭合校验。
- **标源名(P2 #164)**:flags.source = feeds.txt 行内 `# 首词`(lib.sh `extract_feed_urls -t`;
  cinsscore 的 URL 标源名 = `ciarm`,binarydefense/dshield 同名)——在飞不重问与抑制规则
  `source` 谓词按它对齐 `_ops_items.dedup_key.source`。在飞面真源 = `$DOCS_ROOT/ops/items/*.md`
  (_ops_items 树,frontmatter status/dedup_key;旧 `in-flight.json` fixture 已退役)。
- **计数链**:manifest `created=2 reopened=0 deduped=0 suppressed=1`(cinsscore=confirmed
  review_freeze;binarydefense=refuted digest_ignore 恒 low,附带三小裁②)。

## 文件清单

| 文件 | 消费步 | 内容 |
|---|---|---|
| `triage.json` | TRIAGE | 2 幸存一条一假设,均 need_deep(P3 起配真提示词 prompts/health/triage.md)|
| `deep/_stub.json` | DEEP 桩 | P3 桩 canned 回合:全部 verdict=unresolved 直通(#166 真开启时恢复逐假设件)|
| `synth.json` | SYNTH | 三节 canned 报告(计数行 `created=2 reopened=0 deduped=0 suppressed=1` + 深验行 `confirmed=0 refuted=0 unresolved=2`)|

P0 时代的逐假设 deep 件(cinsscore confirmed/binarydefense refuted,registrySeed 演示)已随 P3 桩退役;
A 一律(evidence call_id+field 逐字回引登记表)机制面改由 selftest-pipeline G_DEEP 单元例直构工件钉住。
零 need_deep 轮(空转金轨迹,#162 审 P2-2 裁定①)不经本目录 canned 件:自测以专用 fixtures 目录提供
need_deep=false 的 triage 件与 unresolved=0 的 synth 件(见 selftest-pipeline 金轨迹例)。

在飞面(P2 #164)不经本目录:自测把真形条目 .md 写进各自 DOCS tmp 的 `ops/items/`
(见 selftest-pipeline Case A;status active/snoozed = 在飞,done/dismissed 终态不算)。

预算降级用例(`OPS_PIPELINE_BUDGET_CNY=0.03`):2×0.016>0.03 → binarydefense 截尾
unresolved(budget),DEEP 桩只跑 cinsscore;manifest created 仍=2。canned synth 报告的深验行
unresolved=2 与该场景回算一致(1 桩 unresolved + 1 截尾 unresolved),G_SYNTH 抽检面同过。
