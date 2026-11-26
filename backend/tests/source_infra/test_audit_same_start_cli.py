"""audit_same_start.py 命令行面测试(#476:同起点审计只留一份,接入关改用本脚本)。

脚本层契约(subprocess 真跑,数据目录 tmp_path;脚本自己把 IP_RADAR_DATA_DIR
定到 --data 再导 ipdb,原始文件缺席的源走 SKIPPED,零网络零写入):
- `--sources` 点名的源没登记、或登记了但禁用 → ERROR 行 + 退出码 1
  (接入关里「审不了」必须判不合格——无证据不等于没问题);
- 点名单源时输出里只有这一个源的数据行,其余源零行(不被重建);
- 同起点碰撞(同 start 异 prefixlen)→ VIOLATIONS + 退出码 1;
- 不给 `--sources` 时全部登记源都出现在输出里(缺省行为不变)。
"""
import os
import subprocess
import sys
from pathlib import Path

from ipdb._registry import _sources

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "audit_same_start.py"

# 逐行解析的启用源(IpListSource):原始文件放 tmp 数据目录即可走通 rebuild,
# spy 在 rebuild_dual_family 模块属性上截流,不落任何 LMDB 件。
_PLAIN_SOURCE = "binarydefense"
_PLAIN_FILE = "binarydefense_banlist.txt"


def _run(data_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "IP_RADAR_DATA_DIR"}
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--data", str(data_dir), *extra],
        capture_output=True, text=True, timeout=300, env=env)


def _data_lines(out: str) -> list[str]:
    """输出里的逐源数据行:排除表头(auditing…)、汇总(--- summary)、
    违例明细(四空格缩进)与脚本级 ERROR 行,余下都是「源名: …」行。"""
    return [l for l in out.splitlines()
            if l.strip()
            and not l.startswith(("auditing", "--- summary", "ERROR:"))
            and not l.startswith("    ")]


def test_sources_unknown_or_disabled_error_rc1(tmp_path):
    """点名没登记的名字 → rc1 + ERROR;登记了但禁用 → rc1 + ERROR(#476 裁决:
    接入关「审不了」= 不合格)。禁用面走 source_state.json 的 disabled 键
    (注册表导入时经 _paths.source_state_path() 读同一数据目录)。"""
    r = _run(tmp_path, "--sources", "no_such_source")
    assert r.returncode == 1
    assert "ERROR" in r.stdout
    assert "no_such_source" in r.stdout

    (tmp_path / "source_state.json").write_text(
        '{"disabled": ["binarydefense"]}', encoding="utf-8")
    r = _run(tmp_path, "--sources", "binarydefense")
    assert r.returncode == 1
    assert "ERROR" in r.stdout
    assert "not enabled" in r.stdout


def test_sources_single_scopes_rebuild(tmp_path):
    """点名单源:只有它的数据行;别的源一行都不出现(连 SKIPPED 都没有)。"""
    (tmp_path / _PLAIN_FILE).write_text(
        "203.0.113.5\n198.51.100.7\n", encoding="utf-8")
    r = _run(tmp_path, "--sources", _PLAIN_SOURCE)
    assert r.returncode == 0
    lines = _data_lines(r.stdout)
    assert len(lines) == 1, lines
    assert lines[0].startswith(f"{_PLAIN_SOURCE}: rows=2 keys=2 CLEAN")
    for s in _sources:
        if s.name != _PLAIN_SOURCE:
            assert f"{s.name}:" not in r.stdout


def test_same_start_collision_rc1(tmp_path):
    """同 start 异 prefixlen 两行 → VIOLATIONS + rc1(接入关的碰撣样本形态:
    逐行解析源的数据文件里同起点两行长短不一)。"""
    (tmp_path / _PLAIN_FILE).write_text(
        "203.0.113.0/24\n203.0.113.0/25\n", encoding="utf-8")
    r = _run(tmp_path, "--sources", _PLAIN_SOURCE)
    assert r.returncode == 1
    assert "VIOLATIONS" in r.stdout
    assert "203.0.113.0/24 & 203.0.113.0/25" in r.stdout


def test_no_sources_flag_lists_all_registered(tmp_path):
    """不给 --sources:行为不变——全部登记源(此处全启用,tmp 目录无
    source_state.json)都出现在输出里,缺席原始文件的走 SKIPPED 行。"""
    r = _run(tmp_path)
    assert r.returncode == 0
    assert f"auditing {len(_sources)} enabled sources" in r.stdout
    for s in _sources:
        assert f"{s.name}:" in r.stdout
