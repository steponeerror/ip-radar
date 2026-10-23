# WORKER-REPORT — extract_feed_urls 事实层重构(feeds.txt 清单)

分支 feature/ops-feed-manifest(基于 origin/master ed4fc2e0),commits:45697d93 + 本报告。

## 清单最终条数
**97 条**(旧 rg 扫描 78 → 97,全 https,sort -u 无重复)。逐条与 backend/ipdb/_sources/*.py
交叉核对:67 条字面量直存;30 条 base+文件名 f-string 按名核对(firehol ×4 / malicious_ip ×5 /
blocklist_de ×11 / cn_isp ×10 / rir_delegated ×5 等旧扫描**漏探**真端点,本次全数补入)。

## 删掉的历史混入 URL(旧清单实况比对实证)
- 首页:`https://dataplane.org/`(冻结 291 天伪报元凶)
- 截断形(多行拼接首行):GeoLite `…/latest/download/`、`raw.githubusercontent.com/
  CriticalPathSecurity/`、`DNSCrypt/dnscrypt-resolvers/`(含 docstring `…/master/v3/`)、
  `ShadowWhisperer/IPs/`、`drb-ra/`、`f3cSystems/`、`mthcht/…/main/`、`ziyadnz/`、
  `rules.emergingthreats.net/`
- 裸 base:`lists.blocklist.de/lists`、`ispip.clang.cn`、firehol/malicious-ip base
- 文档/许可证页:`docs.abuseipdb.com`、`creativecommons.org`、`caida.org/catalog`、
  `github.com/proxyscrape`
- 目录形:RIR 五个 stats 目录、裸 `peeringdb.com/api`(真端点=/ix、/ixpfx)
- 清单头另录**刻意不收录**及理由:threatfox/urlhaus v2/files/exports(Auth-Key 路径段,
  匿名 404 必伪报)、dbip_city 月滚 URL、ip2proxy/ipinfo {} 模板、cloud_ranges 微软确认页、
  infra_services 内嵌无抓取。
## 改动与新增检查
- `ops/agent/feeds.txt`(新):分组头 + 行内 `# <source_name>` 标源 + 维护契约
  (新增/改源端点 = 同 PR 更新清单)。
- `ops/agent/lib.sh`:extract_feed_urls 改 `grep -v '^#' | awk 'NF{print $1}' | sort -u`
  读清单;rg 扫描退役删除;签名与调用方零改动(tools.mjs:345 无参调用不变)。
- `ops/agent/selftest.sh`:原断言全保留(≥50/https/binarydefense/无 {});新增
  **EFU_BASELINE=97 防漂移**(合法缩量须同 PR 显式下调)+ 三条事故形状不回流断言
  (dataplane 首页 / abuse.ch key 占位 / raw.githubusercontent 尾斜杠截断形);
  fixture 由源码目录扫描改为清单文件解析面(^# 注释行/行内 # 剥除/空行/首列)。
## 自测结果(判例:commit 后跑,沙箱干净态)
- `source ops/agent/lib.sh; extract_feed_urls | wc -l` → **97**;非 https=0;
  v2/files/exports、/account、confirmation、geolocation 形 = 0。
- `bash ops/agent/selftest.sh` 全量(node_modules 装后):**PASS=97 FAIL=0**
  (装依赖前 T4 六红 = worktree 无 node_modules 环境缺,与本改无关)。
- 本机外网受限(github 直连超时),未做端点活体探测——清单真伪以源码为据。
- 风险:清单是快照:源端点后续变更依赖「同 PR 更新清单」契约 + 基线断言兜底;
abuseipdb/otx_subscribed 无凭据探测得 TOKEN_REQUIRED 读数(设计内,非异常)。
