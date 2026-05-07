# ADR-016: TradingView context — no browser automation

**Date:** 2026-05-04
**Status:** Accepted
**Owner:** Operator

## Context

TradingView holds a stream of operator-curated signals (Pine-script alerts,
hand-drawn chart annotations, screener hits, idea posts, calendar events,
strategy backtests) that the hypothesis-check + research-ask LLM call never
sees. There is no public TradingView API for retail/Pro tier; partner-only.

Three plausible ingest paths:

1. **Pine-script webhook alerts** → already wired via `/webhook` (alerts module).
2. **Manual screenshot drop into vault** → Phase 2 of TV Context layer.
3. **Browser automation** with operator credentials → Playwright session
   logged in as the operator, scraping screeners / chart data nightly.

## Decision

Adopt #1 + #2. **Reject #3.**

## Why no browser automation

- **ToS violation.** TradingView's terms forbid automated access. Detection →
  account ban → loss of paid sub + indicator history + saved layouts.
- **Asymmetric cost.** Browser automation buys *some* additional data
  (screener hits we can't get otherwise); ban risk loses the entire paid
  channel (webhook alerts included). The expected value is negative even
  at low detection probability.
- **Fragility.** Cloudflare anti-bot, DOM changes monthly, headless detection
  fingerprints. Maintenance tax > value.
- **Credentials sprawl.** Storing the operator's TV password in env / secret
  store creates a new attack surface for a single-operator system.
- **Slow.** Browser automation is 10-100× slower than API. Nightly cron at
  laptop scale is fine; real-time signal pulls aren't viable.

## What we accept

- We CANNOT see TV screener results, community-published Pine indicators,
  or strategy-tester P&L curves through the layer.
- Operator must manually screenshot or paste-as-note anything from those
  surfaces. The TV Context UI is built to make this low-friction (drag-drop,
  paste-from-clipboard, vision auto-summary).

## Alternatives considered

- **Mobile/email TV alert forwarding** — same Pine alert system as #1, same
  webhook target. Already covered.
- **TwelveData / Alpha Vantage replacements** — replace the *math* TV does,
  not the *human curation*. Out of scope: those don't replicate the
  operator's hand-drawn annotations.
- **TV official partner API** — gated, expensive, requires registration as
  data redistributor. Not appropriate for single-operator setup.

## Consequences

- Phase 4 hypothesis gating relies on the operator actually attaching
  screenshots when prompted. The friction-cost is on the operator; the
  alternative (auto-scrape) is worse.
- The retention sweep keeps disk usage bounded so the manual-paste workflow
  stays cheap.
