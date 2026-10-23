import os

from alembic import context
from sqlalchemy import create_engine

from hfm.adapters.postgres.orm import Base
from hfm.platform.checkpointer import libpq_dsn, setup_checkpoint_tables

target_metadata = Base.metadata
url = os.environ["DATABASE_URL"]


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
    setup_checkpoint_tables(libpq_dsn(url))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
