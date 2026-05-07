from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import SETTINGS
from app.core.db import Base

# Import models so they register on Base.metadata
from app.alerts import models as _alert_models  # noqa: F401
from app.tickers import models as _ticker_models  # noqa: F401
from app.market_data import models as _ohlcv_models  # noqa: F401
from app.analysis import models as _analysis_models  # noqa: F401
from app.sync import models as _sync_models  # noqa: F401
from app.labels import models as _labels_models  # noqa: F401
from app.predictions import models as _predictions_models  # noqa: F401
from app.schedule import models as _schedule_models  # noqa: F401
from app.watchlist import models as _watchlist_models  # noqa: F401
from app.hypotheses import models as _hypothesis_models  # noqa: F401
from app.trades import models as _trades_models  # noqa: F401
from app.tv_context import models as _tv_context_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_db_url() -> str:
    url = SETTINGS.DATABASE_URL
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


config.set_main_option("sqlalchemy.url", _sync_db_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
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
