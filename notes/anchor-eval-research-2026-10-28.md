# 已知标签 IP 锚点扩展 —— 源普查与证据底座调研稿(2026-10-28)

> 状态:只读调研草稿。理论文献腿(经典:Axelsson / McHugh / Durumeric USENIX'15 / Metcalf & Spring)由父会话并行承担,见配套稿 `anchor-eval-theory-2026-10-28.md`(DOI 已核),本稿不重复。
> 获取方式注记:本稿全部事实经 ① exa 网页搜索(MCP)② r.jina.ai 网页读取 ③ 本地代理 curl 直接拉取官方 JSON/文本端点(命令级"批量静态下载"实测)④ GitHub API(gh)核 MISP warninglists 上游面。凡未直接核到原文的一律标注 UNVERIFIED,不编造。
> 检索日期:2026-10-28。示例数据快照均当日实测(标注"实测")。

---

## A. 锚点维度普查

### A0. 总判(先给结论)

- 厂商自公布 infra/edge 段(A1)几乎全部满足**批量静态下载、无鉴权、机器可读**,是最容易落地的属性真值锚;唯一例外 Akamai(需 API 凭证)。
- 研究/良性扫描名单(A2)呈三层结构:**厂商自报页(Censys/BinaryEdge/Stretchoid/UMich)** → **社区维护镜像(MISP warninglists,~30 个 *-scanning 列表)** → **第三方运营观测面(SANS ISC DShield threatlists,每日 JSON)**。三层谱系重叠严重,接入时须防同源重复计分(「宁少算」哲学)。
- RPKI(A3)提供 prefix→ASN 合法性真值,规模约 **102MB/百万级 ROA**,纯静态可拉。
- sinkhole(A5)有一个现成公共锚:**MISP warninglists `sinkholes` 列表(203 项)**——仓库既有 66+1 表体系内已有,接入成本最低。
- 根服务器段(A6)实测 13 个根 A 记录可直接从 internic.net root.zone 批量拉取,干净锚扩员的最低垂果实。

### A1. 厂商自公布 infra/edge 段

用途定位:**属性真值锚(hosting/CDN/cloud)** + 争议子层成员;**非绝对干净锚**(云 VM 可真实沦陷、可被租户滥用)。

| 厂商 | 官方 URL | 获取方式 | 许可 | 更新节奏 | 规模(实测 2026-10-28) | MISP 重叠 |
|---|---|---|---|---|---|---|
| Cloudflare | https://www.cloudflare.com/ips/ 页;https://www.cloudflare.com/ips-v4 纯文本 | 批量静态下载(实测 curl 直拉) | UNVERIFIED(页面无明示许可条款) | 无固定公告节奏,随网络变更 | ips-v4 = 14 段(实测) | MISP `cloudflare` 列表 22 项(v4+v6,ver 20261014)已覆盖 |
| Google(全量) | https://www.gstatic.com/ipranges/goog.json | 批量静态下载(实测) | UNVERIFIED(JSON 无许可字段) | 文件含 syncToken+creationTime,随变更滚动发布 | 148 prefixes(实测) | MISP `google` 列表是**域名**列表(7556 项),非 IP,勿混 |
| Google Cloud | https://www.gstatic.com/ipranges/cloud.json | 批量静态下载(实测) | UNVERIFIED | 同上 | 1135 prefixes(实测) | MISP `google-gcp` 479 项(明显滞后/子集) |
| AWS | https://ip-ranges.amazonaws.com/ip-ranges.json | 批量静态下载(实测) | JSON 实测已无 `license` 字段;官方文档页含许可条款(原文未抓到,UNVERIFIED,入口 https://docs.aws.amazon.com/vpc/latest/userguide/aws-ip-ranges.html) | createDate 字段实测 2026-10-28-08-07-05,即**每日级滚动** | 10690 IPv4 + 7006 IPv6 prefixes(实测) | MISP `amazon-aws` 4083 项(滞后/子集镜像);直接用官方源更准 |
| Azure | 微软下载中心 id=56519:《Azure IP Ranges and Service Tags – Public Cloud》,https://www.microsoft.com/en-us/download/details.aspx?id=56519 | 批量静态下载,但文件名带日期(ServiceTags_Public_20261019.json,4.6MB),**无稳定裸 URL,需解析下载中心页** | 微软下载中心条款(原文未核,UNVERIFIED) | **每周发布**(实测页面 Version 2026.10.19 / Published 10/20/2026) | 4.6MB JSON(未展开计数) | MISP 树中无 azure 镜像(2026-10-28 main 树 grep 确认) |
| Apple | https://mask-api.icloud.com/egress-ip-ranges(Private Relay 出口段);说明页 https://developer.apple.com/icloud/prepare-your-network-for-icloud-private-relay/ | 批量静态下载(本机代理直拉返回空,经第三方佐证端点存在;标⚠️ 待复测) | UNVERIFIED | 未核 | 未核 | MISP `apple-ipv4` 5 项(ver 20260829);`apple-domains` 为域名列表 |
| Fastly | https://api.fastly.com/public-ip-list | 批量静态下载(实测,无鉴权 JSON `addresses`) | UNVERIFIED(techdocs 未抓到明示条款) | 未核(列表为静态快照式) | 数十段(实测,含 151.101.0.0/16 等) | MISP `fastly` 21 项镜像 |
| Akamai | MISP `akamai` 346 项(ver 20261014)存在;官方面为 techdocs 的 Edge IP ranges API,**需 API 凭证** | per-auth API(非匿名静态) | UNVERIFIED | 未核 | 346 项(MISP 面) | 已被 MISP 覆盖,官方直连性价比低 |

小结:A1 全家可作为「hosting 属性真值 + 争议子层」一体的锚族;**重叠风险主因 = 我们已有 scanner_ranges 之外的 MISP 镜像层**,建议锚库直接引官方源、MISP 镜像仅作谱系注记,避免双算。

### A2. 良性/研究扫描名单

三层谱系(官方自报 → MISP 镜像 → ISC 观测面):

1. **Censys(官方自报,最规范)** — opt-out 文档页直接给出防火墙段清单,原文(2026-10 exa 快照):18 个 IPv4 CIDR(66.132.159.0/24 … 206.168.35.0/24)+ 4 个 IPv6 段 + 3 个 ASN(AS398722/AS398705/AS398324),并注明 HTTP 扫描带 Censys 专用 UA。URL:https://docs.censys.com/docs/opt-out-of-data-collection。批量静态下载(网页即清单)。许可 UNVERIFIED(文档站条款未核)。重叠:MISP `censys-scanning` 23 项镜像;SANS ISC `threatlist/censys`(每日 JSON,实测带 firstseen/lastseen)。
2. **BinaryEdge(官方自报)** — https://api.binaryedge.io/v1/minions,实测返回 JSON `{"scanners":[...单 IP 列表...]}`,无鉴权。粒度=单 IP 而非 CIDR。重叠:MISP `binaryedge-scanning` **12972 项**镜像(明显比 minions 活面宽,含历史)。
3. **Stretchoid(Salesforce)** — 官方自报页 https://stretchoid.com。重叠:MISP `stretchoid-scanning` **5039 项**(描述注明由第三方追踪页面维护,谱系注记:非官方一手→镜像层可能混入观察者推定);SANS ISC `threatlist/stretchoid` 实测有数据。
4. **Shodan** — 官方无简单匿名 CIDR 清单(enterprise 有 `internet-scanners` bulk 数据集,见 https://book.shodan.io/enterprise/bulk-data-files/,付费);社区面:SANS ISC `threatlist/shodan`(每日 JSON,实测含 71.6.146.x 等);MISP `shodan-scanning` 104 项(ver 20261014)。**重叠注记:ISC shodan 列表实测含 71.6.146.186(Rapid7 Project Sonar 段)→ 说明 ISC 观测面本身有跨源污染/归因粒度粗的问题,做锚时宜用厂商自报层,ISC 仅作观测佐证。**
5. **Rapid7 Project Sonar** — MISP `rapid7-scanning` 11 项(ver 20261014);第三方佐证:maltrail 静态 mass_scanner.txt 中大量 71.6.233.x 标注 `scanners.labs.rapid7.com`。官方自报原文面(sonar FAQ)未直接核到 → UNVERIFIED(引 MISP 镜像 + maltrail 佐证)。
6. **GreyNoise RIOT — 红线警示案例** — 原 GitHub 开源库 `GreyNoise-Intelligence/riot` 已下线(2026-10-28 实测 gh api 404);已演化为 GreyNoise 付费/社区 **API 数据集"Business Services Intelligence (formerly RIOT)"**(https://docs.greynoise.io/docs/riot-data)。**获取方式=per-query API(社区免费档限速),不再有批量静态数据面 → 按纯本地红线不可直接接入**;其三级 trust level 分类设计是 C 腿的重要质控实践(见 C 节)。
7. **大学研究扫描段** — ZMap 责任扫描页 https://zmap.io/responsibility/ **已 404**(2026-10-28 实测,GitHub Pages 报 File not found)→ 该任务书假设的上游已失效,改引各校自报页:Michigan ECE https://ece-scan.eecs.umich.edu(实测给出 opt-out 段 **141.213.13.192/28**,含研究伦理声明原文);MISP main 树另有大量大学/研究扫描列表(academyforinternetresearch-scanning、alphastrike-research-nt-scanning、internetmeasurementresearch-scanning、internetresearchproject-scanning、modat-scanner、researchscanner-scanning、securityresearch-scanning 等,完整清单见 A2 附注)。Michigan/Merit/RWTH Aachen/Max Planck 的专用列表在 2026-10-28 main 树 grep 未命中(旧文档记忆可能对应早期 warninglists 或已改名)→ 以实树为准,勿引旧名。
8. **SANS ISC DShield threatlists(观测面层)** — API:https://isc.sans.edu/api/threatlist/{name}?json(佐证:SANS ISC diary 23113)。实测 shodan/censys/binaryedge/stretchoid 四源活,单 IP 粒度带 firstseen/lastseen,每日更新;`research` 等泛化列表实测返回空。用途=扫描正例锚的**独立第三方观测交叉**(注意第 4 条的重叠污染注记)。
9. **Recorded Future** — 自报扫描段 UNVERIFIED(本轮 exa 一次 405 未复查,检索贫化,如实记缺口)。

A2 附注(MISP *-scanning 全量,2026-10-28 main 树):academyforinternetresearch-scanning / alphastrike-research-nt-scanning / binaryedge-scanning / censys-scanning / internetcleanup-scanner / internetmeasurementresearch-scanning / internetresearchproject-scanning / modat-scanner / onyphe-scanner / research-scanner-nt-scanning / researchscanner-scanning / rootevidence-scanning / securityresearch-scanning / rapid7-scanning(+rapid7-nt-scanning) / shodan-scanning(+shodan-nt-scanning) / stretchoid-scanning / sinkholes(归 A5)。**这批与既有 scanner_ranges(MISP 镜像)是同一上游家族,扩展锚库时按谱系去重。**

### A3. RPKI / 路由真值(prefix→ASN 合法性)

- **Cloudflare rpki.json**:https://rpki.cloudflare.com/rpki.json,实测 HTTP 200、Content-Length **107,164,488 字节(≈102MB)**、text/plain。门户页 https://rpki.cloudflare.com/ 实时显示 "Found 1,042,780 ROAs in the global RPKI system",并声明 **"The RPKI Portal is made available solely for informational purposes."**(用途定位原文)。数据引擎为开源 OctoRPKI(https://github.com/cloudflare/cfrpki,官方 README 原文:"It is the data provider behind (including the rpki.json)")。
- **本地验证器路径**:Routinator(NLnet Labs,https://www.routinator.net/,实测 gh api license=BSD-3-Clause,pushed 2026-10-27,活跃维护)——本地 RRDP/rsync 拉 RPKI 仓库 + RTR server,天然满足纯本地红线;或 rpki-client(OpenBSD 系)。
- 锚类型:**路由合法性真值**(prefix→ASN 是否有 ROA、maxLength 是否匹配),非行为指控。规模:百万级 ROA;更新:RPKI 仓库滚动发布(rpki.json 重生成频率未核,UNVERIFIED)。
- 许可:ROA 对象本身是 RIR 签名公开对象;Cloudflare 门户 "informational purposes" 声明如上 → 商用条款 UNVERIFIED。

### A6. 根服务器 / DNS 基础设施段(干净锚扩员)

- **官方数据**:root zone 文件 https://www.internic.net/domain/root.zone,实测 24976 行、**13 个根服务器 A 记录**(如 198.41.0.4 = a.root-servers.net)、**1438 条 NS 记录**(即全部 TLD 权威 NS 段面)。批量静态下载(实测)。概览:https://root-servers.org/(jina 抓取本轮空,站点存活)。
- 许可:IANA/PTI 运营的事实数据,未见明示许可条款(UNVERIFIED);更新=root zone 持续变更(internic 每日重发布,具体节奏 UNVERIFIED)。
- 锚类型:**绝对干净锚扩员**——13 根 letter 地址(及其 anycast 实例段)是全网最强"永不应上榜"候选;TLD NS 地址段(约 1438 个 NS 主机)为次级候选(变更少、属公共 DNS 基础设施,但个别 TLD 运营争议存在,建议只取根 letter 层为一级锚)。


### A4. 暗网望远镜 / 背景辐射(darknet / network telescope)

- **UCSD CAIDA Network Telescope**:项目页 https://www.caida.org/projects/network_telescope/。数据目录实测 22 个数据集(含 UCSD Network Telescope Aggregated Flow Dataset、UCSD Real-time Network Telescope(2020-04 起)、Telescope Darknet Scanners(2016-06)等;2026-10-28 exa 快照)。**获取可行性:非自助批量**——经 CAIDA catalog 申请 + 接受 AUA(补充协议)。许可原文(Acceptable Use Agreement — Supplement,https://www.caida.org/about/legal/aua/caida_telescope_aua.html):"You agree that you will not copy from CAIDA servers or otherwise transfer, distribute, or disclose raw NRTT data or any derived data with identifying or sensitive information without written authorization from CAIDA management." 以及禁止对数据集中 IP 主动接触:"You are not permitted to attempt to connect to, probe, or in any way initiate contact with a machine … identified … within the dataset(s), without written authorization." → **红线判读:即使接入,也禁止再分发原始数据与主动探测库内 IP;只能以聚合/匿名形态用于本地评测**。
- **Team Cymru 暗网社区数据**:概念与用途见其 Darknet 页(https://web.archive.org/web/20180701152349/https://www.team-cymru.com/darknet.html,原文:"Any packet that enters a Darknet is by its presence aberrant.");现行社区共享入口为其 Global Defender Exchange(https://www.team-cymru.com/global-defender-exchange,注册制社区)。**获取可行性:中低(机构合作/注册),现行数据条款 UNVERIFIED**。
- **对本系统的锚价值判读(重要)**:望远镜是"被动收包"侧数据,IP Radar 是 per-IP 静态情报面,二者不是同型数据;望远镜的核心可移植价值是**污染探针构造法**——回散源 IP 是被 DDoS 放大器伪造的随机/受害地址,**任何把回散源当"攻击者"上榜的 feed 都在该维度可证伪**(实证见 C 节银行 spoofing 事件与 MADWeb'25 论文:望远镜 252,879 个地址中 71.24% 至少进过一个 blocklist,而其中含大量无辜回散/扫描源)。

### A5. sinkhole 污染探针

- **现成公共锚:MISP warninglists `sinkholes` 列表** —— 实测 203 项,type=cidr,category=known,描述仅 "List of known sinkholes",**上游 provenance 未在元数据给出(UNVERIFIED,系 MISP 社区维护)**。已在既有 66+1 表体系内,接入成本最低。version 20261014。
- **abuse.ch**:Feodo Tracker(https://feodotracker.abuse.ch/)ipblocklist.json 实测字段:`ip_address / port / status(online|offline) / hostname / as_number / country / first_seen / last_online / malware`——**无显式 sinkhole 标志字段**;sinkholed C2 会以"online"形态混在 C2 榜里(托管方=安全厂商)。abuse.ch 自营 sinkhole 的公布段面:未核到 → UNVERIFIED。
- **Microsoft(DCU)/Google sinkhole 公布面**:本轮负向检索未完成(时间预算),**UNVERIFIED**——开放问题。
- **探针语义**:「把 sinkhole IP 当 C2 上榜」是威胁 feed 的已知 FP 模式;评测构造 = 指控源命中 sinkhole 段 → 记污染分(而非恶意分)。配合 C 节银行 spoofing 判例:sinkhole 段 + 高知名干净段共同构成"指控必须解释"层。

### A7. 既有源复用注记(PeeringDB / cloud_ranges)

- **PeeringDB**(仓内已有源,IX/facility 段):许可**不是**自由批量——AUP 原文(https://www.peeringdb.com/aup):"The PeeringDB data may not be passed on in bulk to any other person or organization unless approved by PeeringDB." 且全库下载限定 "Internet operational issues" 用途(明文包括 network trouble-shooting, abuse reporting, and Internet research and analysis)。→ 判读:IP Radar 本地评测用 IX 段做属性真值锚属"research and analysis"范畴,**合规风险低,但禁止把库数据再分发**;锚化动作零增量数据获取。公共数据面 public.peeringdb.com 存在,条款 UNVERIFIED。锚类型:属性真值(IX/托管设施)。
- **cloud_ranges**(仓内既有源):厂商段聚合,与 A1 同族——锚化=直接升格为属性真值锚 + 争议子层,无新获取动作;谱系注记:若 A1 官方源与 cloud_ranges 同时入库,须做同源去重(「宁少算」)。

---

## C. 实践依据

1. **GreyNoise RIOT → Business Services Intelligence:known-benign 质控实践演化(本腿最核心证据)**。官方文档(https://docs.greynoise.io/docs/riot-data)要点:① 数据面追踪 "CDNs, update servers, public DNS and NTP services, SaaS APIs, and cloud security products" 的 IP 空间;② 维护方法原文:"Our engineering and research teams have implemented several tactics and methods to acquire, track, curate, and age off RIOT data over time."(采集-追踪-策展-老化 四段生命周期,与 ADR 系"新鲜度"关切同构);③ **三级 trust level**(Level 1/2/3,按业务基础设施归属给信任分);④ 明确边界声明原文:"Business Services Intelligence is not a safe list or allow list and should not be used as a network Access Control List." —— 对我们的启示:known-benign 锚的正确产品语义是"读数/降权依据"而非"白名单",与「测量建言,人裁终局」哲学一致;⑤ **获取已 API 化(per-query),开源库已下线(实测 404)→ 红线上不可接入,只可借鉴方法论**。
2. **蜜罐/运营者区分研究扫描器的公开做法(三层标准实践)**:① 厂商自报段预过滤:Censys opt-out 段(A2 第 1 条)、UMich ECE 自报页原文伦理声明("We never attempt to exploit security problems, guess passwords, or change device configurations.",https://ece-scan.eecs.umich.edu/);② 观测面订阅:SANS ISC 向运营者提供每日更新的已知扫描器清单并建议直接做防火墙规则(ISC diary 23113,https://isc.sans.edu/diary/23113,原文:"We do create a list of these IP addresses and update it daily.");③ 文献侧:Deri & Fusco 2023 在扫描检测中明确排除 80/443 防 web crawler 误判("In order to avoid web crawlers being classified as scanners, traffic on destination TCP ports 80 and 443, are not considered.",https://arxiv.org/html/2308.08356v1)。→ IP Radar 的「研究扫描」标签 + eval 真值层排除设计与此三方实践同构。
3. **威胁 feed 评测以蜜罐为真值的先例(Hornet 65 Niner 之外)**:
   - Deri & Fusco,《Evaluating IP Blacklists Effectiveness》(arXiv:2308.08356,2023):三个大型生产网数十万主机被动监测评测黑名单;结论倾向 precision 调优导致 scanning 类恶意完全漏检;并正面讨论"蜜罐 vs 被动监测"的 FP/FN 权衡("with this setup we have very limited, if any, false positives")。
   - 《Towards Continuous Enrichment of Cyber Threat Intelligence: A Study on a Honeypot Dataset》(IEEE/ATHENE·M4D,2022,https://m4d.iti.gr/wp-content/uploads/2022/12/Towards-Continuous-Enrichment-of-Cyber-Threat-Intelligence-A-Study-on-a-Honeypot-Dataset_accepted_v02.pdf):Dionaea 蜜罐 345 起事件为样本,用 AbuseIPDB(阈值 75)+ VirusTotal 构造 ground truth 标签——**警示:这是"用商业 reputation 当真值"的循环引用实例,恰是 IP Radar「谱系派生双算」哲学要在融合层防的坑**。
   - 《Can Public IP Blocklists Explain Internet Radiation?》(MADWeb 2025,https://doi.org/10.14722/madweb.2025.23009):以望远镜观测为真值反评 blocklists——252,879 个望远镜地址仅 28.76% 从未进任何 blocklist;blocklists 倾向在源活跃数日内收录。→ A4 锚价值判读的文献支撑。
4. **Spamhaus DROP/EDROP:段级指控语义的政策原文**。政策页(https://www.spamhaus.org/drop/)实测原文:"Don't Route Or Peer (DROP) lists the worst of the worst IP traffic. It is an advisory 'drop all traffic', containing IP ranges which are so dangerous to internet users that Spamhaus provides access to anyone who wants…" 数据文件实测(https://www.spamhaus.org/drop/drop.txt,2026-10-28):1765 行(含注释),每段挂 SBL 案号(如 `1.10.16.0/20 ; SBL256894`),头部带 Last-Modified/Expires(约小时级重发布);**EDROP 文件头实测声明已并入 DROP**("This list has been merged into https://www.spamhaus.org/drop/drop.txt")。版权行:"(c) 2026 The Spamhaus Project SLU";另有 DROP Fair Use Policy(菜单可见)。→ 语义判读:DROP 是 **netblock 级"犯罪控制/劫持"指控**(带案号可溯源),与 per-IP 事件榜语义不同——融合进评分时必须走不同合并策略维度,且不可当作行为频率证据。
5. **公共解析器/旗舰干净 IP 被自动化误伤的事故记录**:
   - **Cloudflare Gatebot 自伤 1.1.1.1(2018-05-31,实证)**:官方事故复盘(https://blog.cloudflare.com/today-we-mitigated-1-1-1-1/)原文:"our systems interpreted the resolver traffic as an attack… This caused 1.1.1.1 DNS resolver to be globally inaccessible"(17 分钟)——即使是基础设施运营者自己的自动化,也会把旗舰干净段(1.1.1.0/24、1.0.0.0/24)判为攻击;这正是"旗舰公共基础设施 IP 必须进干净锚"的直接证据。
   - **Spamhaus DNSBL × 公共解析器系统性摩擦(实证)**:security.stackexchange #187385(https://security.stackexchange.com/questions/187385/)记录 1.1.1.1 与 8.8.8.8 在 cbl.spamhaus.org 查询返回记录——机制为经公共解析器查询 DNSBL 会得到错误/封禁返回码被工具误读为"被列"(Spamhaus 官方亦公开要求公共解析器用户迁移到其 Data Query Service,https://www.spamhaus.org/resource-hub/email-security/if-you-query-the-legacy-dnsbls-via-cloudflares-dns-move-to-spamhaus-technologys-free-data-query-service/)。
   - **8.8.8.8 被公共黑名单持久误列的厂商级一手记录:UNVERIFIED**(负向检索注记:exa 同义词族检索最高质量命中即上两条;未发现 RFO/官方公告)。
   - **spoofed-source 污染实证(负向检索族命中,强证据)**:CAIDA DDoS-ASPIRE 项目结题报告(https://www.caida.org/funding/ddos-aspire/ddos-aspire_finalreport.pdf)记载:2019-04,攻击者以**伪造的大型美国银行网站 IP** 做可疑扫描,"so that the addresses appeared on blacklists… caused security products to block the bank's addresses"——无辜高价值干净 IP 经 spoofing 进入黑名单的真实判例,直接支撑「污染探针」维度与「无证据≠清白」的措辞纪律。

---

## B. 理论轻量补(2020+ 黑名单/threat feed 评测方法学,仅 4 条,全引)

1. **HADES Attack: Understanding and Evaluating Manipulation Risks of Email Blocklists**,NDSS 2025。DOI: https://doi.org/10.14722/ndss.2025.242156 —— 黑名单本身可被操纵(评测须考虑投毒面),对锚点体系的攻击面假设有直接参考。
2. **Clairvoyance: Inferring Blocklist Use on the Internet**,PAM 2021。DOI: https://doi.org/10.1007/978-3-030-72582-2_4 —— blocklist 使用生态测量;锚点选择要考虑"哪些榜在被谁使用"的生态结构。
3. **Deri & Fusco, Evaluating IP Blacklists Effectiveness**,arXiv:2308.08356,2023。https://arxiv.org/html/2308.08356v1 —— 大规模生产网被动监测型 feed 评测方法(蜜罐替代法,FP 极小化设计)。
4. **Cossaro et al., Can Public IP Blocklists Explain Internet Radiation?**,MADWeb 2025。DOI: https://doi.org/10.14722/madweb.2025.23009 —— 望远镜观测 × blocklist 的交叉评测(真值层构造先例)。

(经典文献腿 Axelsson/McHugh/Durumeric USENIX'15/Metcalf&Spring 由父会话并行覆盖,不重复。)

---

## OPEN QUESTIONS(未收口项,如实记缺口)

1. **AWS ip-ranges.json 许可原文未核到**(JSON 已无 license 字段;docs 页为 JS 壳、license 页 404)——建议下次经 web.archive.org 取 https://aws.amazon.com/ip-ranges-json-license/ 存档原文。
2. **Azure Service Tags 下载条款原文**;**Apple mask-api.icloud.com/egress-ip-ranges 本机复测**(本轮经代理直拉返回空,疑似 UA/地域限制)。
3. **Recorded Future 自报扫描段**是否存在——检索贫化(一次 405 后未复查),如实记缺口。
4. **ZMap responsibility 页已 404**:任务书假设的"大学研究段聚合页"上游失效;Michigan/Merit/RWTH Aachen/Max Planck 旧名单在 2026-10-28 MISP main 树未命中——替代路径=OpenFilters/internet-scanners 元追踪器(https://github.com/OpenFilters/internet-scanners,MISP stretchoid/rapid7 列表实测注明由其追踪)+ 各校自报页(UMich ECE 实测)。建议正式立项时系统盘点该 repo 全量。
5. **Microsoft/Google sinkhole 运营段公布面**负向检索未完成;**MISP `sinkholes` 列表(203 项)的上游 provenance** 未溯源。
6. **Cloudflare rpki.json 更新节奏**、**root.zone 许可与发布节奏**、**public.peeringdb.com 数据面条款**——均未核到一手原文。
7. **SANS ISC threatlist 完整源名录**:`research` 等列表实测返回空,活源(shodan/censys/binaryedge/stretchoid)已验;完整名录需从 ISC 文档再取。
8. 量级缺口:Azure/Apple/Fastly/Akamai 的段数未逐一展开计数(仅 MISP 镜像项数)。

## 附:本轮检索方法注记(供复现)

- 正向族:internet-wide scanning / research scanner / benign scanner RIOT / network telescope darknet background radiation / blocklist ecosystem / IP reputation feed evaluation / sinkhole contamination / ground truth labeled corpus anchor set。
- 负向族(单列):"8.8.8.8 blacklisted"、"spoofed source IP blocklist contamination"(后者命中 CAIDA DDoS-ASPIRE 银行判例,前者仅得 stackexchange/官方迁移公告级证据)。
- 检索贫化处置:zmap.io 404 后改引 MISP 实树 + 各校自报页;CAIDA jina 抓取失败后经 exa 快照取得项目页与 AUA 原文;PeeringDB 的 ODbL 假设经 AUP 原文证伪(教训:许可假设必须引原文)。
