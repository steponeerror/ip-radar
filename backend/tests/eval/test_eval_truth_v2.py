# backend/tests/eval/test_eval_truth_v2.py
"""真值语料 v2 构建器测试(ADR 0017 / issue #260 T1)。

全部离线:合成周快照 CSV(格式照 scripts/truth_v2_weekly_snapshot.sh
文件头)、合成 rir delegated 文件、合成 scanner_ranges.csv;不碰真快照、
不碰 LMDB、零网络。验收线(issue #260):清洗链/90 天滚动窗边界/RIR 滚动
cutoff/组件闸 1,000/版本化双 pin/同输入重跑字节级一致/三闸各带负例。
"""
import ipaddress
import json
from datetime import date

import pytest

from ipdb._eval.assets import load_asset
from ipdb._eval.truth_v2 import (
    MIN_COMPONENT_IPS,
    WINDOW_DAYS,
    apply_reserved_filter,
    load_ops_allowlist,
    load_rir_ranges,
    parse_snapshot_csv,
    run_truth_v2,
    window_bounds,
)


def _ip(s: str) -> int:
    return int(ipaddress.IPv4Address(s))


# 合成可用路由主机段(gate 正例需要 ≥1,000 个互异 v4;185.60.0.0/16
# 是可路由公共段,不落 RFC1918/文档/CGNAT 等保留面)
def _ips(n: int, base: str = "185.60") -> list[str]:
    return [f"{base}.{i // 256}.{i % 256}" for i in range(n)]


def _snap(snap_dir, day: date, rows: list[tuple[str, int]]):
    """写一份 T0 周快照 CSV(逐字照采集脚本头部: # captured_at= 行 +
    ip,attempts 表头 + 数据行)。"""
    snap_dir.mkdir(parents=True, exist_ok=True)
    p = snap_dir / f"{day.isoformat()}.csv"
    p.write_text(
        "# ip-radar truth-v2 weekly snapshot\n"
        f"# captured_at={day.isoformat()}T06:00:00+0000 "
        'log_span_head="Oct 25" host=box\n'
        "# method=auth.log* {Failed password|Invalid user|max-auth} minus "
        "{Accepted login} sources minus ops_allowlist\n"
        "ip,attempts\n"
        + "".join(f"{ip},{n}\n" for ip, n in rows),
        encoding="utf-8")
    return p


def _rir_file(rir_dir, name: str, lines: list[str]):
    rir_dir.mkdir(parents=True, exist_ok=True)
    p = rir_dir / f"{name}.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# 全 v4 旧分配段(1990): 任何窗起点之前 → rir 闸恒放行的背景板
_OLD_ALL = [("ripencc|DE|ipv4|1.0.0.0|4294967294|19900101|allocated")]


def _context(tmp_path, n_pass: int = MIN_COMPONENT_IPS):
    """标准装配上下文: smallbox 组件 n_pass 个可路由 IP + 老分配 rir 面
    + 覆盖 185.61/16 的 scanner csv。"""
    snap = tmp_path / "snapshots"
    _snap(snap, date(2026, 11, 1), [(ip, 3) for ip in _ips(n_pass)])
    rir = tmp_path / "rir"
    _rir_file(rir, "ripencc", _OLD_ALL)
    scan = tmp_path / "scanner_ranges.csv"
    scan.write_text("185.61.0.0/16,Stretchoid\n2600:1f00::/24,Amazon\n",
                    encoding="utf-8")
    return {"components": {"smallbox": snap}, "rir_dir": rir,
            "scanner_csv": scan, "allowlist": None}


# ── 1. 快照解析(fail loud 族) ──────────────────────────────


def test_parse_snapshot_csv_extracts_date_and_rows(tmp_path):
    p = _snap(tmp_path, date(2026, 11, 1), [("1.2.3.4", 25), ("5.6.7.8", 1)])
    day, rows = parse_snapshot_csv(p)
    assert day == date(2026, 11, 1)
    assert rows == {"1.2.3.4": 25, "5.6.7.8": 1}


def test_parse_snapshot_missing_captured_at_fails_loud(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("# no captured line\nip,attempts\n1.2.3.4,5\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="captured_at"):
        parse_snapshot_csv(p)


def test_parse_snapshot_bad_row_fails_loud(tmp_path):
    p = _snap(tmp_path, date(2026, 11, 1), [])
    p.write_text(p.read_text() + "1.2.3.4,not-an-int\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_snapshot_csv(p)


# ── 2. 90 天滚动窗 + 边界归属(前后一天分属两版) ────────────────


def test_window_bounds_90_calendar_days_inclusive():
    start, end = window_bounds(date(2026, 11, 1))
    assert (end - start).days + 1 == WINDOW_DAYS
    assert end == date(2026, 11, 1) and start == date(2026, 8, 4)


def test_window_boundary_ip_attribution(tmp_path):
    """边界日(=窗起点)的 IP 进本版;窗起点前一天的 IP 属上一版不进本版
    (issue #260 验收线「窗边界 IP 归属正确」)。"""
    ctx = _context(tmp_path)
    snap = ctx["components"]["smallbox"]
    # 窗起点 2026-08-04(含)在窗内;前一天 2026-08-03 出局
    _snap(snap, date(2026, 8, 4), [("45.61.1.1", 7)])
    _snap(snap, date(2026, 8, 3), [("45.62.2.2", 9)])
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    assert res["status"] == "published"
    members, meta = load_asset(res["asset_dir"])
    assert "45.61.1.1" in members          # 边界日 = 窗起点当日 → 进
    assert "45.62.2.2" not in members      # 前一天 → 属上一版
    assert meta.params["window_start"] == "2026-08-04"


# ── 3. 组件闸 ≥1,000(负例:999 不装配,哨兵件不 raise) ─────────


def test_component_gate_short_sentinel_no_raise(tmp_path):
    ctx = _context(tmp_path, n_pass=MIN_COMPONENT_IPS - 1)  # 999
    out_root = tmp_path / "out"
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=out_root, eval_env="monthly")
    assert res["status"] == "insufficient"    # 不装配但也不 raise
    vdir = out_root / res["version"]
    assert (vdir / "status.json").is_file()
    assert sorted(p.name for p in vdir.iterdir()) == ["status.json"]  # 零资产落盘
    st = json.loads((vdir / "status.json").read_text())
    assert st["status"] == "insufficient"
    assert st["components"]["smallbox"]["member_count"] == MIN_COMPONENT_IPS - 1


def test_component_gate_mixed_passing_and_failing(tmp_path):
    """A 组件过闸、B 组件不过 → 只装配 A;B 的败因进 provenance 留痕。"""
    ctx = _context(tmp_path)
    honey = tmp_path / "honyport"
    _snap(honey, date(2026, 11, 1), [(ip, 2) for ip in _ips(5, base="185.62")])
    ctx["components"]["honyport"] = honey
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    assert res["status"] == "published"
    members, _ = load_asset(res["asset_dir"])
    assert not any(ip.startswith("185.62.") for ip in members)  # B 全不入
    prov = json.loads((res["asset_dir"] / "provenance.json").read_text())
    comp = prov["inputs"]["components"]
    assert comp["smallbox"]["gate_passed"] is True
    assert comp["honyport"]["gate_passed"] is False
    assert comp["honyport"]["member_count"] == 5


# ── 4. 清洗链: 白名单 / RFC1918 保留段 / 扫描段 ────────────────


def test_ops_allowlist_file_remembers_fixture(tmp_path):
    ctx = _context(tmp_path)
    _snap(ctx["components"]["smallbox"], date(2026, 10, 31),
          [("45.63.3.3", 40)])
    allow = tmp_path / "ops_allowlist.txt"
    allow.write_text("# self ops\n45.63.3.3\n\n", encoding="utf-8")
    ctx["allowlist"] = allow
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    members, _ = load_asset(res["asset_dir"])
    assert "45.63.3.3" not in members
    prov = json.loads((res["asset_dir"] / "provenance.json").read_text())
    c = prov["inputs"]["components"]["smallbox"]
    assert c["removed_by_allowlist"] == 1


def test_load_ops_allowlist_validates_and_skips_comments(tmp_path):
    p = tmp_path / "allow.txt"
    p.write_text("# comment\n1.2.3.4\n\n5.6.7.8\n", encoding="utf-8")
    assert load_ops_allowlist(p) == ["1.2.3.4", "5.6.7.8"]
    assert load_ops_allowlist(None) == []
    bad = tmp_path / "bad.txt"
    bad.write_text("not-an-ip\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ops_allowlist(bad)


def test_reserved_filter_drops_rfc1918_and_special_segments():
    kept, dropped = apply_reserved_filter(
        ["10.1.2.3", "192.168.1.1", "172.16.0.1", "127.0.0.1",
         "169.254.1.1", "100.64.0.1", "203.0.113.9", "240.0.0.1",
         "9.9.9.9", "185.60.0.1"])
    assert kept == ["9.9.9.9", "185.60.0.1"]
    assert dropped == 8


def test_scanner_filter_reuses_csv_first_column(tmp_path):
    """185.61/16 自报段成员被剔(复用 scanner_ranges 首列机制, ADR 0011)。"""
    ctx = _context(tmp_path)
    _snap(ctx["components"]["smallbox"], date(2026, 10, 30),
          [("185.61.5.5", 30)])
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    members, _ = load_asset(res["asset_dir"])
    assert "185.61.5.5" not in members
    prov = json.loads((res["asset_dir"] / "provenance.json").read_text())
    assert prov["inputs"]["components"]["smallbox"]["removed_by_scanner_filter"] == 1


def test_scanner_csv_missing_raises_not_silent(tmp_path):
    """缺件 raise 不静默缩水(排除面缺席=装配错误, v1 同款哲学)。"""
    ctx = _context(tmp_path)
    ctx["scanner_csv"] = tmp_path / "absent.csv"
    with pytest.raises(FileNotFoundError):
        run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                     scanner_csv=ctx["scanner_csv"],
                     allowlist=ctx["allowlist"],
                     out_root=tmp_path / "out", eval_env="monthly")


# ── 5. RIR 滚动 cutoff(负例: 分配日 ≥ 窗起点的段内 IP 剔) ────────


def test_rir_rolling_cutoff_boundary(tmp_path):
    """cutoff 随窗滚动(=窗起点 2026-08-04): 前一日分配保留、窗起点当日
    分配剔除 —— 逐字沿用 v1 闸「≥cutoff 剔」边界(ADR 0017 §6 推广
    ADR 0002 §2)。"""
    ctx = _context(tmp_path)
    _snap(ctx["components"]["smallbox"], date(2026, 10, 30),
          [("45.64.4.4", 5), ("45.65.5.5", 6)])
    _rir_file(ctx["rir_dir"], "apnic", [
        "apnic|CN|ipv4|45.64.4.0|256|20260803|allocated",   # cutoff-1 → 留
        "apnic|CN|ipv4|45.65.5.0|256|20260804|allocated",   # =cutoff → 剔
    ])
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    members, meta = load_asset(res["asset_dir"])
    assert "45.64.4.4" in members and "45.65.5.5" not in members
    assert meta.params["rir_cutoff"] == "2026-08-04"      # 滚动, 非冻结 2024-07-02
    prov = json.loads((res["asset_dir"] / "provenance.json").read_text())
    assert prov["inputs"]["components"]["smallbox"]["removed_by_rir_gate"] == 1


def test_load_rir_dir_fail_loud_on_missing_or_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_rir_ranges(tmp_path / "absent")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="0 ipv4"):
        load_rir_ranges(empty)


# ── 6. 版本化双 pin + 字节级一致 ────────────────────────────


def test_version_monthly_and_double_pin(tmp_path):
    ctx = _context(tmp_path)
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    assert res["version"] == "truthv2-202611"           # 月度重切口径
    vdir = tmp_path / "out" / "truthv2-202611"
    assert (vdir / "ips.txt").is_file()
    assert (vdir / "meta.json").is_file()
    prov = json.loads((vdir / "provenance.json").read_text())  # 双 pin sidecar
    snap_pin = prov["inputs"]["components"]["smallbox"]["files"][0]
    assert snap_pin["sha256"] and len(snap_pin["sha256"]) == 64
    assert prov["inputs"]["scanner_ranges"]["sha256"]
    assert prov["inputs"]["rir"]["files"][0]["sha256"]
    _, meta = load_asset(vdir)
    assert meta.kind == "truth_v2" and meta.eval_env == "monthly"
    assert meta.params["window_end"] == "2026-11-01"


def test_same_input_rerun_byte_identical(tmp_path):
    """同输入重跑字节级一致(issue #260 验收线): created_at 用锚日而非
    墙钟, 三件产物逐字节相等。"""
    import shutil
    ctx = _context(tmp_path)
    a = tmp_path / "out-a"
    b = tmp_path / "out-b"
    ctx2 = {**ctx, "components": {"smallbox": tmp_path / "snapshots2"}}
    shutil.copytree(ctx["components"]["smallbox"], ctx2["components"]["smallbox"])
    r1 = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                      scanner_csv=ctx["scanner_csv"], allowlist=None,
                      out_root=a, eval_env="monthly")
    r2 = run_truth_v2(ctx2["components"], rir_dir=ctx["rir_dir"],
                      scanner_csv=ctx["scanner_csv"], allowlist=None,
                      out_root=b, eval_env="monthly")
    assert r1["fingerprint"] == r2["fingerprint"]
    for name in ("ips.txt", "meta.json", "provenance.json"):
        assert ((a / r1["version"] / name).read_bytes()
                == (b / r2["version"] / name).read_bytes()), name


# ── 7. tamper-red(红证两枚) ───────────────────────────────


def test_tamper_input_snapshot_changes_pins(tmp_path):
    """改一行输入快照 → 成员指纹与输入 sha256 pin 都变(输入侧 pin 咬人,
    防换证不留痕)。"""
    ctx = _context(tmp_path)
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    r1 = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                      scanner_csv=ctx["scanner_csv"], allowlist=None,
                      out_root=out1, eval_env="monthly")
    snap = ctx["components"]["smallbox"] / "2026-11-01.csv"
    snap.write_text(snap.read_text() + "45.66.6.6,1\n", encoding="utf-8")
    r2 = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                      scanner_csv=ctx["scanner_csv"], allowlist=None,
                      out_root=out2, eval_env="monthly")
    assert r1["fingerprint"] != r2["fingerprint"]
    p1 = json.loads((out1 / r1["version"] / "provenance.json").read_text())
    p2 = json.loads((out2 / r2["version"] / "provenance.json").read_text())
    f1 = p1["inputs"]["components"]["smallbox"]["files"][0]["sha256"]
    f2 = p2["inputs"]["components"]["smallbox"]["files"][0]["sha256"]
    assert f1 != f2 and "45.66.6.6" in (out2 / r2["version"] / "ips.txt").read_text()


def test_tampered_published_asset_fails_load(tmp_path):
    """已出版资产被篡改 → load_asset 指纹闸炸(证据永不灭失, assets.py
    惯例;v2 资产同受闸)。"""
    ctx = _context(tmp_path)
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"], allowlist=None,
                       out_root=tmp_path / "out", eval_env="monthly")
    ips = res["asset_dir"] / "ips.txt"
    ips.write_text(ips.read_text() + "45.67.7.7\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        load_asset(res["asset_dir"])


# ── 8. CLI 接线(python -m ipdb._eval --truth-v2) ─────────────


def test_cli_truth_v2_publishes_under_report_dir(tmp_path, monkeypatch, capsys):
    from ipdb._eval.__main__ import main
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "rep"))
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    ctx = _context(tmp_path)
    main(["--truth-v2",
          "--truth-v2-component", f"smallbox={ctx['components']['smallbox']}",
          "--rir-dir", str(ctx["rir_dir"]),
          "--scanner-csv", str(ctx["scanner_csv"])])
    vdir = tmp_path / "rep" / "dev" / "truth-v2" / "truthv2-202611"
    assert (vdir / "ips.txt").is_file()      # 产物按 report_dir 约定
    out = capsys.readouterr().out
    assert "truth-v2" in out and "published" in out


def test_cli_truth_v2_bad_component_spec_fails_loud(tmp_path, monkeypatch, capsys):
    from ipdb._eval.__main__ import main
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "rep"))
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    ctx = _context(tmp_path)
    with pytest.raises(SystemExit) as ei:
        main(["--truth-v2",
              "--truth-v2-component", "no-equals-sign",
              "--rir-dir", str(ctx["rir_dir"]),
              "--scanner-csv", str(ctx["scanner_csv"])])
    assert ei.value.code == 2                 # 坏输入信封 rc=2(matrix_scan 同款)


# ── 9. T1 评审 P2-1: 同月先哨兵后过闸, 版本目录只留出版三件 ────


def test_publish_clears_stale_sentinel_same_month(tmp_path):
    """同月先 999(哨兵)后 ≥1,000(过闸): publish 分支清掉 stale
    status.json —— 版本目录终态 = 出版三件(ips/meta/provenance),
    哨兵残件不得冒充「同月既 insufficient 又 published」(P2-1)。"""
    from ipdb._eval.truth_v2 import run_truth_v2 as _run
    ctx = _context(tmp_path, n_pass=MIN_COMPONENT_IPS - 1)
    out_root = tmp_path / "out"
    r1 = _run(ctx["components"], rir_dir=ctx["rir_dir"],
              scanner_csv=ctx["scanner_csv"], allowlist=None,
              out_root=out_root, eval_env="monthly")
    assert r1["status"] == "insufficient"
    vdir = out_root / r1["version"]
    assert (vdir / "status.json").is_file()
    # 同月补 1 IP 过闸重跑 → publish 清哨兵, 目录只剩出版三件
    _snap(ctx["components"]["smallbox"], date(2026, 10, 31),
          [("45.68.8.8", 11)])
    r2 = _run(ctx["components"], rir_dir=ctx["rir_dir"],
              scanner_csv=ctx["scanner_csv"], allowlist=None,
              out_root=out_root, eval_env="monthly")
    assert r2["status"] == "published"
    assert sorted(p.name for p in vdir.iterdir()) == [
        "ips.txt", "meta.json", "provenance.json"]


def test_insufficient_clears_stale_published_same_month(tmp_path):
    """状态机镜像缺口负例(评审环条目 1, P1): 同月先 published 后跌回
    不足 → 旧出版三件必须清掉, 版本目录终态恰 ["status.json"]。
    probe 只认 ips.txt+meta.json 在场即当 published, 残件会把陈旧语料
    冒充现态(publish 分支清 stale 哨兵的镜像面)。"""
    from ipdb._eval.truth_v2 import run_truth_v2 as _run
    ctx = _context(tmp_path, n_pass=MIN_COMPONENT_IPS)
    out_root = tmp_path / "out"
    r1 = _run(ctx["components"], rir_dir=ctx["rir_dir"],
              scanner_csv=ctx["scanner_csv"], allowlist=None,
              out_root=out_root, eval_env="monthly")
    assert r1["status"] == "published"
    vdir = out_root / r1["version"]
    assert (vdir / "ips.txt").is_file()
    # 同锚月跌回不足(换 999 份快照重跑): 出版三件清, 只剩哨兵
    snap_b = tmp_path / "snapshots_b"
    _snap(snap_b, date(2026, 11, 1),
          [(ip, 3) for ip in _ips(MIN_COMPONENT_IPS - 1)])
    r2 = _run({"smallbox": snap_b}, rir_dir=ctx["rir_dir"],
              scanner_csv=ctx["scanner_csv"], allowlist=None,
              out_root=out_root, eval_env="monthly")
    assert r2["status"] == "insufficient"
    assert sorted(p.name for p in vdir.iterdir()) == ["status.json"]
    # 读数腿探测面同证: 残件不清会把陈旧语料冒充 published 现态
    from ipdb._eval.truth_v2_readout import probe_truth_v2_corpus
    assert probe_truth_v2_corpus(out_root)["status"] == "insufficient"


# ── 10. honyport 日 CSV 组件(issue #265: 表头探测 + 窗边界 + 双组件端到端) ─


def _hp_csv(hp_dir, day: date, rows: list[tuple], name: str | None = None):
    """写一份合成 honyport 日 CSV(逐字照服务器 exporter 实测格式 #265:
    六列表头 ip,service,protocol,events,first_seen,last_seen, 时间戳
    ISO 8601 Z;文件名 honeypot_attackers-<YYYY-MM-DD>.csv, 采集日取自
    文件名而非表头)。rows=六元组, 离线合成不碰真数据。"""
    hp_dir.mkdir(parents=True, exist_ok=True)
    p = hp_dir / (name or f"honeypot_attackers-{day.isoformat()}.csv")
    p.write_text(
        "ip,service,protocol,events,first_seen,last_seen\n"
        + "".join(",".join(str(c) for c in r) + "\n" for r in rows),
        encoding="utf-8")
    return p


def _hp_row(ip: str, events=1, service="beelzebub/Microsoft SQL Server 2019",
            protocol=""):
    return (ip, service, protocol, events,
            "2026-11-01T06:12:19Z", "2026-11-01T06:12:34Z")


def test_parse_honyport_day_from_filename_events_accumulate(tmp_path):
    """采集日取文件名(表头无 captured_at);同 IP 多 service 行 events
    累加(成员判定只看 IP 集合, 行为计数如实; #265 实测样例同 IP 可
    跨 service 多行)。"""
    from ipdb._eval.truth_v2 import parse_honyport_csv
    p = _hp_csv(tmp_path, date(2026, 11, 1), [
        _hp_row("60.20.14.95", events=29),
        _hp_row("60.20.14.95", events=24, service="beelzebub/Redis 7.0.12"),
        _hp_row("202.175.115.114", events=2),
    ])
    day, rows = parse_honyport_csv(p)
    assert day == date(2026, 11, 1)
    assert rows == {"60.20.14.95": 53, "202.175.115.114": 2}


def test_parse_honyport_quoted_service_field_survives(tmp_path):
    """service 字段含逗号(exporter CSV 引号包裹)→ csv.reader 正确
    分列, 不把引号字段拆成坏行。"""
    from ipdb._eval.truth_v2 import parse_honyport_csv
    p = _hp_csv(tmp_path, date(2026, 11, 1), [])
    p.write_text(
        "ip,service,protocol,events,first_seen,last_seen\n"
        '60.20.14.95,"beelzebub/x, y",,29,'
        "2026-11-01T06:12:19Z,2026-11-01T06:12:34Z\n",
        encoding="utf-8")
    _, rows = parse_honyport_csv(p)
    assert rows == {"60.20.14.95": 29}


def test_parse_honyport_fail_loud_family(tmp_path):
    """tamper-red 族: 文件名无日期段/坏表头/列数错/非整数 events/非 v4/
    坏时间戳 → ValueError(坏 CSV 不许静默缩水, parse_snapshot_csv
    同款哲学)。"""
    from ipdb._eval.truth_v2 import parse_honyport_csv
    # 文件名缺 -YYYY-MM-DD 段
    p = _hp_csv(tmp_path, date(2026, 11, 1), [_hp_row("1.2.3.4")],
                name="honeypot_attackers.csv")
    with pytest.raises(ValueError, match="日期"):
        parse_honyport_csv(p)
    # 未知表头(六列但列名不对)
    p = _hp_csv(tmp_path, date(2026, 11, 1), [_hp_row("1.2.3.4")],
                name="honeypot_attackers-2026-11-01.csv")
    p.write_text("ip,svc,proto,n,first,last\n1.2.3.4,s,,1,"
                 "2026-11-01T06:12:19Z,2026-11-01T06:12:34Z\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        parse_honyport_csv(p)
    # 列数错(5 列)
    p = _hp_csv(tmp_path, date(2026, 11, 1), [],
                name="honeypot_attackers-2026-11-01.csv")
    p.write_text("ip,service,protocol,events,first_seen,last_seen\n"
                 "1.2.3.4,s,,1,2026-11-01T06:12:19Z\n", encoding="utf-8")
    with pytest.raises(ValueError, match="6"):
        parse_honyport_csv(p)
    # events 非整数
    p = _hp_csv(tmp_path, date(2026, 11, 1), [],
                name="honeypot_attackers-2026-11-01.csv")
    p.write_text("ip,service,protocol,events,first_seen,last_seen\n"
                 "1.2.3.4,s,,twenty,2026-11-01T06:12:19Z,"
                 "2026-11-01T06:12:34Z\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_honyport_csv(p)
    # 非 v4 地址
    p = _hp_csv(tmp_path, date(2026, 11, 1), [],
                name="honeypot_attackers-2026-11-01.csv")
    p.write_text("ip,service,protocol,events,first_seen,last_seen\n"
                 "not-an-ip,s,,1,2026-11-01T06:12:19Z,"
                 "2026-11-01T06:12:34Z\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_honyport_csv(p)
    # 坏时间戳(first_seen 非 ISO 8601)
    p = _hp_csv(tmp_path, date(2026, 11, 1), [],
                name="honeypot_attackers-2026-11-01.csv")
    p.write_text("ip,service,protocol,events,first_seen,last_seen\n"
                 "1.2.3.4,s,,1,Nov-1,2026-11-01T06:12:34Z\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="timestamp"):
        parse_honyport_csv(p)


def test_load_snapshots_sniffs_both_formats_rejects_unknown(tmp_path):
    """同一组件目录逐文件表头探测(#265): 快照格式与 honyport 日 CSV
    并存可用;未知表头 ValueError fail-loud。"""
    from ipdb._eval.truth_v2 import load_snapshots
    mixed = tmp_path / "mixed"
    _snap(mixed, date(2026, 11, 1), [("45.70.1.1", 3)])
    _hp_csv(mixed, date(2026, 10, 31), [_hp_row("45.71.1.1", events=4)])
    out = load_snapshots(mixed)
    # 文件名序(字典序): '2026-11-01.csv' < 'honeypot_attackers-…',
    # 与格式无关 —— 排序键是文件名不是采集日
    assert [(d, sorted(r)) for _, d, r in out] == [
        (date(2026, 11, 1), ["45.70.1.1"]),
        (date(2026, 10, 31), ["45.71.1.1"]),
    ]
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "x.csv").write_text("ip,count\n1.2.3.4,5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        load_snapshots(bad)


def test_honyport_window_boundary_day_files(tmp_path):
    """窗归属边界(#265 验收线: 边界日前后各一 fixture): 文件名日 =
    窗起点当日(2026-08-04)的日 CSV 计入本版; 前一日(2026-08-03)的
    属上一版不进 —— 归属规则与快照面同律, 只是采集日来源换文件名。
    断言落在组件级 provenance 计数上: honyport 起步个位数 IP 必不过
    组件闸, 出版 ips 只由 smallbox 贡献(窗归属与组件闸正交, #265)。"""
    ctx = _context(tmp_path)
    honey = tmp_path / "honyport"
    _hp_csv(honey, date(2026, 11, 1), [_hp_row("45.72.1.1")])  # 锚日
    _hp_csv(honey, date(2026, 8, 4), [_hp_row("45.73.3.3")])   # 窗起点当日
    _hp_csv(honey, date(2026, 8, 3), [_hp_row("45.74.4.4")])   # 前一日
    ctx["components"]["honyport"] = honey
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    assert res["status"] == "published"        # smallbox 过闸照常出版
    members, _ = load_asset(res["asset_dir"])
    assert not any(ip.startswith("45.7") for ip in members)  # 哨兵组件零漏入
    prov = json.loads((res["asset_dir"] / "provenance.json").read_text())
    hp = prov["inputs"]["components"]["honyport"]
    assert hp["n_snapshots"] == 3
    assert hp["n_snapshots_in_window"] == 2      # 锚日 + 窗起点当日
    assert hp["raw_unique"] == 3 and hp["removed_by_window"] == 1
    assert hp["member_count"] == 2               # 前一日 IP 已被窗剔


def test_two_components_end_to_end_union(tmp_path):
    """两组件(快照 smallbox + 日 CSV honyport)并存端到端(#265 验收
    线): 双双过闸 → 成员=两组件并集, provenance 双 gate_passed。"""
    ctx = _context(tmp_path)               # smallbox: 185.60/16 ×1,000
    honey = tmp_path / "honyport"
    _hp_csv(honey, date(2026, 11, 1),
            [_hp_row(ip, events=2) for ip in _ips(1_000, base="185.63")])
    ctx["components"]["honyport"] = honey
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    assert res["status"] == "published"
    members, meta = load_asset(res["asset_dir"])
    assert res["member_count"] == 2_000   # 1,000 + 1,000 互异基段并集
    assert sum(1 for ip in members if ip.startswith("185.63.")) == 1_000
    comp = {n: st["gate_passed"] for n, st in res["components"].items()}
    assert comp == {"smallbox": True, "honyport": True}


def test_honyport_tiny_component_sentinel_union_with_smallbox(tmp_path):
    """honyport 起步个位数 IP = 恒哨兵(#265 验收线: 合法态): 该组件
    不过闸不装配, smallbox 照常出版, honyport 成员零漏入。"""
    ctx = _context(tmp_path)
    honey = tmp_path / "honyport"
    _hp_csv(honey, date(2026, 11, 1), [_hp_row(ip) for ip in (
        "45.75.1.1", "45.75.1.2", "45.75.1.3")])
    ctx["components"]["honyport"] = honey
    res = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                       scanner_csv=ctx["scanner_csv"],
                       allowlist=ctx["allowlist"],
                       out_root=tmp_path / "out", eval_env="monthly")
    assert res["status"] == "published"          # smallbox 过闸即出版
    members, _ = load_asset(res["asset_dir"])
    assert not any(ip.startswith("45.75.") for ip in members)
    assert res["components"]["honyport"] == {
        "gate_passed": False, "member_count": 3}


def test_tamper_honyport_input_changes_pins(tmp_path):
    """tamper-red(#265): 改一行 honyport 日 CSV → 输入 sha256 pin 变。
    成员指纹不变是正确的(honyport 个位数不过闸, 出版成员只由
    smallbox 决定)—— 换证留痕的证据面是组件输入 pin 与组件计数。"""
    ctx = _context(tmp_path)
    honey = tmp_path / "honyport"
    _hp_csv(honey, date(2026, 10, 31), [_hp_row("45.76.1.1", events=5)])
    ctx["components"]["honyport"] = honey
    r1 = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                      scanner_csv=ctx["scanner_csv"], allowlist=None,
                      out_root=tmp_path / "o1", eval_env="monthly")
    assert r1["fingerprint"]  # smallbox 出版在先, 指纹面存在
    p = honey / "honeypot_attackers-2026-10-31.csv"
    p.write_text(p.read_text() +
                 "45.77.7.7,s,,9,2026-11-01T06:12:19Z,"
                 "2026-11-01T06:12:34Z\n", encoding="utf-8")
    r2 = run_truth_v2(ctx["components"], rir_dir=ctx["rir_dir"],
                      scanner_csv=ctx["scanner_csv"], allowlist=None,
                      out_root=tmp_path / "o2", eval_env="monthly")
    p1 = json.loads((tmp_path / "o1" / r1["version"] /
                     "provenance.json").read_text())
    p2 = json.loads((tmp_path / "o2" / r2["version"] /
                     "provenance.json").read_text())
    h1 = p1["inputs"]["components"]["honyport"]
    h2 = p2["inputs"]["components"]["honyport"]
    assert h1["files"][0]["sha256"] != h2["files"][0]["sha256"]
    assert h1["raw_unique"] == 1 and h2["raw_unique"] == 2
    assert r1["fingerprint"] == r2["fingerprint"]  # 哨兵组件不入出版面

