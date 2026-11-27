# backend/ipdb/_source_base.py
"""A-family Source base for complex/bespoke sources(挂源底座 SourceBase,
_sources/_base.py,#248;与 B 家族 IpListSource 共享生命周期底座)。

Hooks (override what you need):
  download()           — default guarded streaming GET to self.url →
                         self._path (#491: honours token, retries network-
                         class failures, truncation guard). Override for
                         state machines (cursor/budget/bg thread), gzip,
                         multi-file, auth headers.
  harvest()            — parse/transform → yields (cidr_str, Evidence) pairs.
                         Returning pairs (not bare Evidence) supports range→CIDR
                         expansion (one input row → many CIDRs).
  normalize(raw)       — optional per-source classification/field mapping.

Shared(底座 SourceBase 提供):LMDB write from harvest (epoch/ptr swap),
mmap query, health (file-mtime staleness), HTTP get with retries + auth
header + atomic tmp→rename write,__init__ 状态槽与 v6 双族 sidecar。
"""
import http.client
import logging
import ssl
import time
import urllib.error
from pathlib import Path
from typing import Iterator

from ._evidence import Evidence
# #291 三车道收尾共享件:载入期 infra 过滤+排除记账(InfraNoiseGate;
# 覆盖数 v4/v6 分流 covered_counts 为 B/C 预扫描口径,A 车道用 covered=Auto
# 写库循环内统计,不经该件)。namespace pkg:无 __init__ 环,模块级安全。
from ._sources._rebuild_tail import InfraNoiseGate
# 底座(#248):生命周期(__init__/load/query/_query6/health/_http_get/
# download_host)与两家族同款类属性收敛在 _sources/_base.SourceBase;
# 本模块只留 A 家族钩子(download/harvest/normalize)与 harvest 驱动的
# rebuild。import 方向与既有 _lmdb/_download 一致(ipdb 层 → _sources 内部)。
from ._sources._base import SourceBase
from ._sources._download import (
    CancelledError, download_file, redact_url)

logger = logging.getLogger(__name__)

# 请求级重试帽(#491):网络类失败最多试 3 次,退避 2s/4s——形状与
# SourceBase._http_get(_sources/_base.py)相同;两份重试循环刻意不合并
# (工单 #491「不在这次做」写明合并另开票)。重试层只在这层,只这 5 个
# 走默认下载的 A 家族源受益(bruteforce/metowolf_iplist/mirage_feed/
# reportedip/tweetfeed),download_file 与 B 家族 37 源零变化。
_DOWNLOAD_RETRIES = 3


def _sleep_backoff(seconds: float) -> None:
    """重试退避的可观察缝(#491 测试用例 5 桩这里):真身 time.sleep。
    (#491 返工:原名 ``_backoff`` 与 ``RefreshScheduler._backoff``——按
    源记退避状态的表(_scheduler.py)——同名异物,改叫 _sleep_backoff
    避嫌,评审 2026-11-27 建议 7。)"""
    time.sleep(seconds)


def _is_retryable(e: Exception) -> bool:
    """网络类失败判据(#491 §2;返工按评审建议改 2/3 收口):连接被重置
    (ConnectionResetError ⊂ ConnectionError)、超时(TimeoutError;
    socket.timeout 在 3.10+ 就是它,连接期超时经 urllib 包成 URLError)、
    HTTP 层残缺(http.client.HTTPException:IncompleteRead、BadStatusLine、
    LineTooLong 的共同基类,比单列 IncompleteRead 稳)、TLS 半途断开
    (ssl.SSLError ⊂ OSError 但不在 ConnectionError/TimeoutError 之下;
    urllib 只把发请求阶段的 OSError 包成 URLError,读响应阶段的原样
    抛出)、urllib 包装(URLError ⊂ OSError)、download_file 截断守卫
    报错(普通 RuntimeError,按文案前缀判别——空体守卫同为 RuntimeError
    但文案不同,照旧立刻失败不重试)。

    4xx 不重试(确定性服务端答案,评审建议改 2):HTTPError 只有 ≥500
    或 408/429 才值得再试,其余立刻失败。磁盘满这类普通 OSError 不重试
    (刻意不放宽成整个 OSError)。取消(CancelledError)在调用点先行
    原样上抛,不进这里。"""
    if isinstance(e, urllib.error.HTTPError):
        return e.code >= 500 or e.code in (408, 429)
    if isinstance(e, (urllib.error.URLError, http.client.HTTPException,
                      ConnectionError, TimeoutError, ssl.SSLError)):
        return True
    return (isinstance(e, RuntimeError)
            and str(e).startswith("truncated download"))


class Source(SourceBase):
    # When True, rebuild() streams one (cidr, [evidence]) per harvest yield
    # straight into rebuild_lmdb instead of accumulating a full acc dict. Safe
    # only for sources whose harvest yields each CIDR at most once (geo/asset
    # lists like ip2proxy/iptoasn); insert_network overwrites idempotently, so
    # a stray duplicate is harmless. Multi-evidence threat sources must leave
    # this False — they rely on acc to group several evidence per CIDR.
    # 仅 A 家族 rebuild 消费(#248 裁决 5),留在 Source 不上底座。
    single_evidence: bool = False

    def download(self, token=None) -> None:
        """Default: guarded streaming GET → self._path. Override for bespoke.

        #491(2026-11-27):streams via ``_sources._download.download_file``
        so ``token`` is now honored — pre-cancel raises before any request,
        mid-stream cancel between chunks, a body shorter than its
        Content-Length is rejected as truncated, redirects trip
        ``warn_if_redirected`` inside, and per-chunk progress lands on
        ``token.on_progress``. The landing contract is unchanged: raw
        bytes, one atomic replace (ADR 0014 splits the *disk* contract,
        not transport guarantees). The empty-body guard keeps its exact
        message but moved pre-replace into ``download_file``'s ``validate``
        hook, so a blank response leaves the previous file byte-identical.

        Network-class failures (see ``_is_retryable``) retry up to
        ``_DOWNLOAD_RETRIES`` attempts with 2s/4s backoff — same shape as
        ``SourceBase._http_get`` (the two retry loops stay separate;
        merging is a separate ticket). Cancellation, empty responses and
        definitive 4xx answers are not retried; after the last attempt the
        original exception propagates unchanged.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)

        def _reject_blank(scratch: Path) -> None:
            # 空体守卫(#491):download_file 直接原子落 self._path,空白
            # 检查挪进落盘前 validate 口子——拒绝时 scratch 被 download_file
            # 清掉、旧文件字节不动,无需下载前快照/失败还原。文案与旧实现
            # 一字不差。
            if not scratch.read_bytes().strip():
                raise RuntimeError(f"Empty response from {redact_url(self.url)}")

        for attempt in range(1, _DOWNLOAD_RETRIES + 1):
            try:
                download_file(
                    self.url, self._path, token=token, timeout=120,
                    headers={"User-Agent": "ip-lookup-tool/1.0"},
                    validate=_reject_blank)
                return
            except CancelledError:
                raise          # 取消不重试,原样上抛(#491 §2)
            except Exception as e:
                if attempt == _DOWNLOAD_RETRIES or not _is_retryable(e):
                    raise
                delay = 2 ** attempt
                logger.warning(
                    "download attempt %d/%d failed for %s (%s), retrying in "
                    "%ds: %s: %s",
                    attempt, _DOWNLOAD_RETRIES, self.name, redact_url(self.url),
                    delay, type(e).__name__, e)
                _sleep_backoff(delay)

    def harvest(self) -> Iterator[tuple[str, Evidence]]:
        """Parse → yield (cidr_str, Evidence). Override in every concrete source."""
        raise NotImplementedError

    def normalize(self, raw: Evidence) -> Evidence:
        """Optional per-source classification/field mapping. Default: passthrough."""
        return raw

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一入口,经 manager 队列调用)。新 epoch + ptr swap。

        旧 env 不显式 close(各平行副本同此约定):依赖 CPython 引用计数
        在在途读 txn 结束后自然释放 — 查询线程在 reader swap 瞬间正握着旧
        env 时,显式 close 是文档化的段错误路径;而 rebuild 失败时 finally
        里 close 掉的其实是现役 reader(自残)。旧 epoch 目录的磁盘清理由
        rebuild_lmdb 的 prune rmtree 负责(Linux 上 fd 未关亦可删)。"""
        from ._sources._lmdb import Auto, rebuild_dual_family
        from ._logodds import parse_first_seen
        if not self._path.exists():
            return 0
        # 绊线(2026-09-05 IntelMQ 审计):脏 first_seen 在打分期静默按无
        # 衰减计(decay_factor(None)=1.0=最大权重)。中央检查按 distinct 值
        # 去重,单/双遍 harvest(factory 被 rebuild_dual_family 调两次)不双计。
        bad_fs: set[str] = set()
        # 载入期 infra 噪声排除(issue #183;harvest 车道,与
        # _sources/_base.py 的 IpListSource/CsvSource 车道平行):排除只挡
        # 投影,数据文件零改写;宁少算 = 仅 curated 单址精确指控,更大
        # CIDR 不排。single_evidence 双遍 harvest 的重复 append 由
        # log_exclusions 的 set 去重吸收。
        # 过滤+记账收共享 #291(InfraNoiseGate,三车道同源)。
        gate = InfraNoiseGate(self.name, self.infra_noise_filter)

        def _harvest_checked():
            import ipaddress as _ipa
            for cidr, ev in self.harvest():
                if gate.enabled:
                    try:
                        net = _ipa.ip_network(str(cidr), strict=False)
                    except (ValueError, _ipa.AddressValueError,
                            _ipa.NetmaskValueError):
                        net = None
                    if net is not None and gate.blocks(net):
                        continue
                fs = getattr(ev, "first_seen", None)
                if fs and parse_first_seen(fs) is None:
                    bad_fs.add(str(fs))
                yield cidr, ev

        if self.single_evidence:
            # factory 零参 callable,每次调用返回新迭代器(rebuild_dual_family
            # 调用两次做族分区;严禁传裸生成器对象)。harvest 重复解析是既有
            # 模式(CPU 换内存,OOM 纪律见旧注释)。
            def factory():
                for cidr, ev in _harvest_checked():
                    yield cidr, [self.normalize(ev).to_dict()]
        else:
            acc: dict[str, list[dict]] = {}
            for cidr, ev in _harvest_checked():
                ev = self.normalize(ev)
                d = ev.to_dict()
                bucket = acc.setdefault(cidr, [])
                if d not in bucket:
                    bucket.append(d)
            factory = lambda: iter(acc.items())   # 已物化;统一 callable 形态
        # 覆盖数不再预扫描(省两次全量 harvest):covered=Auto 在写库循环内
        # 统计实际入库记录,ptr 提交后经 setter 落内存。
        # 流式 factory 无 __len__:total 用上一轮计数估计(刷新场景极准);
        # 首次重建无历史 → 0,UI --% 不变。
        n4, n6 = rebuild_dual_family(
            factory, self._lmdb_base, self._lmdb6_base,
            reader_setter4=lambda e: setattr(self, "_reader", e),
            reader_setter6=lambda e: setattr(self, "_reader6", e),
            flag_setter4=lambda v: setattr(self, "_disjoint", v),
            flag_setter6=lambda v: setattr(self, "_disjoint6", v),
            covered4=Auto, covered6=Auto,
            covered_setter4=lambda v: setattr(self, "_covered_ips", v),
            covered_setter6=lambda v: setattr(self, "_covered_v6_nets", v),
            progress=progress,
            total_est=self._count + self._count6,
            raw=self._path)   # 族级增量:已收敛族跳过,重试只做未收敛族
        self._count = n4
        self._count6 = n6
        self._loaded_at = time.time()
        gate.flush()
        if bad_fs:
            logger.warning(
                "%s: %d distinct unparseable first_seen value(s), e.g. %s — "
                "time-decay silently disabled for those rows",
                self.name, len(bad_fs), sorted(bad_fs)[:3])
        return n4
