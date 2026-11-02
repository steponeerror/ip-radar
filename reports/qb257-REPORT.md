# qb257 分支简报:前端 api.ts 取数样板折并(#257)

- 分支:`qb257`(基线 queue-batch 805c0d59,开工已验 `git merge-base --is-ancestor queue-batch HEAD`)
- 性质:**纯重构,行为零变化**——所有导出签名、fetch 调用参数(URL/init 逐字)、fallback 错误文案、错误信封路径(throwApiError status+code+message)全部保持;不改任何端点形状。
- 环境:worktree 首跑 `cd frontend && npm ci`(169 包装齐);dryer 工具 `~/.cache/ub-tools/dryer` 本机缺失,已按 code-metrics skill 记录的官方源重装(`git clone https://github.com/unclebob/dryer`,与 2026-10-31 实测同源),非「人工同形清单」降级路径。

## 改了什么

单一文件 `frontend/src/api.ts`(967 → 960 行),四个泛型/专用助手收编 34 处同形「fetch → 非 ok 抛信封错 → 按形状取结果」样板:

| 助手 | 收编对象 | 处数 |
|---|---|---|
| `requestJson<T>(url, init, fallback)` | 返回 JSON body 的端点(原 jsonOrThrow 23 处 + 原生手写 getTasks/enqueueBatch/enqueueSingle 3 处) | 26 |
| `requestVoid(url, init, fallback)` | 成功无 body 的控制端点(204):cancelTask/cancelBatch/pauseBatch/resumeBatch/adminLogin/deleteAdminKey/putAdminToken/clearAdminToken | 8 |
| `patchAdminKey(sub, payload, fallback)` | admin 密钥面共用同一 PATCH 端点 `/api/admin/keys/:sub` 的三动作(sources / disabled:true / disabled:false) | 3 |
| `requestText(url, fallback)` | OpsFileTextOut 系四全文端点(包/台账/判例/待审条目,GET → 单字段 `{text}`) | 4 |

设计要点(注释均已落码内):

- **`init` 为 undefined 时保持单参 `fetch(url)`**:既有测试按调用形状断言(TaskProvider 重同步 `toHaveBeenCalledWith("/api/tasks")` 单参、api.ops 两条 `calls[0][1]).toBeUndefined()`);助手内三元分支保证 mock 记录的参数数组逐字不变。
- **requestVoid 不读 json()**:204 空 body 读 json 会抛 SyntaxError,故与 requestJson 分立(行为红线)。
- **jsonOrThrow 退役**:23 处调用全部收编后零引用,逻辑内联进 requestJson;postUpdate 的「不走 jsonOrThrow」注释同步改指 requestJson。
- **语义不同者明确不收编**(helper 头注释列明,各自原注释保留):apiFetch 演示头通道(getDbStatus/流式查询/STIX)、exportOpsPrecedents blob 下载、postUpdate 202/409 同吃、adminMe 401/503→null 降级、adminLogout 静默容错。
- 单字段提取端点(packages/items/precedents/latest)以泛型参数声明提取形状,取代原隐式 any(如 fetchEvalModel 原 `res as {...}` 断言改泛型)。

## dryer 复跑对照(验收项)

同一命令、同一阈值(0.82 默认),对象 `frontend/src` 全量、只数 api.ts 相关对:

| 时点 | api.ts 对数 | frontend/src 全量对数 |
|---|---|---|
| 基线 queue-batch 805c0d59 | **23**(与票面一致:簇 :494-512/:693-716/:744-756/:772-778/:835-847/:963-966) | 30 |
| 折并后(qb257 3eba584d) | **1** | 8 |

- **23 → 1,降幅 96%**,显著下降达标。
- 残余 1 对 = `listOpsPackages ↔ getOpsItems`(1.00):两列表端点同为「GET 单键列表」形(2 语句、4 行),属端点形状本身;再折需引入 `requestField(url, pick)` 级抽象,收益低于可读性代价,依票面「不强求 23 对全清」留作残余。
- 全量 30 → 8 中的其余 7 对为 ui/i18n/测试镜像等非 api.ts 既有对,本批未触碰(票面豁免/低价值类别)。

## 验证

- `cd frontend && npx tsc --noEmit`:绿(零输出)
- `cd frontend && npm test`(vitest run):**43 文件 / 451 用例全绿**,每个 commit 均跑过一遍
- `npx eslint src/api.ts`:rc=0
- 行为零变化自查:全 diff 人工过目——URL 模板字面量、init 对象(method/headers/body)、fallback 文案、encodeURIComponent 位置逐字保持;`patchAdminKey` 的 `JSON.stringify(payload)` 与原三处内联字面量产物字节相同(含 `{"sources":null}` 分支);字节级一致不适用(票面:前端无 bench;旧称位等价,已退役),以测试面 + 类型面把关。

## 过程插曲(自纠)

- 一次 edit 手滑把 readOpsLedger 的 URL 写成 `"/api/ledger".replace("/ledger", "/ops/ledger")`(求值结果相同但属胡写),commit 前当场发现改回 `"/api/ops/ledger"`;一次 requestText 忘加 `async`(await 语法错),tsc 即刻抓回。两者均未进任何 commit。

## 提交清单(小步 5 提交,均只动本分支)

1. `6ceab80d` 1/4 助手落地 + 任务面收编(7 端点)
2. `2072af9a` 2/4 admin 密钥/登录/token 面收编(10 端点)
3. `07f9aaef` 3/4 源面/评估/版本/自更新读面收编(5 端点)
4. `5c4da638` 4/4 ops 全面收编(12 端点)+ jsonOrThrow 退役
5. `3eba584d` 5 同端点族再收编两族(patchAdminKey/requestText),23→1

收编端点合计 34 处 + 两族内部复用;后续维护新端点时按四助手对号入座即可。
