# IP Radar

纯本地多源 IP 情报融合引擎:摄取→物化→查询→融合→裁决,输出带出处与置信度的 IP 画像。

## Language

### 证词与裁决

**指控章**:
源证词进入 P(恶意)后验计分的资格,verdict ∈ {malicious, suspicious}。全仓单一真源 `_types._ACCUSING`。
_Avoid_: 计票资格、威胁源

**资产弃权**:
源对某 IP 只陈述基础设施属性(proxy/hosting/tor),不构成滥用指控:verdict=""、不计票、不产 STIX Indicator,仅走 attributes 通道。判例:cloud_ranges(首创)、ip2proxy DCH(SM-F2)、ip2proxy VPN/PUB/TOR(grill 2026-10-12)。
_Avoid_: informational 源、降级

**行为源**:
以观测到的滥用行为(扫描/爆破/C2 回连/举报)立证的源,如 bruteforce、ciarm、abuseipdb。与资产属性源相对。
_Avoid_: 恶意源

**单源 conf=r 公理**:
融合层不变式:恰一个 reliability=r 的证人时,合成置信度恒等于 r(σ(logit(r))=r)。
_Avoid_: —

### 质量闸门

(词汇正源为 GLOSSARY.md;本节为 grill 会话工件,冲突时以 GLOSSARY 为准。)

**回放闸门**:
融合数学变更的强制对照实验:对生产数据镜像回放,判据 C2(单指控组分数退化恒等)/C3(benign 语料高分 IP 数不升)/C4(Spearman ρ 不降)。内部回归绊线,非产品承诺。
_Avoid_: eval 门
