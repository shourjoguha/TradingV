# TradingView Webhook Service

Lean backend for catching TradingView alerts.

## Files

- `main.py`: FastAPI app. Has `/webhook` (save) and `/alerts` (read) routes. Uses async SQLAlchemy.
- `config.py`: Loads `DATABASE_URL`, `API_KEY`, `PORT` via `pydantic-settings`.
- `requirements.txt`: Python deps (FastAPI, SQLAlchemy, asyncpg, etc.).
- `Procfile`: Start command for Railway (`web: uvicorn main:app ...`).
- `railway.toml`: Railway config.

## Setup (Local)

1. Create venv: `python -m venv venv`
2. Activate: `source venv/bin/activate`
3. Install: `pip install -r requirements.txt`
4. Set env vars: `DATABASE_URL` and `API_KEY`.
5. Run: `uvicorn main:app --reload`

## Setup (Railway)

1. Create Railway project.
2. Add Postgres plugin.
3. Deploy this repo.
4. Set `API_KEY` in Railway vars.
5. Railway auto-sets `DATABASE_URL` and `PORT`.