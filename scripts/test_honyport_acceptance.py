"""scripts/honyport_acceptance.py 的最小测试(issue #274,TDD 口径)。

跑法(仓根;须用带 backend 三方库的解释器,验收脚本要打查询面):
  backend/.venv/bin/python -m pytest scripts/test_honyport_acceptance.py -q

钉三面(harness 自身的诚实性;被测链路的契约各自有 pytest 正本,#272/#271):
- 绿跑:合成夹具(含已知攻击 IP 195.178.110.218 两天双写法行)→ rc=0,
  五条 §6-1..§6-5 逐条 [PASS];
- 真夹具缺席:§6-1 [SKIP](不红)+ 降级跑 pytest 钉件,rc 仍 0,
  §6-2..§6-5 照常 PASS(合成路径不受影响);
- 失败面:任一检查 FAIL → rc=1(in-process 注入,不靠破坏产品码)。

真夹具(dev/honyport-fixtures/,gitignore)的全链手跑留 reports/
hp274-REPORT.md,不进本套件(与 scripts/test_honyport_aggregate.py 同约)。
"""
import csv
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "honyport_acceptance.py"
DAILY_HEADER = "ip,service,protocol,events,first_seen,last_seen"
KNOWN_IP = "195.178.110.218"   # 规格 §6-1 点名的夹具榜首(SSH 爆破)


def write_daily(d: Path, day: str, rows) -> Path:
    p = d / f"honeypot_attackers-{day}.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(DAILY_HEADER.split(","))
        for ip, svc, ev, first, last in rows:
            w.writerow([ip, svc, "", ev, first, last])
    return p


def synth_fixtures(tmp_path: Path) -> Path:
    """两天日 CSV:KNOWN_IP 双写法(`SSH interactive` / `ssh`)跨日累计,
    照真实夹具形态(#271 报告:481+481=962 的由来)。"""
    d = tmp_path / "fixtures"
    d.mkdir()
    write_daily(d, "2026-11-01", [
        (KNOWN_IP, "beelzebub/SSH interactive", 481,
         "2026-11-01T09:26:11Z", "2026-11-01T13:01:55Z"),
        ("9.9.9.9", "beelzebub/mssql", 10,
         "2026-11-01T08:00:00Z", "2026-11-01T08:05:00Z"),
    ])
    write_daily(d, "2026-11-02", [
        (KNOWN_IP, "beelzebub/ssh", 481,
         "2026-11-01T09:26:11Z", "2026-11-01T13:01:55Z"),
        ("9.9.9.9", "beelzebub/mssql", 5,
         "2026-11-02T01:00:00Z", "2026-11-02T01:03:00Z"),
    ])
    return d


def run(fixtures: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--fixtures", str(fixtures)],
        capture_output=True, text=True, timeout=900)


def test_green_run_all_five_pass(tmp_path):
    r = run(synth_fixtures(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    for n in range(1, 6):
        assert f"[PASS] §6-{n}" in r.stdout, f"§6-{n} 未 PASS:\n{r.stdout}"


def test_missing_fixtures_skip_not_red(tmp_path):
    """真夹具缺席:§6-1 SKIP(降级 pytest 钉件)不红,其余四条照常。"""
    r = run(tmp_path / "no-such-dir")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[SKIP] §6-1" in r.stdout
    assert "test_query_evidence_shape" in r.stdout     # 降级证据可见
    for n in (2, 3, 4, 5):
        assert f"[PASS] §6-{n}" in r.stdout, f"§6-{n} 未 PASS:\n{r.stdout}"


def test_any_fail_exits_one(tmp_path, monkeypatch):
    """harness 诚实报红:任一检查 FAIL → rc=1(注入,不碰产品码)。"""
    import honyport_acceptance as ha
    monkeypatch.setattr(ha, "CHECKS",
                        {1: lambda *a: ("SKIP", ["injected skip"]),
                         2: lambda *a: ("FAIL", ["injected failure"])})
    rc = ha.main(["--fixtures", str(tmp_path / "no-such-dir")])
    assert rc == 1
