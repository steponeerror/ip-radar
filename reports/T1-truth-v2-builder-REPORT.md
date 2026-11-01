# T1 交付报告:真值语料 v2 构建器(truth-v2 批,issue #260)

日期:2026-11-01 | 工单:GitHub issue #260 | 决策:ADR 0017(Accepted)
分支:`truth-v2-t1`(基于整合分支 `truth-v2` = master a539c8f8)

## 改了什么

### 新增 `backend/ipdb/_eval/truth_v2.py`(核心交付)

真值语料 v2 构建器:自建行为观测输入 → 90 天滚动窗版本化真值资产。
纯文件 IO,不碰 LMDB/rebuild,运行期零网络,产物只在 eval 语料目录
(互斥红线 ADR 0017 §7:真值数据永不入池/private_sources)。

管线与验收线逐条对应(issue #260):

| 验收线 | 落地 |
|---|---|
| 清洗链 | `_clean_component`:90 天窗 → ops 白名单(`load_ops_allowlist`,文件传入默认空,一行一个 v4,# 注释跳过,坏行 fail-loud)→ RFC1918/保留段剔(`apply_reserved_filter`,判定=not `is_global`,覆盖 10/8、172.16/12、192.168/16、环回、链路本地、CGNAT 100.64/10、文档段、240/4、广播)→ 扫描段滤(复用 `layer_builders.scanner_ranges_prefixes` 首列机制 + `truth_layer.apply_scanner_filter`,缺件自然 raise FileNotFoundError 不静默缩水)→ RIR 滚动 cutoff |
| 90 天滚动窗+月度重切 | `window_bounds`:`WINDOW_DAYS=90` 含两端;锚日=全组件最新快照日(数据派生);`version="truthv2-YYYYMM"` 月度重切口径 |
| 窗边界归属 | 窗起点当日观测属本版,前一天属上一版;端到端 fixture 钉住(2026-08-04 进 / 2026-08-03 出) |
| RIR 滚动 cutoff | `cutoff = 窗起点`(复用 `truth_layer.apply_rir_filter` 逐字「≥cutoff 剔」边界,ADR 0017 §6 推广 ADR 0002 §2);rir 数据面复用 `parse_rir_delegated` 直读 `rir_delegated/{reg}.txt`;窗起点当日分配剔、前一日保留(boundary fixture);空 rir 面 ValueError(闸静默失能=排除面无声缩水) |
| 组件闸 ≥1,000 | `MIN_COMPONENT_IPS=1_000`(ADR 0017 §4):单组件清洗后独立攻击 IP 数过闸才入装配;不足=该组件不装配;**全部组件不过闸 → 只写哨兵 `status.json` 不 raise**(含逐组件逐级计数,零资产文件落盘) |
| 版本化+双 pin | 过闸 → `ips.txt`+`meta.json`(`assets.save_asset`,S12 版本化,fingerprint 闸)+ `provenance.json` sidecar(逐输入件 sha256:周快照/rir 五件/scanner csv/白名单;sinkhole provenance 先例)。`kind="truth_v2"`(assets.KINDS 同步扩展) |
| 同输入重跑字节级一致 | `created_at`/`generated` = 锚日派生而非墙钟;文件读序 sorted;测试钉住三件产物逐字节相等,真数据面 diff 复证 |
| CLI | `python -m ipdb._eval --truth-v2 --truth-v2-component smallbox=<dir> [--ops-allowlist F] [--scanner-csv F] [--rir-dir D]`;产物落 `report_dir()/truth-v2/<version>/`(report_dir 约定);纯文件面前置于 load_db(--temporal 同律);坏输入族 §5.2 信封 rc=2(--matrix-scan 先例);不过闸=合法读数 rc 恒 0 |
| 测试全离线 | 全部合成 fixture(快照 CSV 逐字照 T0 采集脚本头格式、合成 rir 五件、合成 scanner csv),不碰真快照、零网络 |

**honyport 接口预留**:组件=命名目录(`--truth-v2-component name=dir` 可重复),
honyport CSV 就绪后同名机制并入,零代码改动(ADR 0017 §2)。

**刻意不做的**:v1 的 `MIN_RIR_RANGES=10_000` 段闸不套用(ADR 0017 §6:量闸以
组件 1,000 取代 Hornet 的 10,000 段闸);不写 monthly/keysets(T2/T3 范围);
不造新词(GLOSSARY 两词提案已被否,行文用 ADR 0017 原短语)。

### 改动既有文件(最小面)

- `backend/ipdb/_eval/assets.py`:KINDS 加 `"truth_v2"`(一行 + 注释;save_asset
  写侧闸需要,`load_asset` 本就不校验 kind,零既有行为变化)。
- `backend/ipdb/_eval/__main__.py`:argparse 加 4 旗 + `--truth-v2` handler
  (置于 `--temporal` 之后、registry 装载之前;不触 DB)。

### 新增测试 `backend/tests/eval/test_eval_truth_v2.py`(20 测)

## 为什么这样设计(关键裁决与出处)

1. **锚日从数据派生而非墙钟**:「同输入重跑字节级一致」的硬前提。墙钟锚定
   会让跨日重跑同输入产出不同窗界/版本;最新快照日锚定让窗界随证据走,
   周快照迟到时窗不空转。
2. **RIR cutoff 边界沿用 v1 逐字语义**(≥cutoff 剔,cutoff=窗起点):ADR 0017
   §6 明说「ADR 0002 §2 推广到滚动窗」=推广既有闸,不重定义边界;窗起点当日
   分配属「新近重分配证据」剔,前一日保留(boundary 测试钉死)。
3. **组件闸计数=清洗链终局成员数**:闸保护的是「可入装配的独立攻击 IP 数」,
   不是原始计数——清洗后仍需 ≥1,000 才有统计功率;逐级计数全落 provenance
   (证据不灭失,败因可审计)。
4. **清洗后集合语义与顺序无关**(全为减法),顺序取时间→已知良性→不可路由→
   扫描段→重分配,便于逐级审计;`宁少算`不回补。
5. **哨兵件而非 raise**:ADR 0017 §4 原文「不足=不装配+哨兵状态,不 raise」
   ——采集断供是运营态不是异常;Hornet 留任当安全网。
6. **版本目录 `truth-v2/<version>/` 累积**:月度重切历史版本不覆盖,换版审计
   与趋势重置(T3)有料可查。

## 怎么验证

### 离线测试(TDD:先红后绿)

- 红:测试文件先落,`ImportError: No module named 'ipdb._eval.truth_v2'`
  收集失败(red 证)。
- 绿:`pytest backend/tests/eval/test_eval_truth_v2.py` 20 passed;全量
  `backend/tests/eval` 551 passed(基线 531 + 新增 20);`backend/tests/core`
  742 passed(合计 1293 passed, 8 skipped)。ruff 对新增/改动四文件 All checks
  passed(存量 __main__.py 一处 E731 非本批引入,不动)。

### 真数据面冒烟(只读,产物落 /tmp,零 git 污染)

```
truth-v2: published version=truthv2-202611 members=1807 window=2026-08-04..2026-11-01
  component-gate(≥1000): smallbox:pass(1807)
```

- 输入:T0 首份快照 `dev/truth-v2/snapshots/2026-11-01.csv`(1,822 IP)+
  生产镜像数据面(.eval-prod-data 的 rir 五件 262,413 段 + scanner csv
  29,094 前缀)。
- 清洗链读数:raw_unique 1822 → 扫描段滤剔 15 → 保留段 0 → rir 0 →
  **1807 成员**,组件闸过;420,039 次爆破尝试计入 provenance。
- **字节级一致复证**:同真输入两次跑进两个 EVAL_DIR,`diff -r` 零差异。

### 测试数与红证清单

- 新增 20 测,其中**负例/tamper 红证 6 枚**:
  1. `test_rir_rolling_cutoff_boundary` —— 窗起点当日分配的段内 IP 被剔(负);
  2. `test_scanner_csv_missing_raises_not_silent` —— scanner csv 缺件 raise
     (排除面不得无声缩小);
  3. `test_component_gate_short_sentinel_no_raise` —— 999 IP 不过闸:只出
     status.json 哨兵、零资产文件、不 raise(负);
  4. `test_tamper_input_snapshot_changes_pins` —— 改一行输入快照 → 成员指纹
     与输入 sha256 pin 双变(换证必留痕);
  5. `test_tampered_published_asset_fails_load` —— 已出版 ips.txt 加一行 →
     `load_asset` 指纹闸 ValueError(证据永不灭失);
  6. `test_window_boundary_ip_attribution` —— 前一天 IP 不入本版(窗界负例)。
- fail-loud 族:快照缺 captured_at / 坏行 / 空快照目录 / 空 rir 面 / 白名单
  坏行 / CLI 组件拼写坏(rc=2)各有断言。

## 复核命令

```sh
cd /home/huxiao/dev/pi-ip-lookup-tool/.worktrees/truth-v2-t1
python -m pytest backend/tests/eval -q          # 全量 eval 面(含新增 20 测)
python -m pytest backend/tests/eval/test_eval_truth_v2.py -q   # 仅 T1 面
```

## 遗留与风险(给 T2/T3)

- **过程偏离报备**:纪律要求读码先 codegraph_codegraph_explore,但本 worker
  会话工具清单不含 codegraph MCP(subagent 工具隔离),全程用 grep/read
  fallback 读码;读面窄(仅 eval 包四文件 + 测试惯例),已按 fallback 纪律
  收窄。

- 产物目录当前按 report_dir 约定(issue #260 明文);T2 接月轮附录腿、T3 并排
  对照若需把语料提升到跨 env 共享资产根(「语料是事实不是报告」惯例),
  移动即一行改动 + 指纹不变(members 指纹与目录无关),留 T2 裁决。
- 组件闸过闸阈值 1,000 在窗未满 90 天的过渡期必然不足(单周快照唯一数据源
  只有 ~1.8k,过了;honyport 未上线)——首月即哨兵是预期行为不是缺陷。
- 快照 attempts 列仅入 provenance 计数,不参与成员判定(准入=行为观测语义,
  ADR 0017 §1,不按次数加权)。
