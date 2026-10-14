# NEEDS — 信息需求台账

> **index, not a store**(一行一需求,细节在闭环指针处)。罗盘批定稿(grill 九问,2026-10-10):discover Step 1 普查在头,本台账为第一输入。**任何会话遇到"想问而无槽/答不出",记一行**;立项走 add-intel-source 时置"候选→已立项"。

状态:`open`(无路径或约束顶)| `候选`(本地源已验活,待立项)| `已立项` | `已闭`。"无源"结论均为注明日期的本跑结论,非永久断言——约束会松动,重扫有理。

| 想知道什么 | 首记 | 状态 | 闭环指针 |
|---|---|---|---|
| 查解析器 IP 说不出是什么(service) | <2026-10-10 | 已闭 | dns_public + root_servers,PR #97/#98(普查判例) |
| IP 所在时区 | 2026-10-10 | 已立项（2026-10-10 信息维度批，geolite harvest 透传） | GeoLite2 mmdb 自带 time_zone,harvest 现丢弃;库内扩展非新源(census 矩阵行 1) |
| IP 的注册分配元数据(RIR/分配日期/allocated·assigned·available) | 2026-10-10 | 已立项（2026-10-10 信息维度批，新源 rir_delegated） | rir_delegated:五 RIR delegated-extended,日更免登录(census 矩阵行 2) |
| IP 是否 IX 交换点 fabric | 2026-10-10 | 已立项（2026-10-10 信息维度批，新源 peeringdb） | peeringdb ixpfx:开放 API 批量落地,otx 先例(census 矩阵行 4) |
| ASN 的组织级名称(独立于 ASN 名) | 2026-10-10 | 已闭 | caida_asorg 已交付(PR #101,2026-10-10 双锚批) |
| rDNS 主机名 | 2026-10-10 | open | 红线:需在线解析;无免费批量反解库(2026-10-10 查证) |
| abuse contact | 2026-10-10 | open | RIPE DB bulk 重且仅部分 RIR |
| carrier / is_isp 出中国段 | 2026-10-10 | open | 无免费全球批量源(2026-10-10 两轮查证:IPinfo carrier 批量库 1.18MB CSV 存在但 standard 付费 token 档,无免费路径);现 cn_isp CN 限定单源 |
| is_mobile | 2026-10-10 | open | 无槽;商业专属(2026-10-10 查证) |
| vulnerable-system / misconfiguration(词表死槽) | 2026-10-10 | open | 唯一已知路径 = 类 7 扫描数据(Rapid7 门,见下) |
| IP 的开放端口/服务指纹/TLS | 2026-10-10 | open | Rapid7 Open Data:免费账号+research 许可+大文件,未立项 |
| TLD 权威服务器 | 2026-10-10 | open | CZDS 账号门槛 |
| NTP 基础设施角色 | 2026-10-10 | open | 仅三方小列表(jauderho,活但量薄);NTP Pool 无批量。2026-10-10 二轮:jauderho/public-ntp-servers(BSD-3,活)输出仅 hostname 键配置(ntp.toml/ntp-sources.yml),无 IP 面 → 需在线解析,红线拒 |
| anycast | 2026-10-10 | 已闭 | anycast_census 已交付(PR #101);anycatch 弃置维持:license 真空(无 LICENSE 文件、issue #5 追问 3.5 个月零回复、站点无 ToS,2026-10-10 查证),复活路径=书面许可 |
| ASN 业务类型(ISP/content/edu) | 2026-10-10 | 候选 | CAIDA as-classification 已死(官方 legacy、下载关闭,2026-10-10 查证);其真值本就是 PeeringDB 自报 info_type → 正路 = peeringdb 既有源扩展(org/net 端点 join,闸门判例),立项另裁 |
| 攻击者 IP 第一方测量(蜜罐/传感网) | 2026-10-10 | 已闭 | knock_knock 已交付(PR #104,blacklist=binarydefense 双生判例) |
| DDoS 攻击源 | 2026-10-10 | 已闭 | rtbh 已交付(PR #104,ddos 槽首个专职证人;许可用户签核 2026-10-10) |
| IP 是否研究扫描器(Censys/Shodan 等已知扫描段) | 2026-10-12 | 已立项（2026-10-12 eval 闭环批裁：真值层剔除同源语料污染，产品面同型呈现） | 官方公布段静态文件→attributes 通道，cdn.notice 同构判例；兼作威胁真值层排除清单（语料版本随附） |
| 我们输出的 verdict 在真实执法点(阻断/检测消费端)的 TP/FP 表现 | 2026-10-12 | open | 业界金标准 = 消费端反馈回流(ThreatConnect CAL 社区众包/MISP sightings/GTI 分析师纠正,docs/research/2026-10-12-industry-loop-practices.md);前置 = 产品需有消费 verdict 并能回报处置结论的执法点 + 查询隐私裁决,2026-10-12 用户记「后续想做」;本批以蜜罐锚+纠错检验作无遥测近似 |
| 土耳其政府 SGB 情报(siberguvenlik.gov.tr/api/address/index) | 2026-10-10 | open | JSON API,本轮未验活未取样;与 RTBH 同区域第二票,区域扩展时再验 |
| geo_asn/attributes 通道源的接入关读数口径(现走硬门得零信息报告) | 2026-10-13 | open | 对抗审查第1轮:读数覆盖域=threat/asset 两轴(verdict N/A-ASSET 早退+metrics 仅遍历 classifications),geo_asn 现役 7 源即此态;标量轴/排除清单覆盖率口径未裁,待用户(扩张 Q4/Q18 gate 覆盖域须裁) |
| 语料治理双缺口(固定复用过拟合+活语料漂移)如何治理 | 2026-10-13 | open | 对抗审查第1轮:固定语料逐月复用×声明 r 回流(人审 PR)=未申报适应性过拟合通道;四层误报侧语料含 dns_public 活抓取名单(seed 只冻采样不冻活列表)=尺漂移;候选机制=轮换/seed-bump 趋势重置、语料版本化+换版双跑,均须用户裁 |
| grace period(融合语义防抖) | 2026-10-12 | open | grill Q19 裁另立 NEEDS,industry 启示 5(docs/research/2026-10-12-industry-loop-practices.md) |
| 月轮 action block 对接指针 | 2026-10-12 | open | grill Q9:每轮 action block 在此留一行指针,裁毕置已闭 |
| 非 SSH 攻击类型(C2/DDoS/spam)的真值锚(威胁真值层现仅 SSH 攻击源) | 2026-10-13 | open | 对抗审查第4轮:多类型蜜罐/传感器语料候选;ADR 0002 已自认边界,不扩本批(第4轮 2026-10-13) |
| 资产弃权扩展评估 | 2026-10-13 | open | 闭环原型演示 A 的 recommended_action(asset-abstention-expansion-evaluation),Q9 指针机制仅覆盖月轮 action block,现无追踪落点(对抗审查第5轮)|
| 真值层再锚定策略 | 2026-10-14 | open | 静态 2024 语料只出不进(rir 剔除+长记忆淡出);候选=新蜜罐语料周期再锚/存活率预注册触发线;ADR 0002 语义不动(对抗审查第8轮 2026-10-14,照台账第4轮非 SSH 行先例只登记不裁) |
| 第13轮第三份对抗报告未入当轮宪章裁决 | 2026-10-14 | open | 台账 Round 13 节已预留补裁槽位;报告送达裁决员时须补裁,勿静默吸收 |
