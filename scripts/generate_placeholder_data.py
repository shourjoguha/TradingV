"""Deterministic generator for the demo placeholder JSON.

Crafts realistic-feeling but synthetic data — 10-12 tickers, predictions
made on the cutoff_date - 5 days, actuals filled in for elapsed
horizons, accuracy stats consistent with the per-row outcomes.

Run from the repo root:
    python scripts/generate_placeholder_data.py

Idempotent: same seed -> same output. Re-run to refresh after schema
tweaks. NEVER hits a real database.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo-data"

CUTOFF = date(2026, 5, 9)
ENTRY = date(2026, 5, 4)  # day predictions were made
HORIZONS = [
    ("1d", 1),
    ("2d", 2),
    ("3d", 3),
    ("5d", 5),
    ("10d", 10),
]

TICKERS = [
    ("AAPL", 188.42),
    ("MSFT", 425.18),
    ("NVDA", 920.45),
    ("GOOGL", 168.23),
    ("AMZN", 184.61),
    ("META", 478.92),
    ("TSLA", 178.34),
    ("AMD", 158.47),
    ("JPM", 198.51),
    ("GS", 463.27),
    ("SPY", 519.84),
    ("QQQ", 442.13),
]

RNG = random.Random(42)  # deterministic


def _round(x: float) -> float:
    return round(x, 2)


def gen_predictions() -> tuple[list, list]:
    """Returns (by_horizon_groups, by_target_rows)."""
    horizon_groups: dict[str, list] = {h: [] for h, _ in HORIZONS}
    by_target: dict[str, list] = {t: [] for t, _ in TICKERS}

    for ticker, entry_px in TICKERS:
        # underlying drift over 10 days (small)
        annual_drift = RNG.uniform(-0.10, 0.20)
        annual_vol = RNG.uniform(0.20, 0.45)
        for h_label, h_days in HORIZONS:
            # Predicted move = drift * (h/252) + small noise
            mu = annual_drift * (h_days / 252)
            sigma_pred = annual_vol * (h_days / 252) ** 0.5
            predicted_pct = mu + RNG.gauss(0, sigma_pred * 0.3)
            predicted = entry_px * (1 + predicted_pct)

            target_date = ENTRY + timedelta(days=h_days)
            elapsed = target_date <= CUTOFF

            actual = None
            error_pct = None
            sign_correct = None
            if elapsed:
                # Actual move = different draw with realistic noise vs prediction
                actual_pct = mu + RNG.gauss(0, sigma_pred)
                actual = entry_px * (1 + actual_pct)
                error_pct = (predicted - actual) / actual * 100
                # sign correct = both predicted and actual moves point same direction
                sign_correct = (predicted_pct > 0) == (actual_pct > 0)

            row = {
                "ticker": ticker,
                "entry_price": _round(entry_px),
                "entry_date": ENTRY.isoformat(),
                "predicted": _round(predicted),
                "delta_pct": _round(predicted_pct * 100),
                "target_date": target_date.isoformat(),
                "actual": _round(actual) if actual is not None else None,
                "error_pct": _round(error_pct) if error_pct is not None else None,
                "sign_correct": sign_correct,
                "as_of": CUTOFF.isoformat(),
                # legacy alias used by older frontend code
                "current": _round(actual) if actual is not None else _round(entry_px),
            }
            horizon_groups[h_label].append(row)
            by_target[ticker].append(row)

    by_horizon_payload = [
        {"horizon": h, "rows": horizon_groups[h]} for h, _ in HORIZONS
    ]
    by_target_payload = [
        {
            "ticker": t,
            "entry_price": _round(px),
            "entry_date": ENTRY.isoformat(),
            "horizons": [
                {
                    "horizon": HORIZONS[i][0],
                    "predicted": r["predicted"],
                    "delta_pct": r["delta_pct"],
                    "target_date": r["target_date"],
                    "actual": r["actual"],
                    "error_pct": r["error_pct"],
                    "sign_correct": r["sign_correct"],
                }
                for i, r in enumerate(by_target[t])
            ],
        }
        for t, px in TICKERS
    ]
    return by_horizon_payload, by_target_payload


def gen_accuracy(by_horizon: list) -> list:
    rows = []
    for group in by_horizon:
        elapsed = [r for r in group["rows"] if r["actual"] is not None]
        if not elapsed:
            rows.append({
                "horizon": group["horizon"],
                "samples": 0,
                "mape": None,
                "hit_rate": None,
                "pending": True,
            })
            continue
        mape = sum(abs(r["error_pct"]) for r in elapsed) / len(elapsed) / 100
        hits = sum(1 for r in elapsed if r["sign_correct"])
        rows.append({
            "horizon": group["horizon"],
            "samples": len(elapsed),
            "mape": round(mape, 4),
            "hit_rate": round(hits / len(elapsed), 3),
            "pending": False,
        })
    return rows


def gen_today(by_horizon: list) -> dict:
    # drift alerts: pick 3 tickers/horizons where MAPE looks bad
    elapsed = [
        (g["horizon"], r)
        for g in by_horizon
        for r in g["rows"]
        if r["actual"] is not None
    ]
    elapsed.sort(key=lambda x: abs(x[1]["error_pct"]), reverse=True)
    drift_alerts = []
    for i, (h, r) in enumerate(elapsed[:3]):
        drift_alerts.append({
            "id": f"drift-{i+1}",
            "ticker": r["ticker"],
            "horizon": h,
            "ratio": round(1.2 + abs(r["error_pct"]) / 10, 2),
            "ack": False,
            "created_at": (datetime.combine(CUTOFF, datetime.min.time(), tzinfo=timezone.utc)
                           - timedelta(hours=14 + i * 6)).isoformat(),
            "note": f"{h} MAPE elevated vs all-time baseline.",
        })

    research_pending = [
        {
            "id": "rq-1",
            "question": "Does the trend-breakout rule still beat random in regimes where VIX > 18?",
            "status": "pending",
            "created_at": (datetime.combine(CUTOFF, datetime.min.time(), tzinfo=timezone.utc)
                           - timedelta(days=1)).isoformat(),
        },
        {
            "id": "rq-2",
            "question": "Do mean-reversion signals on QQQ degrade after weeks with a Fed minutes release?",
            "status": "pending",
            "created_at": (datetime.combine(CUTOFF, datetime.min.time(), tzinfo=timezone.utc)
                           - timedelta(days=2)).isoformat(),
        },
        {
            "id": "rq-3",
            "question": "Is per-rule hit-rate stable when the mega-cap names (NVDA, META) are excluded?",
            "status": "pending",
            "created_at": (datetime.combine(CUTOFF, datetime.min.time(), tzinfo=timezone.utc)
                           - timedelta(days=3)).isoformat(),
        },
    ]

    fresh_signals = []
    rules = ["trend-breakout", "mean-reversion", "gap-fill", "momentum-thrust"]
    for i, ticker in enumerate(["NVDA", "AMD", "META", "JPM", "SPY", "TSLA"]):
        fresh_signals.append({
            "id": f"opp-fresh-{i+1}",
            "ticker": ticker,
            "kind": "BUY" if i % 3 != 1 else "SELL",
            "rule": rules[i % len(rules)],
            "score": round(0.55 + RNG.uniform(0, 0.30), 2),
            "horizon": HORIZONS[i % len(HORIZONS)][0],
            "created_at": (datetime.combine(CUTOFF, datetime.min.time(), tzinfo=timezone.utc)
                           + timedelta(hours=7 + i)).isoformat(),
        })

    return {
        "drift_alerts": drift_alerts,
        "research_pending": research_pending,
        "fresh_signals": fresh_signals,
        "regime": {"label": "neutral-bullish", "vix": 14.8, "spy_pct_1w": 1.2},
        "watchlist_delta": [
            {"ticker": "NVDA", "added": True, "reason": "ER beat + AI guidance raise"},
            {"ticker": "ZM", "added": False, "reason": "Removed: low edge over 90 days"},
        ],
    }


def gen_motion(by_horizon: list) -> tuple[dict, dict]:
    rules = ["trend-breakout", "mean-reversion", "gap-fill", "momentum-thrust"]

    opps = []
    for i, ticker in enumerate([t for t, _ in TICKERS]):
        kind = "BUY" if RNG.random() > 0.35 else "SELL"
        rule = rules[i % len(rules)]
        score = round(0.45 + RNG.uniform(0, 0.45), 2)
        # spread statuses
        if i < 4:
            status = "open"
        elif i < 8:
            status = "acted"
        else:
            status = "expired"
        days_ago = RNG.randint(1, 25)
        created = datetime.combine(CUTOFF, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=days_ago)
        opps.append({
            "id": f"opp-{i+1}",
            "ticker": ticker,
            "kind": kind,
            "rule": rule,
            "score": score,
            "horizon": HORIZONS[i % len(HORIZONS)][0],
            "status": status,
            "created_at": created.isoformat(),
        })

    trades = []
    selected_opps = [o for o in opps if o["status"] == "acted"]
    for i, o in enumerate(selected_opps):
        # Match a ticker's price
        entry_px = next(px for t, px in TICKERS if t == o["ticker"])
        side = "long" if o["kind"] == "BUY" else "short"
        ret_pct = RNG.gauss(2.0 if side == "long" else 1.0, 4.5)
        exit_px = entry_px * (1 + (ret_pct / 100) * (1 if side == "long" else -1))
        opened = datetime.fromisoformat(o["created_at"])
        closed = opened + timedelta(days=RNG.randint(2, 10))
        trades.append({
            "id": f"trade-{i+1}",
            "ticker": o["ticker"],
            "side": side,
            "entry_price": _round(entry_px),
            "exit_price": _round(exit_px),
            "pnl_pct": round(ret_pct, 2),
            "rule_attribution": o["rule"],
            "opened_at": opened.isoformat(),
            "closed_at": closed.isoformat(),
        })
    # Add one historical trade with bigger loss (recruiter-honest)
    trades.append({
        "id": "trade-historic-1",
        "ticker": "TSLA",
        "side": "long",
        "entry_price": 195.40,
        "exit_price": 178.20,
        "pnl_pct": -8.80,
        "rule_attribution": "trend-breakout",
        "opened_at": "2026-04-15T13:30:00+00:00",
        "closed_at": "2026-04-22T20:00:00+00:00",
    })

    return {"items": opps}, {"items": trades}


def gen_canned() -> dict:
    return {
        "presets": [
            {"id": "what-is-this", "label": "What is this app?"},
            {"id": "how-accurate", "label": "How accurate are the predictions?"},
            {"id": "what-signals", "label": "How do opportunities get generated?"},
            {"id": "trade-attribution", "label": "How is P&L attributed to rules?"},
            {"id": "model-used", "label": "What model produces forecasts?"},
            {"id": "data-sources", "label": "What data sources feed this?"},
            {"id": "tech-stack", "label": "What's the tech stack?"},
            {"id": "why-frozen", "label": "Why is this demo frozen?"},
            {"id": "drift-alerts", "label": "What is a drift alert?"},
            {"id": "live-vs-demo", "label": "What does the live app do that this demo doesn't?"},
            {"id": "code-access", "label": "Can I see the source code?"},
            {"id": "build-with-me", "label": "Can you build something like this for me?"},
        ],
        "answers": [
            {
                "id": "what-is-this", "title": "What is this app?", "tab": "today",
                "keywords": ["what", "this", "app", "tradingview", "platform", "purpose", "do", "does"],
                "body": "Personal trading-decision-support system. FastAPI backend runs daily Kronos candlestick forecasts on a watchlist, emits rule-based BUY/SELL opportunities, tracks per-rule P&L from manually logged trades. This is a frozen public demo of that system as of 2026-05-09. The live system runs on the operator's laptop with bidirectional sync to a Railway replica.",
            },
            {
                "id": "how-accurate", "title": "How accurate are the predictions?", "tab": "predictions",
                "keywords": ["accurate", "accuracy", "mape", "hit", "rate", "performance", "prediction", "predictions", "error"],
                "body": "Accuracy is tracked per (horizon, target) on every prediction once actuals land. The Predictions → Accuracy tab shows MAPE and hit-rate per horizon. Drift detector flags pairs whose recent MAPE has degraded past threshold and posts to Telegram in the live system. Headline: 1d MAPE ~1.5-2%, 5d MAPE ~4-5%, 1d hit-rate ~60% in the snapshot.",
            },
            {
                "id": "what-signals", "title": "How do opportunities get generated?", "tab": "motion",
                "keywords": ["opportunity", "opportunities", "signal", "signals", "rule", "rules", "buy", "sell", "generated"],
                "body": "An hourly worker runs a fixed rule set over recent predictions: trend-breakout, mean-reversion, gap-fill, momentum-thrust. Each fires only when the prediction's confidence and the rule's gating thresholds are met. Each opportunity is weighted by the rule's historical hit-rate so high-volume / low-edge rules surface lower. Status flow: open → acted (when manually traded) or expired (after horizon).",
            },
            {
                "id": "trade-attribution", "title": "How is P&L attributed to rules?", "tab": "motion",
                "keywords": ["pnl", "p&l", "profit", "loss", "trade", "trades", "attribution", "attributed", "rule"],
                "body": "Manually logged trades carry an opportunity_id back to the rule that produced them. Per-rule P&L rolls up from every closed trade, so a rule with high hit-rate but low average win still ranks below a rare but high-magnitude rule. This closes the loop between forecast → signal → actual outcome.",
            },
            {
                "id": "model-used", "title": "What model produces forecasts?", "tab": "predictions",
                "keywords": ["model", "kronos", "forecast", "candlestick", "ml", "ai", "inference"],
                "body": "Kronos — an open candlestick prediction model. Inference runs on the operator's laptop (GPU-eligible) and forecasts are synced to the always-on Railway replica. The demo ships no model weights and runs no inference; the visible forecasts are frozen historical outputs from the laptop.",
            },
            {
                "id": "data-sources", "title": "What data sources feed this?", "tab": "today",
                "keywords": ["data", "sources", "yfinance", "fred", "feeds", "ingestion", "ingest", "where", "datasources"],
                "body": "Market data from yfinance for prices and IV percentile; FRED for macro signal layer (rates, spreads, employment). TradingView webhook receiver for chart-context screenshots. A separate vault-indexer sidecar embeds an operator-curated knowledge corpus for the Research tab. None of these are called by the public demo — all data here is frozen as of the cutoff.",
            },
            {
                "id": "tech-stack", "title": "What's the tech stack?", "tab": "about",
                "keywords": ["tech", "stack", "fastapi", "python", "react", "vite", "postgres", "railway", "docker"],
                "body": "Python 3.12 + FastAPI + SQLAlchemy + Alembic + Postgres on the backend. React 18 + Vite + TanStack Query + Tailwind on the frontend. Tailscale for laptop ↔ Railway sync. Cloudflare Pages for static frontend hosting. This demo strips the backend to FastAPI + a few JSON files; no DB, no model, no Tailscale.",
            },
            {
                "id": "why-frozen", "title": "Why is this demo frozen?", "tab": "about",
                "keywords": ["why", "frozen", "snapshot", "static", "demo", "live"],
                "body": "Frozen-snapshot demos are cheap (no DB on Railway), safe (no secrets, no write paths, no model), and predictable (recruiters always see the same polished story). The bake script in scripts/ refreshes the JSON from the live laptop DB; the operator chooses when to re-bake.",
            },
            {
                "id": "drift-alerts", "title": "What is a drift alert?", "tab": "today",
                "keywords": ["drift", "alert", "alerts", "degraded", "threshold", "mape"],
                "body": "A drift alert fires when a (ticker, horizon) pair's recent MAPE exceeds DRIFT_RATIO_THRESHOLD × the all-time MAPE for that pair. It's a coarse 'this pair is currently broken' signal, posted to Telegram in the live system and visible on the Today page here. Operator acks dismisses the row.",
            },
            {
                "id": "live-vs-demo", "title": "What does the live app do that this demo doesn't?", "tab": "about",
                "keywords": ["live", "vs", "demo", "difference", "missing", "real"],
                "body": "Live app: runs Kronos inference, ingests yfinance + FRED + TradingView webhooks, evaluates accuracy hourly, runs drift + research + ingestion loops, syncs laptop ↔ Railway via Tailscale, sends Telegram digests, accepts manual trade entries, runs a vault-indexer sidecar for the Research tab. Demo app: serves 7 JSON files. That's it.",
            },
            {
                "id": "code-access", "title": "Can I see the source code?", "tab": "about",
                "keywords": ["code", "source", "github", "repo", "repository", "see"],
                "body": "Yes — the demo branch is public at github.com/shourjoguha/TradingV/tree/demo. The main branch (live system) is gated; reach out via the Request access link in the banner.",
            },
            {
                "id": "build-with-me", "title": "Can you build something like this for me?", "tab": "about",
                "keywords": ["hire", "build", "for", "me", "you", "client", "consult", "consulting"],
                "body": "Open to it. The patterns here — frozen demo on cheap infra, dual-backend laptop+cloud sync, rule engine + per-rule P&L attribution, vault-indexed knowledge layer — generalize past trading. Use the Request access link in the banner.",
            },
        ],
    }


def gen_manifest() -> dict:
    return {
        "schema_version": 1,
        "cutoff_date": CUTOFF.isoformat(),
        "entry_date": ENTRY.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scrub_version": "synthetic-v2",
        "note": "Synthetic data generated by scripts/generate_placeholder_data.py — deterministic from seed=42. Replace via scripts/bake_demo_snapshot.py when ready.",
        "tickers": [t for t, _ in TICKERS],
        "horizons": [h for h, _ in HORIZONS],
    }


def write(path: str, payload):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  wrote {p.relative_to(ROOT)}")


def main() -> None:
    print("generating synthetic demo data…")
    by_horizon, by_target = gen_predictions()
    accuracy = gen_accuracy(by_horizon)
    today = gen_today(by_horizon)
    opps, trades = gen_motion(by_horizon)
    canned = gen_canned()
    manifest = gen_manifest()

    write("manifest.json", manifest)
    write("today.json", today)
    write("predictions/by-horizon.json", {"horizons": by_horizon})
    write("predictions/by-target.json", {"targets": by_target})
    write("predictions/accuracy.json", {"rows": accuracy})
    write("motion/opportunities.json", opps)
    write("motion/trades.json", trades)
    write("canned.json", canned)
    print("done.")


if __name__ == "__main__":
    main()
