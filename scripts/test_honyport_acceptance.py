"""scripts/honyport_acceptance.py 的最小测试(issue #274,TDD 口径;
二期 techniques 检查项扩展 = issue #284)。

跑法(仓根;须用带 backend 三方库的解释器,验收脚本要打查询面):
  backend/.venv/bin/python(worktree 语境指向主检出 venv) -m pytest scripts/test_honyport_acceptance.py -q

钉四面(harness 自身的诚实性;被测链路的契约各自有 pytest 正本,#272/#271/#282):
- 绿跑:合成夹具(含已知攻击 IP 195.178.110.218 两天双写法行 + 二期
  techniques JSON 两件:CVE 件 + commands 件,锚形态逐字照票 A
  pytest 夹具)→ rc=0,六条 §6-1..§6-6 逐条 [PASS];
- 真夹具缺席:§6-1/§6-6 [SKIP](不红)+ 降级跑 pytest 钉件,rc 仍 0,
  §6-2..§6-5 照常 PASS(合成路径不受影响);
- 失败面:任一检查 FAIL → rc=1(in-process 注入,不靠破坏产品码);
- 二期失败面:techniques 夹具坏件(per-IP 键集漂移)→ §6-6 FAIL
  → rc=1(fail-loud 哲学经 harness 转为验收红,不吞)。

真夹具(dev/honyport-fixtures/,gitignore)的全链手跑留 reports/
hp274-REPORT.md,不进本套件(与 scripts/test_honyport_aggregate.py 同约)。
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "honyport_acceptance.py"
DAILY_HEADER = "ip,service,protocol,events,first_seen,last_seen"
KNOWN_IP = "195.178.110.218"   # 规格 §6-1 点名的夹具榜首(SSH 爆破)
CVE_IP = "109.105.210.2"       # 二期 spec §1 CVE 形态锚

# 二期 techniques 锚形态(逐字照票 A backend/tests/sources/
# test_honyport.py 的 _TECH_CVE_ENTRY / _TECH_SSH_ENTRY —— 服务器
# 2026-11-02/03 件真样例;验收夹具与 pytest 夹具同源,不另造形状)
TECH_CVE_ENTRY = {
    "events": 1,
    "first_seen": "2026-11-02T17:10:02.599Z",
    "last_seen": "2026-11-02T17:10:02.599Z",
    "services": ["php2shell-2026/CVE-2026-109618,CVE-2026-109619"],
    "protocols": ["http"],
    "commands": [],
    "statuses": [],
    "actions": ["http_request"],
    "stages": ["probe"],
    "paths": ["/bitsight/internet_census/probe"],
    "user_agents": ["python-requests/2.31.0"],
}
TECH_SSH_ENTRY = {
    "events": 481,
    "first_seen": "2026-11-01T09:26:11Z",
    "last_seen": "2026-11-01T13:01:55Z",
    "services": ["beelzebub/ssh"],
    "protocols": ["SSH"],
    "commands": ["/bin/./uname -s -v -n -r -m",
                 "lspci | grep \"3D controller\" | cut -f5- -d ' '"],
    "statuses": ["Start", "Stateless"],
    "actions": [],
    "stages": [],
    "paths": [],
    "user_agents": [],
}


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
    # 二期 techniques JSON 两件 + 次新对照件:最新件(11-02)含两锚 IP;
    # 次新件(11-01)独有 203.0.113.9 → 钉「只认最新件」+ 键集校验形态
    (d / "honeypot_techniques-2026-11-01.json").write_text(
        json.dumps({"date": "2026-11-01",
                    "ips": {"203.0.113.9": TECH_CVE_ENTRY}},
                   ensure_ascii=False), encoding="utf-8")
    (d / "honeypot_techniques-2026-11-02.json").write_text(
        json.dumps({"date": "2026-11-02",
                    "ips": {CVE_IP: TECH_CVE_ENTRY,
                            KNOWN_IP: TECH_SSH_ENTRY}},
                   ensure_ascii=False), encoding="utf-8")
    return d


def synth_tech_fixtures(tmp_path: Path) -> Path:
    """二期路径:日 CSV 夹具 + techniques JSON(最新件坏 = per-IP 键集
    漂移,票 A fail-loud 面的正样例)。"""
    d = synth_fixtures(tmp_path)
    bad = dict(TECH_CVE_ENTRY)
    bad.pop("paths")                      # 缺键 → 键集漂移
    (d / "honeypot_techniques-2026-11-02.json").write_text(
        json.dumps({"date": "2026-11-02",
                    "ips": {CVE_IP: bad}},
                   ensure_ascii=False), encoding="utf-8")
    return d


def run(fixtures: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--fixtures", str(fixtures)],
        capture_output=True, text=True, timeout=900)


def test_green_run_all_six_pass(tmp_path):
    r = run(synth_fixtures(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    for n in range(1, 7):
        assert f"[PASS] §6-{n}" in r.stdout, f"§6-{n} 未 PASS:\n{r.stdout}"


def test_missing_fixtures_skip_not_red(tmp_path):
    """真夹具缺席:§6-1/§6-6 SKIP(降级 pytest 钉件)不红,其余四条照常。"""
    r = run(tmp_path / "no-such-dir")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[SKIP] §6-1" in r.stdout
    assert "test_query_evidence_shape" in r.stdout     # 降级证据可见
    assert "[SKIP] §6-6" in r.stdout                    # 二期:缺 JSON 语义
    assert "techniques" in r.stdout                     # 降级证据可见
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


def test_techniques_bad_json_fails_red(tmp_path):
    """二期坏件面:最新 techniques JSON per-IP 键集漂移 → §6-6 FAIL,
    rc=1(#282 fail-loud 哲学:rebuild RuntimeError 经 harness 转红,不吞)。"""
    r = run(synth_tech_fixtures(tmp_path))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "[FAIL] §6-6" in r.stdout
    assert "key set mismatch" in r.stdout            # fail-loud 原文可见
