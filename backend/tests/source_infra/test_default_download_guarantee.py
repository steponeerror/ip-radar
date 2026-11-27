"""A 家族默认下载的传输保证(#491,2026-11-27;返工按评审建议改 1-3/6/7)。

钉的行为(``ipdb._source_base.Source.download`` 重写后):
- 内部走 ``_sources._download.download_file``:预取消/流中取消生效、
  Content-Length 截断守卫生效、逐块 ``token.on_progress`` 回调、原子落盘
  (落盘契约不变:原始字节,ADR 0014);
- 网络类失败重试 3 次、退避 2s/4s(经 ``ipdb._source_base._sleep_backoff``
  可观察缝桩掉真 sleep);确定性 4xx 不重试(5xx/408/429 照旧,返工 2);
- 空响应立刻失败不重试,旧文件字节保留(空体守卫挂 download_file 的
  ``validate`` 口子,落盘前拒绝);
- 无 Content-Length 且非分块(close-delimited):一行告警(截断不可判),
  下载照常完成;分块响应不告警(分块截断由 http.client 的 IncompleteRead
  兑底,返工 1)。

全部用例只打 127.0.0.1 一次性 stub 服务器(零外网;事实包探针同法)。
真实源类取 BruteforceSource / TweetFeedSource 两个代表(任务书测试 1),
``url`` 实例属性覆写指向 stub。用例编号对应任务书「测试」一节 1-7,
返工新增用例在文件尾部。
"""
import http.client
import logging
import socket
import ssl
import struct
import threading
import time
import urllib.error

import pytest

from ipdb._source_base import _is_retryable
from ipdb._sources._download import CancelToken, CancelledError
from ipdb._sources.bruteforce import BruteforceSource
from ipdb._sources.tweetfeed import TweetFeedSource


@pytest.fixture(autouse=True)
def _no_proxy_for_loopback(monkeypatch):
    """返工 6(评审建议 7):本文件是仓里第一组真 127.0.0.1 socket + 真
    urllib 的用例(其余测试都 patch urlopen)。环境有 HTTP_PROXY 而没有
    NO_PROXY=127.0.0.1 时,urllib 会把回环请求发给代理,用例卡到读超时;
   本地门和 CI 都没设代理才一直是绿的——这里把两条大小写形态都钉住。"""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")


class _FeedServer:
    """一次性 127.0.0.1 stub HTTP 服务器:每个连接回放 ``behavior(conn, n)``
    写的原始字节(n = 第几次请求,1 起),``requests`` 记请求次数。行为函数
    写裸字节,方便构造半截 / RST / 无 Content-Length 的非常规响应。"""

    def __init__(self, behavior):
        self.behavior = behavior
        self.requests = 0
        self._lsock = socket.create_server(("127.0.0.1", 0))
        self.port = self._lsock.getsockname()[1]
        # 轮询 accept(0.2s 超时):Linux 上 close 监听口不唤醒阻塞中的
        # accept,不轮询的话 close() 的 join 每测试白等 5s(实测)。
        self._lsock.settimeout(0.2)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        n = 0
        while True:
            try:
                conn, _ = self._lsock.accept()
            except TimeoutError:      # socket.timeout 别名:轮询周期
                continue
            except OSError:
                return                    # 监听口关闭 = 服务器下线
            n += 1
            self.requests = n
            try:
                self._drain(conn)
                self.behavior(conn, n)
            except OSError:
                pass                      # 客户端中途断连(取消/重试)是常态
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    @staticmethod
    def _drain(conn):
        conn.settimeout(5)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk

    def close(self):
        self._lsock.close()
        self._thread.join(timeout=5)


def _http_ok(body: bytes, content_length: bool = True) -> bytes:
    head = b"HTTP/1.1 200 OK\r\n"
    if content_length:
        head += b"Content-Length: %d\r\n" % len(body)
    return head + b"Connection: close\r\n\r\n" + body


def _http_status(code: int, reason: str) -> bytes:
    """非 2xx 空体响应(urllib 对 4xx/5xx 抛 HTTPError,响应不进 download_file)。"""
    return (b"HTTP/1.1 %d %s\r\nContent-Length: 0\r\n"
            b"Connection: close\r\n\r\n" % (code, reason.encode()))


def _reset(conn):
    """连接级 RST(SO_LINGER 0 秒猛关):客户端读到 ConnectionResetError
    (urllib 连接期包成 URLError,同属可重试判据)。"""
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                    struct.pack("ii", 1, 0))
    conn.close()


def _make_source(cls, tmp_path, port):
    src = cls(data_dir=tmp_path)
    src.url = f"http://127.0.0.1:{port}/feed"
    return src


def test_normal_download_bytes_identical_and_progress(tmp_path):
    """用例 1:两个真实 A 家族类走默认下载,落盘字节与服务器发送逐字节
    相同、scratch 不残留;``token.on_progress`` 被调过(旧实现从不回调)。"""
    body = b"# header\n1.2.3.4\n5.6.7.8\n"
    progress = []
    for cls in (BruteforceSource, TweetFeedSource):
        server = _FeedServer(lambda conn, n: conn.sendall(_http_ok(body)))
        try:
            src = _make_source(cls, tmp_path, server.port)
            token = CancelToken()
            token.on_progress = lambda r, t: progress.append((r, t))
            src.download(token=token)
            assert src._path.read_bytes() == body
            assert not (tmp_path / (src.filename + ".tmp")).exists()
        finally:
            server.close()
    assert progress, "on_progress never called"


def test_pre_cancelled_token_no_request_old_file_intact(tmp_path):
    """用例 2:预先取消 → CancelledError 原样上抛,零网络请求,_path 不
    存在(test_download.py 预取消用例的形状搬到 A 家族默认路径)。"""
    server = _FeedServer(lambda conn, n: conn.sendall(_http_ok(b"data")))
    try:
        src = _make_source(BruteforceSource, tmp_path, server.port)
        token = CancelToken()
        token.cancel()
        with pytest.raises(CancelledError):
            src.download(token=token)
        assert not src._path.exists()
        assert server.requests == 0
    finally:
        server.close()


def test_cancel_mid_stream_old_file_untouched(tmp_path):
    """用例 3:发到一半取消 → CancelledError,旧文件字节不变。服务器先
    发半截再停住——客户端阻塞在带长度 read 上,直到 EOF 才收到首块并经
    on_progress 取消(on_progress 里取消 = 确定性,不赌时序)。"""
    old = b"previous-good-evidence"

    def partial_then_stall(conn, n):
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 200\r\n\r\n"
                     + b"x" * 20)
        time.sleep(0.5)     # 客户端读到首块(EOF)→ 取消 → 抛错断连

    server = _FeedServer(partial_then_stall)
    try:
        src = _make_source(TweetFeedSource, tmp_path, server.port)
        src._path.write_bytes(old)
        token = CancelToken()
        token.on_progress = lambda r, t: token.cancel()
        with pytest.raises(CancelledError):
            src.download(token=token)
        assert src._path.read_bytes() == old
        assert server.requests == 1          # 取消不重试
    finally:
        server.close()


def test_truncated_with_cl_retries_three_times_keeps_old(tmp_path, monkeypatch):
    """用例 4:带 Content-Length 的半截响应三次都半截 → 最终抛截断守卫错
    (download_file 的 read(n) 形态吃短读、由守卫报 RuntimeError,非
    IncompleteRead);服务器记到 3 次请求 = 重试确实发生;旧文件字节不变。"""
    monkeypatch.setattr("ipdb._source_base._sleep_backoff", lambda secs: None)
    old = b"previous-good-evidence"

    def half(conn, n):
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n"
                     + b"y" * 40)

    server = _FeedServer(half)
    try:
        src = _make_source(BruteforceSource, tmp_path, server.port)
        src._path.write_bytes(old)
        with pytest.raises(RuntimeError, match="truncated download"):
            src.download()
        assert server.requests == 3
        assert src._path.read_bytes() == old
    finally:
        server.close()


def test_reset_retry_succeeds_with_observed_backoff(tmp_path, monkeypatch,
                                                    caplog):
    """用例 5:前两次连接被重置、第三次正常 → 下载成功;退避缝被调两次、
    时长 2s/4s(真 sleep 桩掉,测试不真等);重试日志带源名与原因。"""
    sleeps = []
    monkeypatch.setattr("ipdb._source_base._sleep_backoff", sleeps.append)

    def two_resets_then_ok(conn, n):
        if n <= 2:
            _reset(conn)
        else:
            conn.sendall(_http_ok(b"1.2.3.4\n"))

    server = _FeedServer(two_resets_then_ok)
    try:
        src = _make_source(TweetFeedSource, tmp_path, server.port)
        with caplog.at_level(logging.WARNING, logger="ipdb._source_base"):
            src.download()
        assert src._path.read_bytes() == b"1.2.3.4\n"
        assert sleeps == [2, 4]
        retries = [r for r in caplog.records if "retrying" in r.message]
        assert len(retries) == 2 and "tweetfeed" in retries[0].getMessage()
        # 返工 4:同一行里还有脱敏地址与异常类名字段(格式 "retrying in "
        # "Nds: <类名>: <文本>",至少两处 ": ";类名随断连位置变,不钉具体名)
        assert "127.0.0.1" in retries[0].getMessage()
        assert retries[0].getMessage().count(": ") >= 2
    finally:
        server.close()


def test_empty_response_no_retry_old_file_kept(tmp_path):
    """用例 6:空响应 → Empty response 立刻失败(服务器只收 1 次请求 =
    不重试),旧文件字节保留,scratch 清掉。"""
    server = _FeedServer(
        lambda conn, n: conn.sendall(_http_ok(b"", content_length=False)))
    try:
        src = _make_source(BruteforceSource, tmp_path, server.port)
        old = b"keep-me"
        src._path.write_bytes(old)
        with pytest.raises(RuntimeError, match="Empty response from"):
            src.download()
        assert server.requests == 1
        assert src._path.read_bytes() == old
        assert not (tmp_path / (src.filename + ".tmp")).exists()
    finally:
        server.close()


def test_no_content_length_warns_but_completes(tmp_path, caplog):
    """用例 7:无 Content-Length(close-delimited)完整响应 → 一行告警
    (截断不可判,地址经脱敏带出),下载照常完成、落盘字节正确。"""
    body = b"1.2.3.4\n5.6.7.8\n"
    server = _FeedServer(
        lambda conn, n: conn.sendall(_http_ok(body, content_length=False)))
    try:
        src = _make_source(TweetFeedSource, tmp_path, server.port)
        with caplog.at_level(logging.WARNING,
                             logger="ipdb._sources._download"):
            src.download()
        assert src._path.read_bytes() == body
        hits = [r for r in caplog.records if "Content-Length" in r.getMessage()]
        assert len(hits) == 1
        assert "truncation cannot be detected" in hits[0].getMessage()
        assert "127.0.0.1" in hits[0].getMessage()
    finally:
        server.close()


# ── 返工(评审 2026-11-27「可直接合并」建议改 1-3 + 顺手建议)───────────

_CHUNKED_RESPONSE = (b"HTTP/1.1 200 OK\r\n"
                     b"Transfer-Encoding: chunked\r\n"
                     b"Connection: close\r\n\r\n"
                     b"5\r\nhello\r\n"
                     b"6\r\n world\r\n"
                     b"0\r\n\r\n")          # 解出 b"hello world"


def test_chunked_complete_no_content_length_warning(tmp_path, caplog):
    """返工 1:分块传输本来就没有 Content-Length,但 CPython 对分块截断
    会抛 IncompleteRead(http.client read 路径),「无法判断截断」对它是
    假话且每次刷新都来一遍——告警条件排除分块后,完整分块体正常落盘、
    零告警记录。"""
    server = _FeedServer(lambda conn, n: conn.sendall(_CHUNKED_RESPONSE))
    try:
        src = _make_source(TweetFeedSource, tmp_path, server.port)
        with caplog.at_level(logging.WARNING,
                             logger="ipdb._sources._download"):
            src.download()
        assert src._path.read_bytes() == b"hello world"
        assert not [r for r in caplog.records
                    if "Content-Length" in r.getMessage()]
    finally:
        server.close()


def test_http_404_not_retried(tmp_path, monkeypatch):
    """返工 2:404 是确定性服务端答案,不重试——一次请求、退避桩零调用、
    旧文件原样、HTTPError 原样上抛。"""
    sleeps = []
    monkeypatch.setattr("ipdb._source_base._sleep_backoff", sleeps.append)
    old = b"previous-good-evidence"

    def not_found(conn, n):
        conn.sendall(_http_status(404, "Not Found"))

    server = _FeedServer(not_found)
    try:
        src = _make_source(BruteforceSource, tmp_path, server.port)
        src._path.write_bytes(old)
        with pytest.raises(urllib.error.HTTPError) as ei:
            src.download()
        assert ei.value.code == 404
        assert server.requests == 1
        assert sleeps == []
        assert src._path.read_bytes() == old
    finally:
        server.close()


def test_http_503_retried_then_success(tmp_path, monkeypatch):
    """返工 2:5xx 照旧重试——503 后回 200 → 成功、两次请求、退避一次
    2 秒。"""
    sleeps = []
    monkeypatch.setattr("ipdb._source_base._sleep_backoff", sleeps.append)
    body = b"1.2.3.4\n"

    def service_unavailable_then_ok(conn, n):
        if n == 1:
            conn.sendall(_http_status(503, "Service Unavailable"))
        else:
            conn.sendall(_http_ok(body))

    server = _FeedServer(service_unavailable_then_ok)
    try:
        src = _make_source(TweetFeedSource, tmp_path, server.port)
        src.download()
        assert src._path.read_bytes() == body
        assert server.requests == 2
        assert sleeps == [2]
    finally:
        server.close()


def test_bad_status_line_retried(tmp_path, monkeypatch):
    """返工 3:http.client.HTTPException 家族入判据——桩回非 HTTP 垃圾
    状态行 → BadStatusLine(⊂ HTTPException;原判据只单列 IncompleteRead,
    不认它)重试满 3 次后原样上抛。"""
    monkeypatch.setattr("ipdb._source_base._sleep_backoff", lambda secs: None)

    def garbage(conn, n):
        conn.sendall(b"NOT-HTTP\r\n\r\n")

    server = _FeedServer(garbage)
    try:
        src = _make_source(BruteforceSource, tmp_path, server.port)
        with pytest.raises(http.client.BadStatusLine):
            src.download()
        assert server.requests == 3
    finally:
        server.close()


@pytest.mark.parametrize("exc,expected", [
    # 返工 2:4xx 确定性答案不重试;5xx/408/429 照旧
    (urllib.error.HTTPError("http://x/y", 404, "Not Found", None, None), False),
    (urllib.error.HTTPError("http://x/y", 403, "Forbidden", None, None), False),
    (urllib.error.HTTPError("http://x/y", 500, "Server Error", None, None), True),
    (urllib.error.HTTPError("http://x/y", 503, "Service Unavailable", None, None), True),
    (urllib.error.HTTPError("http://x/y", 408, "Request Timeout", None, None), True),
    (urllib.error.HTTPError("http://x/y", 429, "Too Many Requests", None, None), True),
    # urllib 包装 / 连接级 / 超时
    (urllib.error.URLError(ConnectionResetError("reset")), True),
    (urllib.error.URLError(TimeoutError("timed out")), True),
    (ConnectionResetError("reset"), True),
    (TimeoutError("timed out"), True),
    # 返工 3:HTTPException 基类取代单列 IncompleteRead(更稳)
    (http.client.IncompleteRead(b"xx", 3), True),
    (http.client.BadStatusLine("NOT-HTTP"), True),
    # 返工 3:ssl.SSLError ⊂ OSError 但不在 ConnectionError/TimeoutError 之下
    (ssl.SSLError("WRONG_VERSION_NUMBER"), True),
    # download_file 截断守卫(RuntimeError 按文案前缀);空体守卫不重试
    (RuntimeError("truncated download: http://x/y — got 1 of 2 bytes"), True),
    (RuntimeError("Empty response from http://x/y"), False),
    # 普通异常与磁盘满不重试(刻意不放宽成整个 OSError)
    (ValueError("nope"), False),
    (OSError(28, "No space left on device"), False),
])
def test_retry_predicate_table(exc, expected):
    """返工 3(评审顺手建议):_is_retryable 判据表驱动单测,每种异常
    类型一行,判据不再只被行为用例间接钉住。ssl.SSLError 只能在这里钉:
    端到端构造它需要真 TLS 握手中途失败——纯 HTTP stub 给不出,stdlib
    也造不出证书——这条写明不另钉。"""
    assert _is_retryable(exc) is expected
