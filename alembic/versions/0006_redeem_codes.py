from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from spring_harness.cloud.db import MicrosecondDateTime

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP(6)")  # DATETIME(6) 的默认值 fsp 必须与列一致


def upgrade() -> None:
    # 兑换码：站长生成，用户兑换得 积分/存储配额增量/work 区上限增量。
    # 一次性：兑换走条件 UPDATE 抢占（status ACTIVE + 未过期 → REDEEMED），
    # 同时置 redeemed_by/redeemed_at/deleted_at（软删除）；code 唯一索引永不释放，
    # 软删行仍占位保证同码不重发。过期只在兑换时判定（expires_at），不建 EXPIRED 状态。
    op.create_table(
        "redeem_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("points_amount", sa.DECIMAL(20, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("storage_delta_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("work_quota_delta_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", MicrosecondDateTime(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("redeemed_by", sa.BigInteger(), nullable=True),
        sa.Column("redeemed_at", MicrosecondDateTime(), nullable=True),
        sa.Column("deleted_at", MicrosecondDateTime(), nullable=True),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["redeemed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_redeem_status_created", "redeem_codes", ["status", "created_at"])
    op.create_index("ix_redeem_created_by", "redeem_codes", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_redeem_created_by", table_name="redeem_codes")
    op.drop_index("ix_redeem_status_created", table_name="redeem_codes")
    op.drop_table("redeem_codes")
