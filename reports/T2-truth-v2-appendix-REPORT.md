# T2 报告:真值语料 v2 月报附录读数腿(零持门)

工单 issue #261 | 分支 `truth-v2-t2`(基线 truth-v2 @ 20198603)| ADR 0017 §4 | 2026-11-01

## 改了什么

| 文件 | 改动 |
|---|---|
| `backend/ipdb/_eval/truth_v2_readout.py` **(新)** | 附录读数腿本体:`latest_truth_v2_dir`(语料现场探测)、`truth_v2_corpus_readout`(纯计算)、`run_truth_v2_readout`(CLI 装配+工件落盘)、`render_truth_v2_appendix`(附录节渲染) |
| `backend/ipdb/_eval/__main__.py` | ①新增 `--truth-v2-readout` 旗标与 handler(load_db 后,观测腿区);②`run_readout` 读最新腿工件 `render_truth_v2_appendix(load_truth_v2_readout(out_dir/"model"))` 嵌月报 |
| `backend/ipdb/_eval/monthly.py` | ①`load_truth_v2_readout`(最新件读侧,load_anchor_green 同律);②`compose_monthly_md` 新可选参 `truth_v2_lines`(缺省 None 不出,schema-stable;run_readout 恒传) |
| `backend/ipdb/_eval/truth_v2.py` | **T1 评审 P2-1 顺手修**:publish 分支前置 `(vdir/"status.json").unlink(missing_ok=True)`——同月先哨兵后过闸,版本目录终态只留出版三件 |
| `backend/tests/eval/test_eval_truth_v2_readout.py` **(新)** | 11 测(见下) |
| `backend/tests/eval/test_eval_truth_v2.py` | +1 测(P2-1 负例) |

**CI 零改、scripts/monthly_eval.sh 零改**:`git status` 仅有上述 6 文件;不碰 `.github/`、不碰月轮壳、不碰 LMDB/rebuild(纯 eval 侧文件语料 + 引擎只读查询)。

## 设计:附录腿算什么、怎么算

**读数口径(全部既有语义,零新机制)**:
- 成员指控判定 = lookup 载荷 `layered._accusing_sources`(canary/sentinel 同款借道,指控章单一口径);
- k_all / k_nonhoneypot 双报沿用 v1 truth 层口径(`layered_readout` 同律:蜜罐方法学源剔除 = `config.HONEYPOT_METHODOLOGY` ∪ 源属性;ADR 0017 §8「双报保留」);
- **θ̂ 试算** = Beta(1,1) 后验均值 `(k+1)/(n+2)`(Laplace 平滑,dsem theta0 同款先例):逐源 n = 该源在 v2 语料上的指控成员数,k = 其中还有 ≥1 个其他池源同指控的成员数;池级 θ̂ = (印证≥2源成员数+1)/(命中成员数+2)。**与记分卡 θ 分立**:记分卡是市场先验 ρ + ctype 对口径(model.estimate),附录是平坦先验、无 ctype 维、措辞永远「θ̂ 试算」;零命中 → `value=None`(无证据≠0.5,无话不虚构);
- **独有指控核查** = k_all==1 的语料成员归因到唯一指控源(「独证」,逐成员清单留工件,报告行点名计数+示例≤5);k_all==0 = **全池无指控成员**(已确证攻击行为、池内零指控)——对真值语料这是池盲区的诚实读数;
- asof 锚 = 语料 `created_at`(T1 锚日派生),layered truth 层 T10 同律,读数对齐语料时点不随引擎现态漂移。

**工件结构** `model/truth-v2-readout-<ts>.json`(agg-share/anchors 报告族同形):kind/status/eval_env/gate 声明 + corpus(版本/指纹/窗/锚日)+ readout(命中/k 双直方图/θ̂ 池级+逐源/独证清单/盲区清单/asof)。缺件与哨兵态**也落件**(读数留痕:腿红不持门、工件照写的观测腿律)。

**附录节四态措辞分立**(读者可区分「没工件/没语料/没过闸/出版读数」):
1. 无 `truth-v2-readout` 工件 → `N/A(无 truth-v2-readout 工件;月轮先跑 …)`
2. 无 truth-v2 语料件 → `N/A(无 truth-v2 语料件——先跑 --truth-v2 构建器…)`
3. 组件闸哨兵态 → `N/A(语料哨兵态 insufficient: smallbox:999/1000 未过组件闸, 窗 …)`(引用哨兵件自己的事实,不编)
4. 出版 → 语料指纹/窗/读数源引用 + 命中与 k 双报 + θ̂ 试算 + 独有指控核查 + 逐源表;行内自带「主判定权仍归 Hornet, ADR 0017 §4」

## 零持门三重实证

1. **无 gating exit 码**:handler 对缺件/哨兵态/出版三态都正常 `return`(rc=0);测试 `test_cli_missing_and_sentinel_rc_zero` 逐态钉住(main 不 raise SystemExit)。坏出版件(指纹失配)原样上抛 = 操作失败族,不装假零(2026-10-10 假零判例,sinkhole_probe 同款立场)——`test_corrupt_published_corpus_fails_loud` 红证;「缺件≠坏件」两类失败分立。
2. **不进回归族**:判定门 `--anchors` 的纯计算 `run_anchors` 在语料件在场/删除两态下逐字节同值(`test_anchors_regression_unaffected_by_corpus_presence`,行为面);结构面 anchors/model/suite 零 truth-v2 引用。
3. **CI 零改**:本分支不碰任何 CI 面;全套件跑绿即证(`tests/eval` 563 passed + `tests/core` 742 passed, 8 skipped)。

## 附录读数与主判定分离(负例验收线)

架构:**腿与月报装配面都只读 `truth-v2-readout` 工件,永不直读 truth-v2 语料件**(northstar 读 anchors 工件同律:件先于月报落盘)。两个负例测试钉住:
- `test_main_readout_md_bytes_unchanged_by_corpus_deletion`:两报告目录各先跑附录腿,其一删掉语料件后 `run_readout` 重跑 → **月报逐字节相等**(附录工件已在,主判定输出对语料件在场性零依赖);
- `test_appendix_section_isolated_from_main_verdict_sections`:无工件时附录节渲染 N/A,且**附录节之前的全部月报内容**(主判定各节)与有工件时逐字节相同——附录只长在附录节。

## 月轮接入方式:为什么本轮不加 monthly_eval.sh 腿

**选择:独立命令 + 月报汇编时纳入(northstar 先例),monthly_eval.sh 本轮零改。** 论证:

1. **加了反而违零持门**:monthly_eval.sh 的报告族纪律是「写者工件缺席即族缺员即死」(check_family + 缺员即死)。本腿的合法读数态包含「无语料件/哨兵态」(组件闸不足期可能持续数月,ADR 0017 §4 明文「不足期 v2 只出附录读数」)——若入族,一段无数据期会持死整条月轮管线,直接违反「腿红不持门、工件照写」验收线;若入 LEG_ORDER 而不入族,则「报告族 10 写者」计数与族员语义失配,须改文档约束反而扩大改动面。
2. **上游构建腿不在场**:附录腿的输入 = T1 构建器产物,而 `--truth-v2`(快照目录/rir/scanner 路径)本身尚不在 LEG_ORDER——快照数据路径(服务器 /opt/ip-truth-capture vs 本地 dev)是 T0→T3 的运维决策。现在单加读数腿 = 每月恒渲染 N/A 的空转腿。
3. **T3 才是接线点**:T3(并排对照+换卷触发)要求同轮月轮双语料(Hornet/v2)并排实算、32 锚回归双跑——届时构建腿+读数腿+对照腿一起入 LEG_ORDER,check_family 写者计数与文档一次同步,避免两次改同一约束。

**月轮怎么带上它(现行,直到 T3 接线)**:月轮的 `--readout` 腿之前手动(或包一层脚本)跑两条命令,工件落 `backend/data/eval/monthly/model/`,月报自动嵌附录节:
```bash
cd backend
IP_RADAR_EVAL_ENV=monthly python3 -m ipdb._eval --truth-v2 \
  --truth-v2-component smallbox=<周快照目录>   # T1 构建器(先跑,产物 truth-v2/<version>/)
IP_RADAR_EVAL_ENV=monthly python3 -m ipdb._eval --truth-v2-readout  # 本腿(读最新出版/哨兵件)
IP_RADAR_EVAL_ENV=monthly python3 -m ipdb._eval --readout           # 月报嵌附录节
```
没跑前两条时月报附录节渲染 `N/A(无 truth-v2-readout 工件)`——缺读数不静默省略、不虚构,月报其余部分字节不变(负例测试钉住)。

## T1 评审 P2 处置

- **P2-1 已修**:publish 分支前置 `unlink(missing_ok=True)`;负例测试 `test_publish_clears_stale_sentinel_same_month`(同月 999 哨兵 → 补 1 IP 过闸 → 版本目录只剩 ips.txt/meta.json/provenance.json)。
- **P2-2/P2-3 不改,作为读数侧已知约束**:P2-2(provenance 嵌输入绝对路径,跨路径重跑 provenance 字节不一致)——本腿读数侧只消费 `meta.json` 指纹+锚日,不读 provenance,不受影响;对照口径照评审结论「比 sha256 pin 不比 provenance 字节」。P2-3(parse_snapshot_csv 对表头前非注释行静默跳过)在 T0 格式下不可达,不动。

## 验证

- TDD 先红后绿:新测试文件首跑 `ModuleNotFoundError: No module named 'ipdb._eval.truth_v2_readout'`(红),P2-1 测试首跑 `FAILED test_publish_clears_stale_sentinel_same_month`(红,目录里 status.json 残留),实现后全绿。
- `cd backend && python -m pytest tests/eval -q` → **563 passed**(基线 551 + 新 12:读数腿 11 + P2-1 1)。
- `cd backend && python -m pytest tests/core -q` → **742 passed, 8 skipped**(与基线一致,零回归)。
- tamper-red 两枚:①语料件篡改(ips.txt 改写)→ `ValueError: asset fingerprint mismatch` 上抛不装假零;②P2-1 负例(哨兵残件被过闸重跑清除)。
- 渲染目检:出版/哨兵/缺件三态附录节输出人工核过(措辞、数字、表列)。
- 纪律注记:codegraph MCP 工具不在本工(子代理)工具允许列表内,读码以 grep/read 后备完成(纪律要求的注明项)。

## 残留风险

- 附录工件被腿外篡改(合法 JSON 假数字)会被月报原样嵌入——artifact-trust 边界与 northstar/anchors 工件同(评审可后续加工件自校验,不在本工单面)。
- 月轮未跑腿时月报嵌**上一轮**最新件(文件名 ts 可见,读数源引用行自带时戳,陈旧可辨但不自动告警)。

## 复核命令

```bash
cd /home/huxiao/dev/pi-ip-lookup-tool/.worktrees/truth-v2-t2
git log --oneline -3                       # 基线 20198603 之上
git status --porcelain                     # 只应有本报告相关文件(已 commit 后为空)
cd backend && python -m pytest tests/eval tests/eval/test_eval_truth_v2_readout.py tests/eval/test_eval_truth_v2.py -q   # 563 passed
python -m pytest tests/core -q             # 742 passed, 8 skipped
# 零持门抽验(缺件 rc=0 + N/A 渲染):
IP_RADAR_EVAL_DIR=/tmp/t2-check python3 -m ipdb._eval --truth-v2-readout; echo "rc=$?"   # rc=0(需真 registry,生产数据面)
```
