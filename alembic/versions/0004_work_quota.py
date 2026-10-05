from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 单工作区上限的每用户覆盖值（NULL = 跟随全局默认）
    op.add_column("users", sa.Column("work_quota_bytes", sa.BigInteger(), nullable=True))
    # 全局默认单 work 上限（20MB）
    op.execute(
        "INSERT INTO system_settings (setting_key, setting_value) VALUES ('work_max_bytes', '20971520')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE setting_key = 'work_max_bytes'")
    op.drop_column("users", "work_quota_bytes")
