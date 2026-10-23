# WORKER-REPORT — 票 #163 P2-P1:PROBE 拆出(lib.sh 复用 + 位等价门)

分支 `feature/ops-p2-p1`(基线 d316f18e = feature/p2-health-pipeline tip,merge 后仍 up to date)。
Commits:`36b551ab`(实现)→ `6e536b12`(自测+golden)。

## 改动面(全部在 ops/agent/)

- `tools.mjs`:matrix 扫描 CLI 抽模块级 `matrixScanCli()` + 序列化单源 `matrixArtifactText()`(indent-1、无尾换行)。`runMatrixScan()` 只剩薄包装,legacy 返回形状/信封语义(trace 有无、error 键分支)零改动。
- `pipeline/steps.mjs` PROBE:matrix 由 fixtures 罐装换真扫描(`matrixScanCli` 单源);成功时 `01-probe-matrix.json` 与 legacy `<ts>-matrix-scan.json` 逐字节同文;失败=嵌套信封落件不阻轮。freshness 腿不变(仍是 lib.sh `extract_feed_urls`+`feed_freshness` 真执行,curl 传输层 PATH stub)。
- `selftest-pipeline.mjs`:增⑦位等价例(legacy 腿=agent.mjs `runRound` 真 Agent 循环点 `health_snapshot`,faux 模型 golden health 例同型);curl stub 时间确定性化(Last-Modified=UTC 日界截断,同日内字符串恒定且 age_days 恒=d);新增 `OPS_EVAL_PY` stub(golden stubPy 同型)两腿共用;feeds.txt **101 URL 固定 fixture 钉死**。
- `golden/cases.json`:pipeline 例增 `stubs.matrix` + `01-probe-summary.json` matrix 三键断言 + `01-probe-matrix.json` 断言;$comment 记对照关系。
- `fixtures/pipeline/matrix.json` 删除(罐装件退役);README、gates.mjs 注释(78→101)同步。

## 位等价验证实录(自跑,临时脚本已删)

```
[清单] URL 数 = 101
[legacy 腿] health_snapshot ok=true urls_n=101 frozen=3 matrix_exit=0
[legacy 腿] TSV=…/ops/artifacts/2026-10-23-232704-health-freshness.tsv
[legacy 腿] matrix=…/ops/artifacts/2026-10-23-232704-matrix-scan.json
[管线腿] ok=true [stage] PROBE done gate=PASS dur=0s artifact=01-probe-summary.json
== md5 ==
f8eb012f65c72ef5fc1a241ef79f716d  …-health-freshness.tsv        (legacy)
f8eb012f65c72ef5fc1a241ef79f716d  …/01-probe-freshness.tsv      (管线)
df0ca1199cfd4365a8a2d820dd936182  …-matrix-scan.json            (legacy)
df0ca1199cfd4365a8a2d820dd936182  …/01-probe-matrix.json        (管线)
== diff TSV ==   (diff 输出为空)   101 行 = 101 行
== diff matrix ==(diff 输出为空)   347 B = 347 B
```
计数两口径对拍(sc.frozen_n 等 ↔ summary.buckets)在 selftest ⑦ 内断言,PASS。

## 四门结果(commit 6e536b12 后跑)

1. `node ops/agent/selftest-pipeline.mjs` → **PASS=12 FAIL=0**(含新增位等价例)
2. `node ops/agent/selftest-contract.mjs` → **PASS=15 FAIL=0**
3. `bash ops/agent/selftest.sh` → **PASS=100 FAIL=0**
4. `node ops/agent/golden/run-golden.mjs` → **PASS=9 FAIL=0**(pipeline_health_full_faux 含新 matrix 断言)

## 偏离与理由

1. 票文「复用 lib.sh feed_freshness/**matrix**」——lib.sh 无 matrix 函数;matrix 现路径=tools.mjs `runMatrixScan`→EVAL_PY。处理:抽 `matrixScanCli` 单源两消费方共用,legacy 零行为改动(探测逻辑零重写,以单源达成复用)。
2. matrix 产物路径对照:legacy=`<ts>-matrix-scan.json`(ts-slug 族,ops/artifacts/);管线=`01-probe-matrix.json`(§4.1 序号前缀族)——已记 steps.mjs 注释+cases.json $comment+本报告。**失败面差异**:legacy 失败不落件(sc 嵌套信封),管线按 §4.1 落信封进件(证据不灭失);不阻轮语义两侧一致。
3. curl stub 由 golden 的 -600s 余量改为 UTC 日界截断(仅 selftest-pipeline 一处;golden 各例独立跑不受影响):位等价要求两腿先后跑字节稳定,余量型 stub 每次调用 Last-Modified 含实时秒必不等。理论残余:两腿间隙恰跨 UTC 日界(秒级窗口)→ 失败可复跑。
4. summary.buckets 保持 P0 形状(fresh/frozen/unreachable/token_required/no_lm,无 near_band):位等价验收面=TSV+matrix 工件+计数对拍,near_band 是 legacy 摘要员口径非管线工件契约,不扩形。
