# backend/tests/eval/test_eval_canary.py
"""季度 canary 测试(S10, spec §3.2): 冻结判例 toggle 复跑对照期望。

契约(Phase 2 T7):
- KNOWN_CASES 冻结判例表: greensnow 结构性零 + threatfox POSITIVE
  (spec §8 S10 原文, 控制器裁定只钉两例不扩), 期望值随用例存储
  (冻结在代码, 非运行时读), 表不可变(tuple + frozen dataclass +
  MappingProxyType)。
- run_canary(reg, out_dir) -> {"all_match", "cases", ...}: 逐判例
  toggle 复跑(ablation.run_ablation 同款 OFF→ON), 每 case 记
  {case, expected, actual, matched}; 失配 → all_match=False +
  流程腐化告警行, **不自动修复**(声明 r 同款红线: 只告警)。
- 报告 canary-<ts>.md(eval_env=gate); S37 fail-loud: 显式 monthly/
  dev 拒跑, 未设 → 进程内钉 gate 退出还原。

全 fake reg/stub, 零网络零 DB。
"""
import json
import os
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ipdb._eval.canary import KNOWN_CASES, PRESENT, run_canary
from ipdb._eval.corpus import stable_seed

_ENV_KEY = "IP_RADAR_EVAL_ENV"

# 判例源原始文件成员(>20, 采样封顶 20 —— loop-prototype 环1 判例形态)
_GREENSNOW_IPS = [f"45.61.{i // 256}.{i % 256}" for i in range(1, 26)]
_THREATFOX_IPS = [f"141.98.{i}.10" for i in range(1, 26)]


class _FakeSource:
    """最小真源接口: .name/._path(采样走 corpus 正则提取同款)。"""

    def __init__(self, name, path):
        self.name = name
        self._path = path
        self.category = "threat"


class _FakeRegistry:
    """锚交换语义可关的假舰队(结构性零机制的可控腐化):

    - greensnow 成员: greensnow 启用 → greensnow 指控(谱系锚在场,
      firehol 被遮蔽); 关闭 → anchor_swap=True 时 firehol 复活顶班
      (loop-prototype 演示 B 逐 IP 翻转 {greensnow}→{firehol}),
      anchor_swap=False 时无人指控 → 结构性零不复现 = 腐化。
    - threatfox 成员: 启用 → threatfox 自有指控; 关闭 → 消失;
      threatfox_rot=True 时启用态也无指控(POSITIVE 判例自域效益
      蒸发 = 引擎看不见该源 = 腐化)。
    """

    def __init__(self, sources, *, anchor_swap=True, threatfox_rot=False):
        self.sources = sources
        self.anchor_swap = anchor_swap
        self.threatfox_rot = threatfox_rot
        self.disabled = set()
        self._gs = set(_GREENSNOW_IPS)
        self._tf = set(_THREATFOX_IPS)

    def lookup(self, ip, asof=None):
        acc = []
        if ip in self._gs:
            if "greensnow" not in self.disabled:
                acc.append("greensnow")
            elif self.anchor_swap:
                acc.append("firehol")   # 谱系锚交换: OFF 态顶班
        if (ip in self._tf and "threatfox" not in self.disabled
                and not self.threatfox_rot):
            acc.append("threatfox")
        if not acc:
            return {"ip": ip, "classifications": {}}
        return {"ip": ip, "classifications": {"spam": {
            "type": "spam", "verdict": "malicious",
            "details": [{"source": s, "verdict": "malicious"}
                        for s in acc]}}}

    def toggle(self, name, enabled):
        self.disabled = ((self.disabled - {name}) if enabled
                         else (self.disabled | {name}))


def _reg(tmp_path: Path, **kw) -> _FakeRegistry:
    gs = tmp_path / "greensnow.txt"
    gs.write_text("\n".join(_GREENSNOW_IPS) + "\n")
    tf = tmp_path / "threatfox.txt"
    tf.write_text("\n".join(_THREATFOX_IPS) + "\n")
    fleet = tmp_path / "firehol.txt"
    fleet.write_text("\n".join(_GREENSNOW_IPS) + "\n")  # 镜像对(OC=1.0 判例)
    return _FakeRegistry([_FakeSource("greensnow", gs),
                          _FakeSource("threatfox", tf),
                          _FakeSource("firehol", fleet)], **kw)


# ── 冻结判例表 ─────────────────────────────────────────────────


def test_known_cases_two_spec_cases_with_concrete_expectations():
    by_case = {kc.case: kc for kc in KNOWN_CASES}
    assert len(KNOWN_CASES) == 2
    # spec §8 S10 原文: greensnow 结构性零 + 一个 POSITIVE(控制器: threatfox)
    gs, tf = by_case["greensnow-structural-zero"], by_case["threatfox-positive"]
    assert gs.source == "greensnow" and tf.source == "threatfox"
    # 判例期望 = 具体读数断言: 结构性零 = 舰队命中集 ON/OFF 对称差 0
    assert gs.expected["fleet_hit_delta"] == 0
    assert gs.expected["own_accusing_off"] == 0
    # POSITIVE 冻结稳定属性 present(>0), 不冻具体计数(随数据刷新漂移)
    assert tf.expected["own_accusing_on"] == PRESENT
    assert tf.expected["own_accusing_off"] == 0


def test_known_cases_table_immutable():
    assert isinstance(KNOWN_CASES, tuple)
    with pytest.raises(TypeError):   # 期望映射只读(MappingProxyType)
        KNOWN_CASES[0].expected["fleet_hit_delta"] = 99
    with pytest.raises(FrozenInstanceError):   # 判例字段不可写
        KNOWN_CASES[0].case = "tampered"


# ── 判例匹配通过 ────────────────────────────────────────────────


def test_all_match_pass_writes_gate_report(tmp_path):
    out = tmp_path / "out"
    r = run_canary(_reg(tmp_path), out)
    assert r["all_match"] is True and r["alarms"] == []
    by_case = {c["case"]: c for c in r["cases"]}
    gs = by_case["greensnow-structural-zero"]
    # 采样 20 探针全指控 → 自有在场; OFF 态自有消失; firehol 顶班 → 对称差 0
    assert gs["actual"] == {"own_accusing_on": 20, "own_accusing_off": 0,
                            "fleet_hit_delta": 0}
    assert gs["matched"] is True
    tf = by_case["threatfox-positive"]
    assert tf["actual"] == {"own_accusing_on": 20, "own_accusing_off": 0}
    assert tf["matched"] is True
    # 探针确定性: stable_seed 名派生(sentinel 同款), 季度复跑可比
    assert gs["n_probes"] == 20 and gs["seed"] == stable_seed("greensnow")
    # 报告 canary-<ts>.md(report.py 同形时间戳), eval_env=gate
    mds = sorted(out.glob("canary-*.md"))
    assert len(mds) == 1 and re.fullmatch(
        r"canary-\d{8}-\d{6}\.md", mds[0].name)
    md = mds[0].read_text(encoding="utf-8")
    assert "eval_env=gate" in md
    assert "⚠" not in md   # 零告警行(节标题常在, 未触发≠未评估)
    js = json.loads(sorted(out.glob("canary-*.json"))[0]
                    .read_text(encoding="utf-8"))
    assert js["eval_env"] == "gate" and js["all_match"] is True
    # 复跑收尾复启(run_ablation finally 纪律): 无遗留禁用源
    reg = _reg(tmp_path)
    run_canary(reg, out)
    assert reg.disabled == set()


def test_report_has_sentinel_line_when_all_match(tmp_path):
    """零失配也显式留哨兵行(未触发 ≠ 未评估; gate 报告同纪律)。"""
    out = tmp_path / "out"
    r = run_canary(_reg(tmp_path), out)
    assert r["all_match"] is True
    md = next(iter(out.glob("canary-*.md"))).read_text(encoding="utf-8")
    assert "无失配" in md


# ── 期望失配 → all_match=False + 腐化告警行, 不自动修复 ────────


def test_structural_zero_not_reproduced_alarms(tmp_path):
    """firehol 不再顶班(锚机制腐化)→ 舰队命中集移动 → 告警。"""
    out = tmp_path / "out"
    r = run_canary(_reg(tmp_path, anchor_swap=False), out)
    assert r["all_match"] is False
    gs = next(c for c in r["cases"]
              if c["case"] == "greensnow-structural-zero")
    assert gs["matched"] is False
    # OFF 态舰队命中集清零 → 对称差 = 20(具体读数入案, 可回算)
    assert gs["actual"]["fleet_hit_delta"] == 20
    assert gs["actual"]["own_accusing_on"] == 20   # 该读数本身仍复现
    # threatfox 判例不受连坐: 自域判例独立复跑
    tf = next(c for c in r["cases"] if c["case"] == "threatfox-positive")
    assert tf["matched"] is True
    # 告警行措辞 = 流程腐化告警; 不自动修复 = 只告警无修复动作
    assert len(r["alarms"]) == 1
    assert "流程腐化" in r["alarms"][0] and "greensnow-structural-zero" \
        in r["alarms"][0]
    assert "不自动修复" in r["alarms"][0]
    md = next(iter(out.glob("canary-*.md"))).read_text(encoding="utf-8")
    assert "流程腐化" in md
    # 复跑唯一副作用 = toggle 复启(finally); 失配不触发任何修复
    reg = _reg(tmp_path, anchor_swap=False)
    run_canary(reg, out)
    assert reg.disabled == set()


def test_positive_case_rot_alarms(tmp_path):
    """threatfox 自有指控蒸发(引擎看不见源)→ POSITIVE 期望失配。"""
    r = run_canary(_reg(tmp_path, threatfox_rot=True), tmp_path / "out")
    assert r["all_match"] is False
    tf = next(c for c in r["cases"] if c["case"] == "threatfox-positive")
    assert tf["matched"] is False
    assert tf["actual"]["own_accusing_on"] == 0   # present(>0) 失配
    assert any("threatfox-positive" in a for a in r["alarms"])


def test_missing_source_fails_closed_as_mismatch(tmp_path):
    """判例源从 reg 消失 = 判例不可复跑 → fail-closed 记失配告警
    (无证据 ≠ 通过), actual=None 不冒充读数。"""
    reg = _reg(tmp_path)
    reg.sources = [s for s in reg.sources if s.name != "threatfox"]
    r = run_canary(reg, tmp_path / "out")
    assert r["all_match"] is False
    tf = next(c for c in r["cases"] if c["case"] == "threatfox-positive")
    assert tf["matched"] is False and tf["actual"] is None
    assert any("threatfox" in a for a in r["alarms"])
    md = next(iter((tmp_path / "out").glob("canary-*.md")))
    assert "流程腐化" in md.read_text(encoding="utf-8")


def test_empty_raw_file_fails_closed(tmp_path):
    """原始文件空 → 无探针可复跑 → fail-closed 失配(无证据≠通过)。"""
    reg = _reg(tmp_path)
    for s in reg.sources:
        if s.name == "greensnow":
            s._path.write_text("")
    r = run_canary(reg, tmp_path / "out")
    gs = next(c for c in r["cases"]
              if c["case"] == "greensnow-structural-zero")
    assert gs["matched"] is False and gs["actual"] is None
    assert r["all_match"] is False


# ── eval_env=gate 强制(S37 fail-loud, gate 同款) ──────────────


def test_env_monthly_rejected_fail_loud(tmp_path, monkeypatch):
    monkeypatch.setenv(_ENV_KEY, "monthly")
    with pytest.raises(ValueError, match="gate"):
        run_canary(_reg(tmp_path), tmp_path / "out")


def test_env_unset_pins_gate_and_restores(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV_KEY, raising=False)
    r = run_canary(_reg(tmp_path), tmp_path / "out")
    assert r["eval_env"] == "gate"
    assert _ENV_KEY not in os.environ   # 退出还原, 不污染进程
