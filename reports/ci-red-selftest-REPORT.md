# ci-red 分支简报:ops selftest 月帽 fixture 日期脆性修复(#266)

- 分支:`ci-red`(基线 master a4d2ebd8,开工已验 `git merge-base --is-ancestor master HEAD`)
- 性质:**test-only**,零产品代码改动(`git diff --stat` = 1 file, +4/-1)

## 改了哪几处

仅一处,`ops/agent/selftest-pipeline.mjs:2005-2011`(发现轮月帽共享执法 #207 T1 用例):

- 台账 fixture 行日期 `2026-10-26`(硬编码)→ `${monthNow()}-26` 派生,照 A2 先例(#199,同文件 :1786/:1804/:1815/:1830 的 `monthNow()` 派生惯例)。
- 日取 26 = 每月都有的日子(不取 29/30/31,避免撞月长)。
- 注释三行说人话带出处(#266 + A2 先例 + 机制:月帽按墙钟当月求和,硬编码过月翻页即花费归零不拒跑,断言假红)。
- `monthNow` 经既有模块级 `const budget = await import("./pipeline/budget.mjs")`(:1985)取用,零新 import。

## 红证前后对照

同一命令 `cd ops/agent && node selftest-pipeline.mjs`:

| 时点 | 结果 |
|---|---|
| 修复前 | `FAIL 发现轮月帽共享执法(#207 T1)…Expected values to be strictly equal:` → `pipeline-selftest: PASS=103 FAIL=1` |
| 修复后 | `pipeline-selftest: PASS=104 FAIL=0` |

其余三个 selftest 同分支跑平(全量回归,零新伤):

- `selftest-contract.mjs`:PASS=19 FAIL=0
- `selftest-standard.mjs`:PASS=15 FAIL=0
- `selftest-t4.mjs`:PASS=63 FAIL=0

(环境注:worktree 首跑前 `ops/agent` 内 `npm ci` 装 326 包,undici 等依赖与主检出无关。)

## 同类排查结论

全类排查四个文件(`selftest-{pipeline,contract,standard,t4}.mjs`)喂月帽/预算逻辑的硬编码日期台账行,逐条台账写入(`LEDGER_FILE`/`ledger` write)过筛:

| 位置 | 内容 | 判定 |
|---|---|---|
| selftest-pipeline.mjs:1786/:1804/:1815/:1830 | A2 族月帽/预算用例,行日期 `${m}-01` 已派生 | 本就正确(先例来源) |
| selftest-pipeline.mjs:2000 | 仅表头无日期行(appendRefusalTrace 直测,无月求和) | 无脆性 |
| selftest-pipeline.mjs:2007 | `2026-10-26` 硬编码,唯一喂月帽准入的硬日期行 | **本批修复** |
| selftest-t4.mjs:916 | `2026-10-20` 行,仅喂 `cleanupFixture` smoke 层文件保全断言(查存在性,不进月帽解析),日期无关 | 无脆性,不动 |
| selftest-contract.mjs / selftest-standard.mjs | 零台账行写入(仅注释含日期) | 无脆性 |

配套核实:round-id 里的硬编码日期(如 `RD="2026-10-26-0940-discover"`)只过形状校验(pipeline.mjs:156 正则),不与墙钟比较,不属此类脆性;`mkTree`(:135)不播带日期台账;`fixtures/` 为 faux 模型响应与判例文档,无台账 fixture。

**结论:硬编码日期喂月帽/预算逻辑的脆性仅 #266 一处,已修;无同类残留。**

## 交付状态

- commit 本分支,未 push;完成后 `git merge master`(应无冲突,见 commit 记录)。
