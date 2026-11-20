# SHADOW-RUNBOOK.md — shadow 期运行手册(票 #229 T5 任务书④)

spec 定案 2 安全轨的运维面:旧管线原地不动,v2 在 `ops/agent-v2/` shadow 跑满一月轮周期,golden + 新旧产出对拍一致才切流。**切流时点由用户裁决,本手册不自动切。**

影子轮工件根(导航,2026-11-15 retro 立):服务器容器 `/app/data/ops-shadow/docs/ops/`——轮工件 `rounds/<id>-health/`(含 `05-deep-*-transcript.jsonl`)、轮末 retro 件 `retro/`、台账 `ledger.md` 与判例/条目库同根;注意双层 `docs/ops/` 嵌套易摸错(当日三轮探查实测)。

## 观察面(每轮 cron 后)

```bash
# 对拍闸门(罐装世界,零网络,~1min):旧 replay vs v2 checkpoint 任务
node ops/agent-v2/shadow-diff.mjs <YYYY-MM-DD-HHMM-health>   # 退出 0=全 SAME
# 全量测试套(52 测/51 绿+1 设计 SKIP,含 parity + cron-launchers + E2E + SIGKILL resume + 重试/跨库/exit 码面 + golden 三面)
cd ops/agent-v2 && node --test 'tests/*.test.mjs'
```

双轨 cron 形态(shadow 期):旧 `pipeline.mjs` cron 照跑(生产真源);v2 侧双轮型——健康轮 `run-health.mjs` 每日一轮、发现轮 `run-discover.mjs` 按旧发现轮节拍(周频/手触),各 `--db` 独库(缺省 `docs/ops/agent-v2.sqlite`),轮 id 独立命名,台账/queue 各自世界——**shadow 期 v2 不写生产台账与 queue、不进生产轮目录**。操作面差异:发现轮 real 面强制 `--model provider/modelId` 显式(旧管线自动 resolve;模型清单见 models.mjs),健康轮缺省自动 resolve 同旧。

## SAME 门槛

- `shadow-diff.mjs` 退出 0(可比工件闭集 + 台账行,归一化窄面见其头注)。
- 全量测试套 52 测 51 绿 + 1 设计 SKIP(smoke 凭证门)。
- **golden 对拍(#232 已收口,切流硬门槛)**:管线面 2/2 字节级一致对拍(`pipeline_health_full_faux`+`pipeline_discover_full_faux`,tests/golden-health-parity/golden-discover-parity,归一化窄面同 shadow-diff)+ legacy 判断器 8 例回归钉(golden-judge-regression:判断器例驱动 legacy agent.mjs runRound 面,spec T3 明示不迁 v2——钉的是 v2 依赖世界保持 GOLDENPASS,非管线对拍;切流删旧时随 legacy 面退役)+ smoke 例凭证门(golden-smoke-gated:选层门恒钉,OLD 面双门手跑,NEW=N/A)。
- 连续一个完整月轮周期内:零 infra 结果单(v2 侧)、零对拍 DIFF、SIGKILL/断电恢复演练至少一次通过(`tests/resume.test.mjs` + 人工 kill 面板)。

## 已知差异面(声明,非缺陷)

| 差异 | 性质 | 处置 |
|---|---|---|
| v2 健康轮无 state.json(真源=SQLite checkpoint+工件;仅发现轮落 state.json 兼容旧面) | 实现细节 | 不入对拍面 |
| `.v2-claim.json`(v2 健康轮轮目录认领件;跨库撞轮守卫) | v2 专属守卫落件 | 不入对拍面(shadow-diff NEW 侧白名单已列入) |
| 09-budget.json 旧 CLOSE 也落件(非 v2 专属);真实差异=对拍载具双侧停笔 RETRO 故均不落 | 载具结构 | CLOSE 面落件由 `tests/cron-launchers.test.mjs` 钉(09-budget 存在性断言) |
| 台账 usage 计数(in/out/total)计量边界差 | 两套 harness 合法差 | 对拍归一;cost 细胞逐字比(ENVELOPE.md §usage) |
| RETRO 件 mutation_check_due 提醒行(#352 票尾,ADR 0021 决策6):v2 健康轮 RETRO 工件补变异自检月度到期读数(上次时间取月轮报告根 monthly/model/ 质量报告件,31 天窗;只测量不持门) | v2 面新增字段,旧管线零改动 | 不入对拍闭集(retro 件不在 COMPARABLE 面);钉住面=tests/mutation-due.test.mjs + health-e2e 断言 |
| 对拍载具停笔 RETRO(旧 replay 不入 CLOSE) | 载具结构 | CLOSE 面由 `tests/cron-launchers.test.mjs` 钉(G_CLOSE/09-budget/结果单) |
| PROBE/VERIFY 不入罐装对拍(真探测面,零网络红线) | 载具结构 | 两侧均为零复制 `steps.runStage` 同码路;生产 v2 轮真跑 |

## 影子世界置备(shadow 期轮跑前置)

shadow 期 v2 侧 `DOCS_ROOT` 指影子根(与生产 `docs/ops` 分置),防误指生产写脏。置备=从生产 rsync 一份再清轮次状态:

```bash
mkdir -p <影子根>/docs && rsync -a docs/ops/ <影子根>/docs/ops/
rm -rf <影子根>/docs/ops/rounds/ <影子根>/docs/ops/ledger.md <影子根>/docs/ops/queue.md  # 轮次目录/台账/队列清空——v2 侧从零起卷
# precedents/ rules/ items/ 保留(判例/规则/条目库是轮次输入面,随卷携带)
```

v2 侧 cron 起轮时显式带 `DOCS_ROOT=<影子根>/docs`(与 `--db` 影子库同理);指向生产根属配置事故——认领件/台账/queue 会写脏生产树。

## 回退

v2 无生产流量 → 回退=停 v2 cron 即可,零数据迁移。SQLite 库/轮目录留在原地供事后审计(证据永不灭失)。

## 切流(用户裁决后)

1. 前置:上表 SAME 门槛全满足,用户明示切流;另三件
   ①满月零 infra(影子起始 2026-10-28,至 2026-11-28 到期);
   ②人工 SIGKILL 演练(容器被杀后影子自意恢复);
   ③model_face 失败定性收口:4 起已定性同根=DEEP 终答 JSON 后尾随散文遭严格 parse 误杀(#355,2026-11-15 侦察);修不修、修后观察窗,以 #355 票面人裁为准。
2. 切换 cron:旧 `pipeline.mjs` cron 下线,`run-health.mjs` 接同一轮 id 序列与生产台账世界(`DOCS_ROOT`/`LEDGER_FILE` 指生产)。
3. 首两周双观察:v2 结果单/台账行抽查 + 月度准入读数对拍(月帽口径 ENVELOPE.md)。
4. 观察期满后旧管线代码退役(单独 PR,先归档后删)。

## 已切流(#364;2026-11-20 用户裁「把他转正」)

切流实现件 = `deploy/ops-cron-v2.sh`(v2 run-health 直跑生产世界;cron 脚本冻结面钉在 `tests/ops-cron-v2.test.mjs`)。旧 v1 API 触发形(deploy/ops-cron.sh,POST /api/ops/rounds)从 crontab 下线留档;**ops/agent 代码不删**——退役=后续单独 PR(先归档后删)。日历条件豁免:#355 十轮窗(修复 11-18 部署后全绿,残响不算新 infra)与满月 11-28,用户已明示豁免,以 SAME 记分板其余三项全绿为准。

### 服务器 crontab 变更(部署段动作;本节=操作单,非仓内动作)

```cron
# 旧 v1 行注释留档(回退=去掉行首注释即恢复);/root/.ops-cron-env 随之闲置留档:
# 0 4-23/8 * * * . /root/.ops-cron-env && /opt/ip-lookup-tool/deploy/ops-cron.sh >> /var/log/ipradar-ops-cron.log 2>&1
0 4-23/8 * * * /opt/ip-lookup-tool/deploy/ops-cron-v2.sh >> /var/log/ipradar-ops-cron.log 2>&1
# 影子 cron 停用(切流后 v2 即生产,对拍失对象;shadow-diff.mjs 留仓供审计):
# 40 4-23/8 * * * /opt/ip-lookup-tool/deploy/ops-shadow-cron.sh >> /var/log/ipradar-ops-shadow.log 2>&1
```

- 日志沿用 `/var/log/ipradar-ops-cron.log`(行前缀 `ops-cron-v2:` 与 v1 `ops-cron:` 可辨;回退换行零日志迁移)。
- 轮 id 序列:脚本取容器 UTC 墙钟(v1 pipeline.mjs mkCtx 同钟),宿主 `0 4-23/8`(04/12/20 本地时=03/11/19 UTC)自然接续生产既有序列,零迁移。
- 装机后核对 `chmod +x /opt/ip-lookup-tool/deploy/ops-cron-v2.sh`(git 已带执行位;同 ops-cron.md 部署清单「chmod +x」判例)。

### 回退路径(cron 面单点)

crontab 换回旧行(去掉上行注释)即恢复 v1 生产:后端 API 触发形连生产台账/轮目录续跑,零数据迁移。v2 侧停跑即退——SQLite/轮目录原地留档供事后审计(证据永不灭失);影子对拍工具(shadow-diff.mjs)留仓,可对 v1/v2 历史轮做审计对拍。回退演练验收(票面):换回旧行后下窗 v1 轮正常起,生产台账/queue 恢复 v1 写。

### 切流后 env 面逐键白名单(#364 裁定 2026-11-20;「逐键白名单,不笼统同环境」判例)

| 键 | 值 | 出处 |
|---|---|---|
| DOCS_ROOT | /app/data(=生产 ops 根 /app/data/ops 的父;v1 桥 _round_env `str(root.parent)` 同律) | 生产世界接线 |
| OPS_AUTH | /app/data/ops/auth.json(只读消费;预检缺件=跳过 exit 0 下窗自愈,旧 409 判例直跑形) | 凭证面同 shadow |
| OPS_EVAL_PY / OPS_DATA_DIR | 容器 python3 / /app/data | 桥 _round_env 同源两键(shared.mjs 加载期常量,缺省指开发机路径) |
| PI_CODING_AGENT_DIR | /app/data/ops | v1 桥同键(pi-web-access 读 web-search.json 的 jina 路由面) |
| LANG | C.UTF-8 | C4 判例(bash 面 locale 确定性) |
| OPS_MODEL_HEALTH / OPS_MODEL_DISCOVER | agent-config.json 现读注入 | v1 桥同源;缺配置不注入 |
| unset | IP_RADAR_ADMIN_PASSWORD、IP_RADAR_API_JWT_SECRET | C4 管理密钥摘除 |
| 继承不摘 | GH_TOKEN、IP_RADAR_ALERT_URLS | finding 出口契约员(gh issue + webhook);**透传范围=v2 健康轮子进程,与 v1 后端 C4 白名单 _SPAWN_ENV_EXACT 面一致,非新增暴露** |
| 不设 | OPS_SWEEP_DRY_RUN | 生产语义=finding 出口真开;影子零外发栈(dry-run+GH_TOKEN/ALERT_URLS 摘除)整体随切流拆除 |

### 首两周双观察清单(票面;期满转月度例行)

每窗(或每日抽一窗):

- [ ] `tail /var/log/ipradar-ops-cron.log`:v2 行在位、退出码 0(1=failed/refused/parked 需复盘当窗结果单);缺件跳过行需另判因(auth.json 为何未物化)
- [ ] 结果单/台账行抽查:容器内 /app/data/ops/rounds/<id>-health/ 信封 ok=true;ledger.md 新行形状 `| 日期 | health | … | pipeline:<round_id> |`(月度准入消费面,ENVELOPE.md)
- [ ] 轮 id 序列接续(UTC 03xx/11xx/19xx 形,无跳号/撞号)
- [ ] finding 出口面:08-anchor-sweep-exits.json 出口态——findings=0 → skip 合法;finding>0 → gh issue/webhook 真发,失败信封留痕交人裁(出口永不败轮)
- [ ] 旧管线零写:ops/agent 无新轮目录(v1 API 触发形已下线;发现轮手触面不变)

月度:

- [ ] 月度准入读数对拍:monthSpendOfLedgerText 口径的台账 cost 列合计 vs 月帽(ENVELOPE.md §usage;v1/v2 计量边界差已声明,对拍以 cost 细胞为准)
- [ ] 影子残件:/app/data/ops-shadow 留档不增轮(影子 cron 已停;若增轮=crontab 回退不彻底)

### 切流验收(部署后逐项,票面三断言)

1. 首轮生产轮信封 ok=true,轮 id 序列接续生产(UTC 形);2. 生产台账/queue 由 v2 写、旧管线零写;3. 回退演练=换回旧行下窗 v1 正常起。

## 实际接线(2026-10-28 置备;小机 203.88.124.85)

- v2 宿 = 生产容器 `ip-lookup-tool-ipradar-1`(node 22.23.4,Dockerfile `opsagent-v2` 层烘焙依赖)。env 面逐键白名单(不笼统说「同环境」):`DOCS_ROOT=<影子根>/docs`、`OPS_AUTH=/app/data/ops/auth.json`(生产件只读)、`OPS_EVAL_PY`/`OPS_DATA_DIR`(桥 _round_env 同源两键,shared.mjs 加载期常量,容器内不物化必死 PROBE)、`OPS_SWEEP_DRY_RUN=1`(影子零外发)、`OPS_MODEL_HEALTH`/`OPS_MODEL_DISCOVER`(agent-config.json 现读,缺配置不注)、`LANG=C.UTF-8`;并 `unset IP_RADAR_ADMIN_PASSWORD IP_RADAR_API_JWT_SECRET IP_RADAR_ALERT_URLS GH_TOKEN`(docker exec 继承容器全量 env,管理密钥不带进模型进程;GH_TOKEN 摘除=gh 出口双保险)。
- 影子世界 = 容器内 `/app/data/ops-shadow`(`ipradar-data` 卷内,随卷持久):`docs/` 影子 ops 树(首跑由 `deploy/ops-shadow-cron.sh` 自种,幂等:种入 `docs/ops.tmp` 后 `mv` 终位,同卷 rename 原子,中断不留半树;种子剔除 rounds/、ledger.md、ledger.md.lock、queue.md、auth.json、web-search.json、agent-config.json——影子从零起卷、种子零密钥)+ `docs/ops/agent-v2.sqlite`(缺省落位,DOCS_ROOT 推导)。
- cron(小机 root):`40 4-23/8 * * * /opt/ip-lookup-tool/deploy/ops-shadow-cron.sh >> /var/log/ipradar-ops-shadow.log 2>&1`——旧轮 04/12/20 整点,v2 错峰 40 分(旧轮墙钟帽 1800s 恰 30 分,+30 仍可能踩旧轮尾巴,退到 40);发现轮 shadow=手触(旧发现轮无 cron,同节拍)。**已切流后停用(见 §已切流)。**
- 凭证:只读消费生产物化件 `/app/data/ops/auth.json`(OPS_AUTH;exec 前预检,未物化=打一行明确 skip 退出 0,下窗自愈,同旧 ops-cron 409 跳过判例);模型引用从 `agent-config.json` 现读注入。breaker.json 随影子世界自种(跨轮输入面);影子台账从零起卷,月帽独立于生产。
- 观察面(每窗人工/例行):`tail /var/log/ipradar-ops-shadow.log` 结果单行;对拍闸门与本节以上 SAME 门槛不变。

### 部署验收清单(装 cron 后逐项过)

1. `crontab -l` 核对:`40 4-23/8 * * *` 行在位,脚本路径与日志重定向同上条。
2. 手动跑一轮:直接执行 `/opt/ip-lookup-tool/deploy/ops-shadow-cron.sh`;核日志结果单行 + 容器内影子树落件(`ls /app/data/ops-shadow/docs/ops`:precedents/items/rules/breaker.json 在,rounds/ledger.md/auth.json/web-search.json/agent-config.json 无)。
3. 人为制造失败核退出码链:如 `OPS_SHADOW_CONTAINER=不存在的容器名` 跑一次;确认日志出现「v2 健康轮退出码 N」行且 N≠0、脚本退出码同为 N(rc 透传,结果单语义 ENVELOPE.md)。
4. 生产面零写确认:跑轮前后容器内 `git -C /app status --porcelain -- backend/ frontend/` 为空,且生产 `/app/data/ops` 树(`ledger.md`/`rounds/`/`queue.md`)内容不变——影子轮不写生产面。
