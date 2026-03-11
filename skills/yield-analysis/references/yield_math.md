# Yield Math — Formulas & Worked Examples

## Fee APR Calculation

### Constant-Product Pools (x × y = k)

All LPs share fees proportionally to their liquidity share:

```
fee_apr = fee_rate × daily_volume / tvl × 365
```

**Worked Example:**
- Pool: SOL-USDC on Raydium
- Fee rate: 0.25% (0.0025)
- Daily volume: $3,000,000
- TVL: $12,000,000

```
daily_fees = 3,000,000 × 0.0025 = $7,500
fee_apr = 7,500 / 12,000,000 × 365 = 22.81%
```

Your share with $10,000 deposited:
```
your_share = 10,000 / 12,000,000 = 0.000833
your_daily_fees = 7,500 × 0.000833 = $6.25
your_annual_fees = 6.25 × 365 = $2,281
```

### Concentrated Liquidity (CLMM) Pools

Fee income depends on your range width relative to active trading range:

```
concentration_factor = full_range_liquidity / your_range_width
effective_fee_apr = base_fee_apr × concentration_factor
```

**Worked Example:**
- Base fee APR (full range): 20%
- Your range: ±10% around current price
- Full range equivalent: ±100% (roughly)
- Concentration factor: ~5x (simplified)

```
effective_fee_apr = 20% × 5 = 100%
```

But you only earn when price is in your range. If price stays in range 60% of the time:
```
realized_fee_apr = 100% × 0.60 = 60%
```

Minus rebalancing costs each time you go out of range (gas + potential slippage).

### Volume-Weighted Fee APR

When volume varies significantly day to day, use a trailing average:

```python
trailing_7d_volume = sum(daily_volumes[-7:]) / 7
fee_apr = fee_rate * trailing_7d_volume / current_tvl * 365
```

Using 7-day trailing average smooths out spikes from single large trades.

## APR vs APY Conversion

### Definitions

- **APR** (Annual Percentage Rate): Simple interest, no compounding
- **APY** (Annual Percentage Yield): Includes compounding effect

### Formulas

```
APY = (1 + APR / n)^n - 1
APR = n × ((1 + APY)^(1/n) - 1)
```

Where `n` = number of compounding periods per year.

| Compounding | n | 20% APR → APY |
|------------|---|---------------|
| Annual | 1 | 20.00% |
| Monthly | 12 | 21.94% |
| Weekly | 52 | 22.09% |
| Daily | 365 | 22.13% |
| Continuous | ∞ | 22.14% |

### Continuous Compounding

```
APY = e^APR - 1
APR = ln(1 + APY)
```

### When to Use Which

- **Manual LP** (you claim and reinvest): Use APR — you compound when you choose
- **Auto-compounding vault** (Kamino, Tulip): Use APY — vault compounds for you
- **Lending protocols**: Usually display APY with continuous compounding
- **Staking**: Usually display APR

### Daily Rate

```
daily_rate = APR / 365                     # Simple
daily_rate = (1 + APY)^(1/365) - 1        # Compound-adjusted
```

## Net Yield Calculation

### Full Formula

```
net_daily = fee_income + emission_income - il_cost - gas_cost - rebalance_cost
net_apr = (net_daily × 365) / position_value
```

### Step-by-Step Example

**Pool:** SOL-USDC, $50,000 position

| Component | Daily | Annual | Source |
|-----------|-------|--------|--------|
| Fee income | $20.55 | $7,500 | 15% APR |
| Emission income | $13.70 | $5,000 | 10% APR (RAY) |
| Emission adj. (-30%) | $9.59 | $3,500 | RAY declining |
| IL cost | -$8.22 | -$3,000 | ~6% annual IL |
| Gas costs | -$0.14 | -$50 | Solana tx fees |
| Rebalancing | -$0.27 | -$100 | CLMM adjustments |

```
net_daily = 20.55 + 9.59 - 8.22 - 0.14 - 0.27 = $21.51
net_apr = 21.51 × 365 / 50,000 = 15.70%
```

Compare to nominal displayed APY of 25% — real yield is 15.70%.

## Emission Token Yield

### Basic Calculation

```
daily_emission_usd = daily_tokens_emitted × token_price
emission_apr = (daily_emission_usd × 365) / tvl
```

### Adjusted for Depreciation

Emission tokens face constant sell pressure from farmers. Adjust expected yield:

```
retention_factor = current_price / price_30d_ago
effective_emission_apr = emission_apr × retention_factor
```

**Example:**
- RAY emissions: 1,000 RAY/day to pool
- RAY price today: $2.00 (was $3.00 thirty days ago)
- Pool TVL: $5,000,000

```
daily_emission_usd = 1,000 × 2.00 = $2,000
emission_apr = 2,000 × 365 / 5,000,000 = 14.6%
retention_factor = 2.00 / 3.00 = 0.667
effective_emission_apr = 14.6% × 0.667 = 9.74%
```

### Forward-Looking Emission Adjustment

For more conservative estimates, project further depreciation:

```python
# If token dropped 33% last 30d, project another 33% next 30d
pessimistic_price = current_price * retention_factor
pessimistic_emission_apr = emission_apr * (retention_factor ** 2)
```

## Break-Even Analysis

### Time to Break Even

Given upfront costs (gas to enter, potential IL on entry):

```
entry_cost = deposit_gas + initial_slippage
daily_net_income = daily_fees + daily_emissions_adj - daily_il
break_even_days = entry_cost / daily_net_income
```

### Minimum Fee APR for IL Break-Even

Given expected IL (from the `impermanent-loss` skill):

```
min_fee_apr = expected_il_annual + gas_cost_annual + opportunity_cost
```

**Example:** If expected annual IL is 8%, gas costs 0.5%, and SOL staking yields 7%:
```
min_fee_apr = 8% + 0.5% + 7% = 15.5%
```

The pool must generate at least 15.5% fee APR to justify LP over staking.

### Hold Duration Impact

IL accumulates over time if price keeps trending. Shorter hold periods can be better for volatile pairs:

```python
def optimal_hold_days(fee_apr: float, volatility: float) -> int:
    """Estimate optimal holding period before IL exceeds fees.

    Args:
        fee_apr: Annual fee rate as decimal (e.g. 0.20 for 20%).
        volatility: Annual volatility as decimal (e.g. 0.80 for 80%).

    Returns:
        Approximate optimal hold period in days.
    """
    daily_fee = fee_apr / 365
    # IL grows roughly with sqrt(time) × volatility^2
    # Break-even when cumulative_fees = cumulative_il
    # Simplified: days ≈ (2 × daily_fee / (vol^2 / 365))
    daily_vol_sq = (volatility ** 2) / 365
    if daily_vol_sq == 0:
        return 365
    return int(2 * daily_fee / daily_vol_sq)
```

## Common Pitfalls

1. **Comparing APR to APY**: Always convert to the same basis before comparing
2. **Ignoring IL on volatile pairs**: Fee APR looks great until you account for IL
3. **Assuming emission APR is stable**: Token price changes daily; recalculate regularly
4. **Using spot volume for fee APR**: Use 7-day trailing average, not single-day volume
5. **Forgetting gas on Solana**: Low but not zero — matters for small positions and frequent compounds
6. **Double-counting auto-compound yield**: If vault auto-compounds, don't manually compound APR → APY
