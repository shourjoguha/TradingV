# Laptop backend setup

Run the full TradingView analysis backend on the M3 MacBook. Paired with the Railway replica — ticker sync auto-runs after each job (see [sync.md](../modules/sync.md)).

## One-time

1. **Start dockerized Postgres (port 5439):**
   ```bash
   cd "/Users/shourjosmac/Documents/Claude/TradingView "
   docker compose -f docker-compose.laptop.yml up -d
   ```
   First boot creates a named volume `tradingview_laptop_pg`. Reset with
   `docker compose -f docker-compose.laptop.yml down -v`.

2. **Create your env file:**
   ```bash
   cp .env.laptop.example .env.laptop
   # Edit if you rotate the generated laptop API_KEY or Postgres password.
   ```
   The template is pre-filled with your Railway peer URL + Railway key.

3. **Python deps + migrations:**
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   set -a; source .env.laptop; set +a
   alembic upgrade head
   ```

   `alembic upgrade head` is **mandatory** before booting `uvicorn`. The
   lifespan no longer auto-creates tables via
   `Base.metadata.create_all` (the parity-net was masking schema drift —
   see ADR-013/014 and the resolved backlog item from 2026-05-02). After
   a `git pull` that brought in a new migration, run `alembic upgrade
   head` again before restarting; otherwise boot logs a loud
   `[schema] DB at revision X; latest on disk is Y. Run alembic upgrade
   head ...` warning and skips the missing schema.

### Env vars worth knowing

- `DISABLE_LIFESPAN_BACKGROUND_TASKS=1` — skips every `asyncio.create_task`
  spawned by `app/main.py` lifespan (queue worker, accuracy evaluator,
  drift detector, daily digest, market-data refresh, opportunity tick,
  macro ingestion, hypothesis tick, research weekly). Set automatically
  in `tests/conftest.py` so pytest fixtures tear down cleanly. **Don't
  set in production.**

## Kronos weights (one-time, ~531MB)

```bash
source venv/bin/activate
pip install -r requirements-kronos.txt
HF_HUB_CACHE="$PWD/hf-cache" python3 -c "from huggingface_hub import snapshot_download; \
  [snapshot_download(r) for r in ['NeoQuasar/Kronos-Tokenizer-base','NeoQuasar/Kronos-base', \
  'NeoQuasar/Kronos-Tokenizer-2k','NeoQuasar/Kronos-small','NeoQuasar/Kronos-mini']]"
```

Cached in `./hf-cache/` (gitignored). `.env.laptop` sets `HF_HUB_CACHE="/Users/shourjosmac/Documents/Claude/TradingView /hf-cache"` (absolute path, so uvicorn reuses regardless of launch CWD). Re-run only if upstream NeoQuasar pushes new weights.

## Video-vision deps (one-time, Apple Silicon)

Optional but required for the L2 OCR / L3 caption / structured chart-extraction layers on the channel poller. See [`.claude/modules/video_vision.md`](../modules/video_vision.md) for the full pipeline.

```bash
# Tesseract system binary (~50MB) — required for L2 OCR.
brew install tesseract

# MLX wheels — required for L3 captions + Whisper-MLX acceleration on M-series.
# Already in requirements.txt; the `mlx-vlm` install pulls 200+ deps.
source venv/bin/activate
pip install -r requirements.txt  # picks up mlx-whisper + mlx-vlm + pytesseract
```

**First-run model downloads (lazy, ~3GB total):**
- `whisper-small` MLX checkpoint (~500MB) — first ASR call
- `Qwen2-VL-2B-Instruct-4bit` (~1GB) — first chart caption call (L3)

Both cached at `~/.cache/huggingface/`. No action required; first ingest tick will block ~2-3 min on the downloads.

**Env overrides:**
- `FORCE_TORCH_WHISPER=1` — disables MLX, uses openai-whisper torch path (debugging / non-M3)
- `DISABLE_MLX_VLM=1` — disables L3 captioning entirely

## Daily boot

```bash
cd "/Users/shourjosmac/Documents/Claude/TradingView "
docker compose -f docker-compose.laptop.yml up -d      # Postgres
source venv/bin/activate
set -a; source .env.laptop; set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` is required so Railway (once a tunnel is set up) or a LAN frontend can reach `http://10.0.0.1:8000`.

## Verify

```bash
curl http://localhost:8000/health
curl -H "X-API-Key: $API_KEY" http://localhost:8000/v1/tickers
```

## Run a job end-to-end

```bash
curl -X POST http://localhost:8000/v1/analysis/run \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tickers":["AAPL"],"intervals":["1d"]}'
```

Job finishes → laptop enqueues `AAPL` → background drain POSTs to `https://tradingv-production.up.railway.app/v1/tickers`. Check Railway:
```bash
curl -H "X-API-Key: <railway-key>" https://tradingv-production.up.railway.app/v1/tickers
```

## If the sync fails

Outbox rows stay pending with backoff. Inspect + retry:
```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/v1/sync/outbox?status=pending"
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8000/v1/sync/retry
```

## Frontend (optional)

The Vite + React UI lives in `frontend/`. With the backend running on `:8000`:

```bash
cd "/Users/shourjosmac/Documents/Claude/TradingView /frontend"
cp .env.example .env.local       # fill in VITE_LAPTOP_KEY + VITE_RAILWAY_KEY (first time only)
npm install                      # first time only
npm run dev                      # http://localhost:3000
```

Vite proxies `/v1` and `/health` to `localhost:8000` (no CORS hassle). See [frontend/README.md](../frontend/README.md) for the full doc tree, [frontend/dev-workflow.md](../frontend/dev-workflow.md) for daily commands.

## Known constraints

- Railway → laptop push won't work until you add a public tunnel (Cloudflare/Tailscale) — LAN IPs aren't routable from Railway. Laptop → Railway works today.
- Kronos-base CPU inference on M3 is ~15–30s per prediction. Expected.
- `MAX_CONCURRENT_JOBS=1` — a second `/v1/analysis/run` while one is running returns 429 `{"detail": "at_capacity"}`.
