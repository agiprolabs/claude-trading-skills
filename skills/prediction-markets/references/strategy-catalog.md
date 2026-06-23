# Strategy Catalog — what works, what's hype

Strategies evaluated on Kalshi/Polymarket weather & event markets, with an honest verdict, the evidence, and the catch. "Real" means it survived correct settlement + fees in testing; "marginal/hype/blocked" are flagged so you don't re-chase them.

## ✅ Favorite–longshot fade, maker-side  — the durable edge
- **What:** retail systematically overprices cheap longshot brackets. Sell the overpriced tail = rest a **maker NO bid** on brackets priced roughly **$0.05–$0.20** (the sweet spot; the sub-$0.05 tail premium is too thin to clear fees + tail risk).
- **Evidence:** on Kalshi-settled data the realized hit-rate sits below the price across the cheap tail (priced ~10%, hits ~3–7% → ~+6.7¢/contract); a fee-inclusive rotating-CV backtest returned ~+1.7–3.3% taker / +7.9–9% maker. Corroborated by the literature (takers lose ~20% pre-fee; makers profit). See `evidence-and-literature.md`.
- **Capacity:** thin per bracket; this is a many-small-bets liquidity strategy, not size. Low Sharpe (tail-dominated) → small per-bracket size, diversify across cities/events.
- **Catch:** the rare longshot that hits. Maker fill-rate on thin tails is the open execution risk — measure it forward before sizing up.
- **NOT** a forecasting edge: it does not concentrate in your forecast-sharp cities; it tracks market thinness/retail-ness.

## ✅ Bracket YES-only longshot (forecast-driven)  — works, fee-sensitive
- **What:** when your calibrated forecast says a bracket is materially underpriced, buy YES. Trade brackets **YES-only** — the NO side of a favorite bracket has unfavorable fee-to-risk.
- **Gate:** select on **fee-adjusted net edge** past a threshold θ (15% small acct / 20% large), never raw win-rate. See `sizing-and-edge-gates.md`.
- **Directional sub-rules observed:** low-side bets YES-only (cold-front tail risk makes low-NO dangerous); high-side at-peak bets can be NO targeting model over-prediction of the afternoon max.

## ⚠️ Market-making / liquidity provision  — structurally favored, infra-heavy
- **What:** rest two-sided quotes, capture spread + the longshot premium + Kalshi maker rebates. The maker side is where the profit is (takers fund it).
- **Catch:** inventory risk, adverse selection, and you must win the queue. Real for a disciplined operator with automation; not a casual trade.

## ⚠️ Overround / dutching arbitrage  — real in theory, marginal on Kalshi
- **What:** when the full mutually-exclusive bracket set prices off 1.0, buy/sell the whole set to lock the gap.
- **Catch:** Kalshi's per-leg `0.07·p·(1−p)` fee × N legs + thin/phantom books usually exceeds the few-cent overround. Zero-fee Polymarket is friendlier, but books are thin. Opportunistic at best.

## ❌ Cross-venue arb (Kalshi ↔ Polymarket)  — blocked for most
- **Catch:** **geo/KYC** (one legal entity can't cheaply hold both legs — US persons are restricted from Polymarket), capital lockup until resolution, USDC↔USD friction, and **resolution-rule divergence** (different source/station/DST means the "same" market can settle differently). Negative at the matching step in practice.

## ❌ Latency / news front-running (crypto/index hourlies)  — HFT game
- **Catch:** increasingly colo/HFT-dominated; retail loses the race and gets adversely selected on its own resting quotes. The one semi-open lane is **NWP-run-aware overnight requoting** of thin temp books (minutes-scale, competes on model quality not microseconds) — but that's a forecasting play, see below.

## ⚠️ Near-certainty intraday repricing  — information/latency, fits a real-time feed
- **What:** once the airport sensor effectively confirms the day's extreme, the settling bracket is ~certain but the book still prices a discount for a window — lift it.
- **Catch:** requires fast, correct obs ingestion and the right settlement convention (LST day, station, integer rounding). Real but operationally demanding.

## ❌ Copy-the-sharps
- Mostly survivorship + capacity decay. Usable only as a self-computed flow *input*, never blind copy.

## Bottom line
The one edge that survived correct settlement + fees across testing is the **maker-side favorite-longshot fade**, expressed as selling the $0.05–$0.20 tail, diversified. It is structural (retail behavior), not forecasting. Everything that *looked* better than it turned out to be a backtesting artifact — see `backtesting-methodology.md`.
