# fixtures/pipeline — 模型步 canned 回合集(spec #161 P0;复用律:golden 与 selftest 共用同一份)

#170 起本目录=faux 面专用:仅显式传 `--fixtures`/`opts.fixturesDir` 时消费;运行面
(生产/cron 轮无 --fixtures)走真 provider(models.mjs 装载,不读本目录)。

P4(#166)起三模型步全真装配形态:TRIAGE/SYNTH 单发、DEEP 逐假设 `deep/<slug>.json`
(slug = `hidSlug(signal_id)`,faux provider 真 Agent 循环)。微探针 = `seed`/`seeds`
登记表脚本化(registrySeed 判例:预登记结构化返回,G_DEEP 从 transcript 的 `registry_seed`
行重建登记表逐字回引;`≤3/假设` 由 G_DEEP 机检,`fx.seed` 单腿向后兼容 `fx.seeds` 多腿)。
**A 一律**:canned evidence 只给 `{call_id, field}` 选择对,值由宿主回填(deepConsume);

PROBE(P1,#163 起)不消费本目录：feed_freshness=lib.sh 真执行(curl stub),matrix=
tools.mjs `matrixScanCli` 真扫描(OPS_EVAL_PY stub)。ANCHOR_SWEEP(#182)同样不消费本目录：
`anchorSweepCli` 真扫描,OPS_EVAL_PY stub **按旗标分发**(`--anchor-sweep`→罐装锚巡检 JSON,
其余→罐装矩阵 JSON;selftest-pipeline py-matrix 与 golden stubPy 同款)。

## 本 fixture 集的配对契约(改一处须同步另一处)

- **OPS_EVAL_PY stub 旗标分发**(#182):`--anchor-sweep` → 罐装 anchor_sweep JSON。
  selftest-pipeline 面=事故判例形(8.8.8.8=myip_ms 单源/114DNS=cps+ziyadnz 假印证双
  finding,#183 整改前形状——钉「finding 不持门」语义);golden 面=零 finding 基线(钉全绿
  基线)。锚集镜像 anchors.py 扩员后 19 员(形状钉;锚集真源=python,门只验工件内自洽)。

- **curl stub 规则**(golden `stubs.curl_age_days` / selftest-pipeline 同款):
  `cinsscore→220 天` `binarydefense→210 天` `dshield→200 天` `其余→30 天`。
  由此:旗标 = 冻结 3(cinsscore/binarydefense/dshield)。
- **抑制规则 fixture**(`$DOCS_ROOT/ops/rules/suppressions.json`):R1 = suppress
  `{bucket:"frozen", url_shape:"*dshield.org*"}` → 幸存 = 2(cinsscore 高危 + binarydefense 中危),
  抑制 = 1(R1×dshield)。
- **判例树 fixture**:`2026-06-01-golden-aggregator.md` → SYNTH 注入命中 1 条。
- **标源名(P2 #164)**:flags.source = feeds.txt 行内 `# 首词`(ciarm/binarydefense/dshield)。
- **DEEP 逐假设链(P4 #166)**:cinsscore → confirmed(reprobe_get seed,age_days=220 回填);
  binarydefense → refuted(reprobe_ua seed,age_days=5 回填——TRIAGE 读数 210 与深验实测 5
  的差即证伪腿;probe_hint 提示 GET 而模型选 UA 变体=闭集内自由设计探针,合法)。
- **条目链(P4 #166,ITEMIZE 查表零模型)**:cinsscore confirmed → human_ruling severity=high
  (dedup `ciarm|staleness|age_gt_2x_refresh`);binarydefense refuted → digest_ignore
  severity=low 默认折叠(三小裁②;dedup `binarydefense|staleness|age_gt_2x_refresh`);
  真条目落 `$DOCS_ROOT/ops/items/*.md`(ops-items 桥,同 _ops_items 形)。自测逐轮独立
  DOCS 树(mkTree)——条目库真写后轮间在飞面必须隔离。
- **计数链**:manifest `created=2 reopened=0 deduped=0 suppressed=1`;深验行
  `confirmed=1 refuted=1 unresolved=0`。

## 文件清单

| 文件 | 消费步 | 内容 |
|---|---|---|
| `triage.json` | TRIAGE | 2 幸存一条一假设,均 need_deep(prompts/health/triage.md)|
| `deep/https-cinsscore.com-list-ci-badguys.txt.json` | DEEP | confirmed;seed c-cins reprobe_get age_days=220 |
| `deep/https-www.binarydefense.com-banlist.txt.json` | DEEP | refuted;seed c-bd reprobe_ua age_days=5 |
| `deep/golden-track-canned.json` | DEEP 金轨迹 | unresolved 直通(零 need_deep 轮保活,#162 审 P2-2 裁定①)|
| `synth.json` | SYNTH | 三节 canned 报告(计数行 + 深验行 `confirmed=1 refuted=1 unresolved=0`)|
| `shortlist.json` | SHORTLIST(发现轮,#207 T1) | 2 结构化候选(NEEDS.md:L14 rDNS parquet 候选/L17 carrier open;exclusivity=null→ENQUEUE 恒 skip,罐装轮零入队;prompts/discover/shortlist.md) |

P3 桩件 `deep/_stub.json` 已随真开启退役(#166);`review_freeze` 动作词随 confirmed→human_ruling
裁决退役(P4:人裁终局,建议面恒交人)。

预算降级用例(`OPS_PIPELINE_BUDGET_CNY=0.03`):binarydefense 截尾 unresolved(budget),
DEEP 只跑 cinsscore;深验行回算 `confirmed=1 unresolved=1`(自测自带专用 fixtures 目录)。
上限截尾(>3 假设)由 DISPATCH 单元例直构钉住(reason=`unresolved(dispatch_cap)`)。
