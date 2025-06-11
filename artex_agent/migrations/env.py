import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to Python path to find artex_agent.src
# This assumes 'migrations' directory is at the root of 'artex_agent' project.
# If your project structure is artex_agent/artex_agent/migrations, adjust accordingly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from artex_agent.src.database_models import Base # Target metadata for autogenerate
# Ensure other models are imported if they are not automatically picked up via Base's metadata
# from artex_agent.src import database_models # Could also do this if all models are in __init__.py

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def get_url():
    # Get DATABASE_URL from environment variable, replace 'DB_URL_FROM_ENV_VAR_IN_ENV_PY'
    # in alembic.ini if it was set there as a placeholder.
    # If alembic.ini has sqlalchemy.url = %(DB_URL)s, then config.get_main_option("sqlalchemy.url")
    # would try to use an environment variable named DB_URL for interpolation.
    # For direct os.getenv usage:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set for Alembic.")

    # Alembic's default script runs synchronously. If using an async dialect like aiomysql,
    # ensure the synchronous connection part of the URL is compatible or use a sync driver.
    # For aiomysql, the sync equivalent is pymysql.
    # If DATABASE_URL is "mysql+aiomysql://...", it might work if aiomysql provides a sync shim
    # or if Alembic's context can handle it. Often, it's easier to provide a sync URL for Alembic.
    # For example, if DATABASE_URL="mysql+aiomysql://user:pass@host/db",
    # a sync_url could be "mysql+pymysql://user:pass@host/db".
    # However, let's try with the direct URL first, as modern Alembic might support it.
    # If not, this is the place to adjust it.
    # print(f"DEBUG: Alembic using DB URL: {db_url}") # For debugging
    return db_url

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # compare_type=True, # Enable type comparison
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # compare_type=True, # Enable type comparison
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get database URL from environment variable
    db_url = get_url()

    # Create an asyncio engine
    # The connectable should be an asyncio engine
    connectable = create_async_engine(
        db_url,
        poolclass=pool.NullPool, # Use NullPool for async context
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

# Ensure dotenv is loaded if running alembic commands from CLI directly
# and .env is not sourced by the shell
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
# This ensures that when alembic CLI runs env.py, it loads .env from the project root.
# Note: If alembic.ini uses %(ENV_VAR)s, the shell environment needs to have it.
# This load_dotenv() call here makes it available to os.getenv() within this script.
print(f"DEBUG migrations/env.py: DATABASE_URL from env: {os.getenv('DATABASE_URL')}")
