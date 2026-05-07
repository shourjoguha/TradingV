# ADR-017: Screenshot vision summarization — default ON

**Date:** 2026-05-04
**Status:** Accepted
**Owner:** Operator

## Context

Phase 2 of the TV Context layer accepts manual chart screenshots into the
vault. Without an automated summary, the screenshot's retrieval value
depends entirely on the operator's typed caption — typically terse, often
empty.

A hand-typed caption is the cheapest natural intent. Two alternatives:

1. **Default OFF, opt-in vision** — operator toggles per-upload.
2. **Default ON, opt-out per-upload** — vision call fires automatically;
   operator unchecks the toggle to skip.

## Decision

**Default ON.** Toggle visible per-upload. Operator can change the global
default via `TV_CTX_SCREENSHOT_VISION_DEFAULT=false` env var if cost
becomes a concern.

## Why

Operator pref captured during Phase 4 brainstorm:

> *"I will likely drop in images and not want to type in much context, and
> am ok with the extra cost if it means less effort from me."*

At ~$0.012 per chart (1024px max-width, Sonnet 4.6 vision pricing) and
realistic volume (5–20 charts/wk), the monthly cost is ~$0.50–2.50 — small
relative to the operator's time-saved. The alternative (default OFF)
front-loads decision fatigue every upload and silently produces low-quality
retrieval signals when the operator forgets to opt in.

## Cost surfacing

- Per-upload: estimated cost shown next to the toggle (`~$0.012`).
- Per-month: running tally in TV Context inbox header
  (`GET /v1/tv-context/vision-spend?month=YYYY-MM`).
- Per-row: actual cost stored in `tv_context_items.payload.vision.cost_usd`.

If monthly spend exceeds an internal threshold the operator can flip the
env-var default to `false` without any code change.

## Failure path

Vision call timeouts / 5xx / missing API key never block screenshot ingest.
Failure shows as `payload.vision = {"status":"failed", "error": "..."}`;
the file + row still persist; operator can re-trigger or rely on caption.

## Alternatives considered

- **Always-on, no toggle** — removes user agency. Rejected.
- **Default-OFF, opt-in** — per the operator's stated preference, this
  maximises friction in the common case. Rejected.
- **Cost-budget guardrail (auto-disable when monthly spend > $N)** —
  defer until usage data shows it's needed. Knob exists; we'll wire the
  guardrail later if real spend justifies it.

## Consequences

- A small recurring API spend appears on every operator session that
  involves screenshots.
- Vault grows richer faster: each chart now contributes structured
  indicators / pattern / sentiment text rather than just an image link.
- Tombstones preserve the vision summary even after the image binary is
  unlinked at expiry — long-tail retrieval value survives the disk-bloat
  sweep.
