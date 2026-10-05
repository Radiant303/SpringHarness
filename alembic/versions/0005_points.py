from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from spring_harness.cloud.db import MicrosecondDateTime

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP(6)")  # DATETIME(6) 的默认值 fsp 必须与列一致


def upgrade() -> None:
    # 积分余额：一切变动经 points_ledger 流水 + 事务内更新完成，没有直接 set 的入口
    op.add_column(
        "users",
        sa.Column("points_balance", sa.DECIMAL(20, 6), nullable=False, server_default=sa.text("0")),
    )
    # 存量站长补初始积分（新装由 AuthService 首用户引导发 1000）
    op.execute("UPDATE users SET points_balance = 1000 WHERE role = 'owner'")

    # 模型资费卡：每项费率单位 = 积分/百万 tokens；default 行是兜底卡
    # （派发预扣估算用它；结算按 usage 的实际 model_name 精确匹配，匹配不到回落它）
    op.create_table(
        "models",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("input_points", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("cache_read_points", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("cache_write_points", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("output_points", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.Column("updated_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_name"),
    )
    # 兜底卡：按预扣档位（9w 缓存读 + 1w 输入 + 2w 输出）估算 ≈0.79 积分/轮
    op.execute(
        "INSERT INTO models (id, model_name, input_points, cache_read_points, cache_write_points,"
        " output_points, enabled) VALUES (1, 'default', 10, 1, 10, 30, 1)"
    )

    # 预扣：turn 派发时建立，结算/释放二选一收口；状态迁移走条件 UPDATE 防并发双花
    op.create_table(
        "points_holds",
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="HELD"),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.Column("settled_at", MicrosecondDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("turn_id"),
    )
    op.create_index("ix_holds_status_created", "points_holds", ["status", "created_at"])

    # 积分流水（append-only）：余额永远可由流水推出；(type, ref_id) 唯一作幂等锚
    # （ref_id 为 NULL 的行不受唯一约束，MySQL/SQLite 均视 NULL 互不相等）
    op.create_table(
        "points_ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("change_amount", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("balance_after", sa.DECIMAL(20, 6), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type", "ref_id"),
    )
    op.create_index("ix_ledger_user", "points_ledger", ["user_id", "id"])

    # 预扣预估档位（tokens）：站长可在系统设置运行时调整
    op.execute(
        "INSERT INTO system_settings (setting_key, setting_value) VALUES"
        " ('billing.est_cache_read_tokens', '90000'),"
        " ('billing.est_input_tokens', '10000'),"
        " ('billing.est_output_tokens', '20000')"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE setting_key IN"
        " ('billing.est_cache_read_tokens', 'billing.est_input_tokens', 'billing.est_output_tokens')"
    )
    op.drop_index("ix_ledger_user", table_name="points_ledger")
    op.drop_table("points_ledger")
    op.drop_index("ix_holds_status_created", table_name="points_holds")
    op.drop_table("points_holds")
    op.drop_table("models")
    op.drop_column("users", "points_balance")
