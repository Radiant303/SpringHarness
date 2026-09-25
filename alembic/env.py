"""Alembic 环境：metadata 取自 spring_harness.cloud.db，URL 取自 cloud 配置。"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from spring_harness.cloud.db import Base
from spring_harness.core.config.settings import config as app_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL 从 cloud 配置读；% 是 configparser 的插值符，出现时要转义
database_url = app_config.cloud.database_url
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
