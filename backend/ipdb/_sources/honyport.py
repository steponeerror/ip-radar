"""honyport 自建蜜罐观测 — CsvSource subclass(本地聚合件,不走 HTTP)。

数据链(spec 2026-11-02 docs/research/2026-11-02-honyport-query-source-spec.md
§2,honyport 仓 aggregate cron):exporter 日 CSV → 每日 03:10 聚合出
``honeypot-observed-YYYY-MM-DD.csv``(格式冻结 §2.1:5 行注释头(generated_at/
window_days/source_files/scanner_filtered/allowlist_filtered)+ 列头
``ip,first_seen,last_seen,services,total_events``;行 = last_seen 落在
[文件名日−29d, 文件名日];#271 经 docker bind mount 把
/opt/honyport/aggregate 挂进容器)。本源 download() 从挂载目录取最新合法
件原子拷入 data_dir —— 与线上 API 零接触(架构红线:纯本地源)。

- 目录缺席(开发机无挂载)→ download() 静默跳过、源报 absent(照私有源
  遮蔽先例:未配置环境不受扰,零失败任务/告警噪声);目录在场但无合法
  件 → fail-loud(服务器侧 cron 断供必须可见)。
- materialize 契约(§2.3):坏文件 fail-loud —— 列头逐字断言(加列=断粮)
  + generated_at 可解析;last_seen 超 30d 硬窗(§1 保鲜:以 last_seen 计)
  行拒入,窗锚 = generated_at 日(§2.1 生成日≡文件名日;拷入 data_dir 改
  名后文件名日只存活在头里)—— 文件侧已滤,载入侧再拦一道。

分类 = scanner 槽 + verdict=malicious(sensor 观测类既有槽,turris/dshield
2026-09-29 同类判例;不新增分类枚举);reliability 0.85(自建直接观测,
无转载链,grill 裁决);非 derived;authoritative_for=()。
eval_excluded=True(§3):查询池成员、评估面恒禁用 —— honyport 观测同时
是真值语料组件(ADR 0017 §2),同源双用会自证,故评估跑批(θ/消融/
verdict/锚回归/融合读数)永不启用它;reliability 固定 0.85 不进测量回流
(eval 面无记录 → 永不出现在任何校准建言;declared_r 仅只读对照列)。
honeypot_methodology=True:蜜罐法采集事实声明(k_nonhoneypot 剔除依据,
binarydefense/knock_knock 同族元数据如实;评估面已恒禁用,此处不生效)。
provenance_tier=\"A\":自建采集(官方/自采档,月报记分卡「评估禁用源」行
provenance 列如实)。
"""
import ipaddress
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

from ._base import CsvSource
from ._download import atomic_write_bytes

logger = logging.getLogger(__name__)

AGGREGATE_DIR_ENV = "IP_RADAR_HONYPORT_AGGREGATE_DIR"
# 容器内缺省挂载点:容器数据根 = /app/data(Dockerfile ENV
# IP_RADAR_DATA_DIR),bind mount 目标放数据根子路径;#271 落地时以
# docker-compose.override 同名挂载对齐(或 env 覆写)。开发机无此目录
# → 源 absent。
_DEFAULT_AGGREGATE_DIR = "/app/data/honyport-aggregate"

# §2.1 冻结文件名(日期 = 生成日;聚合 cron 正本在 honyport 仓)
_AGGREGATE_NAME_RE = re.compile(r"^honeypot-observed-(\d{4}-\d{2}-\d{2})\.csv$")

# §2.1 冻结列头(逐字断言;加列 = 断粮,fail-loud)
_COLUMNS = "ip,first_seen,last_seen,services,total_events"

_WINDOW_DAYS = 30   # 30d 硬窗(§1 保鲜:以 last_seen 计,不做随龄衰减)


def _parse_ts(text: str) -> datetime:
    """§2.1 时间戳(exporter Z 形或带偏移 ISO8601);坏值 ValueError。"""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class HonyportSource(CsvSource):
    name = "honyport"
    category = "threat"
    url_exempt = True        # 本地挂载目录取件,无远端 URL(#253 护栏豁免)
    filename = "honyport_observed.csv"
    fields = ("is_malicious",)
    classification_type = "scanner"
    verdict = "malicious"
    stale_days = 2           # 聚合 cron 日更,两日未新 = 陈旧
    reliability = 0.85       # 自建直接观测,无转载链(grill 裁决,固定)
    authoritative_for = ()
    provenance_tier = "A"    # 自建采集
    honeypot_methodology = True
    eval_excluded = True     # 评估面恒禁用(spec §3;查询池照常成员)
    skip_lines = 6           # §2.1 头:5 注释行 + 1 列头行

    def download(self, token=None) -> None:
        """挂载目录取最新合法件原子拷入 data_dir(§2.3,不走 HTTP)。

        目录缺席 → 静默跳过报 absent(私有源遮蔽先例:开发机不受扰,
        不产生失败任务/告警);目录在场但无合法件 → RuntimeError fail-loud
        (cron 断供可见)。最新 = 文件名日期最大(mtime 跨拷贝不可信);
        原子落地 = atomic_write_bytes(scratch+replace,半写不冒充新证据)。
        """
        src_dir = Path(os.environ.get(AGGREGATE_DIR_ENV)
                       or _DEFAULT_AGGREGATE_DIR)
        if not src_dir.is_dir():
            logger.info(
                f"{self.name}: aggregate dir absent ({src_dir}) — source "
                f"stays absent (host without the mount; spec 2026-11-02 §2.3)")
            return
        latest = self._latest_aggregate(src_dir)
        if latest is None:
            raise RuntimeError(
                f"{self.name}: no valid "
                f"honeypot-observed-YYYY-MM-DD.csv in {src_dir} — aggregate "
                f"cron broken? (spec 2026-11-02 §2.3 fail-loud)")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self._path, latest.read_bytes())
        logger.info(
            f"Downloaded {self.name} ({latest.name}, "
            f"{latest.stat().st_size} bytes) -> {self._path.name}")

    @staticmethod
    def _latest_aggregate(src_dir: Path) -> Path | None:
        """目录内最新合法件(文件名日期排序);不匹配名样(.tmp 等)忽略。"""
        latest, latest_key = None, None
        for entry in sorted(src_dir.iterdir()):
            m = _AGGREGATE_NAME_RE.match(entry.name)
            if not m or not entry.is_file():
                continue
            key = (m.group(1), entry.name)
            if latest_key is None or key > latest_key:
                latest, latest_key = entry, key
        return latest

    def _read_window_anchor(self) -> date:
        """§2.1 头解析:generated_at(≡文件名日)+ 列头逐字断言。

        坏文件 fail-loud(§2.3 materialize 契约):列头漂移 / 缺
        generated_at / 坏时间戳 → RuntimeError(rebuild 前置即拒,旧 epoch
        不动)。返回 30d 窗锚日期 = 文件名日。
        """
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as e:
            raise RuntimeError(
                f"{self.name}: cannot read {self._path.name}: {e}") from e
        generated: str | None = None
        header: str | None = None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("# generated_at="):
                generated = s.split("=", 1)[1].strip()
            elif s and not s.startswith("#") and header is None:
                header = s
                break
        if header != _COLUMNS:
            raise RuntimeError(
                f"{self.name}: bad column header {header!r} — expected "
                f"{_COLUMNS!r} (frozen format, spec 2026-11-02 §2.1; "
                f"adding columns starves the query source)")
        if not generated:
            raise RuntimeError(
                f"{self.name}: missing '# generated_at=' header "
                f"(frozen format, spec 2026-11-02 §2.1)")
        try:
            return _parse_ts(generated).date()
        except ValueError as e:
            raise RuntimeError(
                f"{self.name}: bad generated_at {generated!r}: {e}") from e

    def rebuild(self, progress=None) -> int:
        """载入侧前置:表头断言 + 窗锚解析(坏文件 fail-loud),再走基类。

        无数据文件(dev 机 absent)直接交基类 → 返回 0(基类存在性检查)。
        """
        if self._path.exists():
            self._window_anchor = self._read_window_anchor()
        return super().rebuild(progress=progress)

    def parse_row(self, row: list[str]) -> dict | None:
        """§2.1 行:ip,first_seen,last_seen,services,total_events。

        结构坏(列数≠5 / 坏 IP / 非 v4 / 坏时间戳 / 坏计数)→ raise
        ValueError(坏文件 fail-loud,不静默缩水,§2.3);last_seen 超窗
        (rebuild 设的锚日 [−29d, 0] 之外)→ None 拒入(文件侧已滤,
        载入侧再拦一道)。evidence:native_categories=services 列表、
        first_seen/last_seen 富槽、total_events → 查询期 route_record 折
        入 extra(sw_scanners company 先例)。
        """
        if len(row) != 5:
            raise ValueError(
                f"{self.name}: bad row — want 5 columns, got "
                f"{len(row)}: {row!r}")
        ip, first_seen, last_seen, services, total_events = (
            c.strip() for c in row)
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError(f"{self.name}: bad ip {ip!r} in row {row!r}") \
                from None
        if addr.version != 4:
            raise ValueError(f"{self.name}: non-v4 ip {ip!r} in row {row!r}")
        try:
            ls = _parse_ts(last_seen)
            _parse_ts(first_seen)
        except ValueError:
            raise ValueError(
                f"{self.name}: bad timestamp in row {row!r}") from None
        if not total_events.isdigit():
            raise ValueError(
                f"{self.name}: bad total_events {total_events!r} "
                f"in row {row!r}")
        anchor = getattr(self, "_window_anchor", None)
        if anchor is not None and not (
                0 <= (anchor - ls.date()).days < _WINDOW_DAYS):
            return None                     # 超窗行拒入(30d 硬窗)
        return {
            "_ip": ip,
            "classification_type": self.classification_type,
            "verdict": self.verdict,
            "reliability": self.reliability,   # CsvSource 存 dict 原样,须自带(sw_scanners 同款)
            "native_categories": [s for s in services.split(";") if s],
            "first_seen": first_seen,
            "last_seen": last_seen,
            # 「共 X 次」展示锚:扩展字段走 Evidence 现有 extra 机制
            # (sw_scanners company 先例,嵌套预填;字段名测试钉死)
            "extra": {"total_events": int(total_events)},
        }
