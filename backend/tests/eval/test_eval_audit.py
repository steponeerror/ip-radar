# backend/tests/eval/test_eval_audit.py
import json
from pathlib import Path

from ipdb._eval.audit import forward_flow, lineage_audit, load_history


def _mk_run(tmp_path, ts, pairs):
    p = tmp_path / f"model-{ts}.json"
    p.write_text(json.dumps({"kind": "model", "pairs": pairs, "corpus":
                             {"n_ips": 10, "sha8": "x"}}))
    return p


def _pl(prefix, n, fs=None):
    return [[f"{prefix}.{i}", "spam", fs] for i in range(1, n + 1)]


def test_load_history_sorted(tmp_path):
    _mk_run(tmp_path, "20260801-000000", {"a": [["1.1.1.1", "spam", None]]})
    _mk_run(tmp_path, "20260901-000000", {"a": [["1.1.1.1", "spam", None]]})
    runs = load_history(tmp_path)
    assert [r for r in runs] and runs[0]["pairs"]["a"][0][2] is None


def test_load_history_same_date_takes_last(tmp_path):
    _mk_run(tmp_path, "20260801-100000", {"a": [["1.1.1.1", "spam", None]]})
    _mk_run(tmp_path, "20260801-200000", {"a": [["1.1.1.1", "spam", None],
                                                ["2.2.2.2", "spam", None]]})
    runs = load_history(tmp_path)
    assert len(runs) == 1 and len(runs[0]["pairs"]["a"]) == 2


# ── forward_flow (pure) ─────────────────────────────────────────

def test_forward_flow_first_pickup_counted_once():
    p1, p2 = ("1.1.1.1", "spam"), ("2.2.2.2", "spam")
    rounds = [
        {"a": {p1, p2}, "b": set()},
        {"a": {p1}, "b": {p1}},          # a still holds p1 — no recount
        {"a": set(), "b": {p1, p2}},     # b picks p2 only in the last round
    ]
    assert forward_flow(rounds, "a", "b") == (2, 0)


def test_forward_flow_symmetric_and_coasserted_zero():
    p1 = ("3.3.3.3", "spam")
    assert forward_flow([{"a": set(), "b": {p1}},
                         {"a": {p1}, "b": {p1}}], "a", "b") == (0, 1)
    # co-asserted from the start → no flow either direction
    assert forward_flow([{"a": {p1}, "b": {p1}}] * 2, "a", "b") == (0, 0)


# ── lineage_audit v2 (forward-flow direction) ───────────────────

def test_audit_confirms_copier_4rounds(tmp_path, monkeypatch):
    # u1/u2 each list base(10) from round 1 and add 5 new pairs in round 2;
    # c holds base from round 1 and picks up both new sets in round 3.
    base, n1, n2 = _pl("10.0.0", 10), _pl("10.1.0", 5), _pl("10.2.0", 5)
    for i, ts in enumerate(["20260801", "20260808", "20260815", "20260822"]):
        u1 = base + (n1 if i >= 1 else [])
        u2 = base + (n2 if i >= 1 else [])
        c = base + (n1 + n2 if i >= 2 else [])
        _mk_run(tmp_path, f"{ts}-000000", {"u1": u1, "u2": u2, "c": c})
    import ipdb._eval.audit as A
    monkeypatch.setattr(A, "DERIVED_SOURCES", frozenset({"c"}))
    res = A.lineage_audit(tmp_path)
    assert res["n_rounds"] == 4
    assert res["recommended_derived"] == ["c"]
    assert sorted(res["relations"]) == ["c"]           # only c has in-edges
    ups = {u for u, *_ in res["relations"]["c"]}
    assert ups == {"u1", "u2"}                          # u1/u2 are the sources
    for u, f_in, f_out, contain in res["relations"]["c"]:
        assert (f_in, f_out) == (5, 0)                  # 5 picked up, 0 reverse
    assert res["c3"] == {"pass": True, "false_accusations": [],
                         "missing_known": [], "recall": 1.0}
    # u1–u2 share the base but neither flows → not-yet
    row = next(r for r in res["pairs"] if {r["a"], r["b"]} == {"u1", "u2"})
    assert row["state"] == "not-yet"


def test_audit_spamhaus_churn_no_false_accusation(tmp_path, monkeypatch):
    # §7 counterexample: original U churns (drops its base in round 3) while
    # aggregator G keeps history forever. U's first_seen is LATE and G's is
    # EARLY — naive first-seen timing would call U the copier. Forward flow:
    # U→G has flow (G picks up U's new pairs), G→U none → U is the source.
    p0, new = _pl("10.3.0", 12, fs="2026-09-01"), _pl("10.4.0", 5)
    g_p0 = _pl("10.3.0", 12, fs="2026-01-01")           # aggregator saw it first
    for i, ts in enumerate(["20260801", "20260808", "20260815", "20260822"]):
        u = p0 + new if i < 2 else new                   # churn: base dropped
        g = g_p0 + (new if i >= 2 else [])               # always holds history
        _mk_run(tmp_path, f"{ts}-000000", {"U": u, "G": g})
    import ipdb._eval.audit as A
    monkeypatch.setattr(A, "DERIVED_SOURCES", frozenset({"G"}))
    res = A.lineage_audit(tmp_path)
    # G is the known aggregator but only has one confirmed in-edge (<2)
    assert res["recommended_derived"] == []
    # core assertion: the ORIGINAL is not accused
    assert res["c3"]["false_accusations"] == []
    assert "U" not in res["relations"]                   # U has no in-edges
    assert res["relations"]["G"][0] == ("U", 5, 0, 1.0)   # U is the source
    row = next(r for r in res["pairs"] if {r["a"], r["b"]} == {"U", "G"})
    assert row["state"] == "confirmed" and row["copier"] == "G"
    assert row["fab"] + row["fba"] == 5                  # flow 5:0 (or 0:5)


def test_audit_two_rounds_not_yet(tmp_path, monkeypatch):
    # 2 rounds: flow exists (u's round-1 new pairs picked up round 2) but a
    # single transition is not confirmable history → every pair not-yet.
    base, new = _pl("10.5.0", 10), _pl("10.6.0", 5)
    _mk_run(tmp_path, "20260801-000000", {"u": base + new, "c": base})
    _mk_run(tmp_path, "20260808-000000", {"u": base, "c": base + new})
    import ipdb._eval.audit as A
    monkeypatch.setattr(A, "DERIVED_SOURCES", frozenset({"c"}))
    res = A.lineage_audit(tmp_path)
    assert res["n_rounds"] == 2
    assert res["recommended_derived"] == [] and res["relations"] == {}
    assert all(r["state"] == "not-yet" for r in res["pairs"])
    assert res["c3"]["recall"] == 0.0 and res["c3"]["pass"] is False
