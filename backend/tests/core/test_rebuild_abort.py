"""rebuild 低内存预警中止(宁停勿死,哲学 9「先消浪费」的保命版):

旧 epoch/ptr 原样、staging 清除、任务走既有失败退避——964MB demo 机
2026-10-11 宿主 OOM 十杀根因的对症修(6.7GB-vm 大源 rebuild 拖死全容器)。
"""
from pathlib import Path

import pytest

from ipdb._sources._lmdb import rebuild_lmdb, read_ptr, RebuildAborted


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
    """flush 边界 avail < 15% → RebuildAborted:ptr/epoch/计数原样,staging 清除。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.9)
    rebuild_lmdb(_recs(12), base, lambda e: None)          # 先建成功 epoch=1
    before_ptr, before_epochs = read_ptr(base), _epochs(base)

    _set_ratio(monkeypatch, 0.10)                          # 10% < 15%
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
    """ratio == 0.15 不中止(严格小于)。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.15)
    assert rebuild_lmdb(_recs(25), base, lambda e: None) == 25


def test_retry_after_abort_completes(monkeypatch, tmp_path):
    """中止后重试(内存恢复)→ 完成;残留 staging 由重试开头的自清兜底。"""
    monkeypatch.setattr("ipdb._sources._lmdb.BATCH_SIZE", 10)
    base = tmp_path / "t.lmdb"
    _set_ratio(monkeypatch, 0.9)
    rebuild_lmdb(_recs(12), base, lambda e: None)
    _set_ratio(monkeypatch, 0.10)
    with pytest.raises(RebuildAborted):
        rebuild_lmdb(_recs(50), base, lambda e: None)
    _set_ratio(monkeypatch, 0.9)
    assert rebuild_lmdb(_recs(50), base, lambda e: None) == 50
    assert read_ptr(base) is not None
