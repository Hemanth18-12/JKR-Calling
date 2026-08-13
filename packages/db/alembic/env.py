from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

from jkr_db.base import Base  # noqa: E402
from jkr_db.models import *  # noqa: E402,F403 populates Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Migrations run DDL (CREATE TABLE/POLICY/ROLE) and must use the superuser
# role, never the RLS-enforced application role — see docs/DECISIONS/0004.
raw_url = os.environ.get(
    "MIGRATIONS_DATABASE_URL_SYNC",
    os.environ.get(
        "DATABASE_URL_SYNC",
        os.environ.get("DATABASE_URL", "postgresql+psycopg://jkr:jkr_local_dev@localhost:55432/jkr_ai_calling"),
    ),
)
if raw_url.startswith("postgresql+asyncpg://"):
    raw_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+psycopg://", 1)
elif raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+psycopg://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)

MIGRATIONS_DATABASE_URL_SYNC = raw_url
config.set_main_option("sqlalchemy.url", MIGRATIONS_DATABASE_URL_SYNC)



def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
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
