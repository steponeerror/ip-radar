# backend/tests/eval/test_eval_anchors.py
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
