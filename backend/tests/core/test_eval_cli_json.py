"""eval CLI --json 模式与 REPORT_DIR 迁移测试(spec 2026-08-28 §5.2)。

失败路径(nosuchsrc)不依赖本地数据;happy-path 依赖 backend/data 已构建的
binarydefense 库 + corpus.json + pymispwarninglists,缺失则跳过并注明。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]          # backend/

_ERROR_HINT = "确认 DB 已 load"


def _run_cli(args, env_extra=None, timeout=600):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, "-m", "ipdb._eval", *args],
        cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=timeout)


def _benign_ok() -> bool:
    try:
        import pymispwarninglists  # noqa: F401
        return True
    except Exception:
        return False


def test_cli_json_failure_path_is_valid_json(tmp_path):
    """nosuchsrc --json → stdout 合法 JSON 错误体(source_not_found + hint),退出非 0。"""
    p = _run_cli(["nosuchsrc", "--json"], {"IP_RADAR_EVAL_DIR": str(tmp_path)})
    out = json.loads(p.stdout)              # --json 下错误体也必须是合法 JSON
    assert out["error"]["code"] == "source_not_found"
    assert "hint" in out["error"]
    assert p.returncode != 0
    assert "Traceback" not in p.stderr      # 不许未处理异常漏栈


def test_report_dir_respects_env(tmp_path):
    """REPORT_DIR 尊重 IP_RADAR_EVAL_DIR(导入期读取)。"""
    p = subprocess.run(
        [sys.executable, "-c", "import ipdb._eval.__main__ as m; print(m.REPORT_DIR)"],
        cwd=str(BACKEND), env={**os.environ, "IP_RADAR_EVAL_DIR": str(tmp_path)},
        capture_output=True, text=True, timeout=120)
    assert Path(p.stdout.strip()) == tmp_path


def test_report_dir_default_is_backend_data_eval():
    """默认落 <repo>/backend/data/eval(不再写 docs/eval)。"""
    p = subprocess.run(
        [sys.executable, "-c", "import ipdb._eval.__main__ as m; print(m.REPORT_DIR)"],
        cwd=str(BACKEND), capture_output=True, text=True, timeout=120)
    assert Path(p.stdout.strip()) == (BACKEND / "data" / "eval").resolve()
_BD_PTR = BACKEND / "data" / "binarydefense_banlist.txt.lmdb.ptr"


def test_json_load_db_failure_is_envelope(monkeypatch, capsys):
    """P2 修正:--json 下 load_db 失败走 stdout JSON 信封,不许 stderr 裸栈。"""
    import ipdb._registry as reg
    from ipdb._eval.__main__ import main

    def _boom():
        raise RuntimeError("db not built")

    monkeypatch.setattr(reg, "load_db", _boom)
    with pytest.raises(SystemExit) as ei:
        main(["spamhaus", "--json"])
    assert ei.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "internal"
    assert "hint" in out["error"]


def test_json_missing_source_arg_is_envelope(monkeypatch, capsys):
    """P2 修正:--json 且缺 source → JSON bad_request,替代 argparse p.error 裸退出。"""
    import ipdb._registry as reg
    from ipdb._eval.__main__ import main

    monkeypatch.setattr(reg, "load_db", lambda: None)   # 不依赖本地数据
    with pytest.raises(SystemExit) as ei:
        main(["--json"])
    assert ei.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "bad_request"
    assert "hint" in out["error"]


@pytest.mark.skipif(
    not (_BD_PTR.exists() and _benign_ok() and (BACKEND / "ipdb" / "_eval" / "corpus.json").exists()),
    reason="本机缺 binarydefense 已构建库 / corpus / pymispwarninglists,happy-path 无法实跑")
def test_cli_json_happy_path_binarydefense(tmp_path):
    """真实源 --json:stdout 为 write_report 同 schema + source,报告落 env 目录。"""
    p = _run_cli(["binarydefense", "--json"], {"IP_RADAR_EVAL_DIR": str(tmp_path)})
    assert p.returncode == 0, p.stderr[-500:]
    out = json.loads(p.stdout)
    # schema 以 report.render_json 为准:source/generated_at/verdict{state,...}/metrics
    assert out["source"] == "binarydefense"
    assert out["verdict"]["state"]                      # POSITIVE-*/INSUFFICIENT-* 非空
    assert isinstance(out["metrics"], dict) and out["metrics"]
    assert out["generated_at"]                          # date 串
    assert list(tmp_path.glob("binarydefense-*.json")), "报告应落 IP_RADAR_EVAL_DIR"
    assert not (BACKEND / "data" / "eval").exists() or not any(
        (BACKEND / "data" / "eval").glob("binarydefense-*.json")), "不得回落默认目录"
