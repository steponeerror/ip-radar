所有证据已收集完毕。正在编写评审报告（由于没有可用的写入工具，因此完整的产物将在下方返回，以便持久化保存至 `.worktrees/disc-367/review-367.md`）。

## 评审

**结论:PASS-with-notes**(P2×2 + report-only 若干;无 P0/P1)

### 正确 — 逐条核验通过(证据)

**票面①「同 #364 切流件律」**:`deploy/ops-cron-v2-discover.sh` 与 `deploy/ops-cron-v2.sh` 逐键对照同构——同 `OPS_V2_CONTAINER/OPS_V2_OPS_ROOT/OPS_V2_APP_ROOT` 三 override(discover.sh:31-33)、同 `printf %q` 织法两处(32-34 行)、同 auth.json 预检跳过 exit 0、同 `DOCS_ROOT=dirname($OPS)`/`OPS_AUTH`/`OPS_EVAL_PY=$(command -v python3)`/`OPS_DATA_DIR=/app/data`/`PI_CODING_AGENT_DIR=$OPS`/`LANG=C.UTF-8` 六键 export、同 `unset IP_RADAR_ADMIN_PASSWORD IP_RADAR_API_JWT_SECRET` 恰两管理密钥、GH_TOKEN/IP_RADAR_ALERT_URLS 继承、不设 `OPS_SWEEP_DRY_RUN`、同「先跑后取 `$?`」rc 透传形(注释同款判例引用)。无静默漂移;唯一差异面(单模型读/跳过分支/`--model`/run-discover 启动面)全部是票面声明差异且头注写明出处。

**票面②「--model 现读+缺配置跳过」**:run-discover.mjs:66-68 钉死 real 面无缺省 resolve(`if (!modelRef) throw {usage:true}` → exit 2),故 cron 预检跳过是必要的(不跳=每日用法错噪音)。跳过分支紧随读取之后,`|| true` 只包 python 读面,不吞任何后续错误;`--model "$MODEL_DISCOVER"` 双引号包裹 + node 侧 `flag("model")` 形状校验(i<=0<i<len-1)双保险。agent-config 键名与生产实际对得上:`backend/ipdb/_ops_config.py:205,269-270` 写盘键即 `model_discover`,且 `_qualified` 归一为 `provider/modelId` 形(test_ops_config.py:142-145 钉盘上形状),与 --model 校验兼容。

**票面③「月帽真执法」**:执法路径完整——run-discover.mjs:69 `admitRound({roundType:"discover"})` 先于 openHarness → budget-guard.mjs `roundKnobs`→`readDiscoverKnobsV2`(`...budget.readDiscoverKnobs(env)` 展开四键 + `OPS_DISCOVER_MONTHLY_CAP_CNY` 缺省 "20" 覆写 monthlyCapCny,#332 readAddKnobs 同判例)→ `budget.admitOrRefuse({capCny: knobs.monthlyCapCny, round:"discover"})` → 拒启留痕 `[admission]` log + 台账行 `budget_monthly refused est=0.05 cap=20`(轮次列=discover,旧 appendRefusalTrace 原样,v1 selftest-pipeline.mjs:2084 同形)→ CLI 信封 `budget_monthly` exit 1。台账口径不变(monthSpendOfLedgerText Σcost+est 同函数消费)。文案键名改写 `replace("OPS_PIPELINE_MONTHLY_CAP_CNY","OPS_DISCOVER_MONTHLY_CAP_CNY")` 仅 discover 面、refusalOf 单源文案该键恰出现一次,数值语义零变化。健康轮面零波及:entry.mjs:68-72 roundType 缺省 "health"→readBudgetKnobs ¥30 不变;budget-parity 钉「独立键不入健康轮面」(OPS_DISCOVER=7 时 health 仍 30)。

**票面④「cron 时点」**:错峰算术对——健康窗 04:00+约35min=04:35 尾,06:00−04:35=85min ✓;发现轮自身墙钟帽 3600s 最坏 07:00 收,距 12:00 窗 5h,零并发面成立(生产台账/queue/SQLite 全部时序串行)。runbook §已切流补 cron 行+错峰注+chmod 核对行(4 行恰为新增,master 无);ops-cron.md 补留档注。

**票面⑤「不动服务器」**:diff 仅 6 文件全仓内;`ops-cron-v2-discover` 引用面全查(deploy 文档/runbook/测试),无 CI/部署脚本残留。

**红线与门**:`ops/agent/pipeline/budget.mjs` worktree↔master 全文逐字节一致(全文比对);`ops/agent` 全树 grep 逐行同(pipeline.mjs:161/394、agent.mjs:167 等行号内容双检);v2 `budget.mjs` re-export 面未动。budget-guard 差额恰 +24−6(discover 分支换 readDiscoverKnobsV2 + 新函数 + admitRound 改写块,其余 admitRound 壳/knobNames/readAddKnob 族/四界纯函数全同 master)。测试账对:275 基线 + 6(新 cron 冻结面测试)+ 1(budget-parity 新 #367 测)= 282/281 过/1 skip,与门输出一致;`bash -n` 亦入测试。对拍测试新键不破旧值:旋钮对拍测试显式拆月帽键后对拍其余四键 + 缺省/覆写/独立面五断言 + 非法值同文案用法错;月帽对拍含等号放行(19.95+0.05=20.00≤20)、拒启界(20.01>20)、env 覆写 ¥7、健康面不受扰。

### 发现

- **P2-1(文档·回退面缺口)** `ops/agent-v2/SHADOW-RUNBOOK.md:87-92`:§回退路径只写健康轮「两行互换」,未提 #367 新增的 `0 6 * * *` discover 行在回退 v1 时须一并注释——漏摘则 v1 回退期间 v2 发现轮仍每日写生产台账/queue/轮目录,恰是本节自警的「双活」。本缺口由本 diff 造成(diff 前无第二行可漏)。最小修复:§回退路径补一句「回退同时注释 #367 discover 行」(一行)。
- **P2-2(仅报告·命名语义)** `OPS_DISCOVER_MONTHLY_CAP_CNY` 的裁决基数是台账当月**全部**轮次 Σcost+est(非发现轮专项花费)——票面明裁「台账口径不变」,budget-guard 注释已写明;但键名易误读为「发现轮专项帽」。运维推论值得知晓:月花费 ¥20–30 区间发现轮拒启而健康轮照跑;紧急收紧 `OPS_PIPELINE_MONTHLY_CAP_CNY` 不再约束 v2 发现轮(只认新键)。可选:runbook env 表补半句。

仅报告:
- agent-config.json 坏 JSON / python3 缺失会折叠进同一句「缺 model_discover」跳过留痕(成因归因不精确;行为=设计的 skip-exit-0,观察清单已有「跳过行另判因」项)。
- 回退期间 v1 发现轮(手触/API 面)仍走共享 ¥30 帽(旧 readDiscoverKnobs 红线不动)——v1/v2 发现轮帽语义在回退窗不同,与 P2-1 同读。
- `OPS_MODEL_DISCOVER` env 注入不被 v2 run-discover 消费(模型单源 --model);无害,合 #364 白名单判例。

### 合并结论：**通过，附带注意事项**

P2-1 建议随服务器装 cron 前的一行 runbook 补丁同批落地(装机动作本身是票面外的后续部署步骤);其余仅作报告记录，不阻塞。