# Trade/Off — Pilot (S1 · Arc B · "Making the machine see") · Ep B4

**Status**: ready-to-shoot pilot package
**Date**: 2026-05-25
**Series**: Trade/Off · **Production**: hybrid (screen-record backbone + face bookends)
**Compliance**: strict build-only (no tickers, no calls — this episode is pure infra)
**Publishing**: personal handle · single formats[] set
**`source_ref`**: `retro:2026-05-16-vault-phase-e`

> Working title: **"25 seconds → 87 milliseconds. The fix was one word."**
> Chosen as pilot because it's self-contained, has a killer number, a
> one-word fix, and a lesson every dev feels — and because the claim is
> fully verifiable in-repo (below).

---

## 1. Verifiability check (PASSED — cite these on screen)

Every number/claim traces to a real artifact. Confirmed 2026-05-25:

| Claim in script | Source in repo |
|---|---|
| The search fn defaults excerpts ON | `tools/vault_indexer/search.py:50` → `excerpts: bool = True,` |
| That step is the dominant latency | `tools/vault_indexer/search.py:63-68` docstring + `:328-330` comment ("the dominant latency of /search") |
| Turning it off skips the work | `tools/vault_indexer/search.py:334` → `if excerpts:` guards the `select_top_sentences` loop |
| The API exposes the toggle | `tools/vault_indexer/app.py:208-215` → `excerpts: bool = Query(...)` with the "pass `excerpts=false`" note |
| 25s → 87–409ms warm result | `.claude/status/roadmap-shipped.md`, "Vault-indexer Phase E (Commit 1)" retro (2026-05-16) |

**Rule:** if any of these stop being true, the episode is pulled. The
receipt *is* the content.

---

## 2. Master short — 45s vertical (9:16). The TikTok/Reels/Shorts cut.

Hybrid: **face** on the hook + payoff bookends, **screen-record** for the
middle. VO continuous over both.

| t (s) | Mode | On screen | VO (locked) |
|---|---|---|---|
| 0.0–3.0 | **FACE** | Burn-in title card lower-third: `25,000ms → 87ms` | "This query took **twenty-five seconds**. The fix was **one word**." |
| 3.0–10.0 | SCREEN | Scroll the vault `/search` call; cursor lands on the slow result | "My knowledge base kept timing out. Every search re-ranked **every sentence of every result** — for results I was about to throw away." |
| 10.0–22.0 | SCREEN | Open `search.py`, highlight line 50 `excerpts: bool = True`; then highlight the docstring "the dominant latency of /search" | "The function had a default — `excerpts = True`. **Always on.** So even the callers that never used excerpts paid the full cost." |
| 22.0–30.0 | SCREEN | Highlight line 334 `if excerpts:`; type `excerpts=false` at the call site | "I added one parameter — `excerpts=false` — for the path that doesn't need them." |
| 30.0–40.0 | SCREEN | Cut to the retro line; overlay big text `25s → 87ms · warm · same results` | "Twenty-five seconds to **eighty-seven milliseconds**. Warm cache. Same results. **No new infra.**" |
| 40.0–45.0 | **FACE** | End card: series mark **Trade/Off** + "full arc ↓" | "The expensive default nobody questioned. Three more retrieval fixes came after — they're in the long one." |

**Hook hygiene:** the hook is literally true (25,000ms default-path worst
case → 87ms warm). Do not round to "instant" or claim "1000× always."

---

## 3. Shot / capture list (what to actually record)

Record at the real machine; no mockups (verifiability).

1. **FACE-A (hook)** — 1 take, ~4s, eye-line to lens. Energy: "you won't believe this default."
2. **FACE-B (payoff)** — 1 take, ~6s, calmer, point down for the CTA.
3. **SCREEN-1** — terminal/HTTP client hitting `/search`, the slow spinner. (If you can't reproduce the 25s, use the retro text as the receipt instead — do NOT fake a timer.)
4. **SCREEN-2** — editor on `tools/vault_indexer/search.py`, lines 43–68 visible; smooth highlight of `:50` then the docstring.
5. **SCREEN-3** — `search.py:334` `if excerpts:`, then the call site getting `excerpts=false`.
6. **SCREEN-4** — `roadmap-shipped.md` Phase E retro line on screen (the receipt).

Capture screen at 60fps if possible (clean highlight motion); face at whatever your setup gives, vertical-safe framing.

---

## 4. Captions (burn in — vertical safe-area, 2 lines max)

```
00:00  25 seconds. One word fixed it.
00:03  My search kept timing out—
00:05  it re-ranked every sentence of every result.
00:10  The default was excerpts = True. Always on.
00:16  Even callers that didn't need them paid for them.
00:22  I added one param: excerpts=false.
00:30  25s → 87ms. Warm. Same results. No new infra.
00:40  The default nobody questioned. Full arc below.
```

---

## 5. Per-platform publish package (single set — personal handle)

**TikTok / Reels / Shorts (same 45s master, per-platform top text):**
- **TikTok hook text:** "POV: one word made your code 250× faster"
- **Reels cover frame:** the `25,000ms → 87ms` title card; caption ends with "save this for when you over-engineer."
- **Shorts title (front-loaded, evergreen, search-friendly):** "The one-line fix that cut my query from 25s to 87ms"

**Shared caption / description:**
> A default parameter quietly ran the most expensive step in my search
> pipeline — on every call, even the ones that threw the result away.
> One flag (`excerpts=false`) took it from 25s to 87ms. No new infra, same
> results. This is part of *Trade/Off* — every episode is one real
> decision I shipped, with the receipt. Not financial advice; I build the
> tool, I don't tell you what to trade.

**Hashtags (trim per platform):** #buildinpublic #softwareengineering #python #performance #indiehacker #codeoptimization #devtok

**YouTube long-form (the arc destination, ~6 min):** see §6.

---

## 6. Long-form arc explainer — "Making the machine see (then making it fast)"

The shorts funnel here. Outline (each beat = a short that can be extracted):
1. **B1** — why I built an AI to watch finance YouTube (the problem).
2. **B2** — can a 2B model read a candlestick? (Qwen2-VL captions).
3. **B3** — teaching it tickers it's never heard of (review queue).
4. **B4 (pilot)** — the 25s→87ms default (this episode, expanded).
5. **Coda** — the three fixes after: decay model, query parser, lexical/RRF
   hybrid (all in the same Phase E retro). Tease next arc.

Film once (16:9), narrate the whole arc, then extract the four vertical
shorts from it. One session → one long video → N shorts.

---

## 7. Descript assembly (once footage exists)

The Descript MCP can do this end-to-end; I can drive it on request:
1. `import_media` the screen + face clips (URL or direct upload) into a new
   "Trade/Off — Ep B4" project, with `add_compositions` so they land on the timeline.
2. `prompt_project_agent`: "Arrange face hook, then the four screen clips in
   order, trim to the beat-sheet timecodes in §2, add burned-in captions
   from §4, add the `25,000ms → 87ms` title card at 0s and the end card at 40s."
3. Export 9:16 master; duplicate → trim platform variants per §5.

> I have **not** created a Descript project yet — that writes to your
> Descript drive. Say the word (and provide/POINT me at the recorded
> clips) and I'll scaffold the project and run the assembly.

---

## 8. Operator pre-flight checklist
- [ ] Record FACE-A, FACE-B (vertical-safe).
- [ ] Screen-capture SCREEN-1..4 (real repo, real retro line).
- [ ] Confirm the §1 citations still hold at record time.
- [ ] Hand me the clips → I drive Descript assembly (§7) + cut platform variants.
- [ ] Once published, PATCH the episode row's `formats[]` with the live URLs
      (`/v1/content/episodes/{id}`), which flips it to `published` (requires the
      `source_ref`, already set to `retro:2026-05-16-vault-phase-e`).

## See also
- [video-series-platform-design.md](video-series-platform-design.md) — the architecture this pilot validates.
- `tools/vault_indexer/search.py` — the code on screen (§1).
- `.claude/status/roadmap-shipped.md` — Phase E retro (the receipt).
