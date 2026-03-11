---
name: lp-math
description: AMM liquidity provision mathematics including constant-product, concentrated liquidity, price impact, and LP share calculations
---

# LP Math — AMM Liquidity Provision Mathematics

Automated Market Makers (AMMs) replace traditional orderbooks with liquidity pools. Instead of matching buyers and sellers, a mathematical formula determines prices based on reserve ratios. Liquidity providers (LPs) deposit both assets into a pool and earn fees from every trade.

Understanding the math behind AMMs is essential for:
- Evaluating whether providing liquidity is profitable after impermanent loss
- Estimating price impact before executing large trades
- Comparing capital efficiency across pool types (constant product vs concentrated)
- Calculating expected fee revenue for a given pool position

**Related skills**: See `impermanent-loss` for IL calculations, `yield-analysis` for LP yield modeling, `liquidity-analysis` for pool depth assessment.

---

## 1. Constant Product AMM (xy = k)

The foundational AMM model used by Raydium V4 and most Solana DEXes.

### Core Invariant

```
x * y = k
```

Where:
- `x` = reserve amount of token X (e.g., SOL)
- `y` = reserve amount of token Y (e.g., USDC)
- `k` = constant product (increases over time from fees)

### Spot Price

```
P = x / y    (price of Y in terms of X)
P = y / x    (price of X in terms of Y)
```

For a pool with 100 SOL and 10,000 USDC: price of SOL = 10,000 / 100 = 100 USDC.

### Trade Execution

When a trader swaps Δx of token X into the pool:

```python
# Output amount (before fees)
delta_y = y * delta_x / (x + delta_x)

# With fee (e.g., 0.3%)
delta_y_after_fee = delta_y * (1 - fee_rate)

# New reserves
x_new = x + delta_x
y_new = y - delta_y_after_fee
```

The key insight: larger trades get worse prices because each unit moves the ratio further.

### Inverse Calculation

To get a specific output amount Δy, the required input is:

```python
delta_x = x * delta_y / (y - delta_y)
```

### Price After Trade

```python
price_new = y_new / x_new
```

### Worked Example

Pool: 100 SOL / 10,000 USDC (k = 1,000,000), fee = 0.3%

Buy 5 SOL worth of USDC:
1. Gross output: `10,000 * 5 / (100 + 5) = 476.19 USDC`
2. Fee: `476.19 * 0.003 = 1.43 USDC`
3. Net output: `474.76 USDC`
4. Effective price: `474.76 / 5 = 94.95 USDC/SOL` (vs spot 100)
5. Price impact: `(100 - 94.95) / 100 = 5.05%`
6. New reserves: 105 SOL / 9,525.24 USDC
7. New k: `105 * 9,525.24 = 1,000,150.2` (k increased from fees)

See `references/amm_formulas.md` for complete derivations.

---

## 2. Concentrated Liquidity (CLMM)

Used by Orca Whirlpool, Raydium CLMM, and Meteora DLMM. Liquidity is only active within a chosen price range [P_lower, P_upper].

### Key Concepts

```
L = sqrt(x * y)           # Liquidity within the active range
price_at_tick = 1.0001^tick  # Tick-to-price conversion
```

### Capital Efficiency

Concentrating liquidity in a narrow range provides more depth per dollar:

```python
# Capital efficiency ratio
efficiency = sqrt(P_upper / P_lower) / (sqrt(P_upper / P_lower) - 1)

# Example: ±5% range around $100 SOL
P_lower, P_upper = 95, 105
efficiency = sqrt(105/95) / (sqrt(105/95) - 1)  # ≈ 20.5x
```

A ±5% range is ~20x more capital-efficient than full-range, but the position goes 100% into one asset if price moves outside the range.

### Position Value

For a CLMM position with liquidity L in range [P_lower, P_upper] at current price P:

```python
if P <= P_lower:
    # All in token X (below range)
    value_x = L * (1/sqrt(P_lower) - 1/sqrt(P_upper))
    value_y = 0
elif P >= P_upper:
    # All in token Y (above range)
    value_x = 0
    value_y = L * (sqrt(P_upper) - sqrt(P_lower))
else:
    # In range — holds both tokens
    value_x = L * (1/sqrt(P) - 1/sqrt(P_upper))
    value_y = L * (sqrt(P) - sqrt(P_lower))
```

### Range Strategy Comparison

| Range | Efficiency | IL Risk | Fee Capture | Best For |
|-------|-----------|---------|-------------|----------|
| ±2% | ~50x | Very high | High if in range | Stablecoins, tight pegs |
| ±5% | ~20x | High | Good for trending | Active management |
| ±25% | ~4x | Moderate | Consistent | Semi-passive |
| ±100% | ~2x | Low | Lower per $ | Passive, volatile pairs |
| Full range | 1x | Baseline | Always earning | Set and forget |

See `references/amm_formulas.md` for full CLMM derivations.

---

## 3. Price Impact

### Constant Product Impact

```python
# Price impact as a fraction
price_impact = delta_x / (x + delta_x)

# As percentage of pool
pool_fraction = trade_value / pool_tvl

# Rule of thumb: impact ≈ 2 * pool_fraction for constant product
```

### Multi-Hop Impact

For a route through multiple pools, compound the impacts:

```python
def multi_hop_impact(hops: list[dict]) -> float:
    """Calculate total price impact across route legs.

    Args:
        hops: List of {reserve_in, trade_amount} for each leg.

    Returns:
        Total price impact as a fraction.
    """
    remaining = 1.0
    for hop in hops:
        leg_impact = hop["trade_amount"] / (hop["reserve_in"] + hop["trade_amount"])
        remaining *= (1 - leg_impact)
    return 1 - remaining
```

### Impact Thresholds

| Impact | Assessment | Action |
|--------|-----------|--------|
| < 0.1% | Negligible | Proceed normally |
| 0.1–0.5% | Low | Acceptable for most trades |
| 0.5–2% | Moderate | Consider splitting across pools |
| 2–5% | High | Split trade, use TWAP |
| > 5% | Severe | Reduce size or find deeper pools |

---

## 4. LP Share Calculations

### Initial Deposit (Empty Pool)

```python
shares = sqrt(x_deposited * y_deposited)
```

The first depositor sets the ratio and receives shares equal to the geometric mean.

### Subsequent Deposits

```python
shares_minted = min(
    x_added / x_reserve,
    y_added / y_reserve
) * total_shares
```

Deposits must be proportional to the current reserve ratio. Any excess of one token is not used (or returned, depending on implementation).

### Withdrawal

```python
x_out = (shares_burned / total_shares) * x_reserve
y_out = (shares_burned / total_shares) * y_reserve
```

You always receive both tokens in the current ratio.

### Share Value

```python
share_value = pool_tvl / total_shares
your_value = your_shares * share_value
```

---

## 5. Fee Accrual

Fees accumulate inside the pool, increasing k:

```python
# Before trade: k = x * y
# After trade with fee:
# k_new = (x + delta_x) * (y - delta_y_net) > k
# The difference is the fee retained in the pool

# Fee APR estimation
daily_volume = 500_000  # USD
fee_rate = 0.003        # 0.3%
daily_fees = daily_volume * fee_rate  # $1,500
tvl = 2_000_000         # $2M pool
fee_apr = (daily_fees * 365) / tvl    # 27.4%
```

For CLMM positions, fee earnings depend on:
- Whether price stays within your range (out-of-range = no fees)
- Your share of active liquidity in that range
- Total volume routed through the pool

```python
# CLMM fee estimation
your_liquidity = 50_000     # Your L
total_liquidity = 1_000_000  # Total L in your tick range
your_share = your_liquidity / total_liquidity  # 5%
your_daily_fees = daily_fees * your_share  # $75
```

---

## 6. Solana Pool Types

### Raydium V4 (Constant Product)

- Model: Standard xy = k
- Fee: 0.25% (0.22% to LP, 0.03% to RAY buyback)
- Best for: New token launches, volatile pairs
- Note: Integrated with OpenBook for limit order flow

### Orca Whirlpool (Concentrated Liquidity)

- Model: Concentrated liquidity with tick spacing
- Fee tiers: 0.01%, 0.05%, 0.3%, 1%
- Position: Represented as NFT (each position is unique)
- Best for: Major pairs (SOL/USDC), stablecoin pairs

### Raydium CLMM

- Model: Concentrated liquidity (similar to Uniswap V3)
- Tick spacing: 1, 10, 60, 200
- Fee tiers: 0.01%, 0.05%, 0.25%, 1%
- Best for: Pairs with predictable ranges

### Meteora DLMM (Dynamic Liquidity Market Maker)

- Model: Discrete bins instead of continuous ticks
- Strategies: Spot (uniform), Curve (concentrated), Bid-Ask (around current price)
- Fees: Dynamic, adjusting based on volatility
- Best for: Active LPs who rebalance frequently

See `references/pool_mechanics.md` for detailed mechanics and comparison.

---

## 7. Practical Decision Framework

### Should You LP?

```
1. Calculate expected fee APR
2. Estimate impermanent loss for expected price movement
3. Net return = fee APR - IL
4. Compare to simply holding the assets
```

### Which Pool Type?

```
Stablecoin pair     → CLMM with tight range (±0.5%)
Major pair (SOL/USDC) → CLMM with moderate range (±10-25%)
New/volatile token  → Constant product (full range)
Active management   → Meteora DLMM with dynamic rebalancing
```

### Position Sizing for LP

```python
# Never LP more than you can afford to lose to IL
max_lp_allocation = portfolio_value * 0.20  # 20% max in any single pool

# For volatile pairs, reduce further
volatility_adjustment = 1 - (annualized_vol / 2)  # Scale down for vol
adjusted_allocation = max_lp_allocation * max(0.1, volatility_adjustment)
```

---

## Files

### References
- `references/amm_formulas.md` — Complete mathematical derivations for constant product and concentrated liquidity AMMs
- `references/pool_mechanics.md` — Solana-specific pool mechanics for Raydium, Orca, and Meteora

### Scripts
- `scripts/amm_calculator.py` — Constant product AMM calculator with trade simulation, LP shares, and fee accrual
- `scripts/clmm_calculator.py` — Concentrated liquidity calculator with position valuation, capital efficiency, and range comparison

---

## Quick Reference

| Formula | Expression |
|---------|-----------|
| Constant product | `x * y = k` |
| Spot price | `P = y / x` |
| Trade output | `Δy = y * Δx / (x + Δx)` |
| Required input | `Δx = x * Δy / (y - Δy)` |
| Price impact | `Δx / (x + Δx)` |
| Initial LP shares | `sqrt(x * y)` |
| Subsequent shares | `min(Δx/x, Δy/y) * total` |
| Fee APR | `(daily_fees * 365) / TVL` |
| CLMM efficiency | `sqrt(P_u/P_l) / (sqrt(P_u/P_l) - 1)` |
| Tick to price | `1.0001^tick` |
