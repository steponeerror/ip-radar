# ops 健康轮 cron 接线草案(P5 #167;安装=部署段,本文件只交草案+调用链文档)

触发链(C 稿 §5.1 定案;三小裁③:cron 首窗 **04:00 起错峰**——源更新凌晨 rebuild 高峰
不与健康轮抢车道):

```
宿主 crontab(0 4-23/8 * * *  →  04:00 / 12:00 / 20:00)
  → deploy/ops-cron.sh(下文草案;docker exec 进容器,127.0.0.1:8000 回环)
    ① POST /api/auth/jwt/login(表单式 username/password,204 拿 ipradar_admin cookie)
    ② POST /api/ops/rounds {"type":"health","input":"cron 8h 节奏健康轮"}
       - 202(task_id)→ 完;进度 = 驾驶舱 SSE(/api/events task/task_log 事件,
         stderr [stage] 行透传,P5 #167 已核)
       - 409 eval_busy(车道占用)→ 退出码 0 + 跳过行写日志(**不排队**——健康快照
         无回填意义,下个 8h 窗口自然重来,C 稿 §5.1)
       - 其余非 2xx → 退出码非 0(日志行可见,不静默)
  → POST /api/ops/rounds → manager.start_ops_round 串行车道 → spawn(agent.mjs)
  → OPS_PIPELINE 灰度开关(见下)选路径
```

## crontab 行草案(宿主 root)

```cron
# ipradar ops 健康轮(P5 #167):04:00/12:00/20:00 错峰;登录凭据在 /root/.ops-cron-env(chmod 600,不入仓)
0 4-23/8 * * * . /root/.ops-cron-env && /opt/ip-lookup-tool/deploy/ops-cron.sh >> /var/log/ipradar-ops-cron.log 2>&1
```

`/root/.ops-cron-env` 内容形状(值=服务器本地秘密,绝不入仓;与 Caddyfile/
docker-compose.override.yml 同一处置律):

```sh
export OPS_CRON_EMAIL="ipradar_admin"
export OPS_CRON_PASSWORD="<服务器本地设置>"
```

## 调用脚本草案(deploy/ops-cron.sh;部署段落位后 chmod +x)

```sh
#!/usr/bin/env bash
# ops 健康轮 cron 触发(P5 #167 草案;只触发不拥有状态——车道/预算/同型在飞
# 门在 POST /api/ops/rounds 服务端,cron 侧不重实现)。409=跳过留痕退出码 0。
set -u
CONTAINER="${OPS_CRON_CONTAINER:-ip-lookup-tool-ipradar-1}"
: "${OPS_CRON_EMAIL:?需 /root/.ops-cron-env 提供 OPS_CRON_EMAIL}"
: "${OPS_CRON_PASSWORD:?需 /root/.ops-cron-env 提供 OPS_CRON_PASSWORD}"
echo "[$(date -Is)] ops-cron: 触发健康轮"
JAR=/tmp/ops-cron-cookie.$$; trap 'rm -f "$JAR"' EXIT
# ① 管理登录(表单式;204 + Set-Cookie ipradar_admin;判例=2026-10-23 #160 部署验收)
docker exec "$CONTAINER" curl -sS -o /dev/null -w '%{http_code}' \
  -c /tmp/ops-cookie.$$ -X POST http://127.0.0.1:8000/api/auth/jwt/login \
  -H 'content-type: application/x-www-form-urlencoded' \
  --data-urlencode "username=$OPS_CRON_EMAIL" \
  --data-urlencode "password=$OPS_CRON_PASSWORD" > /tmp/ops-login.$$ 2>/dev/null
# 注:cookie 落容器内 /tmp/ops-cookie.$$(容器内续用);JAR 变量为宿主清理占位
code=$(docker exec "$CONTAINER" curl -sS -o /tmp/ops-body.$$ -w '%{http_code}' \
  -b /tmp/ops-cookie.$$ -X POST http://127.0.0.1:8000/api/ops/rounds \
  -H 'content-type: application/json' \
  -d '{"type":"health","input":"cron 8h 节奏健康轮(P5 #167)"}')
case "$code" in
  202) echo "[$(date -Is)] ops-cron: 已受理 $(docker exec "$CONTAINER" cat /tmp/ops-body.$$ 2>/dev/null)"; exit 0 ;;
  409) echo "[$(date -Is)] ops-cron: 车道占用(eval_busy),本轮跳过(不排队,下窗自然重来)"; exit 0 ;;
  *)   echo "[$(date -Is)] ops-cron: 非预期状态码 $code $(docker exec "$CONTAINER" cat /tmp/ops-body.$$ 2>/dev/null)"; exit 1 ;;
esac
```

(草案形状注:登录与触发两跳均在容器内回环完成——凭据不出容器网络面;脚本细节
容器内 /tmp/ops-cookie.$$ 与 /tmp/ops-body.$$ 用毕即删(curl --next 或 && rm;部署段实测定稿)。
如 cookie 传递在部署段实测定稿,以「登录 → 带 cookie POST → 409 即零成本跳过」
三断言为验收面。)

## FROZEN 鉴权矩阵核对(新触发源登记)

- cron 是**新触发源**,不是新路由:走既有 `POST /api/ops/rounds`
  (`_ADMIN_DEPS` = require_admin_configured + current_superuser 超管 cookie 面,
  FROZEN 矩阵零变更,**无需任何路由改动**——本票未实施也不需实施路由变更)。
- 登录凭据 = 既有 admin 账号(ipradar_admin);建议部署段为 cron 单独建只用于
  触发的超管账号或复用现有,秘密只落服务器本地 env 文件。
- 回环(容器内 127.0.0.1)+ `IP_RADAR_PUBLIC_DEMO=1` 演示守卫互不干扰
  (守卫只作用于匿名公网面;已登录 cookie 走真实鉴权依赖)。

## OPS_PIPELINE 灰度开关(与 cron 接线同一部署面)

- 容器 env `OPS_PIPELINE=pipeline`(docker-compose.override.yml)→ agent.mjs 对
  health 轮委派 pipeline.mjs 状态机路径(P5 #167 接线);discover 恒 legacy。
- 模型步面(#170):生产/cron 轮(无 `--fixtures`)真 provider——TRIAGE/SYNTH=
  `OPS_MODEL_HEALTH`(缺省 glm-5.3-flash),DEEP=`OPS_MODEL_DISCOVER`(缺省 glm-5.3);
  手测/重放带 `--fixtures` 则 faux 零成本(重放缺省继承原件面)。真面 DEEP 微探针
  工具=下票(工具面空,深验 verdict 预期 unresolved 占比高,见 GLOSSARY「微探针」)。
- 回滚 = 去掉该 env(缺省 legacy);boot 恢复扫描独立于此开关(state.json 只属于
  pipeline 轮;遗留 in_flight 轮的恢复仍走 pipeline.mjs resume,把已开的轮跑完)。
- 切换验收:驾驶舱 SSE 可见 `[stage] PROBE start` 行族 + 信封 `pipeline.stages`。

## 部署段清单(本票不做,登记待办)

1. 服务器落 `/root/.ops-cron-env`(chmod 600)+ `deploy/ops-cron.sh`(chmod +x);
2. crontab 安装上文行(先手动 dry 一轮验证 202/409 两态);
3. docker-compose.override.yml 增 `OPS_PIPELINE=pipeline`(灰度,待用户裁)。**前置条件更新(#170):真 provider 已接线落地(fixtures 面=faux/运行面=真调用 flash+glm-5.3,预算三闸真面同执法,选择逻辑纯函数+零网络单测)——原「模型步无条件 fauxProvider」禁令解除;剩余前置=生产段真 provider 冒烟一轮(A 一律/门全过+预算门实测数字入台账)+用户裁**(另注:真面 DEEP 微探针工具=下票,真面深验 confirmed/refuted 不可立证——verdict 预期 unresolved 占比高,GLOSSARY「微探针」缺口注记);
4. `/var/log/ipradar-ops-cron.log` 轮转(logrotate 或按大小截断);
5. (可选)生产 ops 树种子 `rules/suppressions.json`:拷 docs 仓规则件或空库 `{"version":0,"rules":[]}`。注:缺席=合法零规则态(与 _ops_review 同口径;首轮 VERIFY 零抑制照常过,首条规则经 RETRO 候选→四键采纳自动建形)——种子仅为带 R12/R7 起步,非必需(审后修 P1 改口径后死锁已除);
6. 生产段验收门(spec #161,部署后逐项收口,勿灭失):①P2 影子轮 N≥3(legacy 与 pipeline 并行,报告对照一致)②P3 三节报告影子对照 ③P4 剧本=人为停一个真源→条目经四键走查 ④首轮 RETRO 候选 ≥1 经采纳后下轮 VERIFY 生效(闭环)。
