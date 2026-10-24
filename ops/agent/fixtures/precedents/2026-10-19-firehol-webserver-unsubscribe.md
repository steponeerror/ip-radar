---
id: 2026-10-19-firehol-webserver-unsubscribe
date: 2026-10-19
subject: 矩阵违例执法 — 案一维持非法,最小执法仅退订 firehol_webserver
context: >
  生产首扫 13 违例格(2026-10-19 裁决包),用户三案裁决:案一 infra 威胁轴 7 格
  (含 webserver 端口扫描类目票)维持非法(ruling-confirmed)。会话推荐
  立即制定融合层豁免清单以清违例。
recommendation: 豁免清单现在做,融合层对四源残差豁免。
human_ruling: >
  用户选最小执法:仅退订 firehol_webserver(_LIST_SPEC 4 子清单,案一唯一执法);
  否决「清单现在做」的推荐——豁免清单 = 独立 grill 另裁。四源残差 6 格违例
  常亮红 park(设计内记账压力)。
reward:
  hard_gates:
    violations_before: 13
    violations_after: 6
    matrix_legal_before: 25
    matrix_legal_after: 31
    parked_residual_cells: 6
  ruling_agreement: amended
  production_delta: null
lineage:
  - "PR #129"
superseded_by: null
---

# 判例:矩阵违例执法取最小面

语义矩阵违例的执法不追求清零:能机械退订的退订(firehol_webserver 是
informational 唯一证人,退订后 8.8.8.8 查询干净),残差违例常亮红 park
作为记账压力留给豁免清单 grill 裁决。豁免清单这类语义面动作不与执法批捆绑。
