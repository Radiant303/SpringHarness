from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from spring_harness.cloud.db import MicrosecondDateTime

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP(6)")  # DATETIME(6) 的默认值 fsp 必须与列一致


def upgrade() -> None:
    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("turn_id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("requests", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_wake", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id"),
    )
    op.create_index("ix_usage_user_time", "usage_records", ["user_id", "created_at"])
    op.create_index("ix_usage_session", "usage_records", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_usage_session", table_name="usage_records")
    op.drop_index("ix_usage_user_time", table_name="usage_records")
    op.drop_table("usage_records")
