"""Cancel-aware atomic download helper shared by file-backed sources."""
import logging
import os
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


def redact_url(url: str) -> str:
    """下载 URL 日志打码(2026-10-08 C 批 Task 1,事故驱动:OTX 与
    IP2PROXY token 各泄过一次——warn_if_redirected 绊线把带 token 的完整
    下载 URL 打进了 docker 日志)。策略:保留 scheme+host+path(feed 腐烂
    排查需要可见落点),query 整体替换为 "?q=REDACTED"——逐参数白名单
    不做(YAGNI):token 可能藏在任意参数名下,全部 query 按敏感处理;
    userinfo(user:pass@)与 fragment 同属凭据面,一并丢弃。"""
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]
    redacted = urlunsplit((parts.scheme, host, parts.path, "", ""))
    if parts.query:
        redacted += "?q=REDACTED"
    return redacted


def _mask_secret(url: str, secret: str | None) -> str:
    """redact_url 之上再打路径段内嵌 secret(票 #159 P0):abuse.ch v2
    认证端点把 Auth-Key 放在 URL 路径段(v2/files/exports/<KEY>/file),
    redact_url 的「path 保留」策略对它失效——入日志/异常串前把 key 替换
    为 ***。secret 缺省 None 时零操作,既有调用面(40+ 源)行为不变。"""
    masked = redact_url(url)
    if secret:
        masked = masked.replace(secret, "***")
    return masked


def warn_if_redirected(url: str, resp, secret: str | None = None) -> None:
    """feed URL 腐烂早期信号绊线(2026-09-05 IntelMQ 审计):urllib 静默跟随
    重定向,落点 URL ≠ 请求 URL = 上游搬家/改路径——在 404 之前就可见。
    (IntelMQ 用版本化迁移函数沉淀这类变更;我们的等价物 = 本绊线 +
    CHANGELOG feed-change 条目约定。)

    secret: URL 路径段内嵌凭据(abuse.ch v2 Auth-Key,票 #159)——警告
    串里 key 替换为 ***;缺省 None 走既有 redact_url 契约。"""
    final = getattr(resp, "geturl", lambda: None)()
    if final and final != url:
        logger.warning("redirected: %s -> %s (feed URL rot early signal)",
                       _mask_secret(url, secret), _mask_secret(final, secret))


class CancelledError(Exception):
    """Raised when a download is cancelled via its CancelToken."""


class CancelToken:
    """Thread-safe cancellation flag checked between download chunks.

    Also carries an optional ``on_progress`` reporter so ``download_file`` can
    stream byte progress (received, total) to the task runner without each
    source having to thread a callback through its ``download()`` signature —
    every source already passes its ``token`` to ``download_file``.
    """

    def __init__(self):
        self._event = threading.Event()
        self.on_progress: Optional[Callable[[int, int], None]] = None

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


def download_file(
    url: str,
    dest: Path,
    token: CancelToken | None = None,
    *,
    timeout: float = 30,
    headers: dict | None = None,
    chunk_size: int = 65536,
    secret: str | None = None,
) -> None:
    """Stream `url` to `dest` atomically.

    Writes a sibling .tmp file, then os.replace onto `dest` on success — so
    readers only ever see a complete old or new file. Checks `token` between
    chunks; on cancel/failure the .tmp is removed and `dest` is untouched.
    A body shorter than its Content-Length is rejected as truncated, so a
    mid-body disconnect can't masquerade as clean EOF and replace the
    previous good file with a partial one.

    Args:
        timeout: stdlib urllib socket timeout applied to all socket ops
            (connect+read); it cannot be split, and bounds abort latency
            to one read.
        secret: 凭据串(abuse.ch v2 Auth-Key,票 #159)——截断报错串里
            URL 的该串替换为 ***;缺省 None 走既有 redact_url 契约。
    """
    if token is not None and token.is_cancelled():
        raise CancelledError("cancelled before start")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".tmp")
    req = urllib.request.Request(url, headers=headers or {})
    on_progress = getattr(token, "on_progress", None) if token is not None else None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            warn_if_redirected(url, resp, secret=secret)
            total = int(resp.headers.get("Content-Length") or 0)
            received = 0
            with open(tmp, "wb") as f:
                while True:
                    if token is not None and token.is_cancelled():
                        raise CancelledError("cancelled mid-stream")
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if on_progress is not None:
                        on_progress(received, total)
            if total and received != total:
                raise RuntimeError(
                    f"truncated download: {_mask_secret(url, secret)} — got {received} of {total} bytes")
            if on_progress is not None and total > 0:
                on_progress(received, total)  # ensure final 100% lands
        os.replace(str(tmp), str(dest))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_bytes(dest: Path, data: bytes) -> None:
    """Atomically install in-memory `data` at `dest` (single repo entry point).

    Same scratch+replace contract as `download_file`, for the sources that
    build their payload in memory (join/parse/zip-extract/gunzip) instead of
    streaming it: write a sibling .tmp, then os.replace — readers only ever
    see the complete old or new bytes, so a kill/OOM/ENOSPC mid-write can
    never leave a truncated file whose fresh mtime masquerades as new
    evidence (DL-F2). Any exception removes the scratch; `dest` is never
    touched on failure. Text callers encode first (single bytes entry point,
    no per-source variants)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(str(tmp), str(dest))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
