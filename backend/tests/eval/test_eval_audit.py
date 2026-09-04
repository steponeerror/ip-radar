# backend/tests/eval/test_eval_audit.py
import json
from pathlib import Path

from ipdb._eval.audit import lineage_audit, load_history


def _mk_run(tmp_path, ts, pairs):
    p = tmp_path / f"model-{ts}.json"
    p.write_text(json.dumps({"kind": "model", "pairs": pairs, "corpus":
                             {"n_ips": 10, "sha8": "x"}}))
    return p


def test_load_history_sorted(tmp_path):
    _mk_run(tmp_path, "20260801-000000", {"a": [["1.1.1.1", "spam", None]]})
    _mk_run(tmp_path, "20260901-000000", {"a": [["1.1.1.1", "spam", None]]})
    runs = load_history(tmp_path)
    assert [r for r in runs] and runs[0]["pairs"]["a"][0][2] is None


def test_audit_finds_copier_and_passes_c3(tmp_path, monkeypatch):
    # two upstreams u1/u2 list pairs before mirror m; m fully contained in both
    pairs_u1 = [[f"10.0.0.{i}", "spam", "2026-08-01"] for i in range(1, 21)]
    pairs_u2 = [[f"10.0.0.{i}", "spam", "2026-08-02"] for i in range(1, 21)]
    pairs_m = [[f"10.0.0.{i}", "spam", "2026-08-15"] for i in range(1, 19)]
    _mk_run(tmp_path, "20260801-000000", {
        "u1": pairs_u1, "u2": pairs_u2, "m": pairs_m,
        "orig": [["10.9.9.9", "scanner", "2026-08-01"],
                 ["10.9.9.8", "scanner", "2026-08-01"]]})
    import ipdb._eval.audit as A
    monkeypatch.setattr(A, "DERIVED_SOURCES", frozenset({"m"}))
    res = A.lineage_audit(tmp_path)
    assert res["recommended_derived"] == ["m"]
    # u2 copies u1 once but 1 < MIN_COPIERS -> not recommended
    assert "u2" not in res["recommended_derived"]
    # orig never copies -> must NOT be recommended (zero false accusations)
    assert "orig" not in res["recommended_derived"]
    assert res["c3"] == {"pass": True, "false_accusations": [],
                         "missing_known": []}
