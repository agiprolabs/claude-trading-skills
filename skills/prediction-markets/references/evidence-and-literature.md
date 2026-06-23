# Evidence & Literature

The empirical basis for the favorite–longshot / maker-edge thesis, and where to verify it. Read these before betting real capital on the structural edge.

## The maker/taker divide (the spine)

- **Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market*** (CEPR VoxEU column; GWU/UCD working papers). Across 300k+ Kalshi contracts the average **pre-fee return is ≈ −20%**, concentrated in **takers** (market-order users) and in **longshot buyers**; **makers** (resting limit orders) earn positive returns. This is the foundational result: winners provide liquidity, losers take it.
- **Large-N Polymarket maker-taker study** (588M+ trades, SSRN): the **top ~1% of accounts capture ~76.5% of profit**, predominantly by **resting limit orders**. Confirms the maker edge generalizes across venues.
- **Gupta, *Who Profits in Binary Prediction Markets? Maker–Taker Dynamics, Behavioral Bias, and Sentiment Arbitrage on Kalshi*** (SSRN). Microstructure + behavioral-bias treatment of who wins and why.

## Favorite–longshot bias (the mechanism)

- Cheap longshots are systematically **overpriced**: a ~$0.05 contract historically wins ~2%; sub-$0.10 contracts lose ~60% of stake to buyers. Favorites are fairly- to slightly-**under**-priced. (Whelan; classic favorite–longshot literature from betting markets; Kalshi-specific replications.)
- Implication: the repeatable trade is **selling the overpriced longshot tail, maker-side**, diversified — not buying favorites, not forecasting.

## Bracket-model skill (reference, internal validation)

A calibrated bracket model is genuinely skillful relative to a uniform prior, but that skill is *not* the trading edge (the market shares the information):

| | Kalshi (2°F) | Polymarket (1°C) |
|---|---|---|
| Top-1 hit rate | ~55% | ~51% |
| Random baseline | 16.7% (1/6) | 9.1% (1/11) |
| Lift over random | ~3.3× | ~5.6× |

## Pricing-theory references

- *Toward Black-Scholes for Prediction Markets: A Unified Kernel and Market Maker's Handbook* (arXiv 2510.15205) — market-making/pricing theory for binary CLOBs.
- *Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets* (arXiv 2508.03474) — overround/dutching arbitrage analysis.
- *Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets* (arXiv 2602.19520) — which domains are mis-calibrated.

## What the evidence does NOT support

- That a good weather forecast beats the market at decision time (it's redundant with the price — see `forecasting-for-brackets.md`).
- That retail-visible cross-venue or intra-venue arbitrage is repeatably profitable net of fees/geo/lockup (see `strategy-catalog.md`).
- That the edge concentrates where your forecast is most accurate (it tracks market thinness/retail-ness instead).

> Verify the specific figures against the primary sources before sizing — magnitudes vary by sample window and venue.
