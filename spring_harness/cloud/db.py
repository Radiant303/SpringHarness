from __future__ import annotations

import datetime
import threading

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from spring_harness.core.config.settings import config

STATUS_ACTIVE = "active"
STATUS_DELETED = "deleted"

DEFAULT_QUOTA_BYTES = 209_715_200  # 每用户 200MB 存储配额


def utc_now() -> datetime.datetime:
    """naive UTC 当前时间：DATETIME 列不带时区，统一按 UTC 存取。"""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class MicrosecondDateTime(DateTime):
    """带微秒精度的 DATETIME。

    MySQL 侧渲染为 DATETIME(6)（updated_at 排序、翻页游标快照都依赖微秒级区分度）；
    不能用 mysql.DATETIME：SQLite 上没有配套的字符串绑定处理器，测试库直接存不进
    datetime，而云端测试正是用 SQLite 跑的。
    """


@compiles(MicrosecondDateTime, "mysql")
def _compile_microsecond_datetime_mysql(type_, compiler, **kw) -> str:
    return "DATETIME(6)"


class Base(DeclarativeBase):
    pass


# BIGINT 主键在 SQLite 上不是 rowid 别名、拿不到自增；测试库（SQLite）换成 INTEGER。
_BigInt = BigInteger().with_variant(Integer, "sqlite")


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    quota_bytes: Mapped[int] = mapped_column(
        _BigInt, nullable=False, default=DEFAULT_QUOTA_BYTES,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)  # uuid4 字符串
    user_id: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workspace_path: Mapped[str] = mapped_column(String(512), nullable=False)
    current_segment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_ACTIVE)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_session_segment", "session_id", "segment_no", "id"),)

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("sessions.id"), nullable=False)
    segment_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 单条 ModelMessage 经 ModelMessagesTypeAdapter dump 后的 JSON 对象
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


# ---- engine / sessionmaker 工厂（懒初始化，双检锁）----

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_factory_lock = threading.RLock()


def get_engine() -> Engine:
    """全局 engine：URL 取自 cloud 配置；改写配置后需 reset_engine 才会重建。"""
    global _engine
    with _factory_lock:
        if _engine is None:
            _engine = create_engine(config.cloud.database_url, pool_pre_ping=True)
        return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """全局 sessionmaker：每次 DB 操作用独立 session（with ... as s），不持有长连接。"""
    global _session_factory
    with _factory_lock:
        if _session_factory is None:
            # expire_on_commit=False：提交后不触发刷新查询，detached 行属性可直接读
            _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
        return _session_factory


def reset_engine() -> None:
    """丢弃缓存的 engine/sessionmaker，下次获取时按当前 cloud 配置重建（测试用）。"""
    global _engine, _session_factory
    with _factory_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
