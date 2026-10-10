# NEEDS — 信息需求台账

> **index, not a store**(一行一需求,细节在闭环指针处)。罗盘批定稿(grill 九问,2026-10-10):discover Step 1 普查在头,本台账为第一输入。**任何会话遇到"想问而无槽/答不出",记一行**;立项走 add-intel-source 时置"候选→已立项"。

状态:`open`(无路径或约束顶)| `候选`(本地源已验活,待立项)| `已立项` | `已闭`。"无源"结论均为注明日期的本跑结论,非永久断言——约束会松动,重扫有理。

| 想知道什么 | 首记 | 状态 | 闭环指针 |
|---|---|---|---|
| 查解析器 IP 说不出是什么(service) | <2026-10-10 | 已闭 | dns_public + root_servers,PR #97/#98(普查判例) |
| IP 所在时区 | 2026-10-10 | 已立项（2026-10-10 信息维度批，geolite harvest 透传） | GeoLite2 mmdb 自带 time_zone,harvest 现丢弃;库内扩展非新源(census 矩阵行 1) |
| IP 的注册分配元数据(RIR/分配日期/allocated·assigned·available) | 2026-10-10 | 已立项（2026-10-10 信息维度批，新源 rir_delegated） | rir_delegated:五 RIR delegated-extended,日更免登录(census 矩阵行 2) |
| IP 是否 IX 交换点 fabric | 2026-10-10 | 已立项（2026-10-10 信息维度批，新源 peeringdb） | peeringdb ixpfx:开放 API 批量落地,otx 先例(census 矩阵行 4) |
| ASN 的组织级名称(独立于 ASN 名) | 2026-10-10 | 候选 | caida_asorg:220k 行月更免登录;许可 add 时核(census 矩阵行 10) |
| rDNS 主机名 | 2026-10-10 | open | 红线:需在线解析;无免费批量反解库(2026-10-10 查证) |
| abuse contact | 2026-10-10 | open | RIPE DB bulk 重且仅部分 RIR |
| carrier / is_isp 出中国段 | 2026-10-10 | open | 无免费全球批量源(2026-10-10 两轮查证:IPinfo carrier 批量库 1.18MB CSV 存在但 standard 付费 token 档,无免费路径);现 cn_isp CN 限定单源 |
| is_mobile | 2026-10-10 | open | 无槽;商业专属(2026-10-10 查证) |
| vulnerable-system / misconfiguration(词表死槽) | 2026-10-10 | open | 唯一已知路径 = 类 7 扫描数据(Rapid7 门,见下) |
| IP 的开放端口/服务指纹/TLS | 2026-10-10 | open | Rapid7 Open Data:免费账号+research 许可+大文件,未立项 |
| TLD 权威服务器 | 2026-10-10 | open | CZDS 账号门槛 |
| NTP 基础设施角色 | 2026-10-10 | open | 仅三方小列表(jauderho,活但量薄);NTP Pool 无批量 |
| anycast | 2026-10-10 | 候选 | ut-dacs/anycast-census(LACeS 主动测量 41,382 前缀日更 MPL-2.0)单源候选;bgptools/anycatch 弃置:license 真空(无 LICENSE 文件、issue #5 追问 3.5 个月零回复、站点无 ToS,2026-10-10 查证),复活路径=书面许可 |
| ASN 业务类型(ISP/content/edu) | 2026-10-10 | 候选 | CAIDA as-classification 已死(官方 legacy、下载关闭,2026-10-10 查证);其真值本就是 PeeringDB 自报 info_type → 正路 = peeringdb 既有源扩展(org/net 端点 join,闸门判例),立项另裁 |
