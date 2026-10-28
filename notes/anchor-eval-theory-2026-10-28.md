# 锚点读数扩展——理论依据腿(父会话调研稿)

日期:2026-10-28 · 状态:文献腿已收,待与 `anchor-eval-research-2026-10-28.md`(子代理维度/实践腿)合并
用途:为「已知标签 IP 锚点评估情报/源质量」提供理论与方法学依据;所有 DOI 经 Crossref 核对。

## 一、为什么「干净锚的误报率」是第一序量

**Axelsson, S. (2000). The Base-Rate Fallacy and the Difficulty of Intrusion Detection. ACM TISSEC 3(3):186–205.** DOI [10.1145/357830.357849](https://doi.org/10.1145/357830.357849)(495 引;会议版 1999 CCS,DOI 10.1145/319709.319710)。
> 由于攻击的基底率(base rate)极低,贝叶斯检出率 P(入侵|告警) 的限制因素是**假阳率**——要得到可用的检出置信,假阳率必须压到极低(某些场景不可达地低)。

映射到本仓:IP 空间中「当前活跃恶意」占比极小,任何源/融合面的质量上限由它在**已知干净 IP 上的误报率**决定——这正是「非指控基础设施层·绝对干净锚」作为误报下界层的理论根据;Axelsson 的结论同时说明:锚上测得的误报率是**条件读数**(条件于锚集),不是全空间无条件误报率,读数措辞须带此注记。

## 二、评测方法学:语料有效性、程序公开、可复算

- **McHugh, J. (2000). Testing Intrusion Detection Systems. ACM TISSEC 3(4):262–294.** DOI [10.1145/382912.382923](https://doi.org/10.1145/382912.382923)(994 引)——对 1998/99 DARPA IDS 评测的方法学批评:测试数据未验证、程序细节未公开、技术选择可疑。核心要求:**语料本身要被验证、评测程序可复算**。
- **Lippmann et al. (2000). The 1998 DARPA Off-line IDS Evaluation. DISCEX'00.** DOI [10.1109/discex.2000.821506](https://doi.org/10.1109/discex.2000.821506)(被批评对象本体,359 引)。
- **Thomas, Sharma & Balakrishnan (2008). Usefulness of DARPA dataset for IDS evaluation. SPIE.** DOI [10.1117/12.777341](https://doi.org/10.1117/12.777341)——合成语料的长期后遗症判例。

映射:本仓「冻结工件/预注册阈值/哨兵(读数附规模+指纹+成员计数)/门求值留痕 gates.json」= McHugh 式要求(程序可复算、语料版本随附)的既有实现;锚集 census 的 N、seed、成员清单必须随读数落盘,同构于 ADR 0011 的 census(N=400, seed 42)。

## 三、黑名单/CTI feed 的实证评测传统

- **Metcalf, L. & Spring, J.M. (2015). Blacklist Ecosystem Analysis. ACM WPISCS, 13–22.** DOI [10.1145/2808128.2808129](https://doi.org/10.1145/2808128.2808129)(ACM 开放 PDF)——跨越两年的公开黑名单生态测量:**重叠/一致性/时效**是 feed 的核心质量维度,单一列表的「独立增量」极小。
- **Griffioen, H., Booij, T. & Doerr, C. (2020). Quality Evaluation of Cyber Threat Intelligence Feeds. LNCS 277–296.** DOI [10.1007/978-3-030-57878-7_14](https://doi.org/10.1007/978-3-030-57878-7_14)(43 引)——CTI feed 质量评测框架(时效/覆盖/重叠等维度化指标)。
- 谱系:**Dietrich & Rossow (2008). Empirical research of IP blacklists. ISSE.** DOI [10.1007/978-3-8348-9283-6_17](https://doi.org/10.1007/978-3-8348-9283-6_17);**Kührer & Holz (2012). An Empirical Analysis of Malware Blacklists. PIK 35(1):11–16.** DOI [10.1515/pik-2012-0003](https://doi.org/10.1515/pik-2012-0003);**Porenta & Ciglarič (2011). Empirical comparison of IP reputation databases. CEAS.** DOI [10.1145/2030376.2030402](https://doi.org/10.1145/2030376.2030402);**Deri & Fusco (2023). Evaluating IP Blacklists Effectiveness. IEEE FiCloud.** DOI [10.1109/ficloud58648.2023.00056](https://doi.org/10.1109/ficloud58648.2023.00056)。

映射:Metcalf&Spring 的「重叠即回声」= 本仓谱系/镜像对/聚合器占比读数;Griffioen 的维度化质量评测 = 接入关四层读数的文献同构;锚基读数族(干净锚误报率、扫描锚召回)是往这套传统里加**非循环真值侧**的一维(现有 独占贡献 已引 Li et al., USENIX Sec'19 "Reading the Tea Leaves",见 GLOSSARY)。

## 四、扫描与暗网维度

- **Pang, Yegneswaran, Barford, Paxson & Peterson (2004). Characteristics of Internet Background Radiation. IMC '04, 27–40.** DOI [10.1145/1028788.1028794](https://doi.org/10.1145/1028788.1028794)(233 引)——网络望远镜/背景辐射的奠基测量:暗网收到的全部流量按定义是**未经请求的**(扫描/反射回散/误配置)→ 暗网命中的源 IP 是强扫描正例,可作「扫描正例锚」的独立维度(获取政策待子代理查证:CAIDA/Team Cymru)。
- **García-Peñas, Rodríguez-Gómez & Maciá-Fernández (2026). IBRAM: Internet Background Radiation Analysis Methodology. SSRN 预印本.** DOI [10.2139/ssrn.6713362](https://doi.org/10.2139/ssrn.6713362)——现代 IBR 分析方法学 + **公开 /24 望远镜数据集**(31 天 6700 万包),若许可兼容纯本地红线,是暗网维度的现成数据面。
- **Durumeric et al. (2015). An Internet-Wide View of Internet-Wide Scanning. USENIX Security 2015.**——internet-wide 扫描与研究扫描器的奠基测量(URL 待子代理核验,Crossref 不收录 USENIX)。

映射:扫描正例锚(scanner_ranges 自报段 + sw_scanners 观测)的文献地位 = Pang/Durumeric 线:「研究扫描器」是可枚举、可自报的类目;「良性扫描器被黑名单当恶意」是语料污染的已知形态 → ADR 0011 排除面的依据。

## 五、边界与未决(理论侧)

- 未见专门论文量化「sinkhole IP 被黑名单收录」的污染面(实践记录在 abuse.ch/Microsoft DCU 类运营文档;子代理实践腿查证)。
- 蜜罐真值层的方法学依据本仓 ADR 0002(Hornet 65 Niner)已足;文献侧 Leita/Dacier 系(Crossref 检索噪声大,未钉住具体篇目,标 UNVERIFIED-pending)。
- 「良性语料选择偏差」在 IP 域无 Alexa-top 式公认判例(域名域判例不可平移),锚集的代表性只能用 census+分层注记自证——这本身是 Q1 谓词绑定与 Q5 统计力设计的理由。
