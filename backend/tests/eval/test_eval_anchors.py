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


# ── #182(#180 租户批):公共解析器锚扩员 + anchor_sweep 巡检件 ──────────

def test_public_resolver_anchors_pinned():
    # 发现固化(ADR 0008;STANDARD.md 金标层 G-2):114DNS(cps+ziyadnz 假印证
    # 事故)/223.5.5.5(阿里公共 DNS)/9.9.9.4(Quad9 未过滤变体,与 9.9.9.9
    # 区分——干净面必须覆盖未过滤腿)三新员入 clean 面。
    for ip in ("114.114.114.114", "223.5.5.5", "9.9.9.4"):
        assert (ip, "clean") in ANCHORS, f"公共解析器锚缺:{ip}"


def _incident(ip):
    # 2026-10-24 事故判例的罐装查询面(勘察件 §1 实测复现,独立真源):
    # 8.8.8.8 = myip_ms 单源指控 conf=55;114DNS = cps+ziyadnz 双聚合器
    # corroborated=True conf=55(#183 整改前形状——fixture 不依赖整改)。
    accusers = {"8.8.8.8": ["myip_ms"],
               "114.114.114.114": ["cps_collected_iocs", "ziyadnz"]}[ip]
    det = [{"source": s, "verdict": "malicious", "reliability": 0.55}
           for s in accusers]
    return {"is_reserved": False, "attributes": {},
            "threat": {"verdict": "malicious", "confidence": 55,
                       "types": ["blacklist"], "is_cdn": False},
            "classifications": {"blacklist": {
                "type": "blacklist", "verdict": "malicious", "detected": True,
                "confidence": 55, "corroborated": len(accusers) >= 2,
                "details": det, "sources": []}}}


def test_anchor_sweep_full_projection_and_shape():
    # 巡检件求值核:ANCHORS 全集投影,逐锚带 verdict/confidence/accusers
    # 数字(ops 轮 G_ANCHOR_SWEEP 门消费面);零 finding 轮形状基线。
    from ipdb._eval.anchors import anchor_sweep
    sweep = anchor_sweep(_matching())
    assert sweep["kind"] == "anchor_sweep"
    assert sweep["n_total"] == len(ANCHORS)
    assert [tuple(a) for a in sweep["anchors"]] == ANCHORS  # 单一真源投影
    assert len(sweep["results"]) == len(ANCHORS)
    assert sweep["n_fail"] == 0 and sweep["failures"] == []
    for r in sweep["results"]:
        assert set(r) == {"ip", "expect", "ok", "reason", "verdict",
                          "confidence", "accusers", "conflict"}
        assert r["ok"] is True and r["reason"] is None
        assert isinstance(r["verdict"], str)
        assert isinstance(r["confidence"], int)
        assert r["accusers"] == []
        assert r["conflict"] is False  # 零冲突基线(#188 新员)


def test_anchor_sweep_incident_finding_not_gate():
    # 票 #182 语义:锚 expectation 失败 = finding(ok=False+reason+accusers
    # 读数),不 raise 不 sys.exit——判定门腿是 --anchors(月轮 rc 1),双轨
    # 分立(ADR 0008 决策 2)。
    from ipdb._eval.anchors import anchor_sweep
    kinds = dict(ANCHORS)

    def lk(ip):
        if ip in ("8.8.8.8", "114.114.114.114"):
            return _incident(ip)
        return _fake(kinds.get(ip, "clean"))(ip)

    sweep = anchor_sweep(lk)  # 不 raise 即票义(不持门)
    assert sweep["n_fail"] == 2
    assert len(sweep["failures"]) == 2
    by_ip = {r["ip"]: r for r in sweep["results"]}
    r88, r114 = by_ip["8.8.8.8"], by_ip["114.114.114.114"]
    assert r88["ok"] is False and "malicious" in r88["reason"]
    assert r88["verdict"] == "malicious" and r88["confidence"] == 55
    assert r88["accusers"] == ["myip_ms"]
    assert r114["accusers"] == ["cps_collected_iocs", "ziyadnz"]
    # 其余锚照常 ok(逐锚独立,不因 finding 中断)
    assert all(r["ok"] for ip, r in by_ip.items()
               if ip not in ("8.8.8.8", "114.114.114.114"))


def test_anchor_sweep_conflict_marker_not_suppression():
    # #188 benign②终态形状:223.5.5.5 = tweetfeed 指控× infra_services
    # 良性断言同场 → 分类组 verdict_conflict=True → 巡检件 conflict 留痕;
    # 宁少算:良性断言不自动压制指控,锚仍 finding(ok=False,人裁)。
    from ipdb._eval.anchors import anchor_sweep
    kinds = dict(ANCHORS)

    def lk(ip):
        if ip == "223.5.5.5":
            return {  # 主体注入面生产形状(a00e2df9:_registry.lookup)
                "is_reserved": False, "attributes": {},
                "threat": {"verdict": "malicious", "confidence": 50,
                           "types": ["other"], "is_cdn": False},
                "classifications": {"other": {
                    "type": "other", "verdict": "malicious",
                    "detected": True, "confidence": 50,
                    "corroborated": False, "verdict_conflict": True,
                    "details": [
                        {"source": "tweetfeed", "verdict": "malicious",
                         "reliability": 0.5},
                        {"source": "infra_services", "verdict": "benign",
                         "reliability": 0.8}],
                    "sources": []}}}
        return _fake(kinds.get(ip, "clean"))(ip)

    sweep = anchor_sweep(lk)
    by_ip = {r["ip"]: r for r in sweep["results"]}
    r = by_ip["223.5.5.5"]
    assert r["conflict"] is True          # 对立留痕出海
    assert r["ok"] is False and "malicious" in r["reason"]  # 锚仍 finding
    assert r["accusers"] == ["tweetfeed"]  # 良性断言不进指控证人列
    # conflict 不传染:其余锚(含同扫 clean 锚)conflict 恒 False
    assert all(not x["conflict"] for i, x in by_ip.items() if i != "223.5.5.5")
    assert sweep["n_fail"] == 1           # 仅该锚 finding,不放大门面


def test_anchor_sweep_cli_json_finding_not_gate(monkeypatch, capsys, tmp_path):
    # --anchor-sweep --json:stdout 恰为 sweep JSON(--anchors 纯 JSON 同纪律),
    # rc 恒 0(finding 不持门)——事故判例轮两 finding 仍 rc 0;非 json 面人读行。
    from types import SimpleNamespace
    import ipdb._eval.__main__ as M
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(M, "_real_registry",
                        lambda: SimpleNamespace(load_db=lambda: None,
                                                lookup=_matching()))
    M.main(["--anchor-sweep", "--json"])  # 无 SystemExit = rc 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "anchor_sweep" and out["n_fail"] == 0
    assert out["n_total"] == len(ANCHORS)

    kinds = dict(ANCHORS)

    def lk(ip):
        return _incident(ip) if ip == "114.114.114.114" \
            else _fake(kinds.get(ip, "clean"))(ip)

    monkeypatch.setattr(M, "_real_registry",
                        lambda: SimpleNamespace(load_db=lambda: None,
                                                lookup=lk))
    M.main(["--anchor-sweep", "--json"])  # finding 轮仍 rc 0(不持门)
    out = json.loads(capsys.readouterr().out)
    assert out["n_fail"] == 1
    assert out["failures"][0]["ip"] == "114.114.114.114"
    M.main(["--anchor-sweep"])  # 非 json 面不炸
    assert "114.114.114.114" in capsys.readouterr().out


def test_anchor_sweep_cli_load_fail_envelope(monkeypatch, capsys, tmp_path):
    # --json 下 load_db 失败走 stdout JSON 信封不裸栈(--matrix-scan 同款,
    # spec §5.2);rc 1 = 巡检面 infra 信封(JS 侧降级旁路消费,票 #182)。
    from types import SimpleNamespace
    import pytest
    import ipdb._eval.__main__ as M

    def boom():
        raise RuntimeError("disk gone")

    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(M, "_real_registry",
                        lambda: SimpleNamespace(load_db=boom,
                                                lookup=_matching()))
    with pytest.raises(SystemExit) as e:
        M.main(["--anchor-sweep", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert d["error"]["code"] == "internal" and e.value.code == 1
