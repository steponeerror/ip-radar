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


# ── GitHub Releases 惰性缓存查询(D2/ETag) ──────────────────────────────
import time

_RELEASES_URL = "https://api.github.com/repos/steponeerror/ip-radar/releases/latest"
_CACHE_TTL = 3600.0  # 1h 惰性缓存(D2)
_cache: dict | None = None          # {"tag","summary","url"}
_cache_at: float = 0.0
_etag: str | None = None


def reset_cache() -> None:
    global _cache, _cache_at, _etag
    _cache, _cache_at, _etag = None, 0.0, None


def _client_factory() -> "httpx.AsyncClient":
    import httpx
    return httpx.AsyncClient(timeout=10.0, follow_redirects=True)


async def fetch_latest(force: bool = False) -> dict | None:
    """查 GitHub latest release;缓存 1h,失败降级旧缓存,从未成功 → None。"""
    global _cache, _cache_at, _etag
    import httpx
    if _cache is not None and not force and (time.monotonic() - _cache_at) < _CACHE_TTL:
        return _cache
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ip-radar"}
    if _etag:
        headers["If-None-Match"] = _etag
    try:
        async with _client_factory() as client:
            resp = await client.get(_RELEASES_URL, headers=headers)
        if resp.status_code == 304 and _cache is not None:
            _cache_at = time.monotonic()
            return _cache
        resp.raise_for_status()
        data = resp.json()
        _etag = resp.headers.get("ETag")
        _cache = {
            "tag": data["tag_name"],
            "summary": (data.get("body") or "")[:200] or None,
            "url": data.get("html_url") or _RELEASES_URL,
        }
        _cache_at = time.monotonic()
        return _cache
    except Exception:
        return _cache  # 离线降级:有旧缓存吐旧的,没有 → None
