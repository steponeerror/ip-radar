# GLOSSARY — 共享语言

本仓库的思考词汇表:agent 与人用同一套词,省下的 token 花在判断上。
定义即教义——很多词条本身就是一条哲学的压缩形态。

维护:铸词即录(铸新自造词的 PR 同步入表);锚点随 `codegraph init` 重建核对。

## 存储

- **epoch**:一次 rebuild 产出的不可变数据目录(`<base>.<n>`),建后永不原地写。锚:backend/ipdb/_sources/_lmdb.py(epoch helpers)
- **ptr**:指向当前 live epoch 的指针文件,唯一事实源;写侧换 ptr 即原子切换,读侧跟随,读者永不见半状态。锚:_lmdb.py(read_ptr)
- **族**:v4/v6 双套平行 LMDB 存储(base/ptr/reader/disjoint 全套独立);族必须显式声明——小 v6 整数数值上落在 v4 范围,按数值分派会错编 key。锚:_lmdb.py(lookup)、_source_base.py
- **disjoint 快路径**:排序区间两两不相交的库可走 O(1) 回扫;前提经 detect_disjoint O(n) 验证才许走,否则保守退到逐前缀 LPM 探测(嵌套库)。算法按数据形状选择,前提显式验证。锚:_lmdb.py(lookup/detect_disjoint)
- **interning(payloads 字典)**:证据 payload 跨 CIDR 去重存 sub-db,主库值里放 ref_id,命中时解引用;解引用 miss 必炸不降级。锚:_lmdb.py(PAYLOADS_NAME/resolve_evidence)

## 证据

- **无损管线**:parse→merge→types 任何一层不得丢弃证据;分类词映不上受控词表就落 other,原始标签全保。评分模型是过客,原始证据是永恒。锚:_evidence.py(route_record)
- **契约声明器,不是过滤器**:Pydantic `_Out` 用 extra="allow" 透传多余键——模型声明响应形状,不做裁剪。锚:_api_models.py(_Out)
- **native_type / native_categories**:源原生分类标签的保底存放处,映不上受控词表时的完整备份。锚:_classification.py
- **指控章 / 存档章**:ACCUSING = malicious|suspicious,有计分资格;informational 只展示不计分;benign = 弃权——不投票、也不亮存档黄灯。核心不变式:confidence 仅由 voters 决定,增删存档观测不改变数字。锚:_merge.py(_assess_classification)
- **无证据≠清白**:conf 0 = 无源命中,不是"干净";缺数据直说缺。锚:_api_models.py(FieldOut)

## 融合

- **宁少算**:融合歧义一律向低估解——同源多观测取 max 不求和、谱系相等也剔、纯存档组退回全量平滑淡出。锚:_logodds.py(dedup_lineage)
- **谱系**:源与源的派生关系(谁聚合了谁);DERIVED_SOURCES = firehol/ipsum/otx/greensnow/drb_ra;计分前谱系去重。锚:_logodds.py(DERIVED_SOURCES)
- **舰队**:评估时的对照基线——在场的其余启用源;与「市场先验」的"其余源"同一集合口径。锚:backend/main.py、backend/ipdb/_eval_reader.py
- **印证**:θ 的语义——与舰队的一致性,不是 accuracy;corroborated = 谱系去重后 ≥2 独立指控源(只数指控章)。锚:_merge.py 教义注释、_eval/model.py
- **市场先验**:其余源(舰队)在该分类上的命中率,作 Beta 先验中心;leave-out 计算防自证。锚:_eval/model.py(_prior_center)
- **喷泉源**:≥2 个源被它包含比例 ≥0.9——嫌疑是它在上游污染整个市场先验。锚:_eval/model.py(_fountain_suspect)
- **背景质量**:multicategory posterior 里 +1 的"未观测答案"概率质量(mass,非品质);没有它单源 conf 会到 100,违反单源 conf=r。锚:_logodds.py(multicategory_posterior)
- **单源 conf = r**:校准公理——一个源单独作证,置信度等于它自己的可靠度,永远到不了 100。锚:backend/tests/core/test_confidence.py
- **衰减**:威胁断言随 first_seen 指数衰减(2^(-age/h),默认 60d 半衰期);方向不变、强度衰减;标量字段不衰减。锚:_logodds.py(decay_factor)
- **声明 r**:SOURCE_RELIABILITY 手定可靠度;永不自动派生自 eval,采纳走人审 PR 且 diff 引用 eval 报告编号;`DATA_DIR/_calibrated.json` 为后验覆盖通道,覆盖直达全融合面(threat details.r 与置信度、标量、STIX;lookup 表优先,DM-1)。锚:_merge.py:65 教义、_registry.py(_apply_calibrated、to_observation 表优先)
- **平滑淡出**:纯存档组(无指控源)的 confidence 退回全量 Σ 而非跳变——数字渐变,不闪断。锚:_merge.py(_assess_classification)、tests/core/test_archive_abstention.py
- **合并策略**:四种标量策略——加权投票(city)/ log-odds 多类别(country/asn)/ 权威(as_name)/ 最长前缀(ip_range);威胁断言走独立路径 _assess_classification(谱系去重+按源衰减),不在标量策略表内。算法跟着字段语义走。锚:_merge.py、_registry.py(_strategies)
- **受控词表**:classification_type 用 IntelMQ 词汇作跨源印证轴——可比性是 schema 保证的,不是模型保证的。锚:_classification.py

## 性能与验证

- **位等价**:同输入必得位相同输出(PYTHONHASHSEED=0);bench 验收,也是未来任何内核重写的迁移合同。锚:backend/scripts/bench_lookup.py
- **消融**:eval 的净影响实验——去掉一个源跑 baseline vs candidate,看它挣不挣得下位置。锚:_eval/ablation.py(run_ablation)
- **回放闸门**:融合数学的变更对着语料回放裁决,不靠 code review 赌。锚:scripts/fusion_replay_gate.py
- **资源预算**:每种资源有上限——内存对数据量平坦(mmap)、LRU 有界、探测有界、进程弹性降级;系统拒绝 OOM 自己。压榨 = 消除浪费,不是增加机械。锚:_memory_valve.py、_batch_pool.py
- **冷启动门**:无需 API key 的源建完前,查询端点 503(warming up)——永不给半个数据集上的判定;建库窗口有超时放行的可用性逃生口。锚:backend/main.py(require_ready/_db_ready)

## 治理

- **NO-DATA**:eval 裁决之一,带成因(empty/collapsed);死源先报数据侧问题,不给语义豁免。锚:_eval/verdict.py(assess)
- **sunset 门**:冻结/已死的 feed 不许再准入;数据内部时间戳检测。锚:tests/core/test_no_feodo_residue.py;详设(本机私有 docs):docs/superpowers/specs/2026-08-04-source-triage-and-sunset-gate-design.md

## It's working if

- 讨论与 PR 描述直接用本表词汇("这是谱系问题"),而不是每次从头解释
- 评审意见引用 AGENTS.md 哲学条目编号

## It's broken if

- PR 铸了新自造词但未同步本表
- agent 输出对「谱系」「宁少算」等词的使用与词条定义矛盾
- 词条锚点指向死代码(随 `codegraph init` 核对)
