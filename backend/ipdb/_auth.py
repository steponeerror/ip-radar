# backend/ipdb/_auth.py — 认证数据层:模型/引擎/引导(spec §6/§10)
"""fastapi-users User/AccessToken 模型、惰性 sqlite 引擎、管理员引导。

IP_RADAR_AUTH_DB 环境变量可覆盖 db 路径(测试逐用例隔离);缺省落在
_registry 数据目录(_STATE_PATH.parent)。引擎/会话工厂按解析出的路径惰性
创建并缓存:生产单路径 → 单实例;不绑定模块导入期状态。
"""
import os
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
        eng = create_async_engine(f"sqlite+aiosqlite:///{path}")
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
