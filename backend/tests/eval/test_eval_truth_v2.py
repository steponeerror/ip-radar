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
