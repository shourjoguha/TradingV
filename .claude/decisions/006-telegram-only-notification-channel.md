# ADR-006: Telegram only (no email, Slack, or push API)

**Date**: 2026-04-27
**Status**: Accepted

## Context

Phase 1.3 (drift alerts) and Phase 4 (daily digest) needed a push channel for the operator. Multi-channel (email + Slack + push) is the obvious "production" answer, but adds 3× config burden and 3× failure modes for a single user.

## Options considered

- **A · Telegram bot** — free, instant mobile push, single token + chat ID, ~30 lines of httpx code.
- **B · Email (SMTP via Gmail / Resend)** — needs SMTP setup or paid service. Inboxes are graveyards.
- **C · Slack webhook** — assumes operator is in Slack regularly.
- **D · Push API (web push, native)** — needs PWA or app shell.
- **E · Multi-channel** — A + B + C + D.

## Decision

**Telegram bot, single channel.** Reasons:
- Free, no SMTP / API key headaches.
- Instant mobile push without a PWA.
- Operator already uses Telegram regularly.
- Single channel means single failure mode (telegraph.org down? rare).
- Notifier no-ops gracefully when unconfigured — code ships dormant; operator activates with bot setup steps in [backlog.md](../backlog.md) Unlock #1.

## Trigger to revisit

- Telegram outage that lasts > 24h and the operator missed an alert.
- Operator stops using Telegram day-to-day.
- A second user is onboarded who doesn't use Telegram.

## Files affected

- `app/notifications/__init__.py`, `telegram.py`, `digest.py`
- `app/core/config.py` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DIGEST_HOUR_UTC`)
- `app/accuracy/drift.py` (`_notify_drifts` calls `telegram.send_message`)
- `app/main.py` (digest_loop in lifespan)

## Cross-references

- [notifications.md](../notifications.md) — channel setup + body format
- [backlog.md](../backlog.md) — Unlock #1: Telegram bot setup steps
- [roadmap-shipped.md](../roadmap-shipped.md) — Phase 1.3 + Phase 4
