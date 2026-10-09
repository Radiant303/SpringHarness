from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 注册邮箱验证码：users 增加 email（接收验证码的 QQ 邮箱）。
    # 唯一但允许 NULL：历史行不回填；MySQL 唯一索引不约束多个 NULL，新注册用户必填。
    op.add_column("users", sa.Column("email", sa.String(length=128), nullable=True))
    op.create_unique_constraint("uk_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uk_users_email", "users", type_="unique")
    op.drop_column("users", "email")
