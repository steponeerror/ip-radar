# #248 两基类抽共享底座(SourceBase)实现报告

- 日期:2026-10-31 | 分支:`ticket/source-base-unify`(基于 master@a3a1e8f9)| 票:#248
- 一句话结论:**已按票面七条裁决落地「形态 A:抽共享底座、钩子分家」,61 个源类行为零变化**——bench 逐字节相同、回放闸门 C2 同语料同计数零失配、全量测试除基线同红的 1 个环境失败外全绿、61 源发现冒烟全实例化、两个 LMDB 读侧委托测试与 patch `_http_get` 的测试文件全绿。

## 一、改了什么(结构)

新建共享底座类 `SourceBase`(「源底座」,GLOSSARY 已录词条),放在 `backend/ipdb/_sources/_base.py` 顶部,收进两个基类逐字重复的部分:

| 成员 | 说明 |
|---|---|
| `__init__` | 15 个状态槽 + v6 双族六属性 + `last_partial_failure`(原两基类各一份,逐行等价,合并取带类型注解版) |
| `load` / `_load_v6_side` | 纯 mmap 载入;v6 侧统一委托 `_lmdb.load_v6_side_state`(#243 的单源点 helper,原 `Source` 侧还留着 #243 之前的逐字拷贝,本票消除) |
| `query` / `_query6` | 带旧 env 撞死重试的双族查询 |
| `health` | 文件 mtime 判陈旧 |
| `_http_get`(staticmethod) | 重试 + UA 头 + 重定向绊线;保持 staticmethod,patch 锚 `Source._http_get` 对 A 家族经继承仍命中 |
| `download_host`(property) | 从 URL 取主机名 |
| 类属性 | name/fields/url/filename/stale_days/reliability/category/authoritative_for/provenance_tier/honeypot_methodology/infra_noise_filter + `lmdb_backed=True`(按裁决 5 上收;消费方 `_registry.py:426` 本来就是 getattr 鸭子型取默认 True,上收后同值) |

两基类挂底座,各自只剩取数钩子:

- `Source(_source_base.py,328→153 行)`:A 家族钩子 `download/harvest/normalize` + harvest 驱动的 rebuild;`single_evidence` 按裁决 5 留在 Source 不上底座(只有它的 rebuild 消费)。
- `IpListSource(_sources/_base.py)`:B 家族钩子 `parse_raw/get_insert_data` + B 契约 download(暂存→解析→规范化明单,失败保留旧文件)+ 明单行驱动 rebuild;`CsvSource` 不动。
- download 落盘契约分叉按裁决 2 **原样保留**,底座 docstring 里有对表说明。
- `ipinfo_lite.py(304→222 行)`按裁决 3 挂底座:删掉手抄的 `__init__` 全套状态槽、`load`、`_load_v6_side`、`health`;自有的 `_url` property(token 门控)、`download`(gzip 解压流式落地)、`rebuild`、带 `_shape` 整形的 `query/_query6`、硬编码 `download_host="ipinfo.io"` 全部保留。路径经核对与原手抄逐值相同(`_path/_lmdb_base/v6 族`由 `filename="ipinfo_lite.csv"` 派生)。

子类侧改动(全在裁决 4 授权范围内):

- `spamhaus.py`、`x4bnet_vpn.py`:download 里 2 处 `Source._http_get(...)` 类名直呼改 `self._http_get(...)`,随删仅为它存在的 `from .._source_base import Source` 导入。
- **13 处手抄 `download_host` 中删了 10 处**(cloud_ranges/cn_isp/dataplane/iptoasn/otx/otx_subscribed/rir_abuse/rir_delegated/dshield/stopforumspam),**保留 3 处**(ip2proxy/malicious_ip/peeringdb)——见下节;B 侧 blocklist_de/firehol 的多端点覆写本就非重复,未动。
- GLOSSARY.md 录「源底座」词条(裁决 7)。

净变化:17 件 +222/−460(含测试与 GLOSSARY)。

## 二、3 处 download_host 为什么没删(票面细节裁决记录)

探查报告把 A 侧 13 个手抄 `download_host` 记为「同款」,实际逐个核对后分两类:

- **10 处与底座实现等价**(返回值在一切输入下相同):dshield/stopforumspam(`urlparse(self.url).hostname`,底座多一层 `or None` 和空 url 判空,结果恒同)、iptoasn/otx/otx_subscribed(`url` 类属性就是那个常量 URL,hostname 相同)、dataplane(url 即 `https://dataplane.org/`)、cloud_ranges/cn_isp/rir_abuse/rir_delegated(url 为 None/缺失,覆写返回 None,底座对空 url 也返回 None)。删后用实例逐个断言 `download_host` 返回值与删前相同(见验收④命令输出)。
- **3 处是真覆写,删了会改变行为**:
  - `ip2proxy`:类无 `url` 属性(token 走 `_url` property),返回硬编码 `"www.ip2location.com"`;底座会返回 None。
  - `malicious_ip`:`url = ""`,返回 `urlparse(_BASE_URL).hostname` = `raw.githubusercontent.com`;底座返回 None。
  - `peeringdb`:`url = None`,返回 `urlparse(_API).hostname` = `www.peeringdb.com`;底座返回 None。

  按「纯删重复、零行为变更」原则保留这 3 处覆写。(cn_isp 删除覆写后补了一行 `url = ""` 注释保留「无单一权威 URL」的决策记录。)

## 三、票面前提的一处偏差(测试 patch 锚)

票面裁决 4 说「patch 锚 `Source._http_get` 经继承仍可命中,7 个测试文件不需改」。实测:对 A 家族子类成立(MRO 含 Source,patch Source 即拦到);但 **`tests/sources/test_sibling_files.py`(spamhaus/x4bnet 的 9 个测试)不成立**——这两个类属 B 家族,MRO 是 `子类 → IpListSource → SourceBase`,不含 Source;旧代码里它们直呼 `Source._http_get` 是类名静态引用,patch 恰好能拦,改成 `self._http_get` 后就拦不到了(改后测试真的去连了外网)。修法:该测试文件的 patch 锚从 `Source` 改挂各自具体类(`patch.object(SpamhausSource/X4BNetVPNSource, "_http_get")`),语义不变(拦本源全部 HTTP 调用),9 个测试全绿且恢复零外网。生产代码保持裁决 4 的 `self._http_get` 不变。其余 6 个 patch `Source._http_get` 的测试文件 + `tests/source_infra/test_source_base.py` 均未改、全绿。

## 四、验收五条逐条证据

1. **bench 位等价** ✅
   - 命令(基线与改后同款):`IP_RADAR_DATA_DIR=/home/huxiao/dev/pi-ip-lookup-tool/backend/data PYTHONHASHSEED=0 backend/.venv/bin/python backend/scripts/bench_lookup.py --snapshot/--compare`,数据面 = 主仓生产 `backend/data`(61 源 LMDB,零拷贝指向),参照 #243 判例。
   - 改后 `--compare /tmp/issue248/bench-baseline.json` 输出 **`bit-identical: zero diff`(exit 0)**;再 `--snapshot /tmp/issue248/bench-after.json` 后 **`cmp` 逐字节相同**(152,302 字节两份)。
   - 工件:`/tmp/issue248/bench-baseline.json`、`/tmp/issue248/bench-after.json`。
2. **回放闸门 C2 同语料逐位一致** ✅
   - 命令(基线与改后同款,仓根跑):`backend/.venv/bin/python scripts/fusion_replay_gate.py --data /home/huxiao/dev/pi-ip-lookup-tool/.eval-prod-data --stride 10 --limit 1000000 --report <路径>`;语料镜像 = 主仓 `.eval-prod-data`(生产 LMDB 快照,只读,起点并集 1,000,001 与 #244 报告同指纹)。
   - 改前/改后 C2 判据段逐字节相同(`cmp` 通过):**严格口径 92,694 IP 失配 0;宽口径 93,307 IP 失配 0;镜像 vs 生产 threat_summary 交叉核对失配 0**。
   - C3/C4 基线即红(benign 误报占比与区分度两个判据,与本票无关的既有状态,改后同为 FAIL 判决不变)。报告里 C3/C4 附属统计在 1e-6 量级有抖动:已用「同一份代码连跑两遍也抖」证伪为本进程集合迭代顺序导致的浮点求和次序噪声(rho 0.528905/0.528906 两跑互跳),非本票改动引入;C2 段四跑(基线×1、改后×2、同码复跑×1)计数稳定。
   - 工件:`/tmp/issue248/replay-baseline.md`、`replay-after.md`、`replay-after2.md`(同码复跑对照)。
3. **全量测试** ✅(1 个基线同红既有失败除外)
   - 命令:`cd backend && backend/.venv/bin/python -m pytest tests -q`。
   - 改后:**1 failed, 2319 passed, 9 skipped**(2 分 39 秒)。唯一失败 `tests/test_ops_rounds_e2e.py::test_health_round_real_run` = ops 健康轮 e2e 拉起 Node 子进程失败,与本票零代码接触面,#243 报告已判定为既有环境问题(基线 commit 同红同断言)。
   - 基线(改动前同命令):1 failed, 2309 passed, 19 skipped。两轮收集总数一致(2320),差 10 个 skip↔pass:改后余下 9 个 skip 全是确定性环境条件(worktree 无 frontend/dist、RUN_SLOW/RUN_MEMORY_SMOKE 未设、docs 嵌套仓缺 precedent store 等,`-rs` 输出核对);基线多出的 10 个 skip 属当时运行窗口的环境波动(基线全量跑与 bench/回放两作业时间重叠),本票零测试增删,不构成回归面。CI 侧另有 `scripts/ci_bitidentity_smoke.sh` 合成库烟测把关(注意 #243 已声明其口径不含 firehol/blocklist_de,两类等价靠本报告①③证据)。
4. **61 源注册发现冒烟** ✅
   - 一次性脚本(经真实发现入口 `ipdb._registry._discover_sources`,即 `_registry.py:67-88` 的模块扫描+实例化路径):**count=61,A 家族 28 + B 家族 32 + ipinfo_lite 1,全部 isinstance(SourceBase),全部实例化成功且 health() 可调用**;61 个名字清单逐一在列(输出存 `/tmp/issue248/smoke61.txt`)。另对被删 `download_host` 的 10 个源逐个断言返回值与删前相同(dshield→'feeds.dshield.org'、iptoasn→'iptoasn.com'、otx/otx_subscribed→'otx.alienvault.com'、stopforumspam→'www.stopforumspam.com'、dataplane→'dataplane.org'、cloud_ranges/cn_isp/rir_abuse/rir_delegated→None,全 OK)。
5. **LMDB 往返 + patch 锚测试不降级** ✅
   - `tests/sources/test_iplist_v6.py`、`tests/sources/test_ipinfo_v6.py` 与 7 个 patch `Source._http_get` 的测试文件(test_cloudzy/test_dns_public/test_dataplane/test_malicious_ip/test_root_servers/test_cloud_ranges/test_sibling_files)+ `tests/source_infra/test_source_base.py` + 顺带的 test_ipinfo_lite_rebuild/test_firehol_lists/test_blocklist_de_lists 合跑:**103 passed**(其中 test_sibling_files 按第三节换锚,其余文件一行未改)。

## 五、已知行为面说明(均为零功能差异,记录在案)

- **sources API 里 ipinfo_lite 的 `url` 字段从 `null` 变 `""`**:挂底座后继承空串默认(与 A 家族无 url 源的既有形态一致);前端 `SourcesPage.tsx:620` 用真值判空(`s.url ? 链接 : 占位`),两者显示完全相同。B 家族 32 个源全部显式定义 url,不受影响。
- `Source._load_v6_side` 从内联六步拷贝改为委托 `load_v6_side_state`:路径构造已核对逐值等价(`env_dir(base, e)` 与原内联 `base.parent / f"{base.name}.{e}"` 同一表达式),#243 已为该 helper 落过等价判例。
- threatfox.py 的 `parse_row`(裁决 6,legacy helper 名字碰撞)未动;caida_asorg 的 `lmdb_backed = False` 覆写不受上收影响。

## 六、遗留与后续

- **ADR 延后另写**(票面裁决 7):「为什么分底座不合成单类」——本报告可引用的实测数字:两基类重复消除后净 −238 行(17 件 +222/−460)、61 源零行为变化(bench 位等价 + C2 零失配)、`_source_base.py` 328→153 行。类 docstring 已留决策摘要。
- CI 位等价烟测语料不含 firehol/blocklist_de(#243 终审已知口径),本票沿用 #243 同款证据组合(本地全量 bench + 逐行等价论证)把关。
- 工件在 `/tmp/issue248/`(临时,未入仓,同 #243 判例):bench 两份、replay 三份、smoke61.txt、两轮测试 tail。
