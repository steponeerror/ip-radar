"""gate 镜像管理测试 (S7 接入关镜像对齐契约 + Q11 常驻增量镜像)。

契约 (Phase 2 T1):
- sync_gate_mirror: rsync -az --partial --delete-after --info=progress2
  <host>:<prod volume>/ <mirror>/(旗标/源路径照 monthly_eval.sh);
  rc=24(源侧活文件消失)容忍当成功, 其余非零 raise(fail-closed);
  dry_run 只回显命令, 不执行不落盘(monthly_eval.sh --dry-run 同义)。
- epoch_fingerprint: 逐源 {<base>.lmdb.ptr 文件名: epoch 值};口径同
  mirror_check._epoch_fingerprint 逐源展开(该处聚合单哈希);不可读 ptr
  记 "?" 不炸;rebuild 换值即变;逐源确定性。
- check_alignment: 逐源比对(值失配/单侧缺席皆失配), detail 列源名;
  双侧皆无 epoch 证据 → 不放行(无证据≠对齐)。
- ensure_gate_mirror: sync → ssh 读远端逐源 epoch → 比对;失配 raise
  GateMirrorMisalignedError(fail-closed, 不跑 gate);对齐返回摘要 dict。

无真实网络: rsync/ssh 一律经注入 stub runner;纯本地红线(不触线上)。
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from ipdb._eval import gate_mirror
from ipdb._eval.gate_mirror import (
    GateMirrorMisalignedError,
    check_alignment,
    ensure_gate_mirror,
    epoch_fingerprint,
    sync_gate_mirror,
)


class StubRunner:
    """rsync/ssh 替身: 零网络;rsync/ssh rc 可配, ssh 回放固定 stdout。"""

    def __init__(self, rsync_rc: int = 0, ssh_rc: int = 0, ssh_stdout: str = ""):
        self.rsync_rc = rsync_rc
        self.ssh_rc = ssh_rc
        self.ssh_stdout = ssh_stdout
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]):
        self.calls.append(list(argv))
        if argv[0] == "rsync":
            return SimpleNamespace(returncode=self.rsync_rc, stdout="", stderr="")
        if argv[0] == "ssh":
            return SimpleNamespace(returncode=self.ssh_rc,
                                   stdout=self.ssh_stdout, stderr="")
        raise AssertionError(f"unexpected command: {argv}")


def make_ptr(d: Path, name: str, epoch: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(epoch + "\n", encoding="utf-8")


# ── sync_gate_mirror ──────────────────────────────────────────


def test_sync_dry_run_emits_command_writes_nothing(tmp_path):
    mirror = tmp_path / "mirror"
    stub = StubRunner()
    r = sync_gate_mirror("root@h", mirror, dry_run=True, runner=stub)
    assert r["ok"] is True and r["dry_run"] is True and r["rc"] is None
    assert r["command"][0] == "rsync"
    assert stub.calls == []                 # 只回显不执行
    assert not mirror.exists()              # 不落盘(连目录都不建)


def test_sync_command_shape_follows_monthly_eval(tmp_path):
    mirror = tmp_path / "mirror"
    r = sync_gate_mirror("root@h", mirror, dry_run=True, runner=StubRunner())
    assert r["command"] == [
        "rsync", "-az", "--partial", "--delete-after", "--info=progress2",
        f"root@h:{gate_mirror.PROD_DATA_DIR}/",   # 尾斜杠=拷内容(monthly_eval.sh)
        f"{mirror}/",
    ]


def test_sync_rc0_and_rc24_tolerated(tmp_path):
    mirror = tmp_path / "mirror"
    r0 = sync_gate_mirror("root@h", mirror, runner=StubRunner(rsync_rc=0))
    assert r0["ok"] is True and r0["rc"] == 0
    r24 = sync_gate_mirror("root@h", mirror, runner=StubRunner(rsync_rc=24))
    assert r24["ok"] is True and r24["rc"] == 24
    assert "24" in r24["note"]              # 容忍但留痕
    assert mirror.is_dir()                  # mkdir -p 先于 rsync(monthly_eval.sh)


def test_sync_other_rc_raises(tmp_path):
    stub = StubRunner(rsync_rc=23)
    with pytest.raises(RuntimeError, match=r"rc=23"):
        sync_gate_mirror("root@h", tmp_path / "m", runner=stub)


# ── epoch_fingerprint(逐源)──────────────────────────────────


def test_epoch_fingerprint_per_source_mapping_stable(tmp_path):
    d = tmp_path / "mirror"
    make_ptr(d, "a.txt.lmdb.ptr", "22")
    (d / "sub").mkdir()
    (d / "sub" / "b.txt.lmdb.ptr").write_text("7\n", encoding="utf-8")  # rglob 递归
    fp = epoch_fingerprint(d)
    assert fp == {"a.txt.lmdb.ptr": "22", "b.txt.lmdb.ptr": "7"}
    assert epoch_fingerprint(d) == fp       # 逐源确定性(两次调用一致)


def test_epoch_fingerprint_changes_on_rebuild(tmp_path):
    d = tmp_path / "mirror"
    make_ptr(d, "a.txt.lmdb.ptr", "22")
    before = epoch_fingerprint(d)
    make_ptr(d, "a.txt.lmdb.ptr", "23")     # rebuild 换纪元
    assert epoch_fingerprint(d) != before


def test_epoch_fingerprint_unreadable_ptr_records_question(tmp_path):
    d = tmp_path / "mirror"
    make_ptr(d, "ok.lmdb.ptr", "5")
    (d / "bad.lmdb.ptr").mkdir()            # 读目录 → OSError → "?"(口径同 mirror_check)
    assert epoch_fingerprint(d) == {"ok.lmdb.ptr": "5", "bad.lmdb.ptr": "?"}


# ── check_alignment ───────────────────────────────────────────


def test_check_alignment_aligned_lists_count(tmp_path):
    d = tmp_path / "mirror"
    make_ptr(d, "a.txt.lmdb.ptr", "22")
    make_ptr(d, "b.txt.lmdb.ptr", "7")
    r = check_alignment(d, {"a.txt.lmdb.ptr": "22", "b.txt.lmdb.ptr": "7"})
    assert r["aligned"] is True
    assert "2" in r["detail"]


def test_check_alignment_value_mismatch_lists_source_name(tmp_path):
    d = tmp_path / "mirror"
    make_ptr(d, "a.txt.lmdb.ptr", "22")
    r = check_alignment(d, {"a.txt.lmdb.ptr": "23"})
    assert r["aligned"] is False
    assert "a.txt.lmdb.ptr" in r["detail"]  # detail 列失配源名
    assert "22" in r["detail"] and "23" in r["detail"]


def test_check_alignment_source_missing_on_either_side(tmp_path):
    d = tmp_path / "mirror"
    make_ptr(d, "local_only.lmdb.ptr", "3")
    r = check_alignment(d, {"remote_only.lmdb.ptr": "4"})
    assert r["aligned"] is False
    assert "local_only.lmdb.ptr" in r["detail"]
    assert "remote_only.lmdb.ptr" in r["detail"]


def test_check_alignment_no_evidence_on_both_sides_fails_closed(tmp_path):
    d = tmp_path / "mirror"
    d.mkdir()
    r = check_alignment(d, {})
    assert r["aligned"] is False             # 无证据≠对齐(路径错/半截同步)


# ── ensure_gate_mirror(sync→ssh 读→比对)─────────────────────


def test_ensure_gate_mirror_aligned_returns_summary(tmp_path):
    mirror = tmp_path / "mirror"
    make_ptr(mirror, "a.txt.lmdb.ptr", "22")
    make_ptr(mirror, "b.txt.lmdb.ptr", "7")
    stub = StubRunner(ssh_stdout="a.txt.lmdb.ptr=22\nb.txt.lmdb.ptr=7\n")
    r = ensure_gate_mirror("root@h", mirror, runner=stub)
    assert r["alignment"]["aligned"] is True
    assert r["prod_epochs"] == {"a.txt.lmdb.ptr": "22", "b.txt.lmdb.ptr": "7"}
    assert r["mirror_epochs"] == {"a.txt.lmdb.ptr": "22", "b.txt.lmdb.ptr": "7"}
    assert r["sync"]["rc"] == 0
    assert [c[0] for c in stub.calls] == ["rsync", "ssh"]   # 序: sync → ssh 读
    assert stub.calls[1][1] == "root@h"     # ssh 形态照 monthly_eval.sh(裸 ssh)


def test_ensure_gate_mirror_mismatch_raises_named_source(tmp_path):
    mirror = tmp_path / "mirror"
    make_ptr(mirror, "a.txt.lmdb.ptr", "22")
    stub = StubRunner(ssh_stdout="a.txt.lmdb.ptr=23\n")
    with pytest.raises(GateMirrorMisalignedError) as ei:
        ensure_gate_mirror("root@h", mirror, runner=stub)
    assert "a.txt.lmdb.ptr" in str(ei.value)          # detail 列失配源名
    assert ei.value.detail == str(ei.value)
    assert [c[0] for c in stub.calls] == ["rsync", "ssh"]  # 拒跑发生在同步+读之后


def test_ensure_gate_mirror_stale_mirror_source_raises(tmp_path):
    # 镜像残留已下线源的 ptr(rsync 与 ssh 读之间生产撤源/换纪元)→ 拒跑
    mirror = tmp_path / "mirror"
    make_ptr(mirror, "stale.lmdb.ptr", "9")
    stub = StubRunner(ssh_stdout="new.lmdb.ptr=1\n")
    with pytest.raises(GateMirrorMisalignedError, match="stale.lmdb.ptr"):
        ensure_gate_mirror("root@h", mirror, runner=stub)


def test_ensure_gate_mirror_sync_failure_propagates(tmp_path):
    stub = StubRunner(rsync_rc=23)
    with pytest.raises(RuntimeError, match="rsync"):
        ensure_gate_mirror("root@h", tmp_path / "m", runner=stub)
    assert [c[0] for c in stub.calls] == ["rsync"]    # 失败后不再 ssh


def test_ensure_gate_mirror_ssh_failure_raises(tmp_path):
    mirror = tmp_path / "mirror"
    make_ptr(mirror, "a.txt.lmdb.ptr", "22")
    stub = StubRunner(ssh_rc=255)
    with pytest.raises(RuntimeError, match="ssh"):
        ensure_gate_mirror("root@h", mirror, runner=stub)
