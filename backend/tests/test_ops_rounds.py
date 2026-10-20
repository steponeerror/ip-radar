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


# 假 agent(python 解释器形态):FAKE_MODE = success|sleep|usage|garbage|multiline|
# failure;FAKE_OUT 落 argv+env 快照;FAKE_PKG 模拟「包已落盘」的失败面。
FAKE_AGENT_PY = r"""
import json, os, sys, time
mode = os.environ.get("FAKE_MODE", "success")
out = os.environ.get("FAKE_OUT")
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
    pkg = os.environ.get("FAKE_PKG")
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
    """假 agent 落 tmp + IP_RADAR_OPS_AGENT_CMD 指向它;返回 (script, dump_path)。"""
    script = tmp_path / "fake-agent.py"
    script.write_text(FAKE_AGENT_PY, encoding="utf-8")
    dump = tmp_path / "child-dump.json"
    monkeypatch.setenv("IP_RADAR_OPS_AGENT_CMD",
                       f"{sys.executable} {script}")
    monkeypatch.setenv("FAKE_OUT", str(dump))
    return script, dump


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


def test_spawn_failure_envelope_ledger_keeps_pkg(rounds, ops_env, fake_agent, monkeypatch):
    """失败信封:code/pkg 落台账(轮次失败≠工件灭失,规格 §3);包文件原样在盘。"""
    pkg = ops_env / "ops" / "packages" / "2026-10-20-health-fake.md"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FAKE_MODE", "failure")
    monkeypatch.setenv("FAKE_PKG", str(pkg))
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == FAILURE_CODES_SAMPLE
    assert result["pkg"] == str(pkg)
    assert pkg.read_text(encoding="utf-8") == "# fake pkg"  # 不灭失
    ledger = _ledger_text(ops_env)
    assert "closure_check" in ledger, "失败信封 code 必须落台账"
    assert str(pkg) in ledger, "失败信封 pkg 必须落台账"


def test_spawn_usage_error_exit2_maps_infra(rounds, ops_env, fake_agent, monkeypatch):
    """exit 2 = 用法错(纯 stderr 无 JSON,契约面)→ 桥侧 infra 兜底 + 台账。"""
    monkeypatch.setenv("FAKE_MODE", "usage")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"
    assert "closure_check" not in _ledger_text(ops_env)
    assert "infra" in _ledger_text(ops_env)


def test_spawn_garbage_stdout_maps_infra(rounds, ops_env, fake_agent, monkeypatch):
    """rc=1 但 stdout 非 JSON → infra 兜底信封 + 台账(不静默丢弃)。"""
    monkeypatch.setenv("FAKE_MODE", "garbage")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"
    assert "infra" in _ledger_text(ops_env)


def test_spawn_multiline_stdout_is_contract_violation(rounds, ops_env, fake_agent, monkeypatch):
    """stdout 必须单行 JSON(GLOSSARY「轮次信封」):多行 = 契约违背 → infra。"""
    monkeypatch.setenv("FAKE_MODE", "multiline")
    result = rounds.spawn_round("health", "输入")
    assert result["ok"] is False
    assert result["error"]["code"] == "infra"


def test_spawn_streams_stderr_to_on_log(rounds, ops_env, fake_agent):
    """stderr 进度行逐行透传回调(→ 任务链 SSE;[turn]/[tool] 行是契约面)。"""
    logs = []
    result = rounds.spawn_round("health", "输入", on_log=logs.append)
    assert result["ok"] is True
    assert logs == ["[turn 1] fake progress"]


def test_spawn_cancelled_token_terminates_child(rounds, ops_env, fake_agent, monkeypatch):
    """admin 取消(经任务链 cancel 路由的 CancelToken)→ 子进程终止、cancelled 面
    + 台账行(九裁决 9:取消的轮次也可能已花真钱,必须留痕)。"""
    from ipdb._sources._download import CancelToken
    monkeypatch.setenv("FAKE_MODE", "sleep")
    token = CancelToken()
    token.cancel()
    t0 = time.monotonic()
    result = rounds.spawn_round("health", "输入", cancel_token=token)
    assert result.get("cancelled") is True
    assert time.monotonic() - t0 < 20  # 未陪跑满 30s sleep = 真被终止
    assert "取消" in _ledger_text(ops_env)


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
    """路由测试面:ops 树 + 假 agent + admin 认证(惰性,不污染非路由测试)。"""
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


def test_rounds_route_busy_round_409(admin_rounds_env, client_as_admin, monkeypatch):
    """ops 轮在飞(sleep 假 agent)→ 第二发 409 eval_busy(一轮一车道)。"""
    import main
    monkeypatch.setenv("FAKE_MODE", "sleep")
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
        admin_rounds_env, ops_env, client_as_admin, monkeypatch):
    """失败信封 → 任务 failed 且 error_code = 信封 code(九词闭集透传)+
    台账行;包不灭失。"""
    import main
    pkg = ops_env / "ops" / "packages" / "2026-10-20-health-route-fake.md"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FAKE_MODE", "failure")
    monkeypatch.setenv("FAKE_PKG", str(pkg))
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
