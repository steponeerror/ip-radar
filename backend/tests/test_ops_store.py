"""P1 ops 树存取(票 #133,TDD 红先行)。

钉住产品化批 Task P1 契约(docs/superpowers/plans/2026-10-19-ops-agent-productization.md):
ops 根解析 $IP_RADAR_DATA_DIR/ops(回落沿 _registry.DATA_DIR 惯例)、树初始化幂等、
种子导入幂等(二次导入零新增)、原子写(半包不留脏文件)、待集成清单追加去重
(去重键 = action+source,T4 tools.mjs queueAction 冻结形状)、台账表头/行形状
(T4 lib.sh ledger_append 冻结形状)、rg 检索 rc≥2 报错不伪装空(T2 Minor-3 判例,
无证据≠清白)、CLI `python -m ipdb._ops_store --import-seeds <目录>`。

期望值全部取自冻结件独立真源(docs/ops/ 现存文件与 tools.mjs/lib.sh 字面),
不从被测模块导入常量,防套套逻辑。
"""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

# T4 lib.sh ledger_append 首建表头(逐字)
LEDGER_HEADER = (
    "# 运营轮次台账\n\n"
    "| 日期 | 轮次 | model | 用量 | 备注 |\n"
    "|---|---|---|---|---|\n"
)
# T4 tools.mjs queueAction 首建表头(逐字)
QUEUE_HEADER = (
    "# 源生命周期动作队列(queue_action 唯一写口;行由 host 模板渲染,rationale 只落工件)\n\n"
    "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n"
    "|---|---|---|---|---|---|---|\n"
)


@pytest.fixture
def store():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误)。"""
    import ipdb._ops_store as ops_store
    return ops_store


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp:IP_RADAR_DATA_DIR 指隔离目录,不碰真 data/。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _seed_dir(tmp_path: Path) -> Path:
    """三文件种子目录(schema 说明 + 两条判例),形状同 docs/ops/precedents/。"""
    d = tmp_path / "seeds"
    d.mkdir()
    (d / "_schema.md").write_text("# 判例库 schema\n", encoding="utf-8")
    (d / "2026-10-18-a-case.md").write_text("---\nid: a\n---\nsunset 判例\n", encoding="utf-8")
    (d / "2026-10-19-b-case.md").write_text("---\nid: b\n---\nmirror 判例\n", encoding="utf-8")
    return d


# ── ops 根解析 ───────────────────────────────────────────────────────


def test_ops_root_resolves_under_data_dir(store, ops_env):
    assert store.ops_root() == ops_env / "ops"


def test_ops_root_falls_back_to_backend_data(store, monkeypatch):
    """未设 env 时回落 <backend>/data/ops,与 _registry.DATA_DIR 同一惯例,不发明第二套。"""
    monkeypatch.delenv("IP_RADAR_DATA_DIR", raising=False)
    expected = Path(store.__file__).resolve().parent.parent / "data" / "ops"
    assert store.ops_root() == expected


# ── 树初始化 ─────────────────────────────────────────────────────────


def test_init_ops_tree_creates_skeleton_idempotent(store, ops_env):
    root = store.init_ops_tree()
    assert root == ops_env / "ops"
    for sub in ("precedents", "packages", "artifacts"):
        assert (root / sub).is_dir(), f"缺子目录 {sub}"
    assert (root / "ledger.md").read_text(encoding="utf-8") == LEDGER_HEADER
    assert (root / "queue.md").read_text(encoding="utf-8") == QUEUE_HEADER
    # 幂等:二次初始化对既有树零改动(表头不重建、目录不报错)
    before = sorted(p.name for p in root.rglob("*"))
    texts = {p.name: p.read_text(encoding="utf-8")
             for p in root.iterdir() if p.is_file()}
    store.init_ops_tree()
    after = sorted(p.name for p in root.rglob("*"))
    assert after == before
    for name, text in texts.items():
        assert (root / name).read_text(encoding="utf-8") == text


# ── 种子导入(一次性幂等) ───────────────────────────────────────────


def test_import_seeds_idempotent_zero_new_on_second_run(store, ops_env, tmp_path):
    seeds = _seed_dir(tmp_path)
    res = store.import_seeds(seeds)
    assert res["imported"] == 3
    target = ops_env / "ops" / "precedents"
    assert sorted(p.name for p in target.glob("*.md")) == [
        "2026-10-18-a-case.md", "2026-10-19-b-case.md", "_schema.md"]
    # 二次导入零新增:目标已有一律跳过
    res2 = store.import_seeds(seeds)
    assert res2["imported"] == 0
    assert res2["skipped"] == 3
    assert sorted(p.name for p in target.glob("*.md")) == [
        "2026-10-18-a-case.md", "2026-10-19-b-case.md", "_schema.md"]


def test_import_seeds_never_overwrites_existing(store, ops_env, tmp_path):
    """种子永不覆写库内判例(无界不删):库是活副本,人裁写回后不得被导入冲掉。"""
    seeds = _seed_dir(tmp_path)
    store.import_seeds(seeds)
    live = ops_env / "ops" / "precedents" / "2026-10-18-a-case.md"
    live.write_text("---\nid: a\nsuperseded_by: 2026-10-20-c.md\n---\n改判后\n",
                    encoding="utf-8")
    store.import_seeds(seeds)
    assert "superseded_by" in live.read_text(encoding="utf-8")


def test_import_seeds_missing_dir_fails_loud(store, ops_env):
    """缺种子目录必须报错:静默零导入会伪装成「无事可做」(无证据≠清白)。"""
    with pytest.raises(FileNotFoundError):
        store.import_seeds(ops_env / "no-such-seed-dir")


# ── 原子写 ───────────────────────────────────────────────────────────


def test_atomic_write_failure_leaves_no_trace(store, tmp_path, monkeypatch):
    """rename 前故障:原文件原样、无半包、无 .tmp 残留(中断不留脏文件)。"""
    target = tmp_path / "ledger.md"
    target.write_text("original\n", encoding="utf-8")

    def boom(*a, **kw):
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError):
        store.atomic_write_text(target, "half-written\n")
    monkeypatch.undo()
    assert target.read_text(encoding="utf-8") == "original\n"
    assert [p.name for p in tmp_path.iterdir()] == ["ledger.md"]


def test_atomic_write_success_no_temp_residue(store, tmp_path):
    target = tmp_path / "precedents" / "a.md"   # 父目录不存在也应自动建
    store.atomic_write_text(target, "内容\n")
    assert target.read_text(encoding="utf-8") == "内容\n"
    assert [p.name for p in (tmp_path / "precedents").iterdir()] == ["a.md"]


# ── 待集成清单(queue.md,T4 冻结形状) ──────────────────────────────


def test_append_queue_row_shape_and_dedup(store, ops_env):
    ev = [("call_x", "age_days", 252),
          ("call_x", "last_modified", "Sun, 08 Feb 2026 15:35:03 GMT")]
    # 新树直接追加:表头首建 + 行形状逐字(T4 evidence 渲染 call:field=json 值)
    res = store.append_queue(round_="discover", action="REJECT",
                             source="threatview_c2", predicate="sunset_frozen",
                             evidence=ev, today=date(2026, 10, 20))
    assert res == {"appended": True, "dedup": False}
    q = (ops_env / "ops" / "queue.md").read_text(encoding="utf-8")
    assert q.startswith(QUEUE_HEADER)
    expected_row = ('| 2026-10-20 | discover | REJECT | threatview_c2 | sunset_frozen | '
                    'call_x:age_days=252;call_x:last_modified="Sun, 08 Feb 2026 15:35:03 GMT" '
                    '| 是(否决=删除本行) |')
    assert expected_row in q.splitlines()

    # 同 action+source 二次入队(日期/轮次/证据不同)→ 幂等去重,不双写
    res2 = store.append_queue(round_="health", action="REJECT",
                              source="threatview_c2", predicate=None,
                              evidence=[("call_y", "age_days", 300)],
                              today=date(2026, 10, 21))
    assert res2 == {"appended": False, "dedup": True}
    q2 = (ops_env / "ops" / "queue.md").read_text(encoding="utf-8")
    rows = [l for l in q2.splitlines() if l.startswith("| 2026-")]
    assert len(rows) == 1

    # 不同 action → 新行(去重键 = action+source,不是 source 单独)
    res3 = store.append_queue(round_="discover", action="ENQUEUE",
                              source="threatview_c2", predicate=None,
                              evidence=ev, today=date(2026, 10, 22))
    assert res3 == {"appended": True, "dedup": False}
    q3 = (ops_env / "ops" / "queue.md").read_text(encoding="utf-8")
    rows = [l for l in q3.splitlines() if l.startswith("| 2026-")]
    assert len(rows) == 2


@pytest.mark.parametrize("kwargs", [
    {"round_": "discover", "action": "PURGE", "source": "threatview_c2"},
    {"round_": "discover", "action": "REJECT", "source": "threatview_c2",
     "predicate": "not_in_set"},
    {"round_": "discover", "action": "REJECT", "source": "Bad-Source"},
])
def test_append_queue_validates_frozen_closed_sets(store, ops_env, kwargs):
    """action/predicate 闭集与 source 形状沿 T4 契约,非法输入拒绝写文件。"""
    with pytest.raises(ValueError):
        store.append_queue(**kwargs)
    assert not (ops_env / "ops" / "queue.md").exists()


# ── 台账(ledger.md,T4 冻结形状) ──────────────────────────────────


def test_append_ledger_header_then_rows(store, ops_env):
    store.append_ledger(round_="health", model="glm-5.3-flash",
                        usage="in=671 out=859 total=5882 cost=0.00064598",
                        note="tools=1 sdk=pi-agent-core", today=date(2026, 10, 20))
    ledger = ops_env / "ops" / "ledger.md"
    text = ledger.read_text(encoding="utf-8")
    assert text.startswith(LEDGER_HEADER)
    assert ("| 2026-10-20 | health | glm-5.3-flash | "
            "in=671 out=859 total=5882 cost=0.00064598 | tools=1 sdk=pi-agent-core |"
            ) in text.splitlines()
    # 二次追加:行增、表头不重建(lib.sh ledger_append 幂等口径)
    store.append_ledger(round_="discover", model="glm-5.3", usage="in=1 out=1",
                        today=date(2026, 10, 21))
    text2 = ledger.read_text(encoding="utf-8")
    assert text2.count("| 日期 | 轮次 | model | 用量 | 备注 |") == 1
    rows = [l for l in text2.splitlines() if l.startswith("| 2026-")]
    assert len(rows) == 2


# ── rg 检索(T2 Minor-3 判例) ──────────────────────────────────────


def test_rg_search_hits_and_schema_excluded(store, ops_env):
    store.init_ops_tree()
    pdir = ops_env / "ops" / "precedents"
    (pdir / "2026-10-18-a-case.md").write_text("Sunset 冻结判死\n", encoding="utf-8")
    (pdir / "2026-10-19-b-case.md").write_text("mirror echo 判例\n", encoding="utf-8")
    (pdir / "_schema.md").write_text("sunset 字样在 schema 里也不算命中\n", encoding="utf-8")
    # 单词命中(大小写不敏感)+ _schema.md 排除
    assert store.rg_search_precedents(["sunset"]) == ["2026-10-18-a-case.md"]
    # 多检索词 = OR(rg 多 -e),命中排序返回
    assert store.rg_search_precedents(["sunset", "mirror"]) == [
        "2026-10-18-a-case.md", "2026-10-19-b-case.md"]


def test_rg_search_zero_hits_is_empty_not_error(store, ops_env):
    """rc=1 = 真零命中:空列表是合法结果,与基础设施故障分开。"""
    store.init_ops_tree()
    (ops_env / "ops" / "precedents" / "a.md").write_text("无关节例\n", encoding="utf-8")
    assert store.rg_search_precedents(["不存在的词"]) == []


def test_rg_search_rc2_raises_not_fake_empty(store, ops_env):
    """rc≥2 = 目录缺失等基础设施故障,必须报错,绝不伪装成空结果(无证据≠清白)。"""
    # ops 树未建:precedents 目录缺失 → rg rc=2
    with pytest.raises(RuntimeError, match="rc=2"):
        store.rg_search_precedents(["sunset"])


# ── CLI:python -m ipdb._ops_store --import-seeds <目录> ────────────


def test_cli_import_seeds_roundtrip_idempotent(store, ops_env, tmp_path):
    seeds = _seed_dir(tmp_path)
    env = {**os.environ, "IP_RADAR_DATA_DIR": str(ops_env)}
    r = subprocess.run(
        [sys.executable, "-m", "ipdb._ops_store", "--import-seeds", str(seeds)],
        capture_output=True, text=True, cwd=BACKEND_DIR, env=env)
    assert r.returncode == 0, r.stderr
    assert "imported 3" in r.stdout
    assert sorted(p.name for p in (ops_env / "ops" / "precedents").glob("*.md")) == [
        "2026-10-18-a-case.md", "2026-10-19-b-case.md", "_schema.md"]
    r2 = subprocess.run(
        [sys.executable, "-m", "ipdb._ops_store", "--import-seeds", str(seeds)],
        capture_output=True, text=True, cwd=BACKEND_DIR, env=env)
    assert r2.returncode == 0, r2.stderr
    assert "imported 0" in r2.stdout and "skipped 3" in r2.stdout


def test_cli_usage_error_exit_2(store, ops_env):
    """用法错 = 纯 stderr + exit 2(沿 _rebuild_child 惯例),零副作用。"""
    env = {**os.environ, "IP_RADAR_DATA_DIR": str(ops_env)}
    r = subprocess.run([sys.executable, "-m", "ipdb._ops_store"],
                       capture_output=True, text=True, cwd=BACKEND_DIR, env=env)
    assert r.returncode == 2
    assert "usage" in r.stderr
    assert not (ops_env / "ops").exists()
