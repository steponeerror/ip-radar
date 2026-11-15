# backend/tests/eval/test_eval_contract.py
"""质量要求表(#349 / ADR 0021)测试:表 schema 校验、runner 对 faux 腿的
执行与质量报告两件产物、无读数维度显形、坏腿留痕不炸整单。

真实腿(--anchors/--exclusive/mirror_check)需要 DB/数据面,由月轮面跑;
本件只钉 runner 机制——契约层是结缔组织,不是第二套工具(工具本体不改)。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval import contract as C
from ipdb._eval.contract import (CONTRACT_PATH, ContractError, load_contract,
                                 render_markdown, run_contract)


def _row(**over):
    row = {
        "id": "r1",
        "dimension": "维度甲",
        "metric": "指标甲读数",
        "oracle": {"kind": "none", "reason": "无读数理由 #999"},
        "expectation": "期望甲",
        "verdict": "finding",
        "track": "baseline",
        "trigger": "round",
        "provenance": "测试 fixture",
    }
    row.update(over)
    return row


def _doc(rows, **over):
    doc = {"schema": C.SCHEMA, "rows": rows}
    doc.update(over)
    return doc


def _write(tmp_path, doc, name="contract.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


# faux 子进程腿:argv 尾接 sys.executable(runner subprocess 口径同款)
PY_OK = ["-c", "import json; print(json.dumps({'n': 3}))"]
PY_GATE_RED = ["-c", "import json,sys; "
               "print(json.dumps({'failures': [{'ip': '9.9.9.9'}]})); "
               "sys.exit(1)"]
PY_CRASH = ["-c", "import sys; print('boom-detail', file=sys.stderr); "
            "sys.exit(3)"]
PY_NOT_JSON = ["-c", "print('hello')"]
PY_ENV_ERR = ["-c", "import json,sys; print(json.dumps({'error': "
              "{'code': 'ENVELOPE_TEST', 'message': '对照闸拒绝'}})); "
              "sys.exit(2)"]


# ── 表 schema 校验 ────────────────────────────────────────────────────

def test_packaged_table_validates_and_covers_five_dimensions():
    doc = load_contract(CONTRACT_PATH)
    rows = doc["rows"]
    # #351 起「事故回归」维度五腿追加在尾(每事故一行,不重排既有五行);
    # #352 起「变异自检」维度一行追加在尾(同律:追加不重排)
    assert [r["dimension"] for r in rows] == [
        "误报克制", "独占率", "新鲜度", "一致性", "召回",
        "事故回归", "事故回归", "事故回归", "事故回归", "事故回归",
        "变异自检"]
    assert {r["verdict"] for r in rows} == {"gate", "finding", "score"}
    assert {r["track"] for r in rows} == {"baseline", "improvement"}
    assert {r["trigger"] for r in rows} == {"round", "change"}


def test_packaged_recall_row_is_coverage_ledger_first_entry():
    doc = load_contract(CONTRACT_PATH)
    recall = next(r for r in doc["rows"] if r["dimension"] == "召回")
    assert recall["oracle"]["kind"] == "none"
    assert recall["expectation"].startswith("无读数")
    assert "#350" in recall["expectation"]
    assert "覆盖账本" in recall["oracle"]["reason"]


def test_packaged_rows_declare_oracle_faces():
    doc = load_contract(CONTRACT_PATH)
    by_dim = {r["dimension"]: r for r in doc["rows"]}
    # 误报克制 = --anchors 判定门面(subprocess 原样调,行为不改)
    assert by_dim["误报克制"]["oracle"] == {
        "kind": "subprocess",
        "argv": ["-m", "ipdb._eval", "--anchors", "--json"]}
    # 独占率 = --exclusive 探针,feed 是运维占位符非表内常量
    assert by_dim["独占率"]["oracle"]["argv"][:3] == [
        "-m", "ipdb._eval", "--exclusive"]
    assert "$FEED_FILE" in by_dim["独占率"]["oracle"]["argv"]
    # 新鲜度 = mirror manifest 守卫 + epoch 指纹(S6/S7)
    assert by_dim["新鲜度"]["oracle"]["argv"][:2] == [
        "-m", "ipdb._eval.mirror_check"]
    assert "$DATA_DIR" in by_dim["新鲜度"]["oracle"]["argv"]
    assert "$MANIFEST" in by_dim["新鲜度"]["oracle"]["argv"]
    # 一致性 = c2 双门现行载体是一次性脚本(写路径+前提过期),只读月轮
    # oracle 不存在 → 无读数显形,理由留痕(覆盖账本第 2 笔显形)
    assert by_dim["一致性"]["oracle"]["kind"] == "none"
    assert "c2" in by_dim["一致性"]["oracle"]["reason"]


def test_validate_rejects_missing_field():
    row = _row()
    del row["expectation"]
    with pytest.raises(ContractError, match="expectation"):
        C.validate_contract(_doc([row]))


def test_validate_rejects_unknown_row_key():
    with pytest.raises(ContractError, match="typo_field"):
        C.validate_contract(_doc([_row(typo_field="x")]))


def test_validate_rejects_bad_enums():
    for field, bad in (("verdict", "hard"), ("track", "gold"),
                       ("trigger", "daily")):
        with pytest.raises(ContractError, match=bad):
            C.validate_contract(_doc([_row(**{field: bad})]))


def test_validate_rejects_duplicate_ids():
    with pytest.raises(ContractError, match="r1"):
        C.validate_contract(_doc([_row(), _row()]))


@pytest.mark.parametrize("oracle", [
    {"kind": "bogus"},                              # 未知 kind
    {"kind": "subprocess"},                         # 缺 argv
    {"kind": "subprocess", "argv": []},             # 空 argv
    {"kind": "subprocess", "argv": "not-a-list"},
    {"kind": "func"},                               # 缺 ref
    {"kind": "func", "ref": "nodot"},               # ref 无模块段
    {"kind": "none"},                               # 缺 reason
])
def test_validate_rejects_bad_oracle_shapes(oracle):
    with pytest.raises(ContractError):
        C.validate_contract(_doc([_row(oracle=oracle)]))


def test_validate_rejects_bad_top_level():
    with pytest.raises(ContractError, match="schema"):
        C.validate_contract({"schema": "nope", "rows": [_row()]})
    with pytest.raises(ContractError, match="rows"):
        C.validate_contract({"schema": C.SCHEMA})
    with pytest.raises(ContractError, match="rows"):
        C.validate_contract({"schema": C.SCHEMA, "rows": []})
    with pytest.raises(ContractError, match="stray_top"):
        C.validate_contract(_doc([_row()], stray_top=1))


# ── runner:faux 腿执行 + 质量报告产物 ──────────────────────────────

def test_runner_executes_faux_legs_and_writes_report(tmp_path):
    table = _write(tmp_path, _doc([
        _row(id="ok-finding", verdict="finding",
             oracle={"kind": "subprocess", "argv": PY_OK}),
        _row(id="gate-red", verdict="gate",
             oracle={"kind": "subprocess", "argv": PY_GATE_RED}),
        _row(id="unbound", verdict="finding",
             oracle={"kind": "subprocess",
                     "argv": ["-c", "print(0)", "$FEED_FILE"]}),
        _row(id="none-leg", verdict="score",
             oracle={"kind": "none", "reason": "待 #350:阳性锚未建"}),
        _row(id="crash", verdict="finding",
             oracle={"kind": "subprocess", "argv": PY_CRASH}),
        _row(id="not-json", verdict="finding",
             oracle={"kind": "subprocess", "argv": PY_NOT_JSON}),
    ]))
    report = run_contract(table, params={}, out_dir=tmp_path)
    by_id = {r["id"]: r for r in report["rows"]}

    assert by_id["ok-finding"]["status"] == "ok"
    assert by_id["ok-finding"]["reading"] == {"n": 3}
    assert by_id["ok-finding"]["gate_pass"] is None   # finding 腿不判门

    assert by_id["gate-red"]["status"] == "ok"        # 读数在手 = 腿跑成
    assert by_id["gate-red"]["gate_pass"] is False    # 期望未满足 = 门红
    assert by_id["gate-red"]["reading"]["failures"][0]["ip"] == "9.9.9.9"

    assert by_id["unbound"]["status"] == "no-reading"
    assert "$FEED_FILE" in by_id["unbound"]["reason"]

    assert by_id["none-leg"]["status"] == "no-reading"
    assert "#350" in by_id["none-leg"]["reason"]

    assert by_id["crash"]["status"] == "failure"
    assert "boom-detail" in by_id["crash"]["error"]
    assert by_id["not-json"]["status"] == "failure"

    # 坏腿留痕不炸整单:failures 面具名,报告照产
    assert [f["id"] for f in report["failures"]] == ["crash", "not-json"]
    s = report["summary"]
    assert (s["n_rows"], s["n_ok"], s["n_no_reading"],
            s["n_failures"]) == (6, 2, 2, 2)
    assert (s["n_gate_total"], s["n_gate_pass"]) == (1, 0)
    assert s["n_gate_failed"] == 0              # crash/not-json 是 finding 腿

    # 质量报告两件落 model/,命名随 ts 后缀惯例
    model = tmp_path / "model"
    [jp] = sorted(model.glob("quality-report-*.json"))
    [mp] = sorted(model.glob("quality-report-*.md"))
    assert json.loads(jp.read_text(encoding="utf-8"))["summary"] == s
    assert jp.stem == mp.stem
    md = mp.read_text(encoding="utf-8")
    for h in ("维度", "指标", "读数", "期望", "判决", "轨道", "触发", "出处"):
        assert h in md
    assert "无读数(待 #350" in md                   # 无读数不静默省略
    assert "$FEED_FILE" in md                        # 未绑定占位符也显形
    assert "boom-detail" in md                       # failures 面进 md
    assert "gate ✗" in md                            # 门红在判决列显形


def test_runner_error_envelope_gate_leg_counts_as_failed_gate(tmp_path):
    """评审 P2-2/P2-3 钉法:§5.2 错误信封腿按 failure 留痕(红态观察,
    非无读数),且崩掉的 gate 腿计入分母并单列——汇总呈 gate 0/1 崩 1,
    不许「gate 0/0 过」假绿。"""
    table = _write(tmp_path, _doc([
        _row(id="env-err", verdict="gate",
             oracle={"kind": "subprocess", "argv": PY_ENV_ERR}),
    ]))
    report = run_contract(table, params={}, out_dir=None)
    r = report["rows"][0]
    assert r["status"] == "failure"
    assert "ENVELOPE_TEST" in r["error"]
    assert "错误信封" in r["error"]
    s = report["summary"]
    assert (s["n_gate_total"], s["n_gate_pass"],
            s["n_gate_failed"]) == (1, 0, 1)
    assert "gate 腿 0/1 过,崩 1" in render_markdown(report)


def test_default_manifest_name_is_env_suffixed(monkeypatch):
    """评审 P2-1 钉法:env=monthly 时 report_dir 与 monthly_eval.sh S7 的
    mirror-manifest.json 同目录,缺省 manifest 名必须带 env 后缀隔离,
    防本地树读数覆写镜像 S7 基线。"""
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")
    assert C._default_params()["MANIFEST"].endswith(
        "mirror-manifest-monthly.json")
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "dev")
    assert C._default_params()["MANIFEST"].endswith(
        "mirror-manifest-dev.json")


def test_runner_subprocess_cwd_pinned_to_backend(tmp_path):
    """腿子进程 cwd 必须钉 backend:实腿全是 -m ipdb.* 形态,backend/ipdb
    或仓根下会 ModuleNotFoundError:ipdb(踩坑实测;cd backend 惯例同
    monthly_eval.sh run_step)。两条钉法:-c 形态验 cwd 在 sys.path,-m
    形态验真实旧子命令可装载。"""
    table = _write(tmp_path, _doc([
        _row(id="cwd-c",
             oracle={"kind": "subprocess", "argv": [
                 "-c",
                 "import ipdb, json; "
                 "print(json.dumps({'mod': ipdb.__name__}))"]}),
        _row(id="cwd-m",
             oracle={"kind": "subprocess",
                     "argv": ["-m", "ipdb._eval.mirror_check"]}),
    ]))
    report = run_contract(table, params={}, out_dir=None)
    by_id = {r["id"]: r for r in report["rows"]}
    # -c 形态:cwd=backend 则 '' (cwd) 在 sys.path,import ipdb 成功
    assert by_id["cwd-c"]["status"] == "ok"
    assert by_id["cwd-c"]["reading"] == {"mod": "ipdb"}
    # -m 形态:无参 mirror_check → 它自己的用法行(stderr),不是模块装载失败
    assert by_id["cwd-m"]["status"] == "failure"
    assert "No module named" not in by_id["cwd-m"]["error"]
    assert "mirror_check" in by_id["cwd-m"]["error"]


def test_runner_gate_green_and_default_params(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_default_params",
                        lambda: {"DATA_DIR": "/tmp/dflt-dir"})
    table = _write(tmp_path, _doc([
        _row(id="g1", verdict="gate",
             oracle={"kind": "subprocess", "argv": PY_OK}),
        _row(id="uses-default", verdict="finding",
             oracle={"kind": "subprocess", "argv": [
                 "-c", "import json,sys; "
                 "print(json.dumps({'p': sys.argv[1]}))", "$DATA_DIR"]}),
    ]))
    report = run_contract(table, out_dir=tmp_path)   # params 缺省 = 内置绑定
    by_id = {r["id"]: r for r in report["rows"]}
    assert by_id["g1"]["gate_pass"] is True
    assert by_id["uses-default"]["reading"] == {"p": "/tmp/dflt-dir"}
    assert report["summary"]["n_gate_pass"] == 1


def test_runner_params_override_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_default_params", lambda: {"DATA_DIR": "/tmp/dflt"})
    table = _write(tmp_path, _doc([
        _row(id="p", oracle={"kind": "subprocess", "argv": [
            "-c", "import json,sys; print(json.dumps({'p': sys.argv[1]}))",
            "$DATA_DIR"]}),
    ]))
    report = run_contract(table, params={"DATA_DIR": "/tmp/cli-bound"},
                          out_dir=None)              # out_dir=None → 只回报告
    assert report["rows"][0]["reading"] == {"p": "/tmp/cli-bound"}
    assert "paths" not in report


def test_runner_func_legs(tmp_path, monkeypatch):
    (tmp_path / "faux_contract_legs.py").write_text(
        "def ok_leg():\n    return {'exclusive_rate': 0.5}\n"
        "def raising_leg():\n    raise ValueError('faux 腿内炸')\n"
        "def gate_green():\n    return {'pass': True, 'n': 1}\n"
        "def gate_red():\n    return {'pass': False}\n"
        "def gate_shapeless():\n    return {'n': 1}\n",
        encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    table = _write(tmp_path, _doc([
        _row(id="f-ok",
             oracle={"kind": "func", "ref": "faux_contract_legs.ok_leg"}),
        _row(id="f-raise",
             oracle={"kind": "func", "ref": "faux_contract_legs.raising_leg"}),
        _row(id="f-gg", verdict="gate",
             oracle={"kind": "func", "ref": "faux_contract_legs.gate_green"}),
        _row(id="f-gr", verdict="gate",
             oracle={"kind": "func", "ref": "faux_contract_legs.gate_red"}),
        _row(id="f-shape", verdict="gate",
             oracle={"kind": "func", "ref": "faux_contract_legs.gate_shapeless"}),
        _row(id="f-missing",
             oracle={"kind": "func", "ref": "faux_contract_legs.no_such"}),
    ]))
    report = run_contract(table, params={}, out_dir=None)
    by_id = {r["id"]: r for r in report["rows"]}
    assert by_id["f-ok"]["status"] == "ok"
    assert by_id["f-ok"]["reading"] == {"exclusive_rate": 0.5}
    assert by_id["f-raise"]["status"] == "failure"
    assert "faux 腿内炸" in by_id["f-raise"]["error"]
    assert by_id["f-gg"]["gate_pass"] is True
    assert by_id["f-gr"]["gate_pass"] is False
    # func gate 腿读数缺布尔 pass 键 = 形状坏,failure 留痕
    assert by_id["f-shape"]["status"] == "failure"
    assert by_id["f-missing"]["status"] == "failure"


def test_markdown_shows_no_reading_for_real_recall_row():
    doc = load_contract(CONTRACT_PATH)
    rows = []
    for r in doc["rows"]:
        rows.append({**r, "status": "no-reading", "reading": None,
                     "gate_pass": None, "rc": None, "error": None,
                     "reason": r["oracle"].get("reason", ""),
                     "elapsed_s": 0.0})
    md = render_markdown({
        "schema": C.REPORT_SCHEMA, "eval_env": "dev",
        "generated_at": "2026-11-15T00:00:00+00:00",
        "contract": {"path": str(CONTRACT_PATH), "n_rows": len(rows)},
        "rows": rows, "failures": [],
        # 汇总走真 _summarize 单源(手拼 dict 会漂:评审 P2-2 加键后曾红)
        "summary": C._summarize(rows)})
    recall_line = next(ln for ln in md.splitlines() if "| 召回 |" in ln)
    assert "无读数(待 #350" in recall_line


# ── CLI:--quality-contract 分发 ──────────────────────────────────────

def test_cli_quality_contract_json(tmp_path, monkeypatch, capsys):
    from ipdb._eval import __main__ as M
    table = _write(tmp_path, _doc([
        _row(id="ok", oracle={"kind": "subprocess", "argv": PY_OK}),
        _row(id="none", oracle={"kind": "none", "reason": "待 #350"}),
    ]), name="cli-contract.json")
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path / "rep")
    M.main(["--quality-contract", "--contract-path", str(table),
            "--contract-param", "FEED_FILE=/tmp/f.txt", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["n_rows"] == 2
    assert out["paths"]["json"].endswith(".json")
    artifacts = sorted(
        p.name for p in (tmp_path / "rep" / "model").glob("quality-report-*"))
    assert len(artifacts) == 2          # .json + .md 两件


def test_cli_quality_contract_human_face(tmp_path, monkeypatch, capsys):
    from ipdb._eval import __main__ as M
    table = _write(tmp_path, _doc([
        _row(id="ok", oracle={"kind": "subprocess", "argv": PY_OK}),
    ]))
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path / "rep")
    M.main(["--quality-contract", "--contract-path", str(table)])
    out = capsys.readouterr().out
    assert "quality-contract:" in out
    assert "quality-report-" in out


def test_cli_rejects_bad_table_rc2(tmp_path, monkeypatch):
    from ipdb._eval import __main__ as M
    bad = _write(tmp_path, _doc([_row(verdict="hard")]))
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    with pytest.raises(SystemExit) as ei:
        M.main(["--quality-contract", "--contract-path", str(bad)])
    assert ei.value.code == 2


def test_cli_rejects_bad_param_rc2(tmp_path, monkeypatch):
    from ipdb._eval import __main__ as M
    table = _write(tmp_path, _doc([
        _row(oracle={"kind": "subprocess", "argv": PY_OK})]))
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    with pytest.raises(SystemExit) as ei:
        M.main(["--quality-contract", "--contract-path", str(table),
                "--contract-param", "NO_EQUALS"])
    assert ei.value.code == 2
