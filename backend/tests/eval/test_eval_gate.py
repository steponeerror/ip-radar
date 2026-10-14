# backend/tests/eval/test_eval_gate.py
"""接入关运行器 run_gate(Q4 双口径, spec §3.1): 测接线与双口径语义。

库件(verdict/metrics/layered/significance/keysets)各有单测; 本文件用
fake reg 断言: ①两臂同语料(同 assets)同 run_seed 的配对 delta 数值;
②共识层装配后剔除候选键集贡献(spec §2.3 gate 场景, 两场景注记入报告);
③gate-<candidate>-<ts>.md 双口径两节显式分题(演示 B 判例措辞)+ F9
读数家族枚举头; ④verdict 8 态透传; ⑤eval_env=gate 强制(S37 fail-loud)。
接入关报告必附 PR(spec §3.1);触发集只升旗不自动动作(声明 r)。
禁综合分(F1): 断言任何层都不产单一综合分, 只有分层向量 + verdict。

T6 追加(S1-S4/S31 接线): ⑥强制人裁/OC 敏感带节(mandatory_review/bands
旗标行透传, R2 基础三态含内)+ conf 档消融诊断列(档位照 yardstick 实测
先例 conf≥70/≥90, 不入 F9 读数家族)+ 触发集输入键组装(truth 资产成员/
蜜罐声明/stratum oc/model unique_share/registry derived attr; 缺省不误旗)。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ipdb._eval.__main__ import CORPUS_PATH
from ipdb._eval.assets import AssetMeta, fingerprint, save_asset
from ipdb._eval.corpus import Corpus
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

    def __init__(self, sources, cand_set, fleet_set, hi_conf=frozenset()):
        self.sources = sources
        self.cand_set, self.fleet_set = set(cand_set), set(fleet_set)
        self.hi_conf = set(hi_conf)      # T6: per-IP 高置信(conf 档诊断列)
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
        conf = 90 if ip in self.hi_conf else 50
        return {"ip": ip, "classifications": {"phishing": {
            "type": "phishing", "verdict": "malicious", "verdict_conflict": False,
            "confidence": conf,
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


def _setup(tmp_path: Path, *, truth: bool = True, hi_conf=frozenset()):
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
        {"10.99.2.1", "10.99.2.2", "10.99.2.3"}, hi_conf=hi_conf)
    return reg, assets


def _run(tmp_path, monkeypatch, *, seed=42, truth=True, out_name="rep",
         hi_conf=frozenset()):
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    reg, assets = _setup(tmp_path, truth=truth, hi_conf=hi_conf)
    out = tmp_path / out_name
    return run_gate("cand", reg, out, run_seed=seed, assets_dir=assets,
                    benign=_FakeBenign()), reg, out


def _setup_trig(tmp_path, *, truth=True, cand_file_ips, cand_set, fleet_set,
                rc=1000, honeypot=False, derived=False):
    """T6 触发集接线 fixture: 布局可调(cand 文件=键集/语料采样源, cand_set
    =候选指控集, fleet_set=舰队恒指控集), 四层资产同 _setup。蜜罐/派生
    声明走源类属性(生产 registry 落地形态)。"""
    assets = tmp_path / "assets"
    if truth:
        _asset(assets / "truth", [f"10.0.0.{i}" for i in range(1, 5)], "truth")
    _asset(assets / "infra", [f"198.51.100.{i}" for i in range(1, 4)], "infra")
    _asset(assets / "neutral", [f"203.0.113.{i}" for i in range(1, 11)], "neutral")
    _asset(assets / "consensus", _CONS_CAND + _CONS_FLEET, "consensus")
    cand_file = tmp_path / "cand.txt"
    cand_file.write_text("\n".join(cand_file_ips) + "\n")
    fleet_file = tmp_path / "fleet.txt"
    fleet_file.write_text("\n".join(sorted(fleet_set)) + "\n")
    src = _FakeSource("cand", cand_file, rc=rc)
    if honeypot:
        src.honeypot_methodology = True   # S1 蜜罐方法学声明(源类属性)
    if derived:
        src.derived = True                # S3 谱系声明(R1-F1 DERIVED_SOURCES 灌装源)
    reg = _FakeRegistry([src, _FakeSource("fleet", fleet_file)],
                        set(cand_set), set(fleet_set))
    return reg, assets


def _run_trig(tmp_path, monkeypatch, reg, assets, *, seed=42):
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    return run_gate("cand", reg, tmp_path / "rep", run_seed=seed,
                    assets_dir=assets, benign=_FakeBenign())


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
    # F1 禁综合分: payload 无任何聚合分字段, 只有分层向量 + verdict;
    # T6 扩展恰两键(triggers/conf_tiers), F9 家族枚举保持 T4 口径
    assert set(res) == {"kind", "eval_env", "candidate", "generated_at",
                        "run_seed", "corpus", "consensus_scenario",
                        "candidate_stratum", "arms", "deltas", "families",
                        "triggers", "conf_tiers", "report"}
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


# ── T6: 触发集接线 + conf 档诊断列(S1-S4/S31, spec §3.1) ───────


def test_gate_triggers_default_zero_flags_and_inputs_recorded(tmp_path, monkeypatch):
    """默认 fixture: 四触发皆不评误 —— 舰队不在语料上指控(oc=0.0)、phishing
    单断言方垄断(unique_share=None)、真值层 delta p≈0.063>0.05 不显著、
    verdict POSITIVE-UNVERIFIED 不入基础三态。零旗标 = 显式空(节内哨兵行,
    非沉默);输入键全录(人裁可对读数复核)。"""
    res, _, _ = _run(tmp_path, monkeypatch)
    t = res["triggers"]
    assert set(t) == {"mandatory_review", "bands", "inputs"}
    assert t["mandatory_review"] == [] and t["bands"] == []
    assert t["inputs"] == {"candidate_keyset_n": 34, "truth_members_n": 4,
                           "honeypot_declared": False, "oc": 0.0,
                           "unique_share": None, "declared_derived": False}
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "## 强制人裁" in md and "无强制人裁旗标" in md
    assert "## OC 敏感带" in md and "无敏感带标注" in md
    # 报告头家族枚举保持 T4 口径(conf 档不入家族, S31)
    assert res["families"]["hypothesis_tested"] == [
        "layer_delta:truth", "layer_delta:infra",
        "layer_delta:neutral", "layer_delta:consensus"]


def test_gate_conf_tier_diagnostic_column(tmp_path, monkeypatch):
    """conf 档消融诊断列(S31): 档位照 yardstick 实测先例(conf≥70/≥90),
    自两臂 F10 快照再生(S29 免重查引擎);hi_conf=10.0.0.1(conf 90)→
    truth 层 ON 1/4、OFF 0/4, 其余层全 50 → 各档 0。"""
    res, _, _ = _run(tmp_path, monkeypatch, hi_conf={"10.0.0.1"})
    ct = res["conf_tiers"]
    assert set(ct) == {"truth", "infra", "neutral", "consensus"}
    tier_expect = {"off_hits": 0, "on_hits": 1, "rate_off": 0.0,
                   "rate_on": pytest.approx(0.25),
                   "rate_delta": pytest.approx(0.25)}
    assert ct["truth"]["n"] == 4
    for tier in ("70", "90"):
        assert ct["truth"]["tiers"][tier] == tier_expect
    assert ct["consensus"]["n"] == 6
    assert all(r["on_hits"] == 0 and r["off_hits"] == 0
               for r in ct["consensus"]["tiers"].values())
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "## conf 档消融诊断列" in md
    assert "conf≥70" in md and "conf≥90" in md
    assert "| truth | 4 | conf≥70 | 0 (0.0000) | 1 (0.2500) | 0.2500 |" in md


def test_gate_missing_truth_layer_s1_not_evaluated(tmp_path, monkeypatch):
    """键缺省不误旗: 候选键集 4/6 落在(不存在的)truth 成员上, 但 truth 资产
    缺 → truth_members 无定义 → S1 不评(T5 契约缺键→不评, 宁少算);
    conf 档该层 NO-LAYER 哨兵行。"""
    cand_file = [f"10.0.0.{i}" for i in range(1, 5)] + ["10.99.0.1", "10.99.0.2"]
    reg, assets = _setup_trig(tmp_path, truth=False, cand_file_ips=cand_file,
                              cand_set=set(cand_file), fleet_set=set())
    res = _run_trig(tmp_path, monkeypatch, reg, assets)
    assert res["deltas"]["truth"] is None
    assert res["conf_tiers"]["truth"] is None
    assert res["triggers"]["inputs"]["truth_members_n"] is None
    assert res["triggers"]["mandatory_review"] == []
    assert res["triggers"]["bands"] == []
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "| truth | — | NO-LAYER" in md


def test_gate_mandatory_review_base_s1_s3(tmp_path, monkeypatch):
    """强制人裁三旗共燃: 基础集(rc=0 → NO-DATA)+ S1(键集 4/6 ⊆ truth
    资产成员, containment=0.67>0.5 且非蜜罐声明)+ S3(fleet 全抄候选真值
    段, oc=4/min(6,4)=1.00≥0.9 且非声明派生)。R2 基础三态旗透传入 md。"""
    cand_file = [f"10.0.0.{i}" for i in range(1, 5)] + ["10.99.0.1", "10.99.0.2"]
    reg, assets = _setup_trig(tmp_path, cand_file_ips=cand_file,
                              cand_set=set(cand_file),
                              fleet_set={f"10.0.0.{i}" for i in range(1, 5)},
                              rc=0)
    res = _run_trig(tmp_path, monkeypatch, reg, assets)
    rows = res["triggers"]["mandatory_review"]
    assert [r[:2] for r in rows] == ["基础", "S1", "S3"]
    assert "NO-DATA" in rows[0] and "基础触发集" in rows[0]
    assert rows[1].startswith("S1") and "0.67" in rows[1]
    assert rows[2].startswith("S3") and "1.00" in rows[2]
    assert res["triggers"]["bands"] == []      # oc=1.0 ≥0.9 → 极端档非带
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "## 强制人裁" in md
    for row in rows:
        assert row in md
    # payload(JSON 件)同源携带
    js = json.loads(Path(res["report"]["json"]).read_text(encoding="utf-8"))
    assert js["triggers"]["mandatory_review"] == rows


def test_gate_oc_band_report_only(tmp_path, monkeypatch):
    """OC 敏感带: fleet 抄候选 5/6 + 一个语料 benchmark IP(自身 corpus 在
    案)→ oc=5/min(6,6)≈0.83 ∈ [0.7, 0.9) → band 行 report-only(不入
    mandatory_review, spec §3.1「报告不触发」)。"""
    bench_ip = Corpus.load(CORPUS_PATH).benchmark["blacklist"][0]
    cand_file = ["10.0.0.1", "10.0.0.2"] + [f"10.99.0.{i}" for i in range(1, 5)]
    reg, assets = _setup_trig(
        tmp_path, cand_file_ips=cand_file, cand_set=set(cand_file),
        fleet_set={"10.0.0.1", "10.0.0.2", "10.99.0.1", "10.99.0.2",
                   "10.99.0.3", bench_ip})
    res = _run_trig(tmp_path, monkeypatch, reg, assets)
    assert res["triggers"]["mandatory_review"] == []
    assert len(res["triggers"]["bands"]) == 1
    band = res["triggers"]["bands"][0]
    assert band.startswith("S3 OC 敏感带 0.7-0.9") and "0.83" in band
    assert "report-only" in band and "不触发人裁" in band
    md = Path(res["report"]["md"]).read_text(encoding="utf-8")
    assert "## OC 敏感带" in md and band in md


def test_gate_s2_quadrant_via_unique_share_wiring(tmp_path, monkeypatch):
    """S2 象限臂接线: unique_share 走 suite/model 落地口径(自有非垄断 pair
    无他源份额)——fleet 仅在语料 benchmark IP 上断言 phishing(ctype 非垄断),
    候选 6 pair 全独有 → unique_share=1.0 × oc=0.0<0.7 → 旗。"""
    bench_ip = Corpus.load(CORPUS_PATH).benchmark["blacklist"][0]
    cand_file = ["10.0.0.1", "10.0.0.2"] + [f"10.99.0.{i}" for i in range(1, 5)]
    reg, assets = _setup_trig(tmp_path, cand_file_ips=cand_file,
                              cand_set=set(cand_file), fleet_set={bench_ip})
    res = _run_trig(tmp_path, monkeypatch, reg, assets)
    assert res["triggers"]["inputs"]["unique_share"] == pytest.approx(1.0)
    assert res["triggers"]["inputs"]["oc"] == pytest.approx(0.0)
    rows = res["triggers"]["mandatory_review"]
    assert [r[:2] for r in rows] == ["S2"]
    assert "独有命中份额=1.0" in rows[0] and "0.00" in rows[0]
    assert "S2" in Path(res["report"]["md"]).read_text(encoding="utf-8")


def test_gate_s1_honeypot_and_s3_derived_exemptions(tmp_path, monkeypatch):
    """声明豁免接线: 源类属性 honeypot_methodology=True → S1 不旗(整抄也
    豁免);derived=True(R1-F1 DERIVED_SOURCES 灌装源)→ S3 极端档豁免。
    仅剩基础集一行。"""
    cand_file = [f"10.0.0.{i}" for i in range(1, 5)] + ["10.99.0.1", "10.99.0.2"]
    reg, assets = _setup_trig(
        tmp_path, cand_file_ips=cand_file, cand_set=set(cand_file),
        fleet_set={f"10.0.0.{i}" for i in range(1, 5)},
        rc=0, honeypot=True, derived=True)
    res = _run_trig(tmp_path, monkeypatch, reg, assets)
    assert res["triggers"]["inputs"]["honeypot_declared"] is True
    assert res["triggers"]["inputs"]["declared_derived"] is True
    assert [r[:2] for r in res["triggers"]["mandatory_review"]] == ["基础"]
    assert res["triggers"]["bands"] == []
