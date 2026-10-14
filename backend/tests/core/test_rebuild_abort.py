"""rebuild 低内存预警中止(宁停勿死,哲学 9「先消浪费」的保命版):

旧 epoch/ptr 原样、staging 清除、任务走既有失败退避——964MB demo 机
2026-10-11 宿主 OOM 十杀根因的对症修(6.7GB-vm 大源 rebuild 拖死全容器)。
"""
from pathlib import Path

import pytest

from ipdb._sources._lmdb import rebuild_lmdb, read_ptr, RebuildAborted, count_path


def _recs(n: int):
    return [(f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}/32",
             {"verdict": "malicious", "reliability": 0.8}) for i in range(n)]


def _set_ratio(monkeypatch, ratio: float):
    monkeypatch.setattr("ipdb._sources._lmdb._avail_ratio", lambda: ratio)


def _epochs(base: Path):
    return sorted(p.name.rsplit(".", 1)[-1]
                  for p in base.parent.glob(f"{base.name}.*")
                  if p.is_dir() and p.name.rsplit(".", 1)[-1].isdigit())


def test_low_memory_aborts_and_keeps_old_epoch(monkeypatch, tmp_path):
    """flush 边界 avail < 8% → RebuildAborted:ptr/epoch/计数原样,staging 清除。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.9)
    rebuild_lmdb(_recs(12), base, lambda e: None)          # 先建成功 epoch=1
    before_ptr, before_epochs = read_ptr(base), _epochs(base)

    _set_ratio(monkeypatch, 0.05)                          # 5% < 8%
    with pytest.raises(RebuildAborted):
        rebuild_lmdb(_recs(50), base, lambda e: None)

    assert read_ptr(base) == before_ptr                    # ptr 不动 = 旧库原样
    assert _epochs(base) == before_epochs                  # 无新 epoch 目录
    assert not list(base.parent.glob(f"{base.name}.*.new.*"))  # staging 已清


def test_healthy_ratio_never_aborts(monkeypatch, tmp_path):
    """多 flush 边界 + 宽裕内存 → 正常完成(ptr 前进)。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.9)
    n = rebuild_lmdb(_recs(25), base, lambda e: None)      # ≥2 次 flush
    assert n == 25
    assert read_ptr(base) is not None


def test_boundary_ratio_exact_threshold_passes(monkeypatch, tmp_path):
    """ratio == 0.08 不中止(严格小于)。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.08)
    assert rebuild_lmdb(_recs(25), base, lambda e: None) == 25


def test_mid_band_ratio_0p10_no_longer_aborts(monkeypatch, tmp_path):
    """ratio 0.10(旧 0.15 与新 0.08 之间)不再中止——钉住 2026-10-14
    标定 0.15→0.08 的行为变化:demo 机常驻 avail 6-12% 属"磨 swap
    但能活"的合法路径,纪元不再冻结。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.10)
    assert rebuild_lmdb(_recs(25), base, lambda e: None) == 25
    assert read_ptr(base) is not None


def test_retry_after_abort_completes(monkeypatch, tmp_path):
    """中止后重试(内存恢复)→ 完成;残留 staging 由重试开头的自清兜底。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.9)
    rebuild_lmdb(_recs(12), base, lambda e: None)
    _set_ratio(monkeypatch, 0.05)
    with pytest.raises(RebuildAborted):
        rebuild_lmdb(_recs(50), base, lambda e: None)
    _set_ratio(monkeypatch, 0.9)
    assert rebuild_lmdb(_recs(50), base, lambda e: None) == 50
    assert read_ptr(base) is not None


def test_sync_before_abort_recovers_and_completes(monkeypatch, tmp_path):
    """T2(2026-10-14 收敛批)写回后再判死:首测低读数(构建期免刷盘的
    staging 脏页自压)→ env.sync 写回 → 复测恢复 → 不中止完成。avail 序列
    钉住判定序:低 → sync → 复测,而非直接 abort。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    seq = [0.05, 0.5]                       # 首边界:低 → sync 后恢复

    def fake_ratio():
        return seq.pop(0) if seq else 0.5   # 后续边界恒健康

    monkeypatch.setattr("ipdb._sources._lmdb._avail_ratio", fake_ratio)
    base = tmp_path / "t.lmdb"
    assert rebuild_lmdb(_recs(25), base, lambda e: None) == 25   # ≥2 次 flush 边界
    assert read_ptr(base) is not None


def test_persistent_low_ratio_still_aborts_after_sync(monkeypatch, tmp_path):
    """T2 守卫语义保留:sync 后仍低于线 → 照旧 abort(旧 epoch/ptr 原样、
    staging 清除)—— 写回只是抢救,不悬空宁停勿死语义。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.9)
    rebuild_lmdb(_recs(12), base, lambda e: None)
    before_ptr, before_epochs = read_ptr(base), _epochs(base)
    _set_ratio(monkeypatch, 0.05)                          # 恒低:sync 也救不回
    with pytest.raises(RebuildAborted):
        rebuild_lmdb(_recs(50), base, lambda e: None)
    assert read_ptr(base) == before_ptr
    assert _epochs(base) == before_epochs
    assert not list(base.parent.glob(f"{base.name}.*.new.*"))  # staging 已清


def test_zero_records_corrupt_count_sidecar_raises(monkeypatch, tmp_path):
    """零记录守卫加固:count sidecar 存在但不可解析 → raise(损坏=有历史,
    保守守死,grill Q1 批 P2-6);旧 epoch/ptr 原样,staging 清除。
    修复前:int() 失败静默回退 prev=0 → 空重建照常提交清空数据。"""
    _set_ratio(monkeypatch, 0.9)
    base = tmp_path / "t.lmdb"
    rebuild_lmdb(_recs(3), base, lambda e: None)          # count sidecar 落盘
    count_path(base).write_text("not-a-number")
    before_ptr, before_epochs = read_ptr(base), _epochs(base)
    with pytest.raises(RuntimeError, match="corrupted"):
        rebuild_lmdb([], base, lambda e: None)            # 零记录 rebuild
    assert read_ptr(base) == before_ptr                   # ptr 不动 = 旧库原样
    assert _epochs(base) == before_epochs
    assert not list(base.parent.glob(f"{base.name}.*.new.*"))  # staging 已清


def test_commit_order_flag_false_before_reader_swap(monkeypatch, tmp_path):
    """提交序:flag_setter(False) → reader_setter → flag_setter(disjoint)。
    False 只是慢不是错:换 reader 前先把 disjoint 快路径压保守,防上 epoch
    的 True 残留值对可能嵌套的新库在窗口内走快路径静默漏报(2026-10-11)。"""
    _set_ratio(monkeypatch, 0.9)
    base = tmp_path / "t.lmdb"
    calls: list[tuple[str, object]] = []
    rebuild_lmdb(_recs(3), base,                          # 不相交单批 → True
                 reader_setter=lambda e: calls.append(("reader", e)),
                 flag_setter=lambda v: calls.append(("flag", v)))
    assert [c[0] for c in calls] == ["flag", "reader", "flag"]
    assert calls[0] == ("flag", False)
    assert calls[2] == ("flag", True)
