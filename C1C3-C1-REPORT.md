# C1C3-C1-REPORT — 工件名表单源(#202 C1,伞票 #201)

工位:`.worktrees/c1c3-c1`(分支 `feature/c1c3-c1`,基 a7c0f150)。零 push;只动本 worktree。

## 交付物

1. **`ops/agent/artifacts.mjs`(新)** — 轮目录工件名单一真源:
   - `ARTIFACTS`(Object.freeze,18 固定名:01-…/02-…×3/03-…×2/04-…/05-deep-verdicts/06-…/07-…×2/08-…×2/09-budget/gates.json/state.json)+ `ARTIFACT_NAMES` 派生名单(禁手抄)
   - DEEP 逐假设参数族:`deepArtifactName(slug)` / `deepTranscriptName(slug)` 工厂 + `DEEP_ARTIFACT_RE` / `DEEP_TRANSCRIPT_RE` 匹配面 + `DEEP_TRANSCRIPT_GLOB`(仅 gates inputs 声明标签面)
   - 范围注释:retro/<round>.json(opsRoot 级)、breaker.json(opsRoot 级)不在表;磁盘名改值=改磁盘名,须过重放/位等价门
2. **`ops/agent/pipeline/gates.mjs`** — 门读面/inputs 声明/reason 字符串全改 `A.*` 取值(十门 ~45 处裸字符串清零;G_DEEP 巡检 regex 改 `DEEP_TRANSCRIPT_RE`,appendGate 写 gates.json 改 `A.GATES`)。gates.json 落盘 inputs/reason 字节不变。
3. **`ops/agent/pipeline/steps.mjs`** — 写出面/读面全改 `A.*` 取值(31 处;DEEP 族走工厂,`modelItemComplete` 的 `${base}.json`/`${base}-transcript.jsonl` 拼接改工厂两查;ITEMIZE replay 回声跨轮读 `06-itemize-manifest.json` 亦改表值)。
4. **`ops/agent/selftest-pipeline.mjs:177`** — 17 名手抄清单退役,改 `ARTIFACT_NAMES` 遍历 + 双向闭包差集断言(名表外文件必须 ∈ DEEP 参数族;名表加项不更新写出面=红;步面新写工件不入表=红)。

## 验收门(全绿,实测数字)

| 门 | 基线 | 实测 |
|---|---|---|
| selftest-pipeline | 78/0 | **78/0** |
| selftest-t4 | 票面 58/0(集成分支已含 PR3b 增 5) | **63/0**(FAIL=0,零回归) |
| selftest-contract | 18/0 | **18/0** |
| golden(run-golden.mjs) | 9/0 | **9/0** |
| standard-check | 47-48 OK | **OK=47 FAIL=0**(条文14 金标3 建议10 挂点31) |
| pytest ops 子集(`tests/ -k "ops or store"`,cwd=worktree/backend,主仓 venv) | 271 passed | **271 passed / 1 skipped / 0 failed** |
| 罐装面工件集合位等价 | — | 见下 |

**位等价抽验**(驱动 `/tmp/c1-equiv-driver.mjs` = selftest R1 同型罐装 faux 轮,child 真跑 `pipeline.mjs health`,重构前/后各一次):
- 轮目录 23 文件名集合**逐字节同**(18 固定 + 2 假设 × (.json/-transcript.jsonl));20/23 md5 直接全等
- 3 异 = 09-budget.json / gates.json / state.json:差异**仅** generated_at/started_at 时戳、dur_ms、wall_s、驱动 TMP 根路径串(mkdtemp 后缀);gates.json 时戳规范化后逐字节同,budget/state 再 TMP 路径规范化后逐字节同 → 零语义漂移(inputs/reason/读数全同)
- `git diff a7c0f150 -- ops/agent/golden/ ops/agent/fixtures/` 空(cases.json 与 fixtures 逐字节未动)

**闭包哨真红验证**(TDD 红步):名表临时加 `TAMPER_PROBE: "10-c1-tamper.json"` → selftest **FAIL=1**(`工件缺:10-c1-tamper.json`)→ 还原 → 78/0 绿。

## Commit 链

```
44e60a4e  wip(#202): C1 开工占位(防超时丢工)
7813d893  #202 C1:工件名表单源 artifacts.mjs + selftest 清单面改单源 + 双向闭包哨(78/0)
86f57d27  #202 C1:gates.mjs 门读面/inputs 声明全改名表取值(~45 处清零,字节不变;78/0)
48826c9c  #202 C1:steps.mjs 写出/读面全改名表取值(~31 处清零;DEEP 参数族工厂;78/0)
<本报告 commit>
```

## 自决清单(实现者裁量,均留痕)

1. `DEEP_TRANSCRIPT_GLOB` 补进 artifacts.mjs:gates G_DEEP inputs 里的 `"05-deep-*-transcript.jsonl"` 标签族与工厂/正则同文件单源(标签漂移面收口)。
2. 表键名风格 `PROBE_SUMMARY` 等(值派生自文件名,不带扩展名后缀);`02-verify-rules.json` 入表键 `VERIFY_RULES`。
3. opsRoot 级文件(retro/<round>.json、breaker.json)不入表——非轮目录面,gates 里 retro 标签 `retro/${key}.json` 维持字面量(非 ctx.dir 工件);已在 artifacts.mjs 头注释声明边界。
4. ticket 写 t4 基线 58/0,实测集成分支基线 63/0(PR3b 已加 5 例);以 FAIL=0 + 实测数为准报告。
5. CHANGELOG 双语条:spec 验收门 5 是**整批一条覆盖 C1-C3**,留给伞收口(C2/C3 合入后一次写),不在 C1 单票内提前写半条。
6. pytest 运行法:cwd=worktree/backend(`python -m pytest` 把 cwd 入 sys.path;直接 cwd=worktree 会 `ModuleNotFoundError: No module named 'ipdb'/'main'`——venv 属主仓,无 editable 指向 worktree)。

## 残余回声面(spec 三层措辞之外,未动;闭包哨兜底)

- `ops/agent/pipeline/faux.mjs:37-39` `transcriptName`:3 处 DEEP/SYNTH/TRIAGE transcript 名字面量(faux 面,写出与 steps 同名;哨管磁盘集合,名字漂移会即时红,但字面量本身未单源)。
- `ops/agent/pipeline.mjs` HEALTH_PIPELINE def `out` 数组(~10 处工件名)、SKIP_WHEN 面 `04-dispatch-bundles.json`/`03-triage-hypotheses.json` 字面量、STAGE_PREFIX:spec C1 三层消费面=gates/steps/selftest,pipeline.mjs 定义表面不在票面;若收口建议随 C2/C3 或伞票顺手(等价改法已验证:`import { ARTIFACTS as A } from "./artifacts.mjs"` + `out: [A.X]`)。

## 余项

无阻塞项。C2(budget.mjs admitOrRefuse 提取)/C3(ctxShape 提取)由同批其他实现者承担;本分支 `feature/c1c3-c1` 待任务评审后并入 `feature/c1c3-artifacts-ctx`。
