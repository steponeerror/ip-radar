"""Base classes for IP data sources — eliminate ~70% boilerplate across sources.

SourceBase(#248 源底座)= A/B 两家族共享的生命周期底座;取数钩子分家:
IpListSource = B 家族(parse_raw/get_insert_data),_source_base.Source =
A 家族(download/harvest/normalize),各自覆写自家基类,底座不含取数路径。
"""
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import lmdb

from .._types import SourceHealth
from . import _infra_filter
from ._download import warn_if_redirected
# 热路径共享:函数体内缓存 import 复测 273ns/调用(2026-10-11 配对
# A/B 修正侦察预估 1.075µs;43µs/IP 为已修正的侦察预估,非实测);提升后
# 配对 A/B 实测 -21µs/IP(5/5 全胜)。_lmdb 仅依赖
# stdlib/lmdb/orjson,无对本模块的反向 import,模块级提升安全(PR-2 Task 3)
from ._lmdb import (
    ip_to_int, ip_to_int6, lookup, read_ptr, open_env_read,
    read_disjoint_flag, load_v6_side_state)

logger = logging.getLogger(__name__)


class SourceBase:
    """源底座(issue #248,形态 A:抽共享底座、钩子分家):Source(A 家族,
    _source_base.py)与 IpListSource(B 家族,本文件)逐字重复的
    __init__/load/_load_v6_side/query/_query6/health 及 _http_get/
    download_host 收敛于此;两家族的取数钩子协议与 download 落盘契约
    (A=原始字节直写 _path;B=暂存→parse_raw→规范化明单,失败保留旧文件)
    原样留在各自基类,底座对表不裁决(统一是另一张语义票)。

    为什么分底座不合成单类:三套 rebuild 取数路径(harvest 驱动 / 明单
    行驱动 / CSV 行驱动)钩子互不兼容,合成单类会把 B 家族 32 个
    "只定义 name/url/filename/fields" 子类与 A 家族 28 个
    "覆写 download/harvest" 子类的约定强行耦合。
    """

    name: str
    fields: tuple[str, ...]
    # url/filename 空串默认(原 Source 侧形态,合一沿用):漏定义的子类
    # 构造不炸、落空路径/空 URL;原 IpListSource 侧为裸注解(漏定义
    # __init__ 即 AttributeError),61 个现存子类全部显式定义,取空串
    # 默认零差异。上收后 API 层可见翻转共两处(PR #250 第 1 轮审查
    # C 席 P1,2026-10-31 逐源实测核对):
    # ① ipinfo_lite url null→""(前端 s.url 真值判空,显示不变);
    # ② A 家族 11 个未覆写 download_host 且 url 非空的源(tweetfeed/
    #    urlhaus/bruteforce/cloudzy/dns_public/reportedip/caida_asorg/
    #    geolite_city/root_servers/dbip_city/anycast_census),任务侧
    #    host 从 None 翻为真实主机名(_tasks.py:174 getattr 落到本
    #    property);其中 cloudzy/dns_public/reportedip/tweetfeed 四源
    #    同为 raw.githubusercontent.com,加入既有 15 源共享 host 锁组
    #    (_tasks.py:461-467),download/rebuild 从不串行变串行——对齐
    #    B 家族同 host 源既有调度行为,裁定良性接受。
    url: str = ""
    filename: str = ""
    stale_days: int = 7
    reliability: float = 0.5
    # ── 元数据契约(spec 2026-08-28 §5.1):源文件是唯一真相 ──
    category: str = "other"            # geo_asn | threat | asset | other
    authoritative_for: tuple = ()      # 本源权威的字段名(反转成 AUTHORITATIVE_SOURCES)
    # eval 元数据(S21/S33,2026-10-14 eval-loop phase1):纯元数据,不参与
    # 抓取/解析/合并;仅偏离默认的源在类内覆写。
    provenance_tier: str = "B"          # A 官方/自采 | B 社区 | C 聚合派生
    honeypot_methodology: bool = False  # 蜜罐法采集(k_nonhoneypot 剔除依据)
    # 设计上无 per-IP LMDB 面的源置 False(caida_asorg:文件即持久层);
    # 2026-10-14 demo 幻影环:ptr 永不存在被当 needs_rebuild → 每 30min 全量重抓。
    # 消费方 _registry.needs_rebuild 为 getattr 鸭子型(默认 True),上收后
    # 由裸属性提供同值。
    lmdb_backed: bool = True
    # 载入期基础设施噪声过滤(issue #183):True = rebuild 载入面排除
    # infra_services curated 单址集(默认 False,事故源显式 opt-in);
    # 三条取数车道(harvest/明单行/CSV 行)各自接线本 flag。
    infra_noise_filter: bool = False

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._path = data_dir / self.filename
        self._lmdb_base = data_dir / f"{self.filename}.lmdb"
        # scheduler 快照契约名(名保留):ptr 文件;C2 后 needs_convert 的
        # 比较对象是 _lmdb_base 族(ptr mtime + .rev harvest 版本戳,ADR 0009)
        from ._lmdb import ptr_path as _ptr_path
        self._mmdb_path = _ptr_path(self._lmdb_base)
        self._reader = None      # LMDB env (readonly, lock=False)
        self._disjoint = False   # epoch-bound sidecar flag(load/retry 时重读)
        self._count: int = 0
        self._covered_ips: int = 0
        self._loaded_at: float = 0.0
        # v6 并行族(spec §3.2):base/ptr/reader/disjoint 全套独立 sidecar
        self._lmdb6_base = data_dir / f"{self.filename}.v6.lmdb"
        self._mmdb6_path = _ptr_path(self._lmdb6_base)
        self._reader6 = None
        self._disjoint6 = False
        self._count6: int = 0
        self._covered_v6_nets: int = 0
        # SA-F1 部分失败信号(cloud_ranges 模式,A1/Task 3):download() 把
        # 失败子项名记入此列表(空 = 全绿);RefreshScheduler._partial_failure_of
        # 消费(done-但-部分失败 → backoff 封顶重试,spec §2.3)。
        # cloud_ranges 在自己 __init__ 里重复声明同名属性,赋值覆写零冲突。
        self.last_partial_failure: list[str] = []

    @property
    def download_host(self) -> str | None:
        """Hostname of the primary remote URL (None when url is unset/local)."""
        return urlparse(self.url).hostname or None if getattr(self, "url", "") else None

    # ── shared lifecycle(两家族逐字同款,#248 收编)──

    def load(self) -> int:
        """纯 mmap:加载现有 LMDB env(若有),永不重建。读 sidecar。"""
        from ._lmdb import (
            read_ptr, open_env_read, cleanup_stale, count_path, cov_path,
            read_disjoint_flag)
        cleanup_stale(self._lmdb_base)
        epoch = read_ptr(self._lmdb_base)
        if epoch is None:
            self._reader = None
            self._disjoint = False
            self._load_v6_side()                  # v6 状态照常解析(v4 缺 ≠ v6 缺)
            return 0
        self._disjoint = read_disjoint_flag(self._lmdb_base, epoch)
        self._reader = open_env_read(
            self._lmdb_base.parent / f"{self._lmdb_base.name}.{epoch}")
        cp, vp = count_path(self._lmdb_base), cov_path(self._lmdb_base)
        self._count = int(cp.read_text().strip()) if cp.exists() else 0
        # cov 只读,缺失则 0,不触发 harvest(rebuild 负责)
        self._covered_ips = int(vp.read_text().strip()) if vp.exists() else 0
        self._load_v6_side()
        self._loaded_at = time.time()
        return self._count

    def _load_v6_side(self) -> None:
        """v6 族 sidecar 解析(additive):早退/正常两条 v4 路径共用;旧数据
        目录(无 v6 sidecar)静默零态。收敛至 _lmdb.load_v6_side_state
        单源点(#243;Source 侧原逐字拷贝随 #248 底座收编一并消除)。"""
        (self._reader6, self._disjoint6, self._count6,
         self._covered_v6_nets) = load_v6_side_state(self._lmdb6_base)

    def query(self, ip: str) -> Any:
        if ":" in ip:                      # v6 查询走并行族 reader(spec §3.2)
            return self._query6(ip)
        if self._reader is None:
            return {}
        ip_int = ip_to_int(ip)
        try:
            result = lookup(self._reader, ip_int, disjoint=self._disjoint)
        except (lmdb.Error, OSError):
            # 撞上刚 close 的旧 env:读 ptr 重开重试一次(与 MMDB 时代同模式)
            epoch = read_ptr(self._lmdb_base)
            self._reader = (open_env_read(
                self._lmdb_base.parent / f"{self._lmdb_base.name}.{epoch}")
                if epoch is not None else None)
            if self._reader is None:
                return {}
            self._disjoint = read_disjoint_flag(self._lmdb_base, epoch)
            result = lookup(self._reader, ip_int, disjoint=self._disjoint)
        return result if result is not None else {}

    def _query6(self, ip: str) -> Any:
        """v6 版 query():与 v4 同构(ptr 重开重试),独立族状态。
        无 v6 env(源无 v6 数据/旧目录)安静返回 {}——与该源不存在同体验。"""
        if self._reader6 is None:
            return {}
        ip_int = ip_to_int6(ip)
        try:
            result = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
                            ip_version=6)
        except (lmdb.Error, OSError):
            # 撞上刚 close 的旧 env:读 ptr 重开重试一次(与 v4 同模式)
            epoch = read_ptr(self._lmdb6_base)
            self._reader6 = (open_env_read(
                self._lmdb6_base.parent / f"{self._lmdb6_base.name}.{epoch}")
                if epoch is not None else None)
            if self._reader6 is None:
                return {}
            self._disjoint6 = read_disjoint_flag(self._lmdb6_base, epoch)
            result = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
                            ip_version=6)
        return result if result is not None else {}

    def health(self) -> SourceHealth:
        # convention 4:staleness 跟 DATA FILE 的 mtime,不跟内存 _loaded_at
        # (load_db 前为 0,跟内存值会逼每次重启都重下载)。
        file_mtime = self._path.stat().st_mtime if self._path.exists() else None
        last_updated = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_mtime))
                        if file_mtime else None)
        is_stale = file_mtime is None or (
            time.time() - file_mtime > self.stale_days * 86400)
        return SourceHealth(
            name=self.name, loaded=self._reader is not None,
            record_count=self._count, last_updated=last_updated, is_stale=is_stale,
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets)

    # ── HTTP helper for subclasses(原 Source._http_get,staticmethod 保留,
    # patch 锚 Source._http_get 经继承仍命中)──
    @staticmethod
    def _http_get(url: str, *, headers: dict | None = None,
                  timeout: int = 120, retries: int = 3) -> bytes:
        h = {"User-Agent": "ip-lookup-tool/1.0"}
        if headers:
            h.update(headers)
        last = None
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    warn_if_redirected(url, resp)
                    return resp.read()
            except Exception as e:
                last = e
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError(f"unreachable: {last}")


class IpListSource(SourceBase):
    """Base for IP/CIDR list sources (tor_exits, x4bnet_vpn, firehol, spamhaus, blocklist_de).

    Subclasses must define: name, url, filename, fields.
    Optionally override: parse_raw(), get_insert_data(), stale_days, reliability, authoritative_for.

    生命周期(__init__/load/query/health/_http_get 等)继承自 SourceBase
    (源底座,#248);本类只保留 B 家族取数钩子与 download 落盘契约。
    """

    # ── Overridable hooks ──

    def parse_raw(self, raw: bytes) -> list[str]:
        """Parse downloaded bytes → list of IP/CIDR strings.

        Default: strip lines, skip comments and empty lines.
        Override for custom formats (e.g. tor_exits regex extraction).
        """
        return [
            line.strip()
            for line in raw.decode(errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def get_insert_data(self) -> dict:
        """Evidence-shaped value stored per CIDR. Constructs via Evidence so the
        dict is the canonical contract form (routes losslessly at query time)."""
        from .._evidence import Evidence
        if getattr(self, "classification_type", None):
            return Evidence(
                classification_type=self.classification_type,
                verdict=getattr(self, "verdict", "malicious"),
                reliability=getattr(self, "reliability", 0.5),
            ).to_dict()
        return {self.fields[0]: True}   # legacy non-threat list shape

    # ── Standard lifecycle ──

    def download(self, token=None) -> None:
        """Fetch the raw list to a scratch path, parse, then install entries.

        Token-aware: pass a CancelToken to allow cooperative cancellation
        between chunk reads. Subclasses may override for bespoke fetch logic.

        Failure contract (A1/Task 3 except-unlink restructure): the raw lands
        on ``<path>.dl`` scratch and ``self._path`` is only touched after
        parse succeeds — any failure (network, empty body, zero entries)
        leaves the previous entries file byte-identical; only the scratch is
        cleaned, never the old evidence (旧实现 except 分支 unlink 会把刚
        顶掉旧文件的好证据一并删光). Empty/no-entries RuntimeError
        signals are preserved.
        """
        from ._download import download_file, atomic_write_bytes, redact_url
        self._data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading {self.name}...")
        scratch = self._path.with_name(self._path.name + ".dl")
        try:
            download_file(self.url, scratch, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            raw = scratch.read_bytes()
            if not raw.strip():
                raise RuntimeError(f"Empty response from {redact_url(self.url)}")
            entries = self.parse_raw(raw)
            if not entries:
                raise RuntimeError(f"No entries parsed from {self.name} response")
        finally:
            scratch.unlink(missing_ok=True)
        atomic_write_bytes(
            self._path, ("\n".join(entries) + "\n").encode("utf-8"))
        logger.info(f"Downloaded {self.name} ({len(entries)} entries)")

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一入口,经 manager 队列调用)。新 epoch + ptr swap。"""
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family, commit_dual_family
        if not self._path.exists():
            return 0
        insert_data = self.get_insert_data()
        exclude_infra = (self.infra_noise_filter
                         and _infra_filter.filter_enabled())
        excluded: list[str] = []
        records = []
        covered = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for sep in (";", "#"):
                    if sep in line:
                        line = line.split(sep, 1)[0].strip()
                if not line:
                    continue
                try:
                    net = _ipa.ip_network(line, strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                # 载入期 infra 噪声排除(数据文件零改写,仅挡投影;issue #183)
                if exclude_infra and _infra_filter.is_infra_noise(net):
                    excluded.append(str(net))
                    continue
                # 每条记录独立浅拷贝:共享同一 dict 会让任一记录的 extra
                # 变更泄漏给同源全部记录(历史动因:build 期写入钩子按记录
                # 挂 extra 键,该机制 2026-10-07 裁决 #5 删除;拷贝保留为
                # 防御)。注意是浅拷贝:get_insert_data 覆写方不得返回嵌套
                # extra 已填充且共享的 dict——浅拷贝只隔离外层 dict,嵌套
                # extra 仍被共享。
                records.append((str(net), [dict(insert_data)]))
                covered.append(str(net))
        cov4 = covered_ip_count(c for c in covered if ":" not in c)
        cov6 = covered_ip_count(
            (c for c in covered if ":" in c), ip_version=6)
        if excluded:
            _infra_filter.log_exclusions(self.name, excluded)
        return commit_dual_family(
            self, records, cov4=cov4, cov6=cov6, progress=progress)


class CsvSource(IpListSource):
    """Base for CSV-format sources (ipsum, ip2proxy, threatfox).

    Subclasses must implement: parse_row(row: list[str]) -> dict | None.
    Optionally override: skip_lines, delimiter.
    """

    skip_lines: int = 0
    delimiter: str = ","

    def parse_raw(self, raw: bytes) -> list[str]:
        """CSV sources store raw bytes (not parsed here)."""
        return [raw.decode(errors="ignore")]

    def parse_row(self, row: list[str]) -> dict | None:
        """Parse one CSV row → {field: value} dict. Return None to skip."""
        raise NotImplementedError("CsvSource subclasses must implement parse_row()")

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一入口,经 manager 队列调用)。新 epoch + ptr swap。"""
        import csv as _csv
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family, commit_dual_family
        if not self._path.exists():
            return 0
        exclude_infra = (self.infra_noise_filter
                         and _infra_filter.filter_enabled())
        excluded: list[str] = []
        # cidr_str -> list[evidence dict], deduped by full-evidence equality
        acc: dict[str, list[dict]] = {}
        with open(self._path, "r", encoding="utf-8") as f:
            for _ in range(self.skip_lines):
                next(f, None)
            reader = _csv.reader(f, delimiter=self.delimiter)
            for row in reader:
                if not row:
                    continue
                parsed = self.parse_row(row)
                if parsed is None:
                    continue
                ip_str = parsed.pop("_ip", row[0].strip())
                cidr_str = parsed.pop("_cidr", None)
                try:
                    if cidr_str:
                        net = _ipa.ip_network(cidr_str, strict=False)
                    elif "/" in ip_str:
                        net = _ipa.ip_network(ip_str, strict=False)
                    else:
                        _ipa.ip_address(ip_str)
                        net = _ipa.ip_network(
                            f"{ip_str}/{'128' if ':' in ip_str else '32'}",
                            strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                # 载入期 infra 噪声排除(数据文件零改写,仅挡投影;issue #183)
                if exclude_infra and _infra_filter.is_infra_noise(net):
                    excluded.append(str(net))
                    continue
                key = str(net)
                bucket = acc.setdefault(key, [])
                # Dedup on the FULL evidence (not just 4-tuple): two rows
                # with same classification/verdict/malware but different
                # native_categories/confidence/first_seen/comment are distinct
                # evidence and must both survive (field-loss fix #6).
                if any(parsed == o for o in bucket):
                    continue
                bucket.append(parsed)
        v4_keys = (c for c in acc if ":" not in c)
        v6_keys = (c for c in acc if ":" in c)
        cov4 = covered_ip_count(v4_keys)
        cov6 = covered_ip_count(v6_keys, ip_version=6)
        if excluded:
            _infra_filter.log_exclusions(self.name, excluded)
        # DQ-2:.count 语义 = LMDB 主库键数(rebuild_lmdb commit 时从 env
        # 回写);旧「count=证据数」覆写已删——同 CIDR 多证据并单键,计数
        # 不再随证据数虚增,record_count 恒等于 env 键数。
        return commit_dual_family(
            self, acc.items(), cov4=cov4, cov6=cov6, progress=progress)
