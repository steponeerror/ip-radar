# 票 #249 + #251 收口报告(分支 ticket/249-251-misc,基于 origin/master@a37caf29)

一次收两张小票:#249(代码,删一处与基类逐值等价的覆写)+ #251(纯文档,README 源表补 16 行 + 架构图改序)。中间有一个票面外的口径修正(threatfox/urlhaus 密钥分区),已经过父会话裁决,详见 §251-3。

---

## #249 threatfox.py download_host 覆写删除

**改了什么**:`backend/ipdb/_sources/threatfox.py` 删掉 `@property download_host` 覆写(原 73-75 行,返回 `urlparse(self.url).hostname`)和随之没人用的 `from urllib.parse import urlparse` import。删除后该属性走基类 `backend/ipdb/_sources/_base.py:109-112`(`SourceBase.download_host`)。

**为什么能删**:threatfox 的 `url = "https://threatfox-api.abuse.ch/v2/files/exports/full.csv.zip"` 非空,基类实现对此返回同样的 `urlparse(self.url).hostname`,即 `threatfox-api.abuse.ch`——两实现逐值等价(这是票面已终审核实的事实,本票只做删除+断言)。

**验收逐条**:

1. **删前后实例断言返回值不变** — 删除前:
   ```
   $ cd .worktrees/tkt-misc/backend && /home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python -c "...ThreatFoxSource(Path('/tmp/tkt-misc-probe')).download_host..."
   BEFORE delete: download_host = 'threatfox-api.abuse.ch'   ← assert passed
   ```
   删除后(同命令):
   ```
   AFTER delete: download_host = 'threatfox-api.abuse.ch'
   resolved from: ipdb._sources._base   ← 断言通过,且 ThreatFoxSource.__dict__ 里已无 download_host(确认覆写确实删净)
   ```
2. **61 源发现冒烟(真实发现入口)** — 经 `ipdb/_registry.py` 模块级 `_discover_sources(DATA_DIR)`(import 即触发,不做桩):
   ```
   total sources: 61
   threatfox in list: True
   threatfox download_host: 'threatfox-api.abuse.ch'
   SMOKE OK: 61 sources, threatfox instantiated, host unchanged
   ```
3. **测试全绿** —
   ```
   $ cd .worktrees/tkt-misc/backend && /home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python -m pytest tests/sources tests/core -q
   1142 passed, 8 skipped in 70.17s
   ```
   评估套件零接触,按要求跳过。

提交:da4c7200(单文件,净删 5 行)。

---

## #251 README 源表补 16 行 + 架构图改序(含裁决的口径修正)

### 251-1 表行补齐(两份 README 同步)

票面点名的 16 个在册未列源全部补入,threat(威胁信誉)+10 / geo_asn(地理与 ASN)+3 / asset(网络资产)+3,与代码里各类的 `category` 属性一一对应(实测:`reg.SOURCE_CATEGORIES` 只有 threat/geo_asn/asset 三类)。每行内容取自各源类的真实代码事实(类 docstring、`url` 属性、源文件内的端点常量),无编造:

| 源 | 表 | Provider 链接来源(代码事实) | 贡献一句(据 docstring) |
|---|---|---|---|
| scanner_ranges | threat | MISP warninglists 仓库 + Xpanse 官方页(`scanner_ranges.py:41-45` 两个 URL 常量) | 66 份 `*-scanning` 列表 + Xpanse 页,厂商自报网段 |
| sw_scanners | threat | github.com/ShadowWhisperer/IPs(`url` 属性) | 自采策展扫描器清单,逐行带厂商名,日更 |
| sw_threats | threat | 同上 | 自采策展威胁清单,逐行带类别/首次出现 |
| myip_ms | threat | myip.ms blacklist(`url`) | 自有爬虫+用户举报,10 天滚动窗 |
| sblam | threat | sblam.com/blacklist.txt(`url`) | 波兰表单陷阱传感器网络的表单垃圾黑名单 |
| data_shield | threat | duggytuxy/Data-Shield_IPv4_Blocklist(`url`) | 每日聚合 IPv4 封禁清单,约 9 万裸 IP |
| ziyadnz | threat | ziyadnz/threat-intel-ip-feeds(`url`) | 聚合约 10 个公开源的每日逐 IP 清单,逐行留出处 |
| cps_collected_iocs | threat | CriticalPathSecurity/Public-Intelligence-Feeds(`url`) | CPS 自有 IOC 汇总,裸 IP |
| malicious_ip | threat | romainmarcoux/malicious-ip(`_BASE_URL`,`url` 为空属下载期分片设计) | 五分片合并,约 100 万唯一 IP,逐时重建 |
| ustc_blackip | threat | blackip.ustc.edu.cn(`url`) | 中国科大校园自保黑名单,约 15 年,解封人工复议 |
| rir_delegated | geo_asn | 五 RIR FTP(`rir_delegated.py:33-42` 端点表) | 每日注册分配文件:分配日期/注册国/状态 |
| rir_abuse | geo_asn | RIPE + AFRINIC dbase dump(docstring 端点清单) | 按网段的 abuse 投诉邮箱(RPSL 全量导出) |
| caida_asorg | geo_asn | caida.org as-organizations 数据集页(`url`) | ASN→组织名月度快照,查询期拼接 |
| peeringdb | asset | www.peeringdb.com/api(`peeringdb.py:30`) | IX fabric 前缀+名称,下载期拉全查询期零在线 |
| cloudzy | asset | CPS 镜像仓 cloudzy.txt(`url`) | Cloudzy VPS 托管网段(资产陈述不指控) |
| anycast_census | asset | manycast.net 导出(`url`) | 主动测量任播 /24 前缀约 4.1 万,混播剔除 |

`*`(聚合器)标记规则:新行里恰给 4 个 `derived = True` 的源(data_shield / ziyadnz / cps_collected_iocs / malicious_ip)——这是代码里可 grep 的客观判据,与图例「`*` = aggregator」一致。sw_scanners/sw_threats docstring 明写「非 derived」,不加;scanner_ranges 代码也非 derived(66 份列表是「一跳镜像直取」不是转抄聚合),不加。存量行的 `*` 现状一律未动(greensnow/otx 等 derived-未星属历史存量,不在本票面内)。

zh 表新行全用平实中文写「贡献」列;存量 zh 行内容(含 threatfox/urlhaus 的英文贡献文案)未动。

**验收(计数脚本逐项过,非目测)**:

```
== README.md:      rows=61 🔑=7  missing=[] extra-not-in-registry=[] duplicated=[]
== README.zh-CN.md rows=61 🔑=7  missing=[] extra=[] duplicated=[]
OVERALL: PASS
```

- 每份 61 行,与 `ipdb/_registry.py` 真实发现出的 61 个源名**集合完全相等**(无缺、无多、无重复行)。
- 所有源表行均为 4 列(计数脚本核对,唯一 3 列的是 Quick Start 密钥表,系其原有设计)。

### 251-2 mermaid 架构图改序

两份 README 的图原来都是 解析 → **融合** → **入库**;实际是入库在前、查询时才融合。已改为:

```
下载(冷启/30min 扫描) → 逐源解析 → LMDB store → Fusion at query time → FastAPI → React UI
```

- 融合节点标注改为 `Fusion at query time`,与 zh 图上方既有文字句「……入库(LMDB)→ 查询时多源加权融合……」(上批已修)对齐。
- 顺手把图下 caption 的同序存量错一并修了(图序改了,caption 不改会自相矛盾):en `Fused, stored, and queried` → `Stored, fused, and queried`;zh `融合、存储、查询` → `存储、融合、查询`。此两行属票面「同序存量错」的同一处修正,特此披露。

### 251-3 口径修正:61 = 56 免 key + 5 key → **61 = 54 免密钥 + 7 需密钥**(票面外,已裁决)

**发现**:验收条款「🔑 行恰 5」与代码事实撞车。实测 7 个源要密钥(不止 5):`_tokens.py:20-25` 受管的 5 个+ **threatfox/urlhaus**(2026-10-23 票 #159 起 v2 端点必须 `ABUSECH_AUTH_KEY`,无 key `download()` 直接 RuntimeError——threatfox.py:70 / urlhaus.py103)。7 源共用 5 个密钥变量(OTX 两源共用、ABUSECH 两源共用)。en 源表本来就标了 7 个 🔑,zh 源表只标 5(#159 之前旧状态没跟上);旧口径「44/49→56/61」的「5」是 #159 之前的真分区,上批 49→61 机械放大把过期分区一并带过去了。

**裁决**(父会话,2026-10-31):改分区,真相优先——两表 threatfox/urlhaus 都带 🔑,正文全量改 61=54+7,验收③按「🔑 恰 7(双语一致)」执行;Quick Start 密钥表本就与真相一致,不动。

**落地**(共 9 处正文分区表述,双语):

| 文件:行 | 改动 |
|---|---|
| README.md:43 | `all but the 5 keyed` → `all but the 7 keyed` |
| README.md:45 | `All but 5 feeds…` → `All but 7 feeds…`,补半句「7 源共用 5 个密钥——OTX 两源、abuse.ch 两源」(裁决允许可加处) |
| README.md:103 | mermaid 首节点 `5 keyed` → `7 keyed` |
| README.zh-CN.md:45 | `除 5 个密钥源外全部` → `除 7 个` |
| README.zh-CN.md:47 | 点名清单从 5 源补全 7 源 + 「共 5 个密钥:OTX 两源共用、abuse.ch 两源共用」半句 |
| README.zh-CN.md:92 | 特性条 `除 5 个…剩下 5 个 🔑 源` → 7/7 |
| README.zh-CN.md:108 | mermaid 首节点 5→7 |
| MANUAL.md:24 | `56 of the 61 sources` → `54 of the 61 sources` |
| MANUAL.zh-CN.md:24 | `61 个源中的 56 个` → `61 个源中的 54 个` |

**改后复核**:旧表述全量清扫零残留(`grep '5 keyed|除 5 个|5 个密钥源|56 of the 61|61 个源中的 56|剩下 5 个'` 四文件零命中);`🔑 = 7` 的行恰为代码里 7 个读密钥 env 的源。审查第 1 轮 P1-1 勘正:裁决时以为「Quick Start 密钥表本就与真相一致」只对 en 成立(6 行/5 变量),zh 表是 #159 前旧状态(4 变量、ABUSECH_AUTH_KEY 整行缺席)——已随审查修 `review-r1` 补行并改导语「四个→五个变量」,双语表至此一致;另 `.env` 样例至今缺 ABUSECH_AUTH_KEY 行(#159 遗留,票外挂账)。

---

## 意外发现与披露

1. **口径修正动了上一批已过审的正文计数**(§251-3)——票面明言「本批只把计数文本 49→61…表行补列留本票」,本票反而又动了 9 处计数;这是按父会话 2026-10-31 裁决执行的修错(旧分区是 #159 前的过期事实),非擅动。票面评论由父会话补,本工未动票。
2. zh 源表「贡献」列存量大量英文(威胁表几乎整列英文),本票只按「zh 用平实中文」写新行,存量未动——存量翻译不在票面。
3. en 表 threatfox/urlhaus 行的贡献列里有中文碎片「v2 认证导出」(#159 时留下),票面外未动,如实披露。
4. 源表 `*` 星标存量与代码 `derived` 标志不完全对齐(greensnow/otx/otx_subscribed 是 derived 但未标星):本票新行按代码标志标,存量未动。若要全量对齐可另开小票。
5. #249 删除时一并删了 `urllib.parse.urlparse` import——该文件里它只被覆写用到(全文件 grep 确认),留着会成为死 import。

## 验证命令清单(可复跑)

```
cd /home/huxiao/dev/pi-ip-lookup-tool/.worktrees/tkt-misc/backend
/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python -m pytest tests/sources tests/core -q   # 1142 passed, 8 skipped
# 61 源冒烟 / 删前后断言 / 表行计数核对:见上文各代码块(均 .venv 绝对路径 python,cd 进 worktree backend/ 跑)
```

## 提交

- da4c7200 — #249 threatfox.py 覆写删除(1 文件,−5 行)
- (本提交)— #251 四文件:README 双语表行 16+16、mermaid 改序、密钥分区口径 9 处 + 本报告
