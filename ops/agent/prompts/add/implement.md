# IMPLEMENT:交接单 → 测试+源码(TDD 硬序)(票 #332 P1;蒸馏自 add-intel-source SKILL Phase 2-4)

输入:交接单(dossier)、钉死的源文件名 stem、期望路径、沙箱路径、pytest 解释器。
你的任务:在沙箱里把这个源实现出来,**测试先行**。

## TDD 硬序(门会机检,跳步=终态)

1. 先写 `backend/tests/sources/test_<stem>.py`:断言解析/查询行为(模块尚不存在)。
   夹具取材先扩样:交接单 `samples` 只是 3-5 行预告——动笔前先用 `run_bash` 抓
   交接单 `url` 的**完整实数据文件**通读全文件形态(表头/注释/空行、脏行形态:
   缺列/坏 IP/占位符 '-'/'.'/空字段、裸 IP 与 CIDR 并存面;大文件可分段 head/tail,
   存沙箱内临时件);夹具行=从实抓全量里**逐字选**的行,实数据里有脏行/边界行
   则至少各选一条入夹具。抓不到(网络拒/超时)如实退回卡内样张为限,不手编假行。
   **样张是预告不是全集**:列表型源的输入面
   通用惯例是裸 IP 与 CIDR(/nn)记法并存、注释/表头行跳过——解析器两类都处理,
   测试各形态至少一条断言(仓内 roster 惯例,不是某源特性)。
   动笔前先读 2-3 个同 archetype(数据形状同族:CSV/TSV/列表/JSON)兄弟源的**逐源
   测试**(`backend/tests/sources/` 下沙箱在场件,非本 stem):仓内逐源测试是证据
   契约的可执行规格,你的测试照它们的断言族写——记录断言怎么组织(哪些槽位必须在
   场、缺值时键省略还是置空、计数字段什么类型、列表槽怎么组)、rebuild+query 回程
   怎么断、脏行夹具取什么形态、下载失败保旧件/部分写怎么断。自造断言风格=对不上
   仓内契约。
2. 跑 `run_pytest`,**亲眼看它以正确理由红**(ModuleNotFoundError:ipdb._sources.<stem>
   或等价)——这是必经一步,不是仪式。
3. 再写 `backend/ipdb/_sources/<stem>.py` 实现转绿。

## 实现契约(SKILL Phase 2-4 的骨架;细节以沙箱内活代码为准)

- 模式照抄既有源:`backend/ipdb/_sources/` 里现成的源文件就是模板——**读它们**,
  不要发明新模式。基类两份(`_base.py`/`_source_base.py`),先 `grep "^class"` 枚举
  活类,不背类清单。
- **主类名拼法收敛(装载约定)**:主类名 = `<stem 拼法>Source`——但仓内逐源类名是
  人工惯例,消费方 import 的是冻结拼法,拼错 = 导入面整个断(collection 面 0 分),
  且无法从 stem 机械推出哪一派。落法:主类名照你的最佳判断定义;模块尾部用
  PEP 562 模块级 `__getattr__` 把**三种规范拼法**都导出可导入(与主类名相同则免):
  ①令牌机械形(stem 去分隔符、仅首字母大写);②品牌拆词形(stem 断成品牌段+
  普通词段,各段首字母大写、段内其余字母**保留原大小写**——缩写段不整体改大写);
  ③缩写全大写形(品牌段整体大写):
  ```python
  _IMPORT_ALIASES = {"<变体名>": "<主类名>"}  # 各变体→主类;与主类同名的不列
  def __getattr__(name):
      if name in _IMPORT_ALIASES:
          return globals()[_IMPORT_ALIASES[name]]
      raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
  ```
  机制面:`from 包 import 名` 对缺席名走模块 `__getattr__`(PEP 562 语义),别名可
  导入;变体**不出现在 `dir()`**——注册表自动发现按 `dir()` 枚举,不会双注册(直接
  赋值别名 `X = 主类` 会进 `dir()`,同一类被注册两次、roster 双行,禁用)。
- 行为对照走执行面,不止读码面:定稿前把 1-2 个同 archetype 兄弟源**跑起来**——
  用 pytest 解释器现场调它的行解析/Evidence 构造面(喂一行真实样本,打印产出的
  记录全 dict);键路由语义(CIDR 行成员查询:含属命中/部分前缀不命中/一行多证据
  并存)用它的 query() 实测对照。你的记录面照**运行时观测到的形状**落——字段集、
  缺值省略面、计数类型、列表组法——不照从代码想象出来的形状。
- 生命周期硬契约:`download()` 只取数据不碰存储;`rebuild()` 是唯一写路径
  (rebuild_lmdb+reader_setter+flag_setter 原样拷);`load()` 纯 mmap;
  `query(ip)` 读 env。ApiSource 基类已删(PR #13,逐 IP 计费红线)——不存在,别找。
- 元数据在源文件内声明(类属性):`category` / `reliability` / `authoritative_for`
  ——注册表与融合表从这些属性派生,不手编 _registry/_merge 的表。**取值惯例:沙箱内
  同 category 兄弟源的 declared 取值就是惯例真源**——写 2-3 个同 category 源的
  reliability/classification_type 对齐着抄(tests/source_infra 会断言 declared 元数据
  达仓内下限,自造低值=门红)。
- 分类受控词表:映射落 `backend/ipdb/_classification.py` 的 per-source `_MAP`,
  受 `normalize()` 约束;不在词表里的类型先查 `ALL_KNOWN` 再措辞,不造新词。
- 字段路由按 `_evidence.py` 三层槽位(CORE_FIELDS/SCALAR_SLOTS/RICH_SLOTS)逐字段
  落定,交接单 `field_routing` 只是草案,冲突以槽位规则为准。**逐列落位:样张每一列
  都要找到兄弟源同名列的既有映射照抄**(如 AS 名称列→as_name、国家码列→country
  类既有惯例),拿不准的列查槽位定义,**不默认塞 extra**。计数/次数类列
  (hits/reports/出现次数)同样查槽位与兄弟源同列惯例落位。

## 工具纪律

- `write_file` 只写沙箱内文件;`run_bash` 沙箱根内执行;`run_pytest` 跑测试。
- 跑测试一律用 `run_pytest` 工具:`run_bash` 里跑 pytest 不入转录机检面,G_IMPLEMENT
  的首红末绿回算只认 `run_pytest` 种子序。
- 测试只许用真实样张与公开网络面取的数据,不手编「应该出现的」结果。
- **收尾自检**:终答前用 `run_pytest` 跑 `backend/tests/source_infra/ -q` 与你自己的
  测试文件,两类全绿才算完——GATE 门就是这套组合,提前自检(这些是沙箱内公共
  门,不是答案)。

## 终答契约

实现转绿后,终答单条 JSON(不要围栏、不要散文):

```json
{"name": "<stem>(逐字=钉死的 stem;勿填交接单人类可读名)", "test_file": "backend/tests/sources/test_<stem>.py", "source_file": "backend/ipdb/_sources/<stem>.py", "red_observed": true, "green_observed": true, "notes": "一句话:红的原因/绿的依据/残留"}
```

- `test_file`/`source_file` 相对沙箱根;门会验文件真在场与 stem 一致。
- `red_observed`/`green_observed` 只在亲眼见过对应 pytest 输出后置 true——
  转录机检(首红末绿)独立回算,谎报必被门抓。
