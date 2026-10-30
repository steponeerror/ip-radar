"""Blocklist.de 多子列表源 — firehol 式目录 + 攻击类型归属。

订阅 10 个攻击类型子列表 + all.txt 兜底（第 11 个列表，blacklist 兜底分类、
优先级最低）。实测 all.txt ≠ 子列表并集（约 ±0.1% 漂移：26 IP 只在 all.txt、
140 IP 只在子列表），双订阅保证零丢失。同 IP 命中多列表时按
brute-force > infected-system > spam > scanner > blacklist 裁决 classification_type，
全部认领子列表名保留在 native_categories。
"""
import logging
import os
import shutil
from pathlib import Path

from ._base import IpListSource
from ._download import download_file, CancelToken, CancelledError
from .._types import SourceHealth
from .._classification import BLOCKLIST_DE_MAP

_BASE_URL = "https://lists.blocklist.de/lists"

logger = logging.getLogger(__name__)

# 迭代序即 native_categories 的记录序；all.txt 放最后（优先级最低的兜底）
_LISTS = ["mail", "ssh", "bruteforcelogin", "ftp", "imap", "sip",
          "bots", "ircbot", "apache", "strongips", "all"]

_PRIORITY = {"brute-force": 0, "infected-system": 1, "spam": 2, "scanner": 3, "blacklist": 4}


class BlocklistDeSource(IpListSource):
    name = "blocklist_de"
    category = "threat"
    url = ""  # unused — custom download() handles multiple URLs
    filename = "blocklist_de"  # directory name
    fields = ("is_malicious",)
    classification_type = "blacklist"   # 兜底（无映射子列表 / all.txt）
    verdict = "malicious"
    stale_days = 1
    reliability = 0.65
    authoritative_for = ()

    def __init__(self, data_dir: Path, selected_lists: list[str] | None = None):
        self._lists = selected_lists or list(_LISTS)
        super().__init__(data_dir=data_dir)
        self._path = data_dir / "blocklist_de"  # directory, not file
        self._files = [self._path / f"{name}.txt" for name in self._lists]

    @property
    def download_host(self) -> str | None:
        return "lists.blocklist.de"

    def _cleanup_legacy(self) -> None:
        """删除旧单文件时代的 blocklist_de.txt 及其 LMDB sidecar。

        sidecar 形态两种：LMDB epoch 目录（blocklist_de.txt.lmdb.N/）用
        rmtree；ptr/count/cov 等文件形态 sidecar 用 unlink。"""
        legacy = self._path.parent / "blocklist_de.txt"
        legacy.unlink(missing_ok=True)
        for side in self._path.parent.glob("blocklist_de.txt.lmdb.*"):
            if side.is_dir():
                shutil.rmtree(side, ignore_errors=True)
            else:
                side.unlink(missing_ok=True)

    def download(self, token: CancelToken | None = None) -> None:
        """两阶段批量下载，词汇正源 GLOSSARY「合法空」/「活性锚」(判例
        ircbot 2026-10-15):

        阶段一逐列表抓到 `<name>.txt.dl` scratch;阶段二锚门裁决后才统一
        os.replace 落地(空文件照落)。bare-IP 列表无头部格式，HTTP 200 +
        空 body = 发布方声明「当前无此类条目」(合法空)：落 0 字节文件，
        下一 epoch 出清该列表条目，不计失败。firehol 是头部化 netset，
        空文件无头即坏，其同款非空守卫语义本对，故不改。

        活性锚 = all.txt 聚合(出版方存活证明)：锚空(200 空)或锚挂
        (404/超时) → 本轮零替换、旧文件全保留(fail-closed，防灾难性
        全空清库)，"all" 记真失败走部分失败梯经告警暴露，不 raise;
        抓取异常的子列表同理保留旧文件并记名 last_partial_failure。
        len(failed) == len(self._lists) 仍 raise(防空 rebuild 清库)。"""
        self._path.mkdir(parents=True, exist_ok=True)
        self._cleanup_legacy()
        landed: list[tuple[Path, Path]] = []   # (scratch, dest) 待锚门裁决
        failed: list[str] = []                 # 仅抓取异常(cancel 直 raise)
        try:
            for list_name in self._lists:
                if token is not None and token.is_cancelled():
                    raise CancelledError(f"{self.name} download cancelled")
                url = f"{_BASE_URL}/{list_name}.txt"
                dest = self._path / f"{list_name}.txt"
                scratch = dest.with_name(dest.name + ".dl")
                logger.info(f"Downloading blocklist_de/{list_name}...")
                try:
                    download_file(url, scratch, token=token,
                                  headers={"User-Agent": "ip-lookup-tool/1.0"})
                    landed.append((scratch, dest))
                except Exception as e:
                    failed.append(list_name)
                    logger.warning(
                        f"Failed to download blocklist_de/{list_name}: {e} "
                        f"— keeping existing file")
                    scratch.unlink(missing_ok=True)
            anchor = self._path / "all.txt.dl"
            anchor_empty = any(s == anchor for s, _ in landed) and \
                not anchor.read_bytes().strip()
            if "all" in failed or anchor_empty:
                for scratch, _ in landed:
                    scratch.unlink(missing_ok=True)
                if "all" not in failed:
                    failed.append("all")
                logger.warning(
                    "blocklist_de liveness anchor (all.txt) broken — "
                    "replacing nothing this cycle (fail-closed)")
            else:
                for scratch, dest in landed:
                    os.replace(scratch, dest)    # 合法空 0 字节照落
        except CancelledError:
            for scratch, _ in landed:            # 已抓未裁决 scratch 不得残留
                scratch.unlink(missing_ok=True)
            raise
        self.last_partial_failure = failed
        if len(failed) == len(self._lists):
            raise RuntimeError(
                f"all blocklist_de lists failed to download: {self._lists}")

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一重建入口)。多列表累积:同 CIDR 按优先级裁决
        classification_type,全部认领列表名进 native_categories。"""
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family, commit_dual_family
        from .._evidence import Evidence
        if not self._path.exists():
            return 0

        # cidr -> {"classification_type": ..., "native_categories": [...]}
        acc: dict[str, dict] = {}
        for list_name in self._lists:
            p = self._path / f"{list_name}.txt"
            if not p.exists():
                continue
            cls = BLOCKLIST_DE_MAP.get(list_name, "blacklist")
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
                    if net in acc:
                        cur = acc[net]
                        if _PRIORITY[cls] < _PRIORITY[cur["classification_type"]]:
                            cur["classification_type"] = cls
                        if list_name not in cur["native_categories"]:
                            cur["native_categories"].append(list_name)
                    else:
                        acc[net] = {"classification_type": cls,
                                    "native_categories": [list_name]}

        records = [
            (cidr, [Evidence(
                classification_type=info["classification_type"],
                verdict=self.verdict,
                reliability=self.reliability,
                native_categories=info["native_categories"],
            ).to_dict()])
            for cidr, info in acc.items()
        ]

        cov4 = covered_ip_count(c for c in acc.keys() if ":" not in c)
        cov6 = covered_ip_count(
            (c for c in acc.keys() if ":" in c), ip_version=6)
        return commit_dual_family(
            self, records, cov4=cov4, cov6=cov6, progress=progress)
    def health(self) -> SourceHealth:
        import time
        mtimes = []
        if self._path.exists():
            for list_name in self._lists:
                p = self._path / f"{list_name}.txt"
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
