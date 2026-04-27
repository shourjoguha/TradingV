# ADR-001: Cloudflare Pages over Lovable for cloud frontend hosting

**Date**: 2026-04-27
**Status**: Accepted

## Context

Frontend was running locally only (`npm run dev`). Wanted a public URL for any-device access. Original plan named Lovable as the host. Lovable's compatibility with the existing Vite + React + TS app was uncertain, so we ran a 30-question pre-flight first.

## Options considered

- **A · Lovable** — AI-assisted dev + hosting. AI editor can mutate source via GitHub sync.
- **B · Cloudflare Pages** — Static host with build-time env vars, per-PR previews, custom-domain support, generous free tier.
- **C · Netlify / Vercel** — Comparable to CF Pages on features.

## Decision

**Cloudflare Pages.** Lovable failed 5/9 axes: no existing-repo import (creates new repo), no build-time `VITE_*` env var UI (secrets-vault is server-side only), no per-PR preview URLs (one preview per project), no header/redirect config, AI editor mutates source bidirectionally. CF Pages has all of these natively. Netlify/Vercel are equivalent; CF picked because of the operator's existing Cloudflare account + Workers integration potential.

Plan: `/Users/shourjosmac/.claude/plans/cloudflare-pages-port.md`.

## Trigger to revisit

- CF Pages shutdown / pricing change.
- Need for Vercel-only features (e.g. Vercel KV, edge config).
- Deciding to use Lovable's AI editor as the dev surface (would necessitate revisiting the host).

## Files affected

- `frontend/public/_redirects` (SPA fallback for CF)
- `frontend/.env.example`
- `.claude/frontend/dev-workflow.md`
- `.claude/backlog.md` (RESOLVED entry)

## Cross-references

- [backlog.md](../backlog.md) — "Cloud frontend hosting" RESOLVED entry
- [frontend/dev-workflow.md](../frontend/dev-workflow.md) — Cloud deploy section
