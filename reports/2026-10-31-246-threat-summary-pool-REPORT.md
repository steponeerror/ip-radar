# #246 指控池第 6 份拷贝(threat_summary 跨组池化)收编 —— 交付报告(2026-10-31)

**分支** `ticket/threat-summary-pool`(基于 origin/master @ a3a1e8f9)
**实现提交** `32ac7136`(本报告随批另提交)
**结论** 按裁决三改面(helper 加参吃跨组池化与 asof 锚 / 生产改调 / 回放闸门镜像同改)+ 测试全绿 + 回放闸门 C2 全部读数前后逐位一致,零行为变更。(回放闸门=用冻结的历史查询数据重跑新代码、逐位对比旧结果,证明改评分代码没改变行为的自动化校验,脚本 `scripts/fusion_replay_gate.py`;C2=其判据组中的第二组:单指控组新旧输出逐位恒等。)

## 一句话说明改了什么

「指控池」= 被指控 IP 的有效指控证人集合( Glossary 已有词条):先按指控章(malicious/suspicious)筛出证人,同一来源只取最强一条断言,再做「谱系去重」(防止互相抄作业的镜像列表被算成两个独立证人),最后用这套系数算总置信度。这个核心循环此前抄了 6 份,#244 收编了前 5 份;本票收编最后 1 份——`_types.py` 的 `threat_summary()`(查询结果顶层"威胁摘要"的置信度重算),它有两个前 5 份没有的特殊点:**跨组池化**(把多个分类组的证人明细放进同一个池,每条证据按自己所属分类的半衰期衰减)和 **asof 锚**(衰减按查询指定的时刻算,而不是现在的墙钟,便于月度读数可复现)。

## 改动明细(3 个代码文件 + 测试 + 词汇表)

### 1. helper 按需加参(`backend/ipdb/_logodds.py:119`)

`accuser_pool` 的 entries 从「只收三元组」扩为「三元组或四元组」:第 4 元 = 该条证据自己的 ctype(分类类型,决定衰减半衰期);不携第 4 元时回退到原有的池级 `ctype` 形参。前 5 个消费面(单分类组、全池同一个 ctype)调用方式一字不动。`now` 形参(asof 锚)是 #244 已有的,本票只是让第 6 份用上。

- **为什么扩元组而不是加新形参**:跨组池化里 ctype 是"逐条证据"的属性而非"整个池"的属性,挂在每个 entry 上是唯一不改变其他 5 个调用面的形态;池级 `ctype` 形参保留为缺省值,语义向前兼容。
- **零行为变更注**:分类类型目前对衰减**实际无影响**(`DECAY_OVERRIDES` 空表,所有类型统一 60 天半衰期),所以第 4 元在今天是"语义正确、数值恒等";等 Phase 2 按类型估出半衰期后它自然生效。

### 2. 生产改调 helper(`backend/ipdb/_types.py:132-160`)

`threat_summary()` 的内联池化循环(组级 + 明细级双滤 → 逐源 max → dedup → σ)替换为一次 `accuser_pool(...)` 调用:

- 指控章判定(组级 `v.verdict` + 明细级 `d["verdict"]` 双滤)留在生成器里,不吞进 helper——#244 判例:判定面形态各异,helper 不做判定。
- 跨组 ctype 逐明细携带(第 4 元 = `v.type`,该证据所属组的类型)。
- asof 锚经 `now=_lo.asof_to_now(self.asof)` 透传(与原实现同式)。
- **细节决定与理由**:
  - 判空条件从旧代码的 `if pool:`(池字典非空)改为 `if deduped:`(去重后列表非空)。两者等价:现行谱系表(DERIVED_SOURCES + LINEAGE_ANCHORS)下,池里最强的非 derived 来源永远不会被剔除,所以"池非空 ⟹ 去重后非空";该不变式已写进代码注释。
  - 喂谱系去重的列表从插入序变 sorted(helper 内统一口径)。这是裁决明示的"浮点求和顺序理论缝随收编自然闭合":求和顺序只影响浮点末位(ulp),置信度是 round 后的整数,实测消化为零漂移(见回放闸门)。**这是本票唯一的口径变化,与 #244 生产 _merge 的同类变更同一判例。**

`threat_summary` 在生产查询路径上(`to_dict()` 每次查询都调),上述全部保持逐位等价,无任何输出字段变化。

### 3. 回放闸门镜像同改(`scripts/fusion_replay_gate.py:79`)

闸门自带的镜像重算 `fusion_pool`(专门镜像 `threat_summary` 的池化循环,防止脚本镜像与生产实现漂移)同步改为调 `_logodds.accuser_pool`:池化数学单源化后,镜像函数只剩"入口构造"(双滤 + 跨组 ctype 携带 + asof 换算),与生产同一条数学路径。镜像与生产的交叉核对(xcheck,失配即报警)机制原样保留——现在它核对的是入口构造是否与生产一致。签名上注入的活函数从 `coefficient` 换成 `accuser_pool`/`asof_to_now`(同一"live 导入防漂移"模式)。调用点的 `pool` 变量相应改为直接使用返回的 `deduped` 列表(等价性同上条)。

### 4. helper 级新测试(`backend/tests/core/test_logodds.py`,仿既有形态,+2 条)

- `test_accuser_pool_per_entry_ctype_cross_group`:跨组池化直断——第 4 元 ctype 生效、缺省回退形参 ctype、四元组与三元组混用;用 monkeypatch 注入半衰期 override 钉语义(空表现状下两路径同值也一并断言 = 零行为变更护栏)。
- `test_accuser_pool_cross_group_with_asof_anchor`:跨组池化 × asof 锚联合直断——4 元组 + `now=`(生产 `_types.threat_summary` 的调用形态):锚回拨 → 证据更"年轻" → 系数更高;epoch 秒锚经 `asof_to_now` 与 datetime 锚同刻。

### 5. 词汇表同步(`GLOSSARY.md`)

「指控池」词条的锚点行"五消费面"同步为六消费面(补 `_types.threat_summary` 跨组池化 + 闸门镜像同调),同概念事实同步,不铸新词。

## 验证证据

### ① 回放闸门 C2(裁决验收第一条)

同语料同参数前后对照,命令(worktree 内、主仓 venv):

```
/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python \
    scripts/fusion_replay_gate.py \
    --data /home/huxiao/dev/pi-ip-lookup-tool/.eval-prod-data \
    --stride 10 --limit 1000000 --report dev/replay-*.md
```

语料指纹(与 #244 报告一致,数据面未动):主仓 `.eval-prod-data/`(生产 LMDB 快照镜像,目录时间 2026-10-29 21:31、顶层条目 129);43 指控源 v4 起点并集 **1,000,001**、stride 10 实际 lookup 10 万次。

| 读数 | 改前(a3a1e8f9) | 改后(32ac7136) |
|---|---|---|
| C2 单指控组新旧恒等 | **PASS**(strict 92,694 / 失配 **0**;loose 93,307 / 失配 **0**) | **PASS**(同,逐位相同) |
| 镜像 vs 生产 threat_summary 交叉核对 xcheck_bad | **0** | **0** |
| 探测 / 指控池非空 / lookup 异常 | 1,000,001 / 99,413 / 0 | 同 |
| 分数直方图(新列)、列联表、k 分布、升降计数、benign 腿 | (基线) | **逐位相同** |

**逐位一致的完整证据链(三轮对照)**:改动前(a3a1e8f9)与改动后(32ac7136)背靠背各跑一轮(相隔 1 分钟),报告除时间戳 / code_commit / 耗时外,后轮相对前轮仅"旧规则直方图"出现 1 个 IP 的桶位漂移(70-79 桶 → 60-69 桶,旧列 2,208→2,207 / 2,687→2,688)。该漂移**不可能来自本票改动**(旧规则是被冻结的内联实现,代码不在改动面;且新列一动不动)。为证伪归因,补跑**同码对照**:改动前代码自己隔 2.5 分钟再跑一轮(pre#2),pre#1 vs pre#2 出现**完全相同的漂移签名**(同一对桶、同方向、rho_old/n 同步 ±1)。最后 diff(改后, 10:51:16) vs (pre#2, 10:52:51):**全部读数逐位一致,仅时间戳、code_commit、耗时三处进程元数据不同**。结论:闸门在墙钟衰减下有 ±1 桶位的固有跑间噪声(证据随真实时间老化,个别 IP 跨过四舍五入边界),与本票改动无关;C2 两口径失配 0、xcheck 0 在所有轮次恒成立。

报告原件:`dev/replay-before-246.md` / `dev/replay-before2-246.md` / `dev/replay-after-246.md`(一次性工件,gitignore,不入 git)。

**既有状态声明(与本票无关)**:三轮 rc 均=1,C3=第三组判据(benign ≥70 占比新≤旧)/C4=第四组判据(Spearman ρ 新≥旧)为 FAIL——基线即如此(闸门拿 2026-10-03 冻结的旧选角规则对比今日融合在今日语料上的差),本票改动前后这两腿数字逐位未动。

### ② 全量测试(裁决验收第二条)

主仓 venv、worktree 代码:

```
backend $ .venv(主仓)/bin/python -m pytest tests -q
→ 2311 passed, 19 skipped, 1 failed(424.5s)
```

唯一失败 `tests/test_ops_rounds_e2e.py::test_health_round_real_run` = **基线同红**:报错为 ops-agent 子进程 Node.js 轮次信封契约违背(环境性,与本票代码零交集);用 `git stash` 回到 a3a1e8f9 干净基线重跑同测同样失败,已实证。其余 2311 全绿(含 types/eval/asof 全部既有等价网与新增 2 条)。

### ③ helper 级新测试(裁决验收第三条)

见上文改动明细第 4 条;`pytest tests/core/test_logodds.py -q` → 20 passed(含既有 4 条 accuser_pool 测试全数保留通过)。

## 边界与风险声明

- 本票零行为变更的根基之一是 `DECAY_OVERRIDES` 空表(ctype 对数值暂无影响);Phase 2 填表后,`threat_summary` 的置信度会开始按各证据自己的类型半衰期衰减——这是**语义上正确**的方向(原内联实现就是这么写的,helper 忠实吃下),不是回归。
- 回放闸门存在墙钟跑间噪声(±1 桶位,见证据链);后续票若做"逐位一致"验收,建议前后轮背靠背跑,或考虑给闸门加 asof 锚定参数(本票未加,超出裁决范围)。
- 未动 `_source_base.py` / `_sources/_base.py`(并行票 #248 地盘);未碰前端;未 push。

## 挂账(超出票面,未动)

无新发现。闸门墙钟噪声现象已在上节声明,是否立票由 triage 裁决。
