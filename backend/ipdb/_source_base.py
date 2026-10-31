# backend/ipdb/_source_base.py
"""A-family Source base for complex/bespoke sources(挂源底座 SourceBase,
_sources/_base.py,#248;与 B 家族 IpListSource 共享生命周期底座)。

Hooks (override what you need):
  download()           — default simple GET to self.url → self._path.
                         Override for state machines (cursor/budget/bg thread),
                         gzip, multi-file, auth headers.
  harvest()            — parse/transform → yields (cidr_str, Evidence) pairs.
                         Returning pairs (not bare Evidence) supports range→CIDR
                         expansion (one input row → many CIDRs).
  normalize(raw)       — optional per-source classification/field mapping.

Shared(底座 SourceBase 提供):LMDB write from harvest (epoch/ptr swap),
mmap query, health (file-mtime staleness), HTTP get with retries + auth
header + atomic tmp→rename write,__init__ 状态槽与 v6 双族 sidecar。
"""
import logging
import time
import urllib.request
from typing import Iterator

from ._evidence import Evidence
from ._sources import _infra_filter   # namespace pkg:无 __init__ 环,模块级安全
# 底座(#248):生命周期(__init__/load/query/_query6/health/_http_get/
# download_host)与两家族同款类属性收敛在 _sources/_base.SourceBase;
# 本模块只留 A 家族钩子(download/harvest/normalize)与 harvest 驱动的
# rebuild。import 方向与既有 _lmdb/_download 一致(ipdb 层 → _sources 内部)。
from ._sources._base import SourceBase
from ._sources._download import (
    warn_if_redirected, atomic_write_bytes, redact_url)

logger = logging.getLogger(__name__)


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
        """Default: simple GET → self._path. Override for bespoke fetch.

        ``token`` is accepted (and ignored) so UpdateManager can call
        ``download(token=...)`` uniformly; subclasses with non-cancellable
        fetches need not override for signature compatibility alone."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            self.url, headers={"User-Agent": "ip-lookup-tool/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            warn_if_redirected(self.url, resp)
            data = resp.read()
        if not data.strip():
            raise RuntimeError(f"Empty response from {redact_url(self.url)}")
        atomic_write_bytes(self._path, data)

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
        exclude_infra = (self.infra_noise_filter
                         and _infra_filter.filter_enabled())
        excluded: list[str] = []

        def _harvest_checked():
            import ipaddress as _ipa
            for cidr, ev in self.harvest():
                if exclude_infra:
                    try:
                        net = _ipa.ip_network(str(cidr), strict=False)
                    except (ValueError, _ipa.AddressValueError,
                            _ipa.NetmaskValueError):
                        net = None
                    if net is not None and _infra_filter.is_infra_noise(net):
                        excluded.append(str(net))
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
        if excluded:
            _infra_filter.log_exclusions(self.name, excluded)
        if bad_fs:
            logger.warning(
                "%s: %d distinct unparseable first_seen value(s), e.g. %s — "
                "time-decay silently disabled for those rows",
                self.name, len(bad_fs), sorted(bad_fs)[:3])
        return n4
