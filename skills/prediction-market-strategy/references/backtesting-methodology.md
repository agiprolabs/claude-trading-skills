# Backtesting Methodology

A correct backtest for prediction market strategies is harder than it looks. Every item in this document corresponds to a real bug that produced a plausible-looking result that later dissolved. Read it before trusting any backtest number.

---

## The Cardinal Rule: Settle on the Venue's Own Result

Never re-derive settlement from a third-party source (weather APIs, news feeds, closing prices). Use the venue's `result` field:

- **Kalshi:** `result: "yes"` or `result: "no"` from the markets API
- **Polymarket:** settlement transaction on-chain

A derived truth that "merely correlates" with the venue's resolution can flip ~10% of outcomes. Even a plausible-seeming re-derivation (e.g., `floor(t) ≤ round(NWS_temp) < cap`) that misses the venue's actual rule (2°F inclusive: `t ∈ {floor, cap}`) flipped enough outcomes to manufacture a fake **+18% fade edge** that did not exist.

---

## Phantom-Edge Hall of Fame

Each of these produced a real, plausible backtest that dissolved under scrutiny. Track which of these you have audited.

| Bug | Symptom | Fix |
|---|---|---|
| Wrong settlement source | Re-derived truth (floor ≤ round(t) < cap instead of t ∈ {floor,cap}) flipped ~10% of outcomes → fake **+18% fade edge** | Use venue `result` only |
| Bracket off-by-one | 2°F inclusive brackets {floor,cap} treated as 1°F half-open [floor,cap) → **+1640%** phantom backtest | Read contract spec; confirm with the venue |
| Phantom penny asks | ≤2¢ ask levels that don't persist across snapshots over-credited depth **23×** (250k vs ~9k real fills) | Count only depth that persists across snapshots AND is corroborated by trade prints |
| `strike_type` misread | Inferring greater/less direction from the ticker instead of reading the API field → **44%** of shadow trades wrong direction, ~$88/day phantom loss | Read `strike_type` from the API; never infer from ticker |
| Shadow/live conflation | Replaying a trade log that mixes shadow + live positions → phantom **$14K/contract** wins | Track PnL from live fills only (use a PositionStore); never in-memory replay |
| Flat/uncalibrated prior | Misconfigured (flat) forecast center → **$121.93** loss in one day | All decisions require a signed, calibrated prior |
| Stale running-extreme seed | Persisted `day_max` poisoned by a bad file made every low bracket appear already-won | Reset/rebuild running-extreme state on startup; never inherit from disk |
| Clock-mismatch look-ahead | Filling at an 18:00Z book snapshot with features cut at 14:00 LST → non-Eastern cities used information from the future | Decide and fill at each market's own local decision time |
| UTC vs local-day feature aggregation | Aggregating forecast features over UTC days instead of the local clock day the venue settles on → misaligned labels, ~14 percentage-point accuracy drop in one study | All aggregation on local settlement-date clock |
| Near-close price as decision price | Using a near-close price (already converged) as the decision-time ask → trades that would never have filled appear profitable | Use decision-time snapshot prices; the mispricing is a decision-time phenomenon |
| Infinite-liquidity / undeduped fills | Assuming full size fills at best price, or counting the same fill twice → inflated ROI | Cap by real top-of-book depth; dedupe across snapshots |

---

## Method Checklist

Work through this before reporting any backtest result.

**Settlement**
- [ ] Settlement from venue `result` field — never self-computed
- [ ] Contract spec confirmed: inclusive vs half-open ranges, which integers are covered
- [ ] `strike_type` read from API for each contract — not inferred

**Timestamps & Clocks**
- [ ] Settlement date from `close_time` or ticker — not date-of-crawl
- [ ] Features cut at the market's local decision time — no UTC/LST mismatch
- [ ] Entry price from a decision-time book snapshot — not near-close (converged) price

**Fills & Depth**
- [ ] Entry price: depth-weighted after walking the ladder to target size
- [ ] Phantom penny levels (≤2¢ non-persistent, unprinted) stripped from the ladder
- [ ] Fills capped by real top-of-book depth; no infinite-liquidity assumption
- [ ] Fills deduplicated across snapshots

**Fees & PnL**
- [ ] All PnL is fee-deducted — never notional
- [ ] Taker fee applied to taker fills; maker rebate (if applicable) applied to maker fills
- [ ] Net-edge gate applied at decision time — not at the end as a filter

**Validation**
- [ ] Temporal holdout or expanding-window walk-forward — no shuffled CV
- [ ] Training data cutoff is strictly before test period — no future-data contamination
- [ ] Synthetic market / infinite-liquidity fill model flagged as a forecast-skill metric, NOT a profit forecast (use only for Brier/accuracy benchmarking)

---

## Forward Paper-Trading

No amount of backtest work is a substitute for forward paper-trading before live capital.

**Protocol:**
1. Run the full pipeline in shadow mode (no live orders).
2. At each decision point, log: `(market_id, p_model, decision_time_ask, net_edge, action_taken)`.
3. After settlement, record the `venue_result` and compute realized PnL as if the trade had executed.
4. After 100+ samples: compare realized Brier score and accuracy to the backtest figures.

**Red flags:**
- Realized Brier score > 2–3 points worse than backtest → likely a leakage or distribution-shift issue.
- Fill rate on maker limit orders significantly below expectation → the tail is thinner than modeled.
- Net edge positive in backtest but near-zero in paper-trading → decision-time ask is higher than backtest assumed (e.g., near-close prices were used).

**Only promote to live after paper-trading confirms the edge is real at execution.**
