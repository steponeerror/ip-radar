"""镜像 manifest 守卫测试 (S7 守卫序 + S6 epoch 指纹)。

fixtures 全 tmp_path 假数据目录, 无引擎/DB 依赖。契约 (T13):
- manifest: files/bytes 全量正则文件递归;抽样 32 确定性(sorted 后每
  len//32 取一, <32 全取)sha256 前 16 hex;epoch=镜像 DB 纪元指纹
  (真实纪元标记 = 每源 *.lmdb.ptr 文本一行整数, _sources/_lmdb.py
  read_ptr;指纹=按名排序后 sha256 前 16 hex;缺席 → "",永不炸)。
- check_against_previous: 无 prev → 记基线;files/bytes 骤降 >20% →
  ok=False;epoch 变更单独非失败(纪元前进正常,留痕)。
- main: ok 才落盘新 manifest;失败保留旧档可复现;非 ok 退出码 1。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval.mirror_check import (
    check_against_previous,
    main,
    manifest,
)


def make_files(d: Path, n: int, size: int = 10) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"{i:04d}.bin").write_bytes(b"x" * size)


# ── manifest ──────────────────────────────────────────────────


def test_manifest_counts_all_regular_files_recursive(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 3, size=10)
    (d / "sub").mkdir()
    (d / "sub" / "deep.bin").write_bytes(b"x" * 5)
    m = manifest(d)
    assert m["files"] == 4
    assert m["bytes"] == 35


def test_manifest_epoch_absent_is_empty_string(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 2)
    assert manifest(d)["epoch"] == ""


def test_manifest_epoch_ptr_fingerprint_changes_on_rebuild(tmp_path):
    # 真实纪元标记: <name>.lmdb.ptr 一行整数(read_ptr 契约)
    d = tmp_path / "mirror"
    make_files(d, 2)
    (d / "a.txt.lmdb.ptr").write_text("22\n")
    e1 = manifest(d)["epoch"]
    assert e1 != ""
    (d / "a.txt.lmdb.ptr").write_text("23\n")   # rebuild 换纪元
    assert manifest(d)["epoch"] != e1
    (d / "b.txt.lmdb.ptr").write_text("7\n")    # 新源入册也换指纹
    assert manifest(d)["epoch"] != e1


def test_manifest_sampling_deterministic(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 64, size=4)
    m1, m2 = manifest(d), manifest(d)
    assert m1 == m2
    assert len(m1["sample_sha256"]) == 32      # 64 // 32 = 每 2 取一
    # 少于 32 个文件 → 全取
    d2 = tmp_path / "small"
    make_files(d2, 5)
    assert len(manifest(d2)["sample_sha256"]) == 5


def test_manifest_sample_values_16_hex(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 3)
    m = manifest(d)
    for v in m["sample_sha256"].values():
        assert len(v) == 16 and int(v, 16) >= 0


# ── check_against_previous ────────────────────────────────────


def test_baseline_recorded_when_no_prev(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 7)
    r = check_against_previous(d, None)
    assert r["ok"] is True
    assert "baseline recorded" in r["detail"]
    assert "7" in r["detail"]


def test_files_drop_30pct_fails_loud(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 100)
    prev = manifest(d)
    for f in sorted(d.glob("*.bin"))[70:]:     # 100 → 70 (删 30 个)
        f.unlink()
    r = check_against_previous(d, prev)
    assert r["ok"] is False
    assert "drop" in r["detail"]
    assert "files" in r["detail"]
    assert "-30.0%" in r["detail"]


def test_drop_10pct_within_tolerance(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 100)
    prev = manifest(d)
    for f in sorted(d.glob("*.bin"))[90:]:     # 100 → 90
        f.unlink()
    r = check_against_previous(d, prev)
    assert r["ok"] is True


def test_bytes_drop_fails_loud(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 50, size=100)
    prev = manifest(d)
    for f in d.glob("*.bin"):
        f.write_bytes(b"x" * 50)               # bytes -50%, 文件数不变
    r = check_against_previous(d, prev)
    assert r["ok"] is False
    assert "drop" in r["detail"]
    assert "bytes" in r["detail"]


def test_epoch_change_alone_is_not_failure(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 4)
    (d / "a.txt.lmdb.ptr").write_text("98\n")
    prev = manifest(d)
    (d / "a.txt.lmdb.ptr").write_text("99\n")  # 纪元前进, 计数完好
    r = check_against_previous(d, prev)
    assert r["ok"] is True
    assert "epoch advanced" in r["detail"]


def test_growth_is_ok(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 10)
    prev = manifest(d)
    make_files(d, 20)
    assert check_against_previous(d, prev)["ok"] is True


# ── main(持久化语义)──────────────────────────────────────────


def test_main_baseline_writes_manifest_creates_dir(tmp_path, capsys):
    d = tmp_path / "mirror"
    make_files(d, 6)
    mp = tmp_path / "eval" / "monthly" / "mirror-manifest.json"
    assert main(d, mp) == 0
    assert mp.is_file()                        # 模块自 mkdir -p
    saved = json.loads(mp.read_text())
    assert saved["files"] == 6
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


def test_main_failure_preserves_prev_manifest_and_exits_1(tmp_path, capsys):
    d = tmp_path / "mirror"
    make_files(d, 100)
    mp = tmp_path / "mirror-manifest.json"
    assert main(d, mp) == 0
    capsys.readouterr()                        # 排掉基线轮输出
    before = mp.read_text()
    for f in sorted(d.glob("*.bin"))[50:]:     # -50% → 失败
        f.unlink()
    assert main(d, mp) == 1                    # 非零 = 守卫先于读数拦下
    assert mp.read_text() == before            # 旧 manifest 保留可复现
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "drop" in out["detail"]


def test_main_pass_updates_manifest(tmp_path):
    d = tmp_path / "mirror"
    make_files(d, 10)
    mp = tmp_path / "mirror-manifest.json"
    main(d, mp)
    make_files(d, 12)                          # 增长通过
    assert main(d, mp) == 0
    assert json.loads(mp.read_text())["files"] == 12
