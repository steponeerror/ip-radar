# qb258 分支简报:_alerts/_auth env 路径覆写同形五连折并(#258)

- 分支:`qb258`(基线 queue-batch 805c0d59,开工已验 `git merge-base --is-ancestor queue-batch HEAD`)
- 性质:微折并 refactor,两模块行为零变化;3 产品文件 + 2 测试文件,+51/−8

## 改了哪几处

1. **`backend/ipdb/_registry.py`**(新增 helper,紧随 `_STATE_PATH` 定义):`env_path_or_state_sibling(env_var: str, filename: str) -> Path` —— env 变量非空 → `Path(env 值)`;否则 `_STATE_PATH.parent / filename`。`_STATE_PATH` 走模块全局动态解析(测试 `monkeypatch.setattr(_registry, "_STATE_PATH", ...)` 即换根,不在导入期捕获)。docstring 带出处(#258、notes/ub-mode-2026-10-31.md)。
2. **`backend/ipdb/_alerts.py`**:`_db_path()` 五连体改一行委托 `_registry.env_path_or_state_sibling("IP_RADAR_ALERTS_DB", "alerts.db")`;函数名保留(`_connect` 调用、`_tokens.py:37` 注释引用的惯例名不动)。
3. **`backend/ipdb/_auth.py`**:`_auth_db_path()` 同型委托(`"IP_RADAR_AUTH_DB", "auth.db"`);函数名保留(`_engine`/`_session_maker` 调用)。

测试(`backend/tests/alerts/test_storage.py` + `backend/tests/auth/test_auth_db.py` 各 +2):
- `test_db_path_env_override` / `test_auth_db_path_env_override`:env 覆写直读(纯路径解析,不落盘)。
- `test_db_path_default_and_empty_env_fall_back` / `test_auth_db_path_default_and_empty_env_fall_back`:缺省回退 `_STATE_PATH` 同目录;**负例**:空串 env 视同未设——钉住 `if env:` 真值语义(而非 `is not None`),这是折并前后零变化的关键边。4 测先对 inline 旧码跑绿(pin),再折并,再全绿。

## 为何(工单方向落实)

工单 #258:ub-mode 批 dryer 命中 `_alerts.py:57-61` ↔ `_auth.py:48-52` score 1.00(换名拷贝),真重复归票。折并位置选 `_registry`(工单建议位):①两模块本就 `from . import _registry`,零新 import;②helper 语义就是「_STATE_PATH 同目录落 db」,归属数据目录真相源;③`_registry` 对 `_alerts`/`_auth` 无顶层依赖,不成环(`_source_info` 里的 `_alerts` 是惰性 import)。

**不强折项(工单「不强行」条款)**:`_alerts._factories/_make_factory`(同步 sqlite3 按路径缓存工厂)与 `_auth._engines/_session_makers`(async SQLAlchemy 引擎/会话缓存)评审为**不同形**——同步/异步、连接对象 vs 引擎对象、`_session_maker` 双字典联动,折并即造抽象层,超出「换名拷贝」范畴;dryer 也从未命中该对。维持现状。

## 验证(三段红绿证 + 全量)

dryer 阈值 0.82,跑法照 `~/.pi/agent/skills/code-metrics/SKILL.md`(`-s backend -s frontend/src`):

| 时点 | 该对命中 | 全库候选对 |
|---|---|---|
| 基线 inline(改动前,即 805c0d59) | **1.00**(`_alerts.py:57-61` ↔ `_auth.py:48-52`) | 79 |
| 折并后 | **消失**(`_alerts.py` 不入任何候选) | 78 |
| 回退内联复证(两调用方 checkout 回 HEAD~1) | **1.00 复现** | 79 |

红证即工单钦定路数「删 helper 改回内联 → dryer 对复现」:折并是该对消失的直接原因(79↔78 恰差这一对),非阈值抖动。报告原件:`/tmp/ub-metrics-qb258/dry-BASELINE-inline.edn`、`/tmp/ub-metrics-qb258-folded/.metrics/dry.edn`、`/tmp/ub-metrics-qb258-revert/.metrics/dry.edn`。

全套件:commit 后干净树 `pytest tests -q` = **2416 passed, 9 skipped, 0 failed**(含 `test_ops_rounds_e2e::test_health_round_real_run` 真跑)。

## 环境注(复核者必读)

- **宿主 python 已被污染**:miniforge site-packages 里 sopagent 两个可编辑安装 .pth 把 `/home/huxiao/dev/sopagent` 注入一切 python 进程 sys.path;其 `tests/__init__.py`(正规包)压过本仓 `tests`(命名空间包),`from tests.conftest import` / 裸 `from conftest import` 全被劫持(2+5 个收集错)。**该污染先于本批存在**(stash 基线同错)。本批复核用干净 venv:`python -m venv /tmp/qb258-venv && pip install -r backend/requirements*.txt`。治本(移除 sopagent .pth 或本仓 tests 加 `__init__.py` 转正规包)属环境治理,未动。
- **e2e 真跑前置**:worktree 须 `ops/agent` 内 `npm install`(326 包)+ **干净树**——agent 侧 `sandbox_assert` 对 backend/frontend 未提交改动直接 `sandbox_violation`(测试 docstring 钦定「先提交再跑」,非测试缺陷)。脏树跑出 1 failed 的 `sandbox_violation` 属预期。
- 复核命令:`cd backend && pytest tests -q`(venv);dryer 三段照上表;单测钉子:`pytest tests/alerts/test_storage.py tests/auth/test_auth_db.py -q` = 21 passed。
