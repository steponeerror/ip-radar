# GLOSSARY — 共享语言

本仓库的思考词汇表:agent 与人用同一套词,省下的 token 花在判断上。
定义即教义——很多词条本身就是一条哲学的压缩形态。

维护:铸词即录(铸新自造词的 PR 同步入表);锚点随 `codegraph init` 重建核对;文档锚以路径+节名 grep 可命中为准(codegraph 只索引代码;死文档锚先例=industry:81 θ 锚,第11轮修)。

## 存储

- **epoch**:一次 rebuild 产出的不可变数据目录(`<base>.<n>`),建后永不原地写。锚:backend/ipdb/_sources/_lmdb.py(epoch helpers)
- **ptr**:指向当前 live epoch 的指针文件,唯一事实源;写侧换 ptr 即原子切换,读侧跟随,读者永不见半状态。锚:_lmdb.py(read_ptr)
- **族**:v4/v6 双套平行 LMDB 存储(base/ptr/reader/disjoint 全套独立);族必须显式声明——小 v6 整数数值上落在 v4 范围,按数值分派会错编 key。锚:_lmdb.py(lookup)、_source_base.py
- **disjoint 快路径**:排序区间两两不相交的库可走 O(1) 回扫;前提经 detect_disjoint O(n) 验证才许走,否则保守退到逐前缀 LPM 探测(嵌套库)。算法按数据形状选择,前提显式验证。锚:_lmdb.py(lookup/detect_disjoint)
- **interning(payloads 字典)**:证据 payload 跨 CIDR 去重存 sub-db,主库值里放 ref_id,命中时解引用;解引用 miss 必炸不降级。锚:_lmdb.py(PAYLOADS_NAME/resolve_evidence)
- **投影(策展静态源)**:策展静态源的 _DATA 常量是唯一真相源,data/ 下 csv 是物化投影——缺失或内容不一致即重物化并 bump mtime(needs_convert 入队一次 rebuild 后收敛,无循环;手工改 csv 会被覆写,是特性);epoch 损坏遇内容变更亦借此自愈。锚:_sources/infra_services.py(_sync_projection)、grill Q6(2026-10-11)

## 证据

- **无损管线**:parse→merge→types 任何一层不得丢弃证据;分类词映不上受控词表就落 other,原始标签全保。评分模型是过客,原始证据是永恒。锚:_evidence.py(route_record)
- **契约声明器,不是过滤器**:Pydantic `_Out` 用 extra="allow" 透传多余键——模型声明响应形状,不做裁剪。锚:_api_models.py(_Out)
- **native_type / native_categories**:源原生分类标签的保底存放处,映不上受控词表时的完整备份。锚:_classification.py
- **指控章 / 存档章**:ACCUSING = malicious|suspicious,有计分资格;informational 只展示不计分;benign = 弃权——不投票、也不亮存档黄灯。核心不变式:confidence 仅由 voters 决定,增删存档观测不改变数字。锚:_merge.py(_assess_classification)
- **benign(两层,勿混)**:①指控缺席 = 弃权——观测级弃权拼写 verdict=""(R17A-1,序列化特判保留,勿兑底 malicious),顶层无指控观测时缺省序列化 verdict="benign"、confidence=0(_types.threat_summary);不投票、不亮黄灯,是「无证据」不是「判良性」——弃权绝不作良性背书(见「无证据≠清白」)。②良性判定 = 非指控信号源明确断言 benign,与指控同场才算真对立(verdict_conflict);今日尚无源产良性断言,该通路为占位。锚:_evidence.py(to_dict 弃权特判)、_types.py(threat_summary)、_merge.py(_assess_classification)
- **资产弃权**:源只陈述基础设施属性(proxy/hosting/tor),不构成滥用指控——verdict="" 不计票、不产 STIX Indicator,仅走 attributes 通道。判例:cloud_ranges(首创)→ip2proxy DCH(SM-F2)→ip2proxy VPN/PUB/TOR(ADR 0001,2026-10-12)。锚:_sources/ip2proxy.py(_proxy_evidence)
- **行为源**:以观测到的滥用行为(扫描/爆破/C2 回连/举报)立证的源,如 bruteforce/ciarm/abuseipdb;与资产属性源相对——「挂着代理」由资产弃权陈述,「在作恶」由行为源指控。锚:_sources/bruteforce.py
- **无证据≠清白**:conf 0 = 无源命中,不是"干净";缺数据直说缺。锚:_api_models.py(FieldOut)

## 融合

- **宁少算**:融合歧义一律向低估解——同源多观测取 max 不求和、谱系相等也剔、纯存档组退回全量平滑淡出。锚:_logodds.py(dedup_lineage)
- **谱系**:源与源的派生关系(谁聚合了谁);DERIVED_SOURCES = firehol/ipsum/otx/otx_subscribed/greensnow/drb_ra(六员,源 class attr `derived=True` 在 _registry 导入时灌装;otx_subscribed 2026-10-07 入列);计分前谱系去重;同上游互嵌无实测 OC 数字者现状不入剔重——otx/otx_subscribed 双票,读数披露见 grill F6(_logodds.py:27)。锚:_logodds.py(DERIVED_SOURCES)
- **镜像对**:同出版方 OC=1.0/包含度 ≥0.9 的互嵌源对(判例 greensnow↔firehol);锚判式剔弱侧,corroborated 不把同一出版方算两票——回声不是印证。锚:_logodds.py(LINEAGE_ANCHORS)。判例:grill Q2 2026-10-11。锚判例一次性、无重校时点(残余盲区,见 grill 待办11③;第18轮 2026-10-14)。
- **回声(两义,勿混)**:①谱系回声=同上游派生重复计票(镜像对条);②记忆回声=长记忆列表对旧攻击者持续指控(威胁真值层条)。锚:本表「镜像对」/「威胁真值层」、grill A1(谱系回声族)/ADR 0002 §3(长记忆条件化)(第20轮 2026-10-14)
- **舰队**:评估时的对照基线——在场的其余启用源;与「市场先验」的"其余源"同一集合口径。锚:backend/main.py、backend/ipdb/_eval_reader.py
- **印证**:θ 的语义——与舰队的一致性,不是 accuracy;corroborated = 谱系去重后 ≥2 独立指控源(只数指控章);eval 接入关门限 θ_MC/θ_CG/θ_conf/θ_fp/θ_other(verdict.py:4)为常量,与本 θ 无关。锚:_merge.py 教义注释、_eval/model.py
- **市场先验**:其余源(舰队)在该分类上的命中率,作 Beta 先验中心;leave-out 计算防自证。锚:_eval/model.py(_prior_center)
- **喷泉源**:≥2 个源被它包含比例 ≥0.9——嫌疑是它在上游污染整个市场先验。锚:_eval/model.py(_fountain_suspect)
- **背景质量**:multicategory posterior 里 +1 的"未观测答案"概率质量(mass,非品质);没有它单源 conf 会到 100,违反单源 conf=r。锚:_logodds.py(multicategory_posterior)
- **单源 conf = r**:校准公理——一个源单独作证,置信度等于它自己的可靠度,永远到不了 100;适用校准族(log-odds 标量/威胁断言、as_name r×100),city 单源恒 50 与 ip_range 50/85 是品质阶梯/几何锚的有意设计(spec 2026-08-29 §4),公理字面不适用此二族。锚:backend/tests/core/test_confidence.py
- **衰减**:威胁断言随 first_seen 指数衰减(2^(-age/h),默认 60d 半衰期);方向不变、强度衰减;标量字段不衰减。锚:_logodds.py(decay_factor)
- **声明 r**:SOURCE_RELIABILITY 手定可靠度;永不自动派生自 eval,采纳走人审 PR 且 diff 引用 eval 报告编号;`DATA_DIR/_calibrated.json` 为后验覆盖通道,覆盖直达全融合面(threat details.r 与置信度、标量、STIX;lookup 表优先,DM-1)。锚:_merge.py:65 教义、_registry.py(_apply_calibrated、to_observation 表优先)
- **平滑淡出**:纯存档组(无指控源)的 confidence 退回全量 Σ 而非跳变——数字渐变,不闪断。锚:_merge.py(_assess_classification)、tests/core/test_archive_abstention.py
- **合并策略**:四种标量策略——加权投票(city)/ log-odds 多类别(country/asn)/ 权威(as_name)/ 最长前缀(ip_range);威胁断言走独立路径 _assess_classification(谱系去重+按源衰减),不在标量策略表内。算法跟着字段语义走。锚:_merge.py、_registry.py(_strategies)
- **受控词表**:classification_type 用 IntelMQ 词汇作跨源印证轴——可比性是 schema 保证的,不是模型保证的。锚:_classification.py
- **折并**:展示层合并规则——归一判定值一致的多源展示合一(正文只显归一值,证人逐行下沉悬停/行内 chips),后端载荷、置信度、算法零动,证据不灭失;不按可靠性挑正文赢家(零选择算法,宁少算)。判例:#105 as_org(2026-10-11)、service chip 泛化(同日,按源侧写死的角色词分组)。锚:frontend/src/components/IpDetailPanel.tsx(orgDup/service 分支)

## 性能与验证

- **位等价**:同输入必得位相同输出(PYTHONHASHSEED=0);bench 验收,也是未来任何内核重写的迁移合同。锚:backend/scripts/bench_lookup.py
- **消融**:eval 的净影响实验——去掉一个源跑 baseline vs candidate,看它挣不挣得下位置。锚:_eval/ablation.py(run_ablation)
- **回放闸门**:融合数学的变更对着语料回放裁决,不靠 code review 赌。锚:scripts/fusion_replay_gate.py
- **资源预算**:每种资源有上限——内存对数据量平坦(mmap)、LRU 有界、探测有界、进程弹性降级;系统拒绝 OOM 自己。压榨 = 消除浪费,不是增加机械。锚:_memory_valve.py、_batch_pool.py
- **冷启动门**:无需 API key 的源建完前,查询端点 503(warming up)——永不给半个数据集上的判定;建库窗口有超时放行的可用性逃生口。锚:backend/main.py(require_ready/_db_ready)

## 质量闸门(eval 闭环)

- **循环语料**:威胁标签取自被评估系统自身(输出导出或舰队源采样)的语料:只能作新旧对照(回归),不能作独立真值(绝对尺);舰队源采样的滚动子类=共识代理层,用途见该词条(本条『只能作新旧对照』限冻结语料)。判例:top_threat_1000(融合结果导出)、benchmark 600(源采样)。锚:CONTEXT.md(质量闸门)、docs/research/2026-10-12-eval-loop-grill-outcomes.md(背景与痛点)
- **威胁真值层**:蜜罐独立传感器观测到的攻击源 IP 构成的正样本层,是绝对读数的非循环锚。配套三闸:rir 分配日期过滤(剔重分配)、长记忆列表收录条件化子读数(离 feed 记忆回声)、k 计数排除蜜罐派生成员(knock_knock/binarydefense,双报 k_all/k_nonhoneypot);独立性组织级降级与语义=历史真值非当前真值属边界声明非闸。判例:Hornet 65 Niner(2024,CC BY 4.0)。锚:docs/adr/0002-honeypot-truth-anchor.md、grill Q6、CONTEXT.md(质量闸门)
- **k 族**:被指控 IP 的有效指控源数(谱系去重后计数;k_nonhoneypot 剔 {knock_knock,binarydefense},与 k_all 双报);研究稿/原型之 k_eff 即 k_all(同构造:per-源 coefficient×decay 取 max+dedup_lineage 后计数;hornet 附录A/loop-prototype/yardstick §一之 k 用旧名)。锚:docs/adr/0002-honeypot-truth-anchor.md、docs/research/2026-10-12-hornet-pilot.md(附录A)
- **共识代理层**:威胁侧语料取自本系统舰队源滚动采样,语义=舰队共识而非真相:只进区分度读数并强制标注循环性,永不充当真值。与冻结回归语料（新旧对照专用）相对。装配例外:接入关场景共识层装配须排除候选自身(照原型环0,loop-prototype:23);月轮全舰队场景自采样自指控=该层固有循环语义,读数注记(第10轮 2026-10-14)。锚：CONTEXT.md（质量闸门）、grill 2026-10-12
- **接入关**:add-intel-source 收尾的强制评估环节:消融 verdict + 四层区分度读数前后对照必附 PR;NEGATIVE/MIXED/NO-DATA 须用户显式裁决记录方放行(grill Q4)。在本地数据镜像上跑,CI 不可行(Q5)。锚:CONTEXT.md(质量闸门)、grill Q4/Q5
- **eval verdict**:eval 机判读数(态:POSITIVE-VERIFIED/POSITIVE-UNVERIFIED/MIXED/MARGINAL/NEGATIVE+INSUFFICIENT-SAMPLE/N/A-ASSET/NO-DATA;verdict.py:2-10 自标 6-state;docstring 实列 5 净影响态+3 特例(INSUFFICIENT-SAMPLE/N/A-ASSET/NO-DATA),『+2 特例』计数矛盾留代码批(第17轮 2026-10-14))——≠融合 verdict{malicious,suspicious}(CONTEXT 指控章,计票资格那一义);Q14/Q4/loop-prototype 的 eval 语境 verdict 指本词。锚:_eval/verdict.py(assess)(第16轮 2026-10-14)
- **双口径并报**:接入关读数义务——candidate stratum(候选自域判别力)与四层语料(舰队净影响)两口径并报,语料口径不同读数可差整个 verdict 态(greensnow 判例:冻结语料 POSITIVE-VERIFIED vs 四层 MARGINAL,谱系锚 firehol 对冲)。锚:loop-prototype(演示B)、_eval/corpus.py:23(candidate_ips 字段)、_eval/__main__.py:117(dynamic candidate stratum)(第16轮 2026-10-14)
- **纠错检验**:逐源列：该源唯一指控 ∩ 威胁真值层的命中率 ÷ P(候选唯一指控|IP∈中性层)(与 loop-prototype 实算口径一致);判定=点估计与 CI 并报(比值界=两个 95% 界之商,联合覆盖 ≥95%(两个单侧 2.5% 误差之并;原 ≥90% 为 Bonferroni 误按双侧相加的保守误算;第9轮 2026-10-14)):下界≥1=真异见(豁免从众型 conflict 定罪)、上界<1=噪声、CI 跨 1=边界态两侧均不得判(第5轮审查 2026-10-13);零事件以 Fisher/正则化稳健估计为主线(扩层算术不足:零事件稀疏--实测数字见 loop-prototype 环2,原型自述不防腐化;第8轮 2026-10-14);出口/Tor 段列表命中=成员资格≠行为检出,分子侧须分层注记;spamhaus DROP/EDROP 段命中=段指控非宿主指控(yardstick 坑7),中性层/非指控基础设施层基线须注记或单列(第5轮审查 2026-10-13);真值层现仅 SSH 攻击源(ADR 0002),非 SSH 主营源该列结构性恒边界态(第5轮审查 2026-10-13);短记忆/滚动窗行为源该列结构性偏低(量=语料年代×名单周转;真值语料 2024-04-28→07-01),读数参照 ADR 0002 §3 长记忆条件化子读数,非当期判别力证据;asset 轴候选该列=范围外延/成本信号,非收益判据;收益判定走接入关消融与弃权面评估(loop-prototype 演示 A)(第9轮 2026-10-14);网络构成混杂(蜜罐偏托管段)已申报,中性侧分层留 spec。防 eval 向共识回归(数学审查 F3,2026-10-12)。锚:CONTEXT.md(质量闸门)、grill Q12、loop-prototype 坑4(第4轮/第5轮 2026-10-13)
- **验收门**:本批自身「正向优化」的判定:V2 蒙特卡洛(真值已知,合成证据走真实融合代码,新旧体制对照)+ V3 历史回测(已知 Episode);阈值跑前冻结(反 p-hacking),不过门回炉。锚:CONTEXT.md(质量闸门)、grill Q15
- **冻结工件**:验收门跑前冻结的工件包:阈值+三场景族参数+五 Episode 名单+逐 Episode scorecard+门决策态归侧映射与 TPR@FPR 评分通道+harness A/A 自检(新旧体制置同跑全 FPR 网格,『过』率的二项 95% CI 须含标称假阳水平;标称=逐点判据实际单侧 α(95% 双侧 CI 下界>0 ⇒ ≈2.5%),「上界<0」失败率侧同款对称口径;A/A 重复次数 N≥max(100, 功效定标与自检判据同口径(双侧 95% CI containment,每侧 ≈2.5%):可检出 ≥2× 标称假阳率、功效 ≥80% ⇒ ≈383+(z=1.96/0.8416,p0=2.5%→p1=5%);旧 ≈310 系单侧 z=1.645 口径,对 containment 实际功效仅约 73%,系第17轮引入的口径自相矛盾(第18轮 2026-10-14 更正));Δρ 腿同入 A/A:无差异世界 Δρ CI 对真 0 的覆盖率须含标称水平(现条款只校准占优腿 FPR 网格;第18轮 2026-10-14);聚合口径(逐点 G 点全称量词 vs pooled)跑前钉死,逐点时假败率≈1−0.95^G 须入功效设计;跑前冻结(第9轮 2026-10-14;第17轮 2026-10-14 改功效定标;第18轮 2026-10-14 改 containment 口径与 Δρ A/A 校准)),hash 锚定(判官/harness 代码在主仓,其 hash 一并记入);工件分节:预注册节(任一增删=整门重跑)+append-only 裁决/运行附录(Q14 边界态裁决记录入附录,追加时主仓 sha256 逐文件行同步 bump,不触发重跑)(第14轮 2026-10-14)。锚:grill(预注册验收阈值·冻结工件行)、Q15/Q17(第8轮 2026-10-14 录入)
- **非指控基础设施层**:区分度读数的误报下界层:已知基础设施 IP(root servers、非 VPN 段公共解析器、云/CDN 段采样),内部拆「绝对干净锚」(进误报分母)与「争议子层」(VPN 段解析器,单独报数不进分母,作资产弃权扩展的观察哨)。锚:CONTEXT.md(质量闸门)、grill Q3
- **中性层**：随机可路由空间静态资产语料（neutral_ips.json 600，逐轮恒定；纠错检验分母+本底误报基线）；未验证阴性(哲学2):采样零良性验证,污染分解口径见 grill R10。锚：docs/research/2026-10-12-yardstick-feasibility.md（§二）、docs/research/2026-10-12-loop-prototype.md（环0）
- **哨兵(两义,勿混)**:①装配哨兵:每层读数附规模+指纹+成员计数,缺层=显式 NO-LAYER,禁跳层/禁报 0;②生效性哨兵:已知源 toggle 复跑验 toggle 真实生效(候选 raw IP 的 eff 源成员,判例 20/20→0/20;接入关物化流程用之;非指控通道候选改验 attributes/标量通道物化 provenance,如 registration 旁路块(_registry.py:632),变体定型留 spec;第13轮 2026-10-14)。锚:grill 待办4、loop-prototype 环1(第12轮 2026-10-14)
- **双轨(两义,勿混)**:①F2 cohort 双轨=威胁/误报侧分轨;②A2 证据双轨=track-1 数据重放/track-2 工件审查(grill Q17)。锚:grill F2/Q17(第20轮 2026-10-14)
- **区分度读数**:以舰队自身输出为对照的命中×误报分离读数族;循环语料只进此族,永不充当真值。锚:CONTEXT.md(质量闸门)(第12轮 2026-10-14)
- **绝对读数**:以非循环锚(威胁真值层/中性层)为基准的真值侧读数,与区分度读数相对。锚:本表「威胁真值层」(第12轮 2026-10-14)
- **action block**:月轮报告尾独立行动清单区块+NEEDS.md 一行指针。锚:grill Q9(第12轮 2026-10-14)

## 治理

- **NO-DATA**:eval 裁决之一,带成因(empty/collapsed);死源先报数据侧问题,不给语义豁免;属「eval verdict」态之一,见该词条。锚:_eval/verdict.py(assess)
- **sunset 门**:冻结/已死的 feed 不许再准入;数据内部时间戳检测。锚:tests/core/test_no_feodo_residue.py;详设(本机私有 docs):docs/superpowers/specs/2026-08-04-source-triage-and-sunset-gate-design.md
- **独占贡献 (Exclusive Contribution)**:候选源自有键中,池内无任何既有源在目标字段作答的比例 Uniq_A=|A\⋃其他源|/|A|(Li et al., "Reading the Tea Leaves", USENIX Sec'19);discover rubric 覆盖价值双锚之一(与轴新颖度取 max),≥300 可抽样键地板、niche 封顶 3、threat 轴独占不豁免 quality 闸(新键≠真阳性);动态孪生=eval 的 unique_share。判例:2026-10-10 grill 五问。锚:`_eval --exclusive` 探针=未实现,补齐须独立 PR(含 control 失败路径测试),此前按手工复刻契约执行(对抗审查第1轮 2026-10-13 声明)、.pi/skills/discover-intel-sources/SKILL.md(rubric)

## It's working if

- 讨论与 PR 描述直接用本表词汇("这是谱系问题"),而不是每次从头解释
- 评审意见引用 AGENTS.md 哲学条目编号

## It's broken if

- PR 铸了新自造词但未同步本表
- agent 输出对「谱系」「宁少算」等词的使用与词条定义矛盾
- 词条锚点指向死代码(随 `codegraph init` 核对)
