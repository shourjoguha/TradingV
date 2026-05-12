# Smart Money Cross-Channel Aggregate — 2026-05-08

## Channels surveyed

- **Insiders** (`/insiders`) — SEC Form 4 open-market buys, ≥$100K, last ~60d. **506 raw rows**.
- **Politicians** (`/politicians`) — STOCK Act disclosures, ≥$100K, 90D. **8 raw rows**. Includes signed % gain/loss since trade in `FV` column.
- **Trailblazers** (`/trailblazers`) — 51 high-performing fund managers, Q4 2025 13F filings, only `Added` or `New` positions. **46/51 funds covered**.
- **Billionaires** (`/billionaires`) — 32 named billionaires, Q4 2025 13F. **6/32 active** (rest held flat with no Added/New).
- **Options-Bullish** (`/options`) — Unusual options flow tagged BULLISH, conviction ≥50, last ~10 days. **98 rows**.
- **Whales** (`/whales`) — *NOT INCLUDED*: Polymarket prediction-market traders (sports / politics / esports). No tickers.

## Tier 1 — Tickers in 4+ distinct channels

Highest cross-channel conviction.

| Ticker | Bil | TB | Ins | Pol | Opt | Notable |
|---|---:|---:|---:|---:|---:|---|
| **META** | 3 | 7 | 0 | 1 | 2 | BIL[3]: Dan Sundheim, David Tepper, Philippe Laffont | TB[7]: Ananym Capital, Cadian Capital, MIG Capital... | POL: Cleo Fields | OPT[2]: conv 78-78 |
| **TSM** | 2 | 7 | 3 | 1 | 0 | BIL[2]: David Tepper, Philippe Laffont | TB[7]: Cadian Capital, MIG Capital, Melqart Asset Management... | POL: Gilbert Cisneros | INS[3]: Ursula M Burns, Shyue-Shyh Lin |
| **MU** | 1 | 8 | 0 | 1 | 1 | BIL[1]: David Tepper | TB[8]: Atreides Management, Crosslink Capital, Kerrisdale Capital... | POL: Cleo Fields | OPT[1]: conv 64-64 |
| **GOOGL** | 2 | 3 | 0 | 1 | 1 | BIL[2]: David Tepper, Tom Gayner | TB[3]: MIG Capital, NZS Capital, SurgoCap Partners | POL: Cleo Fields | OPT[1]: conv 60-60 |

## Tier 2 — Tickers in exactly 3 distinct channels

| Ticker | Bil | TB | Ins | Pol | Opt | Notable |
|---|---:|---:|---:|---:|---:|---|
| NVDA | 2 | 12 | 0 | 0 | 4 | BIL[2]: Dan Sundheim, Philippe Laffont | TB[12]: 9823 Capital, Agave Capital, Atreides Management... | OPT[4]: conv 58-70 |
| MSFT | 1 | 10 | 0 | 0 | 1 | BIL[1]: David Tepper | TB[10]: 11 Capital Partners, 9823 Capital, Agave Capital... | OPT[1]: conv 60-60 |
| MELI | 1 | 6 | 0 | 0 | 1 | BIL[1]: Dan Sundheim | TB[6]: 9823 Capital, Crosslink Capital, Kerrisdale Capital... | OPT[1]: conv 66-66 |
| SPOT | 3 | 3 | 0 | 0 | 3 | BIL[3]: Dan Sundheim, Philippe Laffont, Tom Gayner | TB[3]: Anomaly Capital, MIG Capital, NZS Capital | OPT[3]: conv 52-81 |
| TSLA | 1 | 5 | 0 | 0 | 3 | BIL[1]: Philippe Laffont | TB[5]: 9823 Capital, Nightview Capital, Q3 Asset Management... | OPT[3]: conv 59-70 |
| RDDT | 2 | 4 | 1 | 0 | 0 | BIL[2]: Dan Sundheim, Philippe Laffont | TB[4]: Ananym Capital, Kerrisdale Capital, MIG Capital... | INS[1]: Sarah E Farrell |
| NFLX | 1 | 4 | 0 | 0 | 2 | BIL[1]: Philippe Laffont | TB[4]: Jericho Capital, MIG Capital, Nightview Capital... | OPT[2]: conv 63-65 |
| AMRZ | 1 | 3 | 6 | 0 | 0 | BIL[1]: Leon Cooperman | TB[3]: Ananym Capital, Kerrisdale Capital, Slate Path Capital | INS[6]: Roald Brouwer, Mario Gross |
| AAPL | 1 | 3 | 0 | 0 | 3 | BIL[1]: Tom Gayner | TB[3]: 9823 Capital, NZS Capital, Symmetry Peak | OPT[3]: conv 58-69 |
| APP | 2 | 2 | 0 | 0 | 2 | BIL[2]: Dan Sundheim, Philippe Laffont | TB[2]: Ratan Capital, Whale Rock Capital | OPT[2]: conv 51-56 |
| AMD | 1 | 3 | 0 | 0 | 1 | BIL[1]: Philippe Laffont | TB[3]: Melqart Asset Management, Q3 Asset Management, Ratan Capital | OPT[1]: conv 56-56 |
| CVNA | 1 | 3 | 0 | 0 | 1 | BIL[1]: Philippe Laffont | TB[3]: CAS Investment Partners, Greenoaks Capital, Whale Rock Capital | OPT[1]: conv 62-62 |
| ORCL | 1 | 3 | 0 | 0 | 1 | BIL[1]: Philippe Laffont | TB[3]: MIG Capital, Melqart Asset Management, Ratan Capital | OPT[1]: conv 58-58 |
| GEHC | 2 | 1 | 4 | 0 | 0 | BIL[2]: Dan Sundheim, Leon Cooperman | TB: Anomaly Capital | INS[4]: Lawrence H Culp JR, James Saccaro |
| NKE | 1 | 2 | 4 | 0 | 0 | BIL[1]: Tom Gayner | TB[2]: Slate Path Capital, Symmetry Peak | INS[4]: Timothy D Cook, Elliott Hill |
| BRK.B | 1 | 2 | 1 | 0 | 0 | BIL[1]: Tom Gayner | TB[2]: Anson Capital, Nitorum Capital | INS[1]: Michael J. O'Sullivan |
| PYPL | 1 | 2 | 0 | 0 | 1 | BIL[1]: Philippe Laffont | TB[2]: 9823 Capital, Q3 Asset Management | OPT[1]: conv 63-63 |
| MGM | 1 | 1 | 2 | 0 | 0 | BIL[1]: Tom Gayner | TB: Engine Capital | INS[2]: IAC Inc. |
| SFM | 1 | 1 | 2 | 0 | 0 | BIL[1]: Philippe Laffont | TB: Anomaly Capital | INS[2]: Kristen E Blum, Joel D Anderson |
| CAT | 1 | 1 | 1 | 0 | 0 | BIL[1]: Tom Gayner | TB: Q3 Asset Management | INS[1]: David Maclennan |
| CVX | 1 | 1 | 0 | 0 | 1 | BIL[1]: Warren Buffett | TB: 9823 Capital | OPT[1]: conv 57-57 |
| MTZ | 1 | 1 | 0 | 0 | 1 | BIL[1]: Philippe Laffont | TB: Wolf Hill Capital | OPT[1]: conv 51-51 |
| NAVN | 1 | 1 | 1 | 0 | 0 | BIL[1]: Philippe Laffont | TB: Greenoaks Capital | INS[1]: Anre D Williams |
| TXN | 1 | 1 | 0 | 0 | 1 | BIL[1]: Tom Gayner | TB: NZS Capital | OPT[1]: conv 61-61 |
| TMUS | 0 | 1 | 1 | 0 | 1 | TB: Agave Capital | INS[1]: Andre Almeida | OPT[1]: conv 73-73 |

## Tier 3 — Tickers in 2 channels with high TB cluster (5+ funds)

| Ticker | Bil | TB | Ins | Pol | Opt | Notable |
|---|---:|---:|---:|---:|---:|---|
| AMZN | 1 | 13 | 0 | 0 | 0 | BIL[1]: Philippe Laffont | TB[13]: 11 Capital Partners, 9823 Capital, Agave Capital... |
| GOOG | 2 | 10 | 0 | 0 | 0 | BIL[2]: Philippe Laffont, Tom Gayner | TB[10]: 9823 Capital, Agave Capital, Anomaly Capital... |
| NU | 1 | 9 | 0 | 0 | 0 | BIL[1]: Philippe Laffont | TB[9]: 9823 Capital, Atreides Management, Crosslink Capital... |
| SNOW | 1 | 7 | 0 | 0 | 0 | BIL[1]: Philippe Laffont | TB[7]: Anomaly Capital, Atreides Management, Jericho Capital... |
| AVGO | 2 | 5 | 0 | 0 | 0 | BIL[2]: Dan Sundheim, Philippe Laffont | TB[5]: MIG Capital, Melqart Asset Management, Ratan Capital... |
| INTC | 1 | 6 | 0 | 0 | 0 | BIL[1]: Philippe Laffont | TB[6]: NZS Capital, Octahedron Capital, Q3 Asset Management... |
| SHOP | 1 | 5 | 0 | 0 | 0 | BIL[1]: Tom Gayner | TB[5]: MIG Capital, Melqart Asset Management, NZS Capital... |
| CPNG | 0 | 5 | 3 | 0 | 0 | TB[5]: Abdiel Capital, Greenoaks Capital, Kerrisdale Capital... | INS[3]: Neil Mehta |
