#!/usr/bin/env python3
"""honyport 日 CSV → 30 天窗聚合件(查询源专用,issue #271)。

规格: docs/research/2026-11-02-honyport-query-source-spec.md §2.1/§2.2
(格式冻结, #271/#272 共同契约)。读蜜罐日 CSV 目录(exporter 03:05 出件,
cron 03:10 跑本件),产出 honeypot-observed-YYYY-MM-DD.csv(生成日=文件名日)
到聚合目录。python3 stdlib,零三方依赖 —— 服务器裸 python3 可跑。

与真值组件的关系(§2.1): 真值层(truth_v2)读 /opt/honyport/out/ 日 CSV
原件走自己的 90d 窗清洗链;本产物是查询源专用,两条链互不触碰。

语义要点:
- 窗 = [生成日-29d, 生成日] 含两端(window_days=30);门在 last_seen,
  窗止按日历日收全天(<= 生成日 23:59:59…Z);first_seen/last_seen 取窗内
  保留行的极值(窗门只看 last_seen,first_seen 可早于窗起、原样出海)。
- services 归一照 exporter VOCAB 语义(honyport 仓 d9477ab): 受控词表
  ssh/http/redis/mssql/smb,命不中原样保留(长尾可见)。先剥 `蜜罐id/`
  前缀再判 —— 否则 d9477ab 前的 raw 日 CSV(`beelzebub/Microsoft SQL
  Server 2019`)与其后已归一日 CSV(`beelzebub/mssql`)会折不成同一
  规范名,跨日去重失效;剥前缀也防蜜罐 id 自身含词表串误命中。
  命不中保留全串(含 `事件id/CVE,...` 形态的引号字段,csv 引号自理)。
- total_events = 窗内全部日 CSV events 求和(跨日同 IP 累计)。
- 过滤序贯: 窗 → 扫描段表 → 运维白名单;行计数自报进注释头,一 IP 同
  落两表只计入 scanner_filtered(不双计)。扫描段表 = repo 中间件
  scanner_ranges.csv(cidr,vendor 无表头;裸 IP 收作 /32;缺件=装配错误
  fail-loud,truth_v2 scanner_ranges_prefixes 同哲学);白名单同 truth_v2
  --allowlist 用法(一行一个 v4,# 注释/空行跳过,参数可整体省略)。
- 坏行(非 v4、列数错、坏时间戳、坏表头、空 service)、坏文件名、空输入
  一律 fail-loud 退出非零,不静默缩水(parse_snapshot_csv 同哲学);
  输入目录里的无关文件(如 honeypot_techniques-*.json)忽略。

用法:
  python3 honyport_aggregate.py --scanner-ranges <repo>/data/scanner_ranges.csv \
      [--input-dir /opt/honyport/out] [--output-dir /opt/honyport/aggregate] \
      [--allowlist ops-allowlist.txt] [--date YYYY-MM-DD]

--date 缺省 = 当日 UTC;显式传入用于回填/测试(窗随日期确定性平移)。
"""
from __future__ import annotations

import argparse
import bisect
import csv
import ipaddress
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WINDOW_DAYS = 30
OUT_TMPL = "honeypot-observed-{d}.csv"
DAILY_GLOB = "honeypot_attackers-*.csv"
DAILY_STEM_RE = re.compile(r"^honeypot_attackers-(\d{4}-\d{2}-\d{2})\.csv$")
DAILY_HEADER = ["ip", "service", "protocol", "events", "first_seen",
                "last_seen"]
OUT_HEADER = ["ip", "first_seen", "last_seen", "services", "total_events"]

# service 受控词表 —— 与 honyport exporter/export_ips.py 的 VOCAB 逐字同源
# (honyport 仓 d9477ab, 2026-11-02 Q4 裁): (规范名, 识别串), 顺序敏感。
VOCAB = [("ssh", "SSH"), ("http", "Apache"), ("http", "HTTP"),
         ("redis", "Redis"), ("mssql", "SQL Server"), ("smb", "SMB")]
_CANON = {canon for canon, _ in VOCAB}


def norm_service(value: str) -> str:
    """日 CSV service 值 → 受控词表规范名;命不中返回原串。

    exporter 写 service 恒为 `{蜜罐id}/{规范名或描述}` 形态: 先剥首个 `/`
    前的蜜罐 id 再判(见模块 docstring「语义要点」的跨日折并理由)。
    """
    desc = value.split("/", 1)[1] if "/" in value else value
    low = desc.lower()
    if low in _CANON:            # d9477ab 后已归一形态: beelzebub/mssql
        return low
    for canon, needle in VOCAB:  # d9477ab 前 raw 描述: 含识别串即归一
        if needle.lower() in low:
            return canon
    return value                 # 长尾原样保留(全串,含事件id/CVE 形态)


def parse_ts(raw: str, ctx: str) -> datetime:
    """ISO 8601 且必须带时区(exporter 契约恒 Z)→ 归一 UTC。坏值炸。"""
    s = raw.strip()
    if s.endswith("Z"):          # py<3.11 的 fromisoformat 不认 Z 后缀
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError(f"{ctx}: 坏 ISO 8601 时间戳 {raw!r}") from None
    if dt.tzinfo is None:
        raise ValueError(f"{ctx}: 时间戳缺时区 {raw!r}")
    return dt.astimezone(timezone.utc)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_scanner_ranges(path: Path) -> list[tuple[int, int]]:
    """scanner_ranges.csv → 合并不相交闭区间表 [(start, end)]。

    行格式 cidr,vendor(无表头,与 _sources/scanner_ranges.py 下载件
    同构): 取首列 token,空行跳过;裸 IP 经 ip_network 即 /32,坏 token
    ValueError 炸出。合并成区间后 bisect 判定(29k 段 × 逐行线性扫不可
    收,truth_layer._drop_in_ranges 同法)。缺件自然 FileNotFoundError:
    显式索取的排除清单缺席是装配错误,静默回空表会无声缩小排除面。
    """
    pairs: list[tuple[int, int]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        token = line.split(",", 1)[0].strip()
        if not token:
            continue
        net = ipaddress.ip_network(token, strict=False)  # 容忍主机位脏写
        pairs.append((int(net.network_address),
                      int(net.network_address) + net.num_addresses - 1))
    merged: list[tuple[int, int]] = []
    for s, e in sorted(pairs):
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _in_ranges(ip_n: int, merged: list[tuple[int, int]]) -> bool:
    starts = [s for s, _ in merged]
    i = bisect.bisect_right(starts, ip_n) - 1
    return i >= 0 and ip_n <= merged[i][1]


def load_ops_allowlist(path: Path | None) -> set[str]:
    """运维白名单(truth_v2 load_ops_allowlist 同用法): 一行一个 v4,
    # 注释/空行跳过;坏行炸(白名单失配=静默放行运维 IP)。None=无白名单。"""
    if path is None:
        return set()
    out: set[str] = set()
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        token = ln.strip()
        if not token or token.startswith("#"):
            continue
        out.add(str(ipaddress.IPv4Address(token)))
    return out


def find_daily_files(input_dir: Path) -> list[Path]:
    """输入目录里的日 CSV 清单。文件名 wildcard 段非合法日期 → 炸
    (坏文件名不许静默跳过);零份日 CSV → 炸(空输入不出静默空件)。
    无关文件(techniques JSON 等)不在此 glob 内,自然忽略。"""
    files = sorted(input_dir.glob(DAILY_GLOB))
    for p in files:
        m = DAILY_STEM_RE.match(p.name)
        if not m:
            raise ValueError(
                f"{p}: 文件名缺 -YYYY-MM-DD 日期段")
        try:
            date.fromisoformat(m.group(1))
        except ValueError:
            raise ValueError(
                f"{p}: 文件名日期段非法(应 honeypot_attackers-YYYY-MM-DD"
                f".csv)") from None
    if not files:
        raise ValueError(f"{input_dir}: 无日 CSV(honeypot_attackers-*.csv)"
                         f"—— 空输入拒绝产出静默空聚合件")
    return files


def parse_daily(path: Path) -> list[dict]:
    """单份日 CSV → 行 dict 列表(ip/service/events/first/last, 均已校验)。

    表头逐字断言(exporter/export_ips.py 写出表头;加列=断粮,2026-11-02
    Q2 裁的 CSV 六列契约)。service 可含逗号(引号包裹)故用 csv.reader。
    """
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows or rows[0] != DAILY_HEADER:
        raise ValueError(f"{path}: 坏表头(应 {','.join(DAILY_HEADER)})")
    out: list[dict] = []
    for lineno, cols in enumerate(rows[1:], start=2):
        ctx = f"{path}:{lineno}"
        if len(cols) != len(DAILY_HEADER):
            raise ValueError(f"{ctx}: 列数错({len(cols)} 列, "
                             f"应 {len(DAILY_HEADER)})")
        ip_s, service, _protocol, ev_s, first_s, last_s = cols
        try:
            ip = str(ipaddress.IPv4Address(ip_s.strip()))
        except ValueError:
            raise ValueError(f"{ctx}: 非 v4 地址 {ip_s!r}") from None
        if not service.strip():
            raise ValueError(f"{ctx}: 空 service 列")
        try:
            events = int(ev_s.strip())
        except ValueError:
            raise ValueError(f"{ctx}: 非整数 events {ev_s!r}") from None
        out.append({"ip": ip, "service": service, "events": events,
                    "first": parse_ts(first_s, ctx + " first_seen"),
                    "last": parse_ts(last_s, ctx + " last_seen")})
    return out


def aggregate(input_dir: Path, asof: date,
              scanner_merged: list[tuple[int, int]],
              allowlist: set[str]) -> tuple[list[dict], dict]:
    """读全部日 CSV → (聚合行列表, 注释头计数)。行门与计数见模块 docstring。"""
    files = find_daily_files(input_dir)
    w_start = datetime.combine(asof - timedelta(days=WINDOW_DAYS - 1),
                               datetime.min.time(), tzinfo=timezone.utc)
    w_end_excl = datetime.combine(asof + timedelta(days=1),
                                  datetime.min.time(), tzinfo=timezone.utc)
    stats = {"source_files": len(files), "scanner_filtered": 0,
             "allowlist_filtered": 0}
    acc: dict[str, dict] = {}
    for p in files:
        for row in parse_daily(p):
            # ① 30 天窗: 门在 last_seen,窗止收生成日全天(< 次日零点)
            if not (w_start <= row["last"] < w_end_excl):
                continue
            # ② 扫描段表滤除(repo scanner_ranges)
            if _in_ranges(int(ipaddress.IPv4Address(row["ip"])),
                          scanner_merged):
                stats["scanner_filtered"] += 1
                continue
            # ③ 运维白名单滤除(同落两表只计 ② 一次,不双计)
            if row["ip"] in allowlist:
                stats["allowlist_filtered"] += 1
                continue
            e = acc.setdefault(row["ip"], {"services": set(), "total": 0,
                                           "first": row["first"],
                                           "last": row["last"]})
            e["services"].add(norm_service(row["service"]))
            e["total"] += row["events"]
            e["first"] = min(e["first"], row["first"])
            e["last"] = max(e["last"], row["last"])
    rows = [{"ip": ip, "first_seen": fmt_ts(v["first"]),
             "last_seen": fmt_ts(v["last"]),
             "services": ";".join(sorted(v["services"])),
             "total_events": v["total"]}
            for ip, v in acc.items()]
    rows.sort(key=lambda r: int(ipaddress.IPv4Address(r["ip"])))
    return rows, stats


def write_output(out_dir: Path, asof: date, rows: list[dict],
                 stats: dict, generated_at: datetime) -> Path:
    """原子写聚合件(tmp 同目录写完 os.replace,防 cron 半截件被 #272 拾走)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / OUT_TMPL.format(d=asof.isoformat())
    tmp = dest.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# generated_at={fmt_ts(generated_at)}\n")
        fh.write(f"# window_days={WINDOW_DAYS}\n")
        fh.write(f"# source_files={stats['source_files']}\n")
        fh.write(f"# scanner_filtered={stats['scanner_filtered']}\n")
        fh.write(f"# allowlist_filtered={stats['allowlist_filtered']}\n")
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(OUT_HEADER)
        for r in rows:
            w.writerow([r["ip"], r["first_seen"], r["last_seen"],
                        r["services"], r["total_events"]])
    os.replace(tmp, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="honyport 日 CSV → 30 天窗聚合件(查询源专用, #271)")
    ap.add_argument("--input-dir", type=Path, default=Path("/opt/honyport/out"),
                    help="蜜罐日 CSV 目录(exporter 03:05 出件处)")
    ap.add_argument("--output-dir", type=Path,
                    default=Path("/opt/honyport/aggregate"),
                    help="聚合件输出目录")
    ap.add_argument("--scanner-ranges", type=Path, required=True,
                    help="repo 中间件 scanner_ranges.csv(cidr,vendor)")
    ap.add_argument("--allowlist", type=Path, default=None,
                    help="运维白名单(一行一个 v4;可省)")
    ap.add_argument("--date", type=date.fromisoformat, default=None,
                    help="聚合生成日(=产物文件名日),缺省当日 UTC")
    args = ap.parse_args(argv)
    asof = args.date or datetime.now(timezone.utc).date()
    rows, stats = aggregate(args.input_dir, asof,
                            load_scanner_ranges(args.scanner_ranges),
                            load_ops_allowlist(args.allowlist))
    dest = write_output(args.output_dir, asof, rows, stats,
                        datetime.now(timezone.utc))
    print(f"wrote {dest} (rows={len(rows)}, "
          f"source_files={stats['source_files']}, "
          f"scanner_filtered={stats['scanner_filtered']}, "
          f"allowlist_filtered={stats['allowlist_filtered']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
