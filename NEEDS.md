# NEEDS — 信息需求台账

> **index, not a store**(一行一需求,细节在闭环指针处)。罗盘批定稿(grill 九问,2026-10-10):discover Step 1 普查在头,本台账为第一输入。**任何会话遇到"想问而无槽/答不出",记一行**;立项走 add-intel-source 时置"候选→已立项"。

状态:`open`(无路径或约束顶)| `候选`(本地源已验活,待立项)| `已立项` | `已闭`。"无源"结论均为注明日期的本跑结论,非永久断言——约束会松动,重扫有理。

| 想知道什么 | 首记 | 状态 | 闭环指针 |
|---|---|---|---|
| 查解析器 IP 说不出是什么(service) | <2026-10-10 | 已闭 | dns_public + root_servers,PR #97/#98(普查判例) |
| IP 所在时区 | 2026-10-10 | 候选 | GeoLite2 mmdb 自带 time_zone,harvest 现丢弃;库内扩展非新源(census 矩阵行 1) |
| IP 的注册分配元数据(RIR/分配日期/allocated·assigned·available) | 2026-10-10 | 候选 | rir_delegated:五 RIR delegated-extended,日更免登录(census 矩阵行 2) |
| IP 是否 IX 交换点 fabric | 2026-10-10 | 候选 | peeringdb ixpfx:开放 API 批量落地,otx 先例(census 矩阵行 4) |
| ASN 的组织级名称(独立于 ASN 名) | 2026-10-10 | 候选 | caida_asorg:220k 行月更免登录;许可 add 时核(census 矩阵行 10) |
| rDNS 主机名 | 2026-10-10 | open | 红线:需在线解析;无免费批量反解库(2026-10-10 查证) |
| abuse contact | 2026-10-10 | open | RIPE DB bulk 重且仅部分 RIR |
| carrier / is_isp 出中国段 | 2026-10-10 | open | 无免费全球批量源(2026-10-10 查证);现 cn_isp CN 限定单源 |
| is_mobile | 2026-10-10 | open | 无槽;商业专属(2026-10-10 查证) |
| vulnerable-system / misconfiguration(词表死槽) | 2026-10-10 | open | 唯一已知路径 = 类 7 扫描数据(Rapid7 门,见下) |
| IP 的开放端口/服务指纹/TLS | 2026-10-10 | open | Rapid7 Open Data:免费账号+research 许可+大文件,未立项 |
| TLD 权威服务器 | 2026-10-10 | open | CZDS 账号门槛 |
| NTP 基础设施角色 | 2026-10-10 | open | 仅三方小列表(jauderho,活但量薄);NTP Pool 无批量 |
| anycast | 2026-10-10 | open | 无数据集(2026-10-10) |
| ASN 业务类型(ISP/content/edu) | 2026-10-10 | open | CAIDA as-classification 大概率可得,立项时验 |
