# 黄金标准 v0(spec #180)验收门逐项自检 — 2026-10-24

- 自检者:#186 收口件 worker(worktree `.worktrees/gs-186`,分支 `feature/gs-186`,基点=集成分支 tip `a62d5966`)
- 方法:五门逐项,真跑留指针,不达标如实标 gap;「无验证手段不得称标准」对自检本身同样生效——跑不了的明标占位,不以转述充数
- 总表:①绿 ②占位=部署后 ops 轮真跑(现据=消融旁证;1 gap 在案=定向票 #188) ③绿(设计局限注记) ④占位=PR #187 首跑 ⑤占位=部署后

## ①「STANDARD.md 每条条文的门挂点可机检存在」 — 绿

- 真跑(worktree 内,2026-10-24):`node ops/agent/standard-check.mjs` = **OK=47 FAIL=0**(条文=14 金标=3 建议=12 挂点=29 原语=22,已有10/半缺9/缺3;终审修单 M2 同步——#186 时点原跑 43 OK/挂点 25,F2 措辞修后挂点升格 47/29,主树复跑核真)
- 核对器语义(#181):每条文门挂点路径存在+`#锚词` fragment 在文核对;死锚/空挂点/伪条目(原语组成表外词)/未标类建议 → 非零退出;嵌套 docs 仓路径禁作挂点(CI checkout 缺席判例)
- 挂 selftest 链 §13(#181 落地时 15 例单测);#185 合并复核复跑仍 43 OK 0 FAIL,终审修单 F2 后复跑 47 OK 0 FAIL(挂点 25→29)

## ②「金锚巡检在 ops 轮真跑一轮全绿:8.8.8.8/114.114.114.114 判 clean」 — 占位:部署后 ops 轮真跑(现据=消融旁证,1 gap 在案=定向票 #188)

- **改判说明(终审修单 F7,2026-10-24)**:原判「绿」降为占位——现有据点均为本地镜像面旁证(#182 首扫+#183 消融复算),不是 ops 轮生产查询路径(ANCHOR_SWEEP 经 OPS_EVAL_PY 桥读生产数据)的真跑读数;ops 轮真跑须部署后首个巡检轮,不以旁证充门(自检方法条款「跑不了的明标占位,不以转述充数」对本门同样生效)

- **#182 真扫件**(合并评论 2026-10-24):真产数据首扫 n_total=19 n_fail=4——8.8.8.8=myip_ms(conf 55)/114DNS=cps+ziyadnz(conf 55,纯 derived 聚合器假印证 corr=True)/1.1.1.1=cps(conf 50)/223.5.5.5=tweetfeed(conf 50);均为 #183 整改落地前预期读数(CHANGELOG 已注记)
- **#183 滤后复算**(消融表 notes/infra-noise-ablation-2026-10-24.md;merger 独立复现=4.5G 数据副本双重建,唯一变量 `IP_RADAR_INFRA_NOISE_FILTER`):8.8.8.8 / 114.114.114.114 / 1.1.1.1 三锚 classifications 全空 = **clean ✓**(排除足迹:myip_ms 1564→1563 / ziyadnz 123107→123106 / cps 31767→31765,条目日志明文)
- **残留如实标 gap**:223.5.5.5 = tweetfeed 指控滤后不变(other malicious/50)——tweetfeed 非 opt-in(宁少算,不开全源扩大化,#183 判例),判 clean 属良性断言源接入阶段独立整改面 → **票 #188 承接**(ADR 0008 决策4 已裁定向)
- 门径口径:spec 验收门原文两锚(8.8.8.8/114DNS)判 clean 达成;19 锚全绿缺 223.5.5.5 一员,gap 在案不藏

## ③「聚合器谱系补录过回放闸门(融合层位等价对照,corroborated 语义复核)」 — 绿(设计局限注记)

- **前提澄清**:derived 谱系早已在册——ziyadnz/cps_collected_iocs `derived=True` + `LINEAGE_CLUSTERS` aggregated-threat 簇(威胁源波 1/3,2026-10-18/19);DERIVED_SOURCES 六员。本批实做=**载入期滤噪**(#183)+**聚合器占比披露**(`_eval/agg_share.py`,`--agg-share` CLI,exit 恒 0 只测量不持门)
- **merger 复算**(#183 合并评论 2026-10-24):worktree 全量 pytest 2164 passed 0 failed;消融独立复现如上②;14 IP 面板仅 3 事故 IP 变化,其余 11 逐字段全等(零外溢)
- **回放闸门对照=位等价 PASS(回放面不可见,设计使然非缺陷掩盖)**:fusion_replay_gate.py 只开已物化 LMDB(`reg.load_db()`+`_reader` 直遍),全程零 rebuild/parse 调用,守的是融合评分内核回归,不覆盖载入面;同镜像改前(25269fd0)/改后(300e8699)逐位一致=预期。查询面消融即补此缺口——本地双重建镜像上回放足迹可见:n_accused 2437→2439、C2 严格口径 2361→2349(单指控 IP 消解 12),C3 双态同 FAIL(预存融合代差,与本批无关)。详据:notes/infra-noise-ablation-2026-10-24.md §「已知局限:回放闸门对本过滤不可见」
- **corroborated 语义复核**:纯 derived 互证仍算 corroborated 的现状注记入 `_types.py:85` / `_merge.py`(grill Q2 2026-10-11 裁定语义,v0 只披露不改;改语义须另票过回放闸门);#185 北星第二腿(谱系去重后 corroborated 精度)以 `dedup_lineage` 同款去重入观测分母

## ④「CI 三腿绿」 — 占位:PR #187 首跑

- worker 无开 PR 面,如实标:CI 三腿以 **PR #187 开出后首跑**为准
- 旁证在案:集成分支 `feature/golden-standard-v0` 连续 4 次 push 后 CI 全绿(25269fd0 / 91ce8f8b / 7bc142d1 / 8004125a,2026-10-24,workflow=CI,conclusion=success);tip `a62d5966`(#185 merge)首跑时点 in_progress——终判以 PR #187 为准

## ⑤「部署后影子轮验证 finding 出口(issue 真开出)」 — 占位:部署后

- 出口三件套(#184)已接线:gh issue(needs-triage)+ apprise webhook(env `IP_RADAR_ALERT_URLS`)+ RETRO 摘要行;`OPS_SWEEP_DRY_RUN` 默认关=生产真发;出口只写不动作(结构性断言钉死)
- **验证时点=部署后首个生产巡检轮 finding>0 触发真开 issue**(当前 demo 站尚未部署本批;影子轮 N≥3 门随 cron 轮累积)。标「部署后」,不以 dry-run/测试面充数

## 附:收口件(#186)三交付自检

| 交付 | 状态 | 指针 |
|---|---|---|
| benign② 后续票 | ✅ 已开 #188(needs-triage) | 三锚点+infra_services 升格定向+223.5.5.5 承接 |
| CHANGELOG 汇总条目 | ✅ 本 commit | 引 PR #187,各票细条已分票入册 |
| GLOSSARY 锚核对 | ✅ 10 词条全活 | 下表;standard-check 47 OK 0 FAIL(F2 后;#186 时点 43 OK)|

### GLOSSARY 本批新铸词条锚核对(逐条真验:文件在场+符号 grep 命中;文档锚=路径+节名 grep 可命中)

| 词条 | 锚 | 验法 |
|---|---|---|
| 载入期基础设施过滤 | `_sources/_infra_filter.py` | 文件在场;#183 消融复算 |
| 发现通道 | tools.mjs(normalizeJinaRead/parseMcpSearchText/parseRss)、prompts/discover-system.md、DESIGN §6 | 三函数 grep 命中;§6=「2026-10-24 修订裁定」节含 web_search 裁定行 |
| 黄金标准(四层) | STANDARD.md、standard-check.mjs、docs/adr/0008(嵌套 docs 仓)、notes 研究件 | 四路全在场;ADR 0008=0008-golden-standard-four-layer.md |
| 回归轨 / 能力轨 | docs/adr/0008、`_eval/anchors.py` | ADR 决策2=双轨语义分立原文;anchors.py 在场 |
| 安静失败 | notes 研究件(工业腿③) | 「安静失败」grep 命中(工业腿→③ AgentOps 节,IEEE Spectrum 2026-04-07) |
| 发现固化 | docs/adr/0008 决策3、notes 研究学术腿① | 决策3=事故固化原文;学术腿①节含 Agentic Auditing 2610.31636 |
| 预扣结算 | pipeline.mjs(budget_truncate) | grep 命中(:54 降级标记+:105-108 预算三闸真面执法) |
| 谱系混淆 | `_logodds.py`(dedup_lineage)、notes(三向对撞表) | 函数 :93 在场;三向对撞表含「源谱系混淆模型」行 |
| finding 出口三件套 | finding-exit.mjs、tools.mjs(ghIssueCreate/GH_WRITE_SUBCOMMANDS)、票 #184 | 两文件符号 grep 命中(tools.mjs :251/:256);票 #184 已闭 |
| emit 守卫 | finding-exit.mjs(runFindingExits) | :96 入口+:114-135 emitting/emitted 相位逻辑在场(终审修单 M4 行号;守卫触发不重写工件,emitted 全稿存活) |

死锚:零。standard-check(STANDARD.md 门挂点面)与本表(GLOSSARY 词条面)互补,双绿。
