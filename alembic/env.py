import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine
from sqlmodel import SQLModel
from alembic import context

# Import all models so SQLModel metadata is populated
from app.models.lead import Lead  # noqa
from app.models.call import Call  # noqa
from app.models.document import Document  # noqa
from app.models.follow_up import FollowUp  # noqa
from app.models.lor import LOR  # noqa

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Override sqlalchemy.url with DATABASE_URL env var if present
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Railway provides postgres:// but SQLAlchemy requires postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
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
