# Sizing & Edge Gates

All trade selection is on **fee-adjusted net edge**. Raw win-rate, return on notional, "% correct," and Brier score are not selection metrics — they do not account for fees or for the price you paid.

---

## Fee-Aware Net Edge (the only selection metric)

```
net_edge = p_model - ask - kalshi_fee(ask)
```

Where:
- `p_model` — your calibrated model probability (isotonic-calibrated; verified against OOS held-out data)
- `ask` — the depth-weighted entry price after walking the ladder to your target size
- `kalshi_fee(ask)` — Kalshi taker fee per contract: `ceil(0.07 × ask × (1 − ask) × 100) / 100`
- For Polymarket: fee = 0 (no explicit taker fee; the spread and gas are the cost)

**Select a trade only when `net_edge > θ`.** If the ladder walk pushes net_edge below θ — even if the top-of-book looks favorable — skip the trade.

### Fee Shape

The Kalshi fee is quadratic in price: maximal near $0.50 (~$1.75/contract at max), falling toward zero at $0.01 and $0.99. This makes deeply out-of-the-money and near-certainty contracts relatively cheaper to trade on a fee basis, while mid-probability contracts carry the heaviest fee load.

---

## Expected-Edge Gate (θ)

| Account size | θ (Kalshi) | Rationale |
|---|---|---|
| < $2,000 | 15% | Small account; fee drag proportionally higher |
| ≥ $2,000 | 20% | Standard gate; covers fee + execution uncertainty |
| Polymarket | ~5% | No explicit taker fee; spread and gas are the cost |

θ is the minimum net_edge for a trade to be taken. It is not the expected return — it is the threshold that must be cleared to cover: (1) Kalshi fee, (2) uncertainty in model calibration, and (3) adverse selection from the maker on the other side.

---

## Limit Price Posting (Maker Orders)

When resting a maker order, post your bid θ below model fair value:

```
limit_price_cents = floor((p_model − θ) × 100)
```

This ensures you only fill when the market moves in your favor by at least θ — i.e., the market is offering a price at least θ below your model value. If the market doesn't reach your bid, you don't fill, which is correct: you only want to trade when the edge is real.

---

## Position Sizing

### Fractional-Kelly Formula

```python
f_star = net_edge / (1 − entry_price)    # full Kelly fraction on these odds
stake   = min(kelly_frac × f_star × bankroll, max_bet_fraction × bankroll)
contracts = stake / entry_price
```

Defaults:
- `kelly_frac = 0.25` (quarter-Kelly — standard for correlated, uncertain signals)
- `max_bet_fraction = 0.015` (1.5% of bankroll per contract)

The cap is usually the binding constraint. Full Kelly is theoretically optimal under log-utility with known probabilities; in practice, model uncertainty and correlation mean quarter-Kelly is more appropriate.

---

## Exposure Caps (observed defaults)

| Cap | Value | Rationale |
|---|---|---|
| Per-contract bankroll limit | 1.5% of account | Tail risk; single hit should not be material |
| Single-city / single-event | 5% of account | Correlated exposures within an event series |
| Total open exposure | 20–25% of account | Reserve against correlated-loss scenarios |
| Max slippage as fraction of edge | 50% | Abort if the ladder walk consumes half the edge |

---

## Slippage Is Part of Selection

Compute the entry price by **walking the real NO/YES ladder** to your size — not the displayed best price.

```python
# For each level in the ladder (sorted by price, ascending for NO bids):
# accumulated_contracts += level.size
# accumulated_cost += level.size × level.price
# depth_weighted_entry = accumulated_cost / accumulated_contracts
```

Then re-compute `net_edge` at the depth-weighted entry. If:
- `net_edge < θ` → skip
- `slippage > 0.50 × net_edge` → skip

Phantom penny levels (≤2¢ asks that do not persist across consecutive snapshots AND are not corroborated by trade prints) must be stripped before walking the ladder — they are spoofed and will not fill.

---

## Maker vs. Taker

| Mode | Fee | Edge direction | When to use |
|---|---|---|---|
| Maker (rest limit order) | Reduced or zero | Captures spread + longshot premium | Default for tail-fade and most forecast-driven entries |
| Taker (market order) | Full Kalshi fee | Pays spread | Only when fill probability of a limit order is unacceptably low relative to the opportunity window |

The maker edge compounds the structural longshot fade. Across large samples, makers earn positive returns while the average taker loses ~20% pre-fee. Default to maker.

---

## Implementation

See `scripts/sizing.py` for runnable implementations of:
- `kalshi_fee(price, contracts, rate)` — fee in dollars
- `net_edge(p_model, ask, *, fee)` — fee-aware net edge per contract
- `theta_for_account(bankroll)` — edge gate by account size
- `limit_price_cents(p_model, theta)` — maker bid in cents
- `kelly_contracts(p_model, entry, bankroll, *, kelly_frac, max_bet_fraction)` — fractional-Kelly size
- `slippage_ok(edge, slip, *, max_frac)` — slippage guard
