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
                "attributes": {"is_hosting": [{"source": "cloud_ranges",
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


def test_anchors_json_mode_output_is_pure_json(monkeypatch, capsys, tmp_path):
    # --anchors --json: whole stdout must parse as the envelope (review: prose
    # prints used to leak after it); exit codes stay 0/1 in both modes.
    # T8 后 CLI 会落盘 anchors-*.json → REPORT_DIR 隔离到 tmp_path(断言原样)
    from types import SimpleNamespace
    import pytest
    import ipdb._eval.__main__ as M

    def _reg(lk):
        return SimpleNamespace(load_db=lambda: None, lookup=lk)

    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
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


# ── T8(T14 缓议清偿):anchors 落盘 model/anchors-<ts>.json ──────

def test_anchors_report_persists_json(tmp_path):
    # 落盘件:<out>/model/anchors-<ts>.json(ts 形态同 model-*.json),
    # 件含 eval_env/kind/failures/n_total;返回值与 run_anchors 位等价
    import re
    from ipdb._eval.anchors import anchors_report, run_anchors
    fails = anchors_report(_matching(), out_dir=tmp_path, eval_env="monthly")
    assert fails == run_anchors(_matching()) == []
    files = list((tmp_path / "model").glob("anchors-*.json"))
    assert len(files) == 1
    assert re.fullmatch(r"anchors-\d{8}-\d{6}\.json", files[0].name)
    d = json.loads(files[0].read_text())
    assert d["kind"] == "anchors" and d["eval_env"] == "monthly"
    assert d["failures"] == [] and d["n_total"] == len(ANCHORS)


def test_anchors_report_persists_failures_too(tmp_path):
    # 失败也落盘(证据不灭):failures 原样留档,eval_env 缺省走
    # __main__.eval_env()(IP_RADAR_EVAL_ENV)
    from ipdb._eval.anchors import anchors_report
    import ipdb._eval.__main__ as M  # noqa: F401  (env 解析链路真实性)
    import os
    old = os.environ.get("IP_RADAR_EVAL_ENV")
    os.environ["IP_RADAR_EVAL_ENV"] = "gate"
    try:
        fails = anchors_report(_fake("clean"), out_dir=tmp_path)
    finally:
        if old is None:
            os.environ.pop("IP_RADAR_EVAL_ENV", None)
        else:
            os.environ["IP_RADAR_EVAL_ENV"] = old
    assert fails  # clean-only fake: tor/hosting anchors must fail
    d = json.loads(next((tmp_path / "model").glob("anchors-*.json")).read_text())
    assert d["failures"] == fails and d["eval_env"] == "gate"


def test_anchors_report_pure_read_ignores_invalid_env(monkeypatch, tmp_path):
    # 纯读路径懒解析 eval_env(T8 复审②):out_dir=None 时不得读
    # IP_RADAR_EVAL_ENV——无效值不炸,裸 run_anchors 可成功则
    # anchors_report 纯读也必须成功(不落盘 = 零副作用契约)
    from ipdb._eval.anchors import anchors_report
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "bogus")
    assert anchors_report(_matching()) == [] \
        and not (tmp_path / "model").exists()


def test_anchors_cli_persists_but_stdout_envelope_unchanged(
        tmp_path, monkeypatch, capsys):
    # CLI 位等价:--anchors --json stdout 仍恰为 {"failures": ...}(无
    # eval_env 等落盘侧键);退出码不变;件落 REPORT_DIR/model 带 eval_env
    from types import SimpleNamespace
    import pytest
    import ipdb._eval.__main__ as M
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(M, "_real_registry", lambda: SimpleNamespace(
        load_db=lambda: None, lookup=_matching()))
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")
    with pytest.raises(SystemExit) as e:
        M.main(["--anchors", "--json"])
    assert json.loads(capsys.readouterr().out) == {"failures": []}
    assert e.value.code == 0
    files = list((tmp_path / "model").glob("anchors-*.json"))
    assert len(files) == 1
    d = json.loads(files[0].read_text())
    assert d["kind"] == "anchors" and d["eval_env"] == "monthly"
