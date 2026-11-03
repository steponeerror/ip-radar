#!/usr/bin/env python3
"""honyport 一期验收一键回归(issue #274,规格 §6 五条;
二期 techniques 检查项 = issue #284,spec 2026-11-03 §5)。

规格: docs/research/2026-11-02-honyport-query-source-spec.md §6(权威);
二期: docs/research/2026-11-03-honyport-techniques-spec.md §5。
把五条验收钉成一键可跑的回归脚本 —— 全程离线本地(tmp 数据目录 + 夹具,
零生产接触、零网络);#272/#271 pytest 已钉住的缝不抄实现,断言 pytest
件存在 + 跑 pytest 子集(§6-1 基面 / §6-3 载入侧窗闸 / §6-5 评估面)。

五条 ↔ 实现面:
  §6-1 已知攻击 IP 查询出证,字段与聚合件逐项一致 —— 真夹具
       (dev/honyport-fixtures/,gitignore 不入仓)经 scripts/
       honyport_aggregate.py 聚合 → HonyportSource.rebuild → query;
       期望值从产物行 + 夹具独立回算派生(不硬编码魔法数:962 这类数值
       由「该 IP 全部日 CSV 行 events 求和」得出,聚合件行与查询证逐项
       比对)。真夹具缺席 → [SKIP] + 降级跑 pytest 钉件
       (test_query_evidence_shape,verbatim 真数已钉),不红。
  §6-2 构造含扫描段 IP 的聚合件 → 查询面零泄漏 —— 合成日 CSV(段内 IP
       + 段外正常 IP)+ 合成 scanner_ranges 表 → 聚合 → 产物行缺席 +
       注释头 scanner_filtered 计数 + rebuild 后 query {}(滤除在聚合侧,
       查询面零泄漏 = 聚合件里根本不存在)。
  §6-3 构造 last_seen 超窗行 → rebuild 后无证 —— 合成日 CSV(超窗行)
       → 聚合窗闸滤除 + 查询无证;载入侧窗闸(文件侧已滤、载入侧再拦
       一道)降级跑 pytest(test_rebuild_rejects_over_window_keeps_boundary)。
  §6-4 次日聚合件重跑 materialize → 键集与计数复算一致 —— ①同输入
       D 与 D+1 两次聚合(download 取最新件)物化后键集/字段全同;
       ②再加次日新数据(新 IP + 既有 IP 增计)→ 键集只增、旧键计数 =
       旧值 + 新增量(复算而非重置)。
  §6-5 评估跑批 --all:源清单含禁用行,honyport 无 θ/消融/verdict 记录
       —— 真注册表 in-process 直测(eval_excluded 声明 + _real_registry
       拆面互斥:可评估面/禁用面名字不相交)+ pytest 子集
       (tests/eval/test_eval_excluded.py 全件 + 真注册表剥离闸直测,后者
       钉 --all 禁用行/拒跑/记分卡)。真 --all 跑批需 DB/语料,非离线,
       不在此跑(离线红线,spec §6 脚本化的本意)。
  §6-6(二期 #284)techniques 件在场:锚 IP 出证 extra.techniques
       —— 夹具目录有 honeypot_techniques-*.json 时取最新合法件,合成
       基座(锚 IP 109.105.210.2 真聚合件被扫描段滤除,#282 同法特构造
       基座行;窗/扫描段面归 §6-3/§6-2)→ download 双件 → rebuild →
       查询:八字段形状、七字段直透、CVE 独立回算、回声禁令(JSON
       services 整串与 "services" 键不出海)、次新独有 IP 无键(只认
       最新件)、无条目 IP 一期形状不变、spec §1 两锚特断;缺 JSON
       → [SKIP] + 降级跑 pytest 钉件(test_honyport.py -k 'techniques
       or cve'),不红(开发机语义:真样例取样属部署面 #284)。

跑法(仓根;要打查询面须带 backend 三方库 → 用 backend/.venv 解释器):
  backend/.venv/bin/python scripts/honyport_acceptance.py \
      [--fixtures dev/honyport-fixtures] [--scanner-ranges <真表.csv>]
退出码:无 FAIL = 0(全 PASS 或含 SKIP);任一 FAIL = 1。SKIP 显式报不红。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend"))

import honyport_aggregate as hpa                     # noqa: E402
from ipdb._sources.honyport import (                 # noqa: E402
    AGGREGATE_DIR_ENV, HonyportSource)

KNOWN_IP = "195.178.110.218"   # 规格 §6-1 点名的夹具榜首(SSH 爆破僵尸)
DAILY_HEADER = "ip,service,protocol,events,first_seen,last_seen"
TITLES = {
    1: "已知攻击 IP 查询出证,字段与聚合件逐项一致",
    2: "扫描段 IP 聚合后查询面零泄漏",
    3: "last_seen 超窗行 rebuild 后无证",
    4: "次日聚合件重跑 materialize,键集与计数复算一致",
    5: "评估跑批源清单含禁用行,honyport 无 θ/消融/verdict 记录",
    6: "techniques 件在场:锚 IP 出证 extra.techniques + CVE 剥取 + 回声禁令"
       "(二期 spec 2026-11-03 §5)",
}


def say(msg: str) -> None:
    print(msg, flush=True)


# ── 共用小件 ─────────────────────────────────────────────


def write_daily(d: Path, day: str, rows) -> Path:
    """合成日 CSV;rows = [(ip, service, events, first, last), ...]。"""
    p = d / f"honeypot_attackers-{day}.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(DAILY_HEADER.split(","))
        for ip, svc, ev, first, last in rows:
            w.writerow([ip, svc, "", ev, first, last])
    return p


def run_aggregate(input_dir: Path, out_dir: Path, scanner_csv: Path,
                  asof: str) -> Path:
    """调 #271 正本聚合(子进程等价,同解释器内直调);失败自然抛出。

    产物 generated_at 钉回文件名日 03:10(生产 cron 时刻):#271 正本
    write_output 恒盖 now(),--date 显式回填时时间戳日与文件名日分离,
    而 #272 载入侧窗锚取 generated_at 日(§2.1 生产不变量 = 生成日≡
    文件名日:每日 cron 缺省 --date=当日,两者天然同日)。验收脚本按
    生产时间线仿真,与服务器 03:10 cron 产物同形。"""
    with redirect_stdout(io.StringIO()):
        hpa.main(["--input-dir", str(input_dir), "--output-dir", str(out_dir),
                  "--scanner-ranges", str(scanner_csv), "--date", asof])
    p = out_dir / f"honeypot-observed-{asof}.csv"
    text = p.read_text(encoding="utf-8")
    p.write_text(re.sub(r"^# generated_at=.*$",
                        f"# generated_at={asof}T03:10:00Z", text,
                        count=1, flags=re.M), encoding="utf-8")
    return p


def read_aggregate(p: Path) -> tuple[dict, list[dict]]:
    """聚合件 → (注释头 dict, 数据行 dict 列表)。"""
    lines = p.read_text(encoding="utf-8").splitlines()
    hdr = dict(ln[2:].split("=", 1) for ln in lines
               if ln.startswith("# ") and "=" in ln)
    rows = list(csv.DictReader(lines[5:]))      # 5 注释行 + 列头行在 [5]
    return hdr, rows


def materialize(agg_file: Path, tmp: Path) -> tuple[HonyportSource, int]:
    """聚合件拷入源数据目录 → rebuild → (源, 载入行数)。"""
    data = tmp / "src"
    data.mkdir(exist_ok=True)
    (data / "honyport_observed.csv").write_bytes(agg_file.read_bytes())
    s = HonyportSource(data_dir=data)
    return s, s.rebuild()


def pytest_run(args: list[str]) -> tuple[bool, str]:
    """backend 目录下跑 pytest 子集(降级/委托面);返回 (绿?, 输出尾行)。"""
    r = subprocess.run([sys.executable, "-m", "pytest", *args, "-q"],
                       cwd=REPO / "backend", capture_output=True, text=True,
                       timeout=900)
    tail = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (tail[-1] if tail else f"rc={r.returncode}")


def _default_scanner_table(tmp: Path, detail: list[str]) -> Path:
    """真扫描段表优先(repo 数据目录运行时件);缺席 → 空表代用并记明。

    只影响 §6-1 的滤除真实感,不影响期望推导(期望值本就从聚合产物行
    派生);§6-2 用自己的合成表,与此无关。"""
    for cand in (REPO / "backend" / "data" / "scanner_ranges.csv",
                 REPO / "data" / "scanner_ranges.csv"):
        if cand.is_file():
            detail.append(f"扫描段表: {cand}(repo 运行时件)")
            return cand
    p = tmp / "scanner-empty.csv"
    p.write_text("", encoding="utf-8")      # #271 扫描段表不吃 # 注释
    detail.append("扫描段表: 本地无 repo scanner_ranges.csv → 空表代用"
                  "(§6-2 另有合成表直测滤除面)")
    return p


# ── §6-1 已知攻击 IP 查询出证 ────────────────────────────


def check_1_known_ip(fixtures: Path | None, scanner_ranges: Path | None,
                     tmp: Path) -> tuple[str, list[str]]:
    detail: list[str] = []
    dailies = sorted(fixtures.glob("honeypot_attackers-*.csv")) \
        if fixtures else []
    if not dailies:
        ok, tail = pytest_run([
            "tests/sources/test_honyport.py::test_query_evidence_shape"])
        detail.append(f"真夹具缺席({KNOWN_IP} 全链未跑)→ 降级跑 pytest 钉件"
                      f" test_query_evidence_shape: {tail}")
        return ("FAIL" if not ok else "SKIP"), detail
    asof = max(hpa.DAILY_STEM_RE.match(p.name).group(1) for p in dailies)
    detail.append(f"夹具 {len(dailies)} 份日 CSV,聚合生成日 = {asof}")
    scan = scanner_ranges or _default_scanner_table(tmp, detail)
    agg = run_aggregate(fixtures, tmp / "agg", scan, asof)   # type: ignore
    _hdr, rows = read_aggregate(agg)
    row = next((r for r in rows if r["ip"] == KNOWN_IP), None)
    if row is None:
        return "FAIL", detail + [f"{KNOWN_IP} 未出现在聚合件"
                                 f"(rows={len(rows)};榜首 IP 必须在场)"]
    # 独立回算(不经聚合代码路径):该 IP 全部日 CSV 行 events 求和 ——
    # 数值断言从夹具派生,不硬编码魔法数(#271 报告 962 = 481+481 同法)。
    oracle_total, svc_raw = 0, []
    for p in dailies:
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["ip"] == KNOWN_IP:
                    oracle_total += int(r["events"])
                    svc_raw.append(r["service"])
    if int(row["total_events"]) != oracle_total:
        return "FAIL", detail + [
            f"聚合件 total_events={row['total_events']} ≠ 夹具独立回算 "
            f"{oracle_total}"]
    if "ssh" not in row["services"] or \
            not any("ssh" in s.lower() for s in svc_raw):
        return "FAIL", detail + [
            f"services={row['services']!r} 应含 ssh(夹具原行 "
            f"{svc_raw!r} 均为 SSH 爆破)"]
    # 物化 + 查询:字段与聚合件行逐项一致(spec §6-1)
    s, n = materialize(agg, tmp)
    recs = s.query(KNOWN_IP)
    if not recs:
        return "FAIL", detail + [f"rebuild={n} 行,但 query({KNOWN_IP}) 无证"]
    rec = recs[0]
    expect = [
        ("verdict", rec.get("verdict"), "malicious"),
        ("reliability", rec.get("reliability"), 0.85),
        ("first_seen", rec.get("first_seen"), row["first_seen"]),
        ("last_seen", rec.get("last_seen"), row["last_seen"]),
        ("services", rec.get("native_categories"),
         [x for x in row["services"].split(";") if x]),
        ("total_events", rec.get("extra", {}).get("total_events"),
         int(row["total_events"])),
    ]
    bad = [f"{k}: {got!r} ≠ {want!r}" for k, got, want in expect
           if got != want]
    if bad:
        return "FAIL", detail + ["查询证与聚合件行不一致: " + "; ".join(bad)]
    return "PASS", detail + [
        f"{KNOWN_IP}: services={row['services']} total_events="
        f"{row['total_events']}(夹具独立回算同值) first_seen="
        f"{row['first_seen']} last_seen={row['last_seen']}",
        f"rebuild 载入 {n} 行,查询证六字段逐项一致"
        f"(verdict/reliability/first/last/services/total_events)"]


# ── §6-2 扫描段零泄漏 ────────────────────────────────────


def check_2_scanner_zero_leak(_fixtures: Path | None,
                              _scanner: Path | None,
                              tmp: Path) -> tuple[str, list[str]]:
    detail: list[str] = []
    D = "2026-11-30"
    seg_ip, slash32, normal = "203.0.113.7", "198.51.100.9", "9.9.9.9"
    d = tmp / "daily"
    d.mkdir()
    write_daily(d, D, [
        (seg_ip, "beelzebub/mssql", 11,
         f"{D}T01:00:00Z", f"{D}T01:05:00Z"),
        (slash32, "beelzebub/ssh", 7,
         f"{D}T02:00:00Z", f"{D}T02:01:00Z"),
        (normal, "beelzebub/redis", 5,
         f"{D}T03:00:00Z", f"{D}T03:02:00Z"),
    ])
    scan = tmp / "scanner.csv"
    scan.write_text(f"203.0.113.0/24,Test Vendor\n"
                    f"{slash32}/32,Single Probe\n", encoding="utf-8")
    agg = run_aggregate(d, tmp / "agg", scan, D)
    hdr, rows = read_aggregate(agg)
    ips = {r["ip"] for r in rows}
    leak = [ip for ip in (seg_ip, slash32) if ip in ips]
    if leak or normal not in ips:
        return "FAIL", detail + [
            f"聚合件行集异常: 泄漏 {leak or '无'}, 正常 IP 在场="
            f"{normal in ips}(rows={sorted(ips)})"]
    if hdr.get("scanner_filtered") != "2":
        return "FAIL", detail + [
            f"注释头 scanner_filtered={hdr.get('scanner_filtered')!r} ≠ 2"
            "(段内 /24 一行 + /32 一行)"]
    s, n = materialize(agg, tmp)
    leaks = [ip for ip in (seg_ip, slash32) if s.query(ip)]
    if leaks or not s.query(normal):
        return "FAIL", detail + [
            f"查询面泄漏 {leaks or '无'} / 正常 IP 出证={bool(s.query(normal))}"
            f"(rebuild={n})"]
    return "PASS", detail + [
        f"{seg_ip}(/24 段内)与 {slash32}(/32)聚合滤除"
        f"(scanner_filtered=2)、rebuild={n} 后 query 均无证(零泄漏);",
        f"{normal} 出证正常(total_events="
        f"{s.query(normal)[0]['extra']['total_events']})—— 链路活着,"
        "不是空转绿"]


# ── §6-3 超窗行无证 ──────────────────────────────────────


def check_3_over_window(_fixtures: Path | None, _scanner: Path | None,
                        tmp: Path) -> tuple[str, list[str]]:
    detail: list[str] = []
    D, STALE = "2026-11-30", "2026-10-21"       # 超窗 40d(窗 [11-01, 11-30])
    fresh, stale = "9.9.9.9", "8.8.8.8"
    d = tmp / "daily"
    d.mkdir()
    write_daily(d, "2026-11-29", [
        (stale, "beelzebub/ssh", 3,
         f"{STALE}T00:00:00Z", f"{STALE}T00:01:00Z"),
        (fresh, "beelzebub/mssql", 4,
         "2026-11-29T00:00:00Z", "2026-11-29T00:02:00Z"),
    ])
    scan = tmp / "scanner-empty.csv"
    scan.write_text("", encoding="utf-8")    # 空表 = 零滤除(见上)
    agg = run_aggregate(d, tmp / "agg", scan, D)
    _hdr, rows = read_aggregate(agg)
    ips = {r["ip"] for r in rows}
    if stale in ips or fresh not in ips:
        return "FAIL", detail + [
            f"聚合窗闸异常: 超窗 {stale} 在场={stale in ips}, 窗内 "
            f"{fresh} 在场={fresh in ips}(rows={sorted(ips)})"]
    s, n = materialize(agg, tmp)
    if s.query(stale) or not s.query(fresh):
        return "FAIL", detail + [
            f"rebuild={n} 后 超窗 IP 出证={bool(s.query(stale))}"
            f"(应无证), 窗内 IP 出证={bool(s.query(fresh))}"]
    # 载入侧窗闸(文件带超窗行、载入再拦一道)已由 #272 pytest 钉住 ——
    # 委托跑之,不抄实现(任务单口径)。
    ok, tail = pytest_run([
        "tests/sources/test_honyport.py::"
        "test_rebuild_rejects_over_window_keeps_boundary"])
    detail.append(f"载入侧窗闸 pytest(test_rebuild_rejects_over_window_"
                  f"keeps_boundary): {tail}")
    return ("PASS" if ok else "FAIL"), detail + [
        f"{stale}(last_seen={STALE},超 30d 窗)聚合滤除 + rebuild={n} 后 "
        f"query 无证;{fresh} 窗内出证正常"]


# ── §6-4 次日重跑复算一致 ────────────────────────────────


def _snapshot(agg_file: Path, s: HonyportSource) -> dict[str, tuple]:
    """键集快照 = 聚合件行集;逐键值 = 查询证(services/total/first/last)。"""
    _hdr, rows = read_aggregate(agg_file)
    snap = {}
    for r in rows:
        rec = s.query(r["ip"])
        snap[r["ip"]] = (tuple(rec[0]["native_categories"]),
                         rec[0]["extra"]["total_events"],
                         rec[0]["first_seen"], rec[0]["last_seen"]) \
            if rec else None
    return snap


def check_4_next_day_recompute(_fixtures: Path | None, _scanner: Path | None,
                               tmp: Path) -> tuple[str, list[str]]:
    detail: list[str] = []
    D, D1 = "2026-11-30", "2026-12-01"          # 次日
    ipA, ipB = "9.9.9.9", "8.8.8.8"
    d = tmp / "daily"
    d.mkdir()
    write_daily(d, "2026-11-29", [(ipA, "beelzebub/ssh", 5,
                                   "2026-11-29T00:00:00Z",
                                   "2026-11-29T00:10:00Z"),
                                  (ipB, "beelzebub/mssql", 3,
                                   "2026-11-29T00:00:00Z",
                                   "2026-11-29T00:01:00Z")])
    write_daily(d, D, [(ipA, "beelzebub/ssh", 7,
                        "2026-11-30T00:00:00Z", "2026-11-30T00:10:00Z")])
    scan = tmp / "scanner-empty.csv"
    scan.write_text("", encoding="utf-8")    # 空表 = 零滤除(见上)
    agg_dir = tmp / "agg"
    data = tmp / "src"
    data.mkdir()
    s = HonyportSource(data_dir=data)
    old_env = os.environ.get(AGGREGATE_DIR_ENV)
    try:
        os.environ[AGGREGATE_DIR_ENV] = str(agg_dir)
        # ① 当日件:聚合 → download → 物化 → 快照
        f1 = run_aggregate(d, agg_dir, scan, D)
        s.download()
        n1 = s.rebuild()
        snap1 = _snapshot(f1, s)
        # ② 次日件(同输入重生成,窗平移一天)→ download 取最新 → 复算
        f2 = run_aggregate(d, agg_dir, scan, D1)
        s.download()
        n2 = s.rebuild()
        snap2 = _snapshot(f2, s)
        if snap1 != snap2 or n1 != n2:
            diff = {k: (snap1.get(k), snap2.get(k)) for k in
                    set(snap1) | set(snap2) if snap1.get(k) != snap2.get(k)}
            return "FAIL", detail + [
                f"同输入 D({D}) 与次日 D+1({D1}) 复算不一致 "
                f"(rebuild {n1}→{n2}): {diff}"]
        detail.append(f"同输入 D 与 D+1 各自聚合+download+rebuild: 键集 "
                      f"{sorted(snap1)} 与逐键计数/字段全同(rebuild={n2})")
        # ③ 次日新数据:新 IP + 既有 IP 增计 → 旧键复算 = 旧值 + 增量
        NEW = "7.7.7.7"
        write_daily(d, D1, [(NEW, "beelzebub/redis", 4,
                             f"{D1}T01:00:00Z", f"{D1}T01:02:00Z"),
                            (ipA, "beelzebub/ssh", 6,
                             f"{D1}T02:00:00Z", f"{D1}T02:05:00Z")])
        f3 = run_aggregate(d, agg_dir, scan, D1)
        s.download()
        n3 = s.rebuild()
        snap3 = _snapshot(f3, s)
        want_keys = set(snap2) | {NEW}
        if set(snap3) != want_keys:
            return "FAIL", detail + [
                f"次日新数据后键集 {sorted(snap3)} ≠ 期望 {sorted(want_keys)}"]
        a2, a3 = snap2[ipA], snap3[ipA]
        if a3[1] != a2[1] + 6 or a3[3] != f"{D1}T02:05:00Z" \
                or a3[0] != a2[0] or snap3[ipB] != snap2[ipB]:
            return "FAIL", detail + [
                f"旧键复算异常: {ipA} {a2} → {a3}(应 total+6=5+7+6, "
                f"last={D1}T02:05:00Z, services 不变); {ipB} "
                f"{snap2[ipB]} → {snap3[ipB]}(应不变)"]
        return "PASS", detail + [
            f"次日新数据(新 IP {NEW} + {ipA} 增 6 次)→ 键集只增"
            f"({len(snap2)}→{len(snap3)}), {ipA} total {a2[1]}→{a3[1]}"
            f"(旧值+增量, 复算非重置), {ipB} 不变, rebuild={n3}"]
    finally:
        if old_env is None:
            os.environ.pop(AGGREGATE_DIR_ENV, None)
        else:
            os.environ[AGGREGATE_DIR_ENV] = old_env


# ── §6-5 评估面恒禁用 ────────────────────────────────────


def check_5_eval_disabled(_fixtures: Path | None, _scanner: Path | None,
                          tmp: Path) -> tuple[str, list[str]]:
    detail: list[str] = []
    if HonyportSource.eval_excluded is not True:
        return "FAIL", ["HonyportSource.eval_excluded 必须为 True(spec §3)"]
    from ipdb._eval.__main__ import _real_registry
    ns = _real_registry()
    names = [x.name for x in ns.sources]
    excluded = [x.name for x in ns.eval_excluded_sources]
    if "honyport" in names or "honyport" not in excluded \
            or set(names) & set(excluded):
        return "FAIL", detail + [
            f"真注册表拆面异常: 可评估面含 honyport={'honyport' in names}, "
            f"禁用面含 honyport={'honyport' in excluded}, 交集="
            f"{sorted(set(names) & set(excluded))}"]
    detail.append(f"真注册表剥离闸: honyport 不在可评估面({len(names)} 源),"
                  f"单列禁用面{excluded}, 两面互斥(registry 剥离 + toggle "
                  "强禁两道闸的闸①)")
    # 闸②与 --all 禁用行/拒跑/记分卡:pytest 正本(#272),委托跑不抄实现。
    ok1, tail1 = pytest_run(["tests/eval/test_eval_excluded.py"])
    ok2, tail2 = pytest_run([
        "tests/eval/test_eval_cli.py::"
        "test_real_registry_strips_eval_excluded_sources"])
    detail.append(f"pytest tests/eval/test_eval_excluded.py: {tail1}")
    detail.append(f"pytest test_real_registry_strips_eval_excluded_sources: "
                  f"{tail2}")
    if not (ok1 and ok2):
        return "FAIL", detail
    return "PASS", detail + [
        "θ/消融/verdict/锚回归/融合读数全模式对 honyport 无记录"
        "(CLI 拒跑 + --all 只出禁用行 + 记分卡单列,pytest 正本钉住)"]


# ── §6-6(二期 #284)techniques 件在场:锚 IP 出证 ─────────


# 二期 spec 2026-11-03 §2 件名样(与 backend _TECHNIQUES_NAME_RE 同式;
# 验收侧独立持有,不从实现导入 —— 断言的是契约而非实现)
TECHNIQUES_JSON_RE = re.compile(
    r"^honeypot_techniques-(\d{4}-\d{2}-\d{2})\.json$")
# 二期 spec §3 extra.techniques 八字段(冻结;独立列,同上)
TECH_FIELDS = ("commands", "user_agents", "cves", "protocols",
               "statuses", "actions", "stages", "paths")
CVE_IP = "109.105.210.2"      # spec §1 CVE 形态锚(php2shell 件)
CVE_TOKEN_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")   # spec §1 CVE 词形


def _cve_oracle(services: list) -> list[str]:
    """CVE 剥取独立回算(spec §1:「/」前是事件 id,后是逗号分隔 CVE
    列表;只认 CVE 词形,去重保序)—— 不经 _extract_cves 代码路径
    (§6-1 独立回算同纪律)。"""
    out: list[str] = []
    for item in services:
        for token in str(item).partition("/")[2].split(","):
            cve = token.strip()
            if CVE_TOKEN_RE.fullmatch(cve) and cve not in out:
                out.append(cve)
    return out


def check_6_techniques(fixtures: Path | None, _scanner: Path | None,
                       tmp: Path) -> tuple[str, list[str]]:
    detail: list[str] = []
    cands: list[tuple[str, Path]] = []
    for p in sorted(fixtures.iterdir()) if fixtures else []:
        m = TECHNIQUES_JSON_RE.match(p.name)
        if m and p.is_file():
            cands.append((m.group(1), p))
    if not cands:
        ok, tail = pytest_run(
            ["tests/sources/test_honyport.py", "-k", "techniques or cve"])
        detail.append(
            "真 techniques JSON 缺席(开发机语义:真样例取样属部署面"
            " #284)→ 降级跑 pytest 钉件 test_honyport.py -k 'techniques "
            f"or cve': {tail}")
        return ("FAIL" if not ok else "SKIP"), detail
    cands.sort()
    D, latest = cands[-1]              # 文件名日期挑最新(download 同法)
    ips = json.loads(latest.read_text(encoding="utf-8"))["ips"]
    prev_only = (set(json.loads(cands[-2][1].read_text(encoding="utf-8"))
                     ["ips"]) - set(ips)) if len(cands) >= 2 else set()
    detail.append(f"夹具 {len(cands)} 份 techniques JSON,最新合法件 = "
                  f"{latest.name}(次新独有对照 {sorted(prev_only) or '无'})")
    # 基座 = 脚手架:本项只测 JSON 通道,基座日 CSV 由脚本合成(最新件
    # 全体 IP + 次新独有 IP + 一枚无 JSON 条目 IP)。锚 IP 109.105.210.2
    # 在真服务器聚合件里被扫描段滤除(#282 测试同法特构造基座行);
    # 窗/扫描段面归 §6-3/§6-2,此处空扫描段表 + 窗内行。
    plain = "9.9.9.9"
    d = tmp / "daily"
    d.mkdir()
    rows = [(ip, "beelzebub/ssh", 1, f"{D}T01:00:00Z", f"{D}T01:01:00Z")
            for ip in list(ips) + sorted(prev_only)]
    rows.append((plain, "beelzebub/mssql", 2,
                 f"{D}T02:00:00Z", f"{D}T02:02:00Z"))
    write_daily(d, D, rows)
    scan = tmp / "scanner-empty.csv"
    scan.write_text("", encoding="utf-8")    # 空表 = 零滤除(§6-2 另测)
    agg_dir = tmp / "agg"
    run_aggregate(d, agg_dir, scan, D)
    for _, p in cands:               # 双件同目录:聚合 CSV + 全部合法 JSON
        (agg_dir / p.name).write_bytes(p.read_bytes())
    (agg_dir / "scratch.tmp").write_text("杂件不匹配名样", encoding="utf-8")
    data = tmp / "src"
    data.mkdir()
    s = HonyportSource(data_dir=data)
    old_env = os.environ.get(AGGREGATE_DIR_ENV)
    try:
        os.environ[AGGREGATE_DIR_ENV] = str(agg_dir)
        s.download()                 # 双件:CSV 基座 + 最新合法 JSON
        n = s.rebuild()
        # ① 全体 JSON IP:八字段形状 + 七字段直透 + CVE 独立回算 +
        #    回声禁令(JSON services 整串与 "services" 键零出海)
        for ip, entry in ips.items():
            recs = s.query(ip)
            if not recs:
                return "FAIL", detail + [
                    f"{ip}: 基座行在场但 query 无证(rebuild={n})"]
            rec = recs[0]
            tech = rec.get("extra", {}).get("techniques")
            if not isinstance(tech, dict):
                return "FAIL", detail + [
                    f"{ip}: extra.techniques 缺席: {rec.get('extra')!r}"]
            if set(tech) != set(TECH_FIELDS):
                return "FAIL", detail + [
                    f"{ip}: techniques 字段集 {sorted(tech)} ≠ 冻结八字段"
                    f" {list(TECH_FIELDS)}(spec 2026-11-03 §3)"]
            for k in TECH_FIELDS:
                want = (_cve_oracle(entry["services"]) if k == "cves"
                        else list(entry[k]))
                if tech[k] != want:
                    return "FAIL", detail + [
                        f"{ip}: techniques[{k}]={tech[k]!r} ≠ 独立回算 "
                        f"{want!r}"]
            blob = json.dumps(rec, ensure_ascii=False, default=str)
            leak = [x for x in entry["services"] if str(x) in blob]
            if leak or '"services"' in blob:
                return "FAIL", detail + [
                    f"{ip}: 回声禁令破: JSON services 出海 {leak} 或键"
                    f"在场={'\"services\"' in blob}(spec §3 整列表不出海)"]
        # ② 只认最新件:次新独有 IP 出证而无 techniques 键
        for ip in sorted(prev_only):
            recs = s.query(ip)
            has_key = bool(recs) and "techniques" in recs[0]["extra"]
            if not recs or has_key:
                return "FAIL", detail + [
                    f"{ip}(仅次新件): 出证={bool(recs)}, techniques 键"
                    f"在场={has_key}(应出证而无键 —— 只认最新件)"]
        # ③ 无 JSON 条目 IP:一期 evidence 形状不变(techniques 键整体缺席)
        rec = s.query(plain)[0]
        if rec["extra"] != {"total_events": 2}:
            return "FAIL", detail + [
                f"{plain}(无 JSON 条目): extra={rec['extra']!r} ≠ 一期形状"
                " {'total_events': 2}(spec §3 不填空 dict)"]
        # ④ spec §1 两锚特断(在场才跑;泛化 ① 已覆盖全体 IP)
        anchors = []
        if CVE_IP in ips:
            t = s.query(CVE_IP)[0]["extra"]["techniques"]
            if t["cves"] != ["CVE-2026-109618", "CVE-2026-109619"] \
                    or "python-requests/2.31.0" not in t["user_agents"]:
                return "FAIL", detail + [
                    f"{CVE_IP} 锚不符: cves={t['cves']!r}(spec §1 冻结 = "
                    "[CVE-2026-109618, CVE-2026-109619]), user_agents="
                    f"{t['user_agents']!r}"]
            anchors.append(f"{CVE_IP}: cves={t['cves']}(事件 id 剥取,逗号"
                           "拆分), user_agents 含 python-requests/2.31.0")
        else:
            anchors.append(f"{CVE_IP} 不在最新件,锚断言未跑(泛化 ① 已覆盖)")
        if KNOWN_IP in ips:
            t = s.query(KNOWN_IP)[0]["extra"]["techniques"]
            if "/bin/./uname -s -v -n -r -m" not in t["commands"] \
                    or t["cves"] != []:
                return "FAIL", detail + [
                    f"{KNOWN_IP} 锚不符: commands={t['commands']!r}(spec "
                    "§1 真样例 uname 命令应在场), cves="
                    f"{t['cves']!r}(萤罐id/服务形态应零 CVE)"]
            anchors.append(f"{KNOWN_IP}: commands 含真样例 uname 行, "
                           "cves=[](beelzebub/ssh 形态零 CVE)")
        else:
            anchors.append(f"{KNOWN_IP} 不在最新件,锚断言未跑(泛化 ① 已覆盖)")
        return "PASS", detail + [
            f"download 双件 → rebuild={n}:最新件 {len(ips)} IP 全部出证,"
            "八字段形状 + 七字段直透 + CVE 独立回算逐 IP 一致;",
            "回声禁令:JSON services 整串与 \"services\" 键零出海;",
            f"次新独有 {sorted(prev_only) or '无'} 出证而无 techniques 键"
            f"(只认最新件); {plain} 无条目一期形状不变;",
            *anchors]
    finally:
        if old_env is None:
            os.environ.pop(AGGREGATE_DIR_ENV, None)
        else:
            os.environ[AGGREGATE_DIR_ENV] = old_env


CHECKS = {1: check_1_known_ip, 2: check_2_scanner_zero_leak,
          3: check_3_over_window, 4: check_4_next_day_recompute,
          5: check_5_eval_disabled, 6: check_6_techniques}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="honyport 验收一键回归(#274 一期规格 §6 五条 + "
                    "#284 二期 techniques 检查项)")
    ap.add_argument("--fixtures", type=Path,
                    default=REPO / "dev" / "honyport-fixtures",
                    help="真夹具目录(dev/honyport-fixtures,可缺 → §6-1 "
                         "SKIP+降级 pytest)")
    ap.add_argument("--scanner-ranges", type=Path, default=None,
                    help="扫描段表(缺省: repo 数据目录运行时件,再缺 → "
                         "空表代用并记明)")
    args = ap.parse_args(argv)
    fixtures = args.fixtures if args.fixtures.is_dir() else None
    if fixtures is None:
        say(f"# 真夹具目录缺席({args.fixtures})—— §6-1 将 SKIP+降级,"
            " §6-2..§6-5 走合成路径照常")
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    with tempfile.TemporaryDirectory(prefix="honyport-accept-") as td:
        tmp = Path(td)
        for num in sorted(CHECKS):
            workdir = tmp / f"c{num}"
            workdir.mkdir()
            try:
                status, detail = CHECKS[num](fixtures, args.scanner_ranges,
                                             workdir)
            except Exception as e:                    # 检查内异常 = FAIL,不吞
                status, detail = "FAIL", [f"检查内异常: {e!r}"]
            counts[status] += 1
            say(f"[{status}] §6-{num} {TITLES[num]}")
            for ln in detail:
                say(f"       {ln}")
    say(f"honyport 验收(#274 一期五条 + #284 二期 techniques): "
        f"{counts['PASS']} PASS / {counts['FAIL']} FAIL / "
        f"{counts['SKIP']} SKIP")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
