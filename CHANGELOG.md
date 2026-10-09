# Changelog

本项目的所有重要变更记录于此。自 v1.0.0 起按版本分节，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## Unreleased

### 新增 Added

- 新源 otx_subscribed：AlienVault OTX 订阅库流（/api/v1/pulses/subscribed，与 otx 的 activity 全网扫描流同发布者不同流）——数据 = 账号策展作者群（蜜罐运营方/威胁研究团队），demo 账号实测 83 pulses / 16,929 唯一 IPv4（对比 activity 流同窗口数百条）；取数 = limit=1 逐页（大页必 504，OTX 60s 网关闸；枚举页被巨型 pulse 挡住则跳过记账下轮补）；分类双路 = indicator 自带 role 优先（bruteforce→brute-force）+ pulse 名关键词兜底（Botnet List→c2-server、Malware Delivery→malware-distribution、URLHaus 镜像→malware-distribution、ICS Targeting/Scan port/S3#→scanner、其余→blacklist）；同 IP 重复观测去重保最新 created（first_seen 落观测时间）；TSEC 逐 IP 描述（置信度/行业定向/协议交互）无损入 extra；派生标记 = derived + DERIVED_SOURCES + LINEAGE_CLUSTERS（与 otx/firehol/ipsum 同层，谱系去重兜底 activity∩subscribed 残余回声）；reliability 0.6，stale_days=1（12h 槽）；公开源口径 40→41
  - New source otx_subscribed: the AlienVault OTX subscribed-library stream (/api/v1/pulses/subscribed; same publisher as the otx activity firehose, different stream) — data = the account's curated author set (honeypot operators / threat researchers), live-verified at 83 pulses / 16,929 unique IPv4 on the demo account (vs a few hundred from the activity stream over the same window); fetching = limit=1 page-at-a-time (bigger pages always 504 at OTX's 60s gateway; pages blocked by mega-pulses are logged and skipped, retried next 12h slot); classification is two-path = the indicator's own role first (bruteforce→brute-force) with pulse-name keywords as fallback (Botnet List→c2-server, Malware Delivery→malware-distribution, URLHaus mirrors→malware-distribution, ICS Targeting/Scan port/S3#→scanner, else→blacklist); duplicate observations of the same IP dedup keeping the latest created (first_seen = observation time); TSEC's per-IP descriptions (confidence/sector targeting/protocol interaction) preserved losslessly in extra; lineage = derived + DERIVED_SOURCES + LINEAGE_CLUSTERS (same tier as otx/firehol/ipsum, lineage dedup absorbs the residual activity∩subscribed echo); reliability 0.6, stale_days=1 (12h slot grid); public-source count moves 40→41
- CI 防线批(b/ci-hardening):demo 生产分支加入 CI push 触发面;tests/auth 与 tests/alerts 测试目录纳入 gating;CI Node 20→22 对齐镜像 node:22-alpine;前端 eslint 清零后入闸(strictNullChecks 同步开启,验证面=出货面);新增 bench_lookup 位等价自往返 smoke 门(合成 tiny 库 snapshot→compare 零 diff + 命中断言)与回放闸门 import 安全(setrlimit 移入 main 首行);docker job 从只 build 升级为 compose config 校验 + docker run 健康门(轮询 /api/version 至 200);tag push 新增 tag↔CHANGELOG↔GitHub Release 三真相源一致性检查(漏打 tag/漏建 Release 即红);bench_lmdb 缺省数据目录改一次性 tmp 基座(用后即清)并拒绝直指生产数据目录;registry v6 测试钉住 v4-mapped 翻译进 v4 族的回归
  - CI defense-line batch (b/ci-hardening): the demo production branch joins the CI push trigger surface; the tests/auth and tests/alerts suites enter CI gating; CI Node moves 20→22 to match the image's node:22-alpine; frontend eslint enters the gate after clearing to zero errors (strictNullChecks switched on alongside — the verification surface now equals the shipped surface); a new bench_lookup bit-identity round-trip smoke gate (synthetic tiny library, snapshot→compare zero diff plus hit assertions) and replay-gate import safety (setrlimit relocated to the first line of main); the docker job upgrades from build-only to compose-config validation plus a docker run health gate (polling /api/version until 200); tag pushes gain a tag↔CHANGELOG↔GitHub Release three-source consistency check (a missing tag or a missing Release turns the build red); bench_lmdb's default data dir becomes a throwaway tmp base (cleaned up after use) that refuses to point at the live data dir; and the registry v6 test pins the v4-mapped-translation-into-v4-family regression

### 调整 Changed

- 文档对齐实况(D 批 docs-truth):README 双语架构图「30-min refresh scheduler」改为实况措辞(30 分钟扫描周期 + 按源 12h 错峰刷新槽);GLOSSARY 三词条对齐——「单源 conf=r」补适用族半句(city 单源恓 50 / ip_range 50·85 品质阶梯锚为有意设计,公理字面不适用)、「谱系」DERIVED_SOURCES 五员补 otx_subscribed 六员(与源 attr 灌装实况一致)、新增「benign(两层)」词条厘清指控缺席=弃权(缺省序列化,非良性背书)与良性判定(非指控信号源明确断言)两层;纯文档零行为变化
  - Docs aligned to reality (D-batch docs-truth): the bilingual README architecture diagram's "30-min refresh scheduler" now states the real mechanics (a 30-minute scan cycle plus per-source staggered refresh slots on the 12h grid); three GLOSSARY entries align — "single-source conf = r" gains its applicability clause (city's always-50 single source and ip_range's 50/85 specificity anchors are intentional quality-ladder design, outside the axiom's letter), the lineage entry's DERIVED_SOURCES grows from five to six members with otx_subscribed (matching the attr-filled reality), and a new "benign (two layers)" entry separates accusation-absence abstention (a default serialization, never a benign endorsement) from an explicit benign assertion by a non-accusing signal source; docs-only, zero behavior change
- 运行时镜像瘦身（PF-6）：.dockerignore 排除 backend/tests —— 运行时镜像不再携带 ~180 个测试文件（镜像体积与暴露面双减）；容器内运行路径（uvicorn main:app、/api/version 健康门、自更新工具链）零依赖 tests/，构建后容器内实测无 tests 目录
  - Runtime image slimming (PF-6): .dockerignore now excludes backend/tests — the runtime image no longer carries the ~180 test files (smaller image and a smaller exposure surface in one stroke); the in-container runtime paths (uvicorn main:app, the /api/version health gate, the self-update toolchain) have zero dependency on tests/, and the built container was inspected to confirm no tests directory
- 指控集字面量单源化（A2 遗留收口）：_types._ACCUSING 成为全仓唯一指控章口径 —— _merge._assess_classification 的本地 ACCUSING 与 _eval/anchors.py 的内联 ("malicious","suspicious") 元组改引用之（与 _eval/metrics、_stix_export 既有借道同款）；纯常量提取零行为变化，位等价 smoke（snapshot→compare 自往返零 diff）验证零漂移
  - Accusing-set literals single-sourced (closing the A2 leftover): _types._ACCUSING becomes the sole accusing-chapter set repo-wide — _merge._assess_classification's local ACCUSING and _eval/anchors.py's inline ("malicious","suspicious") tuple now reference it (same cross-module borrowing as the existing _eval/metrics and _stix_export imports); a pure constant extraction with zero behavior change, verified drift-free by the bit-identity smoke (snapshot→compare round-trip, zero diff)
- OL 可靠性速赢组（C 批 Task 2，审计 OL-2/3/4/8）：①启动对账先判版本后判 stale（OL-2）——慢机构建（>15 分钟）但成功的自更新不再被 stale 窗误标 failed（状态与事实相反，顺序钉测试钉住）；②启动孤儿清理补 `*.lmdb.disjoint.new.*`（OL-3）——OOM/SIGKILL 落在 staging 与 replace 之间的 disjoint 边车孤儿文件不再永存；③epoch 损坏不再静默缺席（OL-4）——load_db 抓到 open_env_read 异常时升 ERROR 级日志并把异常记入源状态（/api/sources 的 health.error），告警状态机新增 reader 条件（ptr 在而 reader 未加载即告，恢复后人裁 rebuild 完成 reader 回来自清）；不自动 rebuild（宁少算，数据面安全），rebuild 仍人裁；④IP_RADAR_ALERT_URLS 告警通道可发现（OL-8）——docker-compose.yml 注释块与 README 运维节补示例（apprise 多接收者逗号分隔），默认仍静音零改；顺带（T1 评审 P2）spamhaus/x4bnet_vpn 的 v6 空响应异常消息补 redact_url 打码
  - OL reliability quick-wins (C-batch Task 2, audit OL-2/3/4/8): ① startup reconcile now checks version before the stale window (OL-2) — a slow-machine build (>15 min) that succeeded no longer gets mislabeled failed (state contradicting fact; pinned by an ordering test); ② startup orphan cleanup gains `*.lmdb.disjoint.new.*` (OL-3) — disjoint-sidecar staging orphans left by an OOM/SIGKILL between staging and replace no longer linger forever; ③ a corrupted epoch is no longer silently absent (OL-4) — load_db logs open_env_read failures at ERROR level and records the exception in source state (health.error on /api/sources), and the alert state machine gains a reader condition (ptr present but reader unloaded fires; self-clears via recovery once a human-approved rebuild brings the reader back); no automatic rebuild (better to undercount — the data plane stays safe), rebuilds stay human-adjudicated; ④ IP_RADAR_ALERT_URLS becomes discoverable (OL-8) — the docker-compose.yml comment block and the README ops section now show the example (comma-separated apprise recipients), default stays silent with zero behavior change; along the way (T1-review P2) the spamhaus/x4bnet_vpn empty-v6-sibling exception messages now route through redact_url
- 下载 URL 日志打码（C 批 Task 1，事故驱动：OTX 与 IP2PROXY token 各泄过一次——warn_if_redirected 绊线把带 token 的完整下载 URL 打进了 docker 日志）：新增单源助手 redact_url（保留 scheme+host+path，query 整体替 "?q=REDACTED"，逐参数白名单不做——token 可藏在任意参数名下，userinfo/fragment 同丢）；redirected 绊线、download_file 截断错误、两处基类与七个源的 "Empty/empty response" 异常消息、cn_isp 下载状态行全数过打码（异常消息经 scheduler logger.exception 连同 traceback 落日志，同属暴露面）
  - Download-URL log redaction (C-batch Task 1, incident-driven: the OTX and IP2PROXY tokens each leaked once — the warn_if_redirected tripwire printed the full token-bearing download URL into docker logs): a single-source redact_url helper keeps scheme+host+path and replaces the whole query with "?q=REDACTED" (no per-parameter allowlist — a token can hide under any parameter name; userinfo/fragment dropped too); the redirected tripwire, the download_file truncation error, the "Empty/empty response" exception messages in both base classes and seven sources, and the cn_isp download status line all route through it (exception messages land in logs via the scheduler's logger.exception together with the traceback — same exposure surface)
- 谱系派生集改源类 attr 真相驱动（R1-F1）：DERIVED_SOURCES 从固定字面量改为 _registry 导入时按各源 class attr `derived` 原位灌装（同 SOURCE_RELIABILITY 模式；greensnow 补 derived=True 修正 attr/集合漂移），CI 断言同步为「attr 派生集 == DERIVED_SOURCES 镜像」；eval 侧 _eval/config.py 清单与生产有意分立（注释备案）
  - The lineage derived-set is now driven by source-class attrs (R1-F1): DERIVED_SOURCES switches from a fixed literal to fill-in-place from each source's `derived` class attr at _registry import (same pattern as SOURCE_RELIABILITY; greensnow gains derived=True, fixing the attr/set drift), the CI assertion becomes "attr-derived set == DERIVED_SOURCES mirror", and the eval-side list in _eval/config.py stays deliberately separate (documented in-code)
- 校准 reliability 即时驱动威胁融合（DM-1，裁决 #13）：查询路 to_observation 改表优先——SOURCE_RELIABILITY（含 _calibrated.json 后验覆盖）非空即用，payload/class attr 兕底；声明 r 与校准 r 的双臂分裂消除，GLOSSARY「后验覆盖通道」措辞对齐（通道现及融合）；无 _calibrated.json 时零漂移（输出逐位一致）
  - Calibrated reliability now drives threat fusion immediately (DM-1, adjudication #13): the query-path to_observation goes table-first — SOURCE_RELIABILITY (including _calibrated.json posterior overrides) wins when non-empty, with payload/class-attr as fallback; the declared-r vs calibrated-r arm split is gone and the GLOSSARY "posterior override channel" wording now says the channel reaches fusion; with no _calibrated.json present, zero drift (byte-identical output)
- 权威矩阵幻影轴删除（SM-F1，裁决 #12）：ipinfo_lite 撤 is_hosting/is_mobile 声明（无产出），threatfox/emerging_threats/spamhaus 撤 is_malicious（无证据键生产者），_AUTHORITY_FIELDS 相应去键；AUTHORITATIVE_SOURCES 展示层机制保留，danmeuk/binarydefense 等注释「veto」措辞如实化；api/sources 公共契约快照同步（幻影 x_authoritative 消失）
  - Phantom authority axes pruned from the authority matrix (SM-F1, adjudication #12): ipinfo_lite drops its is_hosting/is_mobile claims (no output), threatfox/emerging_threats/spamhaus drop is_malicious (no evidence-key producer), _AUTHORITY_FIELDS loses the keys accordingly; the AUTHORITATIVE_SOURCES display-layer mechanism stays, the "veto" comment wording on danmeuk/binarydefense etc. is made honest; the api/sources public-contract snapshot updates (phantom x_authoritative entries disappear)
- abuseipdb 刷新 12h→48h(F-1 配额修复,2026-10-07 拍板):stale_days 1→2,免费层 5 次/天配额下基线消耗从 2/5 每天降为 0.5/5 每天(48h 一次),恢复富余给失败重试(1h→12h 退避梯限速);调度器 12h 槽位格与其余源节奏不变(per-source min_refresh 留后续批)
  - abuseipdb refresh moves 12h→48h (F-1 quota fix, adjudicated 2026-10-07): stale_days 1→2 drops the scheduled baseline on the 5-requests/day free tier from 2/5 per day to 0.5/5 (one pull per 48h), restoring headroom for retry rounds (paced by the 1h→12h backoff ladder); the scheduler's 12h slot grid and every other source's cadence are unchanged (a per-source min_refresh knob is deferred to a later batch)
- 威胁列更名「标签」，成为该 IP 全部事实类徽章的家：威胁 chips 在前、资产 chips（CDN 边缘/云/VPN/代理/hosting/carrier）在后、源数/存档/冲突殿后；资产 chips 自判定列与运营者列迁入（运营者列留 ISP 徽章与域名副行），判定列回归纯判定
  - Threat column renamed to Tags, the home for every fact badge of the IP: threat chips first, asset chips (CDN edge/cloud/VPN/proxy/hosting/carrier) after, source count/archive/conflict last; asset chips migrated in from the verdict and operator columns (operator keeps the ISP badge and the domain subtitle), and the verdict column is back to pure verdicts
- 多类别指控融合:顶层 threat.confidence 改证据级重融合——同一 IP 的多类独立佐证全部计入 P(恶意) 后验,多类别指控 IP 分数整体上移(生产镜像全量回放:升 130,696 / 平 3,348,156 / 降 18,平均 Δ+0.18;分数×独立源数区分度 ρ 0.412→0.504);数字语义不变(仍为 P(恶意) 后验 0–100),fail2ban 等消费方 70 阈值继续有效;已知良性段(云/CDN)的误报影响 ≤0.0013%(全量分母 1.74 亿 IP,新增 2,233 个过线,均为 ≥2 独立源佐证,且无 IP 从 ≥70 降破);配套前端页眉威胁分改消费后端 threat 单一真相(本地推导降为回退)
  - Multiclass-accusation fusion: the top-level threat.confidence becomes an evidence-level re-fusion — every independent cross-class corroboration for an IP now feeds the P(malicious) posterior, lifting scores of multi-class IPs as a whole (full replay on the production mirror: 130,696 up / 3,348,156 flat / 18 down, mean Δ+0.18; score-vs-independent-source discrimination ρ 0.412→0.504); the number's semantics are unchanged (still the P(malicious) posterior on 0–100), so consumers like fail2ban keep their 70 threshold working; impact on known-benign cloud/CDN ranges stays ≤0.0013% (2,233 newly-over-70 IPs out of a 174M-IP full denominator, all corroborated by ≥2 independent sources, and zero IPs dropped below 70); the web header score now consumes the backend threat field as the single source of truth (local derivation demoted to a fallback)
- 云厂商五源融合为 cloud_ranges：aws_ranges / gcp_ranges / azure_ranges / oracle_ranges / alibaba_ranges 并为单表驱动源（同一 asset 契约：service=cloud、is_hosting、provider 身份、asset-only 空裁决），五 feed 声明表逐家拉取（Azure 两步直链、Alibaba 内容守卫逐字保留）；部分失败容忍——单家挂仅告警且保留旧中间文件（旧数据继续可查），五家全挂才算失败；per-provider reliability 逐行查表（官方自发布 0.95 ×4，Alibaba 第三方聚合商 0.75）；源健康 feeds 分项（FeedHealth）+ 前端源页逐 feed 健康芯片；旧五源数据文件与 LMDB sidecar（含 v6 变体）由新源首次 download 自动清理，无需手工迁移；公开源口径 44→40
  - Cloud-provider five-source fusion into cloud_ranges: aws_ranges / gcp_ranges / azure_ranges / oracle_ranges / alibaba_ranges merged into one table-driven source (identical asset contract: service=cloud, is_hosting, provider identity, asset-only empty verdict), fetched publisher-by-publisher from a five-feed declaration table (the two-step Azure direct link and the Alibaba content guard kept verbatim); partial-failure tolerance — a single failed feed only warns and keeps its last intermediate (old data stays queryable), only total failure raises; per-provider reliability is per-row from the table (publisher-self 0.95 ×4, Alibaba third-party aggregator 0.75); per-feed health via SourceHealth.feeds (FeedHealth) with per-feed health chips on the admin sources page; the five legacy data files and their LMDB sidecars (v6 variants included) are auto-cleaned by the new source's first download — no manual migration; public-source count moves 44→40
- turris_greylist 定级修正:suspicious → malicious(传感器观测类对齐 dshield/ciarm/dataplane;FP 折价归 reliability 0.60 唯一折价轴)
  - turris_greylist regrade: suspicious → malicious (align the sensor-observation class with dshield/ciarm/dataplane; the FP-risk discount stays in reliability 0.60, the sole discount axis)
- GeoIP 大源 LMDB payload 字典化（interning）：同 epoch 双命名 sub-db（`pidx` 构建期去重索引 + `payloads` 读期字典），值格式 `[end, dict_id]` 与旧 `[end, evidence]` 自描述共存，提交前 `drop(pidx)` + `copy(compact=True)` 收割幽灵页。同料 A/B 实测：dbip 835→358MB（0.43×），命中延迟交错基准 3.0→4.1µs（1.38×，绝对值 <10µs），2,000 随机探测新旧 payload 全等；旧 epoch 零迁移可读，44 源零改动自动受益，重建墙钟 +3%
  - GeoIP sources gain LMDB payload interning: a same-epoch dual named sub-db layout (`pidx` build-time dedup index + `payloads` read-time dictionary); the value format `[end, dict_id]` coexists self-describingly with the legacy `[end, evidence]`, and a pre-commit `drop(pidx)` + `copy(compact=True)` reclaims ghost pages. Same-feedstock A/B measured on dbip: 835→358MB (0.43×), interleaved hit latency 3.0→4.1µs (1.38×, absolute <10µs), 2,000 random probes byte-identical old vs new; old epochs stay readable with zero migration, all 44 sources benefit automatically with no source-code changes, rebuild wall clock +3%
- 管理台源列表 grid 化:全局表头+响应式列(评估 lg+/θ xl+)+滚动锁步,修复按钮换行下沉;组头"地理 / ASN 数据"更名;管理壳 max-w-6xl
  - Sources list regrid: global header + responsive columns (eval lg+/θ xl+) + scroll lockstep, fixes button wrap; group renamed "Geo & ASN data"; admin shell max-w-6xl

### 移除 Removed

- 移除 sentinel/水印机制(裁决 #5,2026-10-07:数据走向开源许可,防盗前提消失):内部合成哨兵源(canary,internal=True,从不计入公开源口径)与谱系标记整体拆除——公开答案对 ~500 个哨兵 IP 不再返回 suspicious;rebuild 不再嵌入 ingest_ref 概率印记;内部源(internal)接线全部移除,源注册表回归单一口径;核验 CLI 一并删除
  - Removed the sentinel/watermark mechanism (adjudication #5, 2026-10-07: the dataset is heading to an open license, dissolving the anti-theft premise): the internal synthetic canary source (internal=True, never counted in the public-source tally) and its lineage marks are torn out wholesale — public answers no longer return suspicious for the ~500 canary IPs; rebuilds no longer embed the ingest_ref probabilistic mark; the internal-source wiring is gone entirely, leaving one uniform source registry; the verifier CLI goes with it

### 修复 Fixed

- 修复：未知 API key 404 独立语义码（AS-8，审计：按 code 分支的客户端把密钥错误当源错误）——admin 密钥路由 PATCH/DELETE 对不存在 sub 的 404 从复用 source_not_found 改为 api_key_not_found；源侧 404（GET/eval 未知源、PATCH sources 未知源）维持 source_not_found 不变，两套码各有测试钉住
  - Fix: unknown API key 404s gain their own semantic code (AS-8, audit: code-branching clients read key errors as source errors) — the admin key routes' PATCH/DELETE 404 for a nonexistent sub switches from reusing source_not_found to api_key_not_found; source-side 404s (unknown source on GET/eval and PATCH sources) keep source_not_found unchanged, both code families pinned by their own tests
- 修复：前端可靠性三连+速赢（C 批 Task 3，审计 U7/U9/U10/U5/U11）——①任务控制端点失败反馈（U7）：cancelTask/cancelBatch/pause/resume 四函数非 ok 现走统一信封 reject（status+code），任务面板的暂停/恢复/终止/逐任务取消失败时红字横幅展示（401 踢回登录页，同 admin 面既有约定）；②底栏失败态重试（U9）：db-status 拉取全挂的常驻红条补就地 Retry 入口（重拉同一公开接口，成功即恢复，成功/警告态仍纯只读）；③密钥复制降级（U10）：copyText 自 VersionBanner 收编为共享 helper，密钥一次性展示的复制在 http:// 非安全上下文（自托管 LAN 主场景，navigator.clipboard 为 undefined）降级 execCommand，两路皆挂不假装已复制；④zh 空态引导改实际按钮名「更新」/「全部刷新」（U5，en 侧核查本就一致）；⑤死 locale 键双侧清除（U11：dbStatus.downloading/loading/starting、column.threat，引用面零残留）
  - Fix: frontend reliability trio + quick wins (C-batch Task 3, audit U7/U9/U10/U5/U11) — ① task-control failure feedback (U7): cancelTask/cancelBatch/pause/resume now reject through the unified envelope on non-ok (status+code), and the task panel's pause/resume/abort/per-task-cancel failures surface as a red banner (401 kicks to the login page, per the established admin convention); ② bottom-bar failure retry (U9): the persistent red bar from a fully-failed db-status fetch gains an in-place Retry entry (re-fetches the same public endpoint, recovering on success; success/warning states stay purely read-only); ③ key-copy fallback (U10): copyText is promoted from VersionBanner to a shared helper, so the copy on the one-time key reveal falls back to execCommand on non-secure http:// contexts (the primary self-hosted LAN scenario, where navigator.clipboard is undefined), and never pretends "copied" when both paths fail; ④ the zh empty-state guidance now names the actual buttons 「更新」/「全部刷新」 (U5; the en side verified already accurate); ⑤ dead locale keys removed from both sides (U11: dbStatus.downloading/loading/starting, column.threat — zero references)
- 修复：指控/存档语义轴四连（R17A-1/SM-F2/AS-1/I18N-F1）——①弃权拼写 verdict="" 在 Evidence.to_dict 序列化中特判保留，读回不再兑底 malicious（三处归因错位注释同步修正）；②ip2proxy DCH 段从「other 指控章 conf=80」改为 asset-only（is_hosting+空裁决，同 cloud_ranges 形状；VPN/PUB/TOR 不动），云网段不再被当威胁断言（重建后生效）；③STIX 导出只对指控章（malicious/suspicious）产 Indicator，存档/信息级分类不再导成拉黑 Indicator；④zh 词典 benign「可信」改「良性」（弃权非信任背书）
  - Fix: four-part accusation/archive semantics axis (R17A-1/SM-F2/AS-1/I18N-F1) — ① the abstention spelling verdict="" is specially preserved through Evidence.to_dict serialization, no longer defaulting back to malicious on read (three misattributed comments realigned); ② ip2proxy DCH segments switch from an "other" accusation chapter at conf=80 to asset-only (is_hosting + empty verdict, mirroring cloud_ranges; VPN/PUB/TOR untouched — takes effect after the next rebuild), so cloud ranges are no longer asserted as threats; ③ STIX export produces Indicators only for accusing chapters (malicious/suspicious), archive/informational classifications no longer become blocklist Indicators; ④ the zh dictionary's benign moves from "可信" (trustworthy) to "良性" (benign; abstention is not an endorsement)
- 修复：eval CG 只计指控票（EV-F1）——_effective_votes 加 verdict 过滤（缺键兑底 malicious=生产读路径同口径，旧快照兼容），纯存档↔存档共现不再挣 POSITIVE-VERIFIED，eval 臂与生产 corroborated 口径对齐
  - Fix: eval CG counts only accusing votes (EV-F1) — _effective_votes gains a verdict filter (missing key defaults to malicious, matching the production read path for old-snapshot compatibility); pure archive↔archive co-occurrence no longer earns POSITIVE-VERIFIED, aligning the eval arm with production corroborated semantics
- 修复：emerging↔spamhaus 谱系锚回声折扣（DQ-1）——新增 LINEAGE_ANCHORS={emerging_threats: spamhaus}（emerging 块清单 ⊇ spamhaus DROP，/12 巨块回声 LMDB 实证），dedup_lineage 对锚源在场且系数不低于目标的谱系对做剔除（宁少算；锚缺席或更弱则保留），42.208.0.0/12 式三源回声有效票 3→2
  - Fix: emerging↔spamhaus lineage-anchor echo discount (DQ-1) — adds LINEAGE_ANCHORS={emerging_threats: spamhaus} (emerging's block list ⊇ spamhaus DROP, /12 mega-block echo verified in the live LMDB); dedup_lineage drops lineage pairs whose anchor is present with a coefficient no lower than the target (better to under-count; a missing or weaker anchor keeps the target), so a 42.208.0.0/12-style three-source echo yields 2 effective votes instead of 3
- 修复：count sidecar 与 LMDB 实际键数背离（DQ-2）——.count 改在 commit 时从提交 env 的主库键数回写（env.stat() 减 payloads 命名库描述符键），不再取流式行数或 CsvSource 证据数覆写；重复行/同起点 CIDR 碰撞不再虚增 UI record_count（本地实测 tor_exits 3328 行 vs 1431 键、firehol +1926 等 7 源背离）；存量背离源待各自下轮 rebuild 自然回写（部署注记：ip2proxy touch raw 触发重建后 DCH 弃指控同步生效）
  - Fix: count sidecar diverged from the LMDB's actual key count (DQ-2) — .count is now written at commit time from the committed env's main-db key count (env.stat() minus the payloads named-db descriptor key), replacing both the streamed-row count and the CsvSource evidence-count override; duplicate rows and same-start CIDR collisions no longer inflate the UI record_count (local measurement: tor_exits 3328 rows vs 1431 keys, firehol +1926, seven sources diverging in total); existing diverged sidecars self-correct on each source's next rebuild (deployment note: touching ip2proxy raw triggers the rebuild through which the DCH abstention also takes effect)
- 修复:下载传输层截断守卫(DL-F1,P0)——download_file 循环以空读当干净 EOF 收尾,received 从不与 Content-Length 比对,mid-body 断连的截断文件被原子落盘为「好文件」并照常解析成缩水 epoch(文本族 feed 无结构校验兜底,gz/zip/mmdb/JSON 源有天然免疫);现诚实 CL 下 received != Content-Length 在提交前抛错、旧文件字节级保留,chunked 传输(total=0)零误报
  - Fix: transport-layer truncation guard for downloads (DL-F1, P0) — the download loop treated an empty read as a clean EOF and never compared received bytes against Content-Length, so a mid-body disconnect's truncated file was atomically installed as a "good file" and parsed into a shrunken epoch (plain-text feeds have no structural checksum to catch it; gz/zip/mmdb/JSON sources are naturally immune); now, under an honest Content-Length, received != Content-Length raises before commit and the old file is preserved byte-for-byte, with chunked transfers (total=0) never false-flagged
- 修复:全仓统一原子写(DL-F2+F-5)——新增单一 atomic_write_bytes 助手并收编全部直写落点(Source.download 基类 resp.read()+write_bytes 族、otx CSV open("w")、cn_isp 逐文件、danmeuk 校验后落地;abuseipdb/ipinfo_lite 为 rename/流式 scratch 同款语义变体,不经助手本体),kill/ENOSPC 窗口下半写文件+新 mtime 换 ptr 提交缩水 epoch 的路径消除(ENOSPC 注入测试钉住)
  - Fix: atomic file writes unified repo-wide (DL-F2 + F-5) — a single atomic_write_bytes helper absorbs every direct-write site (the Source.download resp.read()+write_bytes family, the otx CSV open("w"), cn_isp's per-feed writes, and danmeuk's post-validation install; abuseipdb/ipinfo_lite are rename/streaming-scratch variants with the same semantics, not routed through the helper itself), closing the kill/ENOSPC window where a half-written file with a fresh mtime would hand a shrunken epoch to the pointer swap (pinned by ENOSPC-injection tests)
- 修复:多列表源部分失败语义(SA-F1+F-4)——firehol/blocklist_de/cn_isp/dataplane 单列表失败从「删旧好文件+提交缩水 epoch+零信号」改为 cloud_ranges 模式:旧文件保留、失败名记 last_partial_failure(调度器 done-但-部分失败路径走 1h→12h 退避梯自愈;例外:dataplane 为 join 单文件,部分失败以成功 parts 的缩水 join 覆写旧文件——新旧无法混合,缩水窗口由该退避梯封顶,计划已裁),全挂判据改为本轮失败计数(旧文件存在时不再静默吞掉全挂);spamhaus/x4bnet_vpn v6 兄弟失败不再 v4-only 覆写(旧 join 文件字节级保留);IpListSource 基类 download 重构为 scratch-then-replace,失败路径永不触碰数据文件
  - Fix: partial-failure semantics for multi-list sources (SA-F1 + F-4) — a single failed list in firehol/blocklist_de/cn_isp/dataplane no longer deletes the previous good file, commits a shrunken epoch, and signals nothing; it follows the cloud_ranges pattern (keep the old file, record the failed names in last_partial_failure, and let the scheduler's done-but-partial path self-heal on the 1h→12h backoff ladder; exception: dataplane is a single joined file, so a partial failure overwrites the old file with a shrunk join of the successful parts — old and new cannot be mixed — with that shrink window capped by the same ladder, per the plan's adjudication), with the all-fail criterion now this round's failure count (a total failure no longer passes silently when old files exist); spamhaus/x4bnet_vpn no longer overwrite with a v4-only join when the v6 sibling fails (old file preserved byte-for-byte); the IpListSource base download is restructured to scratch-then-replace so the failure path never touches the data file
- 修复:公开演示部署下管理员会话的更新进度静默(任务订阅被 demo 探测误闸;现挂载即订阅,会话失效自愈断流)
  - Fix: update progress silently dead for admin sessions on public-demo deployments (task subscription wrongly gated by demo probe; now subscribes on mount, self-heals on dead session)
- 修复：verdict 列 CDN 边缘徽章曾与“可疑”判定同用琥珀色且窄列内错位换行（#85 临时同列排版）；根治为迁入标签列，与其它资产 chips 同用天蓝资产族配色，判定列回归纯判定
  - Fix: the CDN edge badge once shared the suspicious verdict's amber palette and wrapped misaligned inside the narrow verdict column (#85 interim same-column layout); root-fixed by moving it into the Tags column alongside the other asset chips in the sky asset-family palette, with the verdict column back to pure verdicts

## v1.4.1 — 2026-09-28

### 调整 Changed

- stopforumspam 降权 reliability 0.70→0.60(用户拍板 2026-09-28,规则内保守档):月轮 eval 首跑实测 θ=0.001(n=117,k=0 零佐证)+ below-market 标记;缓解面=spam 轴 niche(unique 0.48)+ informational 裁决,故不一步到 .55。语料:model-20260928-144045(生产镜像月轮首跑,5/5 checks PASS)
  - stopforumspam demoted, reliability 0.70 -> 0.60 (user-approved 2026-09-28, conservative in-rule step): the first monthly eval round measured theta=0.001 (n=117, k=0 — zero corroborations) plus a below-market flag; mitigating context = the spam axis is a corpus niche (unique share 0.48) and its verdict is informational, hence not dropping all the way to .55. Corpus: model-20260928-144045 (first monthly round on the production mirror, 5/5 checks pass)

### 修复 Fixed

- abuseipdb 生产断供根因修复(P1 实锤 2026-09-28):旧 download() 直写数据文件且 except 分支 unlink——免费层 5 次/天配额被重试烧穿(429)后,每次失败都删掉既有好文件 → raw 永久缺失、LMDB 冻结 9,987 条、stale 恒真。改为 scratch 落盘 + 校验通过才提交(danmeuk 同款),失败永不触碰数据文件
  - abuseipdb production outage root-cause fix (P1, confirmed live 2026-09-28): the old download() wrote straight to the data file and unlinked it in the except branch — once the free-tier 5-requests/day quota was burned by retries (429), every failure deleted the previously-good file, leaving the raw permanently missing, the LMDB frozen at 9,987 records, and is_stale stuck true. Now fetches to a scratch file and commits only after validation (same pattern as danmeuk_tor); a failed download never touches the existing data file
- 公开演示守卫硬化：①OPTIONS 豁免收紧为真 CORS 预检形状（`Origin` + `Access-Control-Request-Method` 两头齐全，裸 OPTIONS 走既有 404/403 判定）；②`/api/update/status` 全部署形态要求管理员鉴权（原完全公开）；③守卫 404/403 改用标准错误信封（`not_found`/`forbidden`，新增 `ErrorCode.not_found`）；④`IP_RADAR_PUBLIC_DEMO` 设为非 "1" 非空值时启动告警（唯一生效值是精确 "1"，绝不阻断启动）；⑤守卫注释口径更新（维护者旁路 = ADMIN_IPS 直连 peer + 可选 XFF 信任，须配套网关保证）；⑥README 双语补 XFF 信任安全前提段
  - Public-demo guard hardening: ① OPTIONS exemption narrowed to real CORS preflights (both `Origin` and `Access-Control-Request-Method` present; bare OPTIONS falls through to the existing 404/403 checks); ② `/api/update/status` now requires admin auth in every deployment (was fully public); ③ guard 404/403 switched to the standard error envelope (`not_found`/`forbidden`, new `ErrorCode.not_found`); ④ a non-"1" non-empty `IP_RADAR_PUBLIC_DEMO` logs a startup warning (the only effective value is exactly "1"; never blocks startup); ⑤ guard comment doctrine updated (maintainer bypass = direct-peer ADMIN_IPS plus opt-in XFF trust that requires a gateway guarantee); ⑥ both READMEs gain the XFF-trust security-premise paragraph
### 新增 Added

- 新源 alibaba_ranges（cloud-ip-ranges.com 聚合的阿里云网段表）：云足迹第 5 名成员（aws/gcp/azure/oracle 之后），service=cloud + is_hosting、provider 标签 Alibaba、asset-only 空裁决；第三方聚合非官方自发布 → reliability 0.75（官方系 0.95）；观测 2026-09-28：2,394 CIDR（v4 2,148 / v6 246）、零重复、Last-Modified 每日 04:00 UTC 推进（站方许可未声明，非商用用户拍板 2026-09-28）；下载内容守卫拒 200-HTML 错误页；新增后公开源 43→44 口径
  - New source alibaba_ranges (Alibaba Cloud ranges aggregated by cloud-ip-ranges.com): fifth member of the cloud footprint family (after aws/gcp/azure/oracle), service=cloud + is_hosting, provider label Alibaba, asset-only empty verdict; third-party aggregator rather than publisher-self → reliability 0.75 (official houses sit at 0.95); observed 2026-09-28: 2,394 CIDRs (v4 2,148 / v6 246), zero duplicates, Last-Modified advancing daily 04:00 UTC (site license unstated; approved for non-commercial use 2026-09-28); download content guard rejects 200-HTML error pages; public-source count moves 43→44
- admin 选源器(SourcePickerBody,创建/编辑/种子行共用)新增「全选 / 反选」:物化当前源目录为显式清单(区别于「全部源」开关的 null 动态语义,固化场景从此不用逐个点勾)
  - admin source picker (SourcePickerBody, shared by create/edit/seed-row) gains Select all / Invert selection: materializes the current catalog as an explicit list (unlike the all-sources switch's null dynamic semantics — frozen-set workflows no longer need per-source clicks)
- 新源 danmeuk_tor（dan.me.uk Tor 节点表）：`is_tor` / `tor` 分类的第二独立证人（官方 tor_exits 保留权威否决位，新源只佐证）；`/torlist/` 为全量 relay 口径（native 标签 RELAY，~10.7k 行，2026-08-23 存档观测、2026-09-28 复核）；30 分钟拉取限速，12h 自动刷新在限内（手动更新同计限速）；下载内容守卫拒绝限速 200-HTML 页，数据文件永不被替换；新增后公开源 42→43 口径
  - New source danmeuk_tor (dan.me.uk Tor node list): a second independent witness for `is_tor` / the `tor` classification (official tor_exits keeps its authoritative veto; the new source corroborates only); the `/torlist/` URL ships the full relay set (native label RELAY, ~10.7k rows, 2026-08-23 archived capture re-verified 2026-09-28); fetch rate limit is one pull per 30 minutes, the 12h auto-refresh stays within it (manual updates count against the limit too); a download content guard rejects the rate-limit 200-HTML page so the data file is never replaced; public-source count moves 42→43
- eval v2 Phase 1(设计:docs/superpowers/specs/2026-09-28-eval-algorithm-optimization-brief.md):评估语料加中性公网层静态资产(逐轮恒定,eval 与源自家 raw 佐证解耦)
  - eval v2 Phase 1 (design: docs/superpowers/specs/2026-09-28-eval-algorithm-optimization-brief.md): a static neutral public-network corpus layer in the eval corpus (constant across rounds, decoupling eval evidence from each source's own raw feeds)
- eval v2 Phase 1:LSO 双轨制——scores/checks 维持旧基线(不含源自身佐证),leave-self-out 去偏结果降为 advisory 视图(scores_lso + "LSO advisory" 报告节)
  - eval v2 Phase 1: dual-track LSO — scores/checks keep the old baseline (self-evidence included), while leave-self-out debiased results are demoted to an advisory view (scores_lso + the "LSO advisory" report section)
- eval v2 Phase 1:NO-DATA 双判据 verdict(feed 空 / record-count 相对历史坍塌,先于其它判定)+ 模型报告 source_health 块 + C1 specialist 分支;前端源页 NO-DATA 灰底红字徽章(title 说明“数据为空或坍塌,该源未在贡献”)
  - eval v2 Phase 1: NO-DATA dual-criteria verdict (feed empty / record-count collapse vs history, gated ahead of all other verdicts), a source_health block in the model report, and the C1 specialist branch; the frontend sources page renders a NO-DATA badge (red on gray, titled "feed empty or collapsed — source did not contribute")
- eval v2 Phase 1:`--temporal` λ_s prequential 确认率仪器(Fisher 精确检验 + Wilson CI,预注册 θ̂ 中位数拆分,需 ≥2 轮 model 历史)
  - eval v2 Phase 1: `--temporal` λ_s prequential confirmation-rate instrument (Fisher exact test + Wilson CI, preregistered θ̂ median split, requires ≥2 rounds of model history)
- eval v2 Phase 1:谱系审计改前向流方向判定(替换 Dong 时钟,三态 confirmed/not-yet/no-relation + C-3 双向检查);新增 scripts/monthly_eval.sh 月轮脚本(master+clean 守卫 → rsync 生产镜像 → 五连 eval 命令,--dry-run 预演)
  - eval v2 Phase 1: lineage audit switches to forward-flow direction (replacing the Dong clock, three states confirmed/not-yet/no-relation + the bidirectional C-3 check); adds scripts/monthly_eval.sh for monthly rotation (master+clean guards → rsync prod mirror → the five eval commands, with --dry-run rehearsal)
- 公开演示守卫(opt-in,净移植自 demo 分支):`IP_RADAR_PUBLIC_DEMO=1` 开启守卫中间件套件——写/内部端点对匿名访客 404(当作不存在)、查询面校验 `x-ipradar-client: web` 头、维护者直连 peer IP 旁路(`IP_RADAR_DEMO_ADMIN_IPS`,XFF 可伪造勿默认信;`IP_RADAR_DEMO_TRUST_XFF=1` 须配套网关保证);默认关闭,未设 env 零行为变化
  - Public-demo guard (opt-in, byte-for-byte port from the demo branch): `IP_RADAR_PUBLIC_DEMO=1` enables the guard middleware suite — write/internal endpoints answer 404 to anonymous visitors, query endpoints enforce the `x-ipradar-client: web` header, and maintainers bypass via direct-peer IPs (`IP_RADAR_DEMO_ADMIN_IPS`; XFF is forgeable, don't trust by default — `IP_RADAR_DEMO_TRUST_XFF=1` requires a gateway guarantee); off by default, zero behavior change without the env
- 前端配套：所有请求带 `x-ipradar-client: web` 头；STIX 导出改同源 fetch+blob 下载（鉴权路径与页面一致，过守卫同规）
  - Frontend companion: every request carries the `x-ipradar-client: web` header; STIX export switches to same-origin fetch+blob download (same auth path as the page, same rule through the guard)

### 修复 Fixed

- CI:后端测试批更新竞态——`test_update_db_enqueues_returns_batch_id` 打桩 `manager.enqueue_batch`,消灭真网络副作用与 `_active_batch` 跨测试泄漏
  - CI: backend test batch-update race — stub `manager.enqueue_batch` in `test_update_db_enqueues_returns_batch_id`, eliminating real-network side effects and cross-test `_active_batch` leakage

## v1.4.0 — 2026-09-26

### 新增 Added

- 每 key 绑定源集合（PR #66）：`api_key_meta.sources` 列（幂等迁移；NULL = 全部公开源）；查询/STIX/流式/批量全链路按 key 收窄，db-status 计数同按身份收窄
  - Per-API-key source sets (PR #66): `api_key_meta.sources` column (idempotent migration; NULL = all public sources); lookup/STIX/stream/batch all narrow per key, db-status counts narrow by identity too
- demoweb 种子行与同源身份：同源网页免钥映射到种子行 scope（fail-closed：行缺失/禁用即拒），支持编辑源集合与吊销（作 kill switch，吊销后可一键重新启用），删除受 403 保护
  - demoweb seed row & same-origin identity: the same-origin web maps to the seed row's scope without a key (fail-closed — a missing or disabled row refuses queries); it supports Edit-sources and Revoke (as a kill switch; a revoked row can be re-enabled with one click), and deletion stays 403-protected
- admin 密钥页源集合多选 + web 徽章（zh/en 双语）：创建/编辑弹窗按目录分组多选，“全部源”开关默认开
  - Admin keys-page source multiselect + Web badge (zh/en): grouped catalog multiselect in the create/edit modals, with an all-sources toggle on by default
- 私源保密（`IP_RADAR_PRIVATE_SOURCES`，逗号分隔，启动时读入，拼错启动告警）：web/匿名身份与 null-scope key 永不可见；admin 可对普通 key 显式授予，web 种子行除外（写入 422 硬拒 + 运行时再滤，防“先公后私”存量授予）
  - Private-source secrecy (`IP_RADAR_PRIVATE_SOURCES`, comma-separated, read at startup, typo warning on boot): invisible to web/anonymous identities and null-scope keys; an admin may grant one explicitly to a regular key, but never to the web seed row (422 hard reject on write + runtime re-filter, guarding grants that predate a source going private)

## v1.3.1 — 2026-09-24

### verdict-aware scoring(spec 2026-09-06)

- 存档章(informational)退出威胁置信度:数字仅由指控章(恶意/可疑)源决定,混合组(含指控源)数字不变;纯存档组沿用旧公式;源计数与 reporter_total 照旧包含存档观测
  - Archive-stamped observations (informational) no longer feed threat confidence: the number is decided solely by accusing sources (malicious/suspicious); mixed groups (with accusing sources) keep their numbers, archive-only groups keep the legacy formula, and source counts and reporter_total still include archive observations
- "冲突"重定义为真对立(benign × 指控,现无 benign 源 → 恒 false 占位);定级分歧改由"含存档记录"黄灯表达
  - "Conflict" redefined as true opposition (benign × accusing; no benign source today → constant-false placeholder); grading disagreements are instead expressed by the "含存档记录" (contains archive records) amber signal
- "已印证"只数指控源;明细逐条带 verdict;API 新增 has_archive
  - "Corroborated" counts accusing sources only; every detail row carries its verdict; the API gains has_archive
- CSV `verdict_conflict` 列值随新语义(今天恒 false,列结构不变);eval Conflict 指标同
  - CSV `verdict_conflict` follows the new semantics (constant false today; column structure unchanged); same for the eval Conflict metric

### 新增 Added

- 三条数据质量绊线(IntelMQ 审计落地):normalize() 未命中映射的原生值按 (map,key) 去重告警一次(上游新增/改名分类码当天可见);rebuild 中央检查 first_seen 可解析性,批末汇总告警(脏格式此前静默按无衰减计=最大权重);下载层重定向预警(geturl≠请求 URL,feed URL 腐烂最早信号,覆盖 download_file/_http_get/默认 download 三路径)
  - Three data-quality tripwires (IntelMQ audit follow-up): normalize() warns once per (map,key) on unmapped native values (upstream category additions/renames surface same-day); rebuild() centrally checks first_seen parseability with an end-of-batch summary (dirty formats previously decayed silently at full weight); download layer warns on redirects (geturl != requested URL - earliest feed-URL-rot signal, covering download_file/_http_get/default download)
- feed 变更沉淀约定:凡改源 URL/文件名/解析形态,必落 CHANGELOG `feed-change:` 条目(IntelMQ upgrades.py 纪律的本地等价物);分类词表版本锚定注释落地 _classification.py(对照 RSIT v1003 / IntelMQ develop@bbe452a)
  - Feed-change sedimentation convention: any source URL/filename/parse-shape change must land a CHANGELOG `feed-change:` entry (local equivalent of IntelMQ's upgrades.py discipline); classification vocabulary version anchor added to _classification.py (RSIT v1003 / IntelMQ develop@bbe452a)
- 谱系审计(`python -m ipdb._eval --audit`)：基于持久化模型历史的镜像方向裁决；advisory，并对已知聚合源清单跑 C-3 零冤枉检查
  - Lineage audit (`python -m ipdb._eval --audit`): copying-direction verdicts
    from persisted model history; advisory, C-3 zero-false-accusation check
    against the known aggregator list.
- 锚点回归（`--anchors`）：精选已知答案 IP 集，任一失败退出码 1；后续凡触生产的改动必过此闸
  - Anchor regression (`--anchors`): curated known-answer IP set; exit 1 on any
    failure. Required gate for future production-touching changes.
- DS-EM 引擎 + `--dsem` 公平对决：逐源/逐 ctype 潜真值率估计（沉默计负、声明 r 锚定）与 T3 三方对决（市场 / 声明 / π̂）；advisory
  - DS-EM engine + `--dsem` fair fight: per-source/per-ctype latent-truth rate
    estimates (silence-as-negative, declared-r anchored) and the three-way T3
    comparison (market / declared / pi-hat). Advisory only.
- 数据源页：实测 θ（印证率，90% CI）与声明 r 并列展示
  - Sources page: measured θ (corroboration, 90% CI) shown beside declared r.
- 结果表：分值语义图例（posterior / consensus / calibration / fixed anchors），逐字段悬停说明
  - Results table: score-semantics legend (posterior / consensus / calibration
    / fixed anchors) with per-field hover.
- 数据水印（PR #62）：双层落印——canary 哨兵源（watermark canary sentinel，`internal=True` 不进 42 源口径）+ rebuild 层 gamma=1/512 概率印记（extra.ingest_ref）；另配双模式核验 CLI（探测 URL / 扫描数据目录）
  - Data watermarking (PR #62): two layers — a hidden canary sentinel source (watermark canary sentinel, `internal=True`, excluded from the 42-source count) plus a rebuild-layer gamma=1/512 probabilistic mark (extra.ingest_ref); a dual-mode verifier CLI rounds it out (probe a URL / scan the data dir)
- PyJWT API key 体系（PR #63）：签发/校验/元数据存储 + `/api/admin/keys` CRUD——明文仅签发时一次可见、列表脱敏、可吊销可删除
  - PyJWT API-key system (PR #63): issue/verify/metadata storage + `/api/admin/keys` CRUD — plaintext visible exactly once at issuance, masked in listings, revocable and deletable
- admin 控制台 `#/admin`（PR #63）：登录 + 标签页壳（数据源管理迁入、密钥管理、任务区，公开数据源页退役为只读）；全局迷你进度条、主题/语言切换
  - Admin console `#/admin` (PR #63): login + tabbed shell (source management moved in, key management, tasks area — the public sources page retired to read-only); global mini progress bar, theme/locale switchers
- slowapi 限流（PR #63）：匿名批量 6/min、匿名单查 30/min、持钥统一 60/min、登录防爆破
  - slowapi rate limits (PR #63): 6/min anonymous batch, 30/min anonymous single lookup, 60/min unified for key holders, plus a login brute-force guard

### 变更 Changed

- 分类词表 P1 迁移(IntelMQ 审计同宗):方言类型 botnet 全量迁往官方型 infected-system(botnet drone 语义:被恶意软件感染的主机,非 C2;RSIT malicious-code.infected-system,IntelMQ harmonization 亦将 botnet drone/ransomware 自动归此型);四张图改指:blocklist_de ircbot、urlhaus mirai/mozi/hajime、tweetfeed #botnet/#mirai/#mozi、reportedip code 23,另 blocklist_de 同 IP 裁决优先级表同步;词表清方言,前端标签/配色随之(zh 受感染系统 / en Infected System,红色系);存量记录刷新四源后生效
  - Classification vocabulary P1 migration: dialect type botnet fully migrated to the official infected-system (botnet-drone semantics: malware-infected hosts, not C2; RSIT malicious-code.infected-system, where IntelMQ harmonization also auto-maps botnet drone/ransomware); four maps re-pointed — blocklist_de ircbot, urlhaus mirai/mozi/hajime, tweetfeed #botnet/#mirai/#mozi, reportedip code 23 — plus blocklist_de's same-IP adjudication priority table; dialect purged from the vocabulary with frontend label/palette following (zh 受感染系统 / en Infected System, red family); stored records pick the new type up after refreshing the four affected sources
- dataplane 新订阅 smtpdata(SMTP DATA 投递行为 → spam,malicious)与 ntpmode7;信号语义经 2026-09-05 IntelMQ 官方对照审计修正:ntpmode7 → scanner/malicious(文件头实证列的是"发起 monlist 请求的源 IP"= 探测方,曾误读 victim 侧反射器归 vulnerable-system/informational);smtpdata 维持 spam,与 IntelMQ 官方 parser 的 scanner 为有意分歧(DATA = 实际投递报文体,RSIT spam 定义更贴合);dnsrd 维持 scanner(权威复核成立)
  - dataplane adds smtpdata (SMTP DATA delivery behavior -> spam, malicious) and ntpmode7; semantics corrected by the 2026-09-05 IntelMQ audit: ntpmode7 -> scanner/malicious (the file header itself lists SOURCE IPs sending monlist requests - probers, was misread as victim-side reflectors -> vulnerable-system/informational); smtpdata stays spam, a deliberate divergence from IntelMQ's parser (DATA carries actual message bodies; RSIT's spam definition fits better); dnsrd stays scanner (upheld)
- blocklist_de 子列表语义修正(同审计):mail → brute-force(上游 = "attacks on Mail/Postfix",攻击邮件服务器的攻击者,曾误归 spam);bots → spam(上游 = "spammed on IRC, open forums, wikis" 灌水滥用,曾误归 botnet)
  - blocklist.de sublist semantics fixed (same audit): mail -> brute-force (upstream = "attacks on Mail/Postfix" - attackers hitting mail servers, was mis-mapped spam); bots -> spam (upstream = "spammed on IRC, open forums, wikis", was mis-mapped botnet)

- stopforumspam 逐条分级：last_seen ≤90 天的记录 verdict 升为可疑（活跃垃圾发送者），其余保持信息；每条记录计算 0-100 咨询分（50% 新近度 + 50% 举报量，log10 千次饱和）存入 native_confidence，融合置信度仍为 log-odds 后验不变（实测 28.1% 记录升档，~13.7 万条）
  - stopforumspam per-record grading: records with last_seen ≤90d upgrade to verdict=suspicious (active spammers), the stale tail stays informational; a 0-100 advisory score (50% recency + 50% report volume, log10 saturating at 1000) rides in native_confidence while fusion confidence stays the untouched log-odds posterior (measured 28.1% of records upgrade, ~137k)
- 查询接口门控（PR #63）：同源或有效 API key 才放行（GET 同则）；管理端点与 /api/events 全部收进 superuser，同源网页免钥、程序化访问走 /admin API key
  - Query endpoints gated (PR #63): same-origin or a valid API key (GET under the same rule); all management endpoints and /api/events now sit behind superuser — same-origin web stays keyless, programmatic access uses an /admin API key
- 集成修复（PR #63）：fail2ban verdict glob 此前永不命中、wazuh 改发 Bearer、graylog content-pack 注意事项、XFF 仅信任已配置代理（代理后按真实 IP 限流需显式开启）
  - Integration fixes (PR #63): the fail2ban verdict glob never fired, wazuh now sends Bearer, a graylog content-pack caveat documented, and XFF trusts only configured proxies (per-IP limits behind a proxy need explicit opt-in)

### 安全 Security

- 安全加固（PR #64）：eval×3 与 sources GET 收进 admin 面；/docs /redoc /openapi.json 默认关闭（IP_RADAR_ENABLE_DOCS=1 显式开启）；SPA 静态兜底不再把非 404 压平成 200 首页；SECRET 未配置兜底 secrets.token_urlsafe；python-dotenv 升 1.2.2
  - Security hardening (PR #64): the three eval endpoints and sources GET moved behind the admin face; /docs /redoc /openapi.json off by default (IP_RADAR_ENABLE_DOCS=1 to enable); the SPA static fallback no longer flattens non-404 errors into a 200 index page; an unset SECRET falls back to secrets.token_urlsafe; python-dotenv bumped to 1.2.2
- 依赖升级清 PYSEC（PR #65）：fastapi 0.141.1 + starlette 1.6.0，清除 16+1 条 PYSEC 公告；冻结表枚举适配（_IncludedRouter）
  - Dependency bump clearing PYSEC (PR #65): fastapi 0.141.1 + starlette 1.6.0 clears 16+1 PYSEC advisories; frozen-table enum adaptation (_IncludedRouter)

## v1.3.0 — 2026-09-02

### 新增 Added

- 双模型评估框架：语料纪元 2026-09-01 冻结（per_type_n 30→60），模型级报告持久化断言历史、新增泉眼/唯一性列与专家源/垄断源脚注；greensnow 纳入 DERIVED_SOURCES 聚合谱系
  - Dual-model eval framework: corpus epoch frozen at 2026-09-01 (per_type_n 30→60); model-level reports persist assertion history and gain fountain/unique columns + specialist/monopoly footnotes; greensnow joins the DERIVED_SOURCES lineage
- 8 个威胁/VPN 源（29→37）：siberkapan、turris_greylist、threatcluster、drb_ra、hookzof、thespeedx、protonvpn、nordvpn
  - 8 threat/VPN sources (29→37): siberkapan, turris_greylist, threatcluster, drb_ra, hookzof, thespeedx, protonvpn, nordvpn
- 5 个信息面源（37→42）：dbip_city 城市第二投票源 + AWS/GCP/Azure/Oracle 官方网段（is_hosting 证人 1→5）
  - 5 info-surface sources (37→42): dbip_city as the city slot's second voting source + publisher-official AWS/GCP/Azure/Oracle ranges (is_hosting witnesses 1→5)
- 服务身份：详情面板新增 Service identity 分组，逐条展示服务声明（8.8.8.8 → DNS · Google Public DNS）
  - Service identity: new "Service identity" section in the detail panel lists every service claim per row (8.8.8.8 → DNS · Google Public DNS)

### 变更 Changed

- LMDB 构建提速：staging env 异步刷盘（sync=False/metasync=False/map_async=True，mdb_load -Q 同款）+ 批次 1 万→10 万，本地 NVMe 构建 18.3s→17.0s（服务器 overlayfs 月度重建收益更大）
  - Faster LMDB builds: the staging env now async-flushes (sync=False/metasync=False/map_async=True — the mdb_load -Q pattern) with batches up from 10k to 100k; local NVMe build 18.3s→17.0s (bigger win on the server's overlayfs monthly rebuild)
- LMDB 查询与写库核心：嵌套网段查询改 CIDR 前缀探测（≤33 次 O(log n) seek，根治深嵌套漏命中）；disjoint 预判移入写库循环（running max_end，免事后 O(n) 扫描）；dbip 双族整数快径（inet_pton + 位运算，harvest 103.3s→75.9s）
  - LMDB core: nested-range lookups now use CIDR prefix probing (≤33 O(log n) seeks — deep-nest misses fixed for good); the disjoint check moved into the write loop (running max_end, no post-hoc O(n) scan); dbip gained an integer fast path (inet_pton + bit ops, harvest 103.3s→75.9s)
- 文档口径收敛：README 双语重定位为「全面 IP 画像」，总源数只在开场白出现一次，其余位置改用稳定表述（「除 4 个密钥源外」）
  - Docs: READMEs repositioned as a "full IP profile" (bilingual); the volatile total count now appears once (hero line), everywhere else uses the stable "all but 4 keyed" phrasing

### 修复 Fixed

- 首次构建进度：总行数未知时保持 0% 展示，不再假造 n/n=100%
  - First-build progress: unknown totals now stay at 0% instead of a fake n/n=100%
- nordvpn 下载路径修正（nordvpn_ips_list.csv）
  - nordvpn download path fixed (nordvpn_ips_list.csv)

## v1.2.2 — 2026-08-26

详见 Release Notes：[v1.2.2 — 数据丰富度与展示管线](https://github.com/steponeerror/ip-radar/releases/tag/v1.2.2)（运营方列 + CDN 防误判徽章、VPN 可见性修复、查询结果更丰富、STIX 资产通道、更新横幅三连修复）

See release notes: [v1.2.2](https://github.com/steponeerror/ip-radar/releases/tag/v1.2.2) (operator column + CDN anti-ban badge, VPN visibility fix, richer results, STIX asset channel, three update-banner fixes).

## v1.2.0 — 2026-08-24

### 新增 Added

- IPv6 查询支持：双族 LMDB 存储（v4 数据零迁移）、裸 v6 / 小段 v6 CIDR 查询、v6 bogon 判定（纯 stdlib）；spamhaus DROPv6、x4bnet、Cloudflare ips-v6 等兄弟源接入，geo/ASN（ipinfo 61% 行、GeoLite 35%、iptoasn 25%）v6 全量入库；STIX 导出产 `ipv6-addr` SCO；`/api/db-status` 新增 `covered_v6_nets` 键
  - IPv6 lookup support: dual-family LMDB storage (zero v4 migration), bare-v6 / small-CIDR queries, stdlib-driven v6 bogon detection; sibling feeds wired in (spamhaus DROPv6, x4bnet, Cloudflare ips-v6) with geo/ASN fully indexed for v6 (61% of ipinfo rows, 35% of GeoLite, 25% of iptoasn); STIX export emits `ipv6-addr` SCOs; `/api/db-status` gains a `covered_v6_nets` key
- 页内版本通知：顶部横幅提示新版本（当前/最新版本号 + 变更摘要），复制更新命令、查看 Release Notes、手动检查更新；版本号由镜像内 `git describe` 自描述，最新版由后端代理查 GitHub Releases（1h 惰性缓存 + ETag，离线静默不弹）
  - In-app version banner: current/latest + release summary, copy-paste update command, release-notes link, manual check; version self-described by in-image `git describe`, latest proxied from GitHub Releases (1h lazy cache + ETag, silent offline)
- 页内一键自更新（可选）：`docker-compose.yml` 取消注释挂载模板（docker.sock + 仓库目录 + `IP_RADAR_UPDATE_TOKEN`）后，横幅出现「立即更新」——确认框 → 全屏更新态 → 容器内 `git pull --ff-only` + 定向重建（compose 项目名经 docker.sock 自发现）；四条件齐备才解锁，未配 token 恒 403
  - One-click self-update (opt-in): uncomment the mounts in `docker-compose.yml` (docker.sock + repo dir + token) to light up the Update-now button — confirm dialog → full-screen overlay → in-container `git pull --ff-only` + targeted rebuild (compose project self-discovered via docker.sock); gated on four conditions, always 403 without a token
- 跨容器更新状态机：发起更新落盘 `from_version`，新容器启动对账（版本已变→上次成功；未变→中断；超 15 分钟→超时），失败原因落盘可在页面查看
  - Cross-container update state machine: `from_version` persisted on start, reconciled on next boot (version changed → success; unchanged → interrupted; >15 min → timed out), failure reason persisted and surfaced in the UI

### 修复 Fixed

- CI flake：`test_stream_pool` 在逐文件跑序中被 `test_scheduler` 触发的冷启动后台线程污染 `backend/data`（部分源文件落盘使 `_is_cold_start` 误判非冷启，LMDB 未建完 → 503 warming）。加 `tiny_db` 隔离（`test_main_routes` 同款）
  - CI flake: `test_stream_pool` got 503s in per-file CI order after `test_scheduler`'s cold-start thread polluted `backend/data`; isolated with the same `tiny_db` fixture `test_main_routes` uses

## v1.1.0 — 2026-08-21

### 新增 Added

- Fail2ban 集成：`scripts/fail2ban/ipradar.conf` —— ban 前先查本地裁决，确认恶意（conf ≥ 70 可调）记入长封名单，CDN/基础设施边缘跳过 ban 免误封
  - Fail2ban integration (`scripts/fail2ban/ipradar.conf`): pre-ban triage consults the local verdict — confirmed-malicious IPs (confidence ≥ 70, tunable) go to a long-ban list, CDN/infra edges are skipped to avoid false bans
- Graylog 集成：`integrations/graylog/` —— 可导入 content pack（Lookup Table + Pipeline）及 HTTP JSONPath 配置指南，日志富化一步到位
  - Graylog integration (`integrations/graylog/`): importable content pack (lookup tables + pipeline) with an HTTP JSONPath setup guide — one-stop log enrichment
- Wazuh 集成：`integrations/wazuh/custom-ipradar` —— 带 IP 告警自动富化为 ECS threat.indicator 跟进告警，本地替代 VirusTotal 集成
  - Wazuh integration (`integrations/wazuh/custom-ipradar`): enriches IP-bearing alerts into ECS threat.indicator follow-on alerts — a local drop-in replacement for the VirusTotal integration
- `/api/lookup` 新增顶层 `threat` 汇总字段（verdict/confidence/types/is_cdn），下游集成一句话拿裁决
  - Top-level `threat` summary field (verdict/confidence/types/is_cdn) in `/api/lookup` responses — integrations get the verdict in one field
- 新增 DShield top-attacker 源：免密钥源 24→25，总源数 28→29
  - New DShield top-attacker source: keyless sources 24→25, total 28→29
- `last_seen` 全管线接通：源采集 → 存储 → 查询 API → 详情面板
  - `last_seen` wired end-to-end: harvest → storage → lookup API → detail panel
- `as_domain` 资产域名槽位，机构行后缀展示
  - `as_domain` asset slot, displayed as a suffix on the org row
- CSV 导出新增 first_seen / last_seen / as_domain 三列
  - CSV export gains first_seen / last_seen / as_domain columns
- 详情面板 extra 值可点击：tweet_url、sbl_id 及裸 URL 自动 linkify
  - Extra values in the detail panel are linkified: tweet_url, sbl_id, and bare URLs become clickable links
- 重建进度升级：加载阶段也有进度信号，终态冻结不再回跳，状态条分段渲染百分比/行数
  - Rebuild progress overhaul: loading phase now emits progress, final-state fractions freeze instead of snapping back, and the status bar renders per-phase percentages and row counts

### 变更 Changed

- 后台自动刷新改为每源固定错峰时刻：日更源每天 2 次、周更源每周期 1 次（此前 30 分钟扫描、过期即拉，全源同刻聚集；AbuseIPDB 等配额源被动挨挤）；调度器状态新增每源 `next_refresh_at`
  - Background refresh moved to fixed per-source staggered slots: daily sources twice a day, weekly sources once per staleness window (previously a 30-minute scan pulled every stale source at the same moment, crowding quota'd feeds like AbuseIPDB); scheduler status now exposes per-source `next_refresh_at`
- stopforumspam 换用 listed_ip_365_all 数据：带走 total（出现次数）与 last_seen
  - StopForumSpam switches to the listed_ip_365_all feed, carrying total (hit count) and last_seen
- proxyscrape 改发 carrier 字段，僵尸 isp 槽位删除
  - ProxyScrape now emits carrier; the zombie isp slot is removed
- 死代码清除：ApiSource 基类、在线富化（enricher）链、enrichError/phase 死契约
  - Dead code removed: the ApiSource base class, the online-enricher chain, and the unused enrichError/phase contract

### 修复 Fixed

- 批量更新收敛竞态：终态 done 事件不再出现 done<total；源中途启用 (re-enable) 或调度器刷新与手动全量更新重叠时，total 动态校正，批次不再可能永久停在 running（需重启才能再全量更新）
  - Batch-update convergence race: terminal done events no longer report done<total; when a source is re-enabled mid-batch or a scheduler refresh overlaps a manual full update, total is dynamically corrected — a batch can no longer get stuck in running forever (which previously required a restart)
- cn_isp 不再把运营商名写进 as_name；ISP 徽标仅中国 IP 显示
  - cn_isp no longer pollutes as_name with carrier names; the ISP badge is shown for CN IPs only
- STIX 导出：Location/AS 对象 id 规范为 `<type>--<UUID>`；残余 http 源 URL 全部改 https
  - STIX export: Location/AS object ids normalized to `<type>--<UUID>`; remaining http feed URLs switched to https
- DShield 解析容错：tab 分隔、`-` 占位归一为 null
  - DShield parsing hardening: tab-split tolerance; `-` placeholders normalized to null
- 进度显示一串修复：resync 后假 0%、rebuild 后取消边界、行数 K/M 晋升格式、loading 计数清零回归、cancelled 灰条
  - A run of progress-display fixes: false 0% after resync, cancel boundary after rebuild, K/M row-count formatting, loading-counter zeroing regression, and the cancelled grey bar

### 内部 Internal

- README：404StarLink banner、新截图、审计修正（链接/警告/venv 引导/刷新口径英文镜像）；agent skills 文档接地重写 + 漂移守卫测试；迁移到 pi 作为主 harness；测试加固（monotonic deadline、退避守卫去空洞化）
  - README: 404StarLink banner, new screenshots, audit fixes (links/warnings/venv bootstrap/EN mirror of refresh cadence); agent-skills docs rewritten as grounded pointers plus drift-guard tests; migrated to pi as the primary harness; test hardening (monotonic deadlines, de-vacuous backoff guard)

## v1.0.0 — 2026-08-18

开源首版。自托管威胁情报融合引擎：FastAPI + React 19 + LMDB，单容器部署，全栈本地运行，查询不出网。

### 核心

- **28 源威胁情报融合** —— 24 个免密钥源开箱即用（GeoLite2 / iptoasn / 主要封禁列表），4 个 🔑 源（ipinfo_lite / abuseipdb / otx / ip2proxy）可选开启
- **一份裁决，不是一堆列表** —— 源可靠性加权、交叉佐证、时间衰减的 0-100 置信度；单 IP 一句话结论，逐源证据可展开
- **地理 · 城市 · ASN · CN ISP 归属**（含港澳台）；开放代理 / VPN / Tor / CDN 一眼认出
- **流式批量查询** —— 文本 / 文件 / CIDR 输入，NDJSON 进度流，单批上限 50 万 IP，流式去重；STIX 2.1 导出
- **冷启动感知** —— 容器秒级可访问，页面横幅实时盯构建进度；积分查询门保证构建期绝不以半份数据出结论，超时强制放行防楔死
- **资源自觉** —— 重建内存阀门按宿主机 RAM 自动收敛并发；LMDB + mmap 存储，查询路径内存 MB 级；默认每 30 分钟后台自动刷新
- **Docker 一键部署** —— `docker compose up -d --build` 即全栈

### 修复

- ip2proxy：PX2 LITE CSV 本无表头，harvest 不再误把首行数据当表头丢弃（此前每次重建恰丢一行代理记录）

### 历程（v1.0.0 之前）

- 2026-06-08 项目起步：TSV 加载器 + FastAPI 查询路由 + React 脚手架
- 2026-06-16 内存索引迁移 MMDB：常驻内存从 GB 级降至 MB 级
- 2026-08-04 更新管线加固：崩溃恢复 / 快照膨胀 / OOM 防护
- 2026-08-11 CIDR 懒展开；结果表 5 万行分页
- 2026-08-12 重建内存阀门：load/rebuild 分离，重建并发按可用内存自动调节
- 2026-08-14 LMDB 存储试点（ipinfo_lite），铺平全源迁移
- 2026-08-17 开源发布：仓库净化，公开为 ip-radar
- 2026-08-18 流式进度协议 v2 + LRU 流式去重；冷启动感知（即时可用 / 横幅 / 积分门）
