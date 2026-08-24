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
    if not repo_dir:  # M1: 未配置不得退化到 CWD(容器 WORKDIR 可能恰是 git 仓库)
        return False
    try:
        # B1: 容器 root vs 宿主用户属主 → git≥2.35.2 dubious ownership 拒绝;repo 路径来自运维配置 env,容器内放开可接受
        return sp.run(["git", "-c", "safe.directory=*", "-C", repo_dir, "rev-parse", "--git-dir"],
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
    """极简 unix-socket HTTP GET(只为读自身 label,不引 docker SDK)。

    httpx 0.28 不支持 http+unix scheme,须走 uds transport(B1);
    localhost 只是占位 host,实际由 uds 指定 socket 路径。
    """
    import httpx
    try:
        transport = httpx.HTTPTransport(uds=DOCKER_SOCK)
        with httpx.Client(transport=transport) as client:
            r = client.get(f"http://localhost{path}", timeout=5.0)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def _compose_labels() -> dict | None:
    info = _self_inspect()
    return info.get("Config", {}).get("Labels") if info else None


def _self_inspect() -> dict | None:
    container = socket.gethostname()  # 容器内 hostname 即容器 ID
    body = _http_unix_get(f"/containers/{container}/json")
    if body is None:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None

_TIMEOUT = 600  # F5


def run_update() -> None:
    """阻塞执行 git pull --ff-only + compose 定向重建;失败 mark_failed(D4/F1/F5)。"""
    mark_updating()
    labels = _compose_labels()
    if not labels:
        mark_failed("无法确定 compose 项目名(docker.sock 不可用或非 compose 部署)")
        return
    project = labels.get("com.docker.compose.project")
    service = labels.get("com.docker.compose.service")
    repo = os.environ.get("IP_RADAR_REPO_DIR", "")
    compose_file = os.environ.get("IP_RADAR_COMPOSE_FILE",
                                  os.path.join(repo, "docker-compose.yml"))
    try:
        r = sp.run(["git", "-c", "safe.directory=*", "-C", repo, "pull", "--ff-only"],
                   capture_output=True, text=True, timeout=_TIMEOUT)
        if r.returncode != 0:
            mark_failed(f"git pull --ff-only 失败(本地有修改?): {r.stderr.strip()[:300]}")
            return
        # 自毁竞态修复(F6):compose 不能在本容器内跑——recreate 停掉旧容器时会把
        # 作为其子进程的 compose CLI 一并杀掉,新容器停在 Created、站点 502(实测)。
        # 改为经 docker.sock 起一次性 helper 容器(同镜像,自带 docker CLI)执行,
        # 与本容器生死解耦;state 留 updating,新容器对账收尾(F2)不变。
        info = _self_inspect() or {}
        host_repo = next((m.get("Source", "") for m in info.get("Mounts", [])
                          if m.get("Destination") == repo), "")
        image = info.get("Config", {}).get("Image", "")
        if not host_repo or not image:
            mark_failed("无法解析 repo 宿主机路径/镜像(docker.sock inspect 失败)")
            return
        compose_host = os.path.join(host_repo, os.path.basename(compose_file))
        cmd = ["docker", "run", "-d", "--rm", "--name", f"{project}-updater",
               "-v", "/var/run/docker.sock:/var/run/docker.sock",
               "-v", f"{host_repo}:{host_repo}", "-w", host_repo,
               "--entrypoint", "docker",   # 镜像 entrypoint 无条件 exec uvicorn,CMD 会被忽略
               image, "compose", "-p", project, "-f", compose_host,
               "up", "-d", "--build"]
        if service:
            cmd.append(service)
        r = sp.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            mark_failed(f"updater 容器启动失败: {r.stderr.strip()[:300]}")
            return
    except sp.TimeoutExpired:
        mark_failed("更新超时(git/compose 超过 10 分钟)")
    except OSError as e:
        mark_failed(f"更新执行异常: {e}")
