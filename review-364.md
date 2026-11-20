核实完毕。所有关键面(轮 id 钟、env 桥、退出码链、测试织法、runbook 操作单)都已对到源码,汇总评审报告。

## Review — PR #365(feat/364-cutover @ dee556ee,票 #364)

**结论:PASS-with-notes。P0/P1 零;P2 ×2(均文档/操作单层面);report-only ×3。**

范围声明:单 commit 范围以任务书预附的 `git show --stat` 为准(watchdog_diff 不含已提交区间);四件改动文件均在 worktree 逐行读过;门命令未重跑(reviewer 无 shell),采信预附尾部输出(275/274/0 fail/1 skip,基线 +5 全绿)。

### Correct(已核实正确的面)

- **票面五条逐条对齐**:①接生产世界——`deploy/ops-cron-v2.sh:58` `export DOCS_ROOT="$(dirname "$OPS")"` = `/app/data`,与 v1 桥 `_round_env` 的 `str(root.parent)` 同律(backend/ipdb/_ops_rounds.py:87);ops 树派生 `opsRootOf`(ops/agent-v2/round-ctx.mjs:14)→ `/app/data/ops`;SQLite 缺省 `DOCS_ROOT/ops/agent-v2.sqlite`(ops/agent-v2/entry.mjs:33-37 resolveDbPath)与头注一致;台账 resolveLedgerPath(tasks/budget-guard.mjs:60-62)落生产 ledger.md,月帽与 v1 历史共享。②crontab 操作单+回退路径落 runbook §已切流(SHADOW-RUNBOOK.md:63-116),未动服务器。③影子 cron 停用(crontab 块内注释行 :74)+ shadow-diff.mjs/ops-shadow-cron.sh 留仓。④首两周双观察清单(:99-112,每窗+月度)。⑤退役明确不在本票(ops/agent 不删)。
- **supervisor 裁定四条全落实**(ops-cron-v2.sh:67 unset 仅两管理密钥;:64 PI_CODING_AGENT_DIR=$OPS;不设 OPS_SWEEP_DRY_RUN;GH_TOKEN/IP_RADAR_ALERT_URLS 走 docker exec 继承——与 `_SPAWN_ENV_EXACT` 同面(backend/ipdb/_ops_rounds.py:152-155 两键均在白名单),finding 出口真读方 = v1 pipeline/finding-exit.mjs(v2 健康轮经 tasks/health-round.mjs 零复制调 v1 steps,steps.mjs:475 接线),无 dry-run=出口真开,runbook :96 的「非新增暴露」措辞成立。
- **轮 id 序列接续**:v1 `roundIdNow` 用容器本地钟(ops/agent/pipeline.mjs:138-139);镜像/compose 全文无 TZ(Debian slim 缺省 UTC)→ 容器本地=UTC;v2 取容器内 `date -u`(ops-cron-v2.sh:70),同钟同族;形状过 run-health.mjs:39 的正则;03/11/19 UTC ↔ 04/12/20 本地(UTC+1)与既有判例「线上 10-25-1900 健康轮」(backend/tests/test_ops_rounds.py:524 注)口径自洽。验收清单里有「无跳号/撞号」断言兜底。
- **判例保留**:%q 转义(:37,同 shadow 形);rc 透传「先跑后取」(:72-75,无 `if !` 取反坑);`set -e` 下 `[ -n ] && export` 惯用形安全(shadow 期同款跑满月)。
- **测试 5 例质量**:mock docker 剥 exec 头真执行内层 sh -c + stub node 录终态 env/argv——wrapper→docker exec→内层→node 全链行为面;钉住预检跳过(exit 0/留痕/零 node 面/恰一次 docker)、env 白名单三方向(set 逐键、unset 两键、继承两键、零 dry-run、缺配置不注入 OPS_MODEL_DISCOVER)、容器名 override、rc 1 与 127 双透传。与 cron-launchers.test.mjs 同律。
- **两世界不互扰**:v1 boot 恢复扫描 `if not d.is_dir() … state.json` 跳过 v2 轮目录(backend/ipdb/_ops_rounds.py:322-325);agent-v2.sqlite 落 ops 根非 rounds/,无扫描面误读。
- **首轮三断言可机检**:信封行落 cron 日志可 grep;v2 轮目录内 `.v2-claim.json`(v2 专属件)可作「由 v2 写」的判别标记;回退演练=换行后下窗看 state.json 形轮目录。

### Finding

- **P2-1**(文档)SHADOW-RUNBOOK.md:3-5 文首框架停留在 shadow 期现在时(「旧管线原地不动…本手册不自动切」);§影子世界置备(:37-45)的「指向生产根属配置事故」与新脚本指生产构成表面张力——历史段虽自我限定 shadow 期,但缺文首总指针。最小修:文首加一行「2026-11-20 已切流(#364),现行生产形见 §已切流」。
- **P2-2**(操作单)车道 seam:旧 409 eval_busy 只护 API 面,ops-cron-v2.sh:26-27 把它映射到「auth.json 缺位跳过」后,**在飞 v1 轮不再有对应物**——生产发现轮仍走 v1 API(周频手触,「发现轮手触面不变」),若与 v2 健康轮窗(≤30min 帽)重叠即两写面并发共享 ledger/items/breaker(ledger/queue 有 flock,items/breaker 无跨进程守卫)。最小修(不写码):runbook §已切流补两行——①回退=两行互换(注释 v2 行+去注释 v1 行,勿双活);②手触 v1 发现轮避开本地 04/12/20 起约 35 分钟。
- **report-only-1**:auth.json/web-search.json 的物化只发生在 v1 桥 `_round_env` 每次 API spawn(backend/ipdb/_ops_rounds.py:106-127);v2 cron 只读现成件。发现轮周频仍在=周期性再物化在;但密钥轮换后若长期无任何 v1 spawn,现成件不刷新——「下窗自愈」的物化前提值得写进观察清单心智(现有「缺件跳过需另判因」条已半覆盖)。
- **report-only-2**:agent-config.json 坏 JSON/缺失 → `python3 … || true` 静默回落缺省模型链(ops-cron-v2.sh:53-54),v1 面(`_ops_config` 坏文件显式报错)更响;影子期同款行为已跑满月,可接受。
- **report-only-3**:回退依赖两件服务器本地留档(`/opt/ip-lookup-tool/deploy/ops-cron.sh` 手装件——仓内 deploy/ 从未有此文件,形参照=ops-cron.md 草案留档注——加 `/root/.ops-cron-env`);清理服务器时勿删。

### Merge verdict: **OK with notes**

P2 两项均为文档/操作单层面,不阻塞合并;建议部署切流前顺手落 P2-1 一行与 P2-2 两行(或记票尾/NEEDS 跟进)。

---

注:本会话无写盘工具,`review-364.md` 未能直接落 `.worktrees/cutover-364/`;上即完整评审报告,请由有写权限的一侧持久化。