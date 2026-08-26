"""② host-lock narrows to the download phase: after download returns, the
lock must be released so the same-host peer's download can start while this
task rebuilds (rebuild is local CPU/disk, unrelated to remote throttling).
Spec: docs/superpowers/specs/2026-08-26-pipeline-three-fixes-design.md §1."""
import threading
import time

from ipdb._tasks import UpdateManager

from test_tasks_concurrency import _Src, _mgr, _wait


def test_host_lock_released_after_download_allows_peer_download_during_rebuild():
    """Same-host A/B: while A is in rebuild(), B's download must have STARTED
    (pre-fix: B waits for A's entire task since the host lock is held through
    rebuild). A's rebuild FAILS the test if B hasn't started within its window —
    waiting for completion instead would pass post-hoc after A releases."""
    in_rebuild = threading.Event()
    b_started = threading.Event()
    a = _Src("a", host="shared")
    b = _Src("b", host="shared")
    orig_rebuild = a.rebuild
    result = {}
    def rebuild_a():
        in_rebuild.set()
        result["peer_started"] = b_started.wait(1.5)
        return orig_rebuild()
    a.rebuild = rebuild_a
    orig_dl = b.download
    def download_b(token=None):
        b_started.set()                  # mark START, before any blocking work
        orig_dl(token)
    b.download = download_b
    mgr, _ = _mgr([a, b], concurrency=2)
    mgr.enqueue_one("a")
    mgr.enqueue_one("b")
    assert in_rebuild.wait(3), "A never reached rebuild"
    assert _wait(mgr, lambda: all(
        t.state in ("done", "failed", "cancelled") for t in mgr._tasks.values()))
    a_task = next(t for t in mgr._tasks.values() if t.source_name == "a")
    assert a_task.state == "done", f"A failed: {a_task.error}"
    assert result["peer_started"], (
        "B's download did not START during A's rebuild — host lock held past download")


def test_host_lock_still_serializes_downloads():
    """Narrowed semantics kept: two same-host downloads must NOT overlap."""
    in_dl = threading.Event()
    overlap = []
    a = _Src("a2", host="shared2")
    b = _Src("b2", host="shared2")
    def guarded_dl(src):
        orig = src.download
        def dl(token=None):
            if in_dl.is_set():
                overlap.append(src.name)
            in_dl.set()
            try:
                return orig(token)
            finally:
                in_dl.clear()
        return dl
    a.download = guarded_dl(a)
    b.download = guarded_dl(b)
    mgr, _ = _mgr([a, b], concurrency=2)
    mgr.enqueue_one("a2")
    mgr.enqueue_one("b2")
    _wait(mgr, lambda: all(
        t.state in ("done", "failed", "cancelled") for t in mgr._tasks.values()))
    assert not overlap, f"same-host downloads overlapped: {overlap}"
