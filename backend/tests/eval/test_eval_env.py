# backend/tests/eval/test_eval_env.py
"""S37:eval 环境隔离(spec 待办9)—— IP_RADAR_EVAL_ENV = monthly|gate|dev。

报告目录 base/<env>(base = IP_RADAR_EVAL_DIR 或默认 backend/data/eval);
rc_history(model 历史)随目录命名空间天然不跨环境混读;所有报告 JSON
顶层 eval_env 字段。默认 dev:base 目录从 data/eval 平铺变 data/eval/dev
是有意的破坏性变更(旧报告迁移非目标)。
"""
import json
from pathlib import Path

import pytest


def test_report_dir_env_namespace(tmp_path, monkeypatch):
    """report_dir() = base/<env>:monthly → base/monthly;未设 → base/dev。"""
    from ipdb._eval.__main__ import report_dir
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")
    assert report_dir() == tmp_path / "monthly"
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    assert report_dir() == tmp_path / "dev"


def test_monthly_run_lands_in_monthly_dir_with_env_field(tmp_path, monkeypatch):
    """env=monthly:write_report 落 base/monthly/,JSON 顶层 eval_env=monthly。"""
    from test_eval_cli import _CAND_IPS, _FakeBenign, _FakeRegistry
    from ipdb._eval.__main__ import run_for_source
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")
    reg = _FakeRegistry()
    reg.sources[0]._path = tmp_path / "cand.txt"
    reg.sources[0]._path.write_text("\n".join(_CAND_IPS) + "\n")
    md, js, _ = run_for_source("cand", registry=reg, corpus_path=tmp_path / "c.json",
                               benign=_FakeBenign())  # out_dir 缺省 → report_dir()
    assert md.parent == tmp_path / "monthly"
    rep = json.loads(Path(js).read_text())
    assert rep["eval_env"] == "monthly"


def test_rc_history_env_isolation(tmp_path, monkeypatch):
    """dev 默认不读 monthly 的 model 历史(monthly 读得到,证 fixture 非空)。"""
    from ipdb._eval.__main__ import _rc_history, report_dir
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    d = tmp_path / "monthly" / "model"
    d.mkdir(parents=True)
    (d / "model-20260901-010101.json").write_text(json.dumps(
        {"generated_at": "2026-09-01",
         "source_health": {"cand": {"rc": 17000, "stale": False}}}))
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    assert _rc_history("cand", report_dir() / "model") == []      # dev 不读 monthly
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")
    assert _rc_history("cand", report_dir() / "model") == [17000]


def test_invalid_env_fails_loud(tmp_path, monkeypatch):
    """非法 env 值 → ValueError(fail loud,不静默回落 dev)。"""
    from ipdb._eval.__main__ import report_dir
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "prod")
    with pytest.raises(ValueError, match="IP_RADAR_EVAL_ENV"):
        report_dir()


def test_render_json_eval_env_key_always_present():
    """schema 稳定:eval_env 键恒在;render_json 直调缺省 None(T2 run_seed 同款)。"""
    from ipdb._eval.metrics import Metric
    from ipdb._eval.report import render_json
    from ipdb._eval.verdict import Verdict
    v = Verdict(state="MARGINAL", benefit_high=False, cost_high=False,
                verified=False, insufficient=False)
    rep = render_json("cand", v, {"mc": Metric(0.0)})
    assert rep["eval_env"] is None
