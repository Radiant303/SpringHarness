from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from spring_harness.cloud.db import MicrosecondDateTime

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP(6)")  # DATETIME(6) 的默认值 fsp 必须与列一致


def upgrade() -> None:
    # 角色：owner（站长）/ admin（管理员）/ user（用户）；存量用户全部落成 user
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=16), nullable=False, server_default=sa.text("'user'")),
    )
    # 账号状态：active / disabled
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
    )
    # 运行时系统设置（站长可在后台修改）；当前只有 registration_open 一个键
    op.create_table(
        "system_settings",
        sa.Column("setting_key", sa.String(length=64), nullable=False),
        sa.Column("setting_value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.PrimaryKeyConstraint("setting_key"),
    )
    op.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES ('registration_open', 'true')")


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_column("users", "status")
    op.drop_column("users", "role")
