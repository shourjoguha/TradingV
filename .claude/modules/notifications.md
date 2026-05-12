# Notifications (Telegram)

Single-channel push notifications for drift alerts (Phase 1.3) and the daily digest (Phase 4). Telegram chosen over email/Slack/Discord: free, instant mobile push, minimal config (just bot token + chat ID).

## When it's silent

The notifier no-ops gracefully when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are unset. First send attempt logs once at INFO ("not configured; will be silent"). All downstream code (drift detector, digest loop) calls `send_message` regardless and handles the False return cleanly. Code is deploy-safe before the operator sets credentials.

Setup steps (when ready): see [backlog.md](../status/backlog.md) "Unlock #1 — Telegram bot setup".

## Module layout

- `app/notifications/telegram.py` — `send_message(text, parse_mode='Markdown', disable_notification=False) -> bool`. Never raises; logs on failure.
- `app/notifications/digest.py` — `digest_loop()` (lifespan task) + `send_digest_now()` (manual). Composes markdown from open opportunities, open drift alerts, and schedule snapshot.

## Daily digest

Loop sleeps until next `DIGEST_HOUR_UTC` (default 12 = ≈ 8 AM ET), composes body, posts. Body:

```
*Daily Kronos digest*

*Top opportunities*
📈 `AAPL` BUY (R1 +2% / 5d): predicted +2.4% · conf 0.65
📉 `NFLX` SELL (R2 -2% / 5d): predicted -3.1% · conf 0.62
...

*Drift alerts*
⚠️ `META` @ +5d (kronos-base): recent MAPE 4.50% vs all-time 2.10% (2.14×)

_Schedule: enabled · last_run=success_
```

Top 5 of each section. Skips the section if empty. Falls back to "_No open opportunities._" line.

## Drift alerts (separate flow)

Drift alerts post immediately when `accuracy.drift.detect_drift()` flags a new pair (i.e. between digest cycles, not bundled). Format:

```
*Drift detected*
• `META` @ +5d (kronos-base) — recent MAPE 4.50% vs all-time 2.10% (2.14× degradation, n_recent=12)
```

## Lifespan tasks

Two loops in `app/main.py`:
- `digest_loop` (every 24h at the configured hour)
- `drift.detector_loop` (every 6h)

Both cancellation-safe and tolerant of Telegram outages — one bad tick logs and continues.

## Config (env vars)

```
TELEGRAM_BOT_TOKEN       # from @BotFather
TELEGRAM_CHAT_ID         # integer; from getUpdates after DM-ing the bot
DIGEST_HOUR_UTC=12       # 0-23
```

Plus drift-detection thresholds (used by drift.py, surfaced via Telegram):

```
DRIFT_RATIO_THRESHOLD=1.5
DRIFT_MIN_RECENT_SAMPLES=10
DRIFT_MIN_ALL_TIME_SAMPLES=30
DRIFT_RECENT_WINDOW_DAYS=30
```

All are settings in [.claude/core.md](core.md) → `app/core/config.py`.
