# IMPLEMENT:交接单 → 测试+源码(TDD 硬序)(票 #332 P1;蒸馏自 add-intel-source SKILL Phase 2-4)

输入:交接单(dossier)、钉死的源文件名 stem、期望路径、沙箱路径、pytest 解释器。
你的任务:在沙箱里把这个源实现出来,**测试先行**。

## TDD 硬序(门会机检,跳步=终态)

1. 先写 `backend/tests/sources/test_<stem>.py`:用交接单 `samples` 里的真实样张做夹具,
   断言解析/查询行为(模块尚不存在)。
2. 跑 `run_pytest`,**亲眼看它以正确理由红**(ModuleNotFoundError:ipdb._sources.<stem>
   或等价)——这是必经一步,不是仪式。
3. 再写 `backend/ipdb/_sources/<stem>.py` 实现转绿。

## 实现契约(SKILL Phase 2-4 的骨架;细节以沙箱内活代码为准)

- 模式照抄既有源:`backend/ipdb/_sources/` 里现成的源文件就是模板——**读它们**,
  不要发明新模式。基类两份(`_base.py`/`_source_base.py`),先 `grep "^class"` 枚举
  活类,不背类清单。
- 生命周期硬契约:`download()` 只取数据不碰存储;`rebuild()` 是唯一写路径
  (rebuild_lmdb+reader_setter+flag_setter 原样拷);`load()` 纯 mmap;
  `query(ip)` 读 env。ApiSource 基类已删(PR #13,逐 IP 计费红线)——不存在,别找。
- 元数据在源文件内声明(类属性):`category` / `reliability` / `authoritative_for`
  ——注册表与融合表从这些属性派生,不手编 _registry/_merge 的表。
- 分类受控词表:映射落 `backend/ipdb/_classification.py` 的 per-source `_MAP`,
  受 `normalize()` 约束;不在词表里的类型先查 `ALL_KNOWN` 再措辞,不造新词。
- 字段路由按 `_evidence.py` 三层槽位(CORE_FIELDS/SCALAR_SLOTS/RICH_SLOTS)逐字段
  落定,交接单 `field_routing` 只是草案,冲突以槽位规则为准。

## 工具纪律

- `write_file` 只写沙箱内文件;`run_bash` 沙箱根内执行;`run_pytest` 跑测试。
- 测试只许用真实样张与公开网络面取的数据,不手编「应该出现的」结果。

## 终答契约

实现转绿后,终答单条 JSON(不要围栏、不要散文):

```json
{"name": "<stem 对应源名,与交接单 name 一致>", "test_file": "backend/tests/sources/test_<stem>.py", "source_file": "backend/ipdb/_sources/<stem>.py", "red_observed": true, "green_observed": true, "notes": "一句话:红的原因/绿的依据/残留"}
```

- `test_file`/`source_file` 相对沙箱根;门会验文件真在场与 stem 一致。
- `red_observed`/`green_observed` 只在亲眼见过对应 pytest 输出后置 true——
  转录机检(首红末绿)独立回算,谎报必被门抓。
