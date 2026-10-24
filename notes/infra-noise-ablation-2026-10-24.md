# infra 噪声载入期过滤消融对照表(issue #183 / ADR 0008)

- 日期:2026-10-24 | 代码:`feature/gs-183` tip `ed8dbf96`(过滤实现 `9ad8e9d0`,agg-share 披露 `300e8699`)
- 方法:**查询面双重建**——同一份 raw 数据(`/tmp/gs183-data` 字节级拷贝 ×2),先删三事故源 LMDB 族强制走载入面,唯一变量 = `IP_RADAR_INFRA_NOISE_FILTER` 开关;重建车道 = 生产同款 `python -m ipdb._rebuild_child <source>`(经 `IP_RADAR_DATA_DIR` 定位数据目录)
- 滤前(off):`IP_RADAR_INFRA_NOISE_FILTER=0`;滤后(on):默认开
- 查询:worktree 代码 `reg.lookup()` 全源融合,字段 = verdict / confidence / corroborated / accusers(指控源名单)

## 载入面排除足迹(排除计数日志复现)

| 源 | v4 键数 滤前→滤后 | 排除条目(日志明文) |
|---|---|---|
| myip_ms | 1564 → 1563 | `8.8.8.8/32` |
| ziyadnz | 123107 → 123106 | `114.114.114.114/32` |
| cps_collected_iocs | 31767 → 31765 | `1.1.1.1/32`, `114.114.114.114/32` |

原始数据文件零改写(排除仅挡 LMDB 投影;关开关重建即原样回算复原——证据永不灭失)。

## 锚面:四公共 DNS 滤前 vs 滤后

| IP | 滤前 verdict/conf | 滤前 accusers | 滤后 verdict/conf | 滤后 accusers |
|---|---|---|---|---|
| 8.8.8.8 | blacklist malicious/55 | myip_ms | **clean**(classifications 空) | — |
| 114.114.114.114 | blacklist malicious/55,corr=True | cps_collected_iocs, ziyadnz | **clean**(classifications 空) | — |
| 1.1.1.1 | blacklist malicious/50 | cps_collected_iocs | **clean**(classifications 空) | — |
| 223.5.5.5 | other malicious/50 | tweetfeed | other malicious/50(不变) | tweetfeed |

- 8.8.8.8 = 事故①(myip_ms 单源惡意55);114.114.114.114 = 事故②(cps+ziyadnz 纯 derived 聚合器假印证,cps+ziyadnz 运行时已 derived=True——ADR 0008 勘探测谎更正 d0f893f);1.1.1.1 = 同族连坐。三者滤后全部判 clean,验收目标达成。
- 223.5.5.5 的 tweetfeed 指控**不变**是预期行为:本票过滤仅对三事故源 opt-in(`infra_noise_filter=True` 显式声明,`_sources/myip_ms.py` 等),tweetfeed 未声明——宁少算,不开全源扩大化;该锚留作后续 benign 源接入阶段的独立整改面。

## 无外溢面:抽样 10 IP 逐字段全等(滤前=滤后)

事故源非 curated 条目 6:
- myip_ms raw 头两条:`34.147.21.60`、`216.73.216.190` — 均保持 blacklist malicious/55, acc=myip_ms
- ziyadnz raw 头两条:`1.0.164.165`(blacklist malicious/60 corr=True,acc=data_shield,firehol,ipsum,malicious_ip,ziyadnz)、`1.0.210.198`(blacklist malicious/55,acc=ziyadnz)
- cps raw 头两条:`3.135.207.58`(blacklist malicious/50,acc=cps_collected_iocs)、`45.95.19.50`(blacklist malicious/55 corr=True,acc=cps_collected_iocs,ziyadnz)

其他指控源对照 4:
- `1.192.244.126`(binarydefense;blacklist malicious/65)、`2.57.17.44`(blacklist malicious/97 corr=True,7 源)
- `64.62.197.5`(dshield 网段成员;blacklist 87 + scanner 74 双组)
- `85.217.149.7`(五组:abuse-reports 60 / blacklist 95 / botnet 57 / exploit 57 / malware 57 / scanner 94)

全部 10/10 UNCHANGED(完整 JSON:`/tmp/gs183-ablation-{off,on}.json`,面板与查询脚本 `/tmp/gs183_ablation_query.py`)→ 排除零外溢:仅 curated 单址精确命中被消,含 infra 的更大 CIDR 不排,其余 IP 判定逐字段不受扰。

## 已知局限:回放闸门(fusion_replay_gate)对本过滤不可见

**结论:证实(设计使然,非缺陷掩盖)。** `scripts/fusion_replay_gate.py` 数据流:

- `:247-249` 设 `IP_RADAR_DATA_DIR=<镜像>` + `sys.path` 指向代码仓 → `:262 reg.load_db()` 打开**已物化**的 LMDB → `:263-271` 全部语料来自已打开的 `s._reader`,经 `iter_source_starts()`(`:183-197`)直接遍历 LMDB v4 键起点——**全程零 rebuild/parse 调用**。
- 载入期过滤钩子在 `ipdb/_sources/_base.py:190-191/211/226`(IpListSource)与 `:320-321/351/368`(CsvSource)的 `rebuild()` 载入面,只改变**写入 LMDB 的投影内容**。

因此改前(25269fd0)/改后(300e8699)代码在**同一份未重建镜像**(`.eval-prod-data`)上跑回放,逐字节等价(仅时间戳/commit/耗时元数据不同)是**预期行为**:回放门守的是融合评分内核回归,不覆盖载入面回归——本消融即补此缺口的查询面证据。旁证:在**本地双重建**镜像(`/tmp/gs183-data`)上,回放面可见足迹——滤前 n_accused=2437/C2 严格口径 2361 组 vs 滤后 2439/2349(单指控 IP 消解 12 个),C3 双态同 FAIL(预存融合代差条件,与本票无关,归因见 /tmp/gs183-replay-localdata-{filtered,unfiltered}.md)。

## 相关件

- 排除实现:`backend/ipdb/_sources/_infra_filter.py`(curated 真源 = `infra_services._DATA` 单真相,勿查可能纪元落后的 LMDB——勘察 §4 判例)
- 纯 derived 组互证现状注记:`backend/ipdb/_types.py:85`(grill Q2 2026-10-11 语义,v0 只披露不改);聚合器占比披露工具:`backend/ipdb/_eval/agg_share.py`(`python -m ipdb._eval --agg-share`)
- 回放闸门(改前/改后对照):/tmp/gs183-replay-{before,after}.md(C2/C3/C4 双 PASS)
