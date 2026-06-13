"""Alembic 环境配置 — 支持 Docker 环境变量覆盖"""

import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Docker 环境：用 DB_HOST 环境变量覆盖 alembic.ini 中的 localhost
db_host = os.environ.get("DB_HOST", "")
if db_host:
    db_url = f"postgresql+psycopg2://chronicle:chronicle_secret@{db_host}:5432/chronicle"
    config.set_main_option("sqlalchemy.url", db_url)

# 导入所有模型让 Alembic 检测到
from app.storage.database import Base
import app.storage.models  # noqa

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
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
