# #253 + #254 交付报告(B 家族 url/filename 护栏 + urlhaus 未映射键告警聚合)

分支 `ticket/253-254-misc`(基于 `origin/master@dd89b20a`),单实现者,2026-10-31。
两票独立可审,#254 的方向选择按票面既定程序走了证据门槛,结论 **B(共享聚合器)成立**,未退 A。

---

## #253:B 家族源 url/filename 非空护栏

### 背景与普查(动手前证据)

源底座合并(#248/#250,ADR 0014)把 B 家族(IpListSource/CsvSource)原来的「裸注解」
(url/filename 不定义就在构造时直接报 AttributeError)换成了空字符串默认值——
新子类漏写 filename 从「启动就报错」变成「悄悄把数据目录本身当文件路径用」。

动手前先普查了全部 61 个真实源(一次性脚本扫类属性,用完即删,结果留档于此):

- **filename:61 个源全部非空,无一例外。** 空文件名没有任何合法形态(路径会落成
  data 目录本身),所以文件名校验无条件严格、不设豁免。
- **url 为空串/None 的共 14 个源**,全部自带定制 download()(多端点/分片/按 token 拼 URL),
  即全部是有意留空,没有一个依赖家族默认下载路径:
  - B 家族 2 个:firehol、blocklist_de(多列表逐个下载,真实 URL 在模块常量里);
  - A 家族 11 个 + 直挂底座的 ipinfo_lite 1 个(本票不管,见裁决)。

**裁决(开工前请示,已批)**:范围 = B1(只查 B 家族,票面口径;A 家族要护另开票);
豁免形态 = E1(显式类属性 `url_exempt = True`,与 infra_noise_filter/derived 同款惯例;
否掉「集中白名单」= 第二份真相源,也否掉「有定制 download 就自动豁免」= 结构猜谜,
将来有人为重试逻辑改写 download 却仍用 self.url 时会误豁免真 bug)。

### 实现(8 处中的 5 处属本票)

| 文件 | 改动 |
|---|---|
| `backend/ipdb/_sources/_base.py` | IpListSource 新增 `url_exempt: bool = False` 类属性(注释含普查结论与出处) |
| `backend/ipdb/_validate.py` | `metadata_problems()` 增 B 家族门控校验:filename 空即报;url 空(含纯空白)且未豁免即报。走 registry 发现期「启动即 raise」既有通道 |
| `backend/ipdb/_registry.py` | 发现期报错提示语补上 url/filename(原来只列 category/reliability/authoritative_for) |
| `backend/ipdb/_sources/firehol.py` | `url_exempt = True`(注释注明多端点设计) |
| `backend/ipdb/_sources/blocklist_de.py` | 同上 |
| `backend/tests/sources/test_b_family_url_filename_guard.py` | 新增 8 个测试(下节) |

既有测试桩(tests/core/test_validate.py 的 _Fake/_Good 是普通对象、根本没有 url/filename
属性且断言检查结果为空)零改动——校验按「是不是 B 家族实例」门控,普通对象不进这道闸。

### 验收逐条

1. **漏定义 filename 的合成坏子类被拒** ✅
   `test_missing_filename_rejected`:合成 IpListSource 子类只给 name/url/fields,
   `metadata_problems()` 报出 `filename is empty …`。配套:空 url 未豁免被拒、
   纯空白 url 被拒、CsvSource 子类(经继承)同样被门控、A 家族不查(钉住裁决范围)。
2. **malicious_ip 等有意空串源不受影响** ✅
   `test_real_exempted_sources_clean`:firehol/blocklist_de 豁免后检查零问题;
   `test_discovery_smoke_all_real_sources`:61 源真实发现冒烟,`_discover_sources()`
   返回恰 61 个、逐一 `metadata_problems() == []`(malicious_ip 是 A 家族,本就不进
   这道闸;B 家族的有意空串源=firehol/blocklist_de,靠豁免标记通过)。
3. **tests/sources + tests/core 绿** ✅ 见文末命令清单。

---

## #254:urlhaus 未映射键告警聚合(接 #241 模式,方向 B)

### 方向裁定:按票面程序走门槛,B 成立

票面给了两个方向:A=照抄 tweetfeed 的做法塞进 urlhaus 自己文件里;B=把聚合逻辑
下沉成 `_classification.py` 里的共享小件,tweetfeed 改调共享件 + urlhaus 接入。
任务书规则:B 若能让 #241 的 4 个新测试**一个断言都不改**仍绿、且两个源的字节
等价复验都过,则 B 优先(避免第三份同型拷贝)。

门槛结果(先实现 B 再验,证据见验收节):

- #241 的 4 个测试(`tests/sources/test_tweetfeed.py` 8 个全绿,零改动)✅
- tweetfeed 双面字节等价(harvest 逐行 JSON + 全量 rebuild 后逐 IP 查询 JSON,
  改前/改后 cmp 完全一致)✅
- urlhaus 双面字节等价 ✅

关键实现约束:tweetfeed 测试钉死了日志措辞(如 `3 unmapped-hashtag hit(s)`、
`2 distinct tag(s)`)和日志器名(`ipdb._sources.tweetfeed`),共享件用两个名词参数
(hits=被计的东西、item=去重后的键)+ 传入源自己的日志器,逐字复现这些字符串。

### 实现(3 处)

| 文件 | 改动 |
|---|---|
| `backend/ipdb/_classification.py` | 新增两个共享函数:`normalize_counted()`(与 normalize() 映射判定逐键同语义,但未命中键不告警、改计数进调用方的 Counter;首现键发一条 DEBUG 留痕)+ `unmapped_summary()`(解析整遍结束后发一条摘要 WARN:总命中数 + 去重键数 + Top-10 及各自计数;零未命中零噪音不发) |
| `backend/ipdb/_sources/tweetfeed.py` | `_classify_tag` 计数核改调 normalize_counted(签名不变);harvest 末的摘要改调 unmapped_summary;删除本地 Top-N 常量与手写摘要文案(由共享件持有) |
| `backend/ipdb/_sources/urlhaus.py` | `_classify(tags_raw, unknown)` 未映射 token(含 32-bit/elf 等文件噪声)改计数;threat 列无可映射值(如 malware_download)同样计数(与旧告警触发集一致);harvest 生成器被完整消费后发一条聚合摘要 |

两个不变式(代码注释均有出处):计数集 = 旧告警触发集(键非空、映射表里没有);
分类返回值逐键与旧实现完全一致(两个源各有镜像测试钉住)。生成器被中途弃置
= 本遍没跑完,不发摘要(#241 契约;现存代码里 harvest 的唯一消费方 rebuild
都是整遍消费)。

### 验收逐条(对齐 #241)

1. **WARN 行数骤降(真实语料实测)** ✅
   语料:生产快照 `.eval-prod-data/urlhaus.csv`(2026-10-29,91,246 行 →
   IP 行 4,126 → 去重 IP 1,285 = 落库键数)。

   | 通道 | 改前(每个重建窗口) | 改后 |
   |---|---|---|
   | `ipdb._classification` 逐键告警 | **325 条**(每个去重后的未映射键一条) | **0 条** |
   | `ipdb._sources.urlhaus` 摘要 | 0 条 | **1 条** |
   | **合计** | **325** | **1** |

   改后摘要原文(截断):`urlhaus: 11044 unmapped-tag hit(s), 325 distinct tag(s)
   -> 'other' (top 10: malware_download=4126, elf=1811, coinminer=1152, ua-wget=384,
   opendir=340, censys=315, 32-bit=210, sshdkit=199, backdoor=187, …)`——
   信息量反而变高:Top-10 直接点名谁是刷屏大户(malware_download 是设计内的
   threat 兜底值,每行都计,旧实现同样每键告警一次,观测面没丢)。
2. **分类结果与落库字节不变(双面)** ✅
   方法同 #241:同一脚本在改前(dd89b20a)与改后各跑一遍,产物 cmp:
   - urlhaus harvest 逐行 JSON(4,126 行):`cmp` **逐字节一致**;
   - urlhaus 独立目录全量 rebuild(1,285 键)后全部 1,285 个 IP 逐个 query()
     的 JSON:`cmp` **逐字节一致**;
   - tweetfeed 同法复验(7,831 行 / 6,956 键 / 6,957 查询):两面 `cmp`
     **逐字节一致**(B 动了刚合的 tweetfeed 代码,所以必须复验);
   - tweetfeed 告警行为不变:每整遍解析仍恰 1 条摘要(1,454 命中 / 54 去重键,
     与改前同数)、逐键告警仍为 0。
3. **未映射键聚合测试** ✅
   `tests/sources/test_urlhaus.py` 新增 4 个(镜像 #241 的 4 个):
   - `test_urlhaus_unknown_keys_aggregate_into_one_summary`:混合语料(tags 噪声
     token + threat 兜底值同计数器合并跨行计数)——零逐键告警、恰 1 条摘要、
     总命中 5/去重 4/malware_download=2、首现 DEBUG 恰 4 条、四行分类不变;
   - `test_urlhaus_unknown_summary_topn_cap_and_ordering`:12 个键计数 12..1
     (共 78 次命中)——只列 Top-10、按计数降序、截断键不出现;
   - `test_urlhaus_no_unknown_keys_means_no_summary`:全可映射(tags+threat
     双路)→ 一条告警都不发;
   - `test_urlhaus_classify_parity_with_normalize`:分类位等价镜像——测试内
     逐字复刻改前「逐 token 调 normalize()」的旧实现作参照,对 URLHAUS_MAP
     全键 + 空值/none/大小写/逗号空档等输入逐一相等。
4. **tests/sources + tests/core 绿** ✅ 见下。

---

## 命令与结果

```
$ cd .worktrees/tkt-253-254/backend && /home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python -m pytest tests/sources tests/core -q
1158 passed, 8 skipped, 4 warnings in 68.46s     (基线 1146 + 新 12:#253 八个 + #254 四个)

$ … -m pytest tests/sources/test_tweetfeed.py tests/sources/test_urlhaus.py -q
22 passed    (#241 的 8 个 tweetfeed 测试零改动全绿;urlhaus 旧 10 + 新 4)

$ … -m pytest tests/ -q --ignore=tests/core --ignore=tests/sources
1180 passed, 1 failed …    # 唯一失败 = test_ops_rounds_e2e::test_health_round_real_run
                            # (Node.js ops-agent 端到端,环境性;git stash 后在干净
                            #  dd89b20a 上同样失败,与本批无关,已验证)

位等价采集(改前/改后同脚本,产物在 /tmp/254/,cmp 结果如上):
$ cd <backend> && …python /tmp/254/eq_harness.py urlhaus  old|new
$ cd <backend> && …python /tmp/254/eq_harness.py tweetfeed old|new
$ cmp /tmp/254/{urlhaus,tweetfeed}__{old,new}__{harvest,query}.jsonl   # 四组全部一致
```

`git diff --stat`(实现面,不含报告):

```
 backend/ipdb/_classification.py       | 54 ++++++++ (共享聚合器两函数)
 backend/ipdb/_registry.py             |  3 +-  (报错提示语)
 backend/ipdb/_sources/_base.py        |  8 ++   (url_exempt 类属性)
 backend/ipdb/_sources/blocklist_de.py |  1 +
 backend/ipdb/_sources/firehol.py      |  1 +
 backend/ipdb/_sources/tweetfeed.py    | 48 ++++--- (改调共享件,净 -10 行)
 backend/ipdb/_sources/urlhaus.py      | 34 +++-  (接聚合)
 backend/ipdb/_validate.py             | 21 +++  (B 家族门控校验)
 backend/tests/sources/test_urlhaus.py | +4 测试
 backend/tests/sources/test_b_family_url_filename_guard.py | 新 8 测试
```

## 意外发现

1. **生产 296 vs 本地 325**:票面生产容器实测 296 条逐键告警,本地 10-29 快照语料
   为 325 条——不同日子语料、不同键集,数量级一致,方向相同(都压到 1 条)。
2. **urlhaus 的告警大户是设计内兜底值**:malware_download(threat 列的兜底取值,
   每行出现)单个键就贡献 4,126 次命中,占总量约 37%;聚合摘要让这个事实第一次
   直接可读。如果将来觉得它没有观测价值,可考虑把它显式映射(票面外,未动)。
3. **#253 普查副产物**:A 家族 14 个空 url 源全部自带定制 download(坏形态会在
   下载期响,不是静默),佐证裁决 B1(A 家族不查)的代价可控;普查清单已留档本报告。
4. tweetfeed 侧 B 化后净 -10 行,且其 8 个测试零改动全绿——共享件没有偷换 #241
   的任何对外行为。
