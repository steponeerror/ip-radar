# backend/tests/core/test_fusion_replay_gate_rc.py
"""fusion_replay_gate rc 机检化守卫(#193 C5,评审D P1-1:回放门=死门)。

契约(TDD 先行):main() 退出码按判据聚合——
  rc 0 = 全 PASS 且语料充分;
  rc 1 = 任一腿真 FAIL(C2/C3/C4);真 FAIL 优先于语料不足(带病≠没测);
  rc 2 = 无真 FAIL 但语料不足/空语料(vacuous PASS 不得冒充绿,空语料
         下限护栏;与真 FAIL 区分——消费者可分「红」与「没测成」)。

seam 两层:gate_rc 纯函数 = rc 聚合单源(判据输入→rc);空目录端到端
subprocess = main() 接线 seam(真实形状:0 指控源 → n_probe=0 → C2 空
vacuous PASS / C3、C4 pass=None → rc 2;修复前恒 0 = 死门本证)。
全仓复核(#193):无既有 rc 消费方依赖恒 0(仅 import smoke 测试与
GLOSSARY 锚),rc 语义变更安全。
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fusion_replay_gate  # noqa: E402


def test_gate_rc_all_pass_with_sufficient_corpus_is_zero():
    rc, fails, insuff = fusion_replay_gate.gate_rc(
        c2_pass=True, c2_strict_n=2361, c2_loose_n=2500,
        c3_pass=True, c4_pass=True)
    assert rc == 0
    assert fails == [] and insuff == []


def test_gate_rc_any_leg_fail_returns_one():
    # 真 FAIL 优先:即使语料同时不足,带病不折衷成「没测成」
    for kw in ({"c2_pass": False},
               {"c3_pass": False},
               {"c4_pass": False}):
        args = dict(c2_pass=True, c2_strict_n=100, c2_loose_n=100,
                    c3_pass=True, c4_pass=True)
        args.update(kw)
        rc, fails, _ = fusion_replay_gate.gate_rc(**args)
        assert rc == 1, f"{kw} 应 rc=1(真 FAIL 优先于语料不足)"
        assert fails, f"{kw} 应点名 FAIL 腿"


def test_gate_rc_empty_corpus_returns_two_not_zero():
    # 空语料护栏:0 探测 IP 时 C2 的 PASS 是 vacuous —— 不得冒充绿
    rc, fails, insuff = fusion_replay_gate.gate_rc(
        c2_pass=True, c2_strict_n=0, c2_loose_n=0,
        c3_pass=True, c4_pass=True)
    assert rc == 2
    assert "C2" in insuff


def test_gate_rc_partial_c2_corpus_counts_as_insufficient():
    # 严格口径语料在而宽口径空(或反之)= 判据半 vacuous,仍 rc 2
    rc, _, insuff = fusion_replay_gate.gate_rc(
        c2_pass=True, c2_strict_n=50, c2_loose_n=0,
        c3_pass=True, c4_pass=True)
    assert rc == 2 and "C2" in insuff


def test_gate_rc_na_legs_are_insufficient_not_fail():
    # C3 benign 语料空 / C4 ρ NaN → pass=None = 「没测成」,rc 2 非 1
    rc, fails, insuff = fusion_replay_gate.gate_rc(
        c2_pass=True, c2_strict_n=100, c2_loose_n=100,
        c3_pass=None, c4_pass=None)
    assert rc == 2
    assert fails == [] and set(insuff) == {"C3", "C4"}


def test_main_empty_data_dir_end_to_end_returns_two(tmp_path):
    """接线 seam:空数据目录跑真 main()(7s 级)——0 指控源/0 探测 IP,
    今日(修复前)恒 return 0 = 死门;契约后 rc 2(语料不足≠绿)。"""
    data = tmp_path / "empty-data"
    data.mkdir()
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "fusion_replay_gate.py"),
         "--data", str(data), "--report", str(tmp_path / "r.md")],
        capture_output=True, text=True, timeout=180)
    assert r.returncode == 2, (
        f"空语料须 rc=2(语料不足,与真 FAIL 区分),实得 {r.returncode}\n"
        f"stderr 尾: {r.stderr[-400:]}")
