"""L2 自更新:状态机 + 启动对账 + subprocess 执行器。

Spec F1/F2/F5;执行器在 Task 4 追加。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess as sp
from datetime import datetime, timedelta, timezone

from ._version import VERSION

STATE_PATH = os.environ.get("IP_RADAR_STATE_FILE",
                            os.path.join(os.environ.get("IP_RADAR_DATA_DIR", "/app/data"), "update_state.json"))
_STALE_AFTER = timedelta(minutes=15)  # F2 双保险:updating 超时视为挂死

_inmem: dict = {"state": "idle", "error": None, "at": None}


def _version_now() -> str:
    return VERSION


def _read_disk() -> dict | None:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _persist(state: str, error: str | None = None) -> None:
    _inmem.update(state=state, error=error, at=datetime.now(timezone.utc).isoformat())
    payload = {**_inmem, "from_version": _version_now()} if state == "updating" else dict(_inmem)
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError:
        pass  # 落盘尽力而为,内存态为准


def state() -> dict:
    return dict(_inmem)


def mark_updating() -> None:
    _persist("updating")


def mark_failed(err: str) -> None:
    _persist("failed", err)


def reconcile_on_startup() -> None:
    d = _read_disk()
    if not d or d.get("state") != "updating":
        _inmem.update(state="idle", error=None, at=None)
        return
    at = d.get("at")
    if at:
        try:
            when = datetime.fromisoformat(at)
            if datetime.now(timezone.utc) - when > _STALE_AFTER:
                _persist("failed", "更新超时(超过 15 分钟未完成)")
                return
        except ValueError:
            pass
    if d.get("from_version") and d["from_version"] != _version_now():
        _inmem.update(state="idle", error=None, at=None)  # 版本已变 → 上次成功
    else:
        _persist("failed", "更新中断(版本未变化,subprocess 未完成)")


# ── L2 解锁检测 + compose 项目名自发现(F1) ──

DOCKER_SOCK = "/var/run/docker.sock"
_enabled_cache: bool | None = None


def reset_checks() -> None:
    global _enabled_cache
    _enabled_cache = None


def _sock_writable() -> bool:
    return os.path.exists(DOCKER_SOCK) and os.access(DOCKER_SOCK, os.W_OK)


def _git_ok(repo_dir: str) -> bool:
    try:
        return sp.run(["git", "-C", repo_dir, "rev-parse", "--git-dir"],
                      capture_output=True, timeout=10).returncode == 0
    except (OSError, sp.TimeoutExpired):
        return False


def self_update_enabled() -> bool:
    global _enabled_cache
    if _enabled_cache is None:
        _enabled_cache = (
            os.environ.get("IP_RADAR_SELF_UPDATE") == "1"
            and bool(os.environ.get("IP_RADAR_UPDATE_TOKEN"))
            and _sock_writable()
            and _git_ok(os.environ.get("IP_RADAR_REPO_DIR", ""))
        )
    return _enabled_cache


def _http_unix_get(path: str) -> bytes | None:
    """极简 unix-socket HTTP GET(只为读自身 label,不引 docker SDK)。"""
    import httpx
    try:
        r = httpx.get(f"http+unix://{DOCKER_SOCK}{path}", timeout=5.0)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def _compose_labels() -> dict | None:
    container = socket.gethostname()  # 容器内 hostname 即容器 ID
    body = _http_unix_get(f"/containers/{container}/json")
    if body is None:
        return None
    try:
        return json.loads(body).get("Config", {}).get("Labels") or None
    except ValueError:
        return None
