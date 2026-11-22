---
id: 2026-10-24-discover-dual-channel-dead
date: 2026-10-24
subject: discover 轮通道设计 — 双通道全灭与失败面不可诊断(工具封装缺陷)
context: >
  2026-10-24 01:59 生产 discover 轮(glm-5.3-flash,in=6141 out=1048,
  cost ¥0.00178307):search_precedents×2 全 rc=2(旧容器/旧卷状态下
  PRECEDENTS_DIR 目标路径不存在,rg rc=2 伪装 infra 故障;当前容器实测
  已活,rc=0 七命中)、gh_search×2 全 rc≠0(镜像无 gh 二进制,#139 挂账
  坐实)。模型信封纪律正确履职:零编造、零 REJECT/ENQUEUE、全量升级
  人裁。但失败面不可诊断:tools.mjs search_precedents 的 trace 硬编码
  rc:0(失败路径也带装饰值)、lib.sh inject_precedents 吞 rg stderr
  (2>/dev/null)、gh_search 失败路径 rc 塞 ENOENT 字符串违反自身
  outputSchema Number 槽、错误无分类(缺装/鉴权/限流/暂态折叠一码)。
  事后只能靠活体容器状态倒推根因。
recommendation: >
  ①gh CLI+GH_TOKEN 烘焙进镜像(#139 提前收);②工具封装修复:trace 恒真
  (真 argv+真 rc Number)、错误分类学四码(channel_missing/channel_auth/
  quota/transient,每码带「下一步合法动作」文案,对齐 MCP 2026-07-28
  isError 语义)、判例检索 JS↔Python 单一语义源契约钉住;③跨轮通道熔断器
  (连续失败达阈开断→快速结构化 tool-unavailable 信封→半开探活恢复,状态
  持久化)——熔断器属宿主层,Formation 2026-09 四界论:circuit breaker
  的职责在环外,不靠模型自己停止重试。
human_ruling: >
  2026-10-24 用户全批裁决(四原则:最少关键围栏/定期目标对齐/token
  效果优先/工具封装完美):gh 烘焙+封装修复+熔断器全数采纳,即日实施
  (工具通道修复批);agent-reach 整只打包方案降级为原生薄工具四件套
  (gh_search/web_read/web_search[s.jina.ai 需 JINA_API_KEY,2026 起
  无 key 直接 401]/rss_parse)。
reward:
  hard_gates:
    channels_dead: "2/2"
    tool_calls_failed: "4/4"
    wasted_cost_cny: "0.00178307"
    wasted_retries: "4"
  ruling_agreement: agreed
  production_delta: null
lineage:
  - 生产轮包 ops/packages/2026-10-24-discover-0159.md(服务器 ops 树)
  - 生产台账 2026-10-24 discover 行(ledger.md;in=6141/out=1048/cost=0.00178307)
  - 2026-10-24 用户裁决会话(grill-with-docs;判例检索两连败信封 call_0601b190/call_3f799144)
  - "PR #TBD(工具通道修复批,合并后补号)"
superseded_by: null
---

# 判例:通道单点全灭可以再修,失败面不可诊断不可再犯

01:59 轮的教训不是「工具会坏」——工具一定会坏(旧容器态、缺装、限流
都是常态)——而是「坏了以后,信封里找不到真相」。装饰性 trace(恒
rc:0)与吞 stderr 让一次五分钟可定位的基础设施故障,变成了要活体容器
倒推的考古题。错误分类学的意义:四码各自映射不同的下一步(缺装→人裁区
注明/鉴权→人裁配 key/限流→退避或弃/暂态→重试一次),模型拿到哪码就
知道走哪条路——即 MCP「错误消息要写清合法值长什么样」的语义。熔断器
是同因的系统性解:通道死是持久态,重试预算(暂态 ≤1)挡不住它烧钱,
01:59 那 2×2 连败重试本不该发生,只有环外的断路器能拦。反向对照:信封
纪律(宁空勿编、rc=2≠零命中、无实测不裁决)当轮正确履职,零编造零
误裁——围栏可以少,这一类要保。

检索词:discover 通道 gh rc 信封 熔断 错误分类 channel_missing
channel_auth quota transient 装饰性 trace 工具封装 基础设施故障
不可诊断 重试白烧 GH_TOKEN 镜像 缺装
