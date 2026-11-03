"""评估面恒禁用机制(spec 2026-11-02 §3,honyport #272)。

eval_excluded 源声明 → 评估 CLI(python -m ipdb._eval 全模式)启动即
强制禁用;单源/--gate/--sentinel 对禁用源 fail-loud 拒跑(消融 finally
会 re-enable 候选,恒禁用红线不允许该路径存在);--all 出禁用行不评估;
月报记分卡单列「评估禁用源」行 + 导语注脚。fixtures 全 fake(零 DB)。
"""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import ipdb._eval.__main__ as M
from ipdb._eval.monthly import compose_monthly_md, render_scorecard


class _FakeSource:
    def __init__(self, name, eval_excluded=False, tier="B"):
        self.name = name
        self.eval_excluded = eval_excluded
        self.provenance_tier = tier


class _FakeRegistry:
    """toggle 记录调用(消融同语义:重赋值集合);load_db no-op。"""

    def __init__(self, sources):
        self.sources = sources
        self.disabled = set()
        self.toggled = []

    def load_db(self):
        pass

    def lookup(self, ip):
        return {"ip": ip, "classifications": {}}

    def toggle(self, name, enabled):
        self.toggled.append((name, enabled))
        self.disabled = (self.disabled - {name}) if enabled \
            else (self.disabled | {name})


# ── force_eval_excluded(启动即强制禁用)────────────────────────


def test_force_eval_excluded_toggles_only_excluded():
    reg = _FakeRegistry([_FakeSource("turris_greylist"),
                         _FakeSource("honyport", eval_excluded=True)])
    excluded = M.force_eval_excluded(reg)
    assert excluded == {"honyport"}
    assert reg.toggled == [("honyport", False)]      # 只动禁用源
    assert "honyport" in reg.disabled


def test_force_eval_excluded_noop_when_none():
    """无 eval_excluded 源 → 零调用,现有行为零变化。"""
    reg = _FakeRegistry([_FakeSource("turris_greylist")])
    assert M.force_eval_excluded(reg) == set()
    assert reg.toggled == []


# ── CLI 面(monkeypatch _real_registry,test_eval_gate_cli 同款缝)──


def _patch(monkeypatch, reg):
    monkeypatch.setattr(M, "_real_registry", lambda: reg)


def test_cli_single_source_refused(tmp_path, monkeypatch, capsys):
    """单源评估禁用源 → --json 信封 rc=1(无 θ/消融/verdict 记录)。"""
    _patch(monkeypatch, _FakeRegistry(
        [_FakeSource("honyport", eval_excluded=True)]))
    with pytest.raises(SystemExit) as ei:
        M.main(["honyport", "--json"])
    assert ei.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "eval_excluded_source"


def test_cli_single_source_refused_text(tmp_path, monkeypatch, capsys):
    _patch(monkeypatch, _FakeRegistry(
        [_FakeSource("honyport", eval_excluded=True)]))
    with pytest.raises(SystemExit) as ei:
        M.main(["honyport"])
    assert ei.value.code == 1
    assert "拒绝" in capsys.readouterr().err


def test_cli_all_prints_disabled_row_no_eval(tmp_path, monkeypatch, capsys):
    """--all:源清单含禁用行,honyport 无任何评估调用(验收 §6-5)。"""
    _patch(monkeypatch, _FakeRegistry(
        [_FakeSource("turris_greylist"), _FakeSource("honyport",
                                                     eval_excluded=True)]))
    calls = []

    def _stub_run(name, registry=None, **kw):
        calls.append(name)
        return (Path("/dev/null"), Path("/dev/null"),
                SimpleNamespace(state="PASS"))

    monkeypatch.setattr(M, "run_for_source", _stub_run)
    M.main(["--all"])
    out = capsys.readouterr().out
    assert "honyport" in out and "eval-excluded" in out   # 禁用行
    assert calls == ["turris_greylist"]                   # 只评估非禁用源


def test_cli_gate_refused_before_mirror(tmp_path, monkeypatch, capsys):
    """--gate 禁用源 → 拒跑且不触镜像前置(便宜失败)。"""
    import ipdb._eval.gate_mirror as gm

    def _no_mirror(*a, **kw):
        raise AssertionError("ensure_gate_mirror must not run")

    monkeypatch.setattr(gm, "ensure_gate_mirror", _no_mirror)
    _patch(monkeypatch, _FakeRegistry(
        [_FakeSource("honyport", eval_excluded=True)]))
    with pytest.raises(SystemExit) as ei:
        M.main(["--gate", "honyport"])
    assert ei.value.code == 1
    assert "eval-excluded" in capsys.readouterr().err


def test_cli_sentinel_refused(tmp_path, monkeypatch, capsys):
    _patch(monkeypatch, _FakeRegistry(
        [_FakeSource("honyport", eval_excluded=True)]))
    with pytest.raises(SystemExit) as ei:
        M.main(["--sentinel", "honyport"])
    assert ei.value.code == 1
    assert "eval-excluded" in capsys.readouterr().err


# ── 月报记分卡(S28)单列行 + 导语注脚 ──────────────────────────


def _model_report(gen, scores, movers):
    return {"kind": "model", "generated_at": gen,
            "scores": [{"source": n, "theta": t} for n, t in scores],
            "movers": movers}


def test_scorecard_excluded_source_single_disabled_row():
    """禁用源不出 θ/冗余度/均分行,单列「评估禁用源: honyport」。"""
    hist = [_model_report("2026-10-01", [("turris_greylist", 0.5)],
                          ["turris_greylist"])]
    rows = render_scorecard(
        hist, [_FakeSource("turris_greylist"),
               _FakeSource("honyport", eval_excluded=True, tier="A")],
        oc_latest={"honyport": 0.9},        # 即使有历史 OC 也不出读数
        today=date(2026, 10, 14))
    by = {r[0]: r for r in rows}
    assert by["评估禁用源: honyport"] == ("评估禁用源: honyport",
                                          "—", "—", "—", "A")
    assert "honyport" not in by                             # 无普通行
    assert by["turris_greylist"][1] != "—"


def test_md_intro_footnote_lists_excluded_sources():
    md = compose_monthly_md(
        {"layers": {}}, [], [], [], [], {"eval_env": "monthly"},
        eval_excluded_names=["honyport"])
    assert "评估融合读数不含评估禁用源" in md
    assert "honyport" in md
    assert "系统性低于线上" in md


def test_md_no_footnote_when_none_excluded():
    """无禁用源 → 无注脚行(schema-stable,既有调用零变化)。"""
    md = compose_monthly_md({"layers": {}}, [], [], [], [],
                            {"eval_env": "monthly"})
    assert "评估融合读数不含评估禁用源" not in md
