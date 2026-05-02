import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("API_KEY", "test-key")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.db as core_db
from app.core.db import Base

# Import every module's models so Base.metadata knows about them BEFORE
# create_all runs. Order matters: app.main imports them transitively, but
# importing explicitly here is cheap and keeps the fixture self-contained.
from app.alerts import models as _alerts_models  # noqa: F401, E402
from app.analysis import models as _analysis_models  # noqa: F401, E402
from app.market_data import models as _market_data_models  # noqa: F401, E402
from app.sync import models as _sync_models  # noqa: F401, E402
from app.tickers import models as _tickers_models  # noqa: F401, E402
from app.labels import models as _labels_models  # noqa: F401, E402
from app.predictions import models as _predictions_models  # noqa: F401, E402
from app.schedule import models as _schedule_models  # noqa: F401, E402
from app.watchlist import models as _watchlist_models  # noqa: F401, E402
from app.accuracy import models as _accuracy_models  # noqa: F401, E402
from app.opportunities import models as _opportunities_models  # noqa: F401, E402
from app.trades import models as _trades_models  # noqa: F401, E402
from app.market_data import derived as _derived_models  # noqa: F401, E402
from app.queue import models as _queue_models  # noqa: F401, E402
from app.macro import models as _macro_models  # noqa: F401, E402
from app.boards import models as _boards_models  # noqa: F401, E402
from app.hypotheses import models as _hypothesis_models  # noqa: F401, E402


@pytest_asyncio.fixture
async def client():
    # Override engine with an in-memory SQLite per test.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # SQLite doesn't enforce FK by default; turn it on so ON DELETE
    # CASCADE behaves like Postgres in prod.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    core_db.engine = engine
    core_db.SessionLocal = session_maker

    # Tests-only schema bootstrap from models. Production / laptop now go
    # through alembic; lifespan no longer auto-creates tables (see
    # ADR-013/014 + the resolved backlog entry from 2026-05-02). This is
    # the ONLY place create_all should run.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Import after env + engine override so routes bind correctly.
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
