"""Render an Agents-lane review snapshot into a markdown report + HTML dashboard.

Consumes either the JSON snapshot written by ``agents_review.py`` (``--from``)
or reads the latest decisions straight from the DB (``--from-db``), and emits:

  * a markdown report (``--md``) — one section per ticker with the stance,
    buy-level call, 6–12mo downside/upside and the case behind each, risks and
    catalysts, plus a summary table. Meant to be committed to ``reports/``.
  * a self-contained, theme-aware HTML dashboard (``--html``) — a comparison
    board with stance chips, a downside↔upside range bar centered at zero, and
    a buy-level rating. Publishable as an Artifact as-is (no external assets).

Usage:
    python scripts/agents_report.py --from reports/agents-review-2026-07-10.json \
        --md reports/agents-review-2026-07-10.md \
        --html reports/agents-review-2026-07-10.html
    python scripts/agents_report.py --from-db --md out.md --html out.html
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

STANCE_ORDER = {"BUY": 0, "HOLD": 1, "SELL": 2}
BUY_LEVEL_SCALE = ["avoid", "rich", "fair", "attractive", "compelling"]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_from_json(path: Path) -> dict:
    snap = json.loads(path.read_text(encoding="utf-8"))
    if "decisions" not in snap:
        raise ValueError(f"{path} is not an agents-review snapshot (no 'decisions')")
    return snap


async def load_from_db(*, limit: int = 100) -> dict:
    from app.agents import service as agents_service
    from app.agents.adapter import get_engine

    decisions = await agents_service.list_decisions(limit=limit, include_meta=True)
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "made_on": None,
        "engine": get_engine().name,
        "stats": {"scanned": len(decisions), "ok": len(decisions), "failed": 0},
        "decisions": decisions,
    }


def _decisions(snapshot: dict) -> list[dict]:
    rows = [d for d in snapshot.get("decisions", []) if not d.get("error")]
    rows.sort(key=lambda d: (STANCE_ORDER.get((d.get("stance") or "").upper(), 9),
                             d.get("ticker", "")))
    return rows


def _review(d: dict) -> dict:
    return d.get("review") or (d.get("meta") or {}).get("review") or {}


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def render_markdown(snapshot: dict) -> str:
    rows = _decisions(snapshot)
    engine = snapshot.get("engine", "?")
    made_on = snapshot.get("made_on") or "—"
    stub = engine == "stub"

    counts = {"BUY": 0, "HOLD": 0, "SELL": 0}
    for d in rows:
        counts[(d.get("stance") or "HOLD").upper()] = counts.get((d.get("stance") or "HOLD").upper(), 0) + 1

    out: list[str] = []
    out.append(f"# Agents-lane buy review — {made_on}\n")
    if stub:
        out.append("> ⚠️ **Preview from the deterministic stub engine — NOT real analysis.** "
                   "Numbers are pipeline sentinels. Enable the lane on the laptop "
                   "(`AGENTS_ENABLED=true` + `requirements-agents.txt`) for real verdicts.\n")
    if engine == "web-research":
        out.append("> ℹ️ **Live web-research read**, not the TradingAgents LLM lane: Sonnet workers "
                   "pulled the data (WebSearch/WebFetch), Opus synthesized. Smart-money = gekko.app "
                   "snapshot (dated). Research aid for one operator — **not investment advice.**\n")
    out.append(f"Engine: `{engine}` · Generated: {snapshot.get('generated_at', '—')} · "
               f"BUY {counts.get('BUY', 0)} · HOLD {counts.get('HOLD', 0)} · SELL {counts.get('SELL', 0)}\n")

    macro = snapshot.get("macro")
    if macro:
        out.append(f"**Macro backdrop:** 10Y {macro.get('ust_10y_pct', '?')}% · "
                   f"2Y {macro.get('ust_2y_pct', '?')}% · 2s10s {macro.get('curve_2s10s_bps', '?')}bps. "
                   f"{macro.get('note', '')}\n")

    # Summary table (richer when web-research facts are present)
    has_facts = any(_review(d).get("facts") for d in rows)
    if has_facts:
        out.append("| Ticker | Stance | Buy level | Price | Analyst mean | Off 52w-high | "
                   "Downside (6–12mo) | Upside (6–12mo) | Smart money |")
        out.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |")
        for d in rows:
            r = _review(d); f = r.get("facts") or {}; sm = r.get("smart_money") or {}
            out.append(
                f"| **{d.get('ticker', '?')}** | {(d.get('stance') or '—').upper()} "
                f"| {r.get('buy_level', '—')} | {_fmt_usd(f.get('price'))} | {_fmt_usd(f.get('target_mean'))} "
                f"| {_fmt_pct(f.get('off_52w_high_pct'))} "
                f"| {_fmt_pct(r.get('downside_pct'))} | {_fmt_pct(r.get('upside_pct'))} "
                f"| {sm.get('tier', '—')} |"
            )
    else:
        out.append("| Ticker | Stance | Buy level | Downside (6–12mo) | Upside (6–12mo) |")
        out.append("| :----- | :----- | :-------- | ----------------: | --------------: |")
        for d in rows:
            r = _review(d)
            out.append(
                f"| **{d.get('ticker', '?')}** | {(d.get('stance') or '—').upper()} "
                f"| {r.get('buy_level', '—')} "
                f"| {_fmt_pct(r.get('downside_pct'))} | {_fmt_pct(r.get('upside_pct'))} |"
            )
    out.append("")

    for d in rows:
        r = _review(d)
        f = r.get("facts") or {}
        sm = r.get("smart_money") or {}
        out.append(f"## {d.get('ticker', '?')} — {(d.get('stance') or '—').upper()}\n")
        out.append(f"**Buy level:** {r.get('buy_level', '—')}  ·  **Horizon:** {r.get('horizon', '6-12mo')}\n")
        if f:
            bits = [f"Price {_fmt_usd(f.get('price'))}"]
            if f.get("forward_pe") is not None:
                bits.append(f"fwd P/E {f['forward_pe']}")
            bits.append(f"analyst mean {_fmt_usd(f.get('target_mean'))} "
                        f"(range {_fmt_usd(f.get('target_low'))}–{_fmt_usd(f.get('target_high'))}, "
                        f"{f.get('analyst_rating', '—')})")
            if f.get("off_52w_high_pct") is not None:
                bits.append(f"{_fmt_pct(f['off_52w_high_pct'])} off 52w-high")
            if f.get("next_earnings"):
                bits.append(f"earnings {f['next_earnings']}")
            out.append("**Facts:** " + " · ".join(bits) + "\n")
        if sm:
            out.append(f"**Smart money ({sm.get('as_of', '—')}):** {sm.get('tier', '—')} — "
                       f"{sm.get('summary', '')}\n")
        out.append(f"- **Downside {_fmt_pct(r.get('downside_pct'))}** — "
                   f"{r.get('downside_case') or '_not quantified_'}")
        out.append(f"- **Upside {_fmt_pct(r.get('upside_pct'))}** — "
                   f"{r.get('upside_case') or '_not quantified_'}")
        if r.get("key_risks"):
            out.append("- **Risks:** " + "; ".join(r["key_risks"]))
        if r.get("catalysts"):
            out.append("- **Catalysts:** " + "; ".join(r["catalysts"]))
        if r.get("source") == "heuristic":
            out.append("- _(risk/reward is a heuristic placeholder — no model extraction ran)_")
        rationale = (d.get("rationale_md") or "").strip()
        if rationale:
            out.append("\n<details><summary>Desk rationale</summary>\n\n" + rationale + "\n\n</details>")
        out.append("")

    return "\n".join(out) + "\n"


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):+.0f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_usd(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


# --------------------------------------------------------------------------- #
# HTML dashboard
# --------------------------------------------------------------------------- #
def render_html(snapshot: dict) -> str:
    rows = _decisions(snapshot)
    engine = snapshot.get("engine", "?")
    made_on = snapshot.get("made_on") or "—"
    stub = engine == "stub"

    max_abs = 1.0
    for d in rows:
        r = _review(d)
        max_abs = max(max_abs, abs(_num(r.get("downside_pct"))), abs(_num(r.get("upside_pct"))))

    counts = {"BUY": 0, "HOLD": 0, "SELL": 0}
    for d in rows:
        s = (d.get("stance") or "HOLD").upper()
        counts[s] = counts.get(s, 0) + 1

    cards = "\n".join(_card_html(d, max_abs) for d in rows)
    if stub:
        banner = ('<div class="banner">Preview from the <strong>stub engine</strong> — '
                  'numbers are pipeline sentinels, not analysis. Enable the lane on the '
                  'laptop for real verdicts.</div>')
    elif engine == "web-research":
        banner = ('<div class="banner info">Live <strong>web-research</strong> read (Sonnet pulled '
                  'data, Opus synthesized) — not the TradingAgents LLM lane. Smart-money = gekko.app '
                  'snapshot. Research aid, <strong>not investment advice</strong>.</div>')
    else:
        banner = ""

    macro = snapshot.get("macro") or {}
    macro_html = ""
    if macro:
        macro_html = (
            '<div class="macro">'
            f'<span><b>10Y</b> {html.escape(str(macro.get("ust_10y_pct", "?")))}%</span>'
            f'<span><b>2Y</b> {html.escape(str(macro.get("ust_2y_pct", "?")))}%</span>'
            f'<span><b>2s10s</b> {html.escape(str(macro.get("curve_2s10s_bps", "?")))}bps</span>'
            f'<span class="macro-note">{html.escape(str(macro.get("note", "")))}</span>'
            '</div>'
        )
    title = f"Agents buy review · {html.escape(str(made_on))}"

    return _HTML_SHELL.format(
        title=title,
        banner=banner,
        macro=macro_html,
        made_on=html.escape(str(made_on)),
        engine=html.escape(str(engine)),
        generated=html.escape(str(snapshot.get("generated_at", "—"))),
        buy=counts.get("BUY", 0), hold=counts.get("HOLD", 0), sell=counts.get("SELL", 0),
        cards=cards,
    )


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _card_html(d: dict, max_abs: float) -> str:
    r = _review(d)
    ticker = html.escape(str(d.get("ticker", "?")))
    stance = (d.get("stance") or "HOLD").upper()
    stance_cls = {"BUY": "buy", "SELL": "sell"}.get(stance, "hold")
    down = _num(r.get("downside_pct"))
    up = _num(r.get("upside_pct"))
    # Range bar: track spans [-max_abs, +max_abs]; 0 sits at 50%.
    down_w = min(abs(down) / max_abs, 1.0) * 50.0
    up_w = min(abs(up) / max_abs, 1.0) * 50.0
    level = str(r.get("buy_level", "")).lower()
    dots = _rating_dots(level)
    risks = "".join(f"<li>{html.escape(x)}</li>" for x in (r.get("key_risks") or []))
    cats = "".join(f"<li>{html.escape(x)}</li>" for x in (r.get("catalysts") or []))
    down_case = html.escape(str(r.get("downside_case") or "not quantified"))
    up_case = html.escape(str(r.get("upside_case") or "not quantified"))
    heuristic = ('<span class="tag-heur" title="No model extraction ran — placeholder risk/reward">'
                 'heuristic</span>' if r.get("source") == "heuristic" else "")

    lists = ""
    if risks:
        lists += f'<div class="col"><h4>Risks</h4><ul>{risks}</ul></div>'
    if cats:
        lists += f'<div class="col"><h4>Catalysts</h4><ul>{cats}</ul></div>'
    lists_html = f'<div class="lists">{lists}</div>' if lists else ""

    f = r.get("facts") or {}
    facts_html = ""
    if f:
        off = f.get("off_52w_high_pct")
        off_html = (f'<span class="off">{off:+.0f}% off high</span>'
                    if isinstance(off, (int, float)) else "")
        fpe = f.get("forward_pe")
        fpe_html = f'<span class="pe">fwd P/E {html.escape(str(fpe))}</span>' if fpe else ""
        facts_html = (
            '<div class="facts">'
            f'<span class="px">{_fmt_usd(f.get("price"))}</span>'
            f'<span class="arrow">&rarr;</span>'
            f'<span class="tgt">{_fmt_usd(f.get("target_mean"))} <em>mean tgt</em></span>'
            f'{fpe_html}{off_html}'
            '</div>'
        )
    sm = r.get("smart_money") or {}
    sm_html = ""
    if sm:
        sm_html = (f'<div class="sm" title="gekko.app smart-money, {html.escape(str(sm.get("as_of","")))}">'
                   f'<span class="sm-tag">Smart money</span> '
                   f'<b>{html.escape(str(sm.get("tier","—")))}</b> · '
                   f'{html.escape(str(sm.get("summary","")))}</div>')

    return f"""
      <article class="card">
        <header>
          <div class="tk">{ticker}</div>
          <span class="chip {stance_cls}">{stance}</span>
        </header>
        {facts_html}
        <div class="rating">
          <span class="rating-label">Buy level</span>
          <span class="dots">{dots}</span>
          <span class="rating-name">{html.escape(level or '—')}</span>
          {heuristic}
        </div>
        <div class="rr">
          <div class="rr-track">
            <div class="rr-down" style="width:{down_w:.1f}%"></div>
            <div class="rr-up" style="width:{up_w:.1f}%"></div>
            <div class="rr-zero"></div>
          </div>
          <div class="rr-nums">
            <span class="down">{down:+.0f}%</span>
            <span class="rr-cap">6–12mo range</span>
            <span class="up">{up:+.0f}%</span>
          </div>
        </div>
        <div class="cases">
          <p><span class="dot-down"></span>{down_case}</p>
          <p><span class="dot-up"></span>{up_case}</p>
        </div>
        {lists_html}
        {sm_html}
      </article>"""


def _rating_dots(level: str) -> str:
    try:
        filled = BUY_LEVEL_SCALE.index(level) + 1
    except ValueError:
        filled = 0
    return "".join(
        f'<i class="{"on" if i < filled else ""}"></i>' for i in range(len(BUY_LEVEL_SCALE))
    )


_HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --ground:#f5f6f8; --panel:#ffffff; --ink:#191e26; --muted:#5f6a78;
    --line:#e2e6ec; --gold:#b7893b;
    --up:#2f9e6a; --up-soft:#d9f0e4; --down:#d05a44; --down-soft:#f6dcd5; --hold:#b7893b;
    --shadow:0 1px 2px rgba(20,28,40,.06),0 8px 24px rgba(20,28,40,.06);
  }}
  @media (prefers-color-scheme:dark) {{
    :root {{
      --ground:#0e1116; --panel:#161b22; --ink:#e7ecf3; --muted:#8b95a4;
      --line:#242b34; --gold:#d4a94f;
      --up:#43b585; --up-soft:#12352a; --down:#e0715a; --down-soft:#3a1f1a; --hold:#d4a94f;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
    }}
  }}
  :root[data-theme="light"] {{
    --ground:#f5f6f8; --panel:#ffffff; --ink:#191e26; --muted:#5f6a78;
    --line:#e2e6ec; --gold:#b7893b;
    --up:#2f9e6a; --up-soft:#d9f0e4; --down:#d05a44; --down-soft:#f6dcd5; --hold:#b7893b;
    --shadow:0 1px 2px rgba(20,28,40,.06),0 8px 24px rgba(20,28,40,.06);
  }}
  :root[data-theme="dark"] {{
    --ground:#0e1116; --panel:#161b22; --ink:#e7ecf3; --muted:#8b95a4;
    --line:#242b34; --gold:#d4a94f;
    --up:#43b585; --up-soft:#12352a; --down:#e0715a; --down-soft:#3a1f1a; --hold:#d4a94f;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--ground); color:var(--ink);
    font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.5; font-variant-numeric:tabular-nums;
  }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:clamp(20px,4vw,44px); }}
  .eyebrow {{ letter-spacing:.14em; text-transform:uppercase; font-size:12px;
    font-weight:600; color:var(--gold); margin:0 0 6px; }}
  h1 {{ font-size:clamp(26px,4vw,38px); margin:0 0 6px; letter-spacing:-.02em; text-wrap:balance; }}
  .meta {{ color:var(--muted); font-size:14px; margin:0 0 20px; }}
  .banner {{ background:var(--down-soft); color:var(--ink); border:1px solid var(--down);
    border-radius:10px; padding:10px 14px; font-size:13.5px; margin:0 0 20px; }}
  .banner.info {{ background:color-mix(in srgb,var(--gold) 12%,transparent); border-color:var(--gold); }}
  .macro {{ display:flex; gap:16px; flex-wrap:wrap; align-items:baseline; background:var(--panel);
    border:1px solid var(--line); border-radius:10px; padding:10px 14px; margin:0 0 22px;
    font-size:13px; color:var(--muted); box-shadow:var(--shadow); }}
  .macro b {{ color:var(--ink); }}
  .macro-note {{ flex:1 1 260px; min-width:200px; }}
  .counts {{ display:flex; gap:10px; flex-wrap:wrap; margin:0 0 26px; }}
  .count {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:8px 14px; font-size:13px; color:var(--muted); box-shadow:var(--shadow); }}
  .count b {{ color:var(--ink); font-size:17px; margin-right:5px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
    padding:18px 18px 16px; box-shadow:var(--shadow); }}
  .card header {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }}
  .facts {{ display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; margin-bottom:12px;
    font-size:13px; }}
  .facts .px {{ font-weight:700; font-size:16px; }}
  .facts .arrow {{ color:var(--muted); }}
  .facts .tgt {{ font-weight:600; color:var(--up); }}
  .facts .tgt em {{ font-style:normal; color:var(--muted); font-weight:500; font-size:11px; }}
  .facts .pe,.facts .off {{ font-size:11px; color:var(--muted); border:1px solid var(--line);
    border-radius:6px; padding:1px 6px; }}
  .sm {{ margin-top:12px; padding-top:10px; border-top:1px solid var(--line); font-size:12px;
    color:var(--muted); }}
  .sm b {{ color:var(--ink); }}
  .sm-tag {{ font-size:10px; letter-spacing:.06em; text-transform:uppercase; color:var(--gold);
    font-weight:700; }}
  .tk {{ font-size:22px; font-weight:700; letter-spacing:-.01em; }}
  .chip {{ font-size:12px; font-weight:700; letter-spacing:.06em; padding:4px 11px;
    border-radius:999px; }}
  .chip.buy {{ background:var(--up-soft); color:var(--up); }}
  .chip.sell {{ background:var(--down-soft); color:var(--down); }}
  .chip.hold {{ background:color-mix(in srgb,var(--hold) 16%,transparent); color:var(--hold); }}
  .rating {{ display:flex; align-items:center; gap:8px; margin-bottom:14px; font-size:13px; }}
  .rating-label {{ color:var(--muted); }}
  .dots {{ display:inline-flex; gap:3px; }}
  .dots i {{ width:9px; height:9px; border-radius:2px; background:var(--line);
    display:inline-block; }}
  .dots i.on {{ background:var(--gold); }}
  .rating-name {{ text-transform:capitalize; font-weight:600; }}
  .tag-heur {{ margin-left:auto; font-size:10.5px; letter-spacing:.05em; text-transform:uppercase;
    color:var(--muted); border:1px dashed var(--line); border-radius:6px; padding:1px 6px; }}
  .rr {{ margin:4px 0 14px; }}
  .rr-track {{ position:relative; height:12px; border-radius:6px; overflow:hidden;
    background:color-mix(in srgb,var(--muted) 14%,transparent);
    display:flex; }}
  .rr-down {{ position:absolute; right:50%; top:0; bottom:0; background:var(--down); border-radius:6px 0 0 6px; }}
  .rr-up {{ position:absolute; left:50%; top:0; bottom:0; background:var(--up); border-radius:0 6px 6px 0; }}
  .rr-zero {{ position:absolute; left:50%; top:-2px; bottom:-2px; width:2px;
    background:var(--ink); opacity:.55; transform:translateX(-1px); }}
  .rr-nums {{ display:flex; justify-content:space-between; align-items:center; margin-top:6px;
    font-size:13px; font-weight:600; }}
  .rr-nums .down {{ color:var(--down); }}
  .rr-nums .up {{ color:var(--up); }}
  .rr-cap {{ color:var(--muted); font-weight:500; font-size:11px; letter-spacing:.04em;
    text-transform:uppercase; }}
  .cases p {{ margin:6px 0; font-size:13.5px; color:var(--ink); display:flex; gap:8px; align-items:baseline; }}
  .dot-down,.dot-up {{ width:8px; height:8px; border-radius:50%; flex:none; transform:translateY(1px); }}
  .dot-down {{ background:var(--down); }}
  .dot-up {{ background:var(--up); }}
  .lists {{ display:flex; gap:20px; flex-wrap:wrap; margin-top:12px; padding-top:12px;
    border-top:1px solid var(--line); }}
  .lists h4 {{ margin:0 0 5px; font-size:11px; letter-spacing:.08em; text-transform:uppercase;
    color:var(--muted); font-weight:600; }}
  .lists ul {{ margin:0; padding-left:16px; font-size:13px; color:var(--ink); }}
  .lists li {{ margin:2px 0; }}
  footer {{ margin-top:30px; color:var(--muted); font-size:12.5px; text-align:center; }}
</style>
</head>
<body>
  <div class="wrap">
    <p class="eyebrow">TradingAgents · multi-agent desk</p>
    <h1>Buy-level review</h1>
    <p class="meta">As of {made_on} · engine <code>{engine}</code> · generated {generated}</p>
    {banner}
    {macro}
    <div class="counts">
      <span class="count"><b>{buy}</b>Buy</span>
      <span class="count"><b>{hold}</b>Hold</span>
      <span class="count"><b>{sell}</b>Sell</span>
    </div>
    <div class="grid">
      {cards}
    </div>
    <footer>Downside/upside are 6–12 month scenario estimates from the desk debate,
      not price targets or advice.</footer>
  </div>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render an agents-review snapshot to markdown + HTML.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from", dest="from_json", help="JSON snapshot from agents_review.py")
    src.add_argument("--from-db", action="store_true", help="Read latest decisions from the DB")
    p.add_argument("--md", help="Output markdown path")
    p.add_argument("--html", help="Output HTML dashboard path")
    p.add_argument("--limit", type=int, default=100, help="Max decisions when reading --from-db")
    return p.parse_args(argv)


def _write(path_str: str | None, content: str) -> None:
    if not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(str(path))


def main(argv=None) -> int:
    args = _parse_args(argv)
    if not args.md and not args.html:
        print("nothing to do: pass --md and/or --html", file=sys.stderr)
        return 2
    if args.from_json:
        snapshot = load_from_json(Path(args.from_json))
    else:
        snapshot = asyncio.run(load_from_db(limit=args.limit))
    _write(args.md, render_markdown(snapshot))
    _write(args.html, render_html(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
