"""Firehol blocklist source — IpListSource subclass with multi-list download.

子列表拆分(2026-08-30):level1/2 之外订阅 firehol 自有的两个语义净新增
列表,per-list 分类(verdict 与同轴直接源对齐,详见 _LIST_SPEC 注释):
- abusers_30d(7/7 上游为 spam 族追踪器)→ spam/informational(对齐 sfs,
  ffae4caf 的 off-threat-axis 裁决);
- proxies(iblocklist/socks/sslproxies 三个无直接源的代理上游)→
  proxy/suspicious + is_proxy(对齐 proxyscrape/ip2proxy)。
firehol_webserver 已退订(2026-10-19 矩阵案一裁决:8.8.8.8 权威 DNS 经
其残差标签显形 spam 的事故执法,ADR 0003;退订回归测试钉死不回流)。
重叠部分由谱系去重兜底(derived=True);同 CIDR 异分类共存(convention 3)。
"""
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from ._base import IpListSource
from ._download import download_file, CancelToken, CancelledError
from .._types import SourceHealth

_BASE_URL = "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master"

logger = logging.getLogger(__name__)

# 列表 → (classification, verdict, Evidence 附加槽)。
# 未列出的列表回退类属性 blacklist/malicious(兼容任意 selected_lists)。
_LIST_SPEC = {
    "firehol_level1":      ("blacklist", "malicious", {}),
    "firehol_level2":      ("blacklist", "malicious", {}),
    "firehol_abusers_30d": ("spam", "informational", {}),
    "firehol_proxies":     ("proxy", "suspicious", {"is_proxy": True}),
}

# 超大列表(2.8M 行)流式直读不落 acc:内存上界由非流式列表总量决定,
# proxies 增长只影响重建时长。撞 acc 就地合并(实测跨列表同 CIDR ≈8.3k)。
_STREAMED = frozenset({"firehol_proxies"})


class FireholBlocklistSource(IpListSource):
    name = "firehol"
    category = "threat"
    url = ""  # unused — custom download() handles multiple URLs
    url_exempt = True  # #253:url 有意空串(多端点走 _BASE_URL),护栏豁免
    filename = "firehol"  # directory name
    fields = ("is_malicious",)
    classification_type = "blacklist"   # 类级回退(未列入 _LIST_SPEC 的列表)
    verdict = "malicious"
    stale_days = 1
    reliability = 0.50
    derived = True                        # 聚合器:谱系去重用(spec 2026-08-29 §3.3)
    provenance_tier = "C"                 # C=聚合派生(S21):多社区黑名单再聚合
    authoritative_for = ()

    def __init__(self, data_dir: Path, selected_lists: list[str] | None = None):
        self._lists = selected_lists or list(_LIST_SPEC)
        super().__init__(data_dir=data_dir)
        self._path = data_dir / "firehol"  # directory, not file
        self._files = [self._path / f"{name}.netset" for name in self._lists]

    @property
    def download_host(self) -> str | None:
        # url class attr is "" but downloads actually come from _BASE_URL.
        return urlparse(_BASE_URL).hostname

    def download(self, token: CancelToken | None = None) -> None:
        """逐列表下载(SA-F1,cloud_ranges 模式):raw 先落 `<name>.netset.dl`
        scratch,非空才 os.replace 落地 — 单列表失败/空响应保留旧 netset
        (rebuild 对缺列表本就容忍),失败列表名记 self.last_partial_failure
        (scheduler 对 done-但-部分失败走 backoff 封顶重试);全挂才 raise。"""
        self._path.mkdir(parents=True, exist_ok=True)
        failed: list[str] = []
        for list_name in self._lists:
            if token is not None and token.is_cancelled():
                raise CancelledError(f"{self.name} download cancelled")
            url = f"{_BASE_URL}/{list_name}.netset"
            dest = self._path / f"{list_name}.netset"
            scratch = dest.with_name(dest.name + ".dl")
            logger.info(f"Downloading {list_name}...")
            try:
                download_file(url, scratch, token=token,
                              headers={"User-Agent": "ip-lookup-tool/1.0"})
                if not scratch.read_bytes().strip():
                    failed.append(list_name)
                    logger.warning(f"Empty response for {list_name}")
                    continue
                os.replace(scratch, dest)
            except Exception as e:
                failed.append(list_name)
                logger.warning(
                    f"Failed to download {list_name}: {e} — keeping existing file")
            finally:
                scratch.unlink(missing_ok=True)
        self.last_partial_failure = failed
        if len(failed) == len(self._lists):
            raise RuntimeError(
                f"all firehol lists failed to download: {self._lists}")

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一重建入口)。新 epoch + ptr swap reader。

        Per-list classification(2026-08-30):每列表按 _LIST_SPEC 各投分类;
        同 CIDR 同模板(cls/verdict/extras 相同)命中合并 tags(2026-08-15
        语义推广),异模板各成一条证据(convention 3)。流式双族
        (ipinfo_lite 惯例):非流式列表先 build acc(位掩码),流式列表
        行级直吐、撞 acc 就地置位——保证同 CIDR 跨列表证据零丢失
        (先物化后流式的顺序是正确性要求)。
        同起止不同长度 CIDR 仍依赖审计脚本零冲突
        (scripts/audit_lmdb_invariants.py)。
        """
        import ipaddress as _ipa
        from ._lmdb import rebuild_dual_family, Auto
        from .._evidence import Evidence
        if not self._path.exists():
            return 0

        def _ev(list_name: str) -> dict:
            cls, verdict, extras = _LIST_SPEC.get(
                list_name, (self.classification_type, self.verdict, {}))
            return Evidence(
                classification_type=cls,
                verdict=verdict,
                reliability=self.reliability,
                tags=[list_name],
                **extras,
            ).to_dict()

        def _factory():
            # acc 位掩码压缩(Task 2,fix/rebuild-time-for-space):值只记
            # "哪些列表命中该 CIDR"(bit i = self._lists[i];Python int 宽
            # 度随列表数动态,无 8 桶假设)。旧实现逐行物化证据 dict
            # (~230k CIDR ≈ 150–250MB 驻留),信息量却只有命中列表集合 →
            # 压成 dict[str,int],230k 量级实测 ~18MB;证据推迟到吐出时按模板重建。
            # 964MB 机子进程车道(interp ~70MB + acc ~18MB)+ Task 1
            # stall 窗口后可过 8% 水线。
            bit_of = {name: 1 << i for i, name in enumerate(self._lists)}
            acc: dict[str, int] = {}
            ordered = ([n for n in self._lists if n not in _STREAMED]
                       + [n for n in self._lists if n in _STREAMED])
            # 名字 → 模板 (cls, verdict, extras);未列入 _LIST_SPEC 的
            # 列表回退类属性(兼容任意 selected_lists,与 _ev 同口径)。
            spec = {n: _LIST_SPEC.get(
                n, (self.classification_type, self.verdict, {}))
                for n in ordered}

            def _evidence(mask: int) -> list[dict]:
                """吐出时按模板分桶重建证据:同模板命中合并 tags
                (sorted 并集),异模板各成一条(convention 3)——与旧
                _merge(sans-tags 等价→tags 并集,否则共存)逐位一致;
                reliability 为类常量全列表同值,不入桶键。桶序 = 首个
                命中列表在 ordered 的位置(= 旧共存追加序)。"""
                buckets: dict[tuple, list[str]] = {}
                for name in ordered:
                    if not mask & bit_of[name]:
                        continue
                    cls, verdict, extras = spec[name]
                    buckets.setdefault(
                        (cls, verdict, tuple(sorted(extras.items()))),
                        []).append(name)
                return [
                    Evidence(
                        classification_type=cls, verdict=verdict,
                        reliability=self.reliability,
                        tags=sorted(set(names)), **dict(extra_items),
                    ).to_dict()
                    for (cls, verdict, extra_items), names in buckets.items()
                ]

            for list_name in ordered:
                p = self._path / f"{list_name}.netset"
                if not p.exists():
                    continue
                bit, streamed = bit_of[list_name], list_name in _STREAMED
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        try:
                            net = str(_ipa.ip_network(line, strict=False))
                        except (ValueError, _ipa.AddressValueError,
                                _ipa.NetmaskValueError):
                            continue
                        if streamed and net not in acc:
                            yield net, [_ev(list_name)]   # 流式直吐,不落 acc
                        else:
                            # 同列表重复行 |= 幂等(internal dup=0 天花板不变)
                            acc[net] = acc.get(net, 0) | bit
            # ponytail: 两个已知天花板(均为保守方向,审计脚本可观测):
            # ① 流式文件内部重复行未设防(实测 5 文件 internal dup=0;非流
            #    式侧 |= 幂等,掩码不会重复置位);
            # ② 同起点不同长度 CIDR 对(实测 1,948/3M≈0.065%,LMDB 键=start
            #    只存其一):跨列表对中 acc 后 yield 恒胜 → 粒度粗化、无假
            #    阳性。要无损消除需 start 集合(~200MB)或排序合并,不值;
            #    升级路径 = _lmdb 键改 (start,prefixlen) 双分量。
            for net, mask in acc.items():
                yield net, _evidence(mask)

        n4, n6 = rebuild_dual_family(
            _factory, self._lmdb_base, self._lmdb6_base,
            reader_setter4=lambda e: setattr(self, "_reader", e),
            reader_setter6=lambda e: setattr(self, "_reader6", e),
            flag_setter4=lambda v: setattr(self, "_disjoint", v),
            flag_setter6=lambda v: setattr(self, "_disjoint6", v),
            covered4=Auto, covered6=Auto,
            covered_setter4=lambda v: setattr(self, "_covered_ips", v),
            covered_setter6=lambda v: setattr(self, "_covered_v6_nets", v),
            progress=progress,
            total_est=self._count + self._count6,
            raw=self._path)   # 族级增量:_path=列表目录,与 _needs_rebuild_of 同基准
        self._count = n4
        self._count6 = n6
        self._loaded_at = time.time()
        return n4

    def health(self) -> SourceHealth:
        import time
        mtimes = []
        if self._path.exists():
            for list_name in self._lists:
                p = self._path / f"{list_name}.netset"
                if p.exists():
                    mtimes.append(p.stat().st_mtime)
        file_mtime = max(mtimes) if mtimes else None
        last_updated = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_mtime))
                        if file_mtime else None)
        is_stale = file_mtime is None or (
            time.time() - file_mtime > self.stale_days * 86400)
        return SourceHealth(
            name=self.name,
            loaded=self._reader is not None,
            record_count=self._count,
            last_updated=last_updated,
            is_stale=is_stale,
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets,
        )
