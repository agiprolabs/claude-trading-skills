---
name: impermanent-loss
description: Impermanent loss calculation, modeling, and breakeven analysis for AMM liquidity provision across pool types
---

# Impermanent Loss — Calculation, Modeling & Breakeven Analysis

Impermanent loss (IL) is the cost of providing liquidity to an automated market maker (AMM) relative to simply holding the tokens. When you deposit tokens into a liquidity pool, the AMM continuously rebalances your position as prices move. This rebalancing always works against you — selling winners and buying losers — resulting in less value than if you had just held the original tokens.

## Why "Impermanent"?

IL is called "impermanent" because it only crystallizes when you withdraw. If prices return to their original ratio, IL reverts to zero. However, in practice, prices rarely return exactly, so IL is usually quite real.

## Key Insight

IL is a function of the **price ratio change**, not the absolute price. A token moving from $1 to $2 produces the same IL as a token moving from $100 to $200 — both are a 2x ratio change. Direction does not matter either: a 2x increase and a 0.5x decrease produce the same IL magnitude.

## Constant-Product IL Formula

For a standard `x * y = k` AMM (Raydium standard, Orca legacy):

```
IL = 2 * sqrt(r) / (1 + r) - 1
```

Where `r = P_new / P_initial` (the price ratio).

### IL at Key Price Ratios

| Price Change | Ratio (r) | IL       |
|-------------|-----------|----------|
| -75%        | 0.25      | -5.72%   |
| -50%        | 0.50      | -5.72%   |
| -25%        | 0.75      | -0.60%   |
| 0%          | 1.00      | 0.00%    |
| +25%        | 1.25      | -0.60%   |
| +50%        | 1.50      | -2.02%   |
| +100% (2x)  | 2.00      | -5.72%   |
| +200% (3x)  | 3.00      | -13.40%  |
| +400% (5x)  | 5.00      | -25.46%  |
| +900% (10x) | 10.00     | -42.54%  |

Note the symmetry: a 2x increase (r=2.0) and a 2x decrease (r=0.5) both produce -5.72% IL.

## Concentrated Liquidity (CLMM) Amplified IL

Concentrated liquidity market makers (Orca Whirlpools, Raydium CLMM, Meteora DLMM) allow LPs to concentrate liquidity within a price range `[P_lower, P_upper]`. This amplifies both fee income **and** IL.

### Concentration Factor

```
concentration_factor = 1 / (1 - sqrt(P_lower / P_upper))
```

For a ±10% range around current price: concentration_factor ≈ 10x.

### CLMM IL Behavior

- **Price within range**: IL is amplified by the concentration factor relative to constant-product IL.
- **Price exits range**: The position becomes 100% of the losing asset. This is the **maximum possible IL** for that direction — you hold only the depreciating token.

```
IL_clmm ≈ IL_constant_product * concentration_factor
```

This approximation holds for small moves. For large moves or prices near range boundaries, use the full CLMM formula (see `references/il_formulas.md`).

### Example: CLMM vs Constant-Product

SOL at $150, LP with ±20% range ($120–$180):

| Scenario       | Constant-Product IL | CLMM IL (±20%) |
|---------------|--------------------:|----------------:|
| SOL → $180    | -0.62%             | ~-3.1%          |
| SOL → $200    | -1.03%             | 100% SOL (exit) |
| SOL → $120    | -1.80%             | ~-9.0%          |
| SOL → $100    | -3.42%             | 100% USDC (exit)|

## IL vs Fees: Breakeven Analysis

The core question for any LP is: **Do fees earned exceed IL incurred?**

```
Net Position = LP_value + accrued_fees - hold_value
```

Profitable when `accrued_fees > IL`.

### Breakeven Fee Rate

For constant-product pools, the expected IL per period is approximately:

```
expected_IL ≈ σ² / 8
```

Where σ is the standard deviation of log returns for that period. This means:

| Daily Volatility (σ) | Expected Daily IL | Min Daily Fee Rate to Break Even |
|----------------------|------------------:|--------------------------------:|
| 1%                   | 0.001%            | 0.001%                          |
| 3%                   | 0.011%            | 0.011%                          |
| 5%                   | 0.031%            | 0.031%                          |
| 10%                  | 0.125%            | 0.125%                          |
| 20%                  | 0.500%            | 0.500%                          |

Daily fee income for an LP:

```
daily_fee_income = (deposit / TVL) * daily_volume * fee_rate
```

For a full breakeven framework, see `references/breakeven_analysis.md`.

## Modeling IL Over Time

### Monte Carlo Simulation

Simulate many random price paths using geometric Brownian motion (GBM):

```python
import numpy as np

def simulate_price_path(
    initial_price: float,
    daily_vol: float,
    days: int,
    drift: float = 0.0,
) -> np.ndarray:
    """Simulate a price path using geometric Brownian motion."""
    dt = 1.0  # daily steps
    log_returns = np.random.normal(
        (drift - 0.5 * daily_vol**2) * dt,
        daily_vol * np.sqrt(dt),
        days,
    )
    prices = initial_price * np.exp(np.cumsum(log_returns))
    return np.insert(prices, 0, initial_price)
```

For each path, compute the IL at each timestep and the cumulative fees earned. After N simulations, analyze the distribution of outcomes.

See `scripts/il_scenario_modeler.py` for a complete Monte Carlo simulation.

### Historical Analysis

Use actual OHLCV price data to compute what IL would have been for a historical period. This gives a more realistic (but backward-looking) estimate.

## IL Mitigation Strategies

### 1. Stablecoin Pairs
Pairs like USDC/USDT have near-zero IL because the price ratio barely moves. Fee income is almost pure profit.

### 2. Correlated Pairs
Pairs like SOL/mSOL or ETH/stETH move together, so the price ratio stays close to 1.0. IL is minimal.

### 3. Wider CLMM Ranges
A wider range reduces concentration factor, reducing IL at the cost of less fee income per unit of capital.

### 4. Active Range Management
Monitor price and rebalance your CLMM range when price approaches boundaries. This reduces the risk of price exiting your range entirely.

### 5. Fee Tier Selection
Higher fee tiers (e.g., 1% vs 0.3%) compensate for higher IL in volatile pairs. Match fee tier to expected volatility.

## When IL Is Acceptable

- **High volume pools**: Fee income significantly exceeds expected IL.
- **Stable or correlated pairs**: IL is structurally minimal.
- **Token accumulation strategy**: You want to accumulate the cheaper token anyway.
- **Short time horizons with active management**: Fees compound, and you rebalance before large moves.

## When to Avoid LPing

- **Low volume, high volatility**: IL dominates, fees are insufficient.
- **Trending markets**: Strong directional moves create large, sustained IL.
- **Illiquid new tokens**: Price can move 10x+ in hours, causing catastrophic IL.
- **Wide-spread pools**: Low volume means fees don't compensate for any IL at all.

## Related Skills

- **lp-math**: AMM mechanics and reserve calculations that underpin IL formulas.
- **yield-analysis**: Compare LP yields net of IL against other DeFi opportunities.
- **liquidity-analysis**: Assess pool depth and volume to estimate fee income.
- **volatility-modeling**: Forecast volatility inputs for IL modeling.

## Files

### References
- `references/il_formulas.md` — Full IL derivations for constant-product, CLMM, and multi-asset pools
- `references/breakeven_analysis.md` — Fee vs IL breakeven framework with practical tools

### Scripts
- `scripts/il_calculator.py` — Calculate IL for any price change across pool types, with tables and comparisons
- `scripts/il_scenario_modeler.py` — Monte Carlo simulation of LP positions over time with fee and IL modeling
