"""运营 agent 配置面(票 #140 立;票 #143 多供应商扩面):ops 树
agent-config.json 存取 + 动态模型目录 + 状态出参。

用户裁(2026-10-20 grill Q5–Q7,ADR 0005):放开 glm 单家——目录由容器内 pi
真实可装载面驱动,不再手抄闭集;key 逐 provider 存放;零硬闸(不设成本/
供应商门,健康轮 = 首次使用的事实验证面)。

- 落位:$IP_RADAR_DATA_DIR/ops/agent-config.json(_ops_store 原子写基座,
  裁④ ops 树一个根);_ops_rounds._round_env 每次 spawn 现读 → 改完即生效,
  无需重启;
- 模型值 = qualified "provider/model"(首个 "/" 前为 provider id;裸值 =
  缺省 provider zai-coding-cn,#140 既有盘上值/env 向后兼容;写盘归一为
  qualified 单拼写);优先级链:配置 > 进程 effective env > models.mjs 缺省
  (env 兜底链不动,override 灌 key 保持兜底语义);
- 动态目录:node 子调用 ops/agent/catalog.mjs(离线 dump,pi-ai builtin 全家
  + 用户两层);结果缓存 TTL 300s;失败/超时/形状坏 → 兜底 #140 五值闭集
  (catalog_source=fallback 显式标注,不伪装动态);PUT 校验用活目录(兜底时
  即兜底目录),未知 provider/模型 422 先校验后落盘(坏入参零写);
  IP_RADAR_OPS_CATALOG_CMD 覆盖命令体(测试面,同 IP_RADAR_OPS_AGENT_CMD
  惯例——后端 CI runner 无 node);
- key 纪律(逐 provider 延伸 #140 面):api_keys:{<providerId>:key} 旧
  zai_api_key 兼容读 alias(api_keys 同家赢,旧字段原样保留不清除);
  write-only:出参只 {configured, tail4},完整 key 绝不进出参、错误消息与
  日志;空串/缺省 = 该家保持不改(无清除面);
- tool_keys(发现通道扩槽,PR3a 2026-10-24 裁定):{toolId:key},槽闭集
  {"jina"}(web_search s.jina.ai 消费,扩槽=代码面);同 write-only 遮蔽
  (出参只 {configured, tail4});值非空校验(空串=422,与 api_keys「空=保持
  不改」不同——票面明写非空校验;无清除面同);_ops_rounds._round_env 注入
  JINA_API_KEY(与 ZAI_CODING_CN_API_KEY 同型:配置优先,改完即生效);
- 坏文件显式报错不静默(沿 _ops_store._parse_precedent 判例):非法 JSON/
  顶层非映射/已知字段非 str/api_keys 非映射或值非 str → RuntimeError(路由
  500 / spawn infra 兜底),绝不伪装成「未配置」(无证据≠清白);未知额外键
  容忍(前向兼容,不消费)。
"""

import json
import logging
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

from . import _ops_store

logger = logging.getLogger(__name__)

# 兜底目录:zai-coding-cn 实测装载目录五值(裁决 2026-10-20;pi-ai 版本由
# ops/agent lockfile 钉——lockfile 升级须复测)。动态目录失败时的闭集与
# PUT 校验面;cost 不手抄(兜底面 UI 成本提示隐去)。
AGENT_MODEL_IDS = ("glm-4.6v", "glm-5.3", "glm-5.3-flash",
                   "glm-5.3-highspeed", "glm-5.3-flashx")
_FALLBACK_CATALOG: dict = {
    pid: [{"id": mid, "name": mid, "cost": None} for mid in AGENT_MODEL_IDS]
    for pid in ("zai-coding-cn",)
}

# models.mjs DEFAULTS 逐字独立抄录(不 import node 面;spawn 侧缺省同值),
# qualified 归一(裸值归 zai-coding-cn)
_MODEL_DEFAULTS = {"health": "zai-coding-cn/glm-5.3-flash",
                   "discover": "zai-coding-cn/glm-5.3"}
_PROVIDER_ID = "zai-coding-cn"
_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # pi provider id 形(kebab)

_CONFIG_NAME = "agent-config.json"
_MAX_KEY_LEN = 512  # _tokens.MAX_TOKEN_LEN 同值(管理面输入上限惯例)
_TOOL_KEY_IDS = ("jina",)  # 工具 key 槽闭集(发现通道 web_search,PR3a;扩槽=代码面非配置面)
_KNOWN_FIELDS = ("model_health", "model_discover", "zai_api_key", "api_keys", "tool_keys")

_REPO_ROOT = Path(__file__).resolve().parents[2]  # 仓根(catalog.mjs 的 cwd)
_CATALOG_SCRIPT = ("node", "ops/agent/catalog.mjs")  # 相对仓根(部署形态)
_CATALOG_CMD_ENV = "IP_RADAR_OPS_CATALOG_CMD"
_CATALOG_TTL_S = 300.0
_CATALOG_TIMEOUT_S = 15.0
_catalog_cache: dict = {"at": None, "data": None, "source": None}
_catalog_lock = threading.Lock()


def _config_path() -> Path:
    return _ops_store.ops_root() / _CONFIG_NAME


def read_config() -> dict:
    """读配置;缺文件 = {}(未配置是真实态;GET 零副作用,不建文件)。

    坏文件 → RuntimeError(消息不含字段值,key 纪律);未知键忽略不消费。"""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise RuntimeError(f"agent-config.json 非法 JSON: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError("agent-config.json 顶层必须是 JSON 对象")
    cfg: dict = {}
    for field in ("model_health", "model_discover", "zai_api_key"):
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise RuntimeError(f"agent-config.json 字段形状坏: {field} 必须是字符串")
        cfg[field] = value
    api_keys = data.get("api_keys")
    if api_keys is not None:
        if not isinstance(api_keys, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in api_keys.items()):
            raise RuntimeError("agent-config.json 字段形状坏: api_keys 必须是 {providerId: 字符串}")
        cfg["api_keys"] = dict(api_keys)
    tool_keys = data.get("tool_keys")
    if tool_keys is not None:
        # 同 api_keys 读面宽容(str:str 即收,槽外 id 不在读取面拒——写面闭集校验;
        # 前向兼容:未来扩槽不改旧文件读取)
        if not isinstance(tool_keys, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in tool_keys.items()):
            raise RuntimeError("agent-config.json 字段形状坏: tool_keys 必须是 {toolId: 字符串}")
        cfg["tool_keys"] = dict(tool_keys)
    return cfg


def effective_keys() -> dict[str, str]:
    """配置面有效 key(逐 provider):api_keys + 旧 zai_api_key alias(api_keys
    同家赢)。不含 env 兜底——zai env 走 ZAI_CODING_CN_API_KEY env 注入链
    (#140 链不动);桥侧物化 auth.json 只物化配置面(ops 树是配置真源)。"""
    cfg = read_config()
    keys = dict(cfg.get("api_keys") or {})
    legacy = cfg.get("zai_api_key")
    if legacy and _PROVIDER_ID not in keys:
        keys[_PROVIDER_ID] = legacy
    return {pid: key.strip() for pid, key in keys.items()
            if isinstance(key, str) and key.strip()}


def _qualified(value: str) -> str:
    """模型值归一:裸值 → 缺省 provider qualified(出参/写盘单拼写)。"""
    return value if "/" in value else f"{_PROVIDER_ID}/{value}"


def catalog() -> tuple[dict, str]:
    """可装载模型目录:(目录, 来源)。动态 dump(TTL 缓存)→ 兜底闭集。

    目录形状 {providerId: [{id, name, cost}, …]}(catalog.mjs dump 逐字);
    任何失败(OSError/超时/exit≠0/JSON 坏/形状坏/空)→ 兜底 + source=
    "fallback"(显式,不伪装动态)。子调用离线零 key,catalog 面无密可泄。"""
    now = time.monotonic()
    with _catalog_lock:
        if _catalog_cache["data"] is not None \
                and _catalog_cache["at"] is not None \
                and now - _catalog_cache["at"] < _CATALOG_TTL_S:
            return _catalog_cache["data"], _catalog_cache["source"]
    override = os.environ.get(_CATALOG_CMD_ENV, "").strip()
    argv = shlex.split(override) if override else list(_CATALOG_SCRIPT)
    try:
        proc = subprocess.run(argv, cwd=str(_REPO_ROOT), capture_output=True,
                              text=True, timeout=_CATALOG_TIMEOUT_S)
        data = json.loads(proc.stdout) if proc.returncode == 0 else None
        if not isinstance(data, dict) or not data:
            raise ValueError("目录空")
        for pid, entries in data.items():
            if not isinstance(pid, str) or not _PROVIDER_ID_RE.match(pid) \
                    or not isinstance(entries, list) or not entries:
                raise ValueError(f"provider {pid!r} 条目形状坏")
            for e in entries:
                if not isinstance(e, dict) or not isinstance(e.get("id"), str):
                    raise ValueError(f"provider {pid!r} 模型条目形状坏")
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        logger.warning("模型目录 dump 失败,兜底闭集: %s", e)  # 消息面零密钥
        return _FALLBACK_CATALOG, "fallback"
    with _catalog_lock:
        _catalog_cache.update(at=now, data=data, source="dynamic")
    return data, "dynamic"


def _validate_model(field: str, value: str, cat: dict) -> None:
    """qualified/裸值模型入参校验(写前门;消息带目录可读,不带 key)。"""
    ref = _qualified(value)
    pid, _, model_id = ref.partition("/")
    entries = cat.get(pid)
    if entries is None:
        providers = "/".join(sorted(cat)[:8])
        raise ValueError(f"{field} 的 provider 未装载: {pid}"
                         f"(目录 {len(cat)} 家: {providers}…)")
    ids = [e["id"] for e in entries]
    if model_id not in ids:
        shown = "/".join(ids[:8]) + ("…" if len(ids) > 8 else "")
        raise ValueError(f"{field} 未在 {pid} 装载目录内({shown}): {ref}")


def status() -> dict:
    """GET/PUT 出参:两模型有效值(配置 > env > 缺省,qualified 归一)+
    逐 provider key 状态 + 动态目录(catalog_source 显式动态/兜底)。"""
    cfg = read_config()
    keys = effective_keys()
    zai_env = os.environ.get("ZAI_CODING_CN_API_KEY", "").strip()
    if zai_env and _PROVIDER_ID not in keys:
        keys[_PROVIDER_ID] = zai_env  # zai env 兜底链(#140 不动);别家 env 归 pi-ai 请求期
    cat, source = catalog()
    return {
        "model_health": _qualified(cfg.get("model_health")
                                   or os.environ.get("OPS_MODEL_HEALTH", "").strip()
                                   or _MODEL_DEFAULTS["health"].partition("/")[2]),
        "model_discover": _qualified(cfg.get("model_discover")
                                     or os.environ.get("OPS_MODEL_DISCOVER", "").strip()
                                     or _MODEL_DEFAULTS["discover"].partition("/")[2]),
        "api_keys": {pid: {"configured": True, "tail4": key[-4:]}
                     for pid, key in sorted(keys.items())},
        # tool_keys 同型遮蔽(configured+tail4,沿 api_keys 面;只报配置面——
        # env 兑底通道经 spawn 继承透传,不在状态面伪装已配置)
        "tool_keys": {tid: {"configured": True, "tail4": key.strip()[-4:]}
                      for tid, key in sorted((cfg.get("tool_keys") or {}).items())},
        "catalog": cat,
        "catalog_source": source,
    }


def update(model_health: str | None = None, model_discover: str | None = None,
           api_keys: dict | None = None, tool_keys: dict | None = None) -> dict:
    """PUT:字段缺省 = 保持不改;api_keys 值空串/纯空白 = 该家保持不改;
    tool_keys 值非空校验(空串/纯空白 = 422,与 api_keys 不同——票面明写;
    槽闭集 {"jina},槽外 id = 422 防拼写静默失效)。

    先全量校验再落盘(写前门:坏入参零写);模型校验用活目录(动态失败时
    即兜底闭集);返回写后 status()。入参形状(type)不在此收口——路由层
    pydantic 先挡(非密面);密钥纪律相关校验(长度/形状)全在此,ValueError
    消息永不回带 key 值。"""
    cat, _ = catalog()
    for name, value in (("model_health", model_health),
                        ("model_discover", model_discover)):
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"{name} 必须是字符串")
            _validate_model(name, value, cat)
    cleaned: dict[str, str] = {}
    if api_keys is not None:
        if not isinstance(api_keys, dict):
            raise ValueError("api_keys 必须是 {providerId: key} 映射")
        for pid, key in api_keys.items():
            if not isinstance(pid, str) or not _PROVIDER_ID_RE.match(pid):
                raise ValueError(f"api_keys provider id 形状坏: {pid!r}")
            if not isinstance(key, str):
                raise ValueError(f"api_keys[{pid}] 必须是字符串")
            key = key.strip()
            if not key:
                continue  # 空 = 该家保持不改(无清除面)
            if len(key) > _MAX_KEY_LEN:
                raise ValueError(f"api_keys[{pid}] 超长(>{_MAX_KEY_LEN} 字符)")  # 不回带值
            cleaned[pid] = key
    cleaned_tools: dict[str, str] = {}
    if tool_keys is not None:
        if not isinstance(tool_keys, dict):
            raise ValueError("tool_keys 必须是 {toolId: key} 映射")
        for tid, key in tool_keys.items():
            if tid not in _TOOL_KEY_IDS:  # 槽闭集:拼写错拒绝而非静默失效
                raise ValueError(f"tool_keys 槽未知: {tid!r}(闭集: {'/'.join(_TOOL_KEY_IDS)})")
            if not isinstance(key, str):
                raise ValueError(f"tool_keys[{tid}] 必须是字符串")
            key = key.strip()
            if not key:  # 非空校验(PR3a 票面;与 api_keys 空=保持不改不同,无清除面同)
                raise ValueError(f"tool_keys[{tid}] 必须非空(无清除面;清除=直接改盘)")
            if len(key) > _MAX_KEY_LEN:
                raise ValueError(f"tool_keys[{tid}] 超长(>{_MAX_KEY_LEN} 字符)")  # 不回带值
            cleaned_tools[tid] = key
    cfg = read_config()  # 合并需要现状;坏文件 RuntimeError → 路由 500
    if model_health is not None:
        cfg["model_health"] = _qualified(model_health)
    if model_discover is not None:
        cfg["model_discover"] = _qualified(model_discover)
    if cleaned:
        cfg.setdefault("api_keys", {}).update(cleaned)
    if cleaned_tools:
        cfg.setdefault("tool_keys", {}).update(cleaned_tools)
    _ops_store.atomic_write_text(
        _config_path(), json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    return status()
