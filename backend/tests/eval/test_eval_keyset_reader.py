# backend/tests/eval/test_eval_keyset_reader.py
"""keyset_reader(全量键集快照读取函数,#569 PR-1 交付)的合同钉。

快照由 keyset_snapshot.py 落(行 = <单元>|<分类类型>,排序,gzip
mtime=0);这里用合成快照钉读取合同,不碰库、不开扫描器。

变异敏感性:
- load_keyset 按 ctype 过滤的分支拆掉(全类型混回)→ 前两条用例红;
- 缺文件返回空集的分支拆掉(炸出)→ 第三条用例红;
- unit_class 的 v6 判据换成「带 / 才是 v6」类错判 → v6 用例红。
"""
import gzip
import json
import sys
from pathlib import Path

# backend/scripts 不在 pytest 的 sys.path(fusion_replay_gate 导入先例,
# tests/core/test_fusion_replay_gate_import.py 同款路径注入)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from keyset_reader import (list_sources, load_keyset, load_keyset_pairs,  # noqa: E402
                           load_meta, unit_class)


def _make_run(tmp_path):
    """合成一轮快照:两源,含 v4 单地址/网段、v6 单地址、双类型同单元。"""
    run_dir = tmp_path / "20260101T000000Z"
    run_dir.mkdir(parents=True)
    files = {
        "spamhaus": [
            "1.0.0.1|blacklist",
            "1.0.0.2|blacklist",
            "10.0.0.0/8|blacklist",
            "2606:4700::1|blacklist",
        ],
        "danmeuk_tor": [
            "9.9.9.9|tor",          # 同单元双类型(审计按 (单元,类型) 对算)
            "9.9.9.9|blacklist",
        ],
    }
    for src, lines in files.items():
        with gzip.open(run_dir / f"{src}.txt.gz", "wb") as gz:
            gz.write(("\n".join(lines) + "\n").encode("utf-8"))
    meta = {"run_id": run_dir.name, "asof": 1_765_000_000.0,
            "epochs": {"spamhaus": [1, None]},
            "units_total": 6, "units_by_class": {"v4_single": 3},
            "n_sources": 2, "counts": {s: len(v) for s, v in files.items()},
            "stats": {"skipped_anomalies": 0, "anomalous_records": 0}}
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return run_dir


def test_unit_class_four_columns():
    """四栏判据:v4/v6 × 单地址/网段(#524 分栏,网段与单地址不互比)。"""
    assert unit_class("1.0.0.1") == "v4_single"
    assert unit_class("10.0.0.0/8") == "v4_cidr"
    assert unit_class("2606:4700::1") == "v6_single"
    assert unit_class("2a00:1450:4001::/48") == "v6_cidr"


def test_load_keyset_filters_by_ctype(tmp_path):
    run = _make_run(tmp_path)
    assert load_keyset(run, "spamhaus", "blacklist") == {
        "1.0.0.1", "1.0.0.2", "10.0.0.0/8", "2606:4700::1"}
    assert load_keyset(run, "spamhaus", "tor") == set()
    assert load_keyset(run, "danmeuk_tor", None) == {"9.9.9.9"}
    assert load_keyset(run, "danmeuk_tor", "tor") == {"9.9.9.9"}
    assert load_keyset(run, "danmeuk_tor", "blacklist") == {"9.9.9.9"}


def test_load_keyset_missing_file_is_empty(tmp_path):
    run = _make_run(tmp_path)
    assert load_keyset(run, "absent", "blacklist") == set()
    assert load_keyset_pairs(run, "absent") == set()


def test_load_keyset_pairs_shape(tmp_path):
    """(单元,分类类型)对集 = pairwise.source_pair_sets 同形状(PR-2
    喂法);同单元双类型各成一队。"""
    run = _make_run(tmp_path)
    assert load_keyset_pairs(run, "danmeuk_tor") == {
        ("9.9.9.9", "tor"), ("9.9.9.9", "blacklist")}


def test_meta_and_sources_roundtrip(tmp_path):
    run = _make_run(tmp_path)
    meta = load_meta(run)
    assert meta["run_id"] == "20260101T000000Z"
    assert meta["epochs"] == {"spamhaus": [1, None]}
    assert list_sources(run) == ["danmeuk_tor", "spamhaus"]
