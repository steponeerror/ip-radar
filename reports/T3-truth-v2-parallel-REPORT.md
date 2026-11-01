# T3 报告:真值语料 v2 并排对照 + 换卷触发(人裁执行)

工单 issue #262 | 分支 `truth-v2-t3`(基线 truth-v2 @ 248b3903)| ADR 0017 §5 | 2026-11-01

## 改了什么

| 文件 | 改动 |
|---|---|
| `backend/ipdb/_eval/truth_v2_parallel.py` **(新)** | T3 本体:`run_truth_v2_parallel`(并排对照装配)、`run_truth_v2_swap`(换卷触发装配)、`load_anchor_rounds`/`swap_trigger_from_rounds`(纯判定) |
| `backend/ipdb/_eval/truth_v2_readout.py` | ①抽出 `probe_truth_v2_corpus`(语料现场探测单一真源,T2 附录腿与 T3 并排共用,T2 行为零改);②P2-3:k 直方图键数值序;③P2-5:`derived_only_corroboration` 计数+披露行 |
| `backend/ipdb/_eval/__main__.py` | ①`--truth-v2-readout` 扩为一腿三工件(附录+并排+换卷判定);②`--truth-v2` 构建腿补 `model/truth-v2-build-<ts>.json` 摘要件(published/哨兵两态恒落);③P2-4 注释改指实际接线;④help 文本同步 |
| `scripts/monthly_eval.sh` | ①快照面 rsync(`$PROD_HOST:/opt/ip-truth-capture/` → `$DATA_DIR/truth-v2-capture/`,rc 容忍同卷镜像律);②LEG_ORDER 10→12 腿(truth-v2、truth-v2-readout);③check_family +4 写者,报告族 10→12 写者;④注释按准确机制措辞(P2-2)。守卫/master+clean/rc 容忍零改 |
| `backend/tests/eval/test_eval_truth_v2_parallel.py` **(新)** | 14 测(见下) |
| `backend/tests/eval/test_eval_truth_v2_readout.py` | +2 测(P2-3 键序、P2-5 派生簇披露)+ P2-1 autouse env 钉 |
| `backend/tests/eval/test_eval_truth_v2.py` | P2-1 autouse env 钉(同款) |
| `backend/tests/eval/test_eval_monthly.py` | +1 测:S17 换卷扩展(见下) |
| `backend/tests/eval/test_monthly_eval_cascade.py` | cascade 桩补两腿写者(构建腿摘要件+读数腿三工件)+ 腿枚举 10→12 + 1 接线测 |

## 接线说明(怎么跑起来)

月轮链新增一段(位置与依据):快照面 rsync 在卷镜像 rsync 后;构建腿在读数腿前(产物=输入);读数腿在 anchors 判定门后(换卷判定须见本轮 anchors 工件)、历史读者(audit/temporal)前(#233 T4 同律)。读数腿一次调用落三件:

- `model/truth-v2-readout-*.json` — T2 附录(月报嵌节,不变);
- `model/truth-v2-parallel-*.json` — 并排对照:同轮对 **Hornet 现行卷**(`<assets 根>/truth/`,无→no-asset;空→empty-asset,缺层≠0 层)与 **v2 卷**(`report_dir/truth-v2/`,no-corpus/insufficient/published)各实算一遍 **θ̂/k 记分**(同一纯函数 `truth_v2_corpus_readout` + 同一 lookup = 对照口径同源,测试钉键形一致)+ **32 锚回归**(引擎判定门 `run_anchors`,与卷无关→同轮单跑两卷共用一份读数,宁少算:同引擎同轮跑两遍是回声;该块自带 note 声明,测试钉);
- `model/truth-v2-swap-*.json` — 换卷触发判定(下节)。

构建腿输入:`--truth-v2-component smallbox=$DATA_DIR/truth-v2-capture/snapshots --ops-allowlist .../ops_allowlist.txt`(T0 采集器产物);rir/scanner 走缺省 `<data_dir>/`(镜像内,与三闸 ops 面同源)。**采集断供 → 构建腿 rc=2 → 族缺员即死**:真值层断供是采集健康事故,须人见——观测腿在合法缺数据态也落件,不存在「缺件持死」,缺员即死只辖崩溃(P2-2 措辞)。

## 触发器语义(issue #262 验收线原文对齐)

- **输入** = 逐轮锚回归结果(`model/anchors-*.json` 工件,升序;坏件/无信息量形状宽容跳过,`load_anchor_green` 同律);
- **规则** = 最近两轮均 `n_fail==0` 且 `n_total == len(ANCHORS)`(=32;历史形状不符的旧轮不算全绿,依据行明示)→ `trigger_met=true`;
- **输出** = 布尔 + 依据行(逐轮 artifact/generated_at/n_total/n_fail → green/red/形状失配 + 判定行),工件恒落;
- **人裁执行**:工件带 `human_decision` 行(「换卷由人裁执行…本判定不触发任何自动动作」),context 段引两卷指纹仅作复核参照、不入判定输入;`context` 读 Hornet 资产坏件照炸(操作失败族)。
- 换卷执行后(人把 truth 层换成 v2 卷)= 真值指纹变化 → 月报 S17 换版注记点亮 = **趋势重置**(既有机制,扩展测试钉:`test_md_reset_note_corpus_swap_hornet_to_v2`,两造指纹出自真实构建器 v1 三闸 ETL / T1 快照装配)。

## P2×5 处置(#261 评论末段,全做完)

1. **flake 修**:根因实证 = 测试函数体内 `import __main__`(import 期 `REPORT_DIR` 快照解析 env)遇 ambient `IP_RADAR_EVAL_ENV` 非法(如空串,跑过月轮命令的 shell 常见)即假红;修 = 两测试文件各加 autouse `_pin_env` fixture(一处 monkeypatch 覆盖全文件)。验证:`IP_RADAR_EVAL_ENV= pytest` 三文件 47 passed(修复前同条件 10 failed)。
2. **论证措辞**:monthly_eval.sh 两处注释 + 本报告均按准确机制(入族成本=LEG_ORDER/写者计数/文档同步;非缺件持死)。
3. **k 直方图键序**:`dict(sorted(..., key=lambda kv: int(kv[0])))`,测试钉 `"2"` 在 `"12"` 前。
4. **`__main__.py` 指空注释**:改指实际接线(「构建/读数两腿已入 monthly_eval.sh LEG_ORDER(2026-11-01 #262 T3 接线)」)。
5. **θ̂ derived-only 披露**:对照读数喂换卷人裁 → `truth_v2_corpus_readout` 增 `derived_only_corroboration`(k≥2 且指控源全属 `config.LINEAGE_CLUSTERS`,layered F6 同款判定)+ 附录披露行;θ̂ 不折减、计数单列。

## 怎么验证

- TDD:新测试文件首跑 `ModuleNotFoundError: No module named 'ipdb._eval.truth_v2_parallel'`(红);P2-3/P2-5 红证:`git stash push backend/ipdb/_eval/truth_v2_readout.py` → 2 测 FAILED → pop → passed(可证伪性实证)。
- tamper-red:并排对照对篡改 v2 语料件(ips.txt 改写)→ `ValueError: asset fingerprint mismatch` 上抛不装假零(`test_parallel_corrupt_corpus_fails_loud`)。
- 全量:`cd backend && python -m pytest tests/eval -q` → **580 passed**(基线 563 + 新 17:并排 14 + P2×2 + S17 1;含 cascade 桩接线测);`python -m pytest tests/core -q` → **742 passed, 8 skipped**(与基线一致);`bash -n scripts/monthly_eval.sh` OK;`bash scripts/monthly_eval.sh --dry-run` 12 腿+4 新写者校验行全回显。
- 零持门:读数腿缺件/哨兵态三件照写 rc=0(CLI 测钉);坏输入(构建腿 rc=2)不落摘要件=族缺员即死(cascade 桩语义同)。
- 纪律注记:codegraph MCP 工具不在本工(子代理)工具允许列表内,读码以 grep/read 后备完成(同 T1/T2 报告注记)。

## 残留风险

- 快照面 rsync 目标 `/opt/ip-truth-capture/` 与 T0 部署事实一致,但**月轮真跑前未在真月轮里过一遍**(本工单全部离线合成验证;首次月轮须人工核 truth-v2-build 件真出版)。
- honyport 组件接口已预留(`--truth-v2-component honyport=<dir>`),honyport CSV 就绪后加一行接线即可(ADR 0017 §2)。

## 复核命令

```bash
cd /home/huxiao/dev/pi-ip-lookup-tool/.worktrees/truth-v2-t3
git log --oneline -2                          # 基线 248b3903 之上
git status --porcelain                        # commit 后应为空
cd backend && env -u IP_RADAR_EVAL_ENV python -m pytest tests/eval -q   # 580 passed
python -m pytest tests/core -q                # 742 passed, 8 skipped
bash -n ../scripts/monthly_eval.sh && bash ../scripts/monthly_eval.sh --dry-run   # 12 腿回显
# 离线抽验并排+触发(CLI 面, 缺件态 rc=0 三件齐落):
IP_RADAR_EVAL_DIR=/tmp/t3-check python -m ipdb._eval --truth-v2-readout && echo rc=0
# P2-1 flake 修复抽验(ambient 非法 env 下三文件仍绿):
IP_RADAR_EVAL_ENV= python -m pytest tests/eval/test_eval_truth_v2.py tests/eval/test_eval_truth_v2_readout.py tests/eval/test_eval_truth_v2_parallel.py -q   # 47 passed
```
