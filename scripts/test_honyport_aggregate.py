"""scripts/honyport_aggregate.py 的 TDD 测试(issue #271,规格 §2.1)。

跑法(仓根): python3 -m pytest scripts/test_honyport_aggregate.py -q

真实两天原件在 dev/honyport-fixtures/(gitignore,不入仓),不进本套件 ——
本套件全部用合成夹具钉契约;真实件手跑产出贴 reports/hp271-REPORT.md。
覆盖矩阵对准规格 §2.1: 注释头逐字/引号 service 往返/跨日累计/窗边界
(起止含两端、超窗剔,门在 last_seen)/扫描段滤除行计数/白名单滤除/
坏行·坏表头·坏文件名·空目录 fail-loud/CLI 退非零。

约定: 聚合生成日 D=2026-11-30 → 窗 [2026-11-01, 2026-11-30] 含两端
(window_days=30: D-29d..D,窗止按日历日收全天)。
"""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

import honyport_aggregate as hpa

DAILY_HEADER = "ip,service,protocol,events,first_seen,last_seen"
D = "2026-11-30"
W_START, W_END = "2026-11-01", "2026-11-30"  # [D-29, D] 含两端

# 扫描段表样例(格式同 repo 中间件 scanner_ranges.csv: 无表头 cidr,vendor,
# 裸 IP 合法收作 /32,与 _sources/scanner_ranges.py 下载件同构)
SCANNER_LINES = ["203.0.113.0/24,Test Vendor",
                 "198.51.100.9/32,Single Probe"]


def write_daily(d: Path, day: str, rows) -> Path:
    """写一份日 CSV。rows = [(ip, service, events, first, last), ...]。"""
    p = d / f"honeypot_attackers-{day}.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(DAILY_HEADER.split(","))
        for r in rows:
            # protocol 槽插空;元组长度原样透传(列数少的坏行 fixture 靠短元组构造)
            w.writerow([r[0], r[1], "", *r[2:]])
    return p


@pytest.fixture
def env(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    scanner = tmp_path / "scanner_ranges.csv"
    scanner.write_text("\n".join(SCANNER_LINES) + "\n", encoding="utf-8")
    return {"tmp": tmp_path, "out": out_dir, "scanner": scanner,
            "agg": tmp_path / "aggregate"}


def run_agg(env, *extra, date=D):
    hpa.main(["--input-dir", str(env["out"]),
              "--output-dir", str(env["agg"]),
              "--scanner-ranges", str(env["scanner"]),
              "--date", date, *extra])
    p2 = env["agg"] / f"honeypot-observed-{date}.csv"
    assert p2.exists(), "产物文件名应为 honeypot-observed-<date>.csv"
    lines = p2.read_text(encoding="utf-8").splitlines()
    hdr = dict(ln[2:].split("=", 1) for ln in lines if ln.startswith("#"))
    rows = list(csv.DictReader(lines[5:]))
    return hdr, rows, lines


# ── 注释头 + 表头契约(§2.1 格式冻结)──


def test_header_lines_exact(env):
    write_daily(env["out"], "2026-11-02",
                [("9.9.9.9", "beelzebub/ssh", 3,
                  "2026-11-02T01:00:00Z", "2026-11-02T02:00:00Z")])
    hdr, rows, lines = run_agg(env)
    assert lines[0].startswith("# generated_at=")
    assert lines[1] == "# window_days=30"
    assert lines[2] == "# source_files=1"
    assert lines[3] == "# scanner_filtered=0"
    assert lines[4] == "# allowlist_filtered=0"
    assert lines[5] == "ip,first_seen,last_seen,services,total_events"
    assert hdr["source_files"] == "1"
    hpa.parse_ts(hdr["generated_at"], "generated_at")  # ISO 8601 可回析


def test_source_files_counts_merged_files(env):
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        write_daily(env["out"], day,
                    [("9.9.9.9", "beelzebub/ssh", 1,
                      f"{day}T01:00:00Z", f"{day}T01:00:01Z")])
    hdr, _, _ = run_agg(env)
    assert hdr["source_files"] == "3"


# ── 聚合语义: 跨日累计 / services 归一 / 排序 ──


def test_cross_day_accumulation_and_service_dedup(env):
    # 同一 IP 两天两形: 11-01 是 exporter 归一前 raw 描述, 11-02 已归一 —— 归一后
    # 必须折并成同一规范名(真实夹具正是这个形态),events 跨日求和,
    # first/last 取窗内极值。
    write_daily(env["out"], "2026-11-01",
                [("9.9.9.9", "beelzebub/Microsoft SQL Server 2019", 10,
                  "2026-11-02T01:00:00Z", "2026-11-02T02:00:00Z")])
    write_daily(env["out"], "2026-11-03",
                [("9.9.9.9", "beelzebub/mssql", 5,
                  "2026-11-03T01:00:00Z", "2026-11-03T03:00:00Z")])
    hdr, rows, _ = run_agg(env)
    assert len(rows) == 1
    r = rows[0]
    assert r["ip"] == "9.9.9.9"
    assert r["total_events"] == "15"
    assert r["first_seen"] == "2026-11-02T01:00:00Z"
    assert r["last_seen"] == "2026-11-03T03:00:00Z"
    assert r["services"] == "mssql"


def test_service_vocab_normalization_join_sorted(env):
    write_daily(env["out"], "2026-11-02", [
        ("8.8.4.4", "beelzebub/SSH interactive", 1,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z"),
        ("8.8.4.4", "beelzebub/Apache 401", 2,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:02Z"),
        ("8.8.4.4", "beelzebub/Redis 7.0.12", 4,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:03Z"),
        ("8.8.8.8", "beelzebub/Windows SMB File Server", 8,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:04Z"),
        ("8.8.8.8", "beelzebub/mssql", 16,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:05Z"),
    ])
    _, rows, _ = run_agg(env)
    by_ip = {r["ip"]: r for r in rows}
    assert by_ip["8.8.4.4"]["services"] == "http;redis;ssh"   # 去重排序 `;` 连
    assert by_ip["8.8.4.4"]["total_events"] == "7"            # 同日多行累计
    assert by_ip["8.8.8.8"]["services"] == "mssql;smb"


def test_unmatched_service_kept_verbatim(env):
    write_daily(env["out"], "2026-11-02",
                [("8.8.8.8", "somenewpot/Fancy Longtail", 1,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    _, rows, _ = run_agg(env)
    assert rows[0]["services"] == "somenewpot/Fancy Longtail"  # 命不中原样保留


def test_quoted_service_roundtrip(env):
    # exporter 事件服务带 CVE 列表(逗号分隔) → 日 CSV 里引号包裹(2026-11-02
    # Q4 裁)。聚合侧原样保留,产物 csv 重引号,消费方 csv.reader 无损回读。
    svc = "php2shell-2026/CVE-2026-109618,CVE-2026-109619"
    write_daily(env["out"], "2026-11-02",
                [("8.8.8.8", svc, 1,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    _, rows, lines = run_agg(env)
    assert rows[0]["services"] == svc
    raw = [ln for ln in lines if ln.startswith("8.8.8.8,")][0]
    assert f'"{svc}"' in raw  # 含逗号字段被 csv 引号包裹


def test_ip_sorted_numerically(env):
    ips = ["193.0.0.1", "2.0.0.1", "10.0.0.1", "9.0.0.1"]
    write_daily(env["out"], "2026-11-02",
                [(ip, "beelzebub/ssh", 1,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")
                 for ip in ips])
    _, rows, _ = run_agg(env)
    assert [r["ip"] for r in rows] == ["2.0.0.1", "9.0.0.1",
                                       "10.0.0.1", "193.0.0.1"]  # 按地址序


# ── 30 天窗(门在 last_seen, [D-29, D] 含两端,窗止收全天)──


def test_window_boundaries_inclusive(env):
    write_daily(env["out"], "2026-11-20", [
        # 窗起当日 00:00:00Z —— 含
        ("1.1.1.1", "beelzebub/ssh", 1,
         f"{W_START}T00:00:00Z", f"{W_START}T00:00:00Z"),
        # 窗止当日 23:59:59Z —— 含(日历日全天收)
        ("2.2.2.2", "beelzebub/ssh", 1,
         f"{W_END}T23:59:59Z", f"{W_END}T23:59:59Z"),
        # 前一日(D-30)23:59:59Z —— 超窗剔
        ("3.3.3.3", "beelzebub/ssh", 1,
         "2026-10-31T23:59:59Z", "2026-10-31T23:59:59Z"),
    ])
    _, rows, _ = run_agg(env)
    assert {r["ip"] for r in rows} == {"1.1.1.1", "2.2.2.2"}


def test_window_gate_is_last_seen_not_first(env):
    # first_seen 早于窗起但 last_seen 窗内 → 保留,first_seen 照实测原样出海
    # (窗门只看 last_seen,first/last 取窗内行的极值,不钳到窗边)。
    write_daily(env["out"], "2026-11-20",
                [("1.1.1.1", "beelzebub/ssh", 1,
                  "2026-10-01T00:00:00Z", f"{W_START}T12:00:00Z")])
    _, rows, _ = run_agg(env)
    assert rows[0]["first_seen"] == "2026-10-01T00:00:00Z"
    assert rows[0]["last_seen"] == f"{W_START}T12:00:00Z"


def test_out_of_window_ip_disappears_entirely(env):
    write_daily(env["out"], "2026-10-01",
                [("3.3.3.3", "beelzebub/ssh", 99,
                  "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z")])
    _, rows, _ = run_agg(env, date="2026-11-30")
    assert rows == []


# ── 过滤: 扫描段表 + 运维白名单(行计数自报,序贯不双计)──


def test_scanner_filter_counts_rows(env):
    write_daily(env["out"], "2026-11-02", [
        ("203.0.113.5", "beelzebub/ssh", 3,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z"),
        ("203.0.113.5", "beelzebub/mssql", 4,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:02Z"),   # 同 IP 两行都剔
        ("8.8.8.8", "beelzebub/ssh", 5,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:03Z"),   # 段外保留
        ("198.51.100.9", "beelzebub/ssh", 6,
         "2026-11-02T01:00:00Z", "2026-11-02T01:00:04Z"),   # 裸 IP /32 命中
    ])
    hdr, rows, _ = run_agg(env)
    assert hdr["scanner_filtered"] == "3"
    assert {r["ip"] for r in rows} == {"8.8.8.8"}


def test_allowlist_filter_and_optional(env):
    write_daily(env["out"], "2026-11-02",
                [("198.51.100.7", "beelzebub/ssh", 3,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    alw = env["tmp"] / "allowlist.txt"
    alw.write_text("# 自家运维源\n\n198.51.100.7\n", encoding="utf-8")
    hdr, rows, _ = run_agg(env, "--allowlist", str(alw))
    assert hdr["allowlist_filtered"] == "1"
    assert rows == []
    # 缺省可省: 不传 --allowlist 照跑,计数 0
    hdr2, rows2, _ = run_agg(env)
    assert hdr2["allowlist_filtered"] == "0"
    assert len(rows2) == 1


def test_filters_sequential_no_double_count(env):
    # IP 同时落扫描段又在白名单: 序贯管线只计 scanner_filtered 一次
    write_daily(env["out"], "2026-11-02",
                [("203.0.113.5", "beelzebub/ssh", 3,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    alw = env["tmp"] / "allowlist.txt"
    alw.write_text("203.0.113.5\n", encoding="utf-8")
    hdr, rows, _ = run_agg(env, "--allowlist", str(alw))
    assert hdr["scanner_filtered"] == "1"
    assert hdr["allowlist_filtered"] == "0"
    assert rows == []


# ── fail-loud: 坏数据退非零,不静默缩水(parse_snapshot_csv 同哲学)──


@pytest.mark.parametrize("row", [
    ("8.8.8.8", "beelzebub/ssh", 1, "2026-11-02T01:00:00Z"),          # 列数少一
    ("not-an-ip", "beelzebub/ssh", 1, "2026-11-02T01:00:00Z",
     "2026-11-02T01:00:01Z"),                                          # 非 v4
    ("2001:db8::1", "beelzebub/ssh", 1, "2026-11-02T01:00:00Z",
     "2026-11-02T01:00:01Z"),                                          # v6 不收
    ("8.8.8.8", "beelzebub/ssh", "abc", "2026-11-02T01:00:00Z",
     "2026-11-02T01:00:01Z"),                                          # 非整数 events
    ("8.8.8.8", "beelzebub/ssh", 1, "bogus",
     "2026-11-02T01:00:01Z"),                                          # 坏时间戳
    ("8.8.8.8", "beelzebub/ssh", 1, "2026-11-02 01:00:00",
     "2026-11-02T01:00:01Z"),                                          # 无时区
    ("8.8.8.8", "", 1, "2026-11-02T01:00:00Z",
     "2026-11-02T01:00:01Z"),                                          # 空 service
])
def test_bad_rows_fail_loud(env, row):
    write_daily(env["out"], "2026-11-02", [tuple(row)])
    with pytest.raises(ValueError):
        run_agg(env)


def test_bad_header_fails(env):
    p = env["out"] / "honeypot_attackers-2026-11-02.csv"
    p.write_text("ip,service,protocol,events,first,last\n"
                 "8.8.8.8,beelzebub/ssh,,1,2026-11-02T01:00:00Z,"
                 "2026-11-02T01:00:01Z\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run_agg(env)


@pytest.mark.parametrize("name", ["honeypot_attackers-2026-02-30.csv",
                                  "honeypot_attackers-daily.csv"])
def test_bad_filename_fails(env, name):
    (env["out"] / name).write_text(
        DAILY_HEADER + "\n8.8.8.8,beelzebub/ssh,,1,"
        "2026-11-02T01:00:00Z,2026-11-02T01:00:01Z\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run_agg(env)


def test_empty_dir_fails(env):
    with pytest.raises(ValueError):
        run_agg(env)


def test_dir_with_only_unrelated_files_fails(env):
    (env["out"] / "honeypot_techniques-2026-11-02.json").write_text("{}", "utf-8")
    with pytest.raises(ValueError):
        run_agg(env)


def test_unrelated_files_ignored_when_daily_present(env):
    write_daily(env["out"], "2026-11-02",
                [("8.8.8.8", "beelzebub/ssh", 1,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    (env["out"] / "honeypot_techniques-2026-11-02.json").write_text("{}", "utf-8")
    (env["out"] / "README.txt").write_text("notes", "utf-8")
    hdr, rows, _ = run_agg(env)
    assert hdr["source_files"] == "1"
    assert len(rows) == 1


def test_missing_scanner_table_fails(env):
    # 显式索取的排除清单缺席 = 装配错误(scanner_ranges_prefixes 同哲学),
    # 静默回空表会无声缩小排除面。
    write_daily(env["out"], "2026-11-02",
                [("8.8.8.8", "beelzebub/ssh", 1,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    with pytest.raises(FileNotFoundError):
        hpa.main(["--input-dir", str(env["out"]),
                  "--output-dir", str(env["agg"]),
                  "--scanner-ranges", str(env["tmp"] / "nope.csv"),
                  "--date", D])


def test_bad_allowlist_line_fails(env):
    write_daily(env["out"], "2026-11-02",
                [("8.8.8.8", "beelzebub/ssh", 1,
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    alw = env["tmp"] / "allowlist.txt"
    alw.write_text("not-an-ip\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run_agg(env, "--allowlist", str(alw))


def test_cli_exit_nonzero_on_bad_row(env):
    write_daily(env["out"], "2026-11-02",
                [("8.8.8.8", "beelzebub/ssh", "abc",
                  "2026-11-02T01:00:00Z", "2026-11-02T01:00:01Z")])
    r = subprocess.run(
        [sys.executable, str(Path(hpa.__file__).resolve()),
         "--input-dir", str(env["out"]),
         "--output-dir", str(env["agg"]),
         "--scanner-ranges", str(env["scanner"]),
         "--date", D],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert "abc" in r.stderr or "events" in r.stderr  # traceback 带证据
