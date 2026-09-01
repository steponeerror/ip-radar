# backend/tests/source_infra/test_lmdb_progress.py
"""rebuild_lmdb progress 回调:total 检测、跳点位置、map 扩容路径计数。"""
from ipdb._sources._lmdb import BATCH_SIZE, rebuild_lmdb


def _base(tmp_path):
    return tmp_path / "s.lmdb"


def _records(n, val=b"x"):
    return [(f"10.{(i >> 16) & 0xff}.{(i >> 8) & 0xff}.{i & 0xff}/32", [{"f": val.decode()}])
            for i in range(n)]


def test_progress_known_total_initial_then_flush_ticks(tmp_path):
    n_total = 2 * BATCH_SIZE + 5_000          # 两永 mid-flush 边界 + 余数
    calls = []
    rebuild_lmdb(_records(n_total), _base(tmp_path),
                 reader_setter=lambda e: None,
                 progress=lambda n, t: calls.append((n, t)))
    assert calls == [(0, n_total), (BATCH_SIZE, n_total),
                     (2 * BATCH_SIZE, n_total), (n_total, n_total)]


def test_progress_generator_total_unknown_no_initial(tmp_path):
    """无 __len__ 且无 total_est:不发初始(0,total);total 保持 0(诚实
    不定态)—— 2026-09-01 修正:跟随 received 的 (n,n) 会让 UI 在首建全程
    假报 100%,v4 commit + v6 双族长尾期间误导 WarmupBanner。行数反馈由
    WarmupBanner 的 currentRows 分支(received 计数)独立承担。"""
    calls = []
    gen = (r for r in _records(2 * BATCH_SIZE + 5_000))
    rebuild_lmdb(gen, _base(tmp_path),
                 reader_setter=lambda e: None,
                 progress=lambda n, t: calls.append((n, t)))
    assert calls == [(BATCH_SIZE, 0), (2 * BATCH_SIZE, 0),
                     (2 * BATCH_SIZE + 5_000, 0)]


def test_progress_none_smoke(tmp_path):
    n = rebuild_lmdb(_records(50), _base(tmp_path), reader_setter=lambda e: None)
    assert n == 50


def test_progress_survives_map_growth(tmp_path):
    calls = []
    n = rebuild_lmdb(_records(30_000, val=b"y" * 512), _base(tmp_path),
                     reader_setter=lambda e: None, map_size=4 * 1024 * 1024,
                     progress=lambda dn, t: calls.append((dn, t)))
    assert n == 30_000
    ns = [c[0] for c in calls]
    assert ns[0] == 0 and ns[-1] == 30_000 and ns == sorted(ns)
