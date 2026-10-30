# 票 #243 交付报告 — 源生命周期读侧纯删层(架构评审候选 1 第一层)

日期:2026-10-30 · 分支:`ticket/arch-src-lifecycle-dedupe`(基于 origin/master @ 34021685)· 实现:SDD worker

## 一句话结论

firehol / blocklist_de 的 4 处照抄覆写(load ×2、query ×2)已删,子类直接继承 `IpListSource` 基类实现;ipinfo_lite 的 `_load_v6_side` 拷贝按票面许可的「模块级共享函数」方案消除。零行为变化:**bench_lookup 位等价 zero diff、backend 2314 测试通过**(1 失败为基线 commit 同样红的既有环境问题,与本票无关,见 §4)。

## 删了什么

| 文件 | 删除 | 行数(删) |
|---|---|---|
| `backend/ipdb/_sources/firehol.py` | `load()`(:105-125)、`query()`(:243-264)两处覆写;随删仅被覆写使用的模块级 `import lmdb` 与 `from ._lmdb import (ip_to_int, lookup, read_ptr, open_env_read, read_disjoint_flag)`(含 2 行注释) | 49 |
| `backend/ipdb/_sources/blocklist_de.py` | `load()`(:132-152)、`query()`(:204-225)两处覆写;随删模块级 `import time`(删 load 后仅剩 health() 内联 import 使用)、`import lmdb`、同款 `_lmdb` import 块(含 2 行注释) | 50 |
| `backend/ipdb/_sources/_base.py` | `IpListSource._load_v6_side` 体由 17 行逐字实现 → 2 行单源点委托(docstring 改指向共享函数) | 净 -17 |
| `backend/ipdb/_sources/ipinfo_lite.py` | `IPinfoLiteSource._load_v6_side` 同上收敛 | 净 -17 |
| `backend/ipdb/_sources/_lmdb.py` | **新增** `load_v6_side_state(base)` 单源点(+19,纯新增,不改既有行) | +19 |

合计:31 增 / 143 删,净 **-112 行**。

## 等价性论证(逐行 diff,删前完成)

方法:对每个待删覆写,用 `sed` 按行号精确切出覆写与基类实现,`diff` 逐行比对(切件存 `/tmp/issue243/*.txt`)。

1. **firehol.load / blocklist_de.load vs IpListSource.load**(`_base.py:138-158`):仅 docstring 措辞(「打开已有 env,读 sidecar,不重建」vs「加载现有 env(若有),永不重建」)与 import 断行差异;方法体逐字相同。→ 等价,删。
2. **firehol.query / blocklist_de.query vs IpListSource.query**(`_base.py:230-248`):差异为 ①签名注解 `-> Any`(有无)、②局部变量名 `node` vs `result`、③尾部 `if node is None: return {} / return node` vs 三元 `return result if result is not None else {}`。三条全落在票面「变量名等差异算等价」许可内;分支结构、异常重试路径、返回值逐位同义。→ 等价,删。
3. **ipinfo_lite._load_v6_side vs IpListSource._load_v6_side**:`diff` 退出码 **0**(零差异,含 docstring)。→ 等价。

随删的模块级 import 均为核验后「仅被已删覆写使用」(grep 复核 firehol/blocklist_de 余文无引用;`time` 在 firehol 仍被 rebuild 使用故保留,blocklist_de 删)。

## ipinfo_lite 处置及理由(票面第 3 条)

票面许可「提取模块级共享函数供两边调用」,采之:

- `_lmdb.py` 新增 `load_v6_side_state(base: Path) -> tuple[object | None, bool, int, int]`,即原拷贝的逐位搬运(cleanup_stale → read_ptr → 零态早退 / read_disjoint_flag → open_env_read → count/cov 解析);`env_dir(base, e6)` 与原 `base.parent / f"{base.name}.{e6}"` 是同一表达式既有工厂函数。
- `_base.py`(`IpListSource`)与 `ipinfo_lite.py` 的 `_load_v6_side` 改为 2 行委托,方法本体保留(两条 v4 路径早退/正常各调一次的结构不变);`load_v6_side_state` 加入两处既有的模块级 `from ._lmdb import`(_lmdb 本就被模块级导入,零新增导入成本)。测试 monkeypatch 均打在 `ipdb._sources._lmdb.*` 模块面(已核全仓),共享函数在 `_lmdb` 命名空间内解析这些名字,patch 语义不变。
- **Source(`_source_base.py`)侧同款逐字拷贝不动**:`_source_base.py` 不在票面点名文件内,收敛它属「两基类合一」后续票;已在共享函数与两处委托的 docstring 留注指向。

**唯一微差(已审计,不可观测)**:原 else 分支先赋 `self._disjoint6` 再 `open_env_read` 赋 `self._reader6`;委托版两个值都算完才一次性解包赋值。若 `open_env_read` 抛异常,原版会留下已更新的 `_disjoint6`(半态),新版不更新。审计全仓 `_disjoint6` 读者:全部是 `_query6` 内 `lookup(..., disjoint=self._disjoint6, ...)`,且都先过 `if self._reader6 is None: return {}` 门(重试路径则二者同源重读)——异常传播出 `load()` 后没有任何代码路径能读到「有 _disjoint6 无 _reader6」的半态。返回值、异常类型、后续查询结果逐位一致。

## 验证结果

- **位等价**(票面验收):`PYTHONHASHSEED=0 backend/scripts/bench_lookup.py --snapshot / --compare`,数据面 = 主工作副本 `backend/data`(4.6G,61 源 LMDB;worktree 经 `IP_RADAR_DATA_DIR` 指向,零拷贝)。
  - 基线(删前):`/tmp/issue243/bench-baseline.json`
  - 删后 `--compare`:**`bit-identical: zero diff`(exit 0)**
  - 删后再 `--snapshot`:`/tmp/issue243/bench-after.json`,与基线 **`cmp` 字节全同**
  - 该基准覆盖 firehol/blocklist_de 走继承 load/query、ipinfo_lite 走委托 `_load_v6_side` 的真实查询路径(60 IP × 61 源融合输出逐位比对,epochs 无漂移)。
- **测试**(backend 全套,`backend/.venv` + `python -m pytest tests -q`):**2314 passed, 9 skipped, 1 failed**。
  - 唯一失败 `tests/test_ops_rounds_e2e.py::test_health_round_real_run`:ops 健康轮 e2e 拉起 Node.js 子进程失败(`rc=1,stdout 非单行 JSON … Node.js v22.23.2`),与本票改动无代码接触面;**stash 掉本票全部改动后在基线 commit 34021685 上同样红**(同断言同信封),属既有环境问题。
  - 直接相关面全绿:`tests/sources/test_firehol_lists.py`、`test_blocklist_de_lists.py`、`test_ipinfo_lite_rebuild.py`、`test_ipinfo_v6.py`、`test_iplist_v6.py`、`tests/core/test_storage_helpers.py` 合跑 **50 passed**。
- 语法/导入面:5 个改动文件 `ast.parse` 全过;整仓测试收集与运行即证明导入图完好。

## 顺手核出的其它照抄拷贝(票面许可「顺手核,不扩土」——仅记录,未动)

`rg 'def (load|query|_query6)\(' backend/ipdb/_sources/*.py` 全景核对,以下覆写不在票面点名范围:

- `cn_isp.py:89 load / :138 query`、`stopforumspam.py:78 load`、`infra_services.py:140 load`、`caida_asorg.py:103 load / :115 query`、`ipinfo_lite.py:106 load / :228 query / :250 _query6`:各有与基类同形或近形的生命周期拷贝,归「两基类合一」票统一裁决(其中 ipinfo_lite.query/_query6 含 `_shape` 整形,非纯照抄,不可盲删)。
- `Source`(`_source_base.py`)与 `IpListSource`(`_base.py`)两基类间的 load/_load_v6_side/query/_query6/health 五联平行拷贝:本票红线,不动。

## 遗留与建议

- 无行为遗留;唯一外部依赖 = `/tmp/issue243/` 下基线/after 两份 snapshot 属临时工件(未入仓),票面要求的「备查」以此报告 §验证结果 + CI 位等价烟测(`scripts/ci_bitidentity_smoke.sh`,PR CI 自动跑)双保险。
- 后续票建议:两基类合一(harvest/Evidence vs parse_raw/fields 钩子调和)时,把 Source 侧 `_load_v6_side` 一并收敛到 `load_v6_side_state`,并复评 §顺手核 清单。
