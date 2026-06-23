# Sizing & Edge Gates

How to turn a model probability into a trade: select on **fee-adjusted net edge**, gate on a threshold, size with fractional Kelly, and cap exposure. These are the risk rules that keep a real edge from being eaten by fees, slippage, and tail variance.

## Fee-aware net edge (the only selection metric)

Never select on raw win-rate or raw model edge — always net of the fee you'll pay:

```
fee_per_contract(ask) = ceil(0.07 · ask · (1 − ask) · 100) / 100      # Kalshi; Polymarket = 0
net_edge(p_model, ask) = p_model − ask − fee_per_contract(ask)
```

Trade only when `net_edge > θ`. The fee peaks at ask=0.50 (~1.75¢) and shrinks toward the wings, which is one reason the cheap-tail longshot-sell survives.

> The `0.07` coefficient is an **exchange convention that can change** — verify the current Kalshi fee schedule at <https://docs.kalshi.com> before relying on it for live sizing.

## Expected-edge gate (θ)

A minimum net edge before any order. Observed production values:

| Account size | θ (Kalshi) |
|---|---|
| < $2,000 | **15%** |
| ≥ $2,000 | **20%** |
| Polymarket (zero-fee) | **5%** net of slippage |

Limit price from the model and gate (Kalshi, cents):
```
P_limit = floor((P_model − θ) · 100)        # post your bid θ below model fair value
```

## Position sizing

- **Fractional Kelly** on the net-edge odds: `f* = net_edge / (1 − entry)`, scaled by a Kelly fraction (e.g. 0.25). Binary-contract Kelly.
- The tail risk of selling longshots means **small per-bracket size + broad diversification** matter more than squeezing Kelly — a single faded longshot that hits costs ~(1−entry).

## Exposure caps (observed defaults)

| Cap | Value | Purpose |
|---|---|---|
| `MAX_BET_FRACTION` | 1.5% of bankroll / trade | per-position risk |
| `MAX_DAILY_WAGER_FRACTION` | 15% of bankroll / day | daily deployment |
| `MAX_SLIPPAGE_FRACTION_OF_EDGE` | 0.50 | abort if walking the ladder eats > half the edge |
| `MIN_CITY_HITRATE` | 0.45 | only trade cities the model actually predicts |
| per-track daily cap | ~25% of daily bankroll | concentration limit per city |
| contract cap / bracket | capacity-tuned | the ladder erodes the edge with size |

## Slippage is part of selection

Compute the entry price by **walking the real NO/YES ladder** to your size, not the displayed best price. If the depth-weighted entry pushes `net_edge` below θ — or slippage exceeds `MAX_SLIPPAGE_FRACTION_OF_EDGE` of the edge — skip the trade. Phantom penny levels must be excluded from the ladder first (see `backtesting-methodology.md`).

## Maker vs taker

- **Taker** pays the full fee and the spread → the structural loser (~−20% pre-fee in aggregate).
- **Maker** rests a bid (0 fee + rebate) and captures spread + the longshot premium → where the edge lives. The trade-off is **fill uncertainty**: a resting bid on a thin tail may not fill. Measure realized maker fill-rate from the trade tape before trusting maker-side backtest ROI.
