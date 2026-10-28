# sinkholes 列表上游溯源(MISP misp-warninglists)— #233 T2 污染探针准入闸

- 日期:2026-10-28 | 调研:#233 v0 探索子代理(ADR 0013);固化:T2 实现者
- 对象:MISP misp-warninglists 仓 `lists/sinkholes/` 列表(GLOSSARY「污染探针」首批准入对象,203 项)
- 结论速览:**有具名上游(brakmic/Sinkholes,per-entry 组织归属)+ 有文档化再生成管线(tools/generate-sinkholes.py,PR #440)→ PASS,探针已落地**;完整 VERDICT 行见文末。
- 落地(本仓工件):语料 `backend/ipdb/_eval/sinkhole_ranges.json`(203 = 186 裸 IP + 17 CIDR,eval-only,永不进 LMDB/产品源);双 pin sidecar `backend/ipdb/_eval/sinkhole_ranges.provenance.json`;探针模块 `backend/ipdb/_eval/sinkhole_probe.py`(`--sinkhole-probe`);详溯见下文。
- ⚠️ 仓库改名事实:MISP 仓已更名 **`MISP/warninglists` → `MISP/misp-warninglists`**(gh api 用旧名直接 404,raw 亦然);实现一律用新名(本仓 `scanner_ranges.py` 的 `_MISP_URL_TMPL` 已是新名)。

## ① list.json 元数据(main @ f8d976e794,2026-10-14)

来源:<https://github.com/MISP/misp-warninglists/blob/main/lists/sinkholes/list.json>

| 字段 | 值 |
|---|---|
| name / description | `List of known sinkholes` |
| type | `cidr` |
| category | `known`(2026-10-14 由 13f171aea0 新增) |
| version | `20261014`(int,YYYYMMDD 版式,PR #397 规约) |
| matching_attributes | `["ip-src","ip-dst","domain|ip","ip-src|port","ip-dst|port"]` |
| source 字段 | **不存在**(MISP 该列表 schema 无 per-list `source` URL;provenance 只活在生成器脚本+git 史——这正是本调研存在的原因) |
| entries | **203** = 186 个裸单 IP + 17 个 CIDR(最小 /31 `104.244.14.252/31`;最大 /22 `104.244.12.0/22`) |

## ② 提交史(贡献者、节奏、条目增长)

方法:`gh api "repos/MISP/misp-warninglists/commits?path=lists/sinkholes/list.json&per_page=100"` — 该文件历史全量 **27 个 commit**。

| SHA | 日期 | 作者 | 条目 | 事件 |
|---|---|---|---|---|
| c6fc6e89fe | 2018-09-26 | Alexandre Dulaunoy | 76 | 建列(手工种子)+ 同日去重 a205adba1f |
| 3789dbf107 / 1e654dca9d | 2019-11 | Ԝеѕ(PR #119/#122) | 79 | `Add additional Sinkhole IPs` |
| 300d823638 | 2020-04-03 | Raphaël Vinot | 79 | 排序/去重工具化,零增长 |
| 3e81a6e376 | 2021-10-27 | Drew Middlesworth | 88 | `New sinkholes detected from work with riskrecon.com and other security sites.` |
| …69460b61d1…66a0d53d67 | 2021-11 → 2022-09 | Drew Middlesworth(PR #193-#217) | 88→107 | 手工增量期(见③) |
| e48c2539c2 | 2024-04-22 | Jeroen Pinoy | 107 | 只加 matching_attributes,零增长 |
| 35d266869f | 2026-08-29 | elhoim | 107 | 版本号改 YYYYMMDD,零增长 |
| **cdb6cf3076** | **2026-09-08** | Alexandre Dulaunoy | **107→203(+96)** | `chg: [lists] updated to the latest version`(真实来源=PR #440 生成器首次批量跑) |
| f8d976e794 / 13f171aea0 | 2026-10-14 | Sami Mokaddem | 203 | 加 `category` 字段,零增长 |

**节奏判读:** 2018 种子 → 2019-2022 手工 trickle → 2024-2026-08 **停滞两年半(恒 107)** → 2026-09-04 起转入**生成器自动化**。当前距上次数据更新 2026-09-08 ~7 周(合理:sinkhole 段面变化慢)。

**贡献者谱:** Alexandre Dulaunoy(MISP 联合创始人,全仓第一)、Sami Mokaddem、Raphaël Vinot、Jeroen Pinoy、elhoim(生成器作者)、Drew Middlesworth、Ԝеѕ——全为 MISP 生态活跃维护者/社区贡献者,无匿名一次性注入。

## ③ 条目从哪来(核心判定)

**分期:2026-09-04 之前=社区手工 OSINT 聚合;之后=具名上游 + 文档化生成管线。**

### 3a. 手工期(76→107,2018-2022):具名第三方观测面,非运营方自公布

Drew Middlesworth 的 PR 标题/commit message 即出处,全部可点:PR #211/#210/#209 riskrecon.com(现 Bitsight)、PR #197 bitsight.com、PR #217 securityscorecard.com、PR #206 abuseat.com、PR #194/#209 shadowserver(含 reverse DNS 佐证,commit 77de13eac0 `Reverse lookup of this IP shows sinkhole.hyas.com.`)、cert.pl 合并段(48465b733e)。方法论 = 第三方安全厂商观测面 + 反向 DNS 推断聚合,**不是** sinkhole 运营方一手公布(公开一手公布面经此前调研确认不存在——notes/anchor-eval-research-2026-10-28.md §A5 的 Microsoft/Google 公布面即 UNVERIFIED)。

### 3b. 生成器期(107→203,2026-09-04 起):具名上游已接入并文档化

**PR #440** `[high] Add sinkholes warninglist generator`(elhoim,2026-09-04 合并):

> "**Source:** [`brakmic/Sinkholes`](https://github.com/brakmic/Sinkholes) (`Sinkholes_List.json`) — curated malware/research sinkhole ranges with the operating organisation."
> "**Effect:** **+96** entries (107 → 203), 0 removed."
> "**Unions, never replaces.** Every entry committed today survives untouched."

落地物:`tools/generate-sinkholes.py`(145 行,已入 main,接入 `generate_all.sh`),docstring 声明上游=brakmic/Sinkholes、谱系=Lesley Carhart's Consolidated Malware Sinkhole List、union-never-replace、解析不了的形状 skipped-with-warning、拒绝写空表。数据端点(脚本内 URL):`https://raw.githubusercontent.com/brakmic/Sinkholes/master/Sinkholes_List.json`。

### 3c. 上游 brakmic/Sinkholes 全貌

- 作者 **Harris Brakmic**(个人),MIT License,107 stars,2017-05-16 建仓,最后 push **2026-05-25**(audit fixes + CI,HEAD=1a284cd9)。
- README「Sources and credits」:Lesley Carhart 的 Consolidated Malware Sinkhole List(tisophone.net,2017)seeding;"The 2026 refresh draws from the public OSINT list at grettir/malware-sinkholes"。
- 权威数据=`Sinkholes_List.csv`,其余格式由它再生成;`Sinkholes_List.json` 现值 **168 行**,字段逐条 `Organization / IP Range / Whois / Notes`——**每条带运营组织归属**+多数带佐证链接。2026 refresh(c3e90d81,2026-04-25)覆盖 AnubisNetworks、Bitdefender、CERT Australia、Dell SecureWorks、SecurityScorecard、Shadowserver、Spamhaus 等。
- 次级源 grettir/malware-sinkholes 已休眠(2019-08 后),只作 2026 refresh 一次性输入,非活水。
- 分支注意:生成器钉 `master`,仓库默认分支已是 `main`;T2 固化时(2026-10-28)`master` 已不可经 commits API 解析,`main` HEAD = **1a284cd902e4bf023f1e45aa79a5d7d3dfff5abf**(2026-05-25T17:12:33Z),该 SHA 下 `Sinkholes_List.json` = 168 行,SHA256 `6b6836e1…ad65e21b`。

### 3d. 判定

条目来源 = **具名上游链**:MISP `sinkholes` ←(生成器,文档化)← brakmic/Sinkholes(per-entry Organization/Whois/Notes + Carhart 谱系)← Lesley Carhart 2017 手工汇总 + grettir 2026 补充。**非**「社区无出处聚合」;亦**非**运营方一手公布(该面公开不存在,见 3a)。

## ④ 同谱系镜像

| 仓 | 关系 |
|---|---|
| firehol/update-ipsets | 活水自动镜像(`configs/firehol/sources/malware_infrastructure/misp_sinkholes.yaml`) |
| telekom-security/misp-warning-lists | 企业级 vendored 全量镜像(同路径文件) |
| OpenFilters/internet-scanners | **非**镜像——范围=扫描器组织,`sinkhole` 0 命中 |
| 其余 28 个字面命中仓 | SOC 部署模板死拷贝,非独立谱系 |

## ⑤ 固化记录(T2 落地实测,2026-10-28)

- 取数通道:`gh api repos/MISP/misp-warninglists/contents/lists/sinkholes/list.json`(raw.githubusercontent.com 本机连接重置,api.github.com 可达);字节级落盘后 SHA256 = `de791ba3fcbf7fe087ba6c55103212d781a538e574282716df60d8609d1b3c7f`,version=20261014,203 项 = 186 裸 IP + 17 CIDR——与本文档调研数字一致。
- 双 pin 落位(随件 `sinkhole_ranges.provenance.json`,探针 artifact 透传 version/sha256/upstream_commit):MISP version **20261014** + list.json 内容 SHA256 **de791ba3…d1b3c7f** + 上游 brakmic/Sinkholes commit **1a284cd902e4bf023f1e45aa79a5d7d3dfff5abf** + 生成日期 2026-10-28 + 条目构成数 {203, 186, 17}。
- 语料条目 MISP 原拼写(裸 IP 不带 /32);运行期零网络(纯本地红线,取数一次性)。

## 风险与实现注意(T2 已按此执行)

1. **不是运营方一手数据**:组织归属系 OSINT(Carhart 谱系 + 厂商观测面 + 反向 DNS)。对探针语义可接受——污染探针要的是「这些 IP 长期是 sinkhole」这一事实,归属误差只影响归因注记,不影响污染计数。
2. **单 IP(186/203)重指派残余风险**:union-never-replace 政策让已退役 sinkhole IP 永驻列表,已易主 IP 的「命中」会被误记污染。缓解(已落地):探针读数分层 CIDR 基(强信号)vs 单 IP 基(弱信号),artifact 保留原始 (source, ip, sinkhole_entry) 三元组可回查,不裸给结论。
3. **上游半休眠**(brakmic 最后 push 2026-05-25;grettir 已死):语料固化为仓内静态资产 + 双 pin,无活网依赖。
4. MISP 侧 schema 该列表无 `source` 字段——v1 若直引上游,以 `tools/generate-sinkholes.py` 的 URL 为准。
5. 生成器 union 语义 ⇒ MISP 203 ≥ 上游 168 + 手工遗产(36/107 不在上游)——T2 语料用 MISP 面拿全集;要 per-entry 组织归属则回上游 JSON 对齐(裸 IP 字符串 join)。

## VERDICT

**VERDICT: PASS —— 有具名上游(brakmic/Sinkholes,168 行 per-entry Organization/Whois/Notes 归属,MIT,谱系=Lesley Carhart 2017 汇总)且有文档化维护流程(MISP 仓内 tools/generate-sinkholes.py 生成器 + union-never-replace 政策 + PR #440 评审合并 + YYYYMMDD 版本化),2026-09-08 起的 203 项即其首次再生产物——探针按 ADR 0013 可落地,条件=固化语料时双 pin(MISP version 20261014/或 list.json 内容 SHA + 上游 commit SHA)并对 186 个单 IP 条目标注重指派残余风险。**(条件已于 T2 固化时清偿,见 §⑤)
