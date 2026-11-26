"""「一个源的数据文件有多新」的唯一算法源(#465 卡16,伞票 #451)。

第四轮架构评审卡16(文档仓 reviews/2026-11-25-architecture-review-round4.md
第 16 张卡):这段算法此前抄在 12 处——基类 SourceBase.health() 一份、
单文件覆写两份(caida_asorg/insightflare_asn_blocklist)、多文件「取最新
mtime」四份(blocklist_de/echelon/cn_isp/firehol)、逐家 FeedHealth 三份
(rir_abuse/rir_delegated/cloud_ranges)、调度器 _scheduler._read_mtime 与
_registry._source_info 的 content_age_h 两处各算各的,其中注册表一处已和
health() 漂移(目录型源取到目录自身 mtime;调度器早就取目录内最新文件,
未漂)。本模块只放函数、不依赖任何源类:
源侧只声明数据文件清单(SourceBase._data_files 钩子),算法统一走这里。

行为契约(与 2026-11-26 master 02006a69 的旧实现逐字对齐;工单验收:
health() 改前改后逐源逐字段相同):
- convention 4(全文自 _base.py health() 迁入):staleness 跟 DATA FILE
  的 mtime,不跟内存 _loaded_at——load_db 前它为 0,跟内存值会逼每次
  重启都重下载。
- freshness:一个存在的文件都没有 → (None, True);否则 (最新 mtime 的
  UTC 串, now - 最新 mtime > stale_days*86400)。mtime 恰为 0 时
  last_updated 沿用旧基类 ``if file_mtime else None`` 的口径出 None
  (is_stale 同旧体照算)——仅 mtime==0 边界与「无文件」结果重合,
  保真不动;该口径与 feed_health 路径的旧体(rir_* 系,无 0 特例)在
  mtime==0 处差一档(mtime==0 即 1970-01-01T00:00:00Z 整,做得到——
  os.utime(p, (0, 0)) 或解包带零时间戳的 tar 成员——但本仓的下载和
  解包路径不产生修改时间为 0 的文件),不改旧语义。
- feed_health:文件缺失 → (None, True);存在 → 按各自停更线判。
"""
import time
from pathlib import Path

from .._types import FeedHealth

_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def newest_mtime(paths) -> float | None:
    """paths(可迭代)里存在的文件的 mtime 取最大;一个都不存在 → None。

    调度器目录分支对 OSError 自有 try/except(保持原位),本函数不吞。
    """
    mtimes = [Path(p).stat().st_mtime for p in paths if Path(p).exists()]
    return max(mtimes) if mtimes else None


def freshness(paths, *, stale_days: int,
              now: float | None = None) -> tuple[str | None, bool]:
    """(last_updated, is_stale)。规则与旧 SourceBase.health() 逐字一致,
    见模块 docstring 的行为契约。"""
    if now is None:
        now = time.time()
    m = newest_mtime(paths)
    if m is None:
        return None, True
    last_updated = time.strftime(_ISO_FMT, time.gmtime(m)) if m else None
    return last_updated, now - m > stale_days * 86400


def feed_health(specs, *, now: float | None = None) -> list[FeedHealth]:
    """specs 每项 (名字, 路径, 停更天数) → FeedHealth 列表(顺序保持)。

    逐家规则与 rir_abuse/rir_delegated/cloud_ranges 旧体一致(rir_* 用
    源级 stale_days,cloud_ranges 查 _FEEDS 表);缺文件 → last_updated
    None / is_stale True。源级裁决(任一家过期或无文件 → 源级过期;
    last_updated = 最新文件)留在各源 health(),此处不越权。
    """
    if now is None:
        now = time.time()
    feeds = []
    for name, path, stale_days in specs:
        last_updated, is_stale = freshness(
            [path], stale_days=stale_days, now=now)
        feeds.append(FeedHealth(
            name=name, last_updated=last_updated, is_stale=is_stale))
    return feeds
