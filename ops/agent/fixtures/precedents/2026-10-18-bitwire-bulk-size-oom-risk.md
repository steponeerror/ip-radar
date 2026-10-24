---
id: 2026-10-18-bitwire-bulk-size-oom-risk
date: 2026-10-18
subject: 体量门 — 二阶聚合大源不整收(OOM 风险 + 谱系污染)
context: >
  bitwire-it/ipblocklist inbound 4,580,659 键(2h 更),数据 CC BY-NC-SA 4.0
  (README License 节,代码 MIT;扫编表初版误记 MIT 已正),排他 48.3%;
  波 1+队列候选全落后复算 31%——真增量 = 尾巴 ~16 小一手源。小机 964MB RAM:
  大源 rebuild 曾触发宿主全局 OOM(每 ~94min 杀容器一次)。
recommendation: >
  不整收(二阶聚合 + 4.58M 键体量 OOM 风险 + NC-SA;真增量在尾巴小源,
  按需单独直接收保谱系干净;尾巴源记档为下轮 discover 候选)。
human_ruling: >
  用户简报将 bitware-it 列入 tails 轮预出局名单未碰(2026-10-19);
  尾巴 16 小源按档直接调查(dossier §预出局名单)。
reward:
  hard_gates:
    keys_inbound: 4580659
    exclusive_rate: "48.3%"
    exclusive_after_wave1_replay: "31%"
    host_ram_mb: 964
  ruling_agreement: agreed
  production_delta: null
lineage:
  - docs/research/2026-10-18-blocklist-sweep.md
  - docs/research/2026-10-19-tails-discover.md
superseded_by: null
---

# 判例:二阶聚合体量炸弹 — 增量在尾巴一手源

整收二阶聚合大源双输:小机 OOM 判例 + 谱系被聚合器染色。正确姿势 = 找出其
独有尾巴一手源直接收(谱系逐行可声明)。注意百万键级接入本身可行
(malicious_ip 1,021,274 键实测峰值仅 +90MB,子进程车道),但前提是
独有增量归属清晰;bitwire 拒的是「二阶 + 增量稀释」,不是单纯键数。
