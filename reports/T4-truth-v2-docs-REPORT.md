# T4 报告:truth-v2 批文档收口 + 微修

工单 issue #263 | 分支 `truth-v2-t4`(基线 truth-v2 @ 21bcfd6e)| ADR 0017 | 2026-11-01

批内前置:T1(#260 构建器)/ T2(#261 附录读数腿)/ T3(#262 并排对照+换卷触发+LEG_ORDER 10→12)均已合并进 truth-v2 整合分支。

## 改了什么

| 文件 | 改动 |
|---|---|
| `backend/ipdb/_eval/truth_v2_readout.py` | **P2-1 微修**(T3 评审 P2×4 第 1 条):删 44-48 行 `_MD_EXAMPLE_CAP` 注释+赋值的重复块(重复 3 行),模块行为零改 |
| `CONTEXT.md` | 质量闸门节新增「真值层 v2(自建测量)」条目(插在「蜜罐真值层」与「源池自采样测试集」之间):准入=行为观测/身份段永不进、90 天滚动窗口+月度重切、三闸适配(RIR 随窗滚动/扫描段滤沿用/量闸=组件 ≥1,000)、过渡期主判定权归 Hornet、月报附录节的读数零持门、并排对照+连续两轮 32 锚全绿触发换卷(人裁执行)、S17 趋势重置、真值↔考生互斥红线;全部带 ADR 0017 出处 |
| `CHANGELOG.md` | 「新增 Added」节顶部(最新在前)加 truth-v2 四单伞条中英双份:T1 构建器/T2 附录读数腿/T3 并排+触发+月轮接线/T4 文档收口,含门数字(580/742/8) |
| `NEEDS.md` | 「真值层再锁定策略」行:open → 已闭,闭环指针=ADR 0017 + spec docs/research/2026-11-01-truth-layer-v2-spec.md + 工单 #260/#261/#262/#263(基线=本 worktree HEAD 版本;主检出另有未提交改动,以任务口径重写) |
| `reports/T4-truth-v2-docs-REPORT.md` | 本报告 |

## 为什么(决策记录)

- **词条不入 GLOSSARY**:「滚动窗」「附录读数」两词 2026-11-01 用户裁定不入(路人测试不过);本工单不碰 GLOSSARY.md,CONTEXT/CHANGELOG/NEEDS 行文一律完整短语(「90 天滚动窗口」「月报附录节的读数」),CONTEXT 新条目 `_Avoid_` 行记下该裁定与替换写法,防后人再写回。
- **拒用词闸真咬人(实测)**:首稿在 CONTEXT.md 写「窗界由…锚定」、NEEDS.md 写「自建行为观测语料」,`tests/core/test_glossary_anchors.py::test_no_retired_terms_in_living_docs` 立即抓红(「锚定」NEEDS 语境→锁定/再校准、「语料」→测试集,均改名对照表旧词);改「派生」「测试集」后全绿。CONTEXT/NEEDS 现用「真值层 v2」「测试集」拼写;CHANGELOG 不在闸面(#259 延后批,仓内既有条目本就保留各时代词),故沿用批名「真值语料 v2」(=模块 docstring/ADR 自称),两处拼写分工照仓内先例。
- **CHANGELOG 测试计数勘误**:T1 评审口径「20 测」是 T1 交付时点数;T2 顺手修往该文件补了 1 个负例(test_publish_clears_stale_sentinel_same_month),现文件 21 测——条目按终态写明(21=批内 20+T2 补 1),不沿用会漂移的时点数。
- **P2-1 删法**:保留首份注释+赋值,删第二份(空行+注释+赋值 3 行);该常量仅为报告行可读性上限,无行为面,13 测定向复跑无伤。

## 怎么验证

- P2-1:`tests/eval/test_eval_truth_v2_readout.py` 13 passed(定向);
- 全量:`cd backend && env -u IP_RADAR_EVAL_ENV python -m pytest tests/eval -q` → **580 passed**(与 T3 基线一致);`python -m pytest tests/core -q` → **742 passed, 8 skipped**(与基线一致;含拒用词闸 6 passed);
- `bash -n scripts/monthly_eval.sh` OK;`bash scripts/monthly_eval.sh --dry-run` 12 腿回显(truth-v2 腿带 `--truth-v2-component smallbox=… --ops-allowlist …`、truth-v2-readout 腿在 anchors 后,与 T3 报告一致);
- **文档↔实现字节对齐自查**(逐一对照代码):旗标名 `--truth-v2`/`--truth-v2-component NAME=DIR`/`--truth-v2-readout`/`--ops-allowlist`(__main__.py:543/557/564/568)✓;产物路径 `report_dir/truth-v2/<version>/{ips.txt,meta.json,provenance.json|status.json}` + `model/truth-v2-{build,readout,parallel,swap}-*.json` ✓;阈值 `WINDOW_DAYS=90`/`MIN_COMPONENT_IPS=1_000`(truth_v2.py:38-40)✓;版本名 `truthv2-{anchor:%Y%m}` ✓;腿名 LEG_ORDER 含 `truth-v2`/`truth-v2-readout`(monthly_eval.sh:160)✓;rsync 面 `/opt/ip-truth-capture/→truth-v2-capture/` ✓。
- 纪律注记:codegraph MCP 工具不在本工(子代理)工具允许列表内,读码以 grep/read 后备完成(同 T1-T3 报告注记);真数据/快照零入 git。

## 残留风险

- 无新增;T3 评审 P2×4 其余三条(报告分桶口径 580 实数、级联桩 TRUTH_V2_MODE 保真度注记、快照面 rsync 无 --delete)属 T3 批注记,本工单不重复处置。
- 首次真月轮须人工核 truth-v2-build 真出版(T3 报告已注,跨单残留)。

## 复核命令

```bash
cd /home/huxiao/dev/pi-ip-lookup-tool/.worktrees/truth-v2-t4
git log --oneline -3                          # 基线 21bcfd6e 之上
git status --porcelain                        # commit 后应为空
sed -n '40,48p' backend/ipdb/_eval/truth_v2_readout.py   # _MD_EXAMPLE_CAP 单份
grep -n "真值层 v2" CONTEXT.md && grep -n "真值层再锁定策略" NEEDS.md
grep -n "真值语料 v2" CHANGELOG.md            # 中英双条各 1 处标题
cd backend && env -u IP_RADAR_EVAL_ENV python -m pytest tests/eval -q   # 580 passed
python -m pytest tests/core -q                # 742 passed, 8 skipped
bash -n ../scripts/monthly_eval.sh && bash ../scripts/monthly_eval.sh --dry-run | grep -cE '^==> (model|all|anchors|dsem|agg-share|sinkhole-probe|anchor-readouts|truth-v2|truth-v2-readout|audit|temporal|readout):'   # 12 腿
```
