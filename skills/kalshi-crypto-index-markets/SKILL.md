---
name: kalshi-crypto-index-markets
description: Kalshi daily and hourly range markets on crypto prices (BTC, ETH) and equity indices (S&P 500, Nasdaq-100) — bracket structure, Gaussian P(YES) modeling on price/vol, close-offset decision timing, longshot-sell edge with honest evidence bounds
---

# Kalshi Crypto & Index Range Markets

Kalshi lists daily (and for crypto, hourly) **range bracket markets** on the level of four liquid underlyings: S&P 500, Nasdaq-100, Bitcoin, and Ethereum. The math is the same partition-and-Gaussian framework as weather brackets — the variable is just price/return and σ comes from the underlying's realized or implied volatility, not a temperature model.

> Cross-references: for Kalshi API mechanics see `kalshi-api`; for the strategy, sizing, and backtesting framework see `prediction-market-strategy`; for the temperature counterpart see `kalshi-weather-markets`; for the shared bracket/overround formulas see `prediction-markets/references/brackets-and-settlement.md`.

---

## Series & Market-Type Mapping

```python
SERIES_MARKET = {
    "KXINX":       "index",   # S&P 500 index level
    "KXNASDAQ100": "index",   # Nasdaq-100 index level
    "KXBTC":       "crypto",  # Bitcoin price (USD)
    "KXETH":       "crypto",  # Ethereum price (USD)
}
```

- `market_type = "index"` — daily range only; underlying is the index points level at the official market close.
- `market_type = "crypto"` — daily **and hourly** range markets; BTC and ETH each have multiple hourly events running in parallel with the daily.

Cadence is higher than weather: crypto hourlies open and settle throughout the day; daily markets open the prior session and settle at the reference close.

---

## Bracket Structure

Each event is a **mutually exclusive, collectively exhaustive** partition of the underlying's possible values at settlement:

- An interior bracket `B<center>` covers a contiguous price band (floor to cap, both-ends-inclusive). Bracket widths are set per-market — read the event's market list; do not assume a fixed width.
- Two open-tail markets anchor the partition: a `less-than` (below the lowest bracket floor) and a `greater-than` (above the highest bracket cap).
- At settlement exactly **one** bracket is YES; all others are NO.

The overround (sum of all YES prices) is typically > 1.0. The excess is concentrated in the cheap tails — the same favorite–longshot bias seen in weather markets. See `prediction-markets/references/brackets-and-settlement.md` for the overround formula.

---

## Gaussian P(YES) on Price/Vol

Given a price forecast distribution `N(μ, σ)` for the underlying at settlement, with bracket covering `[floor, cap]`:

```
# interior bracket
P(YES) = Φ((cap − μ) / σ) − Φ((floor − μ) / σ)

# open-tail, "greater than cap"
P(YES) = 1 − Φ((cap − μ) / σ)

# open-tail, "less than floor"
P(YES) = Φ((floor − μ) / σ)
```

`Φ` is the standard normal CDF. Unlike temperature brackets (which settle on integers), price brackets settle on a continuous reference price — the half-integer continuity correction used for weather is **not applicable here**. Do not add ±0.5.

### Sourcing σ

- **Realized vol:** rolling 5- or 20-day realized volatility of the underlying, scaled to the settlement horizon.
- **Implied vol:** the ATM IV from listed options (SPX/NDX for index, CME/Deribit for crypto) is a forward-looking σ that already embeds the market's distributional view for the horizon.
- **Hourly markets:** for BTC/ETH hourlies, σ is the 1-hour IV or intraday realized vol. Σ shrinks rapidly — even small absolute moves land in a different bracket. Sensitivity is high; prefer IV-derived σ.

For daily markets, a simple log-return diffusion gives `σ_daily ≈ σ_annual / √252` for index, or the equivalent annualized vol / √365 for crypto. Express in price units (not %) before inserting into the formula.

---

## Decision Timing — Close-Offset, Not a City Hour

**This is the key difference from weather markets.**

Weather settles on a daily extreme that occurs at some unknown intraday time. The decision book is read near the likely peak/trough (a city-local hour).

Crypto and index markets settle at a **fixed reference close**:

- Daily S&P 500 / Nasdaq-100: the official market close (4:00 PM ET).
- Daily BTC/ETH: a defined reference close published in the market's rulebook.
- Hourly BTC/ETH: the close of each hour interval per the rulebook.

The practical convention used in production:

```python
DECISION_OFFSET_MINUTES = 120   # read book ~2h before settlement close
decision_ts = settlement_close_ts - timedelta(minutes=DECISION_OFFSET_MINUTES)
```

This offset balances information freshness (IV and order-book signal) against the risk of being front-run by news that drops in the final window. Tune per-series based on your fill-rate observations.

---

## Settlement — Verify the Rulebook Reference

Settlement is on Kalshi's own `result` field. **Do not re-derive from an external feed.** The exact reference price for each series (e.g., official SPX close vs. a crypto composite) is specified per-market in the Kalshi rulebook.

Honest caveat: the exact reference price spec was not pinned for every series during development. Before trading any new series, read the market's rulebook and confirm:
1. The settlement price source (exchange, composite, or Kalshi-computed).
2. The settlement time and timezone.
3. Whether the bracket is inclusive/exclusive at the boundary.

Backtesting against a price feed that differs from the true settlement source is the primary way to manufacture fake edge in these markets.

---

## Edge: Longshot-Sell Generalization

The **favorite–longshot bias** generalizes from weather to index and crypto brackets. Tail brackets are systematically overpriced relative to a Gaussian model calibrated to realized/implied vol; interior brackets near the current underlying level are fairly priced or underpriced.

### Evidence (be precise about depth)

From production testing with a rotating CV approach, Kalshi-settled outcomes, fee-inclusive:

| Market type | Sweet band | Edge direction | Sample | Result |
|-------------|-----------|----------------|--------|--------|
| **Index** | Market-implied P ∈ [0.05, 0.20] | Longshot-sell (short tail brackets) | ~50 trades | ~+1.7% taker / ~+9% maker |
| **Crypto daily** | — | — | Too sparse | Inconclusive |
| **Crypto hourly** | — | — | Too sparse | Inconclusive |

**Interpret conservatively.** ~50 trades is not a stable estimate; confidence intervals are wide. The index result is directionally consistent with the weather finding and prior literature on longshot bias, but treat it as a hypothesis to validate forward, not a confirmed edge.

### The HFT Caveat (critical for hourlies)

Crypto and index markets settle on public, real-time price ticks. The underlying is continuously quoted on liquid venues with sub-millisecond latency. This means:

- The information content of any bracket price is rapidly arbitraged by HFT and market-maker algos watching the same tick.
- **Latency front-running** — buying or selling brackets based on price moves — is a colocation/HFT game. From a retail connection you will be consistently on the wrong side of news-driven bracket repricing.
- The retail-feasible angle is the **structural longshot-sell** (exploiting the persistent overpricing in cheap tails that is stable across market regimes), not speed-based positioning.
- Hourly crypto markets are the most HFT-contested of all Kalshi markets. Maker fills on tail brackets may be scarce precisely when the edge is largest.

---

## Market Microstructure Notes

- **Overround** is the primary microstructure signal. For a partition of N brackets, `overround = Σ P_yes`. When overround > 1.10 in the tails, the aggregate tail sell has positive expected value before fees; after Kalshi taker fees (~7 cents/$1 per leg) the bar is higher. Maker rebates change the math substantially.
- **Thin books:** individual bracket markets on hourly crypto may show wide spreads and low depth. Model a realistic fill at a depth level before sizing.
- **Basket dutch:** selling the complete set of tail brackets is not trivially an arb even when overround > 1.0; fees per leg plus execution uncertainty can eliminate the overround advantage. See `prediction-market-strategy` for the dutch/portfolio treatment.

---

## Files

### References
- `references/structure-and-modeling.md` — Series details, bracket structure, σ-from-vol modeling, decision timing, settlement
