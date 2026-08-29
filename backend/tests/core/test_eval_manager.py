"""EvalManager 单槽状态机测试(spec 2026-08-28 §5.2):done/busy/failed/timeout。

monkeypatch 目标是 ipdb._eval_manager.subprocess.Popen(模块内引用);假脚本
经临时 .py 文件 + [sys.executable, str(path)] 命令替换执行。
"""
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ipdb._eval_manager import EvalManager, EvalBusyError


def _fake_script(tmp_path: Path, name: str, body: str) -> list:
    s = tmp_path / name
    s.write_text(textwrap.dedent(body))
    return [sys.executable, str(s)]


def _patch_popen(monkeypatch, cmd: list) -> None:
    """把 _eval_manager 内的 subprocess.Popen 换成跑假脚本的真 Popen。

    必须先捕获真 Popen 再替换——否则 lambda 在调用期引用到已被替换的
    subprocess.Popen 名字,无限递归。
    """
    import ipdb._eval_manager as em
    real = em.subprocess.Popen
    monkeypatch.setattr(
        em.subprocess, "Popen",
        lambda *a, **k: real(cmd, stdout=k.get("stdout"),
                             stderr=k.get("stderr"), text=k.get("text")))


def _wait_terminal(m: EvalManager, seconds: float = 15.0) -> dict:
    """轮询至终态;超时即 fail(防止测试悬挂吞掉断言)。"""
    for _ in range(int(seconds / 0.05)):
        if m.current is not None and m.current["state"] != "running":
            return m.current
        time.sleep(0.05)
    pytest.fail(f"job 未在 {seconds}s 内到达终态: {m.current}")


def test_initial_idle():
    assert EvalManager().current is None


def test_run_done(tmp_path, monkeypatch):
    _patch_popen(monkeypatch, _fake_script(tmp_path, "fake_ok.py", "print('{}')\n"))
    m = EvalManager()
    job = m.run("spamhaus")
    assert job["state"] == "running"
    assert job["source"] == "spamhaus"
    assert job["job_id"]
    assert job["started_at"].endswith("Z")        # UTC ISO
    assert job["error"] is None
    final = _wait_terminal(m)
    assert final["state"] == "done"
    assert final["error"] is None


def test_busy(tmp_path, monkeypatch):
    _patch_popen(monkeypatch, _fake_script(
        tmp_path, "fake_slow.py", "import time; time.sleep(30)\n"))
    m = EvalManager(timeout_s=0.3)   # 短超时:测试尾部自动清槽,不留活进程
    m.run("spamhaus")
    with pytest.raises(EvalBusyError) as ei:
        m.run("otx")
    assert ei.value.running_source == "spamhaus"
    _wait_terminal(m)                # 超时清理路径,验证槽位释放


def test_failed_exit_nonzero(tmp_path, monkeypatch):
    _patch_popen(monkeypatch, _fake_script(
        tmp_path, "fake_fail.py",
        "import sys; print('boom', file=sys.stderr); sys.exit(3)\n"))
    m = EvalManager()
    m.run("spamhaus")
    final = _wait_terminal(m)
    assert final["state"] == "failed"
    assert "boom" in final["error"]


def test_timeout(tmp_path, monkeypatch):
    _patch_popen(monkeypatch, _fake_script(
        tmp_path, "fake_hang.py", "import time; time.sleep(30)\n"))
    m = EvalManager(timeout_s=0.2)
    m.run("spamhaus")
    final = _wait_terminal(m)
    assert final["state"] == "failed"
    assert final["error"] == "timeout"
