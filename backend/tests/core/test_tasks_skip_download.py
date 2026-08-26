"""④ scheduler retry skips re-download when the raw file is already newer
than the committed ptr (download succeeded, rebuild failed → backoff retry must
not burn quota). Spec 2026-08-26 §3.

Invariant chain: download_file commits via os.replace (raw mtime refreshed);
rebuild_lmdb success writes a NEW ptr (ptr mtime > raw). So
raw_mtime > ptr_mtime ⟺ raw is newer than the last committed build ⟺ skip.
"""
import os
import threading
import time
from pathlib import Path

from ipdb._tasks import UpdateManager

from test_tasks_concurrency import _wait


class _QuotaSrc:
    """Source with a real data file + ptr file, counting downloads."""
    def __init__(self, tmp_path, name="quota_t"):
        self.name = name
        self.download_host = "q.example"
        self._path = tmp_path / "quota_t.csv"
        self._path.write_text("1.2.3.4\n")
        self._ptr = tmp_path / "quota_t.csv.lmdb.ptr"
        self._ptr.write_text("1\n")
        # 与真实 Source 同名同位:_run_task ④ 检查读 _mmdb_path(即 ptr 文件)
        self._mmdb_path = self._ptr
        self.download_calls = 0
        self.rebuild_calls = 0

    def download(self, token=None):
        self.download_calls += 1
        # mimic download_file: atomic replace refreshes mtime
        os.replace(self._path, self._path)  # no-op touch of mtime is NOT guaranteed; do explicit:
        import datetime
        now = time.time() + 100
        os.utime(self._path, (now, now))

    def rebuild(self, progress=None):
        self.rebuild_calls += 1


def _touch(path, t=None):
    t = t if t is not None else time.time()
    os.utime(path, (t, t))


def _mgr(src, **kw):
    locks = {}
    return UpdateManager(
        resolve_source=lambda n: src if n == src.name else None,
        lock_for=lambda n: locks.setdefault(n, threading.Lock()),
        concurrency=1, **kw)


def test_detached_retry_skips_download_when_raw_newer_than_ptr(tmp_path):
    src = _QuotaSrc(tmp_path)
    _touch(src._ptr, time.time() - 1000)        # raw is newer → skip
    mgr = _mgr(src)
    mgr.enqueue_one_detached("quota_t", skip_download_if_fresh=True)
    assert _wait(mgr, lambda: all(
        t.state in ("done", "failed", "cancelled") for t in mgr._tasks.values()))
    t = next(iter(mgr._tasks.values()))
    assert t.state == "done", f"task failed: {t.error}"
    assert src.download_calls == 0, "quota burned: download ran despite fresh raw"
    assert src.rebuild_calls == 1


def test_detached_retry_downloads_when_raw_older_than_ptr(tmp_path):
    src = _QuotaSrc(tmp_path)
    _touch(src._ptr, time.time() + 1000)        # ptr newer → download
    mgr = _mgr(src)
    mgr.enqueue_one_detached("quota_t", skip_download_if_fresh=True)
    assert _wait(mgr, lambda: all(
        t.state in ("done", "failed", "cancelled") for t in mgr._tasks.values()))
    assert src.download_calls == 1, "stale raw must be re-downloaded"


def test_manual_path_never_skips_download(tmp_path):
    src = _QuotaSrc(tmp_path)
    _touch(src._ptr, time.time() - 1000)        # raw newer, but manual path
    mgr = _mgr(src)
    mgr.enqueue_one("quota_t")
    assert _wait(mgr, lambda: all(
        t.state in ("done", "failed", "cancelled") for t in mgr._tasks.values()))
    assert src.download_calls == 1, "manual update must always re-download"


def test_default_flag_off_keeps_current_behavior(tmp_path):
    """enqueue_one_detached without the flag → always download (back-compat)."""
    src = _QuotaSrc(tmp_path)
    _touch(src._ptr, time.time() - 1000)
    mgr = _mgr(src)
    mgr.enqueue_one_detached("quota_t")
    assert _wait(mgr, lambda: all(
        t.state in ("done", "failed", "cancelled") for t in mgr._tasks.values()))
    assert src.download_calls == 1
