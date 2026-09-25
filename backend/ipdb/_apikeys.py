# backend/ipdb/_apikeys.py — JWT-as-API-key(spec §7)
"""API key 核心:PyJWT 签发/校验 + api_key_meta 元数据存取 + 查询端点依赖。

密钥本体是 HS256 JWT(无状态校验),元数据(sub/name/last_used/disabled)
落 auth db 的 api_key_meta 表,供管理端点 CRUD 与吊销。表模型定义在本
模块并注册进 _auth.Base.metadata;main.py 模块级 import 本模块,使 lifespan
的 init_auth_db() 一并建表(controller ruling)。

失效语义(spec §7.1):IP_RADAR_API_JWT_SECRET 未设或 <32 字节 → keys
disabled —— issue/verify 抛 503 admin_disabled;api_key_dep 对带
Authorization 头的请求先 503(在 jwt.decode 摸到缺失 secret 之前)。
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import jwt as pyjwt
from fastapi import Request
from fastapi.security import HTTPBearer
from sqlalchemy import Boolean, DateTime, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ._auth import Base, _session_maker
from ._errors import ApiError, ErrorCode

_log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# last_used 节流落盘(spec §7.3):模块级缓存 + 上次 flush 时间戳,距上次
# flush ≥30s 才批量 UPDATE。纯展示元数据 —— flush 失败仅记日志,绝不影响请求。
_LAST_USED_FLUSH_INTERVAL = 30.0
_last_used_cache: dict[str, float] = {}   # sub -> ts
_last_flush = 0.0

# demo 前端种子的保留 sub(Task 3 的 resolve_web_identity 依此识别 web 身份)
DEMO_SUB = "demoweb"


class ApiKeyMeta(Base):
    """API key 元数据表;JWT 本体不入库,sub 为主键关联。"""
    __tablename__ = "api_key_meta"

    sub: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sources: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON 数组(源名,registry 序)| NULL=全部公开源(spec §4;私源只能显式点名)


def keys_enabled() -> bool:
    s = os.environ.get("IP_RADAR_API_JWT_SECRET", "")
    return len(s.encode()) >= 32


def _secret() -> str:
    return os.environ["IP_RADAR_API_JWT_SECRET"]


def _require_keys_enabled() -> None:
    if not keys_enabled():
        raise ApiError(
            ErrorCode.admin_disabled,
            "API keys disabled: IP_RADAR_API_JWT_SECRET not set or <32 bytes")


def _meta_dict(row: ApiKeyMeta) -> dict:
    return {
        "sub": row.sub,
        "name": row.name,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
        "disabled": row.disabled,
        "sources": _parse_sources(row.sources),
        "web": row.sub == DEMO_SUB,
    }


async def issue_key(name: str, expires_days: int = 180,
                    sources: list[str] | None = None) -> tuple[dict, str]:
    _require_keys_enabled()
    sub = uuid.uuid4().hex[:16]
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": sub, "kname": name, "iat": now,
         "exp": now + expires_days * 86400},
        _secret(), algorithm="HS256")
    sm = _session_maker()
    async with sm() as s:
        s.add(ApiKeyMeta(sub=sub, name=name,
                         sources=(json.dumps(sources)
                                  if sources is not None else None)))
        await s.commit()
    return {"sub": sub, "name": name}, token


async def verify_key(token: str) -> dict:
    _require_keys_enabled()
    try:
        claims = pyjwt.decode(token, _secret(), algorithms=["HS256"])
    except pyjwt.InvalidTokenError as e:
        raise ApiError(ErrorCode.unauthorized,
                       f"invalid or expired API key: {type(e).__name__}")
    sub = claims.get("sub", "")
    sm = _session_maker()
    async with sm() as s:
        row = await s.get(ApiKeyMeta, sub)
        if row is None:
            raise ApiError(ErrorCode.unauthorized, "unknown API key")
        if row.disabled:
            raise ApiError(ErrorCode.forbidden, "API key disabled")
    await _touch_last_used(sub)
    return {"sub": sub, "name": claims.get("kname") or row.name,
            "sources": _parse_sources(row.sources)}


async def migrate_sources_column() -> None:
    """create_all 不给已有表加列(审计 C1):幂等 ALTER,失败 fail-fast。"""
    from ._auth import _engine
    async with _engine().begin() as conn:
        rows = (await conn.exec_driver_sql(
            "PRAGMA table_info(api_key_meta)")).fetchall()
        if "sources" not in {r[1] for r in rows}:
            await conn.exec_driver_sql(
                "ALTER TABLE api_key_meta ADD COLUMN sources TEXT")


async def ensure_demo_row() -> None:
    """种子行(spec §4):仅 keys_enabled 时建;已存在不动(保留管理员改过的集合)。"""
    if not keys_enabled():
        return
    sm = _session_maker()
    async with sm() as s:
        if await s.get(ApiKeyMeta, DEMO_SUB) is None:
            s.add(ApiKeyMeta(sub=DEMO_SUB, name="demo 前端"))
            await s.commit()


async def set_sources(sub: str, sources: list[str] | None) -> None:
    sm = _session_maker()
    async with sm() as s:
        await s.execute(
            update(ApiKeyMeta).where(ApiKeyMeta.sub == sub)
            .values(sources=json.dumps(sources) if sources is not None else None))
        await s.commit()


def _parse_sources(raw: str | None) -> list[str] | None:
    return json.loads(raw) if raw else None


async def set_disabled(sub: str, flag: bool) -> None:
    sm = _session_maker()
    async with sm() as s:
        await s.execute(
            update(ApiKeyMeta).where(ApiKeyMeta.sub == sub)
            .values(disabled=flag))
        await s.commit()


async def delete_key(sub: str) -> None:
    sm = _session_maker()
    async with sm() as s:
        await s.execute(delete(ApiKeyMeta).where(ApiKeyMeta.sub == sub))
        await s.commit()


async def list_keys() -> list[dict]:
    """全部密钥元数据(不含 token 本体)。"""
    sm = _session_maker()
    async with sm() as s:
        rows = (await s.execute(
            select(ApiKeyMeta).order_by(ApiKeyMeta.created_at.desc())
        )).scalars().all()
    return [_meta_dict(r) for r in rows]


async def _touch_last_used(sub: str) -> None:
    """记内存缓存;距上次 flush ≥30s 时内联批量落盘(不搞 fire-and-forget)。"""
    _last_used_cache[sub] = time.time()
    if time.time() - _last_flush < _LAST_USED_FLUSH_INTERVAL:
        return
    try:
        await flush_last_used()
    except Exception:  # 展示元数据,失败不影响请求
        _log.warning("flush_last_used failed", exc_info=True)


async def flush_last_used() -> None:
    """缓存全量批量 UPDATE(单语句 WHERE sub IN);成功才清缓存/推时间戳。"""
    global _last_flush
    subs = list(_last_used_cache)
    if not subs:
        return
    now = datetime.now(timezone.utc)
    sm = _session_maker()
    async with sm() as s:
        await s.execute(
            update(ApiKeyMeta).where(ApiKeyMeta.sub.in_(subs))
            .values(last_used_at=now))
        await s.commit()
    _last_used_cache.clear()
    _last_flush = time.time()


def _same_origin(request: Request) -> bool:
    """Origin(无则 Referer)是否指向本站(spec §4 + Q1-B)。

    目标集:IP_RADAR_PUBLIC_ORIGIN(设了才算,proxy 逃生口,比对含
    scheme)+ Host 头 + X-Forwarded-Host(取首个值)。对 Host/XFH 比对
    scheme 不敏感 —— https 页面打 http host(TLS 终结代理)是同源现实;
    对 PUBLIC_ORIGIN 比对 scheme。netloc 一律大小写不敏感;Referer 走
    同一 netloc 比对(等效前缀匹配,路径任意)。Origin/Referer 皆无 → False。
    """
    def _netloc(url: str) -> str:
        return (urlsplit(url).netloc or "").lower()

    def _scheme(url: str) -> str:
        return (urlsplit(url).scheme or "").lower()

    strict: list[tuple[str, str]] = []   # (scheme, netloc) — PUBLIC_ORIGIN
    loose: list[str] = []                # netloc-only — Host / X-Forwarded-Host
    pub = os.environ.get("IP_RADAR_PUBLIC_ORIGIN", "").strip()
    if pub:
        strict.append((_scheme(pub), _netloc(pub)))
    host = request.headers.get("host")
    if host:
        loose.append(host.lower())  # 裸 netloc(无 scheme),不进 urlsplit
    xfh = request.headers.get("x-forwarded-host", "")
    if xfh:
        loose.append(xfh.split(",")[0].strip().lower())

    source = request.headers.get("origin") or request.headers.get("referer", "")
    src_netloc = _netloc(source)
    if not src_netloc:  # 无 Origin/Referer,或 Origin: null
        return False
    if src_netloc in loose:
        return True
    return any(s == _scheme(source) and n == src_netloc for s, n in strict)


async def api_key_dep(request: Request) -> None:
    # Q1-B:无 GET 匿名分支 —— GET 与 batch 同规,Task 6 查询端点统一挂本依赖。
    # 顺序即语义:keys 失效时,任何 Authorization 头(含非 Bearer scheme,那
    # 不会进 verify_key)都先 503 —— 绝不带缺失 secret 走到 jwt.decode(KeyError)。
    if not keys_enabled() and request.headers.get("authorization"):
        raise ApiError(
            ErrorCode.admin_disabled,
            "API keys disabled: IP_RADAR_API_JWT_SECRET not set or <32 bytes")
    cred = await _bearer(request)
    if cred is not None:
        info = await verify_key(cred.credentials)
        request.state.api_key_sub = info["sub"]
        return
    if _same_origin(request):
        return
    raise ApiError(ErrorCode.unauthorized,
                   "API key required for programmatic access")
