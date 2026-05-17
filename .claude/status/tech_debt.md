# Active tech debt

Things we know about, deferred on purpose, with the trigger to revisit. Different from [backlog.md](backlog.md): backlog tracks _features_ deferred for product reasons; tech_debt tracks _code cruft_ deferred for engineering reasons. When in doubt: if removing it would feel like a feature, it's backlog. If removing it would feel like a chore, it's here.

## Canary-Qwen 2.5B as alternate video ASR (uninstalled, revisit on better hardware)

**What:** Tried swapping default video transcription to NVIDIA Canary-Qwen 2.5B (English-only, LLM-fused decoder, top of HF open-ASR leaderboard). Two blockers:
1. ~5GB model + ~7-10 min cold load thrashed M3 16GB swap alongside normal workload. Solo debug spike on synthetic TTS audio also produced *degenerate* output (3 tokens "Transcript" + EOS) — couldn't validate real-speech behaviour due to memory pressure on follow-ups.
2. Even functional, ~6× real-time on MPS (~50 min for a 30-min podcast vs ~8 min for Whisper-small).

**Cleanup (2026-05-06):** removed the 4.8GB HF cache + uninstalled `nemo_toolkit`, `lhotse`, `pytorch_lightning`, `peft`, `librosa`, `wandb`, `numba`/`llvmlite` (later restored — Whisper depends), `onnx`, `tensorboard`, `pyarrow`, `datasets`, `accelerate`, `sentry-sdk`, `gitpython`. `transcribe_canary()` and `--asr` flag stripped from `tools/vault_indexer/ingest/ingest_video.py`. `requirements.txt` was never modified for Canary, so no rollback needed there.

**How to apply when ready:**
- Operator upgrades to 32GB+ Mac OR runs ingest on a CUDA-equipped machine.
- Re-install: `pip install "nemo_toolkit[asr]"` (will downgrade `transformers` to 4.x — verify Kronos still works).
- Re-spike: load Canary, transcribe a real 60s human-speech clip on MPS+CPU. Confirm sensible output (NOT just "Transcript").
- Restore `transcribe_canary()` + ffmpeg-chunking helpers + `--asr` flag in `ingest_video.py`. The 2026-05-06 commit history has the full implementation if needed as reference.
- Alternative path: try the CoreML-compiled variant (`phequals/canary-qwen-2.5b-coreml-fp16` on HF) — may run faster on Apple Silicon than NeMo's PyTorch path. Different API; would be a separate transcribe function.

**Trigger to revisit:** operator complains Whisper-small transcript is missing crucial number/jargon precision and bumping to `--whisper-model medium` or `large-v3` doesn't fix it, OR hardware upgrade.

---

## Railway: torch/Kronos still installed even with KRONOS_ENABLED=false

**What:** Railway image bundles `torch`, `huggingface_hub`, `einops`, `safetensors` (full Kronos stack ~500MB) even though `KRONOS_ENABLED=false` on Railway. Python imports cost RAM at idle even when toggle is off — those packages get pulled into module space at any code path that touches `app/kronos/`.

**Why deferred:** Stripping requires a separate `requirements-laptop.txt` + Railway-specific Dockerfile (or pip install branching by env). Kept on Railway today because `RAILWAY_FALLBACK_ENABLED` *could* be flipped to `True` and need Kronos. Most of operator's bill is RAM ($2.46/wk) and torch is the fattest import.

**How to apply when ready:**
- Decide: is `RAILWAY_FALLBACK_ENABLED` ever going to be true?
  - **No** → split requirements: `requirements.txt` slim, `requirements-laptop.txt` adds Kronos. Railway image drops ~500MB of torch RAM. Estimated savings: ~$5-7/mo (about 50% of RAM line).
  - **Yes** → lazy-load: don't import `torch` at startup. Import only inside `kronos.real_adapter.activate()`. Cold start 30-60s on first fallback fire — acceptable for once-a-day backfill.

**Trigger to revisit:** Railway bill review after the lifespan-loop gate (this commit) lands — if RAM line still dominates, this is the next lever.

---

## TV-context: hypothesis tickers field

**What:** `hypothesis.requires_tv_context=True` can't be auto-evaluated during the daily tick because `Hypothesis` has no first-class ticker list — only a free-form `axis` (e.g. `equity:AAPL`). Today the gate only fires on `/v1/research/ask` when the operator passes `tickers` explicitly.

**Why deferred:** Adding `Hypothesis.tickers` (JSON list) is a real schema change; the gate already works for the common path (operator-driven research). Daily-tick auto-flag is "nice to have," not blocking.

**How to apply when ready:**
- Migration: `ALTER TABLE hypothesis ADD COLUMN tickers JSON DEFAULT '[]'`
- Backfill: parse `axis` strings; for `claim_type='single_name'` extract the ticker from the axis suffix.
- `app/hypotheses/service.run_daily_tick`: when `requires_tv_context=True` and `tickers` non-empty and `tv_context.recent_for_ticker(...)` empty, write evaluation row with `status_after='needs_context'`. Add this status to the CHECK constraint.
- Surface "needs_context" badge on hypothesis cards.

**Trigger to revisit:** operator complains they're attaching context after-the-fact instead of being prompted, OR the daily tick logs a hypothesis going stale that a context-gate would have caught.

**Partial mitigation (2026-05-17):** Phase 3 of `tv-context-decision-engine-enrichment` shipped `tv_context_count_since` + `tv_context_stance_count_since` invalidator DSL ops. Operators can author per-hypothesis invalidators reading `HypothesisTVContextLink` directly — no `Hypothesis.tickers` column needed for the link-based path. The original auto-flag-on-empty-context concern still applies for hypotheses that lack an invalidator op; deferred as before.

> **Review cadence:** monthly. Walk every entry — has its trigger fired? If yes, schedule the cleanup. Once this file crosses ~10 active entries, archive RESOLVED ones to `.claude/tech_debt-archive.md` to keep the active list scannable. Update the entry the moment a phase ships and intentionally leaves cruft behind — a stale tech_debt list is worse than none.

---

## `submit_queue` schedule_config columns (post-Phase queue)

**What:** `schedule_config.pending_run` and `schedule_config.retry_minutes` columns are unused after the job submission queue ships. The `last_run_status='deferred_429'` enum value becomes unreachable (queue can't 429).

**Why deferred:** Migration 0017 already creates the queue table; adding column-drop migrations is more rollback risk than the cruft is worth. Rows continue to be written with `pending_run=false`, `retry_minutes=<default>` — harmless.

**How to apply when ready:**
- New migration to `ALTER TABLE schedule_config DROP COLUMN pending_run, DROP COLUMN retry_minutes`.
- Remove read/write of those fields in `app/schedule/service.py` + `app/schedule/runner.py`.
- Remove "deferred_429" branch from any frontend page that surfaces `last_run_status`.

**Trigger to revisit:** another schedule_config schema change comes up — bundle this in.

---

## `app.analysis.concurrency` slot gate (post-Phase queue)

**What:** `app/analysis/concurrency.py` (`AtCapacityError`, `acquire_slot`) is kept inside `analysis.service.submit_run` after the queue ships. Belt-and-braces: queue worker is single-flight, so the slot gate should never fire. If it does, something's wrong upstream.

**Why deferred:** Cheap insurance. Removing it now means trusting the queue serialization completely; we want a few weeks of clean operation before that.

**How to apply when ready:**
- Delete `app/analysis/concurrency.py`.
- Remove `async with concurrency.acquire_slot()` in `app/analysis/service.py::submit_run`.
- Remove imports + the `AtCapacityError` catch (already gone from routes).
- Tests: drop `tests/test_analysis_concurrency.py` if it exists.

**Trigger to revisit:** queue runs cleanly for 4 weeks with zero `acquire_slot` failures (grep logs). Or: when scale forces multi-worker (Tier 2 in [backlog.md](backlog.md)).

---

## Tier 2 queue (Redis + arq) — long-term replacement

**What:** Tier 1 queue (in-process, single worker, DB-durable) is fine while Kronos is CPU-bound on a single core. When parallelism becomes possible (GPU lands or multi-process worker is desired), swap to Tier 2.

**Why deferred:** Premature for a single-user app with ~1 job/day.

**How to apply when ready:** see [backlog.md](backlog.md) "Job submission queue" → Tier 2 section. Adds a Redis dep + a separate worker process on Railway.

**Trigger to revisit:** sustained queue depth > 5 OR GPU inference lands OR Kronos-base CPU latency drops below 3s/run (parallelism becomes worth the infra).

---

## `sentence_transformers` import broken in test env (2026-05-02, post-Phase 3.7)

**What:** `tests/test_vault_indexer.py` — 4 tests fail with `ImportError` chain through `sentence_transformers` → `transformers` requiring `huggingface-hub>=1.5.0` while `requirements.txt` pins `huggingface_hub==0.33.1`. Surfaced when `anthropic` was added to `requirements.txt` and `pip install -r requirements.txt` re-resolved the env.

**Why deferred:** Core vault-indexer runtime still works (cache.db pre-built, no fresh embeddings needed for tested operator flows). Phase 3.7 ship was on critical path. Production ingestion path (`scripts/ingest_*.py`) only runs when operator manually adds new vault content, which is rare.

**How to apply when ready:**
- Pin `transformers<5.0` in `requirements.txt` (the 5.7.0 version that auto-installed bumps the hub requirement past our pin).
- OR bump `huggingface_hub` past 1.5.0 — verify Kronos weight loader still works (it pins 0.33.1 for a reason; there's a backlog entry on Kronos hf-hub compat).
- Re-run `pytest tests/test_vault_indexer.py` to confirm all 4 pass.

**Trigger to revisit:** next vault-indexer change OR before next fresh-checkout deploy on Railway (CI parity matters).

---

## How to add an entry

Use this skeleton:

```markdown
## <short label> (<context>)

**What:** the cruft, one sentence.
**Why deferred:** the engineering reason.
**How to apply when ready:** concrete steps.
**Trigger to revisit:** the observable signal that says "now's the time."
```

If the entry has a feature angle, link to its [backlog.md](backlog.md) entry instead of duplicating.
