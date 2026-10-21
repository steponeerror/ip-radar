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
import shlex
import subprocess
import sys
import threading
import time
from collections import deque
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
        env["OPS_AUTH"] = str(auth_path)
    zai = keys.get("zai-coding-cn") \
        or os.environ.get("ZAI_CODING_CN_API_KEY", "").strip()
    if zai:
        env["ZAI_CODING_CN_API_KEY"] = zai  # zai env 兜底链不动(stored credential 优先)
    return env


def _infra(round_type: str, message: str) -> dict:
    """infra 兜底信封 + 台账行(契约违背/Popen 失败;不静默丢弃)。"""
    _ops_store.append_ledger(round_type, "—", "—", f"spawn error_code=infra; {message}")
    return {"ok": False, "round": round_type,
            "error": {"code": "infra", "message": message}}


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
        env = {**os.environ, **_round_env()}
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

    stderr_lines: deque[str] = deque(maxlen=_STDERR_KEEP_LINES)

    def _drain() -> None:
        for line in proc.stderr:
            line = line.rstrip("\n")
            stderr_lines.append(line)
            if on_log is not None:
                try:
                    on_log(line)
                except Exception:  # 回调炸不截断 stderr 泵(进度面尽力而为)
                    logger.warning("ops on_log 回调失败", exc_info=True)

    reader = threading.Thread(target=_drain, daemon=True, name="ops-round-stderr")
    reader.start()

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

    lines = [ln for ln in stdout_text.splitlines() if ln.strip()]
    envelope = None
    if len(lines) == 1:
        try:
            parsed = json.loads(lines[0])
            if isinstance(parsed, dict):
                envelope = parsed
        except ValueError:
            envelope = None
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


def run_round(manager, task, round_type: str, input_text: str) -> None:
    """ops 轮线程入口(路由侧 threading.Thread 拉起):spawn → 收口。

    ops 树形状初始化在 spawn_round 内(单一拼写,幂等)。任务态收口走
    manager.finish_ops_round(done/failed/cancelled;error_code =
    信封 error.code 九词闭集透传);stderr 行经 manager.ops_log 进任务链 SSE。
    """
    def on_log(line: str) -> None:
        manager.ops_log(task.id, line)

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
