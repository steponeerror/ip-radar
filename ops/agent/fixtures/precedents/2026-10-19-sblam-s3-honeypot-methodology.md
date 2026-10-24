---
id: 2026-10-19-sblam-s3-honeypot-methodology
date: 2026-10-19
subject: 接入关 S3 强制人裁 — 自有蜜罐传感器 OC 0.99 高读数的解释
context: >
  sblam(波兰 Sblam! 自有表单垃圾传感器黑名单)接入关 POSITIVE-VERIFIED 但
  1 强制人裁旗标 S3:OC=0.9908 ≥0.9 却未声明派生。事实面:sblam = 自有蜜罐
  传感器非聚合,改标 derived 是事实错误;排他实测 26.7%(80/300),1,137 键。
recommendation: >
  选项①接受现声明面(tier B 蜜罐主源,推荐——价值在 spam 轴第二证人 +
  26.7% 独特段);②改判派生降 r(不推荐,错标)。高 OC 读作探针集盲区
  (data_shield 波 2 判例同款:探针集从池构造,看不见池外段)。
human_ruling: >
  2026-10-19 用户按推荐①接受现声明面销账(honeypot_methodology=True,
  表单陷阱网络 = 蜜罐法,orchestrator 裁决;PR #128)。
reward:
  hard_gates:
    oc: 0.9908
    coverage_gain: 86
    false_positives: 0
    verdict_conflicts: 0
    exclusive_rate: "26.7%"
    exclusive_n: "80/300"
    keys: 1137
  ruling_agreement: agreed
  production_delta: null
lineage:
  - "PR #128"
  - docs/research/2026-10-19-tails-discover.md
superseded_by: null
---

# 判例:OC 高 + 非聚合自有传感器 → 探针集盲区,不为过 gate 改事实标

S3「OC ≥0.9 未声明派生」旗标命中自有蜜罐传感器时,正确解是接受现声明面、
把高 OC 读作探针集盲区(探针集从池构造,看不见池外段),而不是错标 derived
去迁就 gate 读数。蜜罐法传感器标 honeypot_methodology=True(bruteforce 先例
对立面:ustc 生产网周边观测 = False)。
