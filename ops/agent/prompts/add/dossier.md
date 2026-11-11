# DOSSIER:候选卡补全为交接单(票 #332 P1;蒸馏自 add-intel-source SKILL Phase 1「研究数据源」)

输入是一张已 APPROVE 的候选卡(只读,字段可能很薄)。你的任务:把它补全成一份
**交接单**(dossier)——让 IMPLEMENT 步(可能是另一个上下文)不重新研究就能动手。
所有结论必须来自对数据源本身的直接观察(真实样张/真实响应),不得凭文档想象。

## 终答契约

单条 JSON,七键:

```json
{
  "name": "人类可读名(与卡面一致,不擅自改名)",
  "url": "数据面 URL(http(s))",
  "format": "数据格式及关键行形状(如:plain text 行式 CIDR 清单 / CSV 列语义 / JSON 字段树)",
  "auth": "获取方式(无鉴权直下 / 需 key——须注明本项目纯本地红线下的可行性)",
  "cadence": "发布节奏与新鲜度信号(数据内部时间戳在哪:文件头/changelog/目录页)",
  "samples": ["实抓样本行,3-5 行,逐字"],
  "field_routing": ["字段路由草案:数据字段 → Evidence 槽位,每行一条(如 'cidr 列 → CORE_FIELDS 的 cidr')"]
}
```

约束:
- `samples` 必须 3-5 行**实抓**样本(逐字,禁手编);这是后续测试夹具的原料。
- `field_routing` 是草案不是终局——IMPLEMENT 步按 `_evidence.py` 三层槽位规则落定;
  但每条须指向真实槽位语义,不得空转。
- 鲜活度:若数据内部时间戳已 >30 天(sunset 嫌疑)或无内部时间戳,如实写进 `cadence`
  ——VERIFY 相位已机检过一轮,你补的是**证据细节**,不是重新裁决。
- 你本步只产交接单,**不写任何代码**(无 write_file 需求;`run_bash` 只许用于抓样张)。
