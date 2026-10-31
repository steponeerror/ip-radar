# #241 tweetfeed 重建期 unmapped hashtag WARN 聚合 —— 实现报告

- 分支:`ticket/tweetfeed-warn-aggregate`(基线 `a37caf29`)
- 改动:仅 2 个文件(`backend/ipdb/_sources/tweetfeed.py` + `backend/tests/sources/test_tweetfeed.py`),`_classification.py` 与数据解析/分类逻辑零改动
- 日期:2026-10-31

## 一句话结论

tweetfeed 解析时的 unknown hashtag(映射不上的话题标签)不再每个标签打一条 WARNING,改成一遍解析结束只打一条汇总 WARNING(总次数 + 出现最多的前 10 个标签及各自次数),另在每个标签第一次出现时打一条 DEBUG 留痕。分类结果和入库数据逐字节不变。

## 真实根因(与票面描述的差异)

票面说「逐行刷屏」。实际查证(2026-10-31):

- WARN 的真实位置不在 tweetfeed 解析文件里,而在 `backend/ipdb/_classification.py:275` 的 `normalize()` 绊线——2026-09-05 加的「未命中映射的原生值按 (映射表, 键) 进程级去重、每键只警一次」的告警。tweetfeed 解析每个 hashtag 逐个调它,所以每个**不同的** unknown hashtag 一条,不是每行一条。
- 票面日志措辞 `unmapped hashtag #xxx` 是转述;真实日志行是 `WARNING:ipdb._classification:unmapped native value '#valleyrat' -> 'other' (upstream may have added/renamed a category)`(已在服务器容器日志核实)。
- 重建走一次性子进程(`ipdb._rebuild_child`),子进程里去重集合是空的,所以**每次重建**都会把这批标签重新全打一遍。用本机留存的 tweetfeed 全量语料(9.8 万行,其中 ip 行 7831)实测:一次重建 54 条 WARN。
- 「重建窗口单核打满」的主因是大源重建本身(内存/写库),54→1 条日志对 CPU 负载的净影响很小;本票消的是日志噪音和日志 IO 这层浪费(哲学 9「先消浪费」的第一刀),不是重建性能的根治——重建性能归 #239 消融那条线。

## 修法(票面候选 1)

`tweetfeed.py`:

1. `_classify_tag()` 的映射判定改为本地三行复制(strip().lower() → 查 `TWEETFEED_MAP` → 词表成员校验),分类结果与原 `normalize()` 路径**位等价**(有专门测试钉住);不再调 `normalize()`,即不再触发它的逐键 WARN。
2. 未命中映射的标签往调用方传入的 `Counter` 累加计数;同一标签跨行自动合并。
3. `harvest()` 一遍解析正常跑完后,若计数非空,发**一条**摘要 WARN:总命中数 + 不同标签数 + Top-10 标签及各自计数;每个标签首现时另发一条 DEBUG(生产容器日志级别是 INFO,DEBUG 不落日志,但开 DEBUG 即可看到全量首现痕迹——信息不灭失,哲学 1)。
4. 计数口径:只计分类器实际扫过的「首个可映射标签之前」的未映射标签,与旧绊线的触发集合完全一致(首个可映射标签之后的标签本来就不被检查)。

`_classification.py` 一行未动:urlhaus、otx 等其它源继续用原绊线,行为不变。

真实语料上的新摘要行长这样(生产 INFO 级别下):

```
WARNING:ipdb._sources.tweetfeed:tweetfeed: 1454 unmapped-hashtag hit(s), 54 distinct tag(s) -> 'other' (top 10: #rat=275, #xworm=194, #apt=181, #kimsuky=161, #dprk=103, #opendir=89, #clickfix=61, #stealer=54, #netsupport=44, #ransomware=27) — upstream may have added/renamed tags; full first-seen trail at DEBUG
```

## 验收逐条

### ① 合成语料新测试钉住聚合行为

新增 4 个测试(`backend/tests/sources/test_tweetfeed.py`):

- `test_tweetfeed_unknown_hashtags_aggregate_into_one_summary`:4 行语料(#valleyrat ×3 行、#winos、#phishing、`#c2 #valleyrat`)——断言:没有任何一条 `unmapped native value` WARN;tweetfeed 模块恰好 **1 条**摘要 WARN;总命中 **3**(valleyrat 2 + winos 1;`#c2 #valleyrat` 行里 valleyrat 在首个可映射标签之后、不计入);同 tag 跨行合并(`#valleyrat=2`、`#winos=1`);首现 DEBUG 恰 2 条;分类结果不变(unknown 行落 other、`#c2` 前缀行落 c2-server)。
- `test_tweetfeed_unknown_summary_topn_cap_and_ordering`:12 个不同标签、次数 12..1(共 78 次命中)——断言:总数 78、distinct 12、只列 top 10(`#t00=12`…`#t09=3` 在,`#t10=`/`#t11=` 不在)、按次数降序。
- `test_tweetfeed_no_unknown_tags_means_no_summary`:全可映射语料——一条 WARN 都不发(零噪音)。
- `test_tweetfeed_classify_tag_parity_with_normalize`:分类位等价——测试内逐字镜像改前的「逐 token 调 normalize」旧循环作参照,对 TWEETFEED_MAP 全键 + 空值/纯空白/None/大小写/前缀可映射截断等输入,新实现与旧实现逐一相等。

命令与结果:

```
$ cd .worktrees/tkt-tweet/backend && /home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python -m pytest tests/sources/test_tweetfeed.py -q
8 passed, 1 warning in 0.63s      (旧 4 个全保留全绿,新 4 个)
```

### ② 落库数据面不变

方法:在基线 `a37caf29` 挂临时 worktree,同一 venv、同一真实语料(`/home/huxiao/dev/pi-ip-lookup-tool/.eval-prod-data/tweetfeed.csv`,98050 行 / ip 行 7831),两边跑同样的脚本做字节级对比。

解析产物逐字节等价(每行 `json.dumps([ip, asdict(Evidence)])`):

```
改前:7831 rows -> /tmp/harvest_old.jsonl
改后:7831 rows -> /tmp/harvest_new.jsonl
$ cmp /tmp/harvest_old.jsonl /tmp/harvest_new.jsonl
HARVEST BYTE-IDENTICAL
```

落库+查询面逐字节等价(独立 tmp 数据目录全量 rebuild,再对全部 distinct IP 逐个 `query()` 落 JSON 对比):

```
改前:rebuild=6956, queried=6957 ips
改后:rebuild=6956, queried=6957 ips
$ cmp /tmp/rebuildq_old.jsonl /tmp/rebuildq_new.jsonl
REBUILD+QUERY BYTE-IDENTICAL
```

(6957 个 distinct IP、6956 个库键,两侧一致;键数差 1 是基线既有现象,与本票无关。)

另:`git diff --stat` 恰 2 个文件、全部在解析日志层,数据路径零触碰:

```
 backend/ipdb/_sources/tweetfeed.py      |  46 +++++++++++---
 backend/tests/sources/test_tweetfeed.py | 107 ++++++++++++++++++++++++-
 2 files changed, 144 insertions(+), 9 deletions(-)
```

### ③ tests/sources + tests/core 全绿

```
$ cd .worktrees/tkt-tweet/backend && /home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python -m pytest tests/sources tests/core -q
1146 passed, 8 skipped, 4 warnings in 69.43s
```

### ④ 同语料改前 vs 改后的 WARN 行数

同一份全量语料(7831 ip 行),数日志记录:

| | 改前(基线 a37caf29) | 改后 |
|---|---|---|
| `ipdb._classification` WARN | **54 条**(每个不同 unknown hashtag 一条) | **0 条** |
| `ipdb._sources.tweetfeed` WARN | 0 条 | **1 条**(聚合摘要) |
| `ipdb._sources.tweetfeed` DEBUG | — | 54 条(生产 INFO 级别下不可见) |
| **WARN 总行数** | **54** | **1** |

改前实测命令(基线 worktree,同一 venv):捕获 `ipdb._classification` 的 WARNING 记录数 = 54;改后同法 = 上表。

## 意外发现

1. **urlhaus 是同病更重的患者**:现役生产容器(docker logs,容器 2026-10-31 起)里 `unmapped native value` 共 **296 条,全部来自 `rebuild child urlhaus`**(urlhaus 的 tags 列把 `32-bit/elf/mips` 这类文件噪声也喂给了绊线)。tweetfeed 修好后它成了最大残留噪音源,建议开后续票同法聚合(urlhaus 车道在 `_sources/urlhaus.py`,同样是逐 token 调 `normalize`)。
2. **票面「逐行」与实际「逐 unique tag」有差**:现行绊线 2026-09-05 起就有每键一次的去重,单次重建最多 54 条(本语料),不是数千条;票面印象里的「海量」更像长窗口内多源重建(含 urlhaus 296 条)叠加的观感。聚合法对此两种规模都成立。
3. 重建期打满单核的根因是大源重建本身(内存/写库),本票不解决也不恶化;性能结论应以重建前后计时为准,别把日志行数当负载因果(哲学 6)。
4. 服务器上 2026-10-29 事发容器的日志已随容器重建丢失,只能以现行容器 + 本地全量语料复原口径;两者现象同型(unmapped native value 逐键 WARN)。

## 纪律

- 改动 + 本报告均已 commit 到 `ticket/tweetfeed-warn-aggregate`,未 push(按票规)。
- 票面之外零改动:未动 `_classification.py`、未动数据解析/分类语义、未动 CHANGELOG(票面未要求;如需补一条「tweetfeed unknown hashtag 改聚合摘要」待用户示意)。
