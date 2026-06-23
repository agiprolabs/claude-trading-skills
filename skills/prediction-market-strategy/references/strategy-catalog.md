# Strategy Catalog — what works, what's hype

Strategies evaluated on Kalshi/Polymarket weather and event markets, with an honest verdict, the evidence, and the catch. "Real" means it survived correct settlement + fees in testing; "marginal/hype/blocked" are flagged so you don't re-chase them.

---

## ✅ Favorite–longshot fade, maker-side — the durable edge

- **What:** retail systematically overprices cheap longshot brackets. Sell the overpriced tail = rest a **maker NO bid** on brackets priced roughly **$0.05–$0.20** (the sweet spot; the sub-$0.05 tail premium is too thin to clear fees + tail risk).
- **Evidence:** on Kalshi-settled data the realized hit-rate sits below the price across the cheap tail (priced ~10%, hits ~3–7% → ~+6.7¢/contract gross); a fee-inclusive rotating-CV backtest returned ~+1.7–3.3% taker / +7.9–9% maker. Corroborated by the literature (takers lose ~20% pre-fee; makers profit). See `evidence-and-literature.md`.
- **Capacity:** thin per bracket; this is a many-small-bets liquidity strategy, not size. Low Sharpe (tail-dominated) → small per-bracket size, diversify across cities/events.
- **Catch:** the rare longshot that hits. Maker fill-rate on thin tails is the open execution risk — measure it forward before sizing up.
- **NOT** a forecasting edge: it does not concentrate in your forecast-sharp cities; it tracks market thinness/retail-ness.

---

## ✅ Bracket YES-only longshot (forecast-driven) — works, fee-sensitive

- **What:** when your calibrated forecast says a bracket is materially underpriced, buy YES. Trade brackets **YES-only** — the NO side of a favorite bracket has unfavorable fee-to-risk.
- **Gate:** select on **fee-adjusted net edge** past a threshold θ (15% small acct / 20% large), never raw win-rate. See `sizing-and-edge-gates.md`.
- **Directional sub-rules observed:** low-side bets YES-only (cold-front tail risk makes low-NO dangerous); high-side at-peak bets can be NO targeting model over-prediction of the afternoon max.
- **Catch:** requires a calibrated model and a correct, fee-inclusive backtest to confirm edge exists at your decision time. Most of the time the market price already reflects the forecast — see `evidence-and-literature.md`.

---

## ⚠️ Market-making / liquidity provision — structurally favored, infra-heavy

- **What:** rest two-sided quotes, capture spread + the longshot premium + Kalshi maker rebates. The maker side is where the profit is (takers fund it).
- **Catch:** inventory risk, adverse selection, and you must win the queue. Real for a disciplined operator with automation; not a casual trade.
- **Verdict:** worth building toward if you have the infrastructure. The single-sided NO fade (above) is the practical entry point for most operators.

---

## ⚠️ Overround / dutching arbitrage — real in theory, marginal on Kalshi

- **What:** when brackets sum to more than $1.00, buy the underpriced residual. When they sum to less, sell across all legs. The overround is the arbitrage pool.
- **Why marginal:** Kalshi bracket fills are sequential, not simultaneous. By the time you fill leg 2, leg 1 has moved. Real on exchanges with true cross-leg linking; rare and fleeting on Kalshi at retail scale.
- **Verdict:** monitor for it; don't build a strategy around it.

---

## ❌ Cross-venue arb (Kalshi ↔ Polymarket) — blocked for most

- **What:** simultaneous position in equivalent contracts on two venues (e.g., the same event priced differently on Kalshi and Polymarket).
- **Why blocked:** transfer time and cost between venues destroy the edge. Kalshi USD is trapped (withdrawal T+1 at best); Polymarket USDC bridge has gas + slippage. By the time you close both legs, the prices have converged.
- **Exception:** for a well-capitalized operator with pre-positioned float on both sides, the mechanics work — but this is institutional, not retail.

---

## ❌ Latency / news front-running (crypto/index hourlies) — HFT game

- **What:** react to a breaking news event or a new block/print before the prediction market reprices.
- **Why not retail:** requires sub-100ms latency, co-location or hosted proximity to the venue's matching engine, and robust risk controls for adverse fills. The window is milliseconds. Any "edge" visible to a human or a normal API polling loop has already been arbed out.

---

## ⚠️ Near-certainty intraday repricing — information/latency, fits a real-time feed

- **What:** markets are sometimes slow to reprice contracts that have become near-certain intraday (e.g., a high-temp bracket that is already structurally impossible with 2 hours to close). Buy the underpriced near-certain YES or sell the overpriced near-certain NO.
- **Catch:** requires a real-time feed and automation to detect and act. Not a manual strategy. The window is typically minutes.
- **Verdict:** worth building if you have the polling infrastructure. Validate that the apparent edge survives correct decision-time pricing (not near-close prices, which have already converged).

---

## ❌ Copy-the-sharps

- **What:** identify apparently profitable accounts on public data and mirror their positions.
- **Why it fails:** survivorship bias in the account selection; no reliable signal on public data distinguishing skill from luck; past winners regress; by the time you see their positions, the price has moved.

---

## Bottom Line

Two strategies survive correct accounting:
1. **The behavioral tail fade** (maker-side NO bids on cheap longshots, diversified) — structural, not forecast-dependent.
2. **Forecast-driven YES entry past the θ gate** — works at the margin when your model finds genuine mispricings.

Everything else is either HFT-scale, infrastructure-heavy, or dissolves under correct settlement + fees.
