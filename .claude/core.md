# Core (`app/core/`)

Shared plumbing. No business logic here.

## `config.py`
`pydantic-settings` loads `DATABASE_URL`, `API_KEY`, `PORT` from env / `.env`. Exported as `SETTINGS`. `extra="ignore"` so unknown env vars don't crash boot.

## `db.py`
- Normalizes `DATABASE_URL` → async driver: `postgres://` and `postgresql://` rewritten to `postgresql+asyncpg://`.
- Exposes `engine`, `SessionLocal` (async sessionmaker), `Base` (DeclarativeBase).
- **Import rule**: consumers should use `from app.core import db as _db` then `_db.SessionLocal()`. Binding `SessionLocal` at module import breaks test overrides.

## `auth.py`
Single API-key dep: `verify_api_key` checks `X-API-Key` against `SETTINGS.API_KEY`. Returns 403 on mismatch. Missing header returns 401 (FastAPI default).

## Decisions
- No dependency injection container. FastAPI `Depends` is sufficient.
- Async SQLAlchemy 2.0 syntax (`Mapped[...]`, `mapped_column`). No legacy `declarative_base()`.
- Sessions are scoped per-request (`async with SessionLocal()`), not per-app.
