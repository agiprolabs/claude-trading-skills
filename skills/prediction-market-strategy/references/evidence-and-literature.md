# Evidence & Literature

Primary sources and internal validation results that underpin the strategy thesis. Verify figures against primary sources before sizing — magnitudes vary by sample window and venue.

---

## The Maker/Taker Divide (the spine)

### Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market*
CEPR VoxEU column; GWU/UCD working papers.

Across **300k+ Kalshi contracts**, the average **pre-fee return is ≈ −20%**, concentrated in **takers** (market-order users) and in **longshot buyers**; **makers** (resting limit orders) earn positive returns.

This is the foundational result: winners provide liquidity, losers take it. The Kalshi market is not a zero-sum game at the aggregate — takers systematically subsidize makers.

### Large-N Polymarket Maker-Taker Study
SSRN; 588M+ trades.

The **top ~1% of accounts capture ~76.5% of profit**, predominantly by **resting limit orders**. Confirms the maker edge generalizes across venues and is not a Kalshi-specific artifact. The distribution of outcomes is highly concentrated — a small number of sophisticated market-makers capture nearly all the surplus from the much larger population of retail takers.

### Gupta, *Who Profits in Binary Prediction Markets? Maker–Taker Dynamics, Behavioral Bias, and Sentiment Arbitrage on Kalshi*
SSRN.

Microstructure + behavioral-bias treatment of who wins and why. Covers adverse selection, sentiment-driven overpricing of longshots, and the conditions under which maker-side strategies extract durable returns.

---

## Favorite–Longshot Bias (the mechanism)

### Classic betting-market literature (Thaler, Ziemba, et al.)
Longshots win less often than their price implies across most wagering markets. This is one of the most replicated findings in financial economics, predating prediction markets by decades. The mechanism is behavioral: retail participants are systematically overconfident in cheap contracts (low-probability, high-payout).

### Kalshi-specific magnitudes
- A ~$0.05 contract historically wins ~2% of the time (priced at 5% → ~60% overpriced).
- Sub-$0.10 contracts lose ~60% of stake to buyers in aggregate.
- Favorites (> $0.70) are fairly- to slightly-**underpriced** — the flip side of the longshot bias.

### Tradeable implication
The repeatable expression: **seller of the overpriced longshot tail, maker-side** (rest NO bids on brackets priced ~$0.05–$0.20), diversified across many events to survive the rare hit. This is structural/behavioral, not forecasting-dependent.

---

## Bracket-Model Skill (reference, internal validation)

Internal rotating-CV backtest on Kalshi weather markets (fee-inclusive):

| Execution mode | Estimated ROI on longshot fade |
|---|---|
| Taker | ~+1.7–3.3% |
| Maker | ~+7.9–9.0% |

Gross per-contract edge on brackets priced ~10% with realized hit-rate ~3–7%: **~+6.7¢/contract** before fee. Maker economics improve this further.

These figures are from a correctly-settled (venue `result`), fee-inclusive backtest. They represent forecast-skill confirmation, not a profit forecast (fills were against a synthetic market — real fill rate and depth constraints apply).

---

## Pricing-Theory References

- **Manski (2006), "Interpreting the Predictions of Prediction Markets"** — foundational: market price = mean belief under certain conditions; not a consensus probability in the frequentist sense. Relevant when building a pricing model.
- **Gjerstad & Hall (2005)** — pricing dynamics and efficiency in thin prediction markets.
- **Wolfers & Zitzewitz (2004)** — prediction markets as forecasting tools; limitations when markets are thin or manipulable.

---

## What the Evidence Does NOT Support

- That a good weather or event forecast beats the market at decision time. Forecasts are largely redundant with the price — markets aggregate NWS/ECMWF/GFS output efficiently enough that retail models add little.
- That retail-visible cross-venue or intra-venue arbitrage is repeatably profitable net of fees, geo-lock, and transfer time.
- That the edge concentrates where your forecast is most accurate. The longshot-fade edge tracks market **thinness and retail-ness**, not forecast quality.
- That copying apparently-profitable accounts produces durable returns. Survivorship bias; no reliable public signal.
