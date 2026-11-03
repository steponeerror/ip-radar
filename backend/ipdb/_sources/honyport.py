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

二期 techniques 扩展(spec 2026-11-03 docs/research/
2026-11-03-honyport-techniques-spec.md §3,issue #282):download() 双件
= CSV 基座照旧 + 挂载目录内最新合法 honeypot_techniques-YYYY-MM-DD.json
原子拷入;rebuild 载 JSON 成 {ip: 八字段} 合并表,parse_row 按 IP 并入
extra.techniques(嵌套单键,字段名冻结 §3)。回声禁令(宁少算):JSON
services 整列表不出海 —— 查询面 services 仍以一期 CSV 归一词表为准,
JSON services 只走 CVE 提取(「事件id/CVE1,CVE2」剥前缀逗号拆分),防
同一事实双列表。容忍与报错:有 CSV 无 JSON → 一期行为不变(techniques
空,二期 cron 未上线期间不断供);JSON 在场但坏(缺 date/ips 键、坏
日期、per-IP 键集不符)→ fail-loud;JSON 有而基座无该 IP → 不出海
(基座缺席不补行)。源声明零改动(stale_days/reliability/eval_excluded
全沿用)。
"""
import ipaddress
import json
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

# 二期 §2:techniques 件名样(同目录同挂载,零新挂载点)
_TECHNIQUES_NAME_RE = re.compile(
    r"^honeypot_techniques-(\d{4}-\d{2}-\d{2})\.json$")

# §1 冻结 per-IP 键集(逐字断言;增删键 = 坏件 fail-loud)
_TECHNIQUES_IP_KEYS = frozenset({
    "events", "first_seen", "last_seen", "services", "protocols",
    "commands", "statuses", "actions", "stages", "paths",
    "user_agents"})

# §3 extra.techniques 八字段(嵌套单键,字段名冻结;cves 由 services
# 提取,其余七字段直透;services/events/first_seen/last_seen 不出海 ——
# 回声禁令 + 基座 CSV 已有)
_TECHNIQUES_FIELDS = ("commands", "user_agents", "cves", "protocols",
                      "statuses", "actions", "stages", "paths")

# CVE 词形(CVE-YYYY-NNNN+,2014 年后编号 ≥4 位;真样例锚
# php2shell-2026/CVE-2026-109618,CVE-2026-109619,spec §1)
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")

# §1 date 形:YYYY-MM-DD(fromisoformat 3.11+ 收紧形,名样即格式)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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
    techniques_filename = "honyport_techniques.json"   # 二期 §3 稳定名
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
        """挂载目录双件取件原子拷入 data_dir(§2.3 + 二期 §3,不走 HTTP)。

        CSV 基座:目录缺席 → 静默跳过报 absent(私有源遮蔽先例:开发机
        不受扰,不产生失败任务/告警);目录在场但无合法件 → RuntimeError
        fail-loud(cron 断供可见)。最新 = 文件名日期最大(mtime 跨拷贝
        不可信);原子落地 = atomic_write_bytes(scratch+replace,半写不
        冒充新证据)。
        techniques JSON(二期):与 CSV 同法取最新合法件;挂载目录无
        JSON 件 → 跳过不报错(§3 容忍:一期行为不变,techniques 空,
        二期 cron 未上线期间不断供)。
        """
        src_dir = Path(os.environ.get(AGGREGATE_DIR_ENV)
                       or _DEFAULT_AGGREGATE_DIR)
        if not src_dir.is_dir():
            logger.info(
                f"{self.name}: aggregate dir absent ({src_dir}) — source "
                f"stays absent (host without the mount; spec 2026-11-02 §2.3)")
            return
        latest = self._latest_named(src_dir, _AGGREGATE_NAME_RE)
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
        # 二期双件:techniques JSON 可缺席(§3 容忍),在场才拷
        latest_json = self._latest_named(src_dir, _TECHNIQUES_NAME_RE)
        if latest_json is None:
            logger.info(
                f"{self.name}: no honeypot_techniques JSON in {src_dir} — "
                f"techniques stay empty (spec 2026-11-03 §3 tolerance)")
            return
        atomic_write_bytes(self._techniques_path, latest_json.read_bytes())
        logger.info(
            f"Downloaded {self.name} techniques ({latest_json.name}, "
            f"{latest_json.stat().st_size} bytes) "
            f"-> {self._techniques_path.name}")

    @property
    def _techniques_path(self) -> Path:
        """data_dir 内 techniques 稳定名(download 拷入目标)。"""
        return self._data_dir / self.techniques_filename

    @staticmethod
    def _latest_named(src_dir: Path, name_re: re.Pattern) -> Path | None:
        """目录内最新合法件(文件名日期排序);不匹配名样(.tmp 等)忽略。

        CSV 基座与 techniques JSON 共用(二期 §2 同法取最新)。"""
        latest, latest_key = None, None
        for entry in sorted(src_dir.iterdir()):
            m = name_re.match(entry.name)
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
        """载入侧前置:表头断言 + 窗锚解析 + techniques 合并表(坏件
        fail-loud),再走基类。

        无数据文件(dev 机 absent)直接交基类 → 返回 0(基类存在性检查);
        techniques 件缺席 → 空表(一期行为不变,§3 容忍)。合并表每次
        rebuild 重建(旧件删后重跑不留残影)。
        """
        self._techniques = (self._load_techniques()
                            if self._techniques_path.exists() else {})
        if self._path.exists():
            self._window_anchor = self._read_window_anchor()
        return super().rebuild(progress=progress)

    def _load_techniques(self) -> dict[str, dict]:
        """techniques JSON → {ip: 八字段 dict};坏件 fail-loud(§3)。

        校验:date/ips 键在场、date 为 YYYY-MM-DD 合法日历日、per-IP
        键集 == §1 冻结集(增删键 = 坏件;exporter 格式漂移必须可见,
        不静默缩水)。services 只走 CVE 提取(回声禁令);events/
        first_seen/last_seen 不出海 —— 时间与计数基座 CSV 已有,evidence
        只认基座值,双源双值不并报。
        """
        try:
            data = json.loads(
                self._techniques_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise RuntimeError(
                f"{self.name}: cannot parse "
                f"{self._techniques_path.name}: {e} "
                f"(spec 2026-11-03 §3 fail-loud)") from e
        if (not isinstance(data, dict) or "date" not in data
                or "ips" not in data):
            raise RuntimeError(
                f"{self.name}: {self._techniques_path.name} missing "
                f"date/ips key (frozen format, spec 2026-11-03 §1)")
        if not _DATE_RE.fullmatch(str(data["date"])):
            raise RuntimeError(
                f"{self.name}: bad date {data['date']!r} in "
                f"{self._techniques_path.name} — want YYYY-MM-DD "
                f"(spec 2026-11-03 §1)")
        try:
            date.fromisoformat(str(data["date"]))
        except ValueError as e:
            raise RuntimeError(
                f"{self.name}: bad date {data['date']!r} in "
                f"{self._techniques_path.name}: {e}") from e
        ips = data["ips"]
        if not isinstance(ips, dict):
            raise RuntimeError(
                f"{self.name}: 'ips' not an object in "
                f"{self._techniques_path.name} (spec 2026-11-03 §1)")
        out: dict[str, dict] = {}
        for ip, entry in ips.items():
            if (not isinstance(entry, dict)
                    or set(entry) != _TECHNIQUES_IP_KEYS):
                raise RuntimeError(
                    f"{self.name}: per-IP key set mismatch for {ip} in "
                    f"{self._techniques_path.name} — want exactly "
                    f"{sorted(_TECHNIQUES_IP_KEYS)} (frozen, spec "
                    f"2026-11-03 §1)")
            out[ip] = {
                k: (self._extract_cves(entry["services"]) if k == "cves"
                    else list(entry[k]))
                for k in _TECHNIQUES_FIELDS}
        return out

    @staticmethod
    def _extract_cves(services: list) -> list[str]:
        """services 的唯一出口(回声禁令):「事件id/CVE1,CVE2」剥事件
        id 前缀、逗号拆分;只认 CVE 词形(「萤罐id/服务」形态自然落空)。
        去重保序(宁少算:同一 CVE 多事件不双计)。"""
        cves: list[str] = []
        for item in services:
            _, _, rest = str(item).partition("/")
            for token in rest.split(","):
                cve = token.strip()
                if _CVE_RE.fullmatch(cve) and cve not in cves:
                    cves.append(cve)
        return cves

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
        extra = {"total_events": int(total_events)}
        # 二期 §3:techniques 按 IP 并入(嵌套单键);JSON 有而基座无的
        # IP 走不到这里(rebuild 只出 CSV 行),基座缺席不补行;基座行
        # 无 JSON 条目 → 键整体缺席(一期形状不变,不填空 dict)
        tech = getattr(self, "_techniques", {}).get(ip)
        if tech is not None:
            extra["techniques"] = tech
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
            "extra": extra,
        }
