# backend/tests/eval/test_eval_temporal.py
"""λ_s prequential confirmation-rate instrument (W1, Task 4).

Synthetic 3-round history pins:
- unique assertion (round t) → later-round independent confirmation
- same-cluster copier does NOT confirm (LINEAGE_CLUSTERS)
- same-round OC ≥ 0.30 copier does NOT confirm (single-round OC table)
- rc==0 source skipped per window and named in `skipped`
- n=0 → lam/CI all None; <2 rounds → CLI "insufficient rounds" exit 2
"""
import json

import pytest

from ipdb._eval.__main__ import main
from ipdb._eval.temporal import (compute_temporal, fisher_exact,
                                 rounds_from_history, temporal_report)


def _round(date, pairs, source_health=None, scores=None):
    return {"date": date, "pairs": pairs,
            "source_health": source_health or {}, "scores": scores or []}


def _p(ip, ctype="spam"):
    return [ip, ctype, None]


# ── synthetic fleet ────────────────────────────────────────────
# A/B plain independent sources; C=firehol confirmed only by ipsum
# (same aggregated-threat cluster); E blocked from F by round-2 OC=1.0;
# D dead in round 2 (source_health rc=0); G/H co-assert (never unique).
R1_PAIRS = {
    "A": [_p(f"10.0.0.{i}") for i in range(1, 11)],
    "firehol": [_p(f"10.1.0.{i}") for i in range(1, 5)],
    "E": [_p(f"10.2.0.{i}") for i in range(1, 5)],
    "G": [_p("10.9.0.1")],
    "H": [_p("10.9.0.1")],
}
R2_PAIRS = {
    "B": [_p(f"10.0.0.{i}") for i in range(1, 6)],          # picks up 5 of A's
    "ipsum": [_p(f"10.1.0.{i}") for i in range(1, 5)],      # same cluster as firehol
    "E": [_p(f"10.2.0.{i}") for i in range(1, 5)],
    "F": [_p(f"10.2.0.{i}") for i in range(1, 3)],          # OC(E,F)=1.0 in r2
    "D": [_p(f"10.3.0.{i}") for i in range(1, 4)],          # dead: rc=0
    "A": [_p("10.0.0.11"), _p("10.0.0.12")],
}
R3_PAIRS = {"B": [_p("10.0.0.11")]}                          # confirms A's r2

ROUNDS = [
    _round("2026-08-01", R1_PAIRS,
           scores=[{"source": "A", "theta": 0.9},
                   {"source": "firehol", "theta": 0.6},
                   {"source": "E", "theta": 0.2},
                   {"source": "G", "theta": 0.1}]),   # H 无评分 → 不入组
    _round("2026-09-01", R2_PAIRS,
           source_health={"D": {"rc": 0, "stale": True}},
           scores=[{"source": "A", "theta": 0.8},
                   {"source": "B", "theta": 0.15},
                   {"source": "D", "theta": 0.2},
                   {"source": "ipsum", "theta": 0.1}]),
    _round("2026-10-01", R3_PAIRS),
]


def test_fisher_exact_known_values():
    # classic lady-tasting-tea table: two-sided p = 34/70
    assert fisher_exact(3, 1, 1, 3) == pytest.approx(34 / 70)
    # all-or-nothing table: p = 2/252
    assert fisher_exact(5, 0, 0, 5) == pytest.approx(2 / 252)
    # degenerate empty table
    assert fisher_exact(0, 0, 0, 0) == 1.0


def test_compute_windows_and_lambda():
    rep = compute_temporal(ROUNDS)
    assert rep["n_rounds"] == 3
    assert [w["from"] for w in rep["windows"]] == ["2026-08-01", "2026-09-01"]
    assert all(w["to"] == "2026-10-01" for w in rep["windows"])

    w1, w2 = rep["windows"]
    # A: 10 unique, 5 confirmed by independent B → λ=0.5, Wilson CI straddles
    a = w1["per_source"]["A"]
    assert (a["n_uniq"], a["n_conf"]) == (10, 5)
    assert a["lam"] == pytest.approx(0.5)
    assert a["ci_lo"] < 0.5 < a["ci_hi"]
    # firehol uniques picked up ONLY by same-cluster ipsum → not confirmed
    c = w1["per_source"]["firehol"]
    assert (c["n_uniq"], c["n_conf"], c["lam"]) == (4, 0, 0.0)
    assert c["ci_lo"] == 0.0 and 0.0 < c["ci_hi"] < 0.6
    # E: F re-asserts 2 of its pairs but OC(E,F)=1.0 in round 2 → blocked
    assert (w1["per_source"]["E"]["n_uniq"], w1["per_source"]["E"]["n_conf"]) == (4, 0)
    # G/H co-assert → n=0 → lam/CI all None (Wilson must not divide by zero)
    assert w1["per_source"]["G"]["n_uniq"] == 0
    assert w1["per_source"]["G"]["lam"] is None
    assert w1["per_source"]["G"]["ci_lo"] is None
    assert w1["per_source"]["G"]["ci_hi"] is None
    assert w1["skipped"] == []

    # window 2: A 2 unique / 1 confirmed; D dead (rc=0) skipped by name
    assert (w2["per_source"]["A"]["n_uniq"], w2["per_source"]["A"]["n_conf"]) == (2, 1)
    assert "D" not in w2["per_source"]
    assert w2["skipped"] == ["D"]


def test_compute_preregistration_pooled_fisher():
    rep = compute_temporal(ROUNDS)
    pre = rep["preregistration"]
    # θ̂ ≥ median → above(以上含本数:奇数个评分时中位源落 above 组)
    # window1 med=0.4 above={A,firehol} below={E,G} (H 无评分不入组);
    # window2 med=0.175 above={A,D(skipped)} below={B,ipsum};
    # uniques: w1 A(10,5) firehol(4,0) E(4,0); w2 A(2,1) B(5,0) ipsum(4,0)
    assert (pre["above"]["n_uniq"], pre["above"]["n_conf"]) == (16, 6)
    assert (pre["below"]["n_uniq"], pre["below"]["n_conf"]) == (13, 0)
    assert pre["above"]["lam"] == pytest.approx(6 / 16)
    assert pre["below"]["lam"] == 0.0
    assert 0.0 < pre["fisher_p"] < 1.0
    assert pre["direction"] == "above>below"


def test_rounds_from_history_dedup_and_defaults(tmp_path):
    d = tmp_path / "model"
    d.mkdir()
    # two files same date → lexicographic-last filename wins
    stale = dict(ROUNDS[0]); stale["pairs"] = {**R1_PAIRS, "A": R1_PAIRS["A"] + [_p("10.0.0.99")]}
    for ts, r in [("20260801-000000", stale), ("20260801-120000", ROUNDS[0]),
                  ("20260901-000000", ROUNDS[1]), ("20261001-000000", ROUNDS[2])]:
        (d / f"model-{ts}.json").write_text(json.dumps(
            {"kind": "model", "generated_at": r["date"],
             "pairs": r["pairs"], "source_health": r["source_health"],
             "scores": r["scores"]}))
    rounds = rounds_from_history(d)
    assert [r["date"] for r in rounds] == ["2026-08-01", "2026-09-01", "2026-10-01"]
    assert len(rounds[0]["pairs"]["A"]) == 10          # last-of-date wins
    assert rounds[0]["source_health"] == {}            # old round: no key → {}
    assert rounds[1]["source_health"] == {"D": {"rc": 0, "stale": True}}
    assert rounds[2]["scores"] == []


def test_temporal_report_writes_json(tmp_path):
    d = tmp_path / "model"
    d.mkdir()
    for ts, r in [("20260801-000000", ROUNDS[0]), ("20260901-000000", ROUNDS[1]),
                  ("20261001-000000", ROUNDS[2])]:
        (d / f"model-{ts}.json").write_text(json.dumps(
            {"kind": "model", "generated_at": r["date"], "pairs": r["pairs"],
             "source_health": r["source_health"], "scores": r["scores"]}))
    rep = temporal_report(d, out_dir=tmp_path)
    assert rep["n_rounds"] == 3
    assert rep["windows"][1]["skipped"] == ["D"]
    files = list(tmp_path.glob("temporal-*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["preregistration"]["direction"] == "above>below"


def test_cli_insufficient_rounds_exit_2(tmp_path, monkeypatch, capsys):
    d = tmp_path / "model"
    d.mkdir()
    (d / "model-20260801-000000.json").write_text(json.dumps(
        {"kind": "model", "generated_at": "2026-08-01", "pairs": R1_PAIRS}))
    import ipdb._eval.__main__ as cli
    monkeypatch.setattr(cli, "REPORT_DIR", tmp_path)
    with pytest.raises(SystemExit) as e:
        main(["--temporal"])
    assert e.value.code == 2
    assert "insufficient rounds" in capsys.readouterr().out


def test_cli_summary_three_rounds(tmp_path, monkeypatch, capsys):
    d = tmp_path / "model"
    d.mkdir()
    for ts, r in [("20260801-000000", ROUNDS[0]), ("20260901-000000", ROUNDS[1]),
                  ("20261001-000000", ROUNDS[2])]:
        (d / f"model-{ts}.json").write_text(json.dumps(
            {"kind": "model", "generated_at": r["date"], "pairs": r["pairs"],
             "source_health": r["source_health"], "scores": r["scores"]}))
    import ipdb._eval.__main__ as cli
    monkeypatch.setattr(cli, "REPORT_DIR", tmp_path)
    main(["--temporal"])                                # no SystemExit
    out = capsys.readouterr().out
    assert "3 rounds, 2 windows" in out
    assert "2026-08-01 -> 2026-10-01" in out
    assert "skipped: D" in out
    assert "report:" in out
