"""Managed-token store — admin UI 配置的源 token 存取(sources-redesign T1)。

冻结映射(plan 2026-10-17 Global Constraint):四个 env var,OTX 双源共享一 key。
grill 裁决落地:
- UI 值优先于 .env:load() **覆盖** os.environ;tokens.json 落 DATA_DIR
  (数据卷,容器重建留存)。部署零变化门槛:文件初始不存在 → 环境与现状逐字节等价。
- 完整值永不回显:status() 只出 configured + tail4;日志不打值。
- 清除回落启动快照:server `.env` 四 key 保留不动是回落语义的前提。
"""
import json
import logging
import os
from typing import Optional

from . import _registry

logger = logging.getLogger(__name__)

# env var → 消费源名(冻结;os.environ 是唯一 effective 真相,源侧使用点读取)
MANAGED: dict[str, list[str]] = {
    "ABUSEIPDB_API_KEY": ["abuseipdb"],
    "IPINFO_TOKEN": ["ipinfo_lite"],
    "IP2PROXY_TOKEN": ["ip2proxy"],
    "OTX_API_KEY": ["otx", "otx_subscribed"],
}

# 启动快照:模块导入期捕获,先于任何 mutation。「清除」回落 .env 注入的启动值;
# 无启动值(None)→ 清除即从 environ 移除。
_BOOT_SNAPSHOT: dict[str, Optional[str]] = {
    var: os.environ.get(var) for var in MANAGED
}

MAX_TOKEN_LEN = 512


def _tokens_path():
    # 调用期解析(循 _auth._auth_db_path 惯例):测试逐用例换 DATA_DIR
    return _registry.DATA_DIR / "tokens.json"


def _read_store() -> dict:
    path = _tokens_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:   # 坏 JSON/坏编码/不可读(卷权限、EIO):不炸启动(plan 裁决 + 终审 I-1)
        logger.warning("tokens.json unreadable (%s); ignoring stored tokens", e)
        return {}
    return data if isinstance(data, dict) else {}


def _write_store(data: dict) -> None:
    """原子写(写盘 0600 后 rename):fchmod 定死权限,umask 不参与。"""
    path = _tokens_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, json.dumps(data, indent=2).encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)


def load() -> None:
    """lifespan 早期调用:tokens.json 逐键**覆盖** os.environ(UI 优先裁决)。
    缺文件 = no-op;坏 JSON/文件不可读 = warning + no-op。防御:非受管键/空白值跳过
    (手工改过的文件不得 brick 启动——os.environ 赋非 str 会 TypeError)。"""
    for var, value in _read_store().items():
        if var in MANAGED and isinstance(value, str) and value.strip():
            os.environ[var] = value


def set_token(var: str, value: str) -> None:
    if var not in MANAGED:
        raise ValueError(f"unknown managed env var: {var}")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("token value must be a non-empty string")
    if len(value) > MAX_TOKEN_LEN:
        raise ValueError(f"token value exceeds {MAX_TOKEN_LEN} chars")
    data = _read_store()
    data[var] = value
    _write_store(data)
    os.environ[var] = value   # 即时生效裁决:写盘同时覆盖运行进程


def clear_token(var: str) -> None:
    if var not in MANAGED:
        raise ValueError(f"unknown managed env var: {var}")
    data = _read_store()
    data.pop(var, None)
    _write_store(data)
    boot = _BOOT_SNAPSHOT[var]
    if boot is not None:
        os.environ[var] = boot   # 回落 .env 启动值
    else:
        os.environ.pop(var, None)


def status() -> list[dict]:
    """每受管 var 一行;effective 值 = 当前 os.environ(含 .env 注入的启动值)。
    硬约束:只出 configured + tail4,完整值永不回显。"""
    out = []
    for var, sources in MANAGED.items():
        val = (os.environ.get(var) or "").strip()
        out.append({
            "env_var": var,
            "sources": list(sources),
            "configured": bool(val),
            "tail4": val[-4:] if val else None,
        })
    return out
