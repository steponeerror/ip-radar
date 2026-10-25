"""P2 轮次桥:任务链串行车道内 spawn 运营 agent CLI(票 #134)。

契约真源:主仓 GLOSSARY「spawn 契约」「轮次信封」+ ops/agent/agent.mjs
(SPAWN_CONTRACT_ENV 表,17 名 env 面唯一详述点);本模块是后端侧唯一消费方
(ops/agent 冻结面零触碰)。

- argv = node --max-old-space-size=256 ops/agent/agent.mjs <round> <input>
  (三层内存围栏第一层钉在拉起层,裁⑥;计划书 Global Constraints「一切子进程
  必须带资源围栏」——964MB 小机 OOM 前科);cwd = 仓根(部署形态相对路径);
- env 注入(桥侧归属名):ops 树落位三名(DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE
  → $IP_RADAR_DATA_DIR/ops 一个根,裁④,经 P1 _ops_store.ops_root 解析;agent
  侧派生 queue.md/artifacts 挂 DOCS_ROOT/ops/*,故 DOCS_ROOT 钉在 ops 根的父
  目录)+ 求值 CLI(OPS_EVAL_PY=本进程解释器、OPS_DATA_DIR=registry 数据面,
  exclusive_probe 复用产品同一 DB)+ 票 #140 配置面三元(OPS_MODEL_HEALTH/
  OPS_MODEL_DISCOVER/ZAI_CODING_CN_API_KEY:ops 树 agent-config.json 配置
  优先,未配置回落 effective env 兜底链,每次 spawn 现读改完即生效)——key
  绝不进日志(裁⑤);其余 OPS_* 围栏(OPS_PROBE_MAX_KEYS 等,
  裁①闸二)经 env 继承透传(operator 可调,spawn 层可见);
- stdout = 单行 JSON 轮次信封(成功/失败同形);exit 0=成功面 / 1=失败面 /
  2=用法错(纯 stderr 无 JSON);exit 2、非单行 stdout、rc×ok 组合非法 =
  契约违背 → infra 兜底信封;
- 一切失败面与 admin 取消落台账(_ops_store.append_ledger;轮次失败≠工件
  灭失,规格 §3;九裁决 9:取消的轮次也可能已花真钱,留痕);成功面桥零追加
  (agent 侧 lib.sh 自记真实 usage,双记=回声);
- stderr 进度行([turn]/[tool],契约面)逐行回调 on_log(run_ops_round 接任务链
  SSE 的 task_log 事件)。

测试/P5 部署 seam:IP_RADAR_OPS_AGENT_CMD 覆盖命令体(shlex 切分;参数面
<round> <input> 不变)——后端 CI runner 无 node,单测用 python 假 agent 真过
spawn 层;e2e 真跑(tests/test_ops_rounds_e2e.py)不设此值。
"""

import json
import logging
import os
import re as _re
import shlex
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import _ops_store

logger = logging.getLogger(__name__)

# spawn 契约 argv(GLOSSARY「spawn 契约」;--max-old-space-size=256 = 三层内存
# 围栏第一层,参数钉在拉起层——裁⑥)
_DEFAULT_AGENT_CMD = ["node", "--max-old-space-size=256", "ops/agent/agent.mjs"]

_REPO_ROOT = Path(__file__).resolve().parents[2]  # 仓根(agent CLI 的 cwd)
_STDERR_TAIL_CHARS = 300  # 失败面 stderr 尾部入错误消息(定位用,不倾倒)
_STDERR_KEEP_LINES = 20
# PR3a web_search(pi-web-access MCP)回退链:fallbackOn = 包的全部合法回退面
# (gemini-search.ts VALID_ROUTING_KINDS 闭集);duckduckgo keyless 起步、jina 可用性
# 门后置——选型 why 见 _round_env 注释(2026-10-24 裁定)。
_WEB_SEARCH_ROUTING = {
    "providers": ["duckduckgo", "jina"],
    "fallbackOn": ["transient", "quota", "network", "invalid-response", "unsupported"],
}


def _agent_argv(round_type: str, input_text: str) -> list[str]:
    """完整 argv = 命令体(契约缺省/IP_RADAR_OPS_AGENT_CMD 覆盖)+ <round> <input>。"""
    override = os.environ.get("IP_RADAR_OPS_AGENT_CMD", "").strip()
    cmd = shlex.split(override) if override else list(_DEFAULT_AGENT_CMD)
    return cmd + [round_type, input_text]


def _round_env() -> dict[str, str]:
    """桥侧注入的契约 env(其余 SPAWN_CONTRACT_ENV 名经继承透传)。

    票 #140:agent-config.json(ops 树,_ops_config)每次 spawn 现读——
    配置优先,未配置回落继承的 effective env(env 兜底链不动,override 灌
    key 语义保持);模型名未配置时不注入(继承透传 operator 的 OPS_MODEL_*,
    都无则 models.mjs 缺省)。改完即生效,无需重启。
    """
    from . import _registry  # 惰性导入:单测仅解析路径时不牵源发现链
    from . import _ops_config

    root = _ops_store.ops_root()
    cfg = _ops_config.read_config()
    env = {
        "DOCS_ROOT": str(root.parent),
        "PRECEDENTS_DIR": str(root / "precedents"),
        "LEDGER_FILE": str(root / "ledger.md"),
        "OPS_EVAL_PY": sys.executable,
        "OPS_DATA_DIR": str(_registry.DATA_DIR),
    }
    if cfg.get("model_health"):
        env["OPS_MODEL_HEALTH"] = cfg["model_health"]
    if cfg.get("model_discover"):
        env["OPS_MODEL_DISCOVER"] = cfg["model_discover"]
    # 票 #143(ADR 0005 裁②):配置面 key(api_keys + 旧 zai_api_key alias)→
    # 每次 spawn 物化合并 auth.json 落 ops 树(pi auth.json 同形),OPS_AUTH 指它
    # (models.mjs 读面 #143 起逐家);零 key 配置 → 不物化不注入(回落
    # ~/.pi/agent/auth.json / 各家 env 链,#140 行为零回归)。零硬闸:不在此设
    # 任何成本/供应商门(裁③)。
    keys = _ops_config.effective_keys()  # 配置面逐家(含旧 alias;不含 env)
    if keys:
        auth_path = root / "auth.json"
        _ops_store.atomic_write_text(auth_path, json.dumps(
            {pid: {"type": "api_key", "key": key} for pid, key in keys.items()},
            ensure_ascii=False, indent=2) + "\n")
        auth_path.chmod(0o600)  # C4 附带(#196):密钥件 0600 钉住契约(mkstemp 已隐式,防漂移)
        env["OPS_AUTH"] = str(auth_path)
    zai = keys.get("zai-coding-cn") \
        or os.environ.get("ZAI_CODING_CN_API_KEY", "").strip()
    if zai:
        env["ZAI_CODING_CN_API_KEY"] = zai  # zai env 兜底链不动(stored credential 优先)
    # PR3a 发现通道扩槽:tool_keys.jina(agent-config)→ JINA_API_KEY 注入
    # (web_search 的 jina provider 消费——pi-web-access 包自读 env;与
    # ZAI_CODING_CN_API_KEY 同型:配置优先,改完即生效;未配置不注入,
    # override 灌 env 经继承透传保持兜底链)。
    jina = (cfg.get("tool_keys") or {}).get("jina")
    if jina and jina.strip():
        env["JINA_API_KEY"] = jina.strip()
    # PR3a web_search 引擎 = pi-web-access MCP(2026-10-24 用户令「用 pi-web-access
    # 实现网络搜索」,https://pi.dev/packages/pi-web-access;pin 0.44.0)。provider 路由
    # 配置单源 web-search.json:物化进 ops 树 + PI_CODING_AGENT_DIR 指路(auth.json
    # 同型判例;包自读,tools.mjs 不读)。选型 why:显式回退链 duckduckgo(keyless,
    # isDuckDuckGoAvailable()≡true,零配置一发即活,离线确定性优先)→ jina(可用性
    # = jinaApiKey/JINA_API_KEY,充值/配置后自然入链);零配置 Exa MCP 需运行时拉起
    # 外部进程,不入链。每次 spawn 现读物化 = 改完即生效。
    web_cfg = {"searchRouting": dict(_WEB_SEARCH_ROUTING)}
    if env.get("JINA_API_KEY"):
        web_cfg["jinaApiKey"] = env["JINA_API_KEY"]  # 包的 web-search.json 键名(jinaApiKey)
    _ops_store.atomic_write_text(
        root / "web-search.json",
        json.dumps(web_cfg, ensure_ascii=False, indent=2) + "\n")
    (root / "web-search.json").chmod(0o600)  # C4 附带(#196):jinaApiKey 承载件 0600 钉住
    env["PI_CODING_AGENT_DIR"] = str(root)
    return env


# C4(#196)spawn env 白名单:契约单源 = ops/agent/agent.mjs SPAWN_CONTRACT_ENV
# (OPS_*/PI_* 前缀名 + 精确名 ZAI_CODING_CN_API_KEY/JINA_API_KEY/GH_TOKEN/
# DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE/IP_RADAR_ALERT_URLS)。此前
# {**os.environ, **_round_env()} 全量继承把 ADMIN_PASSWORD/JWT_SECRET 等
# 仓外密钥全传子进程,违 least-privilege(arch 评审 C4)。契约外一概不透传;
# 改契约表须同步本面 + test_ops_rounds 白名单对拍(独立真源)。运行必需非密钥
# 面:PATH/HOME(node/gh CLI 找位)、TMPDIR(os.tmpdir)、IP_RADAR_DATA_DIR
# (数据面单根,_ops_store 同名回路面)。IP_RADAR_ALERT_URLS = #184 finding
# webhook 出口契约员(与 backend _alerts.push 双消费面,agent 侧自读),保留。
_SPAWN_ENV_EXACT = frozenset({
    "PATH", "HOME", "TMPDIR",
    "GH_TOKEN", "IP_RADAR_DATA_DIR", "IP_RADAR_ALERT_URLS",
    "ZAI_CODING_CN_API_KEY", "JINA_API_KEY",
    "DOCS_ROOT", "PRECEDENTS_DIR", "LEDGER_FILE",
})
_SPAWN_ENV_PREFIXES = ("OPS_", "PI_")


def _spawn_env() -> dict[str, str]:
    """白名单 env 构造(C4 #196):契约面+运行必需面,叠加 _round_env 桥注入
    (override 语义保持:桥注入赢白名单面)。"""
    base = {k: v for k, v in os.environ.items()
            if k in _SPAWN_ENV_EXACT or k.startswith(_SPAWN_ENV_PREFIXES)}
    return {**base, **_round_env()}


def _infra(round_type: str, message: str) -> dict:
    """infra 兜底信封 + 台账行(契约违背/Popen 失败;不静默丢弃)。"""
    _ops_store.append_ledger(round_type, "—", "—", f"spawn error_code=infra; {message}")
    return {"ok": False, "round": round_type,
            "error": {"code": "infra", "message": message}}


def _drain_stderr(proc, on_log):
    """stderr 泵线程(spawn_round/_spawn_resume 共用):tail 留痕 + on_log 进度回调,
    回调炸不截断泵(进度面尽力而为)。"""
    stderr_lines: deque[str] = deque(maxlen=_STDERR_KEEP_LINES)

    def _drain() -> None:
        for line in proc.stderr:
            line = line.rstrip("\n")
            stderr_lines.append(line)
            if on_log is not None:
                try:
                    on_log(line)
                except Exception:
                    logger.warning("ops on_log 回调失败", exc_info=True)

    reader = threading.Thread(target=_drain, daemon=True, name="ops-round-stderr")
    reader.start()
    return stderr_lines, reader


def _stdout_envelope(stdout_text: str) -> dict | None:
    """轮次 CLI stdout 单行 JSON 信封解析(契约违背返回 None;两 spawn 面共用)。"""
    lines = [ln for ln in stdout_text.splitlines() if ln.strip()]
    if len(lines) != 1:
        return None
    try:
        parsed = json.loads(lines[0])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def spawn_round(
    round_type: str,
    input_text: str,
    *,
    on_log: Optional[Callable[[str], None]] = None,
    cancel_token=None,
) -> dict:
    """拉起运营 agent CLI 一轮,返回轮次信封(dict)。

    成功面:agent stdout 单行 JSON 透传;失败面(ok=false)原样透传且
    error.code/pkg 追加台账行;契约违背(exit 2/非单行/形状非法)→ infra 兜底;
    cancel_token 已取消(CancelToken,任务链 cancel 路由)→ 子进程终止,
    返回 {"cancelled": True}(台账留痕,九裁决 9)。
    """
    argv = _agent_argv(round_type, input_text)
    try:
        env = _spawn_env()  # C4(#196):显式白名单,废止 {**os.environ} 全量继承
    except RuntimeError as e:  # agent-config.json 坏文件(读面显式报错不静默)
        return _infra(round_type, f"agent 配置读取失败: {e}")
    try:
        # ops 树形状先行（裁④一个根；幂等建目录+表头）——判例注入（lib.sh rg
        # 对 PRECEDENTS_DIR）在空树也须能跑，目录缺失会伪装成 rg rc=2 基础设施
        # 故障（T2 Minor-3：无证据≠清白）
        _ops_store.init_ops_tree()
        proc = subprocess.Popen(
            argv, cwd=str(_REPO_ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", env=env)
    except OSError as e:  # 如 node 不在 PATH(P5 镜像未装时的显式失败面)
        return _infra(round_type, f"agent 拉起失败: {e}")

    # C1(#196):Popen 后整段异常逃生而 → 终止子进程防孤儿(任务兑底在
    # 线程入口 _settle_crash,不在此重复收口)
    try:
        stderr_lines, reader = _drain_stderr(proc, on_log)  # 两 spawn 面共用泵(终审 smell 收口)

        cancelled = threading.Event()

        def _watch_cancel() -> None:
            while proc.poll() is None:
                if cancel_token is not None and cancel_token.is_cancelled():
                    cancelled.set()
                    proc.terminate()
                    return
                time.sleep(0.2)

        watcher: Optional[threading.Thread] = None
        if cancel_token is not None:
            watcher = threading.Thread(target=_watch_cancel, daemon=True,
                                       name="ops-round-cancel")
            watcher.start()

        stdout_text = proc.stdout.read()
        proc.stdout.close()
        rc = proc.wait()
        reader.join(timeout=5)
        if watcher is not None:
            watcher.join(timeout=5)

        if cancelled.is_set():
            _ops_store.append_ledger(
                round_type, "—", "—", "admin 取消(无轮次信封;已花用量未知,九裁决 9 留痕)")
            return {"cancelled": True, "round": round_type}

        envelope = _stdout_envelope(stdout_text)
        if envelope is None or "ok" not in envelope:
            tail = " | ".join(list(stderr_lines)[-3:])[-_STDERR_TAIL_CHARS:]
            return _infra(round_type, f"轮次信封契约违背(rc={rc},stdout 非单行 JSON 含 ok): "
                                      f"{tail or '(stderr 空)'}")
        ok = envelope.get("ok")
        if rc == 0 and ok is True:
            return envelope  # 成功面:agent 侧已记账(lib.sh),桥零追加
        err = envelope.get("error")
        if rc == 1 and ok is False and isinstance(err, dict) \
                and isinstance(err.get("code"), str):
            pkg = envelope.get("pkg")
            note = f"spawn error_code={err['code']}" + (f"; pkg={pkg}" if pkg else "")
            _ops_store.append_ledger(round_type, "—", "—", note)
            return envelope
        return _infra(round_type, f"轮次信封形状非法(rc={rc}, ok={ok!r})")
    except BaseException:
        if proc.poll() is None:
            proc.terminate()  # 异常逃生不留守孤儿 agent 进程
        raise


# ── P5 #167 boot 恢复扫描(C稿 §4.6;轮次路由语义零改动——独立恢复面)──────────
# backend lifespan 启动时扫描 rounds/*/state.json 的 in_flight 轮:
#   ① 龄 >16h(2×8h cron)→ 标 FAILED(infra, stale)+台账(陈旧快照无恢复意义);
#   ② 自动恢复已用尽(resume_count≥1)→ 标 FAILED(infra)+台账留 replay 提示,
#      交人(每轮至多一次自动恢复);
#   ③ 其余 → 后台拉起 pipeline.mjs resume(经串行车道:借 manager.start_ops_round
#      占道,恢复轮与手动/cron 轮同一互斥面;stderr stage 行经 ops_log 进 SSE)。
# 恢复三规则在 pipeline.mjs resume 侧实施(脚本步幂等重入/工件齐补门不重花
# token/工件缺重跑);本面只做准入裁决与处置留痕。永不抛异常(启动面尽力而为;
# 处置失败轮保持 in_flight,下次 boot 再扫)。
_RESUME_ARGV_HEAD = ["node", "--max-old-space-size=256",
                     "ops/agent/pipeline.mjs", "resume"]
_STALE_HOURS = 16.0        # 2× 8h cron 周期(C稿 §4.6 规则 5)
_REPLAY_DIR_RE = _re.compile(r"-r\d+$")  # 重放目录不入恢复(终态语义,pipeline 侧已终态化)


def scan_inflight_rounds(now: datetime | None = None) -> list[dict]:
    """纯读扫描:rounds/*/state.json 的 in_flight 轮 → 处置建议清单。

    action ∈ {resume, fail_stale, fail_twice, skip_unreadable};-rN 重放目录
    与非 in_flight 轮不入清单。age_h=None 表示 updated_at 不可解析(按 stale 处置:
    无证据≠清白,不赌陈旧态可恢复)。
    """
    root = _ops_store.ops_root() / "rounds"
    if not root.is_dir():
        return []
    now = now or datetime.now(timezone.utc)
    rows: list[dict] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or _REPLAY_DIR_RE.search(d.name):
            continue
        sp = d / "state.json"
        if not sp.is_file():
            continue
        try:
            state = json.loads(sp.read_text(encoding="utf-8"))
        except ValueError:
            rows.append({"round_id": d.name, "dir": d,
                         "action": "skip_unreadable"})
            continue
        if not isinstance(state, dict) or state.get("status") != "in_flight":
            continue
        try:
            updated = datetime.fromisoformat(str(state.get("updated_at")))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_h = (now - updated).total_seconds() / 3600.0
        except ValueError:
            age_h = None
        if age_h is None or age_h > _STALE_HOURS:
            rows.append({"round_id": d.name, "dir": d, "action": "fail_stale",
                         "age_h": age_h})
        elif (state.get("resume_count") or 0) >= 1:
            rows.append({"round_id": d.name, "dir": d, "action": "fail_twice"})
        else:
            rows.append({"round_id": d.name, "dir": d, "action": "resume"})
    return rows


def _mark_round_failed(rd: Path, state: dict, reason: str) -> None:
    """in_flight → FAILED(infra) 就地终态化(仅改 status/stage/updated_at 三行
    + boot_marked 留痕字段——pipeline.mjs state schema 只增不改;原子写)。"""
    state = dict(state)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    state["status"] = "failed"
    state["stage"] = "FAILED"
    state["updated_at"] = now_iso
    state["boot_marked"] = {"code": "infra", "reason": reason,
                            "marked_at": now_iso}
    _ops_store.atomic_write_text(
        rd / "state.json",
        json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _spawn_resume(round_id: str, *, on_log: Callable[[str], None] | None = None,
                  env: dict | None = None) -> dict:
    """拉起 pipeline.mjs resume <round_id>(boot 恢复专用;不经 IP_RADAR_OPS_AGENT_CMD
    ——该覆盖面是轮次 spawn 契约 <round> <input> 形)。返回轮次信封(同 spawn_round
    单行 JSON 契约;形状违背 → infra 兜底信封)。"""
    argv = _RESUME_ARGV_HEAD + [round_id]
    try:
        proc = subprocess.Popen(
            argv, cwd=str(_REPO_ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", env=env or _spawn_env())  # C4(#196):回落面同白名单
    except OSError as e:
        return _infra("health", f"resume 拉起失败: {e}")
    # C1(#196):Popen 后异常逃生 → 终止子进程防孤儿(收口在 _run_recovery_round)
    try:
        stderr_tail, reader = _drain_stderr(proc, on_log)  # 同 spawn_round 泵(终审 smell 收口)
        stdout_text = proc.stdout.read()
        proc.stdout.close()
        rc = proc.wait()
        reader.join(timeout=5)
        envelope = _stdout_envelope(stdout_text)
        if envelope is None or "ok" not in envelope:
            tail = " | ".join(list(stderr_tail)[-3:])[-_STDERR_TAIL_CHARS:]
            return _infra("health", f"resume 信封契约违背(rc={rc}): {tail or '(stderr 空)'}")
        if envelope.get("ok") is not True:
            err = envelope.get("error")
            if isinstance(err, dict):
                _ops_store.append_ledger(
                    "health", "—", "—",
                    f"boot 恢复失败 error_code={err.get('code')}; {err.get('message')}")
        return envelope
    except BaseException:
        if proc.poll() is None:
            proc.terminate()  # 异常逃生不留守孤儿 agent 进程
        raise


def _run_recovery_round(manager, round_id: str) -> None:
    """恢复轮线程入口:占串行车道(与手动/cron 轮同一互斥面)→ resume spawn → 收口。"""
    task, busy = manager.start_ops_round("health")
    if task is None:
        logger.warning("boot 恢复:车道忙(%s),%s 留待下次启动扫描", busy, round_id)
        return

    def on_log(line: str) -> None:
        manager.ops_log(task.id, line)

    # C1(#196):恢复轮线程入口同面兑底——占道后链上任何异常也落终态+放车道。
    try:
        try:
            env = _spawn_env()  # C4(#196):同 spawn_round 白名单面
        except RuntimeError as e:
            manager.finish_ops_round(task.id, "failed", f"agent 配置读取失败: {e}", "infra")
            return
        result = _spawn_resume(round_id, on_log=on_log, env=env)
        if result.get("ok") is True:
            manager.finish_ops_round(task.id, "done")
            return
        err = result.get("error") or {}
        manager.finish_ops_round(
            task.id, "failed",
            err.get("message") or json.dumps(result, ensure_ascii=False),
            err.get("code") if isinstance(err.get("code"), str) else "infra")
    except Exception as e:
        logger.exception("boot 恢复轮线程未捕获异常(%s)", round_id)
        _settle_crash(manager, task.id, e, "health")


def recover_inflight_rounds(manager=None) -> list[dict]:
    """boot 处置入口(lifespan 调用;返回处置清单供测试/日志断言)。"""
    handled: list[dict] = []
    try:
        rows = scan_inflight_rounds()
    except Exception:
        logger.warning("boot 恢复扫描失败(轮次保持 in_flight,下次启动再扫)",
                       exc_info=True)
        return handled
    for row in rows:
        rid = row["round_id"]
        try:
            if row["action"] == "skip_unreadable":
                logger.warning("boot 恢复:state.json 不可解析,跳过 %s", rid)
                handled.append({**row, "done": False})
            elif row["action"] in ("fail_stale", "fail_twice"):
                state = json.loads((row["dir"] / "state.json")
                                   .read_text(encoding="utf-8"))
                _age = row.get("age_h")
                age = f"{_age:.1f}h" if _age is not None else "不可解析"
                reason = (f"in_flight 龄 {age}>16h(2×8h cron,stale)"
                          if row["action"] == "fail_stale"
                          else f"自动恢复已用尽(resume_count={state.get('resume_count')})")
                _mark_round_failed(row["dir"], state, reason)
                _ops_store.append_ledger(
                    "health", "—", "—",
                    f"boot 恢复:{reason} 标 FAILED(infra)——审计走 "
                    f"node ops/agent/pipeline.mjs replay {rid}(replay 可救,交人)")
                logger.info("boot 恢复:%s → FAILED(infra):%s", rid, reason)
                handled.append({**row, "done": True})
            elif row["action"] == "resume" and manager is not None:
                threading.Thread(
                    target=_run_recovery_round, args=(manager, rid),
                    daemon=True, name=f"ops-boot-resume-{rid}").start()
                logger.info("boot 恢复:%s → 后台 resume(车道互斥,SSE 可见)", rid)
                handled.append({**row, "done": True})
            elif row["action"] == "resume":
                logger.info("boot 恢复:%s 可 resume 但无 manager(测试面),跳过拉起", rid)
                handled.append({**row, "done": False})
        except Exception:
            logger.warning("boot 恢复处置失败:%s(轮保持 in_flight)",
                           rid, exc_info=True)
            handled.append({**row, "done": False})
    return handled


def _settle_crash(manager, task_id: str, exc: BaseException,
                  round_type: str = "health") -> None:
    """C1 兑底收口(#196):轮次线程链上未捕获异常(磁盘满 OSError 等)→
    任务落 failed 终态 + 释放串行车道,源 worker 车道不停摆至容器重启。
    失败原因照实三面留痕(task error/task_log/台账 best-effort——注入面自身
    在炸时台账可能再败,不赌),不吞异常信息;兑底自身再炸只记日志,
    绝不二次撕链(finish 最后走,车道必放)。"""
    reason = f"轮次线程异常兑底: {exc!r}"
    try:
        manager.ops_log(task_id, reason)
    except Exception:
        logger.exception("C1 兑底 ops_log 失败(task %s,原因已保 task error 面)", task_id)
    try:
        _ops_store.append_ledger(round_type, "—", "—",
                                 f"spawn error_code=infra; {reason}")
    except Exception:
        logger.exception("C1 兑底台账留痕失败(task %s;磁盘满等注入面未恢复时预期)", task_id)
    try:
        manager.finish_ops_round(task_id, "failed", reason, "infra")
    except Exception:
        logger.exception("C1 兑底 finish_ops_round 失败(task %s)——车道释放链断,需人工介入", task_id)


def run_round(manager, task, round_type: str, input_text: str) -> None:
    """ops 轮线程入口(路由侧 threading.Thread 拉起):spawn → 收口。

    ops 树形状初始化在 spawn_round 内(单一拼写,幂等)。任务态收口走
    manager.finish_ops_round(done/failed/cancelled;error_code =
    信封 error.code 九词闭集透传);stderr 行经 manager.ops_log 进任务链 SSE。
    C1(#196):线程入口整体兑底——链上任何未捕获异常(如磁盘满 OSError)
    也落终态+放车道,不得卡 running 撕停摆源 worker。"""
    def on_log(line: str) -> None:
        manager.ops_log(task.id, line)

    try:
        result = spawn_round(round_type, input_text, on_log=on_log,
                             cancel_token=task.token)
        if result.get("cancelled"):
            manager.finish_ops_round(task.id, "cancelled")
            return
        if result.get("ok") is True:
            manager.finish_ops_round(task.id, "done")
            return
        err = result.get("error") or {}
        manager.finish_ops_round(
            task.id, "failed",
            err.get("message") or json.dumps(result, ensure_ascii=False),
            err.get("code") if isinstance(err.get("code"), str) else "infra")
    except Exception as e:
        logger.exception("ops 轮线程未捕获异常(task %s, round_type=%s)",
                         task.id, round_type)
        _settle_crash(manager, task.id, e, round_type)
