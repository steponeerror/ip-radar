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

## gh_search 通道凭证(GH_TOKEN;PR #177 工具通道修复)

判例 docs/ops/precedents/2026-10-24-discover-dual-channel-dead:生产 discover 轮
gh_search 双通道全灭,一面 = 容器无 gh(镜像面,已随 Dockerfile 装 CLI 修复);另一面
= 凭证缺失(gh 匿名撞鉴权墙)。凭证经 docker-compose.override.yml 的**映射式 env 段**
注入服务器(与 `IP_RADAR_REBUILD_SUBPROCESS` 同段;override 不入仓,与 Caddyfile 同
处置律):

```yaml
services:
  ipradar:
    environment:
      IP_RADAR_REBUILD_SUBPROCESS: "1"        # 既有行(同段示例)
      GH_TOKEN: "github_pat_<服务器本地秘密>"   # gh CLI 自读(tools.mjs 不读;契约表 GH_TOKEN 项豁免面)
```

- **粒度建议**:fine-grained PAT,只读 public 仓检索粒度(Repository access = Public
  repositories / 最小权限;`gh search` 面无需任何写权限与私仓授权)。凭证泄漏面控制:
  服务器本地 override chmod 600,永不入仓、永不入日志/台账/裁决包(提示词脱敏律;
  gh 失败信封只携带 stderr 摘要,不含令牌)。
- **失败面**:凭证缺失/失效 → `channel_auth` 分类信封(二进制缺装才归 channel_missing;tools.mjs
  classifyChannelError;文案自带下一步),模型侧直接人裁区不重试——修复属部署动作,
  勿轮内自纠。

## web_search 引擎与通道凭证(pi-web-access;PR3a 发现通道薄工具)

发现通道三件之一 web_search 已由 **pi-web-access**(2026-10-24 用户令「用
pi-web-access 实现网络搜索」,https://pi.dev/packages/pi-web-access;镜像内
pin 0.44.0,ops/agent/package.json + Dockerfile npm ci 自动带入)驱动:多 provider
网络搜索 + 智能回退链,**零配置一发即活**(缺省路由 keyless DuckDuckGo——正式
取代 Jina 充值前置)。工具契约面不变(归一 SERP/每轮预算/失败四码信封)。

### provider 路由(配置单源:web-search.json 物化)

桥侧 `_round_env` **每次 spawn 现读物化** ops 树 `web-search.json` +
`PI_CODING_AGENT_DIR` 指路(auth.json 同型判例):回退链
`duckduckgo(keyless,零配置)→ jina(可用性 = jinaApiKey/JINA_API_KEY,
充值/配置后自然入链)`;零配置 Exa MCP 需运行时拉起外部进程,不入链
(确定性优先,2026-10-24 裁定)。改完即生效,无需重启/重部署。

### jina key(可选,入回退链;agent-config tool_keys 扩槽)

UI 配置面属后续批,当前经 API 配(管理登录后,容器内回环):

```bash
curl -X PUT http://127.0.0.1:8000/api/ops/agent-config \
  -H 'content-type: application/json' -b /tmp/ops-cookie.$$ \
  -d '{"tool_keys": {"jina": "jina_<服务器本地秘密>"}}'
```

- **出参遮蔽**:GET/PUT 回显只 `{configured, tail4}`(沿 api_keys 面);完整 key
  永不回显、永不入错误消息/日志/台账/裁决包(1113 纪律;失败信封只携状态码
  /stderr 真因摘要,不含令牌)。值非空校验(空串 422);槽闭集 {"jina"}。
- **实测事实(2026-10-24,两行为勿写反)**:r.jina.ai(web_read)裸调用无
  Authorization 正常,带欠费 key 反 402——web_read 恒不带 key,无需配置;
  s.jina.ai(现作为 jina provider 经 pi-web-access)需 key:欠费 → quota 信封
  (账户面:充值或窗口恢复后自然可用,模型侧人裁区不重试),缺配不入链不报错。
- **部署段真网验(待办)**:web_read 一发(无 key 应通);web_search 一发
  (零配置 DDG 应活——已开发机预验一发;充值后再验 jina 入链)。

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
   注(#170 审 P2-3):真面轮 crash 后 boot 会自动 resume 缺工件步(有界:每轮一次/仅缺工件步/#167 三规则)——无人值守时可能再花少量真钱,预算门 0.05¥ 硬拦,知悉即可;
6. 生产段验收门(spec #161,部署后逐项收口,勿灭失):①P2 影子轮 N≥3(legacy 与 pipeline 并行,报告对照一致)②P3 三节报告影子对照 ③P4 剧本=人为停一个真源→条目经四键走查 ④首轮 RETRO 候选 ≥1 经采纳后下轮 VERIFY 生效(闭环)。
