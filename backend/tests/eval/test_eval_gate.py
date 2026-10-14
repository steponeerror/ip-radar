# backend/tests/eval/test_eval_gate.py
"""接入关运行器 run_gate(Q4 双口径, spec §3.1): 测接线与双口径语义。

库件(verdict/metrics/layered/significance/keysets)各有单测; 本文件用
fake reg 断言: ①两臂同语料(同 assets)同 run_seed 的配对 delta 数值;
②共识层装配后剔除候选键集贡献(spec §2.3 gate 场景, 两场景注记入报告);
③gate-<candidate>-<ts>.md 双口径两节显式分题(演示 B 判例措辞)+ F9
读数家族枚举头; ④verdict 8 态透传; ⑤eval_env=gate 强制(S37 fail-loud)。
禁综合分(F1): 断言任何层都不产单一综合分, 只有分层向量 + verdict。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ipdb._eval.assets import AssetMeta, fingerprint, save_asset
from ipdb._eval.gate import run_gate

# 候选文件主段 30 IP(≥ N_FLOOR=20, verdict 不进 INSUFFICIENT-SAMPLE)
_CAND_FILE_IPS = [f"10.99.0.{i}" for i in range(1, 31)]
# 共识层资产里的候选键集成员(4, 回声项 —— 不剔除会灌大共识 delta)+ 舰队成员(6)
_CONS_CAND = [f"10.99.1.{i}" for i in range(1, 5)]
_CONS_FLEET = [f"10.99.2.{i}" for i in range(1, 7)]


class _FakeSource:
    """真 .name/._path/.classification_type/.health —— run_for_source 与
    keysets._source_ips 都要读(链上真源对象契约, test_eval_cli 同款)。"""

    def __init__(self, name, path, rc=1000):
        self.name = name
        self._path = path
        self.classification_type = "phishing"
        self._rc = rc

    def query(self, ip):
        return []

    def health(self):
        from types import SimpleNamespace
        return SimpleNamespace(record_count=self._rc, is_stale=False)


class _FakeBenign:
    """离线假 checker(run_for_source 同款 DI: 免真 warninglists 加载)。"""

    def overall_hit_pct(self, ips): return 0.0

    def hit_pct(self, ips): return {}


class _FakeRegistry:
    """两臂唯变因素 = 候选启停(Q14 配对设计)。

    cand 启用 → cand_set 指控; fleet 恒指控 fleet_set(两臂同, delta 全
    归因候选)。载荷 = to_dict 生产契约: metrics 读 sources[], layered
    读组级 verdict + details[](两口径同真源, 评测硬化条款)。"""

    def __init__(self, sources, cand_set, fleet_set):
        self.sources = sources
        self.cand_set, self.fleet_set = set(cand_set), set(fleet_set)
        self.disabled = set()
        self.asof_seen = []

    def lookup(self, ip, asof=None):
        if asof is not None:
            self.asof_seen.append(asof)
        acc = []
        if "cand" not in self.disabled and ip in self.cand_set:
            acc.append("cand")
        if ip in self.fleet_set:
            acc.append("fleet")
        if not acc:
            return {"ip": ip, "classifications": {}}
        return {"ip": ip, "classifications": {"phishing": {
            "type": "phishing", "verdict": "malicious", "verdict_conflict": False,
            "confidence": 50,
            "details": [{"source": s, "verdict": "malicious"} for s in acc],
            "sources": [{"source": s} for s in acc]}}}

    def toggle(self, name, enabled):
        self.disabled = ((self.disabled - {name}) if enabled
                         else (self.disabled | {name}))


def _asset(dir_: Path, members, kind):
    save_asset(dir_, members, AssetMeta(
        version="v-test", kind=kind, fingerprint=fingerprint(members),
        member_count=len(members), params={}, eval_env="monthly",
        created_at="2026-10-01"))          # F2 执行锚时点(两臂同锚)


def _setup(tmp_path: Path, *, truth: bool = True):
    """四层资产 + fake reg。指控布局:
    - cand 指控: 自文件 34 IP + truth 2/4 + neutral 2/10 + 舰队 10.99.2.1
      (fleet 并证 → ON 臂 k=2)与 10.99.2.4;
    - fleet 恒指控: 10.99.2.{1,2,3}(共识层 OFF 臂 3 命中的来源)。"""
    assets = tmp_path / "assets"
    if truth:
        _asset(assets / "truth", [f"10.0.0.{i}" for i in range(1, 5)], "truth")
    _asset(assets / "infra", [f"198.51.100.{i}" for i in range(1, 4)], "infra")
    _asset(assets / "neutral", [f"203.0.113.{i}" for i in range(1, 11)], "neutral")
    _asset(assets / "consensus", _CONS_CAND + _CONS_FLEET, "consensus")
    cand_file = tmp_path / "cand.txt"
    cand_file.write_text("\n".join(_CAND_FILE_IPS + _CONS_CAND) + "\n")
    fleet_file = tmp_path / "fleet.txt"
    fleet_file.write_text("\n".join(_CONS_FLEET) + "\n")
    reg = _FakeRegistry(
        [_FakeSource("cand", cand_file), _FakeSource("fleet", fleet_file)],
        set(_CAND_FILE_IPS) | set(_CONS_CAND) | {
            "10.0.0.1", "10.0.0.2", "203.0.113.1", "203.0.113.2",
            "10.99.2.1", "10.99.2.4"},
        {"10.99.2.1", "10.99.2.2", "10.99.2.3"})
    return reg, assets


def _run(tmp_path, monkeypatch, *, seed=42, truth=True, out_name="rep"):
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    reg, assets = _setup(tmp_path, truth=truth)
    out = tmp_path / out_name
    return run_gate("cand", reg, out, run_seed=seed, assets_dir=assets,
                    benign=_FakeBenign()), reg, out


def test_gate_dual_caliber_deltas_and_consensus_exclusion(tmp_path, monkeypatch):
    res, reg, out = _run(tmp_path, monkeypatch)
    # ⑤ 报告双件落 out_dir, eval_env=gate
    assert Path(res["report"]["md"]).is_file() and Path(res["report"]["json"]).is_file()
    assert Path(res["report"]["md"]).name.startswith("gate-cand-")
    assert res["eval_env"] == "gate" and res["run_seed"] == 42

    # ② 两臂同语料: 各层 n(共识层 10-4=6, 剔除后口径)
    d = res["deltas"]
    assert (d["truth"]["n"], d["infra"]["n"], d["neutral"]["n"],
            d["consensus"]["n"]) == (4, 3, 10, 6)
    # ③ 配对 delta 数值(手算期望: ON-OFF 命中数)
    assert d["truth"]["rate_delta"] == pytest.approx(0.5)      # 2/4 - 0/4
    assert d["neutral"]["rate_delta"] == pytest.approx(0.2)    # 2/10 - 0/10
    assert d["consensus"]["rate_delta"] == pytest.approx(1 / 6)  # 4/6 - 3/6
    assert d["infra"]["rate_delta"] == 0.0                     # 两臂同 0
    assert d["truth"]["stats"]["paired_bootstrap"]["delta"] == pytest.approx(0.5)
    assert d["truth"]["stats"]["mcnemar"] == {"b": 2, "c": 0, "p": 0.5}
    assert d["consensus"]["stats"]["mcnemar"] == {"b": 1, "c": 0, "p": 1.0}
    assert d["infra"]["stats"]["mcnemar"]["p"] == 1.0
    # ①排除证明(数值面): 不剔除共识 delta 会是 8/10-3/10=0.5, 实得 1/6
    assert res["consensus_scenario"]["excluded_n"] == 4
    assert res["consensus_scenario"]["candidate_keyset_n"] == 34
    note = " ".join(res["arms"]["on"]["intersection_audit"]["consensus"]["notes"])
    assert "excluded 4 candidate-keyset ips" in note
    assert "gate=排除候选" in note and "monthly=全舰队" in note  # §2.3 两场景注记

    # ④ k 族直方图位移(描述性): 共识 ON {1:3, 2:1} vs OFF {1:3}
    k = d["consensus"]["k_all"]
    assert k["on"] == {1: 3, 2: 1} and k["off"] == {1: 3}
    assert k["delta_hist"] == {1: 0, 2: 1} and k["mean_delta"] == pytest.approx(0.25)
    assert d["neutral"]["k_all"]["delta_hist"] == {1: 2}      # 2 IP 各 1 源
    assert d["neutral"]["k_all"]["mean_delta"] is None        # OFF 臂零命中 → 无定义

    # ① verdict 8 态透传(字段全量, 不截断不降档)
    v = res["candidate_stratum"]["verdict"]
    assert v["state"] == "POSITIVE-UNVERIFIED"
    assert {"state", "benefit_high", "cost_high", "verified", "insufficient",
            "reason", "suspicion_flags", "action"} <= set(v)

    # md 双口径两节显式分题(演示 B 判例措辞)+ F9 家族枚举头
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "## ① candidate-stratum 自域判别力" in md
    assert "## ② 四层舰队净影响" in md
    assert "是两个问题" in md and v["state"] in md
    assert "读数家族" in md and "conf 档不入家族" in md
    assert "gate=排除候选" in md and "月轮=全舰队" in md
    # F1 禁综合分: payload 无任何聚合分字段, 只有分层向量 + verdict
    assert set(res) == {"kind", "eval_env", "candidate", "generated_at",
                        "run_seed", "corpus", "consensus_scenario",
                        "candidate_stratum", "arms", "deltas", "families",
                        "report"}
    assert set(res["deltas"]) == {"truth", "infra", "neutral", "consensus"}

    # F10 两臂快照 + F2 执行锚(truth created_at 锚定, 两臂同值)+ 候选复启
    snaps = list((out / "snapshots").glob("gate-cand-*-off/*.jsonl.gz"))
    assert {p.name.removesuffix(".jsonl.gz") for p in snaps} == {
        "truth", "infra", "neutral", "consensus"}
    assert reg.asof_seen and len(set(reg.asof_seen)) == 1
    assert reg.asof_seen[0] == datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
    assert "cand" not in reg.disabled


def test_gate_same_seed_reproducible(tmp_path, monkeypatch):
    """同 run_seed 两跑 → delta(含 bootstrap CI)逐字节同(S36 复现纪律)。"""
    res1, _, _ = _run(tmp_path / "a", monkeypatch, seed=7, out_name="rep")
    res2, _, _ = _run(tmp_path / "b", monkeypatch, seed=7, out_name="rep")
    assert (json.dumps(res1["deltas"], sort_keys=True)
            == json.dumps(res2["deltas"], sort_keys=True))
    assert res1["candidate_stratum"]["verdict"] == res2["candidate_stratum"]["verdict"]


def test_gate_missing_truth_layer_no_layer_sentinel(tmp_path, monkeypatch):
    """缺 truth 资产 = NO-LAYER 哨兵(缺层≠0 层): 该层 delta=None, 报告照发。"""
    res, _, _ = _run(tmp_path, monkeypatch, truth=False)
    assert res["deltas"]["truth"] is None
    assert res["arms"]["off"]["layers"]["truth"]["status"] == "NO-LAYER"
    assert res["arms"]["off"]["degraded"] is True
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "NO-LAYER" in md and "缺层≠0 层" in md
    assert res["deltas"]["neutral"]["rate_delta"] == pytest.approx(0.2)  # 其余层照算


def test_gate_forces_gate_env(tmp_path, monkeypatch):
    """eval_env=gate 强制: 显式 monthly → 拒跑; 未设 → 钉 gate(含嵌套
    run_for_source 报告)且进程环境还原。"""
    reg, assets = _setup(tmp_path)
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")
    with pytest.raises(ValueError, match="gate"):
        run_gate("cand", reg, tmp_path / "rep", run_seed=1, assets_dir=assets,
                 benign=_FakeBenign())
    monkeypatch.delenv("IP_RADAR_EVAL_ENV")
    res = run_gate("cand", reg, tmp_path / "rep", run_seed=1, assets_dir=assets,
                   benign=_FakeBenign())
    assert json.loads(Path(res["report"]["json"]).read_text())["eval_env"] == "gate"
    # 嵌套 candidate-stratum 报告也带 gate 标签(不串 dev)
    nested = next((tmp_path / "rep").glob("cand-*.json"))
    assert json.loads(nested.read_text())["eval_env"] == "gate"
    assert os.environ.get("IP_RADAR_EVAL_ENV") is None       # 退出还原


def test_gate_verdict_insufficient_sample_passthrough(tmp_path, monkeypatch):
    """8 态透传第二态: 候选触达 < N_FLOOR → INSUFFICIENT-SAMPLE 原样进
    payload 与 md ①节(run_gate 不吞不降档)。"""
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    reg, assets = _setup(tmp_path)
    (tmp_path / "cand.txt").write_text("\n".join(_CAND_FILE_IPS[:3]) + "\n")
    res = run_gate("cand", reg, tmp_path / "rep", run_seed=3, assets_dir=assets,
                   benign=_FakeBenign())
    assert res["candidate_stratum"]["verdict"]["state"] == "INSUFFICIENT-SAMPLE"
    assert res["candidate_stratum"]["verdict"]["insufficient"] is True
    assert "INSUFFICIENT-SAMPLE" in Path(res["report"]["md"]).read_text()
