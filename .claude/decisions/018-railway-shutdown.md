# ADR 018 — Railway backend permanently shut down

**Status:** accepted
**Date:** 2026-05-17

## Context

The TradingView app shipped on a dual-backend topology: **laptop**
(primary, GPU-eligible inference, vault + indexer) and **Railway** (always-on
replica, bidirectional Tailscale sync from laptop). The frontend exposed a
`BackendToggle` in the top ribbon so operator could flip between the two; the
Railway replica was useful for cross-machine read access when the laptop was
asleep.

The operator decided to permanently retire the Railway services. Reasons:
- Vault + indexer + research + tv-context surfaces were always laptop-only.
- The remaining cross-machine value (read replica during sleep) was outweighed
  by ongoing Railway cost + the sync-outbox maintenance burden.
- Tailscale tunnel back to laptop already works for the actually-mobile use
  case (e.g. phone via TailScale → laptop via Tailscale).

## Decision

Drop the Railway backend. Frontend collapses to a single `'laptop'` backend.

**Frontend surface changes:**
- `BackendToggle.tsx` deleted.
- `BackendHealthBanner` collapses to a single-backend down-notice (no switch
  button).
- `Research.tsx` + `TVContextInbox.tsx` no longer render their
  `LaptopOnlyBanner` branches — those routes were already laptop-only in
  practice, the banner just guided railway-toggle users back.
- `CadencesTab.tsx` drops the "Admin UI is laptop-local" warning.

**Type plumbing kept minimal:**
- `BackendId = 'laptop'` — single-member union retained so the ~80
  `backendId` cache-key plumbing call sites in `hooks/use-api.ts` continue
  compiling without a sweep. A future cleanup can strip the parameter.
- `getBackendId()` / `setBackendId()` / `availableBackends()` retained as
  collapse-to-laptop functions for back-compat.

## Out of scope (deliberately not touched)

- **Backend `app/sync/`** module + `SyncOutbox` table left in place. The
  module is dormant when the peer URL env var is unset — harmless. Removing
  it would invalidate sync rows already in the DB and require a migration
  rollback. Future tech-debt entry.
- **`app/core/config.py`** Railway-fallback inference logic retained
  (defensive; doesn't trigger on the laptop instance).
- **Tailscale entrypoint** + Dockerfile + `railway.toml` left in repo so
  someone could re-deploy if the decision reversed. Marked as archived in
  `.claude/guides/railway-deployment.md` but not deleted.
- **Old doc references** to Railway-specific behaviour across module docs
  not yet swept — too high-surface for one pass. Treat as authoritative-of-
  history; new readers should cross-reference this ADR.

## Consequences

- (+) Top ribbon is gone — recovers ~40px of vertical real estate.
- (+) Two dead-code banners removed; Research / TVContextInbox simpler.
- (+) No more "is the toggle pointing at the right backend?" cognitive tax.
- (–) Cross-machine read access during laptop sleep no longer available.
  Mitigation: Tailscale tunnel still works when laptop is awake.
- (–) Doc sweep is partial — some module docs still reference Railway as if
  it's deployed. Acceptable because the docs are historically accurate;
  this ADR is the canonical "and then we shut it off" entry.
