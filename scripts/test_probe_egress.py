"""scripts/probe-egress.sh 的单测(#304②,外联路由一次性探测)。

跑法(仓根): python3 -m pytest scripts/test_probe_egress.py -q

覆盖矩阵(全部零网络——只测参数面与清单面,不真探测):
- --list:默认四通道清单(exa.ai/r.jina.ai/api.github.com/raw.githubusercontent.com,
  事实源=docs 仓 notes 两篇研究注记,见脚本头注)全打印且恰四条;
- 位置参数追加端点进清单(去重保序),非 http(s) 端点拒收(用法错非零退出);
- --timeout 缺值/非数值拒收(非数值若漏到探测期会变「不可达 rc 0」,须在参数面拦下);--help 零退出。
默认清单被改丢通道时测试红(端点事实钉死,防清单静默缩水)。
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).resolve().parent / "probe-egress.sh"
DEFAULTS = [
    "https://exa.ai",
    "https://r.jina.ai",
    "https://api.github.com",
    "https://raw.githubusercontent.com",
]


def run(*args: str) -> subprocess.CompletedProcess:
    # cwd=REPO + 脚本绝对路径:从任意目录调用的形态与 CI 步一致
    return subprocess.run(
        [ "bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=REPO, timeout=30,
    )


def test_list_prints_default_manifest_exactly():
    r = run("--list")
    assert r.returncode == 0, r.stderr
    urls = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith("https://")]
    assert urls == DEFAULTS, f"默认清单漂移:{urls}(事实源=docs 仓 notes,改动须带出处)"


def test_list_appends_positional_endpoints_dedup_in_order():
    r = run("--list", "https://example.org/foo", "https://exa.ai", "https://example.org/bar")
    assert r.returncode == 0, r.stderr
    urls = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith("https://")]
    # 追加两个新端点;重复的 exa.ai 只计一次且保序
    assert urls == DEFAULTS + ["https://example.org/foo", "https://example.org/bar"], urls


def test_non_url_positional_is_usage_error():
    r = run("--list", "not-a-url")
    assert r.returncode != 0
    assert "http" in (r.stderr + r.stdout)


def test_timeout_requires_value():
    r = run("--list", "--timeout")
    assert r.returncode != 0
    assert "--timeout" in (r.stderr + r.stdout)


def test_timeout_non_numeric_is_usage_error_exit_2():
    # tri-ci 评审 P2:非数值必须在参数面 exit 2——探测件不持门(不可达也 rc 0),
    # 若漏到探测期,curl --max-time 拒参会被 probe_one 吞成「不可达 rc 0」的假观测
    r = run("--list", "--timeout", "15s")
    assert r.returncode == 2
    assert "--timeout" in (r.stderr + r.stdout)
    assert "用法错" in (r.stderr + r.stdout)


def test_help_exits_zero():
    r = run("--help")
    assert r.returncode == 0
    assert "--list" in r.stdout
