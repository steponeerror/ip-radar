# backend/tests/source_infra/test_canary_registry.py
"""Registry/main wiring guards for the internal canary source (spec §5.2 + F2/F3/F4)."""
from pathlib import Path

import pytest

import ipdb._registry as reg


class _FakeReal:
    name = "real1"
    category = "threat"
    internal = False
    fields = ("is_malicious",)
    authoritative_for = ()
    reliability = 0.5
    classification_type = "blacklist"
    url = "https://example.invalid/feed"

    def __init__(self, loaded=True, count=10, stale=False):
        self._loaded, self._count, self._stale = loaded, count, stale

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=self._loaded,
                            record_count=self._count, last_updated="2026-01-01T00:00:00Z",
                            is_stale=self._stale, covered_ips=self._count, covered_v6_nets=0)


class _FakeCanary(_FakeReal):
    name = "sentinel"
    internal = True
    url = ""


def test_real_registry_has_hidden_sentinel():
    src = reg._find_source("sentinel")
    assert src is not None and getattr(src, "internal", False) is True
    assert reg.is_enabled("sentinel") is True
    assert "sentinel" not in [s["name"] for s in reg.list_sources()]
    assert "sentinel" not in reg.roster()


def test_db_loaded_ignores_internal(monkeypatch):
    monkeypatch.setattr(reg, "_sources", [_FakeReal(loaded=False), _FakeCanary(loaded=True)])
    monkeypatch.setattr(reg, "_disabled", set())
    reg._loaded_cache["key"] = None          # invalidate cache
    assert reg._db_loaded() is False         # F2: sentinel alone must not load


def test_get_status_excludes_internal_counts(monkeypatch):
    monkeypatch.setattr(reg, "_enabled_sources",
                        lambda: [_FakeReal(count=10), _FakeCanary(count=999)])
    # get_status 按名字查 SOURCE_CATEGORIES 分桶;fake 名 real1 不在真册,
    # 显式指成 threat 才能验证 canary 的 999 不进 threat 桶。
    monkeypatch.setattr(reg, "SOURCE_CATEGORIES",
                        {**reg.SOURCE_CATEGORIES, "real1": "threat"})
    st = reg.get_status()
    assert st["total_records"] == 10 and st["threat_records"] == 10


def test_set_source_enabled_rejects_internal(monkeypatch):
    monkeypatch.setattr(reg, "_find_source", lambda n: _FakeCanary())
    with pytest.raises(ValueError, match="internal source not toggleable"):
        reg.set_source_enabled("sentinel", False)


def test_needs_rebuild_of_internal_branch(tmp_path, monkeypatch):
    canary = _FakeCanary()
    canary._mmdb_path = tmp_path / "sentinel.lmdb.ptr"
    canary._mmdb6_path = tmp_path / "sentinel.v6.lmdb.ptr"
    assert reg._needs_rebuild_of(canary) is True            # F3: ptr 缺失
    canary._mmdb_path.write_text("1")
    canary._mmdb6_path.write_text("1")
    assert reg._needs_rebuild_of(canary) is False


def test_stale_source_names_excludes_internal(monkeypatch):
    # 两 fake 均报 stale=True 才真正考验 filter:canary 能通过 stale 筛选,
    # 只靠 internal 排除被拦下;real1 存活证明过滤不过宽 → 恰为 ["real1"]。
    monkeypatch.setattr(reg, "_enabled_sources",
                        lambda: [_FakeReal(stale=True), _FakeCanary(stale=True)])
    assert reg.stale_source_names() == ["real1"]


def test_scheduler_scan_never_enqueues_sentinel(tmp_path, monkeypatch):
    """F1 tripwire(P1):ptr 已就位的 sentinel(已建状态,不走 needs_rebuild
    分支)永无数据文件 → _read_mtime None → 若进调度扫描循环则每个周期
    (~1800s)永久入队。enabled_offline_sources 必须按 internal 过滤。"""
    import time as _time
    from ipdb._scheduler import RefreshScheduler
    from ipdb._sources.canary import CanarySource

    canary = CanarySource(tmp_path)
    canary._mmdb_path.write_text("1")     # 已建状态:F3 ptr 齐 → 非重建
    canary._mmdb6_path.write_text("1")
    real = _FakeReal()
    real.stale_days = 1
    real._path = tmp_path / "real1.txt"
    real._path.write_text("x")            # 新鲜 mtime:未到 slot → 本就不入队
    monkeypatch.setattr(reg, "_enabled_sources", lambda: [real, canary])
    assert [s.name for s in reg.enabled_offline_sources()] == ["real1"]

    class _Mgr:
        def __init__(self):
            self.enqueued = []

        def enqueue_one_detached(self, name):
            from ipdb._tasks import Task
            self.enqueued.append(name)
            return Task(id=f"t{len(self.enqueued)}", source_name=name,
                        host=None, batch_id=None)

        def task_state(self, tid):
            return "done"

    mgr = _Mgr()
    sch = RefreshScheduler(manager=mgr,
                           enabled_offline_sources=reg.enabled_offline_sources,
                           needs_rebuild_of=reg._needs_rebuild_of)
    sch.scan(now=_time.time())
    assert mgr.enqueued == []


def test_update_source_route_404_for_internal(monkeypatch, client_as_admin):
    # F4 补口:manual re-embed 触发点(POST /api/sources/{name}/update)对
    # internal 源必须与 PATCH/eval 同款 404。manager 用记录桩,红跑零副作用。
    import main as main_mod
    monkeypatch.setattr(main_mod._ipdb_registry, "_find_source",
                        lambda n: _FakeCanary() if n == "sentinel" else None)

    class _Mgr:
        def __init__(self):
            self.calls = []

        def enqueue_one(self, name):
            self.calls.append(name)
            return type("T", (), {"id": "t0"})()

    stub = _Mgr()
    monkeypatch.setattr(main_mod, "manager", stub)
    assert client_as_admin.post("/api/sources/sentinel/update").status_code == 404
    assert stub.calls == []


def test_eval_routes_404_for_internal(monkeypatch, client_as_admin):
    # main 模块导入方式照抄 backend/tests/core/test_main_routes.py
    import main as main_mod
    # POST 路由的 require_ready 是 route 级依赖,先于 404 守卫;孤立运行无
    # DB 会 503 短路。被测点是 404 守卫,不是 ready 门 → 门放行。
    monkeypatch.setattr(main_mod, "_db_ready", lambda: True)
    monkeypatch.setattr(main_mod._ipdb_registry, "_find_source",
                        lambda n: _FakeCanary() if n == "sentinel" else None)
    # GET /api/eval/{source} 2026-09-22 审计 F2 起同样要超管;404 守卫语义不变
    assert client_as_admin.get("/api/eval/sentinel").status_code == 404
    # POST run Task 3 起要超管 → 登录 client,404 守卫语义不变
    assert client_as_admin.post("/api/eval/sentinel/run").status_code == 404


def test_all_real_disabled_is_not_warming(monkeypatch):
    # 回归(review round 1):仅 internal 源 enabled = 全源禁用 —— internal 恒
    # enabled,若按 _enabled_sources() 判空,该分支永不触发 → 永久 warming 503,
    # 横幅 Retry(/api/update-db 候选仅 sentinel)永远打不开门(main.py:722 语义)。
    from fastapi.testclient import TestClient
    import main as main_mod
    monkeypatch.setattr(reg, "_enabled_sources", lambda: [_FakeCanary(loaded=True)])
    monkeypatch.setattr(main_mod, "_db_ready", lambda: False)
    client = TestClient(main_mod.app)
    r = client.get("/api/db-status")
    assert r.status_code == 200
    assert r.json()["warming_up"] is False


def test_require_ready_no_sources_when_only_internal(monkeypatch):
    # 同口径的 require_ready 侧:全源禁用必须走 no-sources 分支(诚实报错),
    # 而不是落到 warming 分支。直接调依赖函数,无需 TestClient。
    from fastapi import HTTPException
    import main as main_mod
    monkeypatch.setattr(reg, "_enabled_sources", lambda: [_FakeCanary(loaded=True)])
    with pytest.raises(HTTPException) as ei:
        main_mod.require_ready()
    assert ei.value.status_code == 503
    assert ei.value.headers["X-IPRadar-Reason"] == "no-sources"
