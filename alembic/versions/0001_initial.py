from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from spring_harness.cloud.db import MicrosecondDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP(6)")  # DATETIME(6) 的默认值 fsp 必须与列一致


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("209715200")),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("workspace_path", sa.String(length=512), nullable=False),
        sa.Column("current_segment", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.Column("updated_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_user_updated", "sessions", ["user_id", "updated_at"])
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.CHAR(length=36), nullable=False),
        sa.Column("segment_no", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_session_segment", "messages", ["session_id", "segment_no", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_session_segment", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_sessions_user_updated", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
