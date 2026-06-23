# Backtesting Methodology

Prediction-market backtests are unusually easy to fake out. Every phantom edge below was *real-looking* until the bug was found. The discipline that survives:

## The cardinal rule: settle on the venue's own result

Score every contract against the **venue's authoritative resolution**, never a derived truth source that merely correlates:
- **Kalshi:** the `result` field (`"yes"`/`"no"`) from `GET /markets?event_ticker=...`, or IEM-ASOS daily CLI which is a **100% match**. Apply the exact rule: bracket YES iff `cli ∈ {floor, cap}`; threshold greater iff `cli ≥ T+1`, less iff `cli ≤ T−1`.
- **Polymarket:** the on-chain resolution / `outcomePrices` (`["1","0"]`=YES won).
- **Never** settle on grid actuals / model reanalysis (leaky + inaccurate), nor on a different station/clock than the venue uses.

## Phantom-edge hall of fame (each cost real credibility)

| Bug | Symptom | Fix |
|---|---|---|
| Wrong settlement source | Re-deriving truth with `floor ≤ round(t) < cap` (1°F half-open) instead of `t ∈ {floor,cap}` (2°F inclusive) flipped ~10% of outcomes → fake **+18% "fade edge."** | Settle on venue `result`. |
| Bracket off-by-one | Treating 2°F brackets as 1°F → **+1640%** phantom backtest. | `B<c>` covers two integers {floor,cap}. |
| Phantom penny asks | Filling against spoofed ≤2¢ levels over-credited depth **23×** (250k vs ~9k real). | Count only depth that persists across snapshots AND is corroborated by trade prints. |
| `strike_type` misread | Inferring greater/less from the ticker → **44%** of shadow trades wrong-direction, ~$88/day. | Read `strike_type` from the API. |
| Shadow/live conflation | Replaying a trade log that mixes shadow + live positions → phantom **$14K/contract** wins. | Track P&L from live fills only (a `PositionStore`), not in-memory replay. |
| Flat/uncalibrated prior | A misconfigured (flat) forecast center → **$121.93** loss in one day. | All decisions use the signed, calibrated prior. |
| Stale running-extreme seed | A persisted running `day_max` seeded from a poisoned file made every low bracket look already-won. | Reset/rebuild running-extreme state on startup; never inherit. |

## Method checklist

1. **Leak-free validation.** Use a **temporal holdout** or expanding-window walk-forward; never report shuffled-CV as out-of-sample. The risk is dataset-level train/test overlap.
2. **Decision-time, not near-close.** Settled-market APIs return *converged* prices. The tradeable mispricing is a decision-time phenomenon — measure edge at your actual decision hour (each city's own local time), not at the near-close print.
3. **Clock alignment.** Decide/fill at each city's own local decision time. Filling an 18:00Z snapshot with features cut at 14:00 LST trades non-Eastern cities on future info. Aggregate features on the **local-clock day the venue settles on** (UTC-day aggregation cost ~14pp accuracy in one study).
4. **Real-ladder fills + fees.** Walk the captured ladder to your size with the Kalshi fee; cap by real top-of-book depth; dedupe contracts. Infinite-liquidity / best-price fills inflate ROI.
5. **Date from the ticker.** `KXHIGHNY-26JUN21` settles 2026-06-21; `close_time` is next-day UTC (~00:59 ET). Join on the ticker date.
6. **Maker fill realism.** A resting maker bid does not always fill. Either model fill from the trade tape (a taker hitting your price) or forward-paper-trade to measure the real fill-rate before trusting maker ROI.
7. **Rotating cross-validation** over contiguous date folds; report pooled + per-fold (a single bad fold reveals tail risk).

## Forward paper-trading

The cleanest validation of a maker strategy: rest your intended bids, measure fills from the **real trade tape** (a taker selling into your bid), settle on the venue result, accrue P&L — no real orders. It resolves the two unknowns a historical backtest can't: maker **fill-rate** and out-of-sample multi-day P&L.
