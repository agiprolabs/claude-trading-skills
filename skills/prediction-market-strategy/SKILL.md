---
name: prediction-market-strategy
description: Venue- and market-type-agnostic strategy, sizing, and backtesting layer for binary prediction markets (Kalshi, Polymarket, ForecastEx). Covers the durable edge thesis, fee-aware selection, fractional-Kelly sizing, and leak-free validation methodology.
---

# Prediction Market Strategy

Binary prediction markets price contracts as probabilities. This skill covers the *strategy, sizing, and validation* layer that applies across all venues and market types. API mechanics live in `kalshi-api` / `polymarket-api`; contract semantics and settlement live in `kalshi-weather-markets` / `kalshi-crypto-index-markets`. This is the strategy/sizing/validation layer that applies across all of them.

## Core Thesis

**Price = implied probability.** A contract priced at $0.18 claims an 18% chance of resolving YES. Brackets in a series sum to just above $1.00 — the overround is the house margin (roughly 5–8% for weather markets on Kalshi).

**Takers systematically lose; makers systematically win.** Across 300k+ Kalshi contracts, the average pre-fee return is ≈ −20%, concentrated in takers (market-order users) and in longshot buyers. Makers (resting limit orders) earn positive returns. On Polymarket (588M+ trades), the top ~1% of accounts capture ~76.5% of profit, predominantly by resting limit orders. This is the foundational result.

**Favorite–longshot bias is the durable mechanism.** Cheap longshots are systematically overpriced: a $0.05 contract historically wins ~2%; sub-$0.10 contracts lose ~60% of stake to buyers. Favorites are fairly- to slightly-underpriced. The repeatable expression is **selling the overpriced longshot tail, maker-side** — resting NO bids on brackets priced ~$0.05–$0.20, diversified across many events to survive the rare hit. This is structural/behavioral, not a forecasting edge.

**Forecast skill ≠ trading edge.** A good weather or event forecast is largely redundant with the market price at decision time. Markets aggregate information efficiently enough that even a measurably better model produces near-zero net edge after fees unless it finds systematic mispricings (which are behavioral, not informational). The exception is official-label ML in lightly-traded markets — but that is bounded by fill-rate and capacity, not forecast accuracy.

---

## Strategy Catalog

Strategies evaluated on Kalshi/Polymarket weather and event markets. "Real" means it survived correct settlement + fees in testing; others are flagged so you don't re-chase them.

| Strategy | Verdict | Mechanism | Key Catch |
|----------|---------|-----------|-----------|
| Favorite–longshot fade, maker-side | ✅ Durable | Rest maker NO bids on ~$0.05–$0.20 brackets; behavioral tail overpricing | Rare longshot hit; measure fill-rate forward |
| Bracket YES-only (forecast-driven) | ✅ Works, fee-sensitive | Buy YES when calibrated model says bracket is materially underpriced | Requires net_edge > θ gate; not raw win-rate |
| Market-making / liquidity provision | ⚠️ Structurally favored, infra-heavy | Two-sided quotes, capture spread + maker rebates | Inventory risk, adverse selection, queue priority |
| Overround / dutching arbitrage | ⚠️ Real in theory, marginal in practice | Sum-to->$1.00 across brackets; buy the underpriced residual | Legs must fill simultaneously; Kalshi fills are sequential |
| Cross-venue arb (Kalshi ↔ Polymarket) | ❌ Blocked for most | Simultaneous position in equivalent contracts on two venues | Transfer time/cost destroys edge; geo-lock |
| Latency / news front-running (crypto/index hourlies) | ❌ HFT game | React to public feeds before market reprices | Sub-100ms requirement; co-location; not retail |
| Near-certainty intraday repricing | ⚠️ Information/latency edge | Markets slow to reprice near-certain contracts; capture the residual | Requires real-time feed + automation |
| Copy-the-sharps | ❌ Survivorship illusion | Mirror apparent winning accounts | No reliable signal on public data; past winners regress |

**Bottom line:** Two strategies survive correct accounting — the behavioral tail fade (maker-side) and the forecast-driven YES entry past the θ gate. Everything else is either HFT-scale, infrastructure-heavy, or dissolves under correct settlement + fees.

---

## Fee-Aware Sizing & Edge Gates

All selection is on **fee-adjusted net edge**. Raw win-rate, return on notional, and % correct are not selection metrics.

### Net Edge Formula

```python
net_edge = p_model - ask - kalshi_fee(ask)
# Kalshi taker fee: ceil(0.07 * price * (1 - price) * 100) / 100 per contract
# Polymarket fee: 0 (no explicit taker fee; spread is the cost)
```

Select a trade only when `net_edge > θ`.

### Expected-Edge Gate (θ)

| Account size | θ (Kalshi) | Rationale |
|---|---|---|
| < $2,000 | 15% | Small account; fee drag is proportionally higher |
| ≥ $2,000 | 20% | Standard gate covering fee + execution uncertainty |
| Polymarket | ~5% | No explicit taker fee; spread and gas are the cost |

### Limit Price Posting

When placing maker orders, post your bid θ below model fair value:

```
limit_price_cents = floor((p_model - θ) × 100)
```

This ensures you only fill when the market moves in your favor by at least θ.

### Fractional-Kelly Sizing

```python
f_star = edge / (1 - entry_price)          # full Kelly fraction
stake = min(kelly_frac * f_star * bankroll, max_bet_fraction * bankroll)
contracts = stake / entry_price
# Defaults: kelly_frac=0.25 (quarter-Kelly), max_bet_fraction=0.015
```

The 1.5% bankroll cap is the binding constraint for most trades. Quarter-Kelly is aggressive enough to compound but mild enough to survive a bad run of correlated hits.

### Exposure Caps (observed defaults)

| Cap | Value |
|---|---|
| Per-contract bankroll limit | 1.5% of account |
| Single-city / single-event | 5% of account |
| Total open exposure | 20–25% of account |
| Max slippage as fraction of edge | 50% |

### Slippage Is Part of Selection

Walk the **real NO/YES ladder** to your full size to compute the depth-weighted entry price. If the walk pushes `net_edge` below θ — or slippage exceeds 50% of the edge — skip the trade. Phantom penny levels (≤2¢ asks that don't persist across snapshots and lack trade-print corroboration) must be excluded from the ladder before walking it.

### Maker vs. Taker

Resting a limit order (maker) captures the spread instead of paying it, avoids (or reduces) the taker fee, and is the execution mode used by profitable accounts. The maker edge compounds the structural longshot fade. Market orders (taker) should be used only when the fill probability of a limit order is unacceptably low relative to the opportunity.

All sizing functions are in `scripts/sizing.py`. Run directly for a worked example.

---

## Backtesting Methodology

### Cardinal Rule: Settle on the Venue's Own Result

Never re-derive settlement from a third-party source. Use the venue's `result` field (Kalshi: `result: "yes"/"no"`; Polymarket: settlement transaction). Any derived truth that merely correlates with the venue's resolution can flip ~10% of outcomes and manufacture double-digit fake edges.

### Method Checklist

- [ ] Use venue `result` for settlement — never self-computed truth
- [ ] Use `close_time` (or settlement date from the ticker), not date-of-crawl
- [ ] Decision features cut at the city/event's own local decision time — no UTC mismatch
- [ ] Entry prices from a decision-time snapshot, not near-close prices (which have already converged)
- [ ] Walk the real ladder to your size; cap by top-of-book depth; deduplicate fills
- [ ] Fee-deducted PnL only — never notional
- [ ] Temporal holdout or expanding-window walk-forward only — no shuffled CV
- [ ] Forward paper-trading before live capital: log model p, decision-time ask, and outcome; compare to the backtest Brier/accuracy

### Phantom-Edge Hall of Fame

Each of these produced a plausible-looking backtest that dissolved on closer inspection.

| Bug | Symptom | Fix |
|---|---|---|
| Wrong settlement source | Re-derived truth flipped ~10% of outcomes → fake +18% fade edge | Use venue `result` |
| Bracket off-by-one | 2°F inclusive brackets {floor,cap} treated as 1°F half-open → **+1640%** phantom backtest | Read contract spec carefully |
| Phantom penny asks | ≤2¢ spoofed levels over-credited depth **23×** (250k vs ~9k real fills) | Count only depth that persists across snapshots AND is corroborated by trade prints |
| `strike_type` misread | Inferring greater/less from ticker → **44%** of shadow trades wrong direction | Read `strike_type` from the API — never infer |
| Shadow/live conflation | Replaying a log mixing shadow + live positions → phantom **$14K/contract** wins | Track PnL from live fills only (PositionStore); never replay in-memory |
| Flat/uncalibrated prior | Misconfigured forecast center → **$121.93** live loss in one day | All decisions require a signed, calibrated prior |
| Stale running-extreme seed | Poisoned persisted `day_max` made every low bracket look already-won | Reset/rebuild running-extreme state on startup; never inherit |
| Clock-mismatch look-ahead | Filling at an 18:00Z book snapshot with features cut at 14:00 LST leaked future info for non-Eastern cities | Decide and fill at each market's own local decision time |

### Forward Paper-Trading

Before committing live capital: run the full pipeline in shadow mode. Log model `p`, decision-time ask, and realized settlement. Compare the resulting Brier score and accuracy to the backtest figures. A gap > 2–3 Brier points sustained over 100+ samples indicates data leakage or a distribution shift that must be diagnosed before going live.

---

## Why Forecast Skill ≠ Trading Edge

A good forecast is a necessary but not sufficient condition for a trading edge.

1. **Markets aggregate information.** By decision time, the market price already reflects NWS model output, recent actuals, and whatever edge the sharp accounts have extracted. Your forecast must be measurably *better than the market* — not just accurate.

2. **Brier score is not edge.** A 0.07 OOS Brier score (better than climatology) is consistent with zero net edge if the market is priced at 0.07 too.

3. **The actual edge is behavioral.** The longshot overpricing is not informational — it's behavioral (retail overconfidence in cheap contracts). You capture it by being the liquidity provider on the tail, regardless of your forecast quality in those brackets.

4. **Forecast-driven YES entries work only at the margin.** When your calibrated model says a bracket is *materially* underpriced (> θ net edge after fees), buying YES is valid. But this is a small subset of decision points, and the fill rate on thin tails constrains capacity.

The practical implication: build and validate your forecast for its own sake (it improves NO-bid targeting and limits exposure in adverse conditions), but do not assume forecast accuracy translates to trading returns without a separate, correct, fee-inclusive backtest.

---

## Evidence & Literature

### Foundational Results

- **Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market*** (CEPR VoxEU; GWU/UCD working papers). 300k+ Kalshi contracts. Average pre-fee return ≈ −20%, concentrated in takers and longshot buyers. Makers earn positive returns. The foundational result: winners provide liquidity, losers take it.

- **Large-N Polymarket maker-taker study** (588M+ trades, SSRN). Top ~1% of accounts capture ~76.5% of profit, predominantly by resting limit orders. Confirms the maker edge generalizes across venues.

- **Gupta, *Who Profits in Binary Prediction Markets? Maker–Taker Dynamics, Behavioral Bias, and Sentiment Arbitrage on Kalshi*** (SSRN). Microstructure + behavioral-bias treatment of who wins and why.

### Favorite–Longshot Bias

- Classic betting-market literature (Thaler, Ziemba): longshots win less often than their price implies across most wagering markets.
- Kalshi-specific: ~$0.05 contract historically wins ~2%; sub-$0.10 contracts lose ~60% of stake to buyers. Favorites are fairly- to slightly-underpriced.
- The tradeable expression: NO-side maker bid on cheap brackets, diversified.

### Internal Validation (bracket-model skill)

- Fee-inclusive rotating-CV backtest on Kalshi weather markets: ~+1.7–3.3% taker ROI / +7.9–9% maker ROI on the longshot fade.
- Realized hit-rate on brackets priced ~10%: ~3–7% → ~+6.7¢/contract gross; maker economics improve this further.

### What the Evidence Does NOT Support

- That a good weather or event forecast beats the market at decision time (redundant with the price — see Lessons above).
- That retail-visible cross-venue or intra-venue arbitrage is repeatably profitable net of fees/geo/lockup.
- That the edge concentrates where your forecast is most accurate (it tracks market thinness/retail-ness instead).

> Verify specific figures against primary sources before sizing — magnitudes vary by sample window and venue.

---

## Files

### References
- `references/strategy-catalog.md` — Full strategy verdicts with evidence and catches
- `references/sizing-and-edge-gates.md` — Complete fee-aware sizing rules and gate derivations
- `references/backtesting-methodology.md` — Settle-on-venue-result rule, phantom-edge hall of fame, method checklist
- `references/evidence-and-literature.md` — Primary sources: Whelan, Polymarket 588M, Gupta, favorite-longshot magnitudes

### Scripts
- `scripts/sizing.py` — `kalshi_fee`, `net_edge`, `theta_for_account`, `limit_price_cents`, `kelly_contracts`, `slippage_ok` — pure stdlib, runs offline
