# backend/ipdb/_auth.py — 认证数据层:模型/引擎/引导(spec §6/§10)
"""fastapi-users User/AccessToken 模型、惰性 sqlite 引擎、管理员引导。

IP_RADAR_AUTH_DB 环境变量可覆盖 db 路径(测试逐用例隔离);缺省落在
_registry 数据目录(_STATE_PATH.parent)。引擎/会话工厂按解析出的路径惰性
创建并缓存:生产单路径 → 单实例;不绑定模块导入期状态。
"""
import os
import secrets
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseUserTableUUID,
    SQLAlchemyUserDatabase,
)
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyAccessTokenDatabase,
    SQLAlchemyBaseAccessTokenTableUUID,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from . import _registry


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    """用户/管理员表;列(id/email/hashed_password/is_* )全部继承基类。"""


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    """fastapi-users 会话表;token/created_at/user_id 全部继承基类。"""


def _auth_db_path() -> Path:
    env = os.environ.get("IP_RADAR_AUTH_DB")
    if env:
        return Path(env)
    return _registry._STATE_PATH.parent / "auth.db"


# ponytail: 按路径字符串缓存引擎/会话工厂;测试多路径各一份,生产单路径单实例
_engines: dict[str, AsyncEngine] = {}
_session_makers: dict[str, async_sessionmaker[AsyncSession]] = {}


def _engine() -> AsyncEngine:
    path = _auth_db_path()
    key = str(path)
    eng = _engines.get(key)
    if eng is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # ponytail: NullPool(每会话新连接)—— sqlite 文件库 + admin 量级流量,
        # 连接池跨 event loop 复用 aiosqlite 连接必炸(TestClient 每请求新 loop);
        # 若未来多用户高并发再评估池化 + 单 loop 架构
        eng = create_async_engine(
            f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
        _engines[key] = eng
    return eng


def _session_maker() -> async_sessionmaker[AsyncSession]:
    key = str(_auth_db_path())
    sm = _session_makers.get(key)
    if sm is None:
        sm = async_sessionmaker(_engine(), expire_on_commit=False)
        _session_makers[key] = sm
    return sm


async def init_auth_db() -> None:
    """create_all,幂等。"""
    async with _engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_maker()() as session:
        yield session


async def get_user_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase, None]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


async def get_superuser_count() -> int:
    async with _session_maker()() as s:
        return (
            await s.scalar(
                select(func.count()).select_from(User).where(User.is_superuser)
            )
            or 0
        )


_admin_flag = False


def admin_configured() -> bool:
    """bootstrap_admin() 见到/创建过 superuser 后为 True;Task 2 的同步 FastAPI 依赖读此标志。"""
    return _admin_flag


async def bootstrap_admin() -> None:
    """无 superuser 且 IP_RADAR_ADMIN_PASSWORD 已设 → 创建 admin;已有 superuser 即跳过。"""
    global _admin_flag
    if await get_superuser_count() > 0:
        _admin_flag = True
        return
    pwd = os.environ.get("IP_RADAR_ADMIN_PASSWORD", "")
    if not pwd:
        _admin_flag = False
        return
    email = os.environ.get("IP_RADAR_ADMIN_EMAIL", "admin@ipradar.local")
    hashed = PasswordHelper().hash(pwd)
    async with _session_maker()() as s:
        s.add(
            User(
                email=email,
                hashed_password=hashed,
                is_superuser=True,
                is_active=True,
            )
        )
        await s.commit()
    _admin_flag = True


# ── Task 2:fastapi-users 接线(spec 2026-09-21 §6)──
# 登录 = OAuth2 密码表单换 cookie 会话(DatabaseStrategy 写 accesstoken 表,
# 无 JWT);SECRET 只供 reset/verify token(对应路由未挂),留默认以便后续任务。
import uuid

from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    UUIDIDMixin,
    schemas as fu_schemas,
)
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
)
from fastapi_users.authentication.strategy.db import (
    AccessTokenDatabase,
    DatabaseStrategy,
)

# 兜底 per-process 随机(审计 F7):本 SECRET 只喂未挂载的 fastapi-users
# reset/verify token secret;API key 层走独立 env 门(keys_enabled),
# 仓库里不留已知常量,缺 env 也不炸默认自部署的模块导入。
SECRET = os.environ.get("IP_RADAR_API_JWT_SECRET") or secrets.token_urlsafe(48)

_ADMIN_COOKIE = "ipradar_admin"
_COOKIE_LIFETIME = 7 * 24 * 3600
_cookie_secure = os.environ.get("IP_RADAR_INSECURE_COOKIE", "") != "1"


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET


class UserRead(fu_schemas.BaseUser[uuid.UUID]):
    """对外用户形状;GET/PATCH /api/users/me 的响应模型。"""

    # bootstrap 默认 admin@ipradar.local 等保留 TLD 会被基类的 EmailStr 拒绝;
    # 读取侧只回显库中已有值,放宽为 str(写入侧 UserUpdate 仍走 EmailStr)
    email: str


class UserUpdate(fu_schemas.BaseUserUpdate):
    """/me 可改字段;PATCH /api/users/me 的请求模型。"""


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    yield UserManager(user_db)


def get_cookie_strategy(
    access_token_db: AccessTokenDatabase = Depends(get_access_token_db),
) -> DatabaseStrategy:
    return DatabaseStrategy(access_token_db, lifetime_seconds=_COOKIE_LIFETIME)


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=CookieTransport(
        cookie_name=_ADMIN_COOKIE,
        cookie_max_age=_COOKIE_LIFETIME,
        cookie_secure=_cookie_secure,
        cookie_httponly=True,
        cookie_samesite="lax",
    ),
    get_strategy=get_cookie_strategy,
)

app_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# verified=False:bootstrap 的 admin 沿用基类默认 is_verified=False,
# 不开任何 require-verification 行为(Task 1 复审裁定)。
# fastapi-users 15 已移除 FastAPIUsers.current_superuser,超管门 =
# current_user(superuser=True)(401 未登录 / 403 非超管)。
current_superuser = app_users.current_user(
    active=True, verified=False, superuser=True)
