"""P2 轮次端点 + agent 桥(票 #134,TDD 红先行)。

钉住产品化批 Task P2 契约(docs/superpowers/plans/2026-10-19-ops-agent-productization.md
+ 票 #134 验收标准;期望值取自冻结件独立真源 GLOSSARY「spawn 契约」「轮次信封」与
ops/agent/agent.mjs,不从被测模块导入常量,防套套逻辑):

- POST /api/ops/rounds {type: health|discover, input}:admin 鉴权(匿名 401/非超管 403);
- 串行车道(裁①闸二):源更新任务在飞(queued/downloading/loading/throttled)→
  409 eval_busy 拒绝;ops 轮在飞 → 409;ops 轮期间源任务 worker 停摆(真互斥,
  964MB 小机 OOM 前科);ops 轮 running 态不计入 has_active_offline_tasks
  (查询门无扰,冷启动验收 1「公网查询无扰」);
- spawn 契约:argv = node --max-old-space-size=256 ops/agent/agent.mjs <round> <input>
  (内存围栏裁⑥,参数钉在拉起层);env 注入 ops 树落位(裁④:$IP_RADAR_DATA_DIR/ops
  一个根,经 DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE 三名传导)+ 求值 CLI(OPS_EVAL_PY/
  OPS_DATA_DIR)+ zai key(裁⑤:effective env 注入子进程,绝不写盘)+ OPS_* 围栏
  透传(裁①闸二:探针键量上限 operator 可调,子进程可见);stdout 单行 JSON 轮次信封
  解析(成功/失败同形;exit 0/1/2);stderr 进度行透传回调(→任务链 SSE);
- 失败信封路径:error.code/pkg 落台账(规格 §3 轮次失败≠工件灭失);exit 2(用法错,
  无 JSON)/非单行 stdout = 契约违背 → infra 兜底信封 + 台账;admin 取消 → cancelled
  + 台账行(花过真钱的轮次必须入账,九裁决 9);
- 探针超线降级(裁①闸三):降级人裁区语义在 agent 侧冻结面(tools.mjs 体量信封);
  桥的钉法 = OPS_PROBE_MAX_KEYS 围栏透传 + 一切 ok=false 信封落台账不静默丢弃。

子代理解释器形态伪桩:单测用 python 假 agent(IP_RADAR_OPS_AGENT_CMD 覆盖;真 argv
形状由纯函数测试钉死)——后端 CI runner 无 node,e2e 真跑(node+zai 凭证)单列
test_ops_rounds_e2e.py。
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

# ── 冻结件期望值(独立真源,逐字)──
# spawn 契约 argv(GLOSSARY「spawn 契约」+ 计划书 P2:--max-old-space-size=256 围栏)
DEFAULT_AGENT_CMD = ["node", "--max-old-space-size=256", "ops/agent/agent.mjs"]
# 轮次信封失败面 error.code 九词闭集(agent.mjs ERROR_CODES,此处只用到子集)
FAILURE_CODES_SAMPLE = "closure_check"


@pytest.fixture
def rounds():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误;P1 同型)。"""
    import ipdb._ops_rounds as ops_rounds
    return ops_rounds


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp + zai key/围栏注入面:IP_RADAR_DATA_DIR 指隔离目录。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAI_CODING_CN_API_KEY", "zai-secret-key-1234")
    monkeypatch.setenv("OPS_PROBE_MAX_KEYS", "424242")
    return tmp_path


# 假 agent(python 解释器形态):mode = success|sleep|usage|garbage|multiline|failure;
# out 落 argv+env 快照;pkg 模拟「包已落盘」的失败面。驱动参数走同目录
# fake-agent-cfg.json 而非 env(#196 C4 前置:spawn env 即将收白名单,测试钩子
# 不得依赖 os.environ 继承进子进程)。
FAKE_AGENT_PY = r"""
import json, os, sys, time
cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "fake-agent-cfg.json"), encoding="utf-8"))
mode = cfg.get("mode", "success")
out = cfg.get("out")
if out:
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"argv": sys.argv[1:], "env": dict(os.environ)}, f)
print("[turn 1] fake progress", file=sys.stderr)
if mode == "sleep":
    time.sleep(30)
    sys.exit(0)
if mode == "usage":
    print("usage: node agent.mjs <round> <input>", file=sys.stderr)
    sys.exit(2)
if mode == "garbage":
    print("not-json")
    sys.exit(1)
if mode == "multiline":
    print("leading noise")
    print(json.dumps({"ok": True, "round": sys.argv[1]}))
    sys.exit(0)
if mode == "failure":
    pkg = cfg.get("pkg")
    if pkg:
        with open(pkg, "w", encoding="utf-8") as f:
            f.write("# fake pkg")
    env = {"ok": False, "round": sys.argv[1],
           "error": {"code": "closure_check", "message": "fake failure"}}
    if pkg:
        env["pkg"] = pkg
    print(json.dumps(env))
    sys.exit(1)
print(json.dumps({"ok": True, "round": sys.argv[1], "pkg": "/tmp/fake-pkg.md",
                  "usage": {"input": 10, "output": 5, "totalTokens": 15, "cost": 0.001},
                  "queue_writes": [], "verify": {"ok": True, "cited": 0}}))
sys.exit(0)
"""


@pytest.fixture
def fake_agent(tmp_path, monkeypatch):
    """假 agent 落 tmp + IP_RADAR_OPS_AGENT_CMD 指向它;返回 (script, dump_path)。
    模式/驱动参数走 _fake_agent_set(cfg 文件),不经 env 继承(#196 C4 前置)。"""
    script = tmp_path / "fake-agent.py"
    script.write_text(FAKE_AGENT_PY, encoding="utf-8")
    dump = tmp_path / "child-dump.json"
    (tmp_path / "fake-agent-cfg.json").write_text(
        json.dumps({"mode": "success", "out": str(dump), "pkg": None}),
        encoding="utf-8")
    monkeypatch.setenv("IP_RADAR_OPS_AGENT_CMD",
                       f"{sys.executable} {script}")
    return script, dump


def _fake_agent_set(script: Path, mode: str, pkg=None) -> None:
    """切换假 agent 模式(改写同目录 cfg;pkg 传 str 路径时写入驱动面)。
    独立于 env 继承——spawn env 白名单落地后子进程只见契约面。"""
    cfg_path = script.parent / "fake-agent-cfg.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["mode"] = mode
    if pkg is not None:
        cfg["pkg"] = str(pkg)
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")


def _read_dump(dump_path: Path) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if dump_path.exists():
            return json.loads(dump_path.read_text(encoding="utf-8"))
        time.sleep(0.02)
    raise AssertionError("假 agent 未落 env 快照(子进程未起?)")


def _ledger_text(tmp_path: Path) -> str:
    p = tmp_path / "ops" / "ledger.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── P5 #167 boot 恢复扫描(C稿 §4.6;三规则实施在 pipeline.mjs resume,本面=准入裁决)──


def _write_state(ops_env, round_id, *, status="in_flight", stage="TRIAGE",
                 resume_count=0, updated_at="2026-10-24T04:05:00.000Z",
                 **over):
    import json as _json
    d = ops_env / "ops" / "rounds" / round_id
    d.mkdir(parents=True, exist_ok=True)
    state = {"schema": 1, "round_id": round_id, "type": "health",
             "status": status, "stage": stage, "stages": [],
             "budget_cny": 0.05, "resume_count": resume_count,
             "updated_at": updated_at, **over}
    (d / "state.json").write_text(
        _json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return d


def test_scan_inflight_classifies_actions(rounds, ops_env):
    """纯读扫描分类:resume / fail_stale(>16h)/ fail_twice(resume_count≥1)/
    重放目录(-rN)与终态轮不入清单;updated_at 不可解析按 stale(不赌陈旧态)。"""
    from datetime import datetime, timezone
    now = datetime(2026, 10, 24, 20, 0, 0, tzinfo=timezone.utc)
    _write_state(ops_env, "2026-10-24-0400-health")                     # 龄 16h→15h58m,resume
    _write_state(ops_env, "2026-10-23-0400-health",
                 updated_at="2026-10-23T04:05:00.000Z")              # 龄 ~40h,fail_stale
    _write_state(ops_env, "2026-10-24-1200-health", resume_count=1)     # 二次崩溃
    _write_state(ops_env, "2026-10-24-0400-health-r1")                  # 重放目录:忽略
    _write_state(ops_env, "2026-10-22-0400-health", status="done", stage="CLOSE")
    bad = ops_env / "ops" / "rounds" / "2026-10-24-0800-health"
    bad.mkdir(parents=True)
    (bad / "state.json").write_text("{not json", encoding="utf-8")
    rows = {r["round_id"]: r["action"] for r in rounds.scan_inflight_rounds(now)}
    assert rows["2026-10-24-0400-health"] == "resume"
    assert rows["2026-10-23-0400-health"] == "fail_stale"
    assert rows["2026-10-24-1200-health"] == "fail_twice"
    assert rows["2026-10-24-0800-health"] == "skip_unreadable"
    assert "2026-10-24-0400-health-r1" not in rows
    assert "2026-10-22-0400-health" not in rows


def test_recover_marks_failed_states_and_ledger(rounds, ops_env):
    """stale/twice → state 就地终态化(failed/FAILED/boot_marked 留痕)+ 台账行带
    replay 提示(交人);resume 无 manager 时不拉起(轮保持 in_flight 待产线接线)。"""
    import json as _json
    from datetime import datetime, timedelta, timezone
    _now = datetime.now(timezone.utc)
    stale_dir = _write_state(
        ops_env, "2026-10-23-0400-health",
        updated_at=(_now - timedelta(hours=17)).isoformat())   # 龄 17h>16h:不赌真实钟面
    twice_dir = _write_state(ops_env, "2026-10-24-1200-health", resume_count=1,
                             updated_at=_now.isoformat())   # 新鲜+resume_count≥1:fail_twice
    live_dir = _write_state(ops_env, "2026-10-24-1900-health",
                           updated_at=_now.isoformat())   # 新鲜 in_flight:不动(钟面相对化,防时间炸弹)
    handled = rounds.recover_inflight_rounds()   # manager=None:resume 档不拉起
    by = {h["round_id"]: h for h in handled}
    assert by["2026-10-23-0400-health"]["done"] is True
    assert by["2026-10-24-1200-health"]["done"] is True
    for d, frag in ((stale_dir, "stale"), (twice_dir, "自动恢复已用尽")):
        st = _json.loads((d / "state.json").read_text(encoding="utf-8"))
        assert st["status"] == "failed" and st["stage"] == "FAILED"
        assert st["boot_marked"]["code"] == "infra"
        assert frag in st["boot_marked"]["reason"]
    led = _ledger_text(ops_env)
    assert led.count("boot 恢复:") == 2
    assert "replay 2026-10-23-0400-health" in led   # 台账 replay 提示(交人)
    live = _json.loads((live_dir / "state.json").read_text(encoding="utf-8"))
    assert live["status"] == "in_flight"            # 无 manager 不动活轮


class _FakeManager:
    """恢复轮线程入口的 manager 替身(车道占用/ops_log/收口三面)。"""

    def __init__(self, busy=None):
        self.busy = busy
        self.logs = []
        self.finished = []

    def start_ops_round(self, round_type):
        if self.busy:
            return None, self.busy
        self.task_id = f"t{len(self.finished)}"
        return type("T", (), {"id": self.task_id})(), None

    def ops_log(self, task_id, line):
        self.logs.append((task_id, line))

    def finish_ops_round(self, task_id, state, error=None, error_code=None):
        self.finished.append((task_id, state, error, error_code))


def test_recovery_round_occupies_lane_and_settles(rounds, ops_env, monkeypatch):
    """恢复轮与手动/cron 轮同一互斥面:占车道 → resume spawn(stderr 进 ops_log)→
    收口 done;失败信封 → failed(error_code 透传)。"""
    _write_state(ops_env, "2026-10-24-1900-health")
    envelopes = [
        {"ok": True, "round": "health"},
        {"ok": False, "round": "health",
         "error": {"code": "model_face", "message": "TRIAGE 重试尽"}},
    ]

    def fake_spawn(round_id, *, on_log=None, env=None):
        assert round_id == "2026-10-24-1900-health"
        assert on_log is not None
        on_log("[stage] TRIAGE start")
        return envelopes.pop(0)

    monkeypatch.setattr(rounds, "_spawn_resume", fake_spawn)
    for want, code in (("done", None), ("failed", "model_face")):
        mgr = _FakeManager()
        rounds._run_recovery_round(mgr, "2026-10-24-1900-health")
        assert mgr.finished == [(mgr.task_id, want, None if want == "done" else "TRIAGE 重试尽", code)]
        assert mgr.logs and mgr.logs[0][1] == "[stage] TRIAGE start"

    mgr_busy = _FakeManager(busy="round")
    rounds._run_recovery_round(mgr_busy, "2026-10-24-1900-health")
    assert mgr_busy.finished == []       # 车道忙:不拉起,轮留待下次启动


def test_recover_dispatches_resume_thread(rounds, ops_env, monkeypatch):
    """resume 档 → 后台线程拉起 _run_recovery_round(recover 编排面);扫描面零异常总兜底。"""
    import json as _json
    from datetime import datetime, timezone
    calls = []

    class _T:
        def __init__(self, target=None, args=(), **_kw):
            self.target, self.args = target, args

        def start(self):
            calls.append(self.args)

    _write_state(ops_env, "2026-10-24-1900-health",
                 updated_at=datetime.now(timezone.utc).isoformat())   # 新鲜:resume 档(钟面相对化,防时间炸弹)
    monkeypatch.setattr(rounds.threading, "Thread", _T)
    handled = rounds.recover_inflight_rounds(manager="mgr")
    assert calls == [("mgr", "2026-10-24-1900-health")]
    assert handled[0]["done"] is True


# ── B4. #196 C1:轮次线程兜底(链上异常也落终态+放车道,不停摆源 worker)──


def test_run_round_crash_settles_task_and_frees_lane(
        rounds, ops_env, fake_agent, monkeypatch):
    """C1 兑底(#196):链上未捕获异常(磁盘满 OSError 注入 append_ledger)不得
    撕线程——ops task 落 failed 终态、_ops_active 清空、车道可再占(源 worker
    车道不停摆至容器重启);失败原因照实进 task error,不吞异常信息。"""
    _fake_agent_set(fake_agent[0], "failure")  # 失败信封路径 → spawn_round 内 append_ledger

    def disk_full(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(rounds._ops_store, "append_ledger", disk_full)
    mgr = _make_manager([])
    task, busy = mgr.start_ops_round("health")
    assert task is not None and busy is None
    t = threading.Thread(target=rounds.run_round,
                         args=(mgr, task, "health", "体检输入"), daemon=True)
    t.start()
    t.join(timeout=15)
    assert not t.is_alive(), "run_round 线程必须收口退出,不得死挂"
    snap = {row["id"]: row for row in mgr.snapshot()["tasks"]}
    assert snap[task.id]["state"] == "failed"
    assert snap[task.id]["error_code"] == "infra"
    assert "No space left on device" in (snap[task.id].get("error") or "")
    assert mgr._ops_active is None, "车道必须释放(_ops_active 清空)"
    again, again_busy = mgr.start_ops_round("health")  # 车道可再占 = 源 worker 不停摆
    assert again is not None and again_busy is None
    mgr.finish_ops_round(again.id, "done")


def test_recovery_round_crash_settles_task(rounds, ops_env, monkeypatch):
    """C1 兑底(#196):boot 恢复轮线程同面——_spawn_resume 抛 OSError → 任务落
    failed/infra 终态,原因照实透出且留 task_log 痕,不静默不裸抛。"""
    def disk_full(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(rounds, "_spawn_resume", disk_full)
    mgr = _FakeManager()
    rounds._run_recovery_round(mgr, "2026-10-24-1900-health")
    assert len(mgr.finished) == 1
    task_id, state, error, code = mgr.finished[0]
    assert state == "failed" and code == "infra"
    assert "No space left on device" in error
    assert mgr.logs, "兑底路径留痕 task_log(不吞异常信息)"


# ── #139 挂账①:轮次内存峰值(cgroup 读数三态 + run_round 收口面台账行)──


def test_read_memory_peak_cgroup_v2(rounds, tmp_path, monkeypatch):
    """cgroup v2 可读:memory.peak(P5 容器内即容器峰值高水位)。"""
    v2 = tmp_path / "cgroup2" / "memory.peak"
    v2.parent.mkdir()
    v2.write_text("838860800\n", encoding="utf-8")
    monkeypatch.setattr(rounds, "_CGROUP_V2_PEAK", v2)
    monkeypatch.setattr(rounds, "_CGROUP_V1_PEAK", tmp_path / "cgroup1" / "nope")
    assert rounds.read_memory_peak() == 838860800


def test_read_memory_peak_cgroup_v1_fallback(rounds, tmp_path, monkeypatch):
    """v2 不可读 → 回退 cgroup v1 memory.max_usage_in_bytes(旧内核容器)。"""
    v1 = tmp_path / "cgroup1" / "memory" / "memory.max_usage_in_bytes"
    v1.parent.mkdir(parents=True)
    v1.write_text("1048576\n", encoding="utf-8")
    monkeypatch.setattr(rounds, "_CGROUP_V2_PEAK", tmp_path / "cgroup2" / "nope")
    monkeypatch.setattr(rounds, "_CGROUP_V1_PEAK", v1)
    assert rounds.read_memory_peak() == 1048576


def test_read_memory_peak_absent_returns_none(rounds, tmp_path, monkeypatch):
    """两代路径皆不可读(开发机裸机无 cgroup/无权限)→ None 不抛:
    缺读数≠零用量,绝不虚构(测量建言/宁少算)。"""
    monkeypatch.setattr(rounds, "_CGROUP_V2_PEAK", tmp_path / "cgroup2" / "nope")
    monkeypatch.setattr(rounds, "_CGROUP_V1_PEAK", tmp_path / "cgroup1" / "nope")
    assert rounds.read_memory_peak() is None


# ── A. argv 契约(纯函数;真 node 命令形状)──────────────────────────────────


def test_default_agent_argv_shape(rounds):
    """缺省命令 = node --max-old-space-size=256 ops/agent/agent.mjs <round> <input>
    (spawn 契约 argv;围栏参数钉在拉起层,裁⑥)。"""
    argv = rounds._agent_argv("health", "体检输入")
    assert argv == DEFAULT_AGENT_CMD + ["health", "体检输入"]


def test_agent_cmd_env_override_split(rounds, monkeypatch, tmp_path):
    """IP_RADAR_OPS_AGENT_CMD 覆盖(测试/P5 部署形态 seam):shlex 切分。"""
    monkeypatch.setenv("IP_RADAR_OPS_AGENT_CMD", f"{sys.executable} {tmp_path / 'a.py'}")
    argv = rounds._agent_argv("discover", "x")
    assert argv[:2] == [sys.executable, str(tmp_path / "a.py")]
    assert argv[2:] == ["discover", "x"]


# ── B. spawn 层(假 agent;围栏/env/信封/台账/取消)──────────────────────────


def test_spawn_env_injects_ops_tree_and_fences(rounds, ops_env, fake_agent):
    """env 注入:ops 树三名(DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE 指向
    $IP_RADAR_DATA_DIR/ops 树,裁④)+ 求值 CLI(OPS_EVAL_PY/OPS_DATA_DIR)+
    zai key(裁⑤ env-only)+ OPS_PROBE_MAX_KEYS 围栏透传(裁①闸二)。"""
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    root = ops_env / "ops"
    assert dump["env"]["DOCS_ROOT"] == str(ops_env)
    assert dump["env"]["PRECEDENTS_DIR"] == str(root / "precedents")
    assert dump["env"]["LEDGER_FILE"] == str(root / "ledger.md")
    assert dump["env"]["OPS_EVAL_PY"] == sys.executable
    assert Path(dump["env"]["OPS_DATA_DIR"]).is_absolute()
    assert dump["env"]["ZAI_CODING_CN_API_KEY"] == "zai-secret-key-1234"
    assert dump["env"]["OPS_PROBE_MAX_KEYS"] == "424242"
    # argv 尾部 = <round> <input>(命令体被覆盖,参数面不变)
    assert dump["argv"][-2:] == ["health", "输入"]


# C4(#196)spawn env 白名单面(独立真源硬编码,不从被测模块导入——防套套逻辑):
# 契约单源 = ops/agent/agent.mjs SPAWN_CONTRACT_ENV(OPS_*/PI_* 前缀 + 精确名)
# + 运行必需(PATH/HOME/TMPDIR/IP_RADAR_DATA_DIR)。IP_RADAR_ALERT_URLS 是
# #184 finding webhook 出口契约员(与 backend _alerts.push 双消费面),保留透传。
SPAWN_ENV_EXACT = {"PATH", "HOME", "TMPDIR", "GH_TOKEN",
                   "IP_RADAR_DATA_DIR", "IP_RADAR_ALERT_URLS",
                   "ZAI_CODING_CN_API_KEY", "JINA_API_KEY",
                   "DOCS_ROOT", "PRECEDENTS_DIR", "LEDGER_FILE"}


def test_spawn_env_allowlist_excludes_secrets(
        rounds, ops_env, fake_agent, monkeypatch):
    """C4(#196):子进程 env = 显式白名单(契约面),全量继承废止——仓外密钥
    (ADMIN_PASSWORD/JWT_SECRET 等)绝不透传子进程(least-privilege)。"""
    monkeypatch.setenv("ADMIN_PASSWORD", "boot-admin-pass-xyz")
    monkeypatch.setenv("JWT_SECRET", "boot-jwt-secret-xyz")
    monkeypatch.setenv("SOME_RANDOM_SECRET", "not-in-contract")
    rounds.spawn_round("health", "输入")
    env = _read_dump(fake_agent[1])["env"]
    for k in ("ADMIN_PASSWORD", "JWT_SECRET", "SOME_RANDOM_SECRET"):
        assert k not in env, f"契约外 env {k} 透传子进程"
    assert env["DOCS_ROOT"] == str(ops_env)              # 桥注入面在场
    assert env["ZAI_CODING_CN_API_KEY"] == "zai-secret-key-1234"


def test_spawn_env_exactly_contract_face(
        rounds, ops_env, fake_agent, monkeypatch):
    """C4(#196):子进程 env 键集恰为白名单面(前缀 OPS_/PI_ + 精确名集),
    契约外一概不透传;契约员 GH_TOKEN 保留(gh CLI 自读)。"""
    monkeypatch.setenv("GH_TOKEN", "gh-contract-token-1")
    rounds.spawn_round("health", "输入")
    env = _read_dump(fake_agent[1])["env"]
    env.pop("LC_CTYPE", None)  # python 假 agent PEP 538 locale 强注(C.UTF-8)非桥透传面;真实 node agent 无此注入
    assert env["GH_TOKEN"] == "gh-contract-token-1"      # 契约员透传
    extra = [k for k in env if k not in SPAWN_ENV_EXACT
             and not (k.startswith("OPS_") or k.startswith("PI_"))]
    assert extra == [], f"白名单外 env 透传子进程: {extra}"


def test_round_env_secret_files_0600(rounds, ops_env, fake_agent):
    """C4 附带(#196):物化密钥件(auth.json/web-search.json)权限 0600——
    mkstemp 面已隐式满足,显式钉住契约防实现漂移(arch 评审 C4 附带项)。"""
    _plant_agent_config(ops_env, {"api_keys": {"zai-coding-cn": "sk-zai-1"},
                                  "tool_keys": {"jina": "jina-key-1"}})
    rounds.spawn_round("health", "输入")
    for name in ("auth.json", "web-search.json"):
        mode = (ops_env / "ops" / name).stat().st_mode & 0o777
        assert mode == 0o600, f"{name} 权限 {oct(mode)} ≠ 0600"


def test_spawn_success_envelope_roundtrip(rounds, ops_env, fake_agent):
    """成功信封逐字段透传;桥不追加台账行(agent 侧 lib.sh 自记,双记=回声);
    树形状初始化幂等建头(裁④),但零数据行。"""
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is True
    assert result["round"] == "health"
    assert result["usage"] == {"input": 10, "output": 5, "totalTokens": 15, "cost": 0.001}
    ledger = _ledger_text(ops_env)
    assert not any(ln.startswith("| 2") for ln in ledger.splitlines()), \
        ledger  # 桥零追加(表头可有可无,数据行必无)


def test_spawn_failure_envelope_ledger_keeps_pkg(rounds, ops_env, fake_agent):
    """失败信封:code/pkg 落台账(轮次失败≠工件灭失,规格 §3);包文件原样在盘。"""
    pkg = ops_env / "ops" / "packages" / "2026-10-20-health-fake.md"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    _fake_agent_set(fake_agent[0], "failure", pkg=pkg)
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == FAILURE_CODES_SAMPLE
    assert result["pkg"] == str(pkg)
    assert pkg.read_text(encoding="utf-8") == "# fake pkg"  # 不灭失
    ledger = _ledger_text(ops_env)
    assert "closure_check" in ledger, "失败信封 code 必须落台账"
    assert str(pkg) in ledger, "失败信封 pkg 必须落台账"


def test_spawn_usage_error_exit2_maps_infra(rounds, ops_env, fake_agent):
    """exit 2 = 用法错(纯 stderr 无 JSON,契约面)→ 桥侧 infra 兜底 + 台账。"""
    _fake_agent_set(fake_agent[0], "usage")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"
    assert "closure_check" not in _ledger_text(ops_env)
    assert "infra" in _ledger_text(ops_env)


def test_spawn_garbage_stdout_maps_infra(rounds, ops_env, fake_agent):
    """rc=1 但 stdout 非 JSON → infra 兜底信封 + 台账(不静默丢弃)。"""
    _fake_agent_set(fake_agent[0], "garbage")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"
    assert "infra" in _ledger_text(ops_env)


def test_spawn_multiline_stdout_is_contract_violation(rounds, ops_env, fake_agent):
    """stdout 必须单行 JSON(GLOSSARY「轮次信封」):多行 = 契约违背 → infra。"""
    _fake_agent_set(fake_agent[0], "multiline")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"


def test_spawn_streams_stderr_to_on_log(rounds, ops_env, fake_agent):
    """stderr 进度行逐行透传回调(→ 任务链 SSE;[turn]/[tool] 行是契约面)。"""
    logs = []
    result = rounds.spawn_round("health", "输入", on_log=logs.append)
    assert result["ok"] is True
    assert logs == ["[turn 1] fake progress"]


def test_spawn_cancelled_token_terminates_child(rounds, ops_env, fake_agent):
    """admin 取消(经任务链 cancel 路由的 CancelToken)→ 子进程终止、cancelled 面
    + 台账行(九裁决 9:取消的轮次也可能已花真钱,必须留痕)。"""
    from ipdb._sources._download import CancelToken
    _fake_agent_set(fake_agent[0], "sleep")
    token = CancelToken()
    token.cancel()
    t0 = time.monotonic()
    result = rounds.spawn_round("health", "输入", cancel_token=token)
    assert result.get("cancelled") is True
    assert time.monotonic() - t0 < 20  # 未陪跑满 30s sleep = 真被终止
    assert "取消" in _ledger_text(ops_env)


# ── B2. agent-config.json 注入(票 #140:配置优先,未配置回落 effective env;
# 每次 spawn 现读 = 改完即生效,无需重启)──────────────────────────────────


def _plant_agent_config(ops_env, cfg: dict) -> None:
    """直接落配置文件(独立于被测模块写入面的独立真源)。"""
    (ops_env / "ops").mkdir(parents=True, exist_ok=True)
    (ops_env / "ops" / "agent-config.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def test_spawn_env_injects_configured_models_and_key(rounds, ops_env, fake_agent):
    """配置三元注入:OPS_MODEL_HEALTH/OPS_MODEL_DISCOVER/ZAI_CODING_CN_API_KEY
    spawn 面可见配置值;key 配置优先于 env(ops_env fixture 已灌 env key)。"""
    _plant_agent_config(ops_env, {"model_health": "glm-4.6v",
                                  "model_discover": "glm-5.3-highspeed",
                                  "zai_api_key": "cfg-key-9999"})
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    assert dump["env"]["OPS_MODEL_HEALTH"] == "glm-4.6v"
    assert dump["env"]["OPS_MODEL_DISCOVER"] == "glm-5.3-highspeed"
    assert dump["env"]["ZAI_CODING_CN_API_KEY"] == "cfg-key-9999"  # 配置赢 env


def test_spawn_config_absent_falls_back_to_env(rounds, ops_env, fake_agent, monkeypatch):
    """未配置回落继承的 effective env:operator 灌的 OPS_MODEL_HEALTH 透传、
    zai key 吃 env 兜底链;未涉模型名不注入(models.mjs 缺省兜底)。"""
    monkeypatch.setenv("OPS_MODEL_HEALTH", "glm-5.3-flashx")
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    assert dump["env"]["OPS_MODEL_HEALTH"] == "glm-5.3-flashx"
    assert "OPS_MODEL_DISCOVER" not in dump["env"]  # 未配置不注入
    assert dump["env"]["ZAI_CODING_CN_API_KEY"] == "zai-secret-key-1234"  # env 兜底


def test_spawn_rereads_config_each_spawn(rounds, ops_env, fake_agent):
    """每次 spawn 现读:两轮之间改配置,第二轮即见新值(改完即生效)。"""
    _plant_agent_config(ops_env, {"model_health": "glm-5.3", "zai_api_key": "v1-key-1111"})
    rounds.spawn_round("health", "第一轮")
    first = _read_dump(fake_agent[1])
    fake_agent[1].unlink()
    _plant_agent_config(ops_env, {"model_health": "glm-5.3-flashx", "zai_api_key": "v2-key-2222"})
    rounds.spawn_round("health", "第二轮")
    second = _read_dump(fake_agent[1])
    assert first["env"]["OPS_MODEL_HEALTH"] == "glm-5.3"
    assert first["env"]["ZAI_CODING_CN_API_KEY"] == "v1-key-1111"
    assert second["env"]["OPS_MODEL_HEALTH"] == "glm-5.3-flashx"
    assert second["env"]["ZAI_CODING_CN_API_KEY"] == "v2-key-2222"


# ── B3. 多供应商注入面(票 #143:qualified 模型透传 + api_keys 物化 auth.json
# + OPS_AUTH 指它;ADR 0005 裁②)────────────────────────────────────


def test_spawn_env_qualified_models_pass_through(rounds, ops_env, fake_agent):
    """qualified 模型值(config 或 env)spawn 面逐字透传——provider 限定是值
    文法不是新 env 名(17 名 env 面不变)。"""
    _plant_agent_config(ops_env, {"model_health": "anthropic/claude-x"})
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    assert dump["env"]["OPS_MODEL_HEALTH"] == "anthropic/claude-x"


def test_spawn_materializes_merged_auth_json(rounds, ops_env, fake_agent):
    """api_keys 配置 → 每次 spawn 物化合并 auth.json 落 ops 树(pi auth.json
    同形 {providerId:{type:'api_key',key}}),OPS_AUTH 指它;旧 zai_api_key
    alias 同入;zai env 兜底链不动(ZAI env 仍注入,stored credential 优先)。"""
    _plant_agent_config(ops_env, {
        "api_keys": {"anthropic": "sk-ant-material-8888", "zai-coding-cn": "sk-zai-cfg-7777"}})
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    auth_path = ops_env / "ops" / "auth.json"
    assert dump["env"]["OPS_AUTH"] == str(auth_path)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    assert auth == {
        "anthropic": {"type": "api_key", "key": "sk-ant-material-8888"},
        "zai-coding-cn": {"type": "api_key", "key": "sk-zai-cfg-7777"}}
    assert dump["env"]["ZAI_CODING_CN_API_KEY"] == "sk-zai-cfg-7777"  # env 链不动


def test_spawn_materializes_legacy_zai_alias(rounds, ops_env, fake_agent):
    """仅旧 zai_api_key(无 api_keys)也物化 zai 家(兼容面等价)。"""
    _plant_agent_config(ops_env, {"zai_api_key": "sk-legacy-6666"})
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    auth = json.loads((ops_env / "ops" / "auth.json").read_text(encoding="utf-8"))
    assert auth["zai-coding-cn"]["key"] == "sk-legacy-6666"
    assert dump["env"]["OPS_AUTH"] == str(ops_env / "ops" / "auth.json")


def test_spawn_no_configured_keys_no_auth_materialization(rounds, ops_env, fake_agent):
    """零 key 配置 → 不物化不注入 OPS_AUTH(models.mjs 回落 ~/.pi/agent/auth.json
    /各家 env 链,#140 时期行为零回归);zai env 兜底仍注入。"""
    rounds.spawn_round("health", "输入")
    dump = _read_dump(fake_agent[1])
    assert "OPS_AUTH" not in dump["env"]
    assert not (ops_env / "ops" / "auth.json").exists()
    assert dump["env"]["ZAI_CODING_CN_API_KEY"] == "zai-secret-key-1234"  # env 兜底


def test_spawn_rematerializes_auth_on_key_change(rounds, ops_env, fake_agent):
    """两轮间改 key → 第二轮 auth.json 内容即新值(改完即生效,同模型面)。"""
    _plant_agent_config(ops_env, {"api_keys": {"anthropic": "sk-v1-1111"}})
    rounds.spawn_round("health", "第一轮")
    first = json.loads((ops_env / "ops" / "auth.json").read_text(encoding="utf-8"))
    _plant_agent_config(ops_env, {"api_keys": {"anthropic": "sk-v2-2222"}})
    rounds.spawn_round("health", "第二轮")
    second = json.loads((ops_env / "ops" / "auth.json").read_text(encoding="utf-8"))
    assert first["anthropic"]["key"] == "sk-v1-1111"
    assert second["anthropic"]["key"] == "sk-v2-2222"


def test_spawn_corrupt_config_maps_infra(rounds, ops_env, fake_agent):
    """坏配置文件 = 显式失败不静默:infra 兜底信封 + 台账行(消息不含 key 值)。"""
    (ops_env / "ops").mkdir(parents=True, exist_ok=True)
    (ops_env / "ops" / "agent-config.json").write_text("{broken", encoding="utf-8")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"
    assert "配置" in _ledger_text(ops_env)



# ── C. 串行车道(UpdateManager;FakeSource 模式沿 tests/core/test_tasks.py)──


class FakeSource:
    """阻塞型假源:download 挂到取消;rebuild/load 零动作。"""

    def __init__(self, name, host="h"):
        self.name = name
        self.download_host = host

    def download(self, token=None):
        from ipdb._sources._download import CancelledError
        while token is not None and not token.is_cancelled():
            time.sleep(0.05)
        if token is not None and token.is_cancelled():
            raise CancelledError()

    def load(self):
        pass

    def rebuild(self):
        pass


def _make_manager(sources):
    from ipdb._tasks import UpdateManager
    by_name = {s.name: s for s in sources}
    locks = {}

    def lock_for(n):
        locks.setdefault(n, threading.Lock())
        return locks[n]

    return UpdateManager(resolve_source=lambda n: by_name.get(n),
                         lock_for=lock_for, concurrency=2)


def _wait(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _drain_source_lane(mgr, timeout=15.0):
    """#171 order-fragile 自愈:进 lifespan 的核心测试(`with TestClient`,
    如 test_stream_pool/test_main_routes)会经 _startup_warm → enqueue_stale
    往单例 manager 塞真实源下载任务;有网开发机上大源分钟级在飞,本文件
    排后就见 busy=sources → 路由 409(CI 不可见双因:runner 无外网下载秒
    失败落 failed + core 按 per-file 跑序隔离)。路由测试钉的是「空闲车道」
    语义 → 进门先把滞留任务 cancel 到底。cancel 后 downloading 任务在下一
    chunk 边界收 CancelledError(download_file 逐 chunk 查 token),15s 远
    大于 chunk 间隔;loading 相位在途 rebuild 不可中断,超时则放行,由
    既有 409==202 断言给出清晰失败面(不劣于修前)。"""
    def _active():
        return [t for t in mgr.snapshot()["tasks"]
                if t["state"] in ("queued", "downloading", "loading",
                                   "throttled")]
    for t in _active():
        mgr.cancel(t["id"])
    return _wait(lambda: not _active(), timeout=timeout)


def test_ops_lane_rejected_while_source_task_active():
    """源任务 downloading 中 → 车道拒绝(reason=sources;409 语义的数据面)。"""
    mgr = _make_manager([FakeSource("a")])
    task = mgr.enqueue_one("a")
    try:
        assert _wait(lambda: any(
            t["state"] == "downloading" for t in mgr.snapshot()["tasks"]))
        got, reason = mgr.start_ops_round("health")
        assert got is None and reason == "sources"
    finally:
        mgr.cancel(task.id)


def test_ops_lane_rejected_while_round_active():
    """ops 轮在飞 → 车道拒绝(reason=round;一轮一车道,不排队不并发)。"""
    mgr = _make_manager([])
    task, reason = mgr.start_ops_round("health")
    assert task is not None and reason is None
    assert task.state == "running"
    again, reason2 = mgr.start_ops_round("discover")
    assert again is None and reason2 == "round"
    mgr.finish_ops_round(task.id, "done")


def test_ops_round_blocks_source_workers():
    """ops 轮期间源任务 worker 停摆(真互斥);finish 后放行(排队语义)。"""
    mgr = _make_manager([FakeSource("a")])
    task, _ = mgr.start_ops_round("health")
    try:
        queued = mgr.enqueue_one("a")
        time.sleep(0.6)  # 足够任何空闲 worker 抢跑(若互斥破)
        snap = {t["source"]: t["state"] for t in mgr.snapshot()["tasks"]}
        assert snap["a"] == "queued", "ops 轮在飞时源任务不得进入 downloading"
    finally:
        mgr.finish_ops_round(task.id, "done")
    assert _wait(lambda: any(
        t["state"] in ("downloading", "loading") for t in mgr.snapshot()["tasks"]
        if t["source"] == "a"), timeout=5), "ops 轮结束后源任务应放行"
    mgr.cancel(queued.id)


def test_ops_running_round_not_counted_by_cold_gate():
    """ops 轮 running 态不计入 has_active_offline_tasks(查询门无扰,冷启动验收 1)。"""
    mgr = _make_manager([])
    task, _ = mgr.start_ops_round("health")
    try:
        assert mgr.has_active_offline_tasks() is False
    finally:
        mgr.finish_ops_round(task.id, "done")


def test_ops_task_visible_in_snapshot_and_finish():
    """ops 任务进任务链快照(source=ops,running);finish 落终态并释放车道;
    下一轮 start 清扫上一终态 ops 任务(快照不随轮次累积)。"""
    mgr = _make_manager([])
    t1, _ = mgr.start_ops_round("health")
    snap = {t["source"]: t for t in mgr.snapshot()["tasks"]}
    assert snap["ops"]["state"] == "running"
    mgr.finish_ops_round(t1.id, "failed", error="boom", error_code="infra")
    snap = {t["source"]: t for t in mgr.snapshot()["tasks"]}
    assert snap["ops"]["state"] == "failed"
    assert snap["ops"]["error_code"] == "infra"
    t2, _ = mgr.start_ops_round("health")
    ops_rows = [t for t in mgr.snapshot()["tasks"] if t["source"] == "ops"]
    assert len(ops_rows) == 1, "终态 ops 任务应被下一轮清扫"
    mgr.finish_ops_round(t2.id, "done")


def test_ops_log_emits_task_log_event():
    """stderr 进度行 → 任务链事件总线(task_log 事件;SSE /api/events 原生转发)。"""
    mgr = _make_manager([])
    events = []
    orig = mgr._emit
    mgr._emit = events.append
    try:
        task, _ = mgr.start_ops_round("health")
        mgr.ops_log(task.id, "[turn 1] stopReason=tool_calls usage(in=100 out=5)")
        mgr.finish_ops_round(task.id, "done")
    finally:
        mgr._emit = orig
    logs = [e for e in events if e.get("type") == "task_log"]
    assert logs and logs[0]["task_id"] == task.id
    assert logs[0]["line"].startswith("[turn 1]")


# ── D. 路由层(鉴权/校验/202/409/失败面)────────────────────────────────────


@pytest.fixture
def admin_rounds_env(ops_env, fake_agent, auth_env):
    """路由测试面:ops 树 + 假 agent + admin 认证(惰性,不污染非路由测试);
    进门先清滞留源任务(#171,见 _drain_source_lane)——路由断言全部以
    空闲车道为前提。清不掉则 skip:残留只可能是 loading 相在途真实重建
    (cancel 语义=重建返回后生效,不可中断),这是测试环境串真加载的
    伪象而非产品行为,skip 掉不冒充通过;单跑/触发组合下车道能清空,
    测试照常执行(CI 无外网下载秒失败,永不 skip)。"""
    import main
    if not _drain_source_lane(main.manager):
        stuck = [f"{t['id']}:{t['state']}" for t in main.manager.snapshot()["tasks"]
                 if t["state"] in ("queued", "downloading", "loading", "throttled")]
        pytest.skip(
            "#171 全量序伪象:早期 lifespan 测试串入的真实源重建仍在 loading 相"
            f"(cancel 不可中断),串行车道无法消凑出空闲前提 → {stuck}")
    return ops_env


def _post_rounds(client, body):
    return client.post("/api/ops/rounds", json=body)


def test_rounds_route_requires_admin(admin_rounds_env, auth_client):
    r = _post_rounds(auth_client, {"type": "health", "input": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_rounds_route_forbidden_for_non_superuser(admin_rounds_env, auth_client):
    import asyncio
    from fastapi_users.password import PasswordHelper
    from ipdb import _auth

    async def _mk_peon():
        async with _auth._session_maker()() as s:
            s.add(_auth.User(email="peon@ipradar.local",
                             hashed_password=PasswordHelper().hash("peon-pass-123"),
                             is_superuser=False, is_active=True))
            await s.commit()

    asyncio.run(_mk_peon())
    assert auth_client.post("/api/auth/jwt/login", data={
        "username": "peon@ipradar.local", "password": "peon-pass-123"}).status_code == 204
    r = _post_rounds(auth_client, {"type": "health", "input": "x"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("body", [
    {"type": "audit", "input": "x"},          # type 闭集外
    {"type": "health", "input": ""},          # 空输入
    {"type": "health"},                       # 缺 input
    {"input": "x"},                           # 缺 type
])
def test_rounds_route_validates_body(admin_rounds_env, client_as_admin, body):
    r = _post_rounds(client_as_admin, body)
    assert r.status_code == 422


def test_rounds_route_accepts_and_runs_to_done(admin_rounds_env, ops_env,
                                               client_as_admin):
    """202 + task_id;ops 树初始化(桥拉起前 init);假 agent 成功信封 → done;
    桥不追加台账行。"""
    r = _post_rounds(client_as_admin, {"type": "health", "input": "体检"})
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    import main
    assert _wait(lambda: any(
        t["id"] == task_id and t["state"] == "done"
        for t in main.manager.snapshot()["tasks"])), main.manager.snapshot()
    # ops 树形状就位(裁④:一个根;桥 init 幂等建目录+表头)
    assert (ops_env / "ops" / "precedents").is_dir()
    assert (ops_env / "ops" / "packages").is_dir()
    ledger = _ledger_text(ops_env)
    assert ledger.count("\n") == 4, "成功轮桥不追加台账行(只有表头)"


def test_rounds_route_busy_round_409(admin_rounds_env, fake_agent, client_as_admin):
    """ops 轮在飞(sleep 假 agent)→ 第二发 409 eval_busy(一轮一车道)。"""
    import main
    _fake_agent_set(fake_agent[0], "sleep")
    r1 = _post_rounds(client_as_admin, {"type": "health", "input": "x"})
    assert r1.status_code == 202
    task_id = r1.json()["task_id"]
    try:
        r2 = _post_rounds(client_as_admin, {"type": "health", "input": "y"})
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "eval_busy"
    finally:
        main.manager.cancel(task_id)
        assert _wait(lambda: any(
            t["id"] == task_id and t["state"] in ("cancelled", "done", "failed")
            for t in main.manager.snapshot()["tasks"]))


def test_rounds_route_busy_sources_409(admin_rounds_env, client_as_admin, monkeypatch):
    """源更新任务在飞 → 409 eval_busy(串行互斥的 HTTP 面)。"""
    import main
    from ipdb import _registry
    fake = FakeSource("fakeroundsrc")
    monkeypatch.setattr(_registry, "_sources", [fake])
    task = main.manager.enqueue_one("fakeroundsrc")
    try:
        assert _wait(lambda: any(
            t["state"] == "downloading" for t in main.manager.snapshot()["tasks"]))
        r = _post_rounds(client_as_admin, {"type": "health", "input": "x"})
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "eval_busy"
    finally:
        main.manager.cancel(task.id)


def test_rounds_route_failure_envelope_marks_task_failed(
        admin_rounds_env, fake_agent, ops_env, client_as_admin):
    """失败信封 → 任务 failed 且 error_code = 信封 code(九词闭集透传)+
    台账行;包不灭失。"""
    import main
    pkg = ops_env / "ops" / "packages" / "2026-10-20-health-route-fake.md"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    _fake_agent_set(fake_agent[0], "failure", pkg=pkg)
    r = _post_rounds(client_as_admin, {"type": "health", "input": "x"})
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    assert _wait(lambda: any(
        t["id"] == task_id and t["state"] == "failed"
        for t in main.manager.snapshot()["tasks"]))
    row = next(t for t in main.manager.snapshot()["tasks"] if t["id"] == task_id)
    assert row["error_code"] == "closure_check"
    assert pkg.exists()
    ledger = _ledger_text(ops_env)
    assert "closure_check" in ledger and str(pkg) in ledger
