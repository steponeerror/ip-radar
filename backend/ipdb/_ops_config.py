"""运营 agent 配置面(票 #140):ops 树 agent-config.json 存取 + 状态出参。

用户裁(2026-10-20):前端出「选模型 + 填 key」,运行时可配——轮次模型不再
恒吃 models.mjs 缺省、zai key 不再只靠 compose override 硬灌。

- 落位:$IP_RADAR_DATA_DIR/ops/agent-config.json(_ops_store 原子写基座,
  裁④ ops 树一个根);_ops_rounds._round_env 每次 spawn 现读 → 改完即生效,
  无需重启;
- 优先级链:配置 > 进程 effective env > models.mjs 缺省(env 兜底链不动,
  override 灌 key 保持兜底语义,票面第 5 条);
- 永不回显:出参只含 zai_api_key{configured, tail4}(沿 _tokens.status /
  TokenStatusOut 先例);key 绝不进出参、错误消息与日志(P2 既有纪律);
  空串/缺省 = 保持不改(票面裁定,无清除面);
- 模型闭集 = zai-coding-cn 实测装载目录(2026-10-20 本仓 ops/agent npm ci
  后 loadModels().catalog 逐字;pi-ai 版本由 ops/agent lockfile 钉——lockfile
  升级须复测);PUT 未知值 422,先全量校验后落盘(坏入参零写);
- GET 带 allowed_models:前端下拉由后端驱动(单一真相源,裁决 2026-10-20),
  目录将来变化 UI 无需跟改;
- 坏文件显式报错不静默(沿 _ops_store._parse_precedent 判例):非法 JSON/
  顶层非映射/已知字段非 str → RuntimeError(路由 500 / spawn infra 兜底),
  绝不伪装成「未配置」(无证据≠清白);未知额外键容忍(前向兼容,不消费)。
"""

import json
import os
from pathlib import Path

from . import _ops_store

# 模型闭集:zai-coding-cn 实测装载目录(裁决 2026-10-20;lockfile 升级须复测,
# 见模块头)。前端下拉由 GET allowed_models 驱动,故此表是唯一抄录点。
AGENT_MODEL_IDS = ("glm-4.6v", "glm-5.3", "glm-5.3-flash",
                   "glm-5.3-highspeed", "glm-5.3-flashx")

# models.mjs DEFAULTS 逐字独立抄录(不 import node 面;spawn 侧缺省同值)
_MODEL_DEFAULTS = {"health": "glm-5.3-flash", "discover": "glm-5.3"}

_CONFIG_NAME = "agent-config.json"
_MAX_KEY_LEN = 512  # _tokens.MAX_TOKEN_LEN 同值(管理面输入上限惯例)
_KNOWN_FIELDS = ("model_health", "model_discover", "zai_api_key")


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
    cfg: dict[str, str] = {}
    for field in _KNOWN_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise RuntimeError(f"agent-config.json 字段形状坏: {field} 必须是字符串")
        cfg[field] = value
    return cfg


def effective_key() -> str:
    """有效 zai key:配置 > 进程 env(兜底链;两侧都按 strip 规整)。"""
    return (read_config().get("zai_api_key")
            or os.environ.get("ZAI_CODING_CN_API_KEY", "")).strip()


def status() -> dict:
    """GET/PUT 出参:两模型有效值(配置 > env > 缺省)+ key 状态 + 闭集。"""
    cfg = read_config()
    key = effective_key()
    return {
        "model_health": cfg.get("model_health")
        or os.environ.get("OPS_MODEL_HEALTH", "").strip()
        or _MODEL_DEFAULTS["health"],
        "model_discover": cfg.get("model_discover")
        or os.environ.get("OPS_MODEL_DISCOVER", "").strip()
        or _MODEL_DEFAULTS["discover"],
        "zai_api_key": {"configured": bool(key), "tail4": key[-4:] if key else None},
        "allowed_models": list(AGENT_MODEL_IDS),
    }


def update(model_health: str | None = None, model_discover: str | None = None,
           zai_api_key: str | None = None) -> dict:
    """PUT:三字段缺省 = 保持不改;zai_api_key 空串/纯空白 = 保持不改。

    先全量校验再落盘(写前门:坏入参零写);返回写后 status()。"""
    for name, value in (("model_health", model_health),
                        ("model_discover", model_discover)):
        if value is not None and value not in AGENT_MODEL_IDS:
            raise ValueError(
                f"{name} 必须在闭集内: {'/'.join(AGENT_MODEL_IDS)},实际 {value!r}")
    if zai_api_key is not None:
        zai_api_key = zai_api_key.strip()
        if zai_api_key and len(zai_api_key) > _MAX_KEY_LEN:
            raise ValueError(f"zai_api_key 超长(>{_MAX_KEY_LEN} 字符)")  # 不回带值
    cfg = read_config()  # 合并需要现状;坏文件 RuntimeError → 路由 500
    if model_health is not None:
        cfg["model_health"] = model_health
    if model_discover is not None:
        cfg["model_discover"] = model_discover
    if zai_api_key:  # 空串/缺省 = 保持不改
        cfg["zai_api_key"] = zai_api_key
    _ops_store.atomic_write_text(
        _config_path(), json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    return status()
