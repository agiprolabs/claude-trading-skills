# Lessons & Pitfalls

Hard-won findings from running weather/event prediction-market systems across multiple venues. Each pitfall below has, at some point, produced a *plausible but false* result.

## The durable edge: favorite–longshot bias, maker-side

- **Cheap longshots are systematically overpriced.** Contracts under ~$0.20 win less often than their price implies (a $0.05 contract historically wins ~2%; sub-$0.10 contracts lose ~60% of stake to buyers). Favorites are fairly- to slightly-under-priced.
- **Winners provide liquidity; losers take it.** Across large samples, the average **taker** loses ~20% pre-fee; **makers** earn positive returns. On Polymarket, the top ~1% of accounts capture the majority of profit by **resting limit orders**. Sources: Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market* (CEPR/GWU); large-N Polymarket maker-taker studies (SSRN); Gupta, *Who Profits in Binary Prediction Markets* (SSRN).
- **Therefore:** the repeatable expression is **selling the overpriced longshot tail, maker-side** (rest a NO bid on the cheap brackets), diversified across many events to survive the rare hit. It is **structural/behavioral**, *not* a forecasting edge.

## Forecasting ≠ trading edge

A genuinely good forecast often does **not** beat the market at decision time, because the market has already incorporated the same observations (e.g. the afternoon METAR by the high-temp decision hour). Measure `corr(your_p − market_p, realized)` — if it's near zero or negative, your model is *redundant with*, not *better than*, the price. The forecast's value is more likely as a **tail filter** (avoid selling a longshot your model says is unusually likely) and **venue/city selection**, than as standalone alpha. The longshot edge does **not** concentrate in the cities where your forecast is most accurate — it concentrates where the market is thin/retail.

## Backtesting pitfalls (each produced a phantom edge)

1. **Wrong settlement source.** Scoring against a *derived* truth that merely correlates with the venue's resolution flips ~10% of outcomes and can manufacture a double-digit fake edge. **Settle on the venue's own `result`.** (See brackets-and-settlement.md.)
2. **Bracket off-by-one.** Treating 2°F inclusive brackets `{floor,cap}` as 1°F half-open `[floor,cap)` → +1640% phantom backtest.
3. **Phantom penny asks.** 1¢ ask levels are frequently spoofed; assuming you fill against them over-credited PnL ~23×. Count only depth that **persists across snapshots AND is corroborated by trade prints**; walk the *real* ladder with fees.
4. **Date-in-ticker, not `close_time`.** `KXHIGHNY-26JUN21` settles 2026-06-21; `close_time` is next-day UTC (~00:59 ET). Joining on `close_time` off-by-ones every label.
5. **Clock-mismatch look-ahead.** Filling at an 18:00Z book snapshot while features are cut at 14:00 LST trades non-Eastern cities on information from the future. Decide and fill at each city's *own* local decision time.
6. **UTC vs local-day feature aggregation.** Aggregating forecast features over UTC days instead of the **local-clock day the venue settles on** misaligned labels and cost ~14 percentage points of accuracy in one study.
7. **Infinite-liquidity / undeduped fills.** Assuming you fill the full size at the best price, or double-counting contracts, inflates ROI. Cap by real top-of-book depth and dedupe.
8. **Near-close ≠ decision-time.** Settled-market APIs return prices that have already converged. The tradeable mispricing is a *decision-time* phenomenon; don't measure edge at the converged near-close print.

## Strategies that look good but mostly aren't (retail scale)

- **Intra-venue "dutching"** (buy/sell the whole bracket set when prices sum off 1.0): real arb in theory, but Kalshi's per-leg `0.07·p·(1−p)` fee × N legs plus thin/phantom books usually exceeds the few-cent overround gap.
- **Cross-venue Kalshi↔Polymarket arb:** blocked for most by **geo/KYC** (one legal entity can't cheaply hold both legs), capital lockup until resolution, USDC↔USD friction, and **resolution-rule divergence** (different source/station/DST → the "same" market can settle differently).
- **Latency/news front-running** on crypto/index hourlies: increasingly an HFT/colo game; retail loses the race and gets adversely selected on its own resting quotes.
- **Copy-the-sharps:** mostly survivorship + capacity decay; usable only as a self-computed flow *input*, never blind copy.

## Operational gotchas

- **Kalshi host:** `api.elections.kalshi.com/trade-api/v2` only; the old hosts 401.
- **Kalshi order schema:** dollar-strings (`count_fp`, `yes_price_dollars`), `time_in_force` required, no `type` field, `client_order_id` is `[A-Za-z0-9-]` (sanitize the bracket `.`).
- **`strike_type` is not inferable from the ticker** — read the API field (a misread cost a measurable daily loss gap).
- **Polymarket sort default is oldest-first** — always set `order`/`ascending` or you query closed markets.
- **YES/NO are both bid ladders on Kalshi** — `no_ask = 1 − best_yes_bid`; inverting this silently flips every signal.
