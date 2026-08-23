"""版本真源:镜像自描述版本号 + base-tag semver 比较。

Spec: docs/superpowers/specs/2026-08-23-in-app-update-design.md (D1, D10, F3)
"""
from __future__ import annotations

import os
import re

_BUILD_VERSION_PATH = os.environ.get("IP_RADAR_BUILD_VERSION_FILE", "/app/BUILD_VERSION")
# git describe: "vX.Y.Z[-N-gHEX[-dirty]]" 或 --always 退化 "HEX"
_DESCRIBE_RE = re.compile(r"^(v\d+\.\d+\.\d+)")
# 宽松 semver "vX.Y.Z"
_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _resolve_version() -> str:
    try:
        with open(_BUILD_VERSION_PATH) as f:
            s = f.read().strip()
            if s:
                return s
    except OSError:
        pass
    return os.environ.get("IP_RADAR_VERSION") or "dev"


VERSION: str = _resolve_version()


def base_tag(describe: str) -> str:
    """git describe 输出 → tag 前缀;无可解析 tag 返回原串。"""
    m = _DESCRIBE_RE.match(describe)
    return m.group(1) if m else describe


def _semver_tuple(v: str) -> tuple[int, int, int] | None:
    m = _SEMVER_RE.match(v)
    return tuple(int(x) for x in m.groups()) if m else None


def update_available(current: str, latest: str | None) -> bool:
    """base tag 严格小于 latest 才提示(领先/相等/解析失败均不弹)。"""
    if not latest or current == "dev":
        return False
    cur = _semver_tuple(base_tag(current))
    lst = _semver_tuple(latest)
    if cur is None or lst is None:
        return False
    return cur < lst
