# #244 指控池循环抽公共 helper + 排序口径统一 —— 交付报告(arch-b,2026-10-30)

**分支** `ticket/arch-accusation-pool-helper`(基于 origin/master @ 34021685)
**结论** 五份拷贝收敛为一份公共函数;eval 四份读数逐位不变;生产侧唯一有意行为变更(池列表排序从插入序改 sorted)经回放闸门前后对照验证为零漂移;测试全绿。

## 一句话说明改了什么

「指控池」= 被指控 IP 的有效指控证人集合:先按指控章(malicious/suspicious)筛观测,同一来源只取最强的一条断言(按新鲜度衰减打分),再做谱系去重(防止镜像列表互相抄作业被算成两个独立证人)。这套核心循环此前在生产与 eval 里抄了 5 份;本票把它抽成一个函数放在 `_logodds.py`(谱系去重函数旁边),5 个使用方都改成调它,并把喂给谱系去重的列表顺序统一成按来源名排序。

## helper 签名(backend/ipdb/_logodds.py)

```python
def accuser_pool(entries: Iterable[tuple[str, float, str | None]],
                 ctype: str | None = None, *,
                 now: datetime | None = None) -> list[tuple[str, float]]
```

- `entries` = (来源名, 可靠性, 首见时间) 三元组;返回 dedup 后的 (来源, 系数) 列表,**按来源名 sorted**。
- 设计以 5 份拷贝真实循环为准,零新参数:`now` 只有生产传(时钟锚),eval 快照重算走默认墙钟。
- **指控章判定刻意留在调用方**(helper 不滤 verdict)——逐行 diff 确认判定面有三种形态,不许吞:
  1. eval 三份(agg_share/sinkhole_probe/anchor_readouts):detail 级滤,缺 verdict 键即滤;
  2. metrics._effective_votes:**缺 verdict 键兜底按 malicious 计**(旧快照兼容)——本票发现的隐藏差异,显式留在调用点(带注释),不参数化不吞并;
  3. 生产 _merge:调用方先做 voters-else-回退池预滤(纯存档组退回全量求和,决策 5/乙)——回退池含非指控观测,helper 内再滤会破坏回退语义。
- helper 放 `_logodds.py` 的原因:`_types.py` 反向依赖 `_logodds`(时钟锚/系数/去重都从这导),helper 若要拿指控章集合就必须放 `_types` 或让 `_logodds` 回环导入——判定留调用方后零新依赖,`_logodds` 保持纯函数。

## 五个消费面改造点(各留边缘差异)

| 消费面 | 改造 | 边缘差异(留在原地) |
|---|---|---|
| `_eval/agg_share.py` | 13 行循环 → 1 次 `accuser_pool` 调用(生成器喂入) | derived 占比/纯 derived 组计数 |
| `_eval/sinkhole_probe.py` | 同上 | per-IP accuser 并集(同源多组只记一次) |
| `_eval/anchor_readouts.py` `_group_accusers` | 数学委托 helper,留 raw 收集循环 | `raw_accusers` 原始 detail 三元组留痕(无损红线) |
| `_eval/metrics.py` `_effective_votes` | 循环 → `len(accuser_pool(...))` | 计数口径 + **缺 verdict 兜底 malicious**(调用点显式可见) |
| `_merge.py` `_assess_classification` | 循环 → `_lo.accuser_pool((生成器), ctype, now=_now)` | voters-else-回退池预滤、asof 时钟锚;**插入序→sorted(本票唯一有意行为变更)** |

## 行为变更面(边界声明)

- **唯一有意变更**:生产 `_merge._assess_classification` 谱系去重入参从 `list(by_source.items())`(插入序)改 `sorted(...)`。下游消费:confidence(浮点求和,顺序仅在浮点末位有理论影响)、corroborated(集合计数,序不变)、details(不从 deduped 构造,不变)。由回放闸门实证把关(见下)。
- **eval 四份读数逐位不变**:agg_share/sinkhole/anchor 本来就喂 sorted;metrics 喂 list 但只取 len——dedup 结果集合与输入顺序无关,len 不变。
- `_merge.py:146` LogOddsVoting 的 dedup_lineage 调用是标量多类别投票(无衰减、无逐源取 max),**非同构拷贝,不动**。

## 验证

### 回放闸门(`scripts/fusion_replay_gate.py`)

同语料同参数(`--data .eval-prod-data --stride 10 --limit 1000000`,43 指控源起点并集 1,000,001、实际 lookup 10 万次系统抽样)改动前/后各跑一遍,主仓 venv 解释器。语料/数据面标识:主仓根 `.eval-prod-data/`(生产 LMDB 快照镜像,未随本票重建),目录时间 2026-10-29 21:31、`.lmdb.*` 家族目录 708 个、顶层条目 129 —— 后人复现回放对照以此为准(起点并集 1,000,001 与下表各计数即指纹):

| 读数 | 改动前 | 改动后 |
|---|---|---|
| C2 单指控组新旧恒等 | **PASS**(strict 92,694 / 失配 0;loose 93,307 / 失配 0) | **PASS**(同,逐位相同) |
| 镜像 vs 生产 threat_summary 交叉核对 xcheck_bad | 0 | 0 |
| 探测/指控池非空/lookup 异常 | 1,000,001 / 99,413 / 0 | 同 |
| 分数直方图、列联表、k 分布、升降计数 | (基线) | **逐位相同** |
| 全报告唯一差异 | — | 仅 runtime_sec 61.9→64.9、VmHWM 0.672→0.675GB 两个进程噪声字段 |

报告原件:`dev/replay-before-archb.md` / `dev/replay-after-archb.md`(一次性工件,不入 git)。

**既有状态声明(与本票无关)**:两轮 rc 均=1,C3(benign ≥70 占比新≤旧:1,858→1,877)/ C4(Spearman ρ 0.545419→0.541690)为 FAIL——这是闸门拿 2026-10-03 冻结的旧选角规则对比今日生产融合在今日语料上的差,基线(未含本票改动的 origin/master)即如此;本票改动前后这两腿数字逐位未动,不引入也不修复。

### pytest(主仓 venv,worktree 代码)

- `tests/eval` **531 passed**
- `tests/core/test_logodds.py`(含新增 4 条 accuser_pool 测试:max-per-source/插入序无关/dedup 集成/时钟锚透传)**+ test_merge_scalar + test_archive_abstention + test_types:86 passed**
- `tests/core` 全量 **735 passed, 8 skipped**

## 发现与挂账(超出票面,未动)

- `_types.py:132-160` `threat_summary()`(顶层威胁重融合)是**票面未列出的第 6 份同构拷贝**:跨指控组池化 detail → 逐源 max → dedup → 计数/置信度,含 asof 时钟锚与空池回退。票面范围列 5 份,本票未改它(改动它会连带要求同步 `fusion_replay_gate.py` 的镜像重算,超出票面);建议另开票收编。改动后 xcheck_bad=0 证明闸门镜像与未动的 `_types` 仍一致。
- `_merge.py:146` 确认为不同构造(见上),票面排除正确。
- fusion_replay_gate.py 自带一份镜像重算(镜像的是 `_types.threat_summary`,非本票 5 份),属闸门防漂移自检机制,保持不动。

## 词汇表

GLOSSARY.md 新增「指控池」词条(k 族构造的池形态,含 sorted 口径与五消费面锚点)——票面「铸词即录」,同票提交。
