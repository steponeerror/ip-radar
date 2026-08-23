"""L2 自更新:状态机 + 启动对账 + subprocess 执行器。

Spec F1/F2/F5;执行器在 Task 4 追加。
"""
from __future__ import annotations

import json
import os
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
