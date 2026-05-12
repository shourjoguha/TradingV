# ADR-002: Bidirectional sync via Tailscale (Railway → laptop)

**Date**: 2026-04-26 (Phase B1+B2)
**Status**: Accepted

## Context

v1 shipped with one-way sync (laptop → Railway). Reverse direction (Railway-originated jobs flowing back) was deferred because Railway can't reach a private laptop without a tunnel. Without reverse sync, jobs run on Railway never appeared on the laptop's DB.

## Options considered

- **A · Tailscale userspace networking** — install in container; HTTP CONNECT proxy at :1055. No public laptop exposure; secure.
- **B · Cloudflare Tunnel** — also private, but adds CF-specific config + a domain. More moving parts.
- **C · ngrok / public reverse-proxy** — exposes laptop to public internet. Security trade-off rejected.

## Decision

**Tailscale userspace networking.** Container installs Tailscale; entrypoint runs `tailscaled --tun=userspace-networking --outbound-http-proxy-listen=:1055`, joins operator's tailnet as ephemeral host, exports `HTTP_PROXY=http://127.0.0.1:1055`. httpx + requests + curl auto-honor the env var. `NO_PROXY` excludes Railway-internal hosts (Postgres). No public laptop exposure.

## Trigger to revisit

- Tailscale free tier limit hit (unlikely for personal use).
- Need to reach the laptop from a non-tailnet device (would force a public tunnel).
- Multiple Railway services need to share the proxy (current model is per-service).

## Files affected

- `Dockerfile` (Tailscale install)
- `tailscale-entrypoint.sh` (proxy startup)
- `railway.toml` (Dockerfile builder)
- `.env.railway.example` (`PEER_API_URL`, `TS_AUTHKEY`)

## Lessons learned (worth re-reading if anyone touches the tunnel)

1. `[deploy].startCommand` in `railway.toml` BYPASSES the Docker ENTRYPOINT — entrypoint script never ran. Removed startCommand to let ENTRYPOINT chain into CMD.
2. `tailscaled --tun=userspace-networking` does NOT install kernel routes — direct connection to `100.x.y.z` hangs. Must use the HTTP proxy.
3. `ALL_PROXY=socks5://...` makes httpx import `socksio` (not in requirements). Don't set ALL_PROXY; HTTP_PROXY/HTTPS_PROXY cover both protocols.
4. `PEER_API_URL` MUST include the port (`:8000`); without it requests go to port 80 and 502 from the proxy.

## Cross-references

- [backlog.md](../status/backlog.md) — "Reverse-direction sync: Railway → Laptop" RESOLVED
- [railway-deployment.md](../guides/railway-deployment.md) — Tailscale tunnel section
- [sync.md](../modules/sync.md) — outbox + drain semantics
