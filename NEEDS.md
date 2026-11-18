# NEEDS — 信息需求台账

> **index, not a store**(一行一需求,细节在闭环指针处)。罗盘批定稿(grill 九问,2026-10-10):discover Step 1 普查在头,本台账为第一输入。**任何会话遇到"想问而无槽/答不出",记一行**;立项走 add-intel-source 时置"候选→已立项"。术语与自造词定义见 [GLOSSARY.md](GLOSSARY.md)。

状态:`open`(无路径或约束顶)| `候选`(本地源已验活,待立项)| `已立项` | `已闭`。"无源"结论均为注明日期的本跑结论,非永久断言——约束会松动,重扫有理。

| 想知道什么 | 首记 | 状态 | 闭环指针 |
|---|---|---|---|
| 查解析器 IP 说不出是什么(service) | <2026-10-10 | 已闭 | dns_public + root_servers,PR #97/#98(普查判例) |
| IP 所在时区 | 2026-10-10 | 已立项（2026-10-10 信息维度批，geolite harvest 透传） | GeoLite2 mmdb 自带 time_zone,harvest 现丢弃;库内扩展非新源(census 矩阵行 1) |
| IP 的注册分配元数据(RIR/分配日期/allocated·assigned·available) | 2026-10-10 | 已立项（2026-10-10 信息维度批，新源 rir_delegated） | rir_delegated:五 RIR delegated-extended,日更免登录(census 矩阵行 2) |
| IP 是否 IX 交换点 fabric | 2026-10-10 | 已移除(2026-11-03 源下线,需求暂无证人) | peeringdb ixpfx:开放 API 批量落地,otx 先例(census 矩阵行 4;2026-11-03 用户裁决源下线) |
| ASN 的组织级名称(独立于 ASN 名) | 2026-10-10 | 已闭 | caida_asorg 已交付(PR #101,2026-10-10 双锚批) |
| rDNS 主机名 | 2026-10-10 | 已立项（2026-11-18 用户裁「不用询问了直接加进来」） | 2026-10-18 重扫:免费批量路径出现 = ip.thc.org 月度全量 parquet(49.5GB,HF+镜像双源实测活);ELLIO/InternetData/Rapid7 商业关门(docs/research/2026-10-18-rdns-abuse-contact-rescan.md)。2026-11-17 复验:日片 cs2 实测 327-345MB/日(旧认知 1GB 高估),掉片史(10-04/10-09 缺日)接入须缺片容忍。2026-11-18 用户裁:取消条款问询直接接入(许可文本缺失风险用户自担);装载范围=最新日片单面(约 40-60M 行/日,当前态 rDNS),30 天全量历史(1B 行小机重建)仍留行待裁 | 
| abuse contact | 2026-10-10 | 已闭 | rir_abuse 已交付(本 PR;RIPE+AFRINIC 全库 dump,RPSL 离线链 inetnum→abuse-c→role→abuse-mailbox);调研 docs/research/2026-10-18-rdns-abuse-contact-rescan.md |
| IP 注册组织名称/描述(org_name/descr) | 2026-10-18 | 已立项(本 PR,rir_abuse 扩展) | 同 dump 增量挖掘,org 槽+descr extra;调研 docs/research/2026-10-18-rdns-abuse-contact-rescan.md |
| carrier / is_isp 出中国段 | 2026-10-10 | 已立项(2026-11-18 用户裁「都进」) | 无免费全球批量源(2026-10-10 两轮查证);2026-11-17 复查维持商业面无门。2026-11-18 裁:gaoyifan/china-operator-ip 立项(MIT 日更,BGP 实际宣告派生=独立上游,与 cn_isp 的 APNIC 登记系互证;附带运营商 ASN 面;ispip.clang.cn 非新候选=cn_isp 上游本体,cn_isp.py:17 钉死,rrsi 聚合表命名误判防重犯);metowolf/iplist 有条件立项低优先(只取 ISP 六文件做第三链路互证,数据面许可空白注记待查人裁);chnroutes2 有条件立项低优先(CC-BY-SA 版本自相矛盾注记;补 CN 地理非 ISP 细分,BGP 双采集器互证) |
| netlas-free-iocs 观察位 | 2026-11-17 | open(观察) | CC0、86MB、ip 列现成,但宣称日更实测停于 2026-10-28(3 周);2026-11-17 用户裁:观察两周,12-01 复查 Last-Modified,恢复且持续才立项,再停划掉 |
| openasn 观察位(ASN 业务类型第二票) | 2026-11-18 | open(观察) | RouteViews+ipverse+人策修正派生(≠InsightFlare 的 RIPE 系),CC0,带 IP 级 verdict 面;但发布管线连红 4 周停于 2026-10-21,观察同 netlas 模式:复绿(连续 ≥2 次 nightly 成功、latest build_id 前进)即入队 |
| is_mobile | 2026-10-10 | open | 无槽;商业专属(2026-10-10 查证) |
| vulnerable-system / misconfiguration(词表死槽) | 2026-10-10 | open | 唯一已知路径 = 类 7 扫描数据(见下,已确认无免费源) |
| IP 的开放端口/服务指纹/TLS | 2026-10-10 | open(无免费源确认) | 2026-10-18 重扫:Rapid7 Open Data 已转 commercial Sonar Data(个人研究者出局+禁对外派生应答);2026-11-17 全查关行:scans.io 免登录面只剩 2021 论文档,Censys/Sonar 登录墙+明文非商用+TB 级与小机不兼容——免费批量源已确认无(2026-11-17 核验,docs 仓 research);新源冒头再开新行 |
| TLD 权威服务器 | 2026-10-10 | 已立项(2026-11-17 用户裁) | 免 CZDS 路径实测:root.zone 每日直下 internic.net 2.2MB(serial 2026111700),含全部 TLD 权威 NS 名+IP,无限制性条款——唯一零条件候选,走 add-intel-source 立项 |
| NTP 基础设施角色 | 2026-10-10 | 已闭(2026-11-17 用户裁弃) | 仅三方小列表(jauderho,活但量薄);NTP Pool 无批量。2026-10-10 二轮:jauderho(BSD-3)仅 hostname 无 IP 面 → 红线拒。2026-11-17:greyhat lists.d ntp TSV IPv4/IPv6 列齐但 CC-BY-NC-SA 非商用,用户裁弃;免费源仅 NC 许可,已评估弃
| anycast | 2026-10-10 | 已闭 | anycast_census 已交付(PR #101);anycatch 弃置维持:license 真空(无 LICENSE 文件、issue #5 追问 3.5 个月零回复、站点无 ToS,2026-10-10 查证),复活路径=书面许可 |
| ASN 业务类型(ISP/content/edu) | 2026-10-10 | 已立项(2026-11-17 用户裁) | CAIDA as-classification 已死;2026-11-17 用户裁走 InsightFlare/asn-blocklist(PeeringDB info_type 派生四类表,MIT,周更<250KB;FLAG=官方条款未核,派生镜像自担 MIT);停更两周切 ipverse/as-metadata 兑底(CC0 日更);不碰 PeeringDb 官方 bootstrap(11-03 下线裁未翻+AUP 禁商用) |
| VPN IP 的供应商标注(attribution) | 2026-11-18 | 已立项(2026-11-18 用户裁「都进」) | az0/vpn_ip 立项(GPL-3.0,日 2 更,20K+ IP 每条带供应商名,~25 家厂商 API 直采=独立上游,与 x4bnet 社区汇编互证;本地消费不触发 GPL 分发义务,档案记「禁对外再分发衍生」);融合层 dedup_lineage 按独立源记,防与 x4bnet 输入面重叠双计(宁少算) |
| 住宅代理骨干 ASN(residential proxy backbones) | 2026-11-18 | 已立项低优先(2026-11-18 用户裁「都进」) | iplogs.com/tools 仅取 6 张 curated 表(重点 residential-proxy-backbones 26 ASN、vpn-asns、datacenter-asns;CC-BY 4.0);11 个镜像面=上游回声不收(在册 Tor/云厂商已直连官方);curated 节奏 on-deploy 无 SLA,接受慢 |
| 攻击者 IP 第一方测量(蜜罐/传感网) | 2026-10-10 | 已闭 | knock_knock 已交付(PR #104,blacklist=binarydefense 双生判例) |
| DDoS 攻击源 | 2026-10-10 | 已闭 | rtbh 已交付(PR #104,ddos 槽首个专职证人;许可用户签核 2026-10-10) |
| IP 是否研究扫描器(Censys/Shodan 等已知扫描段) | 2026-10-12 | 已交付待合(SDD 批 PR #216:#212 源接入+#213 eval 排除+#214 标签钉测+#215 文档收口;ADR 0011;报告 docs/research/2026-10-26-scanner-ranges-census.md) | 官方公布段静态文件→attributes 通道,cdn.notice 同构判例;兼作蜜罐真值层排除清单(测试集版本随附);通道裁定=MISP warninglists -scanning 66 列表(CC0)+Xpanse 直读,80.2% 池内污染实测,grill 全裁 2026-10-26(恶意保持+「公开研究扫描/自报段」标签人裁;eval 测试集装配侧排除,ADR 0011;单批三件套);truth ops runbook 换源接线(legacy censys+Xpanse+Shadowserver 手合资产→scanner_ranges loader)留 ops 轮人裁 |
| 我们输出的 verdict 在真实执法点(阻断/检测消费端)的 TP/FP 表现 | 2026-10-12 | open | 业界通行标准 = 消费端反馈回流(ThreatConnect CAL 社区众包/MISP sightings/GTI 分析师纠正,docs/research/2026-10-12-industry-loop-practices.md);前置 = 产品需有消费 verdict 并能回报处置结论的执法点 + 查询隐私裁决,2026-10-12 用户记「后续想做」;本批以蜜罐真值层+独有指控核查作无遥测近似 |
| 土耳其政府 SGB 情报(siberguvenlik.gov.tr/api/address/index) | 2026-10-10 | 已立项(2026-11-17 用户裁) | 官方 API=在线查询红线不碰;2026-11-17 裁走 gorkemgun/sgb-blocklist 镜像(小时级,MIT,IP 按恶意类别分文件;FLAG=官方源条款未核,镜像仓 MIT 已核);bilsectr 同上游弃(TAXII 越红线且无增量优势) |
| geo_asn/attributes 通道源的接入关读数口径(现走硬门得零信息报告) | 2026-10-13 | open | 对抗审查第1轮:读数覆盖域=threat/asset 两轴(verdict N/A-ASSET 早退+metrics 仅遍历 classifications),geo_asn 现役 7 源即此态;标量轴/排除清单覆盖率口径未裁,待用户(扩张 Q4/Q18 gate 覆盖域须裁) |
| 测试集治理双缺口(固定复用过拟合+活测试集漂移)如何治理 | 2026-10-13 | 已立项(2026-10-14 eval 闭环 Phase 1 落地治理机制) | 对抗审查第1轮:固定测试集逐月复用×声明 r 回流(人审 PR)=未申报适应性过拟合通道;四层误报侧测试集含 dns_public 活抓取名单(seed 只冻采样不冻活列表)=尺漂移;已裁落地:测试集版本化(S12)+换版=趋势重置(S17)+run 级采样 seed(S36,月轮报告 v2 报头携带指纹变列);轮换/seed-bump 未采纳为独立机制 |
| grace period(融合语义防抖) | 2026-10-12 | open | grill Q19 裁另立 NEEDS,industry 启示 5(docs/research/2026-10-12-industry-loop-practices.md) |
| 月轮 action block 对接指针 | 2026-10-12 | open | grill Q9:每轮 action block 在此留一行指针,裁毕置已闭 |
| 非 SSH 攻击类型(C2/DDoS/spam)的真值来源(蜜罐真值层现仅 SSH 攻击源) | 2026-10-13 | 已立项(2026-11-18 用户裁「都进」) | 对抗审查第4轮;2026-11-01 honyport 已上线出数(ADR 0017 §2/§7,永不入池)。2026-11-18 裁:offseq/mirage-feed 立项(CC BY 4.0 日更 24h 延迟发布,多台蜜罐传感器网络经完整握手验证的多协议攻击者 IP,15 列含 ATT&CK/KEV/置信度,兼送 known-scanners 面;TLP:CLEAR 署名串入档)+ honeypot.fyi 立项(日更免登录,扫描/漏洞利用/UDP 真值;public unlicensed 注记)。C2 子需求仍缺证人:Feodo Tracker 数据集被执法清空(2026-03-04 冻结,官方 FAQ 自认 Emotet/Endgame 打击致空),abuse.ch 分发已 Spamhaus 化+API 配额;intercept.sh token 门槛+样例面 503 不开;新 C2 源冒头再记 |
| 资产弃权扩展评估 | 2026-10-13 | open | 闭环原型演示 A 的 recommended_action(asset-abstention-expansion-evaluation),Q9 指针机制仅覆盖月轮 action block,现无追踪落点(对抗审查第5轮)|
| 真值层再锁定策略 | 2026-10-14 | 已闭 | 真值层 v2 批落地(2026-11-01):ADR 0017(docs/adr/0017-truth-layer-v2-self-run-corpus.md,自建行为观测、90 天滚动窗口测试集接棒 Hornet 静态卷)+spec docs/research/2026-11-01-truth-layer-v2-spec.md+工单 #260/#261/#262/#263;静态 2024 卷过渡期留任对照,换卷=并排连续两轮 32 锚全绿+人裁执行;原开放因(静态卷只出不进/存活率触发线)由滚动窗口与换卷触发器消解 |
| 第13轮第三份对抗报告未入当轮宪章裁决 | 2026-10-14 | open | 台账 Round 13 节已预留补裁槽位;报告送达裁决员时须补裁,勿静默吸收 |
| 全量变异测试(mutator)在本仓的成本可接受吗(若试仅限融合核心) | 2026-10-31 | open | ub-mode 评估(notes/ub-mode-2026-10-31.md);code-metrics skill 已挂缓议 |
| 「我的推荐:」冒号后的内容被截断(模型输出侧,不易在应用层修) | 2026-11-04 | open | 同一问题三次复发(2026-11-04 #303 登记);换模型后比对是否仍现;呈现侧改列表化可绕过 |
