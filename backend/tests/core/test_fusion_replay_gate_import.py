# backend/tests/core/test_fusion_replay_gate_import.py
"""R3-F3 smoke:scripts/fusion_replay_gate 可安全 import(零副作用)。

setrlimit(RLIMIT_DATA) 曾在模块级执行 —— 任何 import 该脚本的进程都被
永久钳 4GiB 硬顶(RLIMIT 硬限一旦调低不可回升),pytest 进程也不例外。
现移入 main() 首行(CLI 跑语义不变),本文件钉住两个方向的契约:
import 零副作用 + main() 入口仍钳。
"""
import resource
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # tests/core -> tests -> backend -> 仓库根


def test_import_fusion_replay_gate_is_side_effect_free():
    before = resource.getrlimit(resource.RLIMIT_DATA)
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import fusion_replay_gate  # noqa: E402  (路径注入后函数内导入)

    # import 不得钳 rlimit(模块级 setrlimit 回归会被此断言抓死)
    assert resource.getrlimit(resource.RLIMIT_DATA) == before
    # 模块契约面在场(防内部重命名把 import 面 silently 弄坏)
    assert fusion_replay_gate._ACCUSING == frozenset({"malicious", "suspicious"})
    assert fusion_replay_gate._PRECEDENCE["malicious"] == 0
    assert fusion_replay_gate.C3_THRESHOLD == 70
    assert fusion_replay_gate.C3_THRESHOLD_HI == 90
    assert callable(fusion_replay_gate.main)
    assert callable(fusion_replay_gate.old_rule)
    assert callable(fusion_replay_gate.fusion_pool)


def test_main_still_clamps_rlimit_when_run():
    """CLI 语义不变:main() 入口即钳 4GiB(子进程验证,不污染本进程)。"""
    code = (
        "import resource, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts')!r})\n"
        "import fusion_replay_gate\n"
        "sys.argv = ['fusion_replay_gate.py', '--data', '/nonexistent']\n"
        "rc = fusion_replay_gate.main()\n"
        "soft = resource.getrlimit(resource.RLIMIT_DATA)[0]\n"
        "print(f'RC={rc} SOFT={soft}')\n"
    )
    # --data 不存在 → main() 在导入 ipdb 前早退 rc=2(无数据面依赖,纯 stdlib 即可跑)
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, check=True)
    assert f"RC=2 SOFT={4 * 1024**3}" in out.stdout
