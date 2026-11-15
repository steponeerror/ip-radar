# backend/tests/eval/test_eval_incident_replay.py
"""事故回放集(#351 / ADR 0021 决策5)测试:五腿绿面 + 防线改坏红面
+ 契约表接线。

红面证明 = 回归保护语义本体:用 monkeypatch 拆掉防线部件(curated 集
空置/谱系去重拆除/越窗放行拆除/排序键摊平/版本戳腿拆除/对照闸置零),
对应回放腿必须翻红——「防线若被改坏,回放红」不是声明而是被测行为。

夹具纪律:全部合成数据(对照 IP 用 TEST-NET-3 文档段 203.0.113.x),
零外发零网络;事故 IP(8.8.8.8/114.114.114.114)是 curated 防线真实
成员,原样在夹具里才能验防线(tests/sources/test_infra_noise_filter.py
同款纪律)。

第六红面(#351 评审 P2-2):对照闸拆除(CONTROL_MIN_HITS 置 0,对照
源池内零命中也放行=假零可出)→ 事故③对照闸腿红——其余五面之外,
这道「防假零」防线单独钉死。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval import contract as C
from ipdb._eval import incident_replay as IR
from ipdb._eval.contract import CONTRACT_PATH, load_contract, run_contract
from ipdb._sources import _infra_filter

ENV_SWITCH = "IP_RADAR_INFRA_NOISE_FILTER"

ALL_REPLAYS = [
    IR.replay_myip_ms_8888,
    IR.replay_dns114_false_corroboration,
    IR.replay_aggregator_derived_reversal,
    IR.replay_peeringdb_429_residue,
    IR.replay_reportedip_8888,
]


# ── 绿面:五腿全过,证据明细在 ───────────────────────────────────────

@pytest.mark.parametrize("fn", ALL_REPLAYS, ids=lambda f: f.__name__)
def test_replay_green(fn, monkeypatch):
    monkeypatch.setenv(ENV_SWITCH, "1")        # 环境确定性,不造假绿
    r = fn()
    assert r["pass"] is True, [c for c in r["checks"] if not c["ok"]]
    assert r["checks"], "读数须带证据明细(缺读数不虚构)"
    assert r["mechanism"] and r["defense"]     # 出处三件齐


def test_dns114_replay_records_known_gap_honestly():
    """事故②的纯 derived 互证语义今天无门:known_gap 必须如实显形,
    不发明门(报告面 = 覆盖账本,缺门不许静默)。"""
    r = IR.replay_dns114_false_corroboration()
    assert r["pass"] is True                   # 现役防线(载入+去重)绿
    assert r["known_gap"] and "corroborated" in r["known_gap"]
    assert "agg_share" in r["known_gap"]       # 披露面指向真源


# ── 红面:防线改坏 → 回放必红(回归保护证明) ────────────────────────

def test_red_when_curated_infra_set_emptied(monkeypatch):
    """curated 集空置(防线判式失明)→ 事故①②⑤三腿红。"""
    monkeypatch.setenv(ENV_SWITCH, "1")
    monkeypatch.setattr(_infra_filter, "curated_infra_addresses",
                        lambda: frozenset())
    for fn in (IR.replay_myip_ms_8888,
               IR.replay_dns114_false_corroboration,
               IR.replay_reportedip_8888):
        r = fn()
        assert r["pass"] is False, fn.__name__
        red = {c["name"] for c in r["checks"] if not c["ok"]}
        assert any("incident_ip" in n or "excluded_at_load" in n
                   for n in red), red


def test_red_when_lineage_dedup_dismantled(monkeypatch):
    """DERIVED_SOURCES 清空(聚合器不再派生去重)→ 事故②③评分面红。"""
    import ipdb._logodds as lo
    monkeypatch.setattr(lo, "DERIVED_SOURCES", set())
    r = IR.replay_dns114_false_corroboration()
    assert r["pass"] is False
    assert "scoring_dedup_drops_derived_echo" in {
        c["name"] for c in r["checks"] if not c["ok"]}
    r2 = IR.replay_aggregator_derived_reversal()
    assert r2["pass"] is False
    red2 = {c["name"] for c in r2["checks"] if not c["ok"]}
    assert "aggregators_in_runtime_derived_set" in red2
    assert "derived_echo_adds_no_independent_vote" in red2


def test_red_when_deadline_force_release_broken(monkeypatch):
    """越窗强制放行拆除(残局楔死变体,2026-10-11 事故形态回归)→ 事故④红。"""
    from ipdb._coldstart import ColdStartGate

    def broken_db_ready(self):
        building = self.coverage_building()
        if building and not self.episode:
            self.deadline = self.now() + self.window_sec()
        self.episode = building
        if not self.db_loaded():
            return False
        if building:            # 变体:残局在队即永持门,deadline 过期不放行
            return False
        return True

    monkeypatch.setattr(ColdStartGate, "db_ready", broken_db_ready)
    r = IR.replay_peeringdb_429_residue()
    assert r["pass"] is False
    assert "deadline_force_releases_past_window" in {
        c["name"] for c in r["checks"] if not c["ok"]}


def test_red_when_catchup_footprint_key_flattened(monkeypatch):
    """补账排序键摊平(缺失源不再最先收敛)→ 事故④红。"""
    import main
    monkeypatch.setattr(main, "_catchup_footprint", lambda source: 1)
    r = IR.replay_peeringdb_429_residue()
    assert r["pass"] is False
    assert "catchup_orders_missing_source_first" in {
        c["name"] for c in r["checks"] if not c["ok"]}


def test_red_when_harvest_rev_leg_broken(monkeypatch):
    """needs_convert 的 .rev 版本戳腿拆除(mtime-only 变体,#192 时代
    「代码演进不 bump mtime 的静默休眠」形态回归)→ 事故⑤迁移面红。"""
    from ipdb._sources import _lmdb as lm

    def mtime_only(raw_path, base):
        ptr = lm.ptr_path(base)
        if not ptr.exists():
            return True
        return ptr.stat().st_mtime < raw_path.stat().st_mtime

    monkeypatch.setattr(lm, "needs_convert", mtime_only)
    r = IR.replay_reportedip_8888()
    assert r["pass"] is False
    assert "stale_rev_forces_rematerialization" in {
        c["name"] for c in r["checks"] if not c["ok"]}


def test_red_when_control_abort_dismantled(monkeypatch):
    """对照闸拆除(#351 评审 P2-2,第六红面):CONTROL_MIN_HITS 置 0 =
    对照源池内零命中也放行,假零排他率数字可出 → 事故③对照闸腿红,
    且红面单归因(另两防线照绿)。"""
    from ipdb._eval import exclusive as _ex
    monkeypatch.setattr(_ex, "CONTROL_MIN_HITS", 0)
    r = IR.replay_aggregator_derived_reversal()
    assert r["pass"] is False
    red = {c["name"] for c in r["checks"] if not c["ok"]}
    assert red == {"exclusivity_probe_control_aborts_on_uncovered_pool"}, red


# ── 契约表接线:事故回归维度五行,func oracle 可解析可执行 ──────────

INCIDENT_IDS = {
    "incident-replay-myip-ms-8888",
    "incident-replay-dns114-false-corroboration",
    "incident-replay-aggregator-derived-reversal",
    "incident-replay-peeringdb-429-residue",
    "incident-replay-reportedip-8888",
}


def test_contract_table_has_five_incident_replay_rows():
    doc = load_contract(CONTRACT_PATH)
    rows = [r for r in doc["rows"] if r["dimension"] == "事故回归"]
    assert {r["id"] for r in rows} == INCIDENT_IDS
    for r in rows:
        assert r["verdict"] == "gate"
        assert r["trigger"] == "change"
        assert r["track"] == "baseline"
        assert r["oracle"]["kind"] == "func"
        assert callable(C._resolve_func(r["oracle"]["ref"]))
        assert "#351" in r["provenance"]        # 事故出处进表


def test_incident_row_runs_green_through_runner(tmp_path, monkeypatch):
    """单行迷你契约表端到端:func gate 腿读数带 pass,报告单 md 面
    「事故回归」维度可见(runner 接线,不新增第二套编排)。"""
    monkeypatch.setenv(ENV_SWITCH, "1")
    real = load_contract(CONTRACT_PATH)
    row = next(r for r in real["rows"] if r["id"] == "incident-replay-myip-ms-8888")
    table = tmp_path / "mini.json"
    table.write_text(json.dumps(
        {"schema": C.SCHEMA, "rows": [row]}, ensure_ascii=False),
        encoding="utf-8")
    report = run_contract(table, params={}, out_dir=tmp_path)
    leg = report["rows"][0]
    assert leg["status"] == "ok"
    assert leg["gate_pass"] is True
    md = Path(report["paths"]["md"]).read_text(encoding="utf-8")
    assert "事故回归" in md
    assert "myip-ms-8888" in md or "myip_ms" in md
    assert report["summary"]["n_gate_pass"] == 1
