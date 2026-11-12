# GLOSSARY — 共享语言

本仓库的思考词汇表:agent 与人用同一套词,省下的 token 花在判断上。
定义即教义——很多词条本身就是一条哲学的压缩形态。

受众(2026-10-31 用户令):**主人直读优先,agent 可读免费**——agent 读人话无损失,行话省下的 token 归 agent、可读性的代价归人,这笔账不划算;除代码标识符与数学公式,中文文档面默认人直接读得懂,压缩命名走本表人裁。

维护:词条出处随 `codegraph init` 重建核对;文档出处以路径+节名 grep 可命中为准(codegraph 只索引代码;死文档出处先例=industry:81 θ 词条,第11轮修);每条词条必须带出处(test_glossary_anchors 守卫断言)。

命名规则(2026-10-31 用户令,替代旧「铸词即录」):①概念稳定复现后才考虑命名——一次出现就造词=过度命名;②先查现成通用词——查证顺序:全国科技名词委规范术语库(termonline.cn,150+ 学科 80 余万条审定名词,2026-10-31 用户裁决认可)→统计界/工程界通行译名(gold standard→标准答案、anchor→已知答案、ablation→去源对比),实在没有才造新词;③造新词必须过路人测试——无项目背景的人只看词面能猜对方向才算合格;④人裁点头才入表,SDD 批交「命名裁决件」(候选名+通用词检索记录+路人测试结果),不再交「铸词」。统计界通用词(真值/读数/区分度/置信区间)与代码真名(epoch/ptr/verdict/conf/harvest)豁免改名,换掉反而与通行说法脱钩。外文术语首现即附人话对译(notes/ 研究笔记同守此条,堵住直译洗进口)。

## 改名对照(2026-10-31;旧词 grep 本表可达新词)

| 旧词 | 新词 |
|---|---|
| θ | 源间一致率(θ) |
| 消融 | 去源对比 |
| 回放闸门 | 同数据重跑比对 |
| 位等价 | 字节级一致(并入「同数据重跑比对」作判据) |
| 对照对打 | 同数据重跑比对(放宽版,并入) |
| 锚点 / anchor / 锚巡检等「锚」族(仅已知答案义;「锚点范例/锚点文件」=范例代码义,不在本批) | 已知答案 IP / 已知答案(巡检/门/读数/集) |
| 谓词限定锚 / 干净锚误报率 / 扫描锚召回 / 属性真值锚 / 活性锚 / 锚镜像 | 已知答案IP / 干净IP误报率 / 扫描段检出率 / 厂商自报段真值 / 存活证明列表 / 答案集镜像 |
| finding 出口三件套 / emit 守卫 | 巡检发现三出口 / 外发防重守卫 |
| 北极星 / 北星 | 主指标 |
| 谱系(去重/回声/混淆) | 转载关系(转载去重/转载回声/转载混淆) |
| 舰队 | 源池 |
| k 族 | 指控源数(k 值;k_all/k_nonhoneypot 代码名不动) |
| 市场先验 | 同池基准 |
| 喷泉源 | 疑似共同上游 |
| 无损管线 | 不丢证据 |
| 物化谓词 | 重建判定规则 |
| 中性层 | 随机背景样本 |
| 共识代理层 + 循环语料 | 自源测试集(合一) |
| 语料 | 测试集 |
| 合法空 | 声明空列表 |
| 背景质量 | 未见答案保底 |
| 指控章 / 存档章 | 指控证据 / 存档证据 |
| 威胁真值层 | 蜜罐真值层 |
| 冻结工件 | 跑前冻结包 |
| 排他率 + 独占贡献 | 独占率(合一) |
| 纠错检验 | 独有指控核查 |
| 双口径并报 | 两问分报 |
| 非指控基础设施层 | 已知基础设施层 |
| 黄金标准(四层) | 验收标准(四层) |
| 金标集 / 金标 | 标准答案集 / 标准答案 |
| 金轨迹 | 保活任务 |
| 金轨迹集(CONTEXT 语境=回归探针集) | 标准答案集(回归探针集) |
| 金标准 | 通行标准 |
| 锚定(NEEDS 语境) | 锁定/再校准 |
| 谱系审计 | 转载关系审计(README.zh-CN) |
| 回归轨 / 能力轨 | 保底轨 / 爬坡轨 |
| 回归门≈100% | 并入「保底轨」(放行阈值) |
| 静轮 | 零发现轮 |
| 腿级状态件(月轮「腿」) | 子步骤状态文件(子步骤) |
| A 一律 | 引用不抄录 |
| 标源 | 源注解 |
| 召回地板 + 锚判例域词表(现名判例速查表=组件②) | 检索保底(合一) |
| 轮次信封 / 失败信封 / 信封纪律 | 轮次结果单 / 失败结果单 / 并入「通道错误四码」 |
| 通道信封四码 | 通道错误四码 |
| 折叠族 | 同类错误归并 |
| 判例升格通道 | 判例转正通道 |
| 幸存信号集 | 筛后旗标集 |
| 状态机骨架 | 并入「轮次状态机」(P2) |
| 提示词层/装配层/宿主层 + 三层职责线 | 三层职责线(合一,P5) |
| 轮内预算步前检查 | 并入「预扣结算」(P7) |
| NO-DATA | 并入「eval verdict」 |
| 熔断(尾条) | 并入「跨轮熔断」 |
| 轮次状态文件 | 已退役(见底部「已退役」+ checkpoint) |

代码标识符/CLI 参数/文件名/UI 文案本轮不动(英文面,另行开票);CHANGELOG/notes/ADR 为历史记录不改。ops/agent(STANDARD/DESIGN/prompts 等)与 docs/CODEMAP.md 的中文面旧词同属延后批(与代码面同票处理)。

## 存储

- **epoch**:一次 rebuild 产出的不可变数据目录(`<base>.<n>`),建后永不原地写。出处:backend/ipdb/_sources/_lmdb.py(epoch helpers)
- **重建判定规则**:判断一份数据要不要整族重建的固定规则。族是否必须重物化的判定 `needs_convert(raw, base)`,三腿(三个条件,任一成立即触发):ptr 缺失 ∨ harvest 版本戳不匹配 ∨ ptr mtime < raw mtime;数据未变+代码未变 = False(增量跳写),任一腿触发 = True(真重建)。出处:_lmdb.py:372(needs_convert,ADR 0009)
- **harvest 版本戳**:`.rev` sidecar 里存的 harvest 代码代号(rebuild 原子盖章),对照 `HARVEST_REV` 常量;任何 harvest 语义改动必须 bump 常量,否则代码演进静默休眠(2026-10-10/2026-10-25 两起事故判例;存量族缺 .rev = 不匹配 → 首跑自愈重建)。出处:_lmdb.py:337(HARVEST_REV)、:325(rev_path,ADR 0009)
- **ptr**:指向当前 live epoch 的指针文件,唯一事实源;写侧换 ptr 即原子切换,读侧跟随,读者永不见半状态。出处:_lmdb.py(read_ptr)
- **族**:v4/v6 双套平行 LMDB 存储(base/ptr/reader/disjoint 全套独立);族必须显式声明——小 v6 整数数值上落在 v4 范围,按数值分派会错编 key。出处:_lmdb.py(lookup)、_source_base.py
- **disjoint 快路径**:排序区间两两不相交的库可走 O(1) 回扫;前提经 detect_disjoint O(n) 验证才许走,否则保守退到逐前缀 LPM 探测(嵌套库)。算法按数据形状选择,前提显式验证。出处:_lmdb.py(lookup/detect_disjoint)
- **interning(payloads 字典)**:证据 payload 跨 CIDR 去重存 sub-db,主库值里放 ref_id,命中时解引用;解引用 miss 必炸不降级。出处:_lmdb.py(PAYLOADS_NAME/resolve_evidence)
- **投影(策展静态源)**:从代码里的常量表生成磁盘数据文件的加工步骤。策展静态源的 _DATA 常量是唯一真相源,data/ 下 csv 是物化投影——缺失或内容不一致即重物化并 bump mtime(needs_convert 入队一次 rebuild 后收敛,无循环;手工改 csv 会被覆写,是特性);epoch 损坏遇内容变更亦借此自愈。出处:_sources/infra_services.py(_sync_projection)、grill Q6(2026-10-11)

## 摄取

- **声明空列表**:bare-IP 多列表 feed 中 HTTP 200 + 空 body 的子列表——发布方「当前无此类条目」的声明:落 0 字节文件、下一 epoch 出清该列表条目、不计失败。仅限 200;404/超时/存活证明列表为空仍是失败。firehol 等头部化格式不适用(空文件无头即坏)。出处:_sources/blocklist_de.py(download)
- **存活证明列表**:同批下载中证明出版方存活的列表(blocklist_de = all.txt 聚合);存活证明列表为空 = 本轮零替换 + 记真失败(fail-closed),防灾难性全空清库。判例:blocklist_de ircbot 2026-10-15(grill Q1-Q3)。出处:_sources/blocklist_de.py(download)
- **载入期基础设施过滤**:聚合类源 rebuild 载入面排除 curated 公共基础设施单址集——聚合器转载的指控对公认解析器不构成行为证据,排除在投影层(数据文件零改写,不丢证据不破)。真源=infra_services curated 集(单真相,勿查可能纪元落后的 LMDB);基类默认关,事故源显式 opt-in(infra_noise_filter=True);宁少算=仅精确单址命中,含 infra 的更大 CIDR 不排;IP_RADAR_INFRA_NOISE_FILTER=0 + 重建即复原,排除计数+条目日志化。判例:8.8.8.8(myip_ms 单源)/114.114.114.114(cps+ziyadnz 假印证)/1.1.1.1(cps)三公共解析器误报(2026-10-24 事故,ADR 0008 发现固化;哲学同族=资产弃权)。出处:_sources/_infra_filter.py
- **自报段**:IP 段由扫描主体自己公布、经机构镜像(MISP warninglists,CC0;Xpanse 直读)到达的厂商声明——身份证据非行为观测;镜像同源(OpenFilters/internet-scanners)只接一路防回声,与三方自采观测面(sw_scanners)无转载关系重叠;兼作 eval 真值层排除清单(ADR 0011)与扫描段检出率探针真值层(ADR 0013;真值只取厂商自报层,镜像仅转载关系注记)。判例:scanner_ranges 接入 grill 2026-10-26。出处:backend/ipdb/_sources/scanner_ranges.py:129(下载面 _FEEDS 66+1 表在 :119,harvest 证人 :150)
- **源底座**:全部 61 个源共享的生命周期基类 SourceBase(形态 A:抽共享底座、钩子分家,issue #248 2026-10-31 人裁):收编 Source(A 家族)与 IpListSource(B 家族)逐字重复的 __init__/load/_load_v6_side/query/_query6/health,另将 _http_get(原 A 家族单侧)与 download_host(原 B 家族单侧)上收底座(PR #250 第 1 轮审查 C 席勘正:这两者并非两家族逐字重复,原各属一家单侧);取数钩子两家族各自保留(harvest 对 parse_raw/parse_row),download 落盘契约分叉不动(A=原始字节/B=规范化明单+失败保留旧文件);ipinfo_lite 归位挂底座。出处:backend/ipdb/_sources/_base.py::SourceBase(消费者全鸭子型,注册发现不认基类)

## 证据

- **不丢证据**:parse→merge→types 任何一层不得丢弃证据;分类词映不上受控词表就落 other,原始标签全保。评分模型是过客,原始证据是永恒。出处:_evidence.py(route_record)
- **契约声明器,不是过滤器**:Pydantic `_Out` 用 extra="allow" 透传多余键——模型声明响应形状,不做裁剪。出处:_api_models.py(_Out)
- **native_type / native_categories**:源原生分类标签的保底存放处,映不上受控词表时的完整备份。出处:_classification.py
- **指控证据 / 存档证据**:章 = 证据按「能否参与恶意计票」分的两大类;指控证据计票,存档证据只展示。ACCUSING = malicious|suspicious,有计分资格;informational 只展示不计分;benign = 弃权——不投票、也不亮存档黄灯。核心不变式:confidence 仅由 voters 决定,增删存档观测不改变数字。出处:_merge.py(_assess_classification)
- **benign(两层,勿混)**:①指控缺席 = 弃权——观测级弃权拼写 verdict=""(R17A-1,序列化特判保留,勿兜底 malicious),顶层无指控观测时缺省序列化 verdict="benign"、confidence=0(_types.threat_summary);不投票、不亮黄灯,是「无证据」不是「判良性」——弃权绝不作良性背书(见「无证据≠清白」)。②良性断言 = 非指控信号源明确断言 benign(infra_services 升格为首个此类源,#188:curated 公共 DNS/NTP 单址双面 harvest——service 资产面照旧+classification_type=服务角色(dns/ntp)+verdict="benign";弃权拼写 "" 期作废);与指控同场才算真对立(verdict_conflict=True——良性断言 type-agnostic 注入每个指控组同场,注入面在 _registry.lookup);宁少算:良性证人不投票(组 conf/顶层重融合不变)、不压制指控 verdict(precedence 恒指控胜)、不产 STIX Indicator;conflict 留痕人裁不自动压制(已知答案巡检 conflict 投影/巡检发现出口 issue 标记);无指控组时以自身 ctype 成纯良性面(verdict=benign conf≈r,区别于①弃权 benign/0)。出处:_evidence.py(to_dict 弃权特判)、_types.py(threat_summary)、_merge.py(_assess_classification)、_registry.py(lookup 分组注入)、_sources/infra_services.py(harvest 双面)
- **资产弃权**:源只陈述基础设施属性(proxy/hosting/tor),不构成滥用指控——verdict="" 不计票、不产 STIX Indicator,仅走 attributes 通道。判例:cloud_ranges(首创)→ip2proxy DCH(SM-F2)→ip2proxy VPN/PUB/TOR(ADR 0001,2026-10-12)。出处:_sources/ip2proxy.py(_proxy_evidence)
- **行为源**:以观测到的滥用行为(扫描/爆破/C2 回连/举报)立证的源,如 bruteforce/ciarm/abuseipdb;与资产属性源相对——「挂着代理」由资产弃权陈述,「在作恶」由行为源指控。出处:_sources/bruteforce.py
- **公开研究扫描**:厂商自己公布扫描网段后,这类证据在系统里的计分形态——verdict=malicious 是行为类型断言(词表 "aggressive scanning"),非独立过错指控,意图活在 native 标签「研究扫描 · <厂商/机构>(自报段)」里;与行为源指控构成独立两票(观测线独立,corroborated 合法);改判权留用户,非良性断言(自报不构成良性背书,无证据≠清白)。判例:grill Q3 2026-10-26(用户裁「还是恶意但打标签,用户自己评估」)。出处:backend/ipdb/_sources/scanner_ranges.py:150-161(harvest 构造 native_categories=["研究扫描 · <厂商/机构>(自报段)"] :161)
- **无证据≠清白**:conf 0 = 无源命中,不是"干净";缺数据直说缺。出处:_api_models.py(FieldOut)

## 融合

- **宁少算**:融合歧义一律向低估解——同源多观测取 max 不求和、同上游转载相等也剔、纯存档组退回全量平滑淡出。出处:_logodds.py(dedup_lineage)
- **转载关系**:源与源的派生关系(谁聚合了谁);DERIVED_SOURCES = firehol/ipsum/otx/otx_subscribed/greensnow/drb_ra(六员,源 class attr `derived=True` 在 _registry 导入时灌装;otx_subscribed 2026-10-07 入列);计分前转载去重;同上游互嵌无实测 OC 数字者现状不入剔重——otx/otx_subscribed 双票,读数披露见 grill F6(_logodds.py:27)。出处:_logodds.py(DERIVED_SOURCES)
- **镜像对**:同一份内容被两个源重复发布(一份转载另一份的上游清单)的源对,计票只算一票。同出版方 OC=1.0(重合度)/包含度 ≥0.9 的互嵌源对(判例 greensnow↔firehol);转载判式剔弱侧,corroborated 不把同一出版方算两票——回声不是印证。出处:_logodds.py(LINEAGE_ANCHORS)。判例:grill Q2 2026-10-11。转载判式一次性、无重校时点(残余盲区,见 grill 待办11③;第18轮 2026-10-14)。
- **回声(两义,勿混)**:①转载回声=同上游派生重复计票(镜像对条);②记忆回声=长记忆列表对旧攻击者持续指控(蜜罐真值层条)。出处:本表「镜像对」/「蜜罐真值层」、grill A1(转载回声族)/ADR 0002 §3(长记忆条件化)(第20轮 2026-10-14)
- **源池**:评估时的对照基线——在场的其余启用源;与「同池基准」的"其余源"同一集合口径。出处:backend/main.py、backend/ipdb/_eval_reader.py
- **源间一致率(θ)**:θ = 某源的指控与源池其余源指控的一致程度,不是 accuracy(准不准要靠真值,不是靠跟别人像);corroborated(多源印证)= 转载去重后 ≥2 独立指控源(只数指控证据);eval 接入关门限 θ_MC/θ_CG/θ_conf/θ_fp/θ_other(verdict.py:4)为常量,与本 θ 无关。出处:_merge.py 教义注释、_eval/model.py
- **同池基准**:评估模型算源间一致率(θ)前,给该源各分类预置的基准倾向值(取自其余启用源在该分类的命中率)。其余源(源池)在该分类上的命中率,作 Beta 先验中心(统计先验的中心点);leave-out(留一法:算某源时先排除它自己)防自证。出处:_eval/model.py(_prior_center)
- **疑似共同上游**:≥2 个源被它包含比例 ≥0.9——嫌疑是它在上游污染整个同池基准。出处:_eval/model.py(_fountain_suspect)
- **未见答案保底**:给「没观测到的答案」预留的一小块概率。multicategory posterior(多类别后验分布)里 +1 的"未观测答案"概率质量(mass,非品质);没有它单源 conf 会到 100,违反单源 conf=r。出处:_logodds.py(multicategory_posterior)
- **单源 conf = r**:校准公理——一个源单独作证,置信度等于它自己的可靠度,永远到不了 100;适用校准族(log-odds 标量/威胁断言、as_name r×100),city 单源恒 50 与 ip_range 50/85 是品质阶梯/几何锚的有意设计(spec 2026-08-29 §4),公理字面不适用此二族。出处:backend/tests/core/test_confidence.py
- **衰减**:威胁断言随 first_seen 指数衰减(2^(-age/h),默认 60d 半衰期);方向不变、强度衰减;标量字段不衰减。出处:_logodds.py(decay_factor)
- **声明 r**:SOURCE_RELIABILITY 手定可靠度;永不自动派生自 eval,采纳走人审 PR 且 diff 引用 eval 报告编号;`DATA_DIR/_calibrated.json` 为后验覆盖通道,覆盖直达全融合面(threat details.r 与置信度、标量、STIX;lookup 表优先,DM-1)。出处:_merge.py:65 教义、_registry.py(_apply_calibrated、to_observation 表优先)
- **平滑淡出**:纯存档组(无指控源)的 confidence 退回全量 Σ 而非跳变——数字渐变,不闪断。出处:_merge.py(_assess_classification)、tests/core/test_archive_abstention.py
- **合并策略**:四种标量策略——加权投票(city)/ log-odds 多类别(country/asn)/ 权威(as_name)/ 最长前缀(ip_range);威胁断言走独立路径 _assess_classification(转载去重+按源衰减),不在标量策略表内。算法跟着字段语义走。出处:_merge.py、_registry.py(_strategies)
- **受控词表**:classification_type 用 IntelMQ 词汇作跨源印证轴——可比性是 schema 保证的,不是模型保证的。出处:_classification.py
- **折并**:展示层合并规则——归一判定值一致的多源展示合一(正文只显归一值,证人逐行下沉悬停/行内 chips),后端载荷、置信度、算法零动,证据不灭失;不按可靠性挑正文赢家(零选择算法,宁少算)。判例:#105 as_org(2026-10-11)、service chip 泛化(同日,按源侧写死的角色词分组)。出处:frontend/src/components/serviceFold.ts(service 支线共享模块,2026-10-30 抽取)、frontend/src/components/IpDetailPanel.tsx(orgDup 支线)

## 性能与验证

- **同数据重跑比对**:融合数学的变更对着测试集回放裁决,不靠 code review 赌。判据=字节级一致——同输入必得位相同输出(PYTHONHASHSEED=0),bench 验收,也是未来任何内核重写的迁移合同;放宽版=并排对打(STANDARD 原语 P17,半缺)——候选与生产变更在固定数据集上并排对打,三轴 quality/latency/cost,过 release criteria 才放行,字节级一致是下限不是上限(旧名见「改名对照」)。出处:scripts/fusion_replay_gate.py、backend/scripts/bench_lookup.py、ops/agent/STANDARD.md 原语层(P17)
- **去源对比**:eval 的净影响实验——去掉一个源跑 baseline vs candidate,看它挣不挣得下位置。出处:_eval/ablation.py(run_ablation)
- **结构重复**:逐字换名拷贝的代码段——变量名/字段名/字面量不同,调用形状与操作符相同;dryer 可测(阈值 0.82,≥0.9 强信号)。「同思路加料的派生」(如带跨组池化/asof 锚的变体)控制流形状变了指纹即失配,工具不报,仍靠人审与转载关系分析;与「镜像对」(证据域:同一内容两源重复发布)相区分——一个在代码,一个在数据。豁免类别(报告跳过,2026-10-31 分类裁定):源家族 parse/harvest 同构(39 对,残余归「两基类合一」后续票)、第三方 UI 原语(ui/dialog.tsx 等)、API 契约模型声明形(_api_models.py)、防环直查与锁+原子写惯用形(_ops_items↔_ops_store)、限流三桶配置形(_ratelimit.py,每桶 docstring 即 spec 锚)。真重复两批待折:api.ts 取数样板(23 对)、env 路径覆写五连(_alerts/_auth)。判例:ub-mode 评估 2026-10-31;折并批前后 113→78 对,指控池 6 份拷贝全程未报 = 边界实证。出处:notes/ub-mode-2026-10-31.md(dryer 实测)
- **资源预算**:每种资源有上限——内存对数据量平坦(mmap)、LRU 有界、探测有界、进程弹性降级;系统拒绝 OOM 自己。压榨 = 消除浪费,不是增加机械。出处:_memory_valve.py、_batch_pool.py
- **冷启动门**:无需 API key 的源建完前,查询端点 503(warming up)——永不给半个数据集上的判定;建库窗口有超时放行的可用性逃生口。出处:backend/ipdb/_coldstart.py(ColdStartGate)+ backend/main.py(require_ready)

## 质量闸门(eval 闭环)

- **聚合器占比**:披露「互相印证的证据里有多少其实来自转载他人数据的聚合器源」的读数——生产同款重算(per-源 max 系数→dedup_lineage)后计聚合器票在 corroborated 组中的份额,纯 derived 组(互证回声,corroborated 仍 True 的现状面)点名;v0 只测量不持门、不改 corroborated 语义(grill Q2 2026-10-11 裁定),语义变更须另票过同数据重跑比对。判例:114DNS cps+ziyadnz 纯 derived 互证(2026-10-24)。出处:_eval/agg_share.py(CLI --agg-share,落 model/agg-share-<ts>.json)
- **自源测试集**(旧名见「改名对照」;滚动子类=源池自采样测试集):威胁标签取自被评估系统自身(输出导出或源池源采样)的测试集——只能作新旧对照(回归),不能作独立真值(绝对尺);『只能作新旧对照』限冻结测试集。滚动子类=源池自采样测试集:取自本系统源池源滚动采样,语义=源池共识而非真相(与冻结测试集相对),只进区分度读数并强制标注循环性,永不充当真值;装配例外:接入关场景共识测试集装配须排除候选自身(照原型环0,loop-prototype:23);月轮全源池场景自采样自指控=该层固有循环语义,读数注记(2026-10-14 Q22 降格诊断层:不做假设检验、豁免 F9 地板、容量 ~570 独立声明)。判例:top_threat_1000(融合结果导出)、benchmark 600(源采样)。出处:CONTEXT.md(质量闸门)、docs/research/2026-10-12-eval-loop-grill-outcomes.md(背景与痛点)
- **蜜罐真值层**:蜜罐独立传感器观测到的攻击源 IP 构成的正样本层,是绝对读数的非循环锚。配套三闸:rir 分配日期过滤(剔重分配)、长记忆列表收录条件化子读数(离 feed 记忆回声)、指控源数计数排除蜜罐派生成员(knock_knock/binarydefense,双报 k_all/k_nonhoneypot);独立性组织级降级与语义=历史真值非当前真值属边界声明非闸。判例:Hornet 65 Niner(2024,CC BY 4.0)。出处:docs/adr/0002-honeypot-truth-anchor.md、grill Q6、CONTEXT.md(质量闸门)
- **指控源数**:被指控 IP 的有效指控源数(转载去重后计数;k_nonhoneypot 剔 {knock_knock,binarydefense},与 k_all 双报);研究稿/原型之 k_eff 即 k_all(同构造:per-源 coefficient×decay 取 max+dedup_lineage 后计数;hornet 附录A/loop-prototype/yardstick §一之 k 用旧名)。出处:docs/adr/0002-honeypot-truth-anchor.md、docs/research/2026-10-12-hornet-pilot.md(附录A)
- **指控池**:被指控 IP 的有效指控证人集(即「指控源数」构造的池形态,k = 池大小):指控证据判定后逐源 coefficient×decay 取最强单条 + dedup_lineage;排序口径统一 sorted(issue #244,grill Q2 2026-10-30 人裁;生产 _merge 此前插入序属唯一有意行为变更,仅池列表序,同数据重跑比对把关)。出处:backend/ipdb/_logodds.py::accuser_pool(单源化;六消费面:_merge/agg_share/sinkhole_probe/anchor_readouts/metrics/_types.threat_summary 跨组池化——entry 第 4 元携所属组 ctype,#246;fusion_replay_gate 镜像同调)
- **接入关**:add-intel-source 收尾的强制评估环节:去源对比 verdict + 四层区分度读数前后对照必附 PR;NEGATIVE/MIXED/NO-DATA 须用户显式裁决记录方放行(grill Q4)。在本地数据镜像上跑,CI 不可行(Q5)。出处:CONTEXT.md(质量闸门)、grill Q4/Q5
- **eval verdict**:评估程序对一个源值不值得加的机判结论(态:POSITIVE-VERIFIED/POSITIVE-UNVERIFIED/MIXED/MARGINAL/NEGATIVE+INSUFFICIENT-SAMPLE/N/A-ASSET/NO-DATA;verdict.py:2-10 自标 6-state;docstring 实列 5 净影响态+3 特例(INSUFFICIENT-SAMPLE/N/A-ASSET/NO-DATA),『+2 特例』计数矛盾留代码批(第17轮 2026-10-14))——≠融合 verdict{malicious,suspicious}(CONTEXT 指控证据,计票资格那一义);Q14/Q4/loop-prototype 的 eval 语境 verdict 指本词。NO-DATA(带成因 empty/collapsed;旧单列词条已并入):死源先报数据侧问题,不给语义豁免。出处:_eval/verdict.py(assess)(第16轮 2026-10-14)
- **两问分报**:新源评估必须并排报两种口径的读数——candidate stratum(候选自域判别力)与四层测试集(源池净影响),测试集口径不同读数可差整个 verdict 态(greensnow 判例:冻结测试集 POSITIVE-VERIFIED vs 四层 MARGINAL,转载关系判据 firehol 对冲)。出处:loop-prototype(演示B)、_eval/corpus.py:23(candidate_ips 字段)、_eval/__main__.py:117(dynamic candidate stratum)(第16轮 2026-10-14)
- **独有指控核查**:检验某源独有的指控是被已知答案支持、还是纯属噪声的统计检查。逐源列：该源唯一指控 ∩ 蜜罐真值层的命中率 ÷ P(候选唯一指控|IP∈随机背景样本)(与 loop-prototype 实算口径一致);判定=点估计与 CI 并报(比值界=两个 95% 界之商,联合覆盖 ≥95%(两个单侧 2.5% 误差之并;原 ≥90% 为 Bonferroni 误按双侧相加的保守误算;第9轮 2026-10-14)):下界≥1=真异见(豁免从众型 conflict 定罪)、上界<1=噪声、CI 跨 1=边界态两侧均不得判(第5轮审查 2026-10-13);零事件以 Fisher/正则化稳健估计为主线(扩层算术不足:零事件稀疏--实测数字见 loop-prototype 环2,原型自述不防腐化;第8轮 2026-10-14);出口/Tor 段列表命中=成员资格≠行为检出,分子侧须分层注记;spamhaus DROP/EDROP 段命中=段指控非宿主指控(yardstick 坑7),随机背景样本/已知基础设施层基线须注记或单列(第5轮审查 2026-10-13);真值层现仅 SSH 攻击源(ADR 0002),非 SSH 主营源该列结构性恒边界态(第5轮审查 2026-10-13);短记忆/滚动窗行为源该列结构性偏低(量=测试集年代×名单周转;真值测试集 2024-04-28→07-01),读数参照 ADR 0002 §3 长记忆条件化子读数,非当期判别力证据;asset 轴候选该列=范围外延/成本信号,非收益判据;收益判定走接入关去源对比与弃权面评估(loop-prototype 演示 A)(第9轮 2026-10-14);网络构成混杂(蜜罐偏托管段)已申报,随机背景侧分层留 spec。防 eval 向共识回归(数学审查 F3,2026-10-12)。出处:CONTEXT.md(质量闸门)、grill Q12、loop-prototype 坑4(第4轮/第5轮 2026-10-13)
- **验收门**:本批自身「正向优化」的判定:V2 蒙特卡洛(真值已知,合成证据走真实融合代码,新旧体制对照)+ V3 历史回测(已知 Episode);阈值跑前冻结(反 p-hacking),不过门回炉。出处:CONTEXT.md(质量闸门)、grill Q15
- **跑前冻结包**:验收跑之前冻结锁死的全部参数与阈值工件包(防事后挑数据)。验收门跑前冻结的工件包:阈值+三场景族参数+五 Episode 名单+逐 Episode scorecard+门决策态归侧映射与 TPR@FPR 评分通道+harness A/A 自检(新旧体制置同跑全 FPR 网格,『过』率的二项 95% CI 须含标称假阳水平;标称=逐点判据实际单侧 α(95% 双侧 CI 下界>0 ⇒ ≈2.5%),「上界<0」失败率侧同款对称口径;A/A 重复次数 N≥max(100, 功效定标与自检判据同口径(双侧 95% CI containment,每侧 ≈2.5%):可检出 ≥2× 标称假阳率、功效 ≥80% ⇒ ≈383+(z=1.96/0.8416,p0=2.5%→p1=5%);旧 ≈310 系单侧 z=1.645 口径,对 containment 实际功效仅约 73%,系第17轮引入的口径自相矛盾(第18轮 2026-10-14 更正));Δρ 支线同入 A/A:无差异世界 Δρ CI 对真 0 的覆盖率须含标称水平(现条款只校准占优支线 FPR 网格;第18轮 2026-10-14);聚合口径(逐点 G 点全称量词 vs pooled)跑前钉死,逐点时假败率≈1-0.95^G 须入功效设计;跑前冻结(第9轮 2026-10-14;第17轮 2026-10-14 改功效定标;第18轮 2026-10-14 改 containment 口径与 Δρ A/A 校准)),hash 锁定(判官/harness 代码在主仓,其 hash 一并记入);工件分节:预注册节(任一增删=整门重跑)+append-only 裁决/运行附录(Q14 边界态裁决记录入附录,追加时主仓 sha256 逐文件行同步 bump,不触发重跑)(第14轮 2026-10-14)。出处:grill(预注册验收阈值行;旧名见「改名对照」)、Q15/Q17(第8轮 2026-10-14 录入)
- **已知基础设施层**:区分度读数的误报下界层:已知基础设施 IP(root servers、非 VPN 段公共解析器、云/CDN 段采样),内部拆「绝对干净IP」(进误报分母)与「争议子层」(VPN 段解析器,单独报数不进分母,作资产弃权扩展的观察哨)。出处:CONTEXT.md(质量闸门)、grill Q3
- **已知答案IP**:已知答案IP = 拿来当标准答案的已知 IP;每条已知答案IP带自己的具体期望,不做全局干净/恶意二分。已知答案IP条目携带 per-谓词期望(公共解析器/根服务器=沦陷指控不得出现;自报段=行为源应见、沦陷源不应必然见),弃全局干净/恶意二值;干净率只作 census 输出、不作输入假设。判例:grill 2026-10-28 Q1/Q2(用户裁)。出处:backend/ipdb/_eval/anchors.py(ANCHORS expect 列即谓词槽)、docs/adr/0013
- **干净IP误报率**:干净IP上被指控的条件误报读数(Clopper-Pearson 精确界+零事件精确上界(rule of three;k=0 时下界恒 0 无信息量,2026-10-29 勘误),N/seed/成员清单随件落盘);必附被控成因三分类:真误列(feed 缺陷)/伪造源摄入(传感器缺陷,判例=CAIDA 银行 spoofing 2019)/消费端误读(Spamhaus DNSBL×公共解析器机制)。判例:8.8.8.8(myip_ms 单源)/114DNS(cps+ziyadnz)即三分类先例;grill 2026-10-28 Q1/Q6。出处:backend/ipdb/_eval/anchor_readouts.py(clean_anchor_fp 读数A+census N/seed/成员清单随件)、docs/adr/0013、notes/anchor-eval-research-2026-10-28.md(§C5)
- **扫描段检出率**:行为观测类源对自报段成员的灵敏度读数——蜜罐/扫描类源应见研究扫描段,从未看见=盲区证据;真值只取厂商自报层(MISP 镜像滞后仅转载关系注记;SANS ISC 观测面仅佐证且带污染注记:其 shodan 列表实测混 Rapid7 Sonar 段);分子 leave-out 排除 scanner_ranges 自身;与真值层排除刻意不对称(同一 IP 三面:产品恶意/真值排除/召回检查,ADR 0013);v0 只测量不持门。判例:grill 2026-10-28 Q3;MADWeb 2025(望远镜地址 71.24% 曾上榜→榜上有名≠恶意)。出处:backend/ipdb/_eval/anchor_readouts.py(scanner_recall 读数B+leave-out+段成员稳定采样)、backend/ipdb/_sources/scanner_ranges.py、docs/adr/0013
- **污染探针**:已知 sinkhole 段(首批=MISP warninglists sinkholes 203 项,准入前置=上游 provenance 溯源)被指控源命中记污染分不记恶意分——「把 sinkhole IP 当 C2 上榜」是已知 FP 模式;数据落 eval-only 测试集文件(照随机背景样本 neutral_ips.json 先例),不进产品源。判例:grill 2026-10-28 Q1/Q4/Q5。出处:backend/ipdb/_eval/sinkhole_probe.py(探针+eval-only 测试集 sinkhole_ranges.json/provenance sidecar)、docs/adr/0013、notes/anchor-eval-research-2026-10-28.md(§A5)
- **厂商自报段真值**:厂商自公布 infra/edge 段(Cloudflare/Google/AWS 等官方端点直引;MISP 镜像滞后不作真值),只证 hosting/CDN/cloud 属性与争议子层成员资格——非干净IP(云 VM 可真实沦陷);与 cloud_ranges 同源去重防双算(v1 采纳排序)。判例:grill 2026-10-28 Q4。出处:未落地(v1;ADR 0013 采纳排序=厂商官方段直引,代码无实体现)、docs/adr/0013、notes/anchor-eval-research-2026-10-28.md(§A1)
- **随机背景样本**：随机可路由空间静态资产测试集（neutral_ips.json 600，逐轮恒定；独有指控核查分母+本底误报基线）；未验证阴性(哲学2):采样零良性验证,污染分解口径见 grill R10。出处：docs/research/2026-10-12-yardstick-feasibility.md（§二）、docs/research/2026-10-12-loop-prototype.md（环0）
- **哨兵(两义,勿混)**:①装配哨兵:每层读数附规模+指纹+成员计数,缺层=显式 NO-LAYER,禁跳层/禁报 0;②生效性哨兵:已知源 toggle 复跑验 toggle 真实生效(候选 raw IP 的 eff 源成员,判例 20/20→0/20;接入关物化流程用之;非指控通道候选改验 attributes/标量通道物化 provenance,如 registration 旁路块(_registry.py:632),变体定型留 spec;第13轮 2026-10-14)。出处:grill 待办4、loop-prototype 环1(第12轮 2026-10-14)
- **双轨(两义,勿混)**:同一评测里并行报的两条线。①F2 cohort 双轨(评审发现 F2)=按威胁侧/误报侧分开报;②A2 证据双轨(评审发现 A2)=track-1 数据重放/track-2 工件审查(grill Q17)。出处:grill F2/Q17(第20轮 2026-10-14)
- **区分度读数**:以源池自身输出为对照的命中×误报分离读数族;自源测试集只进此族,永不充当真值。出处:CONTEXT.md(质量闸门)(第12轮 2026-10-14)
- **绝对读数**:以非循环锚(蜜罐真值层/随机背景样本)为基准的真值侧读数,与区分度读数相对。出处:本表「蜜罐真值层」(第12轮 2026-10-14)
- **action block**:月轮报告尾独立行动清单区块+NEEDS.md 一行指针。出处:grill Q9(第12轮 2026-10-14)

## 治理

- **sunset 门**:冻结/已死的 feed 不许再准入;数据内部时间戳检测。出处:tests/core/test_no_feodo_residue.py;详设(本机私有 docs):docs/superpowers/specs/2026-08-04-source-triage-and-sunset-gate-design.md
- **独占率**(两词条 2026-10-31 合一,旧名见「改名对照」):一个候选源有多少内容是池内其他源都没有的。eval 实测面:候选 feed 采样键中,池内无任何指控的份额——候选自有增量的实测度量(协议:N=300 稳定 seed、阳性对照、归因到覆盖源、不吞异常;重叠类 REJECT 必须附此实测数,上游映射推断不得替代;动态孪生=unique_share)。discover 评审面:候选自有键中,池内无任何既有源在目标字段作答的比例 Uniq_A=|A\⋃其他源|/|A|(Li et al., "Reading the Tea Leaves", USENIX Sec'19),rubric 覆盖价值双锚之一(与轴新颖度取 max),≥300 可抽样键地板、niche 封顶 3、threat 轴独占不豁免 quality 闸(新键≠真阳性)。判例:malicious-ip(82.7%)/ziyadnz(44.7%)两连翻案(2026-10-18);2026-10-10 grill 五问;独占梯度反向于源间一致率——多源印证段=回声段,单源段=增量段。出处:backend/ipdb/_eval/exclusive.py(`python -m ipdb._eval --exclusive <feed> [--seed] [--json]`)、CONTEXT.md(源发现)、.pi/skills/discover-intel-sources/SKILL.md(rubric)
- **聚合器候选**:上游为多个池内已知出版的聚合列表的候选源;此类候选的映射直觉最不可靠(『出版方都有了』推不出回声),是独占率实测的强制适用域。接入时一律 `derived=True`(转载去重,与主源同现自动折叠)。出处:CONTEXT.md(源发现)、_logodds.py(DERIVED_SOURCES)

## 运营 agent(ops)

- **spawn 契约**:Python 桥(P2)/人/测试与 ops/agent/agent.mjs 之间 CLI interface 的全部事实(argv 形状 + env 表 + 退出码 0/1/2 + 轮次结果单 + stderr 进度行);后端 spawn 该 CLI 是运营轮唯一入口 seam,env 面以 agent.mjs 的 SPAWN_CONTRACT_ENV 为唯一详述点(双向对拍钉死:selftest-contract)。判例:2026-10-20 契约深化批——T4「CLI 契约冻结」后首次修约,消费方未现=修约非违约。出处:ops/agent/agent.mjs(SPAWN_CONTRACT_ENV/main)
- **轮次结果单**:runRound 结果的机器面——agent.mjs stdout 的单行 JSON,成功/失败同形成败面(成功:ok/round/pkg/usage{数字}/queue_writes{action,source,dedup}/verify{cited};失败:error{code 闭集九词,message 原文},pkg 仅当包已落盘);用法错(argv 缺参)=纯 stderr+exit 2 不发结果单。与工具级「失败结果单」(tools.mjs envelope(),铁律②)是两物勿混:失败结果单是单工具返回面,轮次结果单是整轮 CLI 面。出处:ops/agent/agent.mjs(main 序列化处 successEnvelope/failureEnvelope)。pipeline 轮(agent.mjs 委派 pipeline.mjs)结果单另带 pipeline{round_id,stages[]} 扩展字段(只增不改旧键;顶层 usage 仍=各模型步之和)
- **待集成清单**:ops 树 queue.md——裁⑦「全保守」(零自动执行)的唯一动作产物:人裁 agreed 且建议动词落在 T4 冻结闭集 {ENQUEUE,REJECT} 内才经 append_queue 入队(幂等去重键 = action+source,与轮次结果单 queue_writes 的 dedup 同键);闭集外/人裁类动词(ACCEPT/FLAG 等)判例-only 零队列写,不发明闭集外动词;幂等重放仍调 append_queue——去重下真零写,兼自愈队列中途丢失/多写的残态。与判例两物勿混:判例记人裁留痕本体,清单只收闭集动词的已批准动作(集成回 SourcesPage 手动,包 UI 恒标「仅立项」)。出处:backend/ipdb/_ops_store.py(append_queue/_maybe_queue;票 #135)
- **写回四律**:人裁写回 POST /api/ops/ruling(write_ruling)的四条硬律:schema 校验(序列化文本往返解析过 validate_precedent_entry 才落盘,写什么校什么)/ superseded_by(改裁=新条目+旧条目链指,原条目永不删,链指是唯一许可的就地变更;写序先新后旧链,任一瞬间链目标都存在)/ 幂等(键 =(包,建议,verdict,修正案)语义比较,同裁重复含跨日零副作用)/ 修正案逐字留痕(原文进 human_ruling 一字不改,只随 amended);production_delta 恒 null(30 天生产增量写回是独立后续批,未结案不补)。出处:backend/ipdb/_ops_store.py(write_ruling;票 #135)
- **串行车道**:运营轮与源更新任务在任务管理器的互斥机制:ops 轮在飞(占道,一轮一车道)则源任务停摆等待(已 queued 者也不出队,worker 在 _queue_cv 上等 notify_all);反之任一源任务 queued/downloading/loading/throttled 在飞则 ops 轮被拒(busy_reason="sources",queued 也算——关死 worker pop 后未翻相位的并发窗;占道冲突则 busy_reason="round")。ops 相位 running 不入 has_active_offline_tasks 四态 → 不阻查询门(冷启动验收 1)。出处:backend/ipdb/_tasks.py(start_ops_round/_worker;票 #134)
- **驾驶舱**:轮次观察面(票 #142;#148 单卡化):单卡 = 状态 chip 内联节头(节头 lead)+ 上一轮结果(失败面人话化,原始结果单可展开——证据不灭失)+ 健康/发现触发动作入卡,常驻运营页「轮次」子 tab 顶;进行时另有已耗时走字(自本页首见该轮起计,任务面无创建时间戳,宁少算不伪造)/最后一行活动/可折叠全量日志。数据源链 = 任务链内存态(tasks+task_log)优先、台账末行兜底;过往轮次表独立成节(OpsPastRounds),不并入卡。只观察不裁决——裁决动作面在「裁决」子 tab,与档案(审计面)相对。壳层信号灯 = admin nav ops tab 在飞红点。出处:frontend/src/pages/OpsCockpit.tsx(OpsCockpit/OpsPastRounds)
- **档案**:运营页只读审计面(票 #142;P1 扩驻报告):历史(轮次记账)+规则库(人裁留痕)+报告(旧包只读渲染,P1 前裁决交互已移除)三 section 合驻的「档案」子 tab;动作面迁「审阅」子 tab(四键,ADR 0006)与档案(审计面)相对——只读不写,一切结论可回溯原始证据(哲学 1)。出处:frontend/src/pages/OpsPage.tsx(archive 子 tab:LedgerSection/PrecedentsSection/OpsPackagesSection)
- **表格统一件**:运营面表格的单一规范源(opsTable.ts 单源施加):列名映射(ops.col.* 中文词条,轮次表与台账表同集同套)、数字列右对齐、时间统一相对时间+title 完整戳、台账备注 key=value 人话化(title 留原文)——两表改一处同步生效,防两套 schema 漂移;台账 T4 冻结表头是契约冻结面,UI 措辞与之解耦。判例:#148 首创(轮次表),#149 档案台账表收编复用。出处:frontend/src/pages/opsTable.ts
- **节头**:运营面节的头行规范件(SectionHead):标题(+计数,空表不谎报不显)+右排次级动作(描边按钮,硬规④)同排;lead = 标题右邻内联件(非动作,如驾驶舱状态 chip);节头统辖其下唯一面板,从属不悬空;节级主操作(如「保存全部」)可实心——硬规④只辖次级。判例:#147 立规范件,#148 lead 扩展(状态 chip 内联),#149 计数/空态补齐。出处:frontend/src/pages/OpsSectionHead.tsx
- **UI 别名映射**:术语双层决议(2026-10-23 grill,ADR 0006):UI 层换常规词,机制层(文件名/代码/判例 schema)保留原词并映射——包→报告(只读渲染视图)/ 裁决→审阅(四键:同意·修改·忽略·稍后;忽略必填原因,原因即判例输入)/ 判例→规则 / 台账→历史;写回四律与判例闭集语义不变,四键是三动作的 UI 面。出处:docs/adr/0006(嵌套 docs 仓)、frontend i18n ops.* 词条(P1 落码)
- **三层职责线**(旧「提示词层/装配层/宿主层」;STANDARD 原语 P5;ADR 0007,2026-10-23):提示词层=进模型的系统提示内容(角色/回路/阶段门/反模式 tell/few-shot 指针,只判断);装配层=上下文构造(判例速查表预注入/按需检索/轮间 handoff 指针纪律——只指不复制防双源漂移,索引是地图不是存储);宿主层=模型外面的一切(轮次派生/工具白名单/沙箱断言/transcript 工件/retro 钩子/预算卡,只编排);职责线:宿主只编排不判断,提示词只判断不编排,脚本只测量不判断;调用权在宿主不在模型。理念八条律与审阅清单真源 = ops/agent/DESIGN.md。出处:DESIGN.md、ADR 0007(嵌套 docs 仓)、agent.mjs+tools.mjs、ops/agent/STANDARD.md 原语层(P5)
- **待审条目**:运营交互重构的新域对象(2026-10-23 裁,ADR 0006):结构化动作条目,v1 冻结十字段 {id, action, args, evidence, impact, rollback, dedup_key, severity, cause_group, status(active/snoozed/done/dismissed)};markdown 包降级为条目集的只读渲染,不再是审阅面。出处:backend/ipdb/_ops_items.py(存储/状态机)、backend/ipdb/_ops_review.py(四键审阅)、backend/ipdb/_ops_detectors.py(确定性产条)、docs/adr/0006
- **六条硬规**:运营面视觉验收基准(spec #146):①面板等宽通栏 ②数字列右对齐 ③中文术语统一(mono 数据/UI 文案分轨不变) ④次级动作一律描边按钮 ⑤accent 纪律 = 唯一绿 accent,红/琥珀仅事件性警示 ⑥空态用基准「暂无」式居中提示。执行纪律:DOM 测得出的走行为断言(role/aria/可见文本,不断样式类名);测不出的(基线/密度/accent/右对齐)走视觉复评门——截屏对照基准(公开页/源管理页)逐条对拍,零违规是合并裁决前置。出处:spec #146(票面)、frontend/src/pages/opsTable.ts(②⑥)、frontend/src/pages/OpsSectionHead.tsx(④)
- **轮次状态机**:健康轮的显式状态编排(P2 重造,spec #161;C 骨架)——十状态定义表(数据非代码:每态 name/是否模型步/工件清单/门/失败语义三元组;无工件无门无失败语义=不配当状态,加状态过 spec 变更;禁止嵌套子状态机),引擎=一份通用代码驱动全表;模型只在 TRIAGE/DEEP/SYNTH 三步,其余全确定性脚本步;任意步可 replay。STANDARD 原语 P2 同名骨架规则(旧单列词条已并入,见「改名对照」):宿主=显式状态机编排全轮,门全机检;单 agent 优化穷尽前不建多 agent(反多 agent 化默认);本条=其实现细则。出处:ops/agent/pipeline.mjs(HEALTH_PIPELINE)、ops/agent/STANDARD.md 原语层(P2)
- **阶段门**:状态转移的唯一裁判(不信模型自报):每门 =(工件文件集)→{pass,reason} 纯函数,reason 必带数字可回算,求值留痕 gates.json(门名/布尔/耗时/输入摘要)——门的判断本身可被人审;CLOSE 与 replay 全量重跑门(自愈:状态文件与工件不一致时以工件+门为准)。出处:ops/agent/pipeline/gates.mjs
- **筛后旗标集**:VERIFY 步去噪后进入分诊的旗标子集(冻结≥180 天/不可达);被抑制部分留痕于 02-verify-suppressed.json(抑制=证据降权不灭失,翻案可从工件回)。出处:ops/agent/pipeline/steps.mjs(VERIFY)
- **抑制规则库**:VERIFY 消费的人裁采纳规则闭集(DOCS_ROOT/ops/rules/suppressions.json;动作闭集 suppress|annotate,谓词闭集 bucket/url_shape/source/error_family,新增=spec 变更;每规则带 review_at 强制复审防磨烂);只有四键 adopt_rule 能写入(P5 闭环)。出处:同上;首批规则=P2 落地(10-23 两假异常人工判例转写)
- **微探针**:小改一个请求参数重发、分辨「真死还是假死」的复测工具。DEEP 步闭集变体复测工具(reprobe_get/reprobe_ua/upstream_check),辨探测伪迹(10-23 GeoLite 404 类:HEAD 假死 GET 实活);faux 面=P4 起 registry_seed 登记表面(G_DEEP 机检 ≤3 次/假设);真 provider 已接(#170:运行面 flash/glm-5.3 真调用),但真探针工具=下票——真面 DEEP 工具面为空(tools=[]),confirmed/refuted 证据支线需真探针登记表才能过 G_DEEP(设计内缺口,#170 报告注记)。出处:ops/agent/pipeline/gates.mjs(CLOSED_SETS.deep_tool/probe_hint)、fixtures/pipeline/deep/
- **源注解**:feeds.txt 清单行的行内 `# <source_name>` 注解——探测旗标归因到源的锚(VERIFY 在飞对齐/ITEMIZE 条目 dedup_key.source 都靠它);漏注解则回落 host 撞 SOURCE_RE 形状=ITEMIZE verify_failed 终态宁响亮。出处:ops/agent/lib.sh(extract_feed_urls -t)
- **零发现轮**:VERIFY 后零筛后旗标的健康轮预期常态(成本模型:零发现轮近零 token,成本跟异常走不跟日历走)。出处:ops/agent/pipeline/anchors.mjs、gates.mjs(G_TRIAGE 空集面)
- **回声防线**:replay/恢复路径不把原轮产物当新产物的防线族——VERIFY 排除原轮在飞条目、ITEMIZE 桥内 manifest 回声、RETRO replay 恒零写。转载回声的轮次版。出处:pipeline/steps.mjs、ops-items.mjs
- **引用不抄录**:深验步证据铁律(比稿 A 终裁并入 G_DEEP)——模型 evidence 只收 call_id+field 选择对、宿主回填值,复述值透传不静默纠正、写前语义门逐字对拍登记表,不符即门败。结构性消灭复述漂移(摘要员时代病灶)。出处:pipeline/gates.mjs(G_DEEP)、prompts/health/deep.md
- **保活任务**:无事可做的轮次里跑一条固定假想任务,证明回路还活着(空转保活裁定,三小裁①)——零 need_deep 轮 DEEP 仍跑一条 canned-假设 faux 回路(hid=golden-track-canned),零成本保回路活性;真 bundle 轮不得混入(G_DEEP 双向机检)。出处:pipeline/steps.mjs(deepFinalize)
- **同类错误归并**:把同类错误签名归并成一个家族的映射规则。error_signature 的族映射收敛(http_401/403→http_4xx→http_5xx→network→download 兜底),P1 探测器与管线 ITEMIZE 同 dedup_key 空间的同因拼写;条目摘要镜像钉=selftest 对拍 Python 金常量防两语言漂移。出处:pipeline/ops-items.mjs、backend/ipdb/_ops_detectors.py(_error_family)
- **门契约**:十门的清单/序/计数单源——`GATE_SEQUENCE`(=GATES 注册键序)/`GATE_COUNT`(=GATE_SEQUENCE.length,禁手写)/`GATE_NAMES` 全部派生自 pipeline/gates.mjs 注册表本体,消费方(run-golden/selftest-pipeline)一律 import;契约即注册表,分居两文件=伪单源。哨=注册键序↔HEALTH_PIPELINE 执行序双射不变式测试(临时加门/改序即红)。出处:ops/agent/pipeline/gates.mjs(GATE_SEQUENCE)
- **答案集镜像**:python 已知答案集(backend/ipdb/_eval/anchors.py ANCHORS)在 JS 侧的唯一镜像定义点 ops/agent/anchor-mirror.mjs(GOLDEN_SWEEP_ANCHORS 32 员+行键集 ANCHOR_ROW_KEYS 8 键{ip,expect,ok,reason,verdict,confidence,accusers,conflict}+anchorRow 构造器多写/漏写键即 throw=行键 fail-closed);镜像对拍哨(MIRROR)逐成员对拍 python 真源,行键哨(SHAPE)跨语言对拍键集——罐内自洽不算数,#189 桩漏 conflict 判例。出处:ops/agent/anchor-mirror.mjs
- **子步骤状态文件**:子步骤 = 月度大评测切出的子任务;本件记录每个子步骤跑没跑成。月轮十个子步骤(model/all/anchors/dsem/agg-share/sinkhole-probe/anchor-readouts/audit/temporal/readout)的逐子步骤执行状态工件 leg-status-*.json(子步骤代号/rc/时间戳),月报「进行中/子步骤红」节的唯一事实源;双写=render 前件(readout=null 在飞快照)+定稿件;缺省不出节(缺读数不虚构,schema-stable)。出处:scripts/monthly_eval.sh(write_leg_status)、backend/ipdb/_eval/monthly.py(load_leg_status/render_leg_status)
- **降级(轮次语义)**:失败语义三值(重试/降级/终态)之一——跳过可选步或标 unresolved 转人裁,轮仍成功(结果单 ok=true+stages 标 degraded,如 DISPATCH 预算截尾/DEEP 单假设 unresolved/RETRO 跳过);降级不是失败,与终态(九词闭集错误码)两回事。Avoid:「自愈闭环」「自动修复」(有人裁闸门,叫自愈是夸大)、「重试到底」(重试有上限,尽即终态或降级)。出处:ops/agent/pipeline.mjs(runStages 降级分支)
- **检索保底**(两词条 2026-10-31 合一,旧名见「改名对照」):保证任何概念检索不落空的两件套。①总索引=判例库 _INDEX.md(派生可再生缓存:概念判例一行一件,文件名+概念词+一行主张+关键词+状态;留痕判例不进)——库内任何概念至少一行 gist 常驻在场;rg 是精度工具,索引是召回保底;「索引是地图不是存储」(ADR 0007),判例文件才是唯一真源,spawn 前可再生。②判例速查表=anchors-health.json——按高频域(github 重定向假红/限流假面/abuse.ch 迁移/sunset/矩阵 park 残差/聚合器回声)预置域词→判例文件闭集,宿主从旗标读数确定性选判例(零模型),命中并入注入闭集且不越 HIT_CAP;判例指向缺件=编造路径,build-index --check 拒。出处:ops/agent/build-index.mjs、docs/ops/precedents/_INDEX.md(B稿 §2.2①)、ops/agent/anchors-health.json、ops/agent/pipeline/anchors.mjs(B稿 §2.2②)
- **判例转正通道**:同因人裁留痕 ≥2 且 ruling_agreement 一致(键并集:文本归一全等 ∨ 源身份词相交;superseded 链不计数防转载回声)→ retro/promotion-candidates/ 候选件(仅立项:三门槛=可机检/可证伪/非环境特异性以 pending 起步待人裁逐项核);人裁采纳(adopt_rule)才入概念判例,lineage 必列来源留痕(转载关系可回算);检测器永不写判例区。出处:ops/agent/promote-detect.mjs(B稿 §3.2)
- **通道错误四码**(STANDARD 原语 P1 失败表达纪律的码表细则,旧纪律词条已并入改名对照;原则:失败不编造、无证据≠清白、弃权/缺口不冒充零命中):外部通道(gh/rg)失败的结构化分类码——channel_missing(spawn ENOENT/rc=127,通道不在运行环境)/channel_auth(凭证缺失失效:not logged in/401/403)/quota(rate limit 限流)/transient(超时/网络,唯一可重试族,同参数 ≤1 次);判定优先级 channel_missing>channel_auth>quota>transient>原兜底(gh_error/rg_infra 兼容保留);每码文案自带「下一步合法动作」(对齐 MCP isError 语义 2026-07-28:错误要能引导模型自纠或升级)——前三码属基础设施/部署面不可轮内自纠,直接人裁区;trace.rc 恒 Number(ENOENT→127/超时杀→124)。判例:2026-10-24-discover-dual-channel-dead(容器无 gh 双通道全灭,失败不可诊断面)。出处:ops/agent/tools/envelope.mjs(classifyChannelError)、prompts/discover-system.md(结果单处置)、GLOSSARY 同批录入律
- **发现通道**:discover 轮的读向补全三薄工具 web_read(r.jina.ai markdown 正文,恒无鉴权头——实测 2026-10-24:裸调用正常,带欠费 key 反 402)/ web_search(pi-web-access 多 provider 网络搜索,2026-10-24 用户令;缺省路由 keyless duckduckgo 零配置一发即活,jina 经 agent-config tool_keys 扩槽配 key 后入回退链;路由配置单源 = web-search.json 物化进 ops 树 + PI_CODING_AGENT_DIR 指路,auth.json 同型判例)/ rss_parse(本地零依赖 RSS2.0/Atom 结构解析,新鲜门 RSS_FRESH_DAYS=30);与测量工具(fetch_url/gh_search/exclusive_probe/matrix)的边界=数据形状天然隔离:产出发现线索,不进谓词硬门数字与 MEASUREMENT_TOOLS(evidence 语义门不因此放宽);agent-reach 整只不进镜像(异构故障面违 few, sharp tools)。出处:ops/agent/tools/discovery.mjs(normalizeJinaRead/parseMcpSearchText/parseRss)、prompts/discover-system.md(动作面表)、DESIGN §6(2026-10-24 裁定)
- **发现轮**:发现侧(新情报源发现)的管线化轮型,round-id 后缀 `-discover`;六步 SCAN→SHORTLIST→MEASURE→ENQUEUE→RETRO→CLOSE 与运营轮同律(同宿主/同台账/同工件树形制)——SCAN/MEASURE 确定性零模型,SHORTLIST 模型产结构化候选,ENQUEUE 只写不动作(入 queue.md 候选卡,人裁终局);MEASURE 超时/不可达=uncertainty hold 不判死;入队判据(独占率≥0.25+证据存在性+阳性对照)是代码常量,模型无权改(ADR 0010)。出处:ops/agent/pipeline.mjs(DISCOVER_PIPELINE)、docs/adr/0010
- **加源轮**:加源侧(把已人裁点头的候选源实现进代码库)的管线化轮型,round-id 后缀 `-add`;六相位 VERIFY→DOSSIER→IMPLEMENT→GATE→REPORT→CLOSE——VERIFY/GATE 确定性零模型(验活+roster diff+鲜活度门 / 逐源测试+source_infra+审计),DOSSIER 薄卡补交接单(实抓样本/格式/auth/cadence/路由草案),IMPLEMENT 模型 TDD(先测试后源),REPORT 产沙箱分支+轮次信封;轮永不自并入 master(人裁终局,同发现轮 ENQUEUE 只写不动作);= SDD「实现者」环的自动化,评审面人裁;触发 = 人对 queue.md 候选卡 APPROVE(_ops_store 动作词闭集新增,写口仅人面)。出处:ops/agent-v2/tasks/add-round.mjs、docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md(#331)
- **分级钥匙**:加源基准的评分口径(#343,用户已批):每题得分 = 通过的测试函数数 / 总测试函数数(pytest 摘要行「M failed, N passed」→ N/(M+N)),取代旧二值钥匙(过=1/挂=0)作演化判据主面;旧制四扫(champion-1/cand-a-1/cand-c-1/heldout 双面,2026-11-12)即旧制末版,新旧不可直接比对——分级钥匙落地后冠军基线须重测一次才可继续比候选。二值面改作留档键(score_pass 0/1 并存,trial.json 双键)。分母单源 = repo 侧 `--collect-only -q` 函数数(collection error/超时/不可解析面的兜底分母);打分只回传计数不回传函数名断言(零泄漏面)。出处:ops/agent-v2/bench/add-domain/score.mjs(#343)、docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md 勘误节
- **发现管线**:发现轮(自动找新情报源的那轮)的六步执行本体与四道机检门——四门 G_SCAN(形状)/G_SHORTLIST(span 级逐字回引:quote 必须逐字见于 SCAN 工件 evidence 面,幽灵 URL/改写引文即拒)/G_MEASURE(宿主数字复算)/G_ENQUEUE(入队行⊆shortlist∩measure 合格面对账);span 级回引开源界零实现(2026-10 调研判语),判例自铸;OPS_DISCOVER_* 旋钮族独立(30 调用/3600s/¥5),月帽与运营轮共享(admitOrRefuse 同面)。出处:ops/agent/pipeline/gates.mjs(四门)、ops/agent/pipeline/citation.mjs(spanMatcher)
- **PROPOSE(提案动作词)**:queue.md 候选行的 action 词——发现轮管线产出的是提案非动作:ENQUEUE 步与候选卡统一写 PROPOSE(单源 ops/agent/pipeline/discover-candidate.mjs CANDIDATE_ACTION,一词一拼),与运营轮人裁动作词 ENQUEUE/REJECT(python _ops_store.QUEUE_ACTIONS 写面闭集)分立;发现轮写口不得复用 ENQUEUE 混淆「已入队动作」语义(#210 T4 统一判例)。出处:ops/agent/pipeline/discover-candidate.mjs(CANDIDATE_ACTION)、ops/agent/pipeline/steps.mjs(ENQUEUE 步消费)
- **验收标准(四层)**:运营 agent 的开发验收标准体系,分四层(ADR 0008,2026-10-24 用户确认;真源 STANDARD.md v0 = #181)——原语层(22 词,条文必须声明由哪些原语组成)→条文层(编号+判例链,EDD 开发环=头条)→门挂点层(CI/ops 轮/selftest 机检挂口)→标准答案集层(回归测试集);**挂不上验证手段的条目只能称建议,不得称标准**(反面教材=已知答案门死件;机检面=standard-check.mjs,挂 selftest 链)。结构词:条文五件套=编号+主张+原语组成+门挂点+判例链(缺一=伪标准形态);挂口族=门挂点层注册表(CI 挂点/selftest 伞/golden 回归/ops 轮门四族,挂点须落族内载体,嵌套 docs 仓路径禁作挂点)。外部依据只采 2026 源。Avoid:与相近词混用(保活任务=空转保活、golden fixtures=字节等价基线、裁决级已知答案=anchors.py 已知答案集,均非本词)。出处:ops/agent/STANDARD.md(典章真源)、ops/agent/standard-check.mjs(门挂点核对器)、docs/adr/0008(嵌套 docs 仓)、notes/ops-agent-golden-standard-research-2026-10-24.md
- **保底轨 / 爬坡轨**(旧名见「改名对照」):评测双轨语义(ADR 0008)——保底轨=标准答案集+行为探针,≈100% 通过才放行,持 CI+运营轮巡检(回答「agent 是否还能做会的事」);放行阈值≈100%(STANDARD 原语 P11,旧单列「回归门≈100%」已并入):近乎全对才放行,与爬坡轨低通过率起步爬坡分立,门面=CI golden+selftest+月轮 --anchors rc;爬坡轨=主指标(整体情报更准)爬坡观测,不持门;两轨阈值语义不同,不得互相原谅。出处:Anthropic evals 2026-01、docs/adr/0008、backend/ipdb/_eval/anchors.py(保底轨既有件,接线=租户批)、ops/agent/STANDARD.md 原语层(P11)
- **安静失败**:监控面板全绿而系统行为已错——标准可观测性(存活/延迟/错误率)抓不住语义级退化,须行为探针(活路径已知答案查询)代查(IEEE Spectrum 2026-04)。判例:已知答案门死件(8.8.8.8 被打恶而门不响)。出处:notes/ops-agent-golden-standard-research-2026-10-24.md(工业侧③)
- **发现固化**:生产事故与运营 finding 当天转可执行回归测试,人验签核(agent 提名、人裁终局)——学术判例 Agentic Auditing 2026-10(发现→可执行测试→人验,$2-3/轮)。首批标准答案=8.8.8.8/114DNS 判例。STANDARD.md 原语层 P13 词条=本词,同概念同判例(2026-10-24 终审修单统一拼写,典章内不再用「事故固化」拼法)。出处:docs/adr/0008 决策3、notes 研究学术侧①、ops/agent/STANDARD.md 原语层(P13)
- **预扣结算**(STANDARD 原语 P7;旧单列词条已并入,见「改名对照」):预算在动作前检查——reserve 后动作、settle 对账,事后 dashboard 不构成预算控制(Latentism 2026-10)。轮内=每步调用前检查预算并实报累计(budget_truncate 同语义),月度 kill switch 已接线(#199 交付A 双面准入)。出处:ops/agent/pipeline.mjs(budget_truncate)、ops/agent/STANDARD.md 原语层(P7)
- **预算四界**:整轮预算四机械界+同参拦——轮内模型调用数帽/轨迹 token 预算/墙钟超时/花费帽(每轮 ∧ 月度 kill switch)+工具调用哈希重复检测;单发线降为告警线(Formation 四界论 2026-09;STANDARD 原语 P15 面)。实现=#199 交付A:pipeline/budget.mjs readBudgetKnobs 单源(六 OPS_PIPELINE_* 旋钮),双点执法(步前准入+环内),读数面 09-budget.json+G_CLOSE 回声哨。出处:ops/agent/pipeline/budget.mjs、ops/agent/STANDARD.md 原语层(P15)
- **转载混淆**:变量不对齐产生的优势/印证是伪影——源派生重复计票(回声当印证)与算力不对齐的多 agent 优势(swarm tax:同 thinking-token 预算下多 agent 优势消失)同族;工业 eval 框架均不建模源转载关系,本仓独有标准条目。判例:114DNS cps+ziyadnz 假印证。出处:backend/ipdb/_logodds.py(dedup_lineage)、notes 研究(三向对撞表)
- **标准答案集**:已知答案回归测试集(STANDARD 原语 P10,faux 跑零 API 花费)——golden/cases.json 行为回路件+anchors.py 已知答案集(裁决级已知答案);生产事故与 finding 经「发现固化」入集,期望全对≈100% 才放行。出处:ops/agent/STANDARD.md 原语层(P10)、ops/agent/golden/cases.json
- **跨轮熔断**:按通道粒度跨轮累积的熔断器(STANDARD 原语 P16)——恰五通道闭集{gh_search,web_read,web_search,rss_parse,fetch_url}连续 3 次计数码失败(channel_missing/channel_auth/quota;宁少算:transient/infra 不计)即开断 6h,半开探活恢复;开断中调用=结构化 channel_open 结果单零 spawn。实现=#199 交付B:ops/agent/tools/breaker.mjs(ops/breaker.json 跨轮态原子写;坏文件 fail-closed 重置闭路不炸轮),快照入 09-budget.json readings.breaker。Pi Durable 迁移定稿(ADR 0012,旧尾条「熔断」已并入):仍为自有 breaker.json 文件、读写逻辑随迁,不 hook/memo 化;与预算四界同属自持执法面。出处:ops/agent/STANDARD.md 原语层(P16)、ops/agent/tools/breaker.mjs、docs/adr/0012(嵌套 docs 仓)
- **弃权校准**:弃权语义(无证据即无话)之外的校准度量(STANDARD 原语 P19,补课项)——弃权质量须 AUROC/ECE 分立评估(Cost-Aware Abstention 2026-10);度量缺,弃权语义已在。出处:ops/agent/STANDARD.md 原语层(P19)
- **OTel投影**:把每轮结果按 OpenTelemetry 的 GenAI 字段标准(semconv)导出一份只读遥测数据(STANDARD 原语 P20,缺;另票)——内部契约不动,投影=纯读派生。出处:ops/agent/STANDARD.md 原语层(P20)
- **跨轮级评测**:把多轮连续运行当整体评,分 Run/Trace/Thread 三级(STANDARD 原语 P21,缺;LangChain 2026-06)——单轮评测之上补「轨迹跨轮是否连贯」的读数。出处:ops/agent/STANDARD.md 原语层(P21)
- **失败归因图**:失败沿步骤依赖图回溯、定位到具体步骤或工具的方法(DeFA 式,STANDARD 原语 P22,缺)——多步 agent 误差沿依赖图分离定位到步/工具。出处:ops/agent/STANDARD.md 原语层(P22)
- **巡检发现三出口**:巡检发现(ANCHOR_SWEEP 读数 ok 且 finding>0)的三个出口(#184,spec #180 Q6)——gh issue(needs-triage 标签人裁终局,标准模板四件:来源步/已知答案:期望vs实得/证据指针/处置面)/告警 webhook(apprise CLI,env IP_RADAR_ALERT_URLS 与 backend _alerts.push 同 env 同形=双消费面;未配置=skip 留痕轮仍成功)/RETRO 摘要行(retro 工件 anchor_sweep 字段,G_RETRO 机检与 08 工件回算一致)。出口永不败轮(失败=失败结果单记入 08-anchor-sweep-exits.json+结果单 pipeline.finding_exits);dry-run 开关 OPS_SWEEP_DRY_RUN(默认关=真发;测试/golden 恒 1);replay 恒零外发(回声律同款)。**「出口只写不动作」红线**(票面钉死):从 finding 出发仅两写口——gh issue create 与 apprise 推送;无任何调权/停源/写数据面/源管理 API/规则库写口可达,由依赖面闭集结构性断言钉死(export 闭集恰三函数/spawn 目标恰 apprise/禁面符号零在场)。出处:ops/agent/pipeline/finding-exit.mjs、tools/measurement.mjs(ghIssueCreate)、tools/registry.mjs(GH_WRITE_SUBCOMMANDS)、票 #184
- **外发防重守卫**:外发崩溃窗防重发机制(#184)——出口工件先记 phase=emitting 再外发、终记 emitted;同轮重入见 emitting/emitted 一律不重发(崩溃窗内外发状态不可知,宁少算交人工核对:issue 重复开可人关,漏发下轮补);工件缺席=首程照发。与「回声防线」的分工:回声防线管轮间重放不产新产物,外发防重守卫管同轮恢复不重复外发。出处:ops/agent/pipeline/finding-exit.mjs(runFindingExits)
- **conversation**:会话——不可变 transcript 记录的宿主与提交面;运营轮宿主 = root conversation,子代理 = 自有 conversation(不共享主轮上下文)。Pi Durable 域词(ADR 0012)。出处:docs/adr/0012(嵌套 docs 仓)
- **task**:持久任务——相位化的工作单元,提交后由框架驱动至终态、进程崩溃可续;ops 管线轮(健康十态/发现六步)整体相位化为 task,失败三元组(重试/降级/终态)落 task 终态语义。Pi Durable 域词(ADR 0012)。出处:docs/adr/0012(嵌套 docs 仓)
- **checkpoint**:task 相位的持久快照——崩溃恢复的最小续跑点;v2 起替代旧管线的逐步状态持久面(词条已退役,见「改名对照」)。Pi Durable 域词(ADR 0012)。出处:docs/adr/0012(嵌套 docs 仓)
- **replay:safe**:工具崩溃恢复重放的安全声明(缺省 unsafe)——声明该工具重放不产生重复副作用,责任在工具作者;带外部写副作用的工具不得声明。Pi Durable 域词(ADR 0012)。出处:docs/adr/0012(嵌套 docs 仓)
- **轮次**:运营 agent 的一次完整任务运行(健康轮/发现轮同此基义;复合词轮次结果单/轮次状态机沿用)——Pi Durable 迁移定稿(ADR 0012):一轮 = 对 root conversation 的一次 submit(发现轮例外:一轮 = 一 ownerless 会话,tasks/discover-round.mjs:16-24 决策——旧发现轮每模型步全新 Agent 上下文、跨轮零渗漏旧律保持)。出处:docs/adr/0012(嵌套 docs 仓)、docs/superpowers/specs/2026-10-28-ops-agent-pidurable-migration-design.md(术语映射)
- **台账**:运营轮历史的留痕真源——旧管线自维护 ledger.md/queue.md;Pi Durable 迁移定稿(ADR 0012)= storage 里的 transcript+task 记录,ledger.md 降级为兼容输出面,不再作真源(RETRO 兼容行照写,见 ops/agent-v2/ENVELOPE.md),对下游的兼容输出(月轮评估)由 T5 承接;UI 别名「台账→历史」(ADR 0006)不变。出处:docs/adr/0012(嵌套 docs 仓)

## 已退役

- **轮次状态文件**:旧管线的状态机持久面(rounds/<round_id>/state.json)——每步边界原子写(temp+rename,沿 _ops_store 判例),boot 恢复与 replay 的单一事实源;轮次目录 rounds/<round_id>/(round_id=YYYY-MM-DD-HHMM-health),replay 产物写 <round_id>-r<seq>/ 原件零改写——ADR 0012 Pi Durable 迁移后由 checkpoint 取代。出处:ops/agent/pipeline.mjs(writeState/runReplay)、docs/adr/0012(嵌套 docs 仓)

## It's working if

- 讨论与 PR 描述直接用本表词汇("这是转载关系问题"),而不是每次从头解释
- 评审意见引用 AGENTS.md 哲学条目编号

## It's broken if

- PR 铸了新自造词但未同步本表
- agent 输出对「转载关系」「宁少算」等词的使用与词条定义矛盾
- 词条出处指向死代码(随 `codegraph init` 核对)
