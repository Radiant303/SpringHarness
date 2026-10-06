from __future__ import annotations

import datetime
import threading
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
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
    # 角色：owner（站长）/ admin（管理员）/ user（用户）
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    # 账号状态：active / disabled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # 单工作区上限的每用户覆盖值（NULL = 跟随全局默认）
    work_quota_bytes: Mapped[int | None] = mapped_column(_BigInt, nullable=True)
    # 积分余额：一切变动经 points_ledger 流水 + 网关事务内更新完成
    points_balance: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class WorkRow(Base):
    """项目（work）：工作区的隔离单元，目录 = {data-root}/works/{id}，同 work 的会话共享。"""

    __tablename__ = "works"
    __table_args__ = (Index("ix_works_user", "user_id"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)  # uuid4 字符串
    user_id: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_sessions_work", "work_id"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)  # uuid4 字符串
    user_id: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    work_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("works.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    # 单条消息的 JSON 序列化对象
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class UsageRecordRow(Base):
    """一轮对话的模型 token 消耗（计费底账）。

    turn_id 全局唯一：MQ 重投/DLQ 重放导致重复消费时撞唯一键即视为已入账。
    只存原始 token 量与 model_name，不存金额。
    """

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_user_time", "user_id", "created_at"),
        Index("ix_usage_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    # 雪花 ID 或 wake-xxx（催醒轮本地生成）
    turn_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    # 本轮最后一次模型请求的模型；纯错误轮可能没有任何模型请求
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 含 cache_read/cache_write（inclusive 桶）
    input_tokens: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # finished/cancelled/error
    is_wake: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class ModelRateRow(Base):
    """模型资费卡：每项费率单位 = 积分/百万 tokens；default 行是兜底卡。"""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=False)  # 雪花，网关侧生成
    model_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    input_points: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    cache_read_points: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    cache_write_points: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    output_points: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class PointsHoldRow(Base):
    """积分预扣：turn 派发时建立，结算（SETTLED）/释放（RELEASED）二选一收口。"""

    __tablename__ = "points_holds"
    __table_args__ = (Index("ix_holds_status_created", "status", "created_at"),)

    turn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="HELD")
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )
    settled_at: Mapped[datetime.datetime | None] = mapped_column(MicrosecondDateTime, nullable=True)


class PointsLedgerRow(Base):
    """积分流水（append-only）：余额永远可由流水推出；(type, ref_id) 唯一作幂等锚。"""

    __tablename__ = "points_ledger"
    __table_args__ = (
        Index("ix_ledger_user", "user_id", "id"),
        # ref_id 为 NULL 的行不受唯一约束（MySQL/SQLite 均视 NULL 互不相等）
        UniqueConstraint("type", "ref_id"),
    )

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=False)  # 雪花，网关侧生成
    user_id: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    change_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operator_id: Mapped[int | None] = mapped_column(
        _BigInt, ForeignKey("users.id"), nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        MicrosecondDateTime, nullable=False, default=utc_now,
    )


class RedeemCodeRow(Base):
    """兑换码：一次性，兑换经条件 UPDATE 抢占并置软删除；过期只在兑换时判定。"""

    __tablename__ = "redeem_codes"
    __table_args__ = (
        Index("ix_redeem_status_created", "status", "created_at"),
        Index("ix_redeem_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=False)  # 雪花 ID
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    points_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 6), nullable=False, default=0)
    storage_delta_bytes: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    work_quota_delta_bytes: Mapped[int] = mapped_column(_BigInt, nullable=False, default=0)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(MicrosecondDateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=False)
    redeemed_by: Mapped[int | None] = mapped_column(_BigInt, ForeignKey("users.id"), nullable=True)
    redeemed_at: Mapped[datetime.datetime | None] = mapped_column(MicrosecondDateTime, nullable=True)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(MicrosecondDateTime, nullable=True)
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
