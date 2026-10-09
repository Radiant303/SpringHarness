from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from spring_harness.cloud.db import MicrosecondDateTime

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP(6)")  # DATETIME(6) 的默认值 fsp 必须与列一致


def upgrade() -> None:
    # 模型配置入库：站长在管理后台维护 provider 与模型，引擎直读（即改即生效），
    # 取代 config.toml 的 [providers]/[models]/default_model。
    # api_key 敏感：接口只写不读（GET 只回"是否已配置"）。
    op.create_table(
        "model_providers",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("api_key", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("base_url", sa.String(length=256), nullable=True),
        sa.Column("updated_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        # 注意命名：资费卡已占用 models 表名（ModelRateRow），模型定义用 model_definitions
        "model_definitions",
        # id = "provider/模型名"，全局唯一标识：前端模型 picker、计费 join key 都用它
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("max_context_size", sa.BigInteger(), nullable=False),
        sa.Column("max_output_size", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        # 能力/档位列表存 CSV（thinking,image_in,tool_use / low,medium,high）
        sa.Column("capabilities", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("support_efforts", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("default_effort", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("reasoning_key", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.Column("updated_at", MicrosecondDateTime(), nullable=False, server_default=_TIMESTAMP_DEFAULT),
        sa.ForeignKeyConstraint(["provider"], ["model_providers.name"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_defs_provider", "model_definitions", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_model_defs_provider", table_name="model_definitions")
    op.drop_table("model_definitions")
    op.drop_table("model_providers")
