# backend/tests/eval/test_eval_anchors.py
import json

from ipdb._eval.anchors import ANCHORS, run_anchors


def _fake(kind):
    def lk(ip):
        if kind == "clean":
            return {"classifications": {}, "is_reserved": False,
                    "attributes": {}}
        if kind == "reserved":
            return {"classifications": {}, "is_reserved": True,
                    "attributes": {}}
        if kind == "tor":
            return {"classifications": {}, "is_reserved": False,
                    "attributes": {"is_tor": [{"source": "tor_exits",
                                               "value": True}]}}
        return {"classifications": {}, "is_reserved": False,
                "attributes": {"is_hosting": [{"source": "aws_ranges",
                                               "value": True}]}}
    return lk


def _matching():
    # answers each anchor ip with the response its own expectation needs
    kinds = dict(ANCHORS)
    return lambda ip: _fake(kinds.get(ip, "clean"))(ip)


def test_all_kinds_pass_with_matching_lookup():
    # one dispatch covers all four kinds (guarded below), all must pass
    assert {k for _, k in ANCHORS} >= {"clean", "reserved", "tor", "hosting"}
    assert run_anchors(_matching()) == []


def test_failure_reports_ip_and_reason():
    # a tor-anchor checked against a clean-only fake must fail:
    tor_ip = next(ip for ip, k in ANCHORS if k == "tor")
    fails = run_anchors(_fake("clean"))
    assert any(f["ip"] == tor_ip and f["expect"] == "tor" for f in fails)


def test_anchors_json_mode_output_is_pure_json(monkeypatch, capsys):
    # --anchors --json: whole stdout must parse as the envelope (review: prose
    # prints used to leak after it); exit codes stay 0/1 in both modes.
    from types import SimpleNamespace
    import pytest
    import ipdb._eval.__main__ as M

    def _reg(lk):
        return SimpleNamespace(load_db=lambda: None, lookup=lk)

    monkeypatch.setattr(M, "_real_registry", lambda: _reg(_matching()))
    with pytest.raises(SystemExit) as e:
        M.main(["--anchors", "--json"])
    assert json.loads(capsys.readouterr().out) == {"failures": []}
    assert e.value.code == 0

    monkeypatch.setattr(M, "_real_registry", lambda: _reg(_fake("clean")))
    with pytest.raises(SystemExit) as e:
        M.main(["--anchors", "--json"])
    fails = json.loads(capsys.readouterr().out)["failures"]
    assert fails and e.value.code == 1

    with pytest.raises(SystemExit) as e:  # non-json mode: prose + exit 1
        M.main(["--anchors"])
    out = capsys.readouterr().out
    assert "anchors: " in out and "ANCHOR FAIL " in out
    assert e.value.code == 1
