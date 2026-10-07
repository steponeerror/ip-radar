"""Tests for cancel-aware atomic download helper."""
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from ipdb._sources._download import (
    CancelToken, CancelledError, download_file, atomic_write_bytes)


class _FakeResp:
    def __init__(self, chunks, status=200, final_url=None):
        self._chunks = list(chunks)
        self.status = status
        self.closed = False
        self.headers = {}
        self.final_url = final_url
    def geturl(self):
        return self.final_url or "http://x/y"
    def read(self, n):
        if not self._chunks:
            return b""
        data = self._chunks.pop(0)
        return data[:n]
    def close(self):
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, *a):
        self.close()


def _patch_urlopen(resp):
    return patch("urllib.request.urlopen", return_value=resp)


def test_download_file_writes_atomically(tmp_path: Path):
    dest = tmp_path / "out.txt"
    resp = _FakeResp([b"hello-", b"world"])
    with _patch_urlopen(resp):
        download_file("http://x/y", dest)
    assert dest.read_bytes() == b"hello-world"
    assert not (tmp_path / "out.txt.tmp").exists()  # tmp cleaned


def test_download_file_warns_on_redirect(tmp_path: Path, caplog):
    """绊线(2026-09-05):重定向被 urllib 静默跟随,是 feed URL 腐烂最早
    的信号(上游搬家/改路径)。geturl() != 请求 URL → warn 一次。"""
    import logging as _logging
    dest = tmp_path / "out.txt"
    resp = _FakeResp([b"data"], final_url="http://moved.example/new")
    with caplog.at_level(_logging.WARNING, logger="ipdb._sources._download"):
        with _patch_urlopen(resp):
            download_file("http://x/y", dest)
    assert dest.read_bytes() == b"data"
    hits = [r for r in caplog.records if "redirected" in r.message]
    assert len(hits) == 1 and "http://moved.example/new" in hits[0].getMessage()


def test_download_file_no_redirect_no_warning(tmp_path: Path, caplog):
    import logging as _logging
    dest = tmp_path / "out.txt"
    resp = _FakeResp([b"data"])                  # geturl() == 请求 URL
    with caplog.at_level(_logging.WARNING, logger="ipdb._sources._download"):
        with _patch_urlopen(resp):
            download_file("http://x/y", dest)
    assert not [r for r in caplog.records if "redirected" in r.message]


def test_pre_cancelled_token_raises_and_no_dest(tmp_path: Path):
    dest = tmp_path / "out.txt"
    token = CancelToken()
    token.cancel()
    resp = _FakeResp([b"data"])
    with _patch_urlopen(resp):
        try:
            download_file("http://x/y", dest, token=token)
            assert False, "expected CancelledError"
        except CancelledError:
            pass
    assert not dest.exists()
    assert not (tmp_path / "out.txt.tmp").exists()


def test_cancel_mid_stream_cleans_tmp(tmp_path: Path):
    dest = tmp_path / "out.txt"
    token = CancelToken()
    resp = _FakeResp([b"chunk1"])

    def fake_read(n):
        token.cancel()           # cancel during the read
        return b"chunk1"
    resp.read = fake_read
    with _patch_urlopen(resp):
        try:
            download_file("http://x/y", dest, token=token)
            assert False, "expected CancelledError"
        except CancelledError:
            pass
    assert not dest.exists()
    assert not (tmp_path / "out.txt.tmp").exists()


def test_token_threadsafe_cancel():
    t = CancelToken()
    assert not t.is_cancelled()
    threading.Thread(target=t.cancel).start()
    for _ in range(100):
        if t.is_cancelled():
            break
    assert t.is_cancelled()


# --- DL-F1 (P0, 2026-10-07 A1): 传输层截断守卫 -------------------------
# mid-body 断连的空读曾被当干净 EOF,截断文件被原子落盘为「好文件」;
# 修复 = received != Content-Length 时拒绝,dest 保留旧文件、tmp 被清。

def _seed_dest(dest: Path) -> bytes:
    old = b"previous-good-evidence"
    dest.write_bytes(old)
    return old


def test_truncated_single_chunk_raises_keeps_dest(tmp_path: Path):
    """DL-F1:CL=1000/实发 500(单 chunk)→ RuntimeError,dest 保留旧内容,无 .tmp。"""
    dest = tmp_path / "out.txt"
    old = _seed_dest(dest)
    resp = _FakeResp([b"a" * 500])
    resp.headers["Content-Length"] = "1000"
    with _patch_urlopen(resp):
        with pytest.raises(RuntimeError) as ei:
            download_file("http://x/y", dest)
    msg = str(ei.value)
    assert "truncated download" in msg and "500" in msg and "1000" in msg
    assert dest.read_bytes() == old          # 旧证据未灭失
    assert not (tmp_path / "out.txt.tmp").exists()


def test_truncated_multi_chunk_raises_keeps_dest(tmp_path: Path):
    """DL-F1 变体:CL=1000/实发 500(多 chunk,300+200)→ 同样拒绝。"""
    dest = tmp_path / "out.txt"
    old = _seed_dest(dest)
    resp = _FakeResp([b"a" * 300, b"b" * 200])
    resp.headers["Content-Length"] = "1000"
    with _patch_urlopen(resp):
        with pytest.raises(RuntimeError, match="truncated download"):
            download_file("http://x/y", dest)
    assert dest.read_bytes() == old
    assert not (tmp_path / "out.txt.tmp").exists()


def test_honest_content_length_succeeds_progress_unchanged(tmp_path: Path):
    """DL-F1 ②+④:诚实 CL 正常落盘;进度回调语义不变(逐 chunk 事件 + 最终 100%)。"""
    dest = tmp_path / "out.txt"
    resp = _FakeResp([b"a" * 300, b"b" * 200])
    resp.headers["Content-Length"] = "500"
    token = CancelToken()
    events: list[tuple[int, int]] = []
    token.on_progress = lambda r, t: events.append((r, t))
    with _patch_urlopen(resp):
        download_file("http://x/y", dest, token=token)
    assert dest.read_bytes() == b"a" * 300 + b"b" * 200
    assert not (tmp_path / "out.txt.tmp").exists()
    assert events == [(300, 500), (500, 500), (500, 500)]  # 2 chunk 事件 + final


def test_missing_content_length_chunked_succeeds(tmp_path: Path):
    """DL-F1 ③:无 CL(chunked,total=0)→ 不比对,正常;进度事件 total=0。"""
    dest = tmp_path / "out.txt"
    resp = _FakeResp([b"a" * 300, b"b" * 200])   # headers 无 Content-Length
    token = CancelToken()
    events: list[tuple[int, int]] = []
    token.on_progress = lambda r, t: events.append((r, t))
    with _patch_urlopen(resp):
        download_file("http://x/y", dest, token=token)
    assert dest.read_bytes() == b"a" * 300 + b"b" * 200
    assert not (tmp_path / "out.txt.tmp").exists()
    assert events == [(300, 0), (500, 0)]          # total=0:无 final 100% 事件


# ── atomic_write_bytes (DL-F2):in-memory payload 的全仓统一原子落地 ──

def test_atomic_write_bytes_success_installs_and_cleans_scratch(tmp_path: Path):
    """成功:dest 换新字节,scratch(.tmp)无残留;已有内容被完整替换。"""
    dest = tmp_path / "out.bin"
    dest.write_bytes(b"previous-good-evidence")
    atomic_write_bytes(dest, b"new-evidence")
    assert dest.read_bytes() == b"new-evidence"
    assert not (tmp_path / "out.bin.tmp").exists()


def test_atomic_write_bytes_failure_keeps_dest_and_scratch_cleaned(tmp_path: Path):
    """写 scratch 半途异常(模拟 ENOSPC):dest 旧内容字节级保留,.tmp 清掉,
    异常原样上抛(走 scheduler 既有退避)。side_effect 先真实落盘再抛,
    「无 .tmp 残留」断言面对真存在的 scratch,而非从未写过的空目录。"""
    dest = tmp_path / "out.bin"
    dest.write_bytes(b"previous-good-evidence")
    scratch = tmp_path / "out.bin.tmp"
    real_write = Path.write_bytes
    wrote_partial = False

    def enospc_mid_write(data: bytes):
        nonlocal wrote_partial
        real_write(scratch, data[: len(data) // 2])  # 半途:盘上已有部分字节
        wrote_partial = True
        raise OSError(28, "No space left on device")

    with patch.object(Path, "write_bytes", side_effect=enospc_mid_write):
        with pytest.raises(OSError):
            atomic_write_bytes(dest, b"new-evidence")
    assert wrote_partial                              # 失败时盘上确有真 scratch
    assert dest.read_bytes() == b"previous-good-evidence"
    assert list(tmp_path.glob("*.tmp")) == []
