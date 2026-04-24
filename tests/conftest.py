import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("API_KEY", "test-key")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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


@pytest_asyncio.fixture
async def client():
    # Override engine with an in-memory SQLite per test.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    core_db.engine = engine
    core_db.SessionLocal = session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Import after env + engine override so routes bind correctly.
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
