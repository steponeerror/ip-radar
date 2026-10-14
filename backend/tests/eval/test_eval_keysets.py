# backend/tests/eval/test_eval_keysets.py
"""S23 月度源名单快照 + 长记忆列表推导测试。

快照一律经真实 export_source_keysets 落盘(假源只带最小真实接口
.name/._path), 日期控制走 now 参数; 不手造 meta.json。
"""
import gzip
import json
from pathlib import Path

from ipdb._eval.keysets import export_source_keysets, long_memory_ips

DAY = 86400
BASE = 1_700_000_000  # 2023-11-14T22:13:20Z; 纯锚点, 断言只用天级差值


class _FakeSource:
    """最小真实源接口: .name + ._path 原始文件(键集提取与 sample_source_ips 同款)。"""

    def __init__(self, name: str, path: Path):
        self.name = name
        self._path = path


def _make_source(base: Path, name: str, ips: list[str]) -> _FakeSource:
    base.mkdir(parents=True, exist_ok=True)
    p = base / f"{name}.txt"
    p.write_text("\n".join(ips) + "\n")
    return _FakeSource(name, p)


def _snapshot(root: Path, run_id: str, ips: list[str], day: float) -> Path:
    src = _make_source(root / "_raw", run_id, ips)
    return export_source_keysets([src], root, run_id, now=BASE + day * DAY)


def test_four_monthly_snapshots_all_present_in_set(tmp_path):
    # 4 快照 30d 间隔, IP 全程在场: span=90 ≥ 90 且终止于最新 → 入集
    root = tmp_path / "keysets"
    for i in range(4):
        _snapshot(root, f"r{i}", ["1.2.3.4", "9.9.9.9"], i * 30)
    assert long_memory_ips(root) == {"1.2.3.4", "9.9.9.9"}


def test_absent_month_3_breaks_run(tmp_path):
    # 第 3 月缺席(在场日 0/30/90, 缺席缺口 60d > 45)→ 断连出局; 对照 IP 全程在场
    root = tmp_path / "keysets"
    for i in range(4):
        ips = ["9.9.9.9"] + (["1.2.3.4"] if i != 2 else [])
        _snapshot(root, f"r{i}", ips, i * 30)
    lm = long_memory_ips(root)
    assert "1.2.3.4" not in lm and "9.9.9.9" in lm


def test_snapshot_gap_60d_breaks_run(tmp_path):
    # 快照间隔 60d > 45: 全程在场也断连(段内相邻间隔超限, 宁少算)
    root = tmp_path / "keysets"
    for i in range(4):
        _snapshot(root, f"r{i}", ["1.2.3.4"], i * 60)
    assert long_memory_ips(root) == set()


def test_two_snapshots_span_30d_below_min(tmp_path):
    # 仅 2 快照 span=30 < 90 → 出局
    root = tmp_path / "keysets"
    _snapshot(root, "r0", ["1.2.3.4"], 0)
    _snapshot(root, "r1", ["1.2.3.4"], 30)
    assert long_memory_ips(root) == set()


def test_absent_in_latest_snapshot_out(tmp_path):
    # 历史在场但最新快照缺席 → 末见 ≠ 最新快照日期 → 出局
    root = tmp_path / "keysets"
    for i in range(4):
        ips = ["9.9.9.9"] + (["1.2.3.4"] if i < 3 else [])
        _snapshot(root, f"r{i}", ips, i * 30)
    lm = long_memory_ips(root)
    assert "1.2.3.4" not in lm and "9.9.9.9" in lm


def test_presence_union_across_sources(tmp_path):
    # 在场按逐轮并集: 换源接力(sA→sB)仍算持续在场(S23 "任一在册源")
    root = tmp_path / "keysets"
    for i in range(4):
        src_a = _make_source(root / "_raw", f"a{i}",
                             ["1.2.3.4"] if i < 2 else [])
        src_b = _make_source(root / "_raw2", f"b{i}",
                             [] if i < 2 else ["1.2.3.4"])
        export_source_keysets([src_a, src_b], root, f"r{i}",
                              now=BASE + i * 30 * DAY)
    assert long_memory_ips(root) == {"1.2.3.4"}


def test_export_meta_records_and_sorted_dedup_gzip(tmp_path):
    root = tmp_path / "keysets"
    src = _make_source(tmp_path / "_raw", "sA",
                       ["9.9.7.1", "1.1.1.1", "9.9.7.1"])
    run_dir = export_source_keysets([src], root, "run-x",
                                    corpus_fingerprint="cf123", now=BASE)
    assert run_dir == root / "run-x"
    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["run_id"] == "run-x"
    assert meta["date"] == "2023-11-14"
    assert meta["corpus_version_fingerprint"] == "cf123"  # S22 冻结时点绑定
    assert meta["counts"] == {"sA": 2}
    with gzip.open(run_dir / "sA.txt.gz", "rt") as gz:
        assert gz.read().splitlines() == ["1.1.1.1", "9.9.7.1"]  # 排序去重


def test_export_default_fingerprint_null_and_gzip_deterministic(tmp_path):
    root = tmp_path / "keysets"
    src1 = _make_source(tmp_path / "_d1", "sA",
                        ["9.9.7.1", "1.1.1.1", "9.9.7.1"])
    r1 = export_source_keysets([src1], root, "run-y", now=BASE)
    assert json.loads((r1 / "meta.json").read_text())[
        "corpus_version_fingerprint"] is None  # 缺省记 null
    # 确定性 gzip: 同内容(经排序去重)另一轮字节一致(mtime=0)
    src2 = _make_source(tmp_path / "_d2", "sB",
                        ["1.1.1.1", "9.9.7.1", "1.1.1.1"])
    r2 = export_source_keysets([src2], root, "run-z", now=BASE + 5 * DAY)
    assert (r1 / "sA.txt.gz").read_bytes() == (r2 / "sB.txt.gz").read_bytes()
