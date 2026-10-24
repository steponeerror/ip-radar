# backend/tests/eval/test_eval_northstar.py
"""能力轨北星观测件(#185,spec #180 Q5a;STANDARD.md E-5)。

北星=「整体情报更准」的可计算代理,v0 两腿:锚集全绿率(读月轮
anchors-*.json 工件,回归轨判定门同源件)+ 谱系去重后 corroborated 精度
(四层读数 k_all 直方图 k≥2 求和,层互斥无回声双计;派生簇独证占比
折减 = F6 derived_only_corroboration)。**只观测不持门**:不设阈值、
不进 CI、不拦月轮退出码——测试钉住「N/A 哨兵不虚构」与「一行」形态。
fixtures 手算独立真值(勿用被测实现回算):
- kcorr = (5+2) + 4 + (str 键同容 6) = 17;precision = (17−3)/17 = 14/17。
- 锚 17/19 = 0.894736…;环比 = (17/19 − 1)×100 = −10.526…pp。
"""
import json
from datetime import date
from pathlib import Path

import pytest

from ipdb._eval.monthly import (
    compose_monthly_md,
    load_anchor_green,
    load_prev_northstar,
    northstar_record,
    render_northstar,
)

_RATE_17_19 = 17 / 19


def _readout(**over):
    ro = {
        "layers": {
            "truth": {"status": "OK", "k_all": {1: 7, 2: 5, 3: 2}},
            "infra": {"status": "NO-LAYER", "k_all": None},
            "neutral": {"status": "OK", "k_all": {2: 4}},
            # str 键直方图(JSON 往返形状)同容:int 强转口径一致
            "consensus": {"status": "OK", "k_all": {"1": 9, "2": 6}},
        },
        "derived_only_corroboration": 3,
    }
    ro.update(over)
    return ro


def _readout_no_layers(**over):
    ro = {
        "layers": {k: {"status": "NO-LAYER", "k_all": None}
                   for k in ("truth", "infra", "neutral", "consensus")},
        "derived_only_corroboration": 0,
    }
    ro.update(over)
    return ro


_ANCHOR_PREV = {"artifact": "anchors-20261001-000000.json",
                "n_total": 19, "n_fail": 0, "rate": 1.0}
_ANCHOR_CUR = {"artifact": "anchors-20261101-000000.json",
               "n_total": 19, "n_fail": 2, "rate": _RATE_17_19}
_PREV_NS = {"kind": "northstar", "run_id": "r1",
            "corroborated": {"n": 15, "derived_only": 4, "precision": 0.70}}


# ── northstar_record: 两代理纯计算 ─────────────────────────────


def test_record_corroborated_from_k_hist_ok_layers_only():
    ns = northstar_record(_readout(), [_ANCHOR_PREV, _ANCHOR_CUR], _PREV_NS,
                          run_id="r2", eval_env="monthly",
                          today=date(2026, 11, 1))
    # NO-LAYER 层(infra)不入分子;k≥2 直方图桶求和:5+2+4+6=17
    assert ns["corroborated"] == {"n": 17, "derived_only": 3,
                                  "precision": 14 / 17}
    assert ns["anchor_green"] == _ANCHOR_CUR
    assert ns["anchor_prev"] == _ANCHOR_PREV
    assert ns["anchor_green_mom_pp"] == pytest.approx((_RATE_17_19 - 1) * 100)
    assert ns["corroborated_precision_mom_pp"] == pytest.approx(
        (14 / 17 - 0.70) * 100)
    assert ns["kind"] == "northstar" and ns["run_id"] == "r2"
    assert ns["eval_env"] == "monthly" and ns["generated_at"] == "2026-11-01"


def test_record_zero_corroborated_is_none_not_fabricated():
    # 零 corroborated 读数 → precision=None(N/A),不发明 0%/100%
    ns = northstar_record(_readout_no_layers(), [_ANCHOR_CUR], _PREV_NS,
                          run_id="r9", eval_env="monthly",
                          today=date(2026, 11, 1))
    assert ns["corroborated"]["n"] == 0
    assert ns["corroborated"]["precision"] is None
    assert ns["corroborated_precision_mom_pp"] is None  # 前轮值在场不算环比
    assert ns["anchor_green"] == _ANCHOR_CUR


def test_record_first_round_no_anchor_no_prev():
    ns = northstar_record(_readout(), [], None,
                          run_id="r1", eval_env="monthly",
                          today=date(2026, 10, 1))
    assert ns["anchor_green"] is None and ns["anchor_prev"] is None
    assert ns["anchor_green_mom_pp"] is None
    assert ns["corroborated_precision_mom_pp"] is None
    # corroborated 面照算(不依赖锚/前轮件)
    assert ns["corroborated"]["n"] == 17


def test_record_prev_precision_none_yields_no_mom():
    ns = northstar_record(_readout(), [_ANCHOR_CUR],
                          {"corroborated": {"n": 0, "derived_only": 0,
                                            "precision": None}},
                          run_id="r2", eval_env="monthly",
                          today=date(2026, 11, 1))
    assert ns["corroborated_precision_mom_pp"] is None


# ── load_anchor_green: anchors-*.json 工件读数 ──────────────────


def test_load_anchor_green_latest_two_by_filename(tmp_path):
    d = tmp_path / "model"
    d.mkdir()
    for name, payload in (
            ("anchors-20261001-000000.json",
             {"kind": "anchors", "eval_env": "monthly", "generated_at":
              "2026-10-01", "n_total": 19, "failures": []}),
            ("anchors-20261101-000000.json",
             {"kind": "anchors", "eval_env": "monthly", "generated_at":
              "2026-11-01", "n_total": 19,
              "failures": [{"ip": "8.8.8.8"}, {"ip": "1.1.1.1"}]}),
            ("anchors-20261115-000000.json", "{corrupt")):
        (d / name).write_text(payload if isinstance(payload, str)
                              else json.dumps(payload))
    hist = load_anchor_green(d)
    assert [h["artifact"] for h in hist] == [
        "anchors-20261001-000000.json", "anchors-20261101-000000.json"]
    assert hist[0]["rate"] == 1.0 and hist[0]["n_fail"] == 0
    assert hist[1]["n_fail"] == 2
    assert hist[1]["rate"] == pytest.approx(_RATE_17_19)


def test_load_anchor_green_skips_bad_shape_and_empty_dir(tmp_path):
    d = tmp_path / "model"
    d.mkdir()
    (d / "anchors-20261001-000000.json").write_text(json.dumps(
        {"kind": "anchors", "eval_env": "monthly",
         "generated_at": "2026-10-01", "failures": []}))  # 无 n_total
    assert load_anchor_green(d) == []
    assert load_anchor_green(tmp_path / "no-such-dir") == []


# ── load_prev_northstar: 上轮北星件 ────────────────────────────


def test_load_prev_northstar_excludes_current_run(tmp_path):
    (tmp_path / "northstar-r1.json").write_text(json.dumps(_PREV_NS))
    (tmp_path / "northstar-r2.json").write_text(json.dumps(
        {"kind": "northstar", "run_id": "r2"}))
    assert load_prev_northstar(tmp_path, "r2") == _PREV_NS
    # 同 run_id 重跑:排除本轮工件后取最新他轮(r2)
    got = load_prev_northstar(tmp_path, "r1")
    assert got is not None and got["run_id"] == "r2"
    assert load_prev_northstar(tmp_path / "no-such-dir", "r1") is None


# ── render_northstar: 一行 + N/A 哨兵 ──────────────────────────


def test_render_full_values_one_line():
    ns = northstar_record(_readout(), [_ANCHOR_PREV, _ANCHOR_CUR], _PREV_NS,
                          run_id="r2", eval_env="monthly",
                          today=date(2026, 11, 1))
    lines = render_northstar(ns)
    assert len(lines) == 1  # 能力轨记录 = 一行
    ln = lines[0]
    assert ln.startswith("- ")
    assert "能力轨北星" in ln and "E-5" in ln and "只观测不持门" in ln
    assert "锚集全绿率 17/19(89.5%" in ln
    assert "环比 -10.5pp" in ln
    assert "读数源 anchors-20261101-000000.json" in ln
    assert "corroborated 精度 82.4%(corroborated 17 读数, 派生独证 3, " \
           "环比 +12.4pp)" in ln


def test_render_na_sentinels_never_fabricate():
    ns = northstar_record(_readout(), [], None,
                          run_id="r1", eval_env="monthly",
                          today=date(2026, 10, 1))
    ln = render_northstar(ns)[0]
    assert "锚集全绿率 N/A(无 anchors 工件)" in ln
    assert "环比 首轮" in ln              # corroborated 面前轮件缺席


def test_render_zero_corroborated_is_na():
    ns = northstar_record(_readout_no_layers(), [_ANCHOR_CUR], None,
                          run_id="r2", eval_env="monthly",
                          today=date(2026, 11, 1))
    ln = render_northstar(ns)[0]
    assert "corroborated 精度 N/A(零 corroborated 读数)" in ln
    assert "锚集全绿率 17/19(89.5%" in ln     # 锚腿独立于 corroborated 腿


def test_render_prev_record_without_value_is_prev_na():
    # 前轮北星件在场但前轮精度 N/A → 「前轮 N/A」非「首轮」(两态分立)
    ns = northstar_record(_readout(), [_ANCHOR_PREV, _ANCHOR_CUR],
                          {"corroborated": {"n": 0, "derived_only": 0,
                                            "precision": None}},
                          run_id="r2", eval_env="monthly",
                          today=date(2026, 11, 1))
    ln = render_northstar(ns)[0]
    assert "环比 前轮 N/A" in ln
    assert "环比 首轮" not in ln   # 锚腿同带前轮读数 → 全行无「首轮」


def test_render_anchor_prev_rate_none_is_prev_na():
    prev = {**_ANCHOR_PREV, "rate": None}
    ns = northstar_record(_readout(), [prev, _ANCHOR_CUR], None,
                          run_id="r2", eval_env="monthly",
                          today=date(2026, 11, 1))
    ln = render_northstar(ns)[0]
    assert "环比 前轮 N/A" in ln


# ── compose_monthly_md: 北星行挂头块, 缺省 schema-stable ───────


def _header_meta():
    return {"eval_env": "monthly", "corpus": {}, "prev_fingerprints": {},
            "annual": None, "today": date(2026, 11, 1), "epsilon": None}


def _md_min(north_star_lines=None):
    readout = {"layers": {}, "intersection_audit": {},
               "degraded": False, "derived_only_corroboration": 0}
    kwargs = {} if north_star_lines is None else \
        {"north_star_lines": north_star_lines}
    return compose_monthly_md(readout, [], [], [], [], _header_meta(), **kwargs)


def test_md_places_north_star_line_in_header_before_layers():
    md = _md_min(["- 能力轨北星(E-5, 只观测不持门): 样例行"])
    assert "能力轨北星" in md
    assert md.index("能力轨北星") < md.index("## 分层读数")


def test_md_without_north_star_lines_is_schema_stable():
    assert "能力轨北星" not in _md_min()
