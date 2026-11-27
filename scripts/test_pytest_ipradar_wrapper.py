"""scripts/pytest_ipradar.sh 的回退提示(#511 评审建议 4)。

包装器找不到 backend/.venv 时会退回 PATH 上的 python3;#511 起这一步往
stderr 打一行提示。这里把脚本拷进临时目录,造「有 venv」「没有 venv」两种
布局各跑一次 -h(-h 在 exec 解释器之前就退出,不依赖任何 Python 环境)。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "pytest_ipradar.sh"
HINT = "backend/.venv 缺失"


def _run(root: Path) -> subprocess.CompletedProcess:
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "scripts" / "pytest_ipradar.sh")
    (root / "backend").mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_IPRADAR")}
    return subprocess.run(
        ["bash", "../scripts/pytest_ipradar.sh", "-h"],
        cwd=root / "backend", capture_output=True, text=True, timeout=60, env=env,
    )


def test_wrapper_warns_when_venv_missing(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert HINT in r.stderr, r.stderr
    assert "解释器 = " in r.stderr, r.stderr


def test_wrapper_quiet_when_venv_present(tmp_path):
    r0 = _run(tmp_path)
    assert HINT in r0.stderr, "前提:没有 venv 时要有提示,否则下面那条断言是空的"
    venv = tmp_path / "backend" / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(Path(sys.executable).resolve())
    r1 = subprocess.run(
        ["bash", "../scripts/pytest_ipradar.sh", "-h"],
        cwd=tmp_path / "backend", capture_output=True, text=True, timeout=60,
    )
    assert r1.returncode == 0, r1.stderr
    assert HINT not in r1.stderr, r1.stderr
