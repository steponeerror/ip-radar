"""P1 确定性探测器(票 #154,spec #152 §2,TDD 红先行)。

钉住契约(独立真源 = spec §2 与票 #154 字面,不从被测模块导入常量,
防套套逻辑):

- 下载失败探测器:任务终态 failed + error_code=download → 产条
  (probe_class=download / action=retry_download / error_code 透传
  evidence / 连续失败计数);幂等 = 同源二次失败不双开(条目库语义键);
  severity 映射:连续≥3 high / 其余 medium;done/rebuild 失败清连败;
  cancelled 无证据不动;ops 伪源与非 download 码不产;error_signature =
  错误族(HTTP Error 403 → http_403,与降噪刀一同口径);
- 超龄探测器:内容年龄 > 2× 刷新周期产条(恰 2× 不产,严格大于);
  刷新周期 = 日更源 12h 槽位 / 其余 stale_days×24h(45h/12h 实证案例
  = spec §2 钉住);无数据文件不产(无内容年龄证据);幂等二次零写;
  目录型源内容 mtime = 目录内最新文件(_read_mtime 同源,2026-10-03
  线上判例:重写子文件不改目录 mtime);
- _tasks 旁挂零侵入:on_terminal 默认 None;回调吃 to_dict() 只读快照、
  每任务恰一次(_settled 幂等);回调抛错全吞,任务状态机/批次计数不变;
  真探测器装配后任务照常失败且条目即时出现(spec 验收面);
- scheduler on_scan 旁挂:扫描尾回调 (sources, now),默认 None 位等价。
"""

import re
import threading
import time
from pathlib import Path

import pytest
import yaml

# ── 独立真源字面(spec #152 §2 / 票 #154)──
TEN_FIELDS = [
    "id", "action", "args", "evidence", "impact",
    "rollback", "dedup_key", "severity", "cause_group", "status",
]
ITEM_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-item-[0-9a-f]{10}\.md$")


@pytest.fixture
def mod():
    """被测模块(RED 相位 = 模块不存在,逐测试失败;test_ops_items 同型)。"""
    import ipdb._ops_detectors as ops_detectors
    return ops_detectors


@pytest.fixture
def items_mod():
    import ipdb._ops_items as ops_items
    return ops_items


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp:IP_RADAR_DATA_DIR 指隔离目录,不碰真 data/。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _items_dir(ops_env) -> Path:
    return ops_env / "ops" / "items"


def _read_items(ops_env) -> list[dict]:
    """条目全量解析(独立于被测模块:直接 glob + yaml)。"""
    if not _items_dir(ops_env).is_dir():
        return []
    out = []
    for p in sorted(_items_dir(ops_env).glob("*.md")):
        assert ITEM_NAME_RE.match(p.name), f"条目文件名形状非法: {p.name}"
        text = p.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        end = text.find("\n---\n", 4)
        assert end != -1
        out.append(yaml.safe_load(text[4:end]))
    return out


def _wait_items(ops_env, timeout=5) -> list[dict]:
    """等条目落盘(终态 _set_state 先于收口 _settle,钩子在毫秒级尾随)。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        fms = _read_items(ops_env)
        if fms:
            return fms
        time.sleep(0.02)
    return _read_items(ops_env)


def _fail_td(source="spamhaus_drop", error="HTTP Error 403: Forbidden", **over):
    """任务终态快照(to_dict 形状;error_code=download 缺省)。"""
    td = {"id": "t1", "source": source, "host": "h", "state": "failed",
          "error": error, "error_code": "download", "batch_id": None,
          "received": 0, "total": 0}
    td.update(over)
    return td


# ══ 下载失败探测器 ═════════════════════════════════════════════════════

def test_download_failure_creates_item(mod, ops_env):
    det = mod.make_download_fail_detector()
    det(_fail_td())
    [fm] = _read_items(ops_env)
    for field in TEN_FIELDS:
        assert field in fm, f"缺冻结字段 {field}"
    assert fm["action"] == "retry_download"
    assert fm["dedup_key"]["probe_class"] == "download"
    assert fm["dedup_key"]["error_signature"] == "http_403"  # 错误族(401/403 单列)
    assert fm["cause_group"] == "download_failure"
    assert fm["status"] == "active"
    assert fm["args"] == {"source": "spamhaus_drop"}
    # error_code 透传 + 连续失败计数入 evidence(票 #154)
    assert fm["evidence"]["error_code"] == "download"
    assert fm["evidence"]["consecutive_failures"] == 1
    assert fm["evidence"]["last_error"] == "HTTP Error 403: Forbidden"
    assert fm["severity"] == "medium"          # 连续 1 < 3 → medium


def test_download_failure_idempotent_no_double_open(mod, ops_env):
    det = mod.make_download_fail_detector()
    det(_fail_td())
    det(_fail_td(id="t2"))                     # 同源二次失败(同错误族)
    fms = _read_items(ops_env)
    assert len(fms) == 1, "同源二次同族失败不双开(幂等归条目库)"


def test_download_failure_severity_high_at_three(mod, ops_env, items_mod):
    det = mod.make_download_fail_detector()
    det(_fail_td(id="t1"))
    det(_fail_td(id="t2"))                     # 连败 2,条目在飞不双开
    [first] = _read_items(ops_env)
    items_mod.set_status(first["id"], "done")  # 人审处置终态(升级沿复开链)
    det(_fail_td(id="t3"))                     # 连败 3 → 复开,severity high
    fms = _read_items(ops_env)
    assert len(fms) == 2
    reopened = next(f for f in fms if f["id"] != first["id"])
    assert reopened["supersedes"] == first["id"]
    assert reopened["severity"] == "high"      # 连续≥3 → high
    assert reopened["evidence"]["consecutive_failures"] == 3


def test_done_resets_streak(mod, ops_env, items_mod):
    det = mod.make_download_fail_detector()
    det(_fail_td(id="t1"))
    det(_fail_td(id="t2"))
    [first] = _read_items(ops_env)
    items_mod.set_status(first["id"], "dismissed")
    det({"id": "t3", "source": "spamhaus_drop", "host": None, "state": "done",
         "error": None, "error_code": None, "batch_id": None,
         "received": 0, "total": 0})           # 成功清连败
    det(_fail_td(id="t4"))                     # 重新连败 1 → medium
    reopened = [f for f in _read_items(ops_env) if f["id"] != first["id"]][0]
    assert reopened["evidence"]["consecutive_failures"] == 1
    assert reopened["severity"] == "medium"


def test_rebuild_failure_resets_and_produces_no_item(mod, ops_env):
    det = mod.make_download_fail_detector()
    det(_fail_td(id="t1"))                     # 连败 1
    det(_fail_td(id="t2", error_code="rebuild",
                 error="rebuild subprocess failed"))  # 下载已落地:清连败,不产
    det(_fail_td(id="t3"))                     # 重连败 1
    fms = _read_items(ops_env)
    assert len(fms) == 1
    assert fms[0]["evidence"]["consecutive_failures"] == 1


def test_cancelled_and_non_download_no_item(mod, ops_env):
    det = mod.make_download_fail_detector()
    det(_fail_td(id="t1", state="cancelled"))          # 取消:无证据不动
    det(_fail_td(id="t2", error_code="source_not_found"))
    det(_fail_td(id="t3", source="ops", error_code="download"))  # ops 伪源守卫
    assert _read_items(ops_env) == []


def test_error_families_observable(mod, ops_env):
    det = mod.make_download_fail_detector()
    det(_fail_td(source="src_a", error="HTTP Error 429: Too Many Requests"))
    det(_fail_td(source="src_b", error="HTTP Error 503: Service Unavailable"))
    det(_fail_td(source="src_c", error="<urlopen error timed out>"))
    det(_fail_td(source="src_d", error="weird unknown failure"))  # 认不出归 error_code
    sigs = {f["dedup_key"]["source"]: f["dedup_key"]["error_signature"]
            for f in _read_items(ops_env)}
    assert sigs == {"src_a": "http_4xx", "src_b": "http_5xx",
                    "src_c": "timeout", "src_d": "download"}


# ══ 超龄探测器 ═════════════════════════════════════════════════════════

class _FakeSource:
    """最小源形状:name/stale_days/_path(scheduler/_alerts 同信号面)。"""

    def __init__(self, name, path, stale_days):
        self.name = name
        self._path = path
        self.stale_days = stale_days


def _mk_source(tmp_path, name, stale_days, age_s, now):
    p = tmp_path / f"{name}.txt"
    p.write_text("x")
    import os
    os.utime(p, (now - age_s, now - age_s))
    return _FakeSource(name, p, stale_days)


def test_staleness_exact_2x_no_item(mod, ops_env, tmp_path):
    now = 2_000_000.0
    src = _mk_source(tmp_path, "daily_src", stale_days=1,
                     age_s=2 * 43200, now=now)     # 恰 2×(12h 槽位周期)
    mod.run_staleness_detector([src], now=now)
    assert _read_items(ops_env) == [], "恰 2× 不产(严格大于)"


def test_staleness_over_2x_produces_item_45h_case(mod, ops_env, tmp_path):
    now = 2_000_000.0
    src = _mk_source(tmp_path, "daily_src", stale_days=1,
                     age_s=45 * 3600, now=now)     # 45h > 2×12h(spec §2 实证案例)
    mod.run_staleness_detector([src], now=now)
    [fm] = _read_items(ops_env)
    for field in TEN_FIELDS:
        assert field in fm
    assert fm["dedup_key"]["probe_class"] == "staleness"
    assert fm["dedup_key"]["error_signature"] == "age_gt_2x_refresh"
    assert fm["action"] == "refresh_source"
    assert fm["cause_group"] == "staleness"
    assert fm["evidence"]["content_age_h"] == pytest.approx(45.0)
    assert fm["evidence"]["refresh_period_h"] == pytest.approx(12.0)  # 日更 12h 槽位
    assert fm["evidence"]["stale_days"] == 1
    assert fm["severity"] == "medium"
    # 幂等:同轮二次扫描零写(同因在飞不双开)
    mod.run_staleness_detector([src], now=now + 60)
    assert len(_read_items(ops_env)) == 1


def test_staleness_weekly_tier_and_boundary(mod, ops_env, tmp_path):
    now = 2_000_000.0
    ok = _mk_source(tmp_path, "weekly_fresh", stale_days=7,
                    age_s=2 * 7 * 86400, now=now)          # 恰 2×(168h)
    stale = _mk_source(tmp_path, "weekly_stale", stale_days=7,
                       age_s=2 * 7 * 86400 + 60, now=now)  # 过 2× 一分钟
    mod.run_staleness_detector([ok, stale], now=now)
    [fm] = _read_items(ops_env)
    assert fm["dedup_key"]["source"] == "weekly_stale"
    assert fm["evidence"]["refresh_period_h"] == pytest.approx(168.0)


def test_staleness_no_file_no_item(mod, ops_env, tmp_path):
    now = 2_000_000.0
    src = _FakeSource("never_pulled", tmp_path / "missing.txt", stale_days=1)
    mod.run_staleness_detector([src], now=now)   # 无文件 = 无内容年龄证据
    assert _read_items(ops_env) == []


def _mk_dir_source(tmp_path, name, stale_days, child_ages_s, dir_age_s, now):
    """目录型源(cn_isp isp/、cloud_ranges/ 同型:_path 指目录)。

    子文件 mtime 与目录 mtime 脱钩(重写子文件不动目录 mtime)——复现
    2026-10-03 线上判例形状:目录停在首建日、子文件当天刷新。
    """
    import os
    d = tmp_path / name
    d.mkdir()
    for i, age in enumerate(child_ages_s):
        f = d / f"feed_{i}.txt"
        f.write_text("x")
        os.utime(f, (now - age, now - age))
    os.utime(d, (now - dir_age_s, now - dir_age_s))
    return _FakeSource(name, d, stale_days)


def test_staleness_dir_fresh_children_no_item(mod, ops_env, tmp_path):
    """目录源回归(review 发现 1):目录 mtime 停在首建日(30 天旧)、子文件
    刚刷新 → 不产——内容 mtime = 目录内最新文件(_read_mtime 规范信号源),
    只看目录 mtime 会把新鲜多 feed 源误判超龄(线上判例:46 天误报)。"""
    now = 2_000_000.0
    src = _mk_dir_source(tmp_path, "dir_fresh_kids", stale_days=7,
                         child_ages_s=[3600], dir_age_s=30 * 86400, now=now)
    mod.run_staleness_detector([src], now=now)
    assert _read_items(ops_env) == []


def test_staleness_dir_all_children_stale_produces_item(mod, ops_env, tmp_path):
    """目录源子文件全旧超 2× 周期 → 产条;内容年龄 = 最新子文件 mtime
    (非目录 mtime,钉住取数路径)。"""
    now = 2_000_000.0
    newest = 2 * 7 * 86400 + 3600             # 337h > 2×168h 一小时
    src = _mk_dir_source(tmp_path, "dir_all_stale", stale_days=7,
                         child_ages_s=[newest, 3 * 7 * 86400],
                         dir_age_s=30 * 86400, now=now)
    mod.run_staleness_detector([src], now=now)
    [fm] = _read_items(ops_env)
    assert fm["dedup_key"]["source"] == "dir_all_stale"
    assert fm["evidence"]["content_age_h"] == pytest.approx(newest / 3600.0)
    assert fm["dedup_key"]["probe_class"] == "staleness"


# ══ _tasks 旁挂零侵入 ══════════════════════════════════════════════════

class _FakeTaskSource:
    """UpdateManager 可跑的最小源(test_tasks.FakeSource 同型)。"""

    def __init__(self, name, fail=False):
        self.name = name
        self.download_host = "h"
        self._fail = fail

    def download(self, token=None):
        if self._fail:
            raise RuntimeError("HTTP Error 403: Forbidden")

    def load(self):
        pass

    def rebuild(self):
        pass


def _make_manager(sources, concurrency=2):
    from ipdb._tasks import UpdateManager
    by_name = {s.name: s for s in sources}
    locks = {}

    def lock_for(n):
        locks.setdefault(n, threading.Lock())
        return locks[n]

    return UpdateManager(resolve_source=lambda n: by_name.get(n),
                         lock_for=lock_for, concurrency=concurrency)


def _wait_terminal(mgr, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = mgr.snapshot()
        if all(t["state"] in ("done", "failed", "cancelled")
               for t in snap["tasks"]) and snap["tasks"]:
            return snap
        time.sleep(0.02)
    return mgr.snapshot()


def test_on_terminal_default_none_zero_intrusion():
    mgr = _make_manager([_FakeTaskSource("ok_src")])
    assert mgr.on_terminal is None          # 未装配 = 位等价(缺省面)
    mgr.enqueue_one("ok_src")
    snap = _wait_terminal(mgr)
    assert snap["tasks"][0]["state"] == "done"


def test_hook_gets_readonly_snapshot_exactly_once():
    mgr = _make_manager([_FakeTaskSource("bad_src", fail=True)])
    seen = []
    mgr.on_terminal = seen.append
    t = mgr.enqueue_one("bad_src")
    snap = _wait_terminal(mgr)
    assert snap["tasks"][0]["state"] == "failed"
    assert len(seen) == 1
    td = seen[0]
    assert td["id"] == t.id                # to_dict() 快照(含 id/状态码)
    assert td["state"] == "failed"
    assert td["error_code"] == "download"
    mgr._settle(mgr._tasks[t.id])          # cancel/finally 双结算竞态再现
    assert len(seen) == 1, "_settled 幂等保证恰好一次"


def test_hook_exception_swallowed_state_machine_intact():
    mgr = _make_manager([_FakeTaskSource("bad_src", fail=True)])

    def boom(td):
        raise RuntimeError("detector down")

    mgr.on_terminal = boom
    bid = mgr.enqueue_batch(["bad_src"])
    snap = _wait_terminal(mgr)
    assert snap["tasks"][0]["state"] == "failed"   # 回调抛错不反噬状态机
    # 批次计数照常(批次完成后 _active_batch 已释放,直查批次本体)
    assert mgr._batches[bid].to_dict() == {"id": bid, "state": "done",
                                           "done": 1, "total": 1}


def test_manager_with_real_detector_item_appears_immediately(mod, ops_env):
    """spec #152 验收面:停用/失败真源 → 失败条目即时出现(装配即活)。"""
    mgr = _make_manager([_FakeTaskSource("spamhaus_drop", fail=True)])
    mgr.on_terminal = mod.make_download_fail_detector()
    mgr.enqueue_one("spamhaus_drop")
    snap = _wait_terminal(mgr)
    assert snap["tasks"][0]["state"] == "failed"   # 任务面照常(旁挂只读)
    [fm] = _wait_items(ops_env)                     # 条目随终态收口即时落盘
    assert fm["dedup_key"]["source"] == "spamhaus_drop"
    assert fm["action"] == "retry_download"


# ══ scheduler on_scan 旁挂 ═════════════════════════════════════════════

def test_scheduler_on_scan_hook_fires(monkeypatch):
    from ipdb import _scheduler
    from ipdb._scheduler import RefreshScheduler
    # 告警面兑错隔离:本测只钉 on_scan,告警周期整体 no-op(既有调度测试同型)
    monkeypatch.setattr(_scheduler._alerts, "evaluate",
                        lambda *a, **k: None)
    monkeypatch.setattr(_scheduler._alerts, "push", lambda *a, **k: None)
    monkeypatch.setattr(_scheduler._alerts, "prune", lambda *a, **k: None)
    monkeypatch.setattr(_scheduler._alerts, "_heartbeat_path",
                        lambda: None)
    calls = []
    sch = RefreshScheduler(manager=None,
                           enabled_offline_sources=lambda: [],
                           needs_rebuild_of=lambda s: False,
                           interval=1800,
                           on_scan=lambda sources, now: calls.append(
                               (list(sources), now)))
    sch.scan(now=123.0)
    assert calls == [([], 123.0)], "扫描尾恰一次回调 (sources, now)"
