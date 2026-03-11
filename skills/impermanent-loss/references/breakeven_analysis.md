# Impermanent Loss — Breakeven Analysis

## Core Framework

An LP position is profitable when cumulative fee income exceeds cumulative IL:

```
Net P&L = Fees_earned - IL_incurred
```

The breakeven point is when `Fees_earned = IL_incurred`.

## Fee Income Model

### Daily Fee Income

For a deposit of size D in a pool with TVL, daily volume V, and fee rate f:

```
daily_fee_income = (D / TVL) * V * f
```

Your share of fees is proportional to your share of the pool's liquidity.

**Example**: $10,000 deposit in a pool with $1M TVL, $500K daily volume, 0.30% fee:

```
daily_fee_income = (10000 / 1000000) * 500000 * 0.003 = $15.00
```

### Fee Rate as Fraction of Deposit

More useful is the fee rate as a percentage of your deposit:

```
daily_fee_rate = (V / TVL) * f
```

This is independent of deposit size. Common values:

| Pool Type        | V/TVL Ratio | Fee Rate | Daily Fee Rate |
|-----------------|-------------|----------|----------------|
| SOL/USDC (high) | 1.0         | 0.25%    | 0.25%          |
| SOL/USDC (avg)  | 0.3         | 0.25%    | 0.075%         |
| Memecoin pair   | 2.0         | 1.00%    | 2.00%          |
| Stablecoin pair | 0.5         | 0.01%    | 0.005%         |
| Long-tail pair  | 0.05        | 0.30%    | 0.015%         |

### CLMM Fee Amplification

For concentrated positions, fee income is amplified by the concentration factor:

```
daily_fee_rate_clmm = daily_fee_rate * concentration_factor
```

A ±10% range with c ≈ 10.5x turns a 0.075% daily fee rate into ~0.79%.

## Expected IL from Volatility

### Daily Expected IL (Constant-Product)

Using the small-move approximation:

```
E[daily_IL] ≈ σ_daily² / 8
```

Where σ_daily is the daily volatility (standard deviation of daily log returns).

### CLMM Expected IL

```
E[daily_IL_clmm] ≈ (σ_daily² / 8) * concentration_factor
```

The concentration factor amplifies IL just as it amplifies fees.

## Breakeven Conditions

### Constant-Product Breakeven

Setting daily fees equal to daily expected IL:

```
(V / TVL) * f ≥ σ² / 8
```

Solving for maximum tolerable volatility:

```
σ_max = sqrt(8 * (V / TVL) * f)
```

Solving for minimum required volume ratio:

```
(V / TVL)_min = σ² / (8 * f)
```

### CLMM Breakeven

For CLMM, the concentration factor cancels out (it amplifies both fees and IL equally):

```
(V / TVL) * f * c ≥ (σ² / 8) * c
```

This simplifies to the same condition as constant-product:

```
(V / TVL) * f ≥ σ² / 8
```

**Key insight**: Concentration does NOT change the breakeven condition. It amplifies both revenue and cost equally. CLMM is beneficial because you need less capital to earn the same fees, but the breakeven volatility is unchanged.

However, this only holds while price stays in range. The risk of price exiting the range (and suffering maximum directional IL) is the additional cost of CLMM.

## Breakeven Table

| Daily Vol (σ) | σ²/8 (Daily IL) | Breakeven V/TVL at 0.25% fee | Breakeven V/TVL at 1% fee |
|--------------|----------------|------------------------------|---------------------------|
| 1%           | 0.0013%        | 0.005                        | 0.001                     |
| 2%           | 0.0050%        | 0.020                        | 0.005                     |
| 3%           | 0.0113%        | 0.045                        | 0.011                     |
| 5%           | 0.0313%        | 0.125                        | 0.031                     |
| 7%           | 0.0613%        | 0.245                        | 0.061                     |
| 10%          | 0.1250%        | 0.500                        | 0.125                     |
| 15%          | 0.2813%        | 1.125                        | 0.281                     |
| 20%          | 0.5000%        | 2.000                        | 0.500                     |

**Reading the table**: For a pair with 5% daily volatility and 0.25% fee rate, you need a V/TVL ratio of at least 0.125 (12.5% of TVL traded daily) to break even.

## Practical Breakeven Tool

### Given Pool Parameters, Should You LP?

**Input**: fee_rate, daily_volume, TVL, daily_volatility

**Steps**:
1. Compute daily fee rate: `dfr = (daily_volume / TVL) * fee_rate`
2. Compute expected daily IL: `eil = daily_volatility² / 8`
3. Compute daily edge: `edge = dfr - eil`
4. If edge > 0: LP is expected to be profitable

**Example**: SOL/USDC pool, fee=0.25%, volume=$2M, TVL=$5M, daily vol=5%

```
dfr = (2000000 / 5000000) * 0.0025 = 0.001 = 0.10%
eil = 0.05² / 8 = 0.000313 = 0.031%
edge = 0.10% - 0.031% = 0.069% daily
```

Expected daily profit: 0.069% of deposit, or ~25% annualized.

## Time Horizon Analysis

### Compounding Dynamics

Over multiple days, fees compound while IL depends on the total price path:

- **Fees**: Roughly linear accumulation (compound effect is small day-to-day)
- **IL**: Depends on the final price ratio, NOT the sum of daily ILs

This means:
- In **range-bound markets**, daily fees accumulate while IL oscillates near zero. LP wins.
- In **trending markets**, IL grows with the trend while fees provide only linear offset. LP loses.

### Probability of Profit Over Time

With positive daily edge (fees > expected IL), the probability of profit generally increases with time — but so does the variance. The distribution of outcomes widens.

For N days with daily edge e and daily variance v:

```
expected_total_edge = N * e
std_of_total = sqrt(N) * std_daily
```

The Sharpe ratio of the LP position improves with sqrt(N), meaning longer horizons favor the LP when edge is positive.

## When LPing Is NOT Profitable

### Red Flags

1. **V/TVL < 0.05 with fee < 0.5%**: Almost never profitable regardless of volatility.
2. **Daily vol > 15% with fee < 1%**: IL overwhelms fees for most volume levels.
3. **Declining volume trend**: Past V/TVL may not reflect future conditions.
4. **New token launches**: Extreme volatility (50%+ daily) makes IL catastrophic.

### Meme Token Analysis

A typical meme token pool:
- Daily vol: 30-100%
- Fee: 1%
- V/TVL: 0.5-5.0

At 30% daily vol: `eil = 0.30² / 8 = 1.125%`
Breakeven V/TVL at 1% fee: `0.30² / (8 * 0.01) = 1.125`

Even with 1% fee, you need the entire TVL to turn over 1.125x daily just to break even. For higher volatility tokens, it gets worse rapidly.

### Directional Risk

The IL formula assumes you have no view on direction. If you expect SOL to go up 50%, the expected IL is -2.0% — but you also forgo the upside that holding would capture. The total opportunity cost is:

```
opportunity_cost = hold_return - LP_return = hold_return - (hold_return + IL + fees)
                 = -IL - fees  (which is positive when |IL| > fees)
```

In strong trends, simply holding outperforms LPing even when fees > IL, because the LP return is always between the two tokens' returns.

## Summary Decision Framework

```
1. Compute daily_fee_rate = (V / TVL) * fee_rate
2. Estimate daily_vol from recent price data
3. Compute expected_daily_IL = daily_vol² / 8
4. edge = daily_fee_rate - expected_daily_IL

If edge > 0.05%/day  → Strong LP candidate
If 0 < edge < 0.05%  → Marginal, consider risks carefully
If edge < 0           → Do not LP (fees insufficient)
```

Always cross-reference with:
- Volume trend (declining volume = declining edge)
- Market regime (trending = IL worse than expected)
- Token fundamentals (rug risk = total loss, not just IL)
