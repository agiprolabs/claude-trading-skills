# Position Sizing — Formulas Reference

Complete mathematical derivations for all sizing methods with worked examples.

---

## Fixed Fractional Sizing

### Derivation

The goal: lose at most `R%` of account value if the stop loss is hit.

```
risk_amount = account_value × risk_percentage
price_risk_per_unit = |entry_price - stop_loss_price|
position_size_units = risk_amount / price_risk_per_unit
position_value = position_size_units × entry_price
leverage_ratio = position_value / account_value
```

### Worked Example

| Parameter | Value |
|-----------|-------|
| Account value | $10,000 |
| Risk per trade | 2% |
| Entry price | $1.50 |
| Stop loss | $1.30 |

```
risk_amount = $10,000 × 0.02 = $200
price_risk  = $1.50 - $1.30 = $0.20
units        = $200 / $0.20 = 1,000 tokens
position_value = 1,000 × $1.50 = $1,500 (15% of account)
```

If the stop is hit: loss = 1,000 × $0.20 = $200 = 2% of account.

### Fee-Adjusted Version

In practice, include fees and slippage in the risk:

```
effective_risk = price_risk + (entry_price × fee_rate × 2) + estimated_slippage
position_size = risk_amount / effective_risk
```

Example with 0.3% fees each way and 0.5% slippage:

```
fee_cost = $1.50 × 0.003 × 2 = $0.009
slippage = $1.50 × 0.005 = $0.0075
effective_risk = $0.20 + $0.009 + $0.0075 = $0.2165
units = $200 / $0.2165 = 924 tokens (vs 1,000 without fees)
```

---

## Volatility-Adjusted Sizing

### Derivation

Normalize position sizes so each position contributes roughly the same dollar volatility to the portfolio.

```
target_daily_pnl_vol = account_value × target_vol_pct
token_daily_vol = price × daily_return_std
position_size_units = target_daily_pnl_vol / token_daily_vol
```

### Using ATR (Average True Range)

ATR is a smoothed measure of daily price range:

```
daily_vol_pct = ATR(14) / close_price
position_units = (account × target_vol_pct) / ATR(14)
```

### Worked Example

| Parameter | Value |
|-----------|-------|
| Account | $10,000 |
| Target daily vol | 2% of account ($200) |
| Token price | $1.50 |
| ATR(14) | $0.12 |

```
daily_vol_pct = $0.12 / $1.50 = 8%
position_units = $200 / $0.12 = 1,667 tokens
position_value = 1,667 × $1.50 = $2,500
expected_daily_pnl_range = 1,667 × $0.12 = $200 (2% of account)
```

### Comparing Across Assets

This method lets you hold equal-risk positions across assets with very different volatilities:

| Token | Price | ATR(14) | Vol % | Units | Value |
|-------|-------|---------|-------|-------|-------|
| SOL | $150 | $6.00 | 4% | 33 | $4,950 |
| BONK | $0.00002 | $0.0000016 | 8% | 125M | $2,500 |
| JUP | $0.80 | $0.064 | 8% | 3,125 | $2,500 |

Each contributes ~$200 daily PnL volatility despite different position sizes.

---

## Kelly Criterion

### Full Derivation

The Kelly criterion maximizes the expected logarithm of wealth (geometric growth rate).

Given a binary bet with:
- Probability `p` of winning `b` units per unit risked
- Probability `q = 1 - p` of losing 1 unit per unit risked

Maximize: `E[ln(W)] = p × ln(1 + f×b) + q × ln(1 - f)`

Taking the derivative and setting to zero:

```
dE/df = p×b/(1+f×b) - q/(1-f) = 0
p×b×(1-f) = q×(1+f×b)
p×b - p×b×f = q + q×f×b
p×b - q = f×b×(p + q) = f×b
f* = (p×b - q) / b
```

Equivalent forms:
```
f* = (p×b - q) / b
f* = p - q/b
f* = (p×(b+1) - 1) / b
```

### Fractional Kelly

Full Kelly maximizes growth but produces large drawdowns. The variance of returns under Kelly is:

```
Var = p×q×(b+1)² × f²
```

Fractional Kelly reduces variance quadratically while reducing growth only linearly:

| Fraction | Growth Rate | Drawdown Risk | Recommended? |
|----------|-------------|---------------|-------------|
| 1.0x | 100% | Very high | No |
| 0.5x | 75% | Moderate | For well-measured edges |
| 0.25x | 44% | Low | Default recommendation |
| 0.1x | 19% | Very low | Ultra-conservative |

Growth rate at fraction `g`: `G(g) = g × (2 - g) × G(1)` approximately.

### Worked Examples

**Example 1: Moderate edge**
```
Win rate = 55%, avg win = 1.5x avg loss
p = 0.55, q = 0.45, b = 1.5
f* = (0.55 × 1.5 - 0.45) / 1.5 = 0.25 / 1.5 = 0.167 (16.7%)
Quarter Kelly: 4.2% risk per trade
Half Kelly: 8.3% risk per trade
```

**Example 2: High win rate, small payoff**
```
Win rate = 70%, avg win = 0.8x avg loss
p = 0.70, q = 0.30, b = 0.8
f* = (0.70 × 0.8 - 0.30) / 0.8 = 0.26 / 0.8 = 0.325 (32.5%)
Quarter Kelly: 8.1%
```

**Example 3: Low win rate, large payoff (trend following)**
```
Win rate = 35%, avg win = 4x avg loss
p = 0.35, q = 0.65, b = 4.0
f* = (0.35 × 4.0 - 0.65) / 4.0 = 0.75 / 4.0 = 0.1875 (18.75%)
Quarter Kelly: 4.7%
```

**Example 4: No edge**
```
Win rate = 45%, avg win = 1.0x avg loss
f* = (0.45 × 1.0 - 0.55) / 1.0 = -0.10
Negative Kelly → NO EDGE → do not trade
```

---

## Liquidity-Constrained Sizing

### Constant-Product AMM Slippage

For a constant-product AMM (x × y = k):

```
price_impact = trade_size / (pool_reserve + trade_size)
```

For small trades relative to pool size:

```
slippage ≈ trade_size / pool_reserve
```

### Maximum Trade Size

Given a maximum acceptable slippage:

```
max_trade = pool_reserve × max_slippage_pct
```

### Worked Example

| Parameter | Value |
|-----------|-------|
| Pool SOL reserve | 500 SOL |
| Pool token reserve | 5,000,000 tokens |
| Token price | 0.0001 SOL |
| Max slippage | 2% |

```
max_trade_sol = 500 × 0.02 = 10 SOL
max_trade_tokens = 5,000,000 × 0.02 = 100,000 tokens
```

### Multi-Pool Aggregation

When a token has liquidity across multiple pools:

```
total_available = sum(pool_reserve_i × max_slippage for each pool_i)
```

However, a DEX aggregator (Jupiter) will split the order optimally. The effective available liquidity is typically 70-90% of the simple sum due to routing overhead.

### Position vs Trade Size

A position may require multiple trades to build:

```
max_single_trade = pool_liquidity × 0.02   # 2% per trade
max_position = pool_liquidity × 0.05       # 5% total (built in chunks)
trades_needed = ceil(desired_position / max_single_trade)
```

---

## Combined Sizing Ladder

Calculate all four methods and take the minimum:

```python
def sizing_ladder(
    account: float,
    risk_pct: float,
    entry: float,
    stop: float,
    atr: float,
    target_vol: float,
    win_rate: float,
    payoff_ratio: float,
    kelly_fraction: float,
    pool_liquidity: float,
    max_slippage: float,
) -> dict:
    # 1. Fixed fractional
    ff_units = (account * risk_pct) / abs(entry - stop)

    # 2. Volatility-adjusted
    vol_units = (account * target_vol) / atr

    # 3. Kelly
    kelly_f = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio
    kelly_risk = max(0, kelly_f * kelly_fraction)
    kelly_units = (account * kelly_risk) / abs(entry - stop)

    # 4. Liquidity-constrained
    liq_value = pool_liquidity * max_slippage
    liq_units = liq_value / entry

    sizes = {
        "fixed_fractional": ff_units,
        "volatility_adjusted": vol_units,
        "kelly": kelly_units,
        "liquidity": liq_units,
    }
    binding = min(sizes, key=sizes.get)
    return {"sizes": sizes, "recommended": sizes[binding], "binding": binding}
```
