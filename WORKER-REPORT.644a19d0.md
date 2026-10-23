# WORKER 报告 — 票 #164(P2-P2:VERIFY+抑制规则库+B 三件装配层)

分支 feature/ops-p2-p2(基 e0195584,集成分支 tip 未移动,merge no-op);4 commits:f9fe6e9e(VERIFY 真实现)/6740226f(B 三件)/ec2addd6(GLOSSARY 三词)+ 半程 WIP e4667679;另嵌套 docs 仓 1 commit 9296415(规则库首版+_INDEX 首版+8 条 10-23 生产留痕判例同步,服务器逐字节拷贝)。

## 交付(对照任务书)

1. **VERIFY 真实现**:幸存/抑制分区留痕(02-verify-survivors/suppressed.json);在飞不重问真读 ops 树 `items/*.md`(frontmatter status/dedup_key,active|snoozed=在飞,done 不算;源级同因对齐 `_ops_items.dedup_key.source`,溯源到条目 id);G_VERIFY 门同源重算。配套:lib.sh `extract_feed_urls -t` 标源对模式(flags.source=清单 # 首词,ciarm 形)+`_ff_probe` UNREACHABLE 行第 4 列 error_family(http_404/http_429/net_fail);known_noise_digest(机器格式,C稿 §3.5 TRIAGE 只吃 digest)入幸存工件。
2. **rules/suppressions.json 闭集 schema**:normalizeRules 纯函数校验(谓词闭集 bucket/url_shape/source/error_family,动作闭集 suppress|annotate,review_at 缺省=采纳+90 天,坏文件=infra 终态);首批规则全文见下(真实出处=判例 2026-10-23-ruling-bbe1ad6f0c/0db230187f,裁决包 2026-10-23-health-1209)。
3. **B 三件**:①`ops/agent/build-index.mjs` _INDEX 召回地板生成器(概念判例一行一件:文件名+概念词+一行主张+关键词+状态;留痕/`_*` 排除;头注可再生+rebuild 命令;`--check` 锚闭包)②`anchors-health.json` 六锚域词表+`pipeline/anchors.mjs` 纯函数选锚(域词×旗标,空旗标零注入,HIT_CAP 8)③`ops/agent/promote-detect.mjs` 升格检测器(同因=文本归一全等∨源身份词相交并集 union;superseded 链不计数防谱系回声;≥2 且 ruling_agreement 一致→`retro/promotion-candidates/` 候选件,三门槛 可机检/可证伪/非环境特异性 pending 起步;幂等 append-only;仅立项,永不写判例区)。真语料 dry run:`CANDIDATE [agreed] 同源:urlhaus ← ruling-1de2dbae81, ruling-889a2778b0;留痕 8(live 7)→ 候选 1`(threatfox 对裁决不一致正确不立项)。
4. **顺手件(#163 review P2-1)**:matrix 裸失败负例——stub 裸败→01-probe-matrix.json=信封件({ok:false,code:"matrix_failed"}),summary.matrix.ok=false,九门全过轮仍 ok=true。

## 四门(commit 6740226f 后跑,全绿)

`node ops/agent/selftest-pipeline.mjs` → **PASS=19 FAIL=0**(12→19,新增:R12/R7 判例转写命中+反面全 URL 形/闭集负例×6/在飞真读全链(CLI 轮)/matrix 裸失败/B 三件×3);`node ops/agent/selftest-contract.mjs` → **PASS=15 FAIL=0**;`bash ops/agent/selftest.sh` → **PASS=100 FAIL=0**;`node ops/agent/golden/run-golden.mjs` → **PASS=9 FAIL=0**。

## 规则库首版全文(docs 仓 docs/ops/rules/suppressions.json,schema 校验过)

```json
{ "version": 1, "rules": [
  { "id": "R12", "adopted": "2026-10-23",
    "adopted_via": "判例 2026-10-23-ruling-bbe1ad6f0c.md(裁决包 2026-10-23-health-1209.md;人裁修正「不可达我是怎么更新的」:GeoLite 库实为日更,不可达是截断 URL 撞 GitHub 重定向 HEAD-404 的探测伪迹;反面形状见 ops/agent/feeds.txt 头注)",
    "match": { "bucket": "unreachable", "url_shape": "https://github.com/*/releases/latest/download/", "error_family": "http_404" },
    "action": "suppress",
    "note": "GitHub releases/latest/download 截断重定向形:HEAD 恒 404 而 GET 实活(GeoLite 假红,2026-10-23 判例;只压截断形,带文件名全 URL 的 404=真信号仍幸存)",
    "review_at": "2027-01-21" },
  { "id": "R7", "adopted": "2026-10-23",
    "adopted_via": "判例 2026-10-23-ruling-0db230187f.md(裁决包 2026-10-23-health-1209.md;同包 13 不可达多为 raw.githubusercontent 限流/截断假面,S6404 观测后被证为探针工件;lib.sh 降噪刀三对该域 429 已先重试一轮)",
    "match": { "bucket": "unreachable", "error_family": "http_429" },
    "action": "annotate", "note": "限流不可达:降 severity 不抑制(429 是探针礼貌问题非源死亡;annotated_rule 随幸存信号交 TRIAGE)",
    "review_at": "2027-01-21" } ] }
```

## _INDEX 首版节选(docs/ops/precedents/_INDEX.md,12 概念行+8 留痕汇总;可再生)

```
<!-- 派生物可再生:判例文件是唯一真源,本文件由 scripts 重生成,勿手改(「索引是地图不是存储」,ADR 0007)。
     rebuild: node ops/agent/build-index.mjs [--docs-root DIR](B 稿 §2.2①:spawn 前再生;同库状态字节一致) -->
| 文件名 | 概念词 | 一行主张 | 关键词 | 状态 |
| 2026-10-19-threatview-sunset-dead-feed.md | 源候选判死 | 源候选判死 — sunset 硬门(URL Last-Modified 冻结) | sunset url last-modified threatview.io discover | active |
| 2026-10-19-firehol-webserver-unsubscribe.md | 矩阵违例执法 | 矩阵违例执法 — 案一维持非法,最小执法仅退订 firehol_webserver | firehol webserver infra ruling-confirmed | active |
superseded: 0 条(沿革见各文件 superseded_by)  |  档案留痕 8 条不进索引(rg 全文可检)
```

## 偏离与残留

1. 旗标 error_family 值域=精确码族 http_<code>/net_fail(lib.sh 实现),规则谓词值是数据;与 `_ops_detectors` 条目侧 error_signature 族(http_4xx 折叠)不同拼写——P4 ITEMIZE 接 create_item 时做全签映射(注释已钉)。
2. 在飞「同因」=源级(source 名)判定;probe_class/error_signature 全签对齐留 P4(#166)。
3. 锚表首版可指留痕判例(10-23 两假异常今日只有留痕面);升格采纳后自然换概念判例。
4. docs 仓 8 条留痕判例=生产服务器逐字节同步(md5 抽核),为 _INDEX/锚闭包/升格检测真语料;生产 ops 树的 rules/_INDEX/候选件由运维侧再生(P5 部署面)。
5. 影子轮 N≥3(spec #161 P2 验收)=合并后生产侧动作,不在本 worker 面。
