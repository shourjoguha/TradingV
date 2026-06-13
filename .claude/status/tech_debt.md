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

## ~~Railway: torch/Kronos still installed even with KRONOS_ENABLED=false~~ (ARCHIVED 2026-05-20)

**Status:** Moot. Railway shut down permanently on 2026-05-17 ([ADR 018](../decisions/018-railway-shutdown.md)). The split-requirements approach this entry called for is no longer needed; laptop-only deployment carries the full Kronos stack as a hard requirement.

**Why archived here vs. removed:** Dockerfile + `railway.toml` + `tailscale-entrypoint.sh` retained in repo as historical reference; if Railway is ever re-deployed, this entry's analysis (lazy-load vs. split requirements) is still the correct decision tree.

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

## ~~`app.analysis.concurrency` slot gate~~ (RESOLVED 2026-05-20)

**Status:** Stripped. 4+ weeks of clean Tier-1 queue operation with zero `AtCapacityError` fires in `.dev-logs/backend.log`. Removed:

- `app/analysis/concurrency.py` (51 LOC) — deleted
- `tests/test_concurrency.py` (89 LOC) — deleted
- `async with concurrency.acquire_slot()` wrapper in `app/analysis/service.py::submit_run` — removed
- `from app.analysis.concurrency import AtCapacityError` + the `except AtCapacityError` branch in `app/queue/worker.py::_process_one` — removed
- `from app.analysis import concurrency` re-export in `app/analysis/routes.py` — removed

`MAX_CONCURRENT_JOBS=1` setting in `app/core/config.py` retained as a feature flag for any future multi-worker resurrection (Tier 2). Tests: 64 in `test_analysis.py + test_queue.py + test_schedule.py` pass.

If a Tier 2 multi-worker queue ever ships ([backlog.md](backlog.md)), reintroduce a real semaphore — the old single-process counter wouldn't have helped anyway.

---

## Tier 2 queue (Redis + arq) — long-term replacement

**What:** Tier 1 queue (in-process, single worker, DB-durable) is fine while Kronos is CPU-bound on a single core. When parallelism becomes possible (GPU lands or multi-process worker is desired), swap to Tier 2.

**Why deferred:** Premature for a single-user app with ~1 job/day.

**How to apply when ready:** see [backlog.md](backlog.md) "Job submission queue" → Tier 2 section. Adds a Redis dep + a separate worker process on Railway.

**Trigger to revisit:** sustained queue depth > 5 OR GPU inference lands OR Kronos-base CPU latency drops below 3s/run (parallelism becomes worth the infra).

---

## ~~rx denylist + ticker regex duplication~~ (RESOLVED 2026-05-20)

**Status:** Resolved. `app/rx/_constants.py` now owns the canonical `TICKER_TOKEN_RE` + `TICKER_NOISE_DENYLIST` + `extract_tickers()` helper. Refactored:

- `app/rx/service.py` re-exports the constants under the legacy `_TICKER_NOISE_DENYLIST` / `_TICKER_TOKEN_RE` names (backwards-compat for any callers reading the underscore-prefixed surface). `links_for_rec` now uses the compiled regex instead of an inline `re.findall(r"\b[A-Z]{2,5}\b", ...)` call.
- `app/rx/tv_context_signal.py` no longer imports from `app.rx.service` (fragile module-load coupling); now imports the shared `extract_tickers()` helper directly. Local re-export keeps `tv_context_signal.extract_tickers` as the public symbol for `tests/test_rx_attention.py` + `service.create`.

**Frontend** (`frontend/src/pages/RxFinanceDetail.tsx`) keeps its own hardcoded `TICKER_NOISE_DENYLIST` for the "Log trade from this rec" prefill — bundling sync isn't worth a build-step change for a 40-entry frozen set. Comment in `_constants.py` notes the mirror requirement.

**Vault-indexer** (`tools/vault_indexer/ingest/chart_extractor.py`) keeps its OWN denylist intentionally — that module must run without `from app...` imports because three indexer instances (finance / fitness / nutrition) sit outside the FastAPI app's package tree.

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

## n=1 landmine ledger (retrieval-depth-and-debiasing-program, Phase 6)

These are deliberate shortcuts that are **correct at n=1 (single operator) and
detonate the instant a second user exists**. The council's resolution of the
Critic-vs-Pragmatist disagreement: cheap to ignore now because the operator is
the error-correction loop; catastrophic exactly when the system "succeeds"
enough to add a user. Each carries an explicit TRIGGER — the observable signal
that flips it from green to red.

### L1 — substring hypothesis-rec linkage is a fallback, not a guarantee

**What:** `links_for_rec` (`app/rx/service.py`) now prefers explicit
`linked_hypothesis_ids` (Phase 4) but still falls back to a case-insensitive
substring match (`match_type="substring_fallback"`) when no explicit link exists.
At n=1 the operator wrote the vault + hypotheses, so the surface forms are
predictable and self-correcting.
**Why deferred:** removing the substring fallback entirely would drop linkage for
every legacy rec that predates explicit linkage.
**How to apply when ready:** once `/rx-finance` always populates
`linked_hypothesis_ids`, delete the substring branch; treat absence of an
explicit link as "no link" rather than guessing.
**Trigger to revisit:** a SECOND user, OR the hypothesis count grows past ~50
(common-word substrings like "growth"/"risk" start cross-matching unrelated recs
and silently corrupt trade-attribution roll-up — D2 × B4 interaction).

### L2 — single hard-coded operator UUID

**What:** `SETTINGS.RX_OPERATOR_UUID` is server-stamped on every rec + deep
result; all reads filter by it. There is no per-user history, threshold, or auth
scoping.
**Why deferred:** the system is explicitly single-operator; multi-tenancy is
pure cost with zero benefit at n=1.
**How to apply when ready:** introduce a real `users` table + per-request
identity; thread `owner_user_id` from auth, not env; make every threshold
(action-rate gate, drift) per-user.
**Trigger to revisit:** anyone other than the operator needs to log in. This is
the master n=2 landmine — most other shortcuts (L1, L3) detonate with it.

### L3 — action-rate + drift thresholds are global, not per-cohort

**What:** action-rate health bands + the new preference-drift detector
(`app/rx/drift_monitor.py`) treat the operator as the whole population.
**Why deferred:** with one user, a single blob IS the population — per-cohort
analysis would be dividing one data point.
**How to apply when ready:** per-user × per-rule × per-cohort rates; add a
Bayesian smoother instead of the raw ratio so small-N cohorts don't swing wildly.
**Trigger to revisit:** the second user, OR any desire to compare segments.

### L4 — `/rx-analyze` lift/P&L math lives in the command, not app code

**What:** the predictive-lift + P&L computation is prose+SQL in
`~/.claude/commands/rx-analyze.md`; the app exposes mirrored pure helpers in
`app/rx/analytics.py` but the command doesn't call them.
**Why deferred:** the command path works and refactoring to an endpoint is scope
beyond the de-biasing program.
**How to apply when ready:** add a `/v1/rx/analyze` endpoint that calls
`analytics.py`; have the command call the endpoint so there is one source of
truth and no prose-vs-helper drift.
**Trigger to revisit:** the command and helpers ever disagree, OR `/rx-analyze`
needs to run unattended (cron) where in-session prose can't execute.

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
