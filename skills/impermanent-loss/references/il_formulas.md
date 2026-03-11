# Impermanent Loss — Formula Derivations

## Constant-Product AMM (x * y = k)

### Setup

A liquidity provider deposits tokens X and Y into a pool at price P₀ (price of X in terms of Y).

Initial reserves:
- x₀ = amount of token X
- y₀ = amount of token Y
- Invariant: x₀ * y₀ = k
- Price: P₀ = y₀ / x₀
- Initial portfolio value (in Y terms): V₀ = x₀ * P₀ + y₀ = 2 * y₀

### Step 1: Express Reserves in Terms of k and P

From x * y = k and P = y / x:

```
x = sqrt(k / P)
y = sqrt(k * P)
```

Verify: x * y = sqrt(k/P) * sqrt(k*P) = sqrt(k²) = k ✓
Verify: y / x = sqrt(k*P) / sqrt(k/P) = sqrt(P²) = P ✓

### Step 2: Price Changes to P₁ = r * P₀

New reserves after arbitrageurs rebalance the pool:

```
x₁ = sqrt(k / P₁) = sqrt(k / (r * P₀))
y₁ = sqrt(k * P₁) = sqrt(k * r * P₀)
```

### Step 3: Compute LP Value

LP value at new price (in Y terms):

```
V_lp = x₁ * P₁ + y₁
     = sqrt(k / P₁) * P₁ + sqrt(k * P₁)
     = sqrt(k * P₁) + sqrt(k * P₁)
     = 2 * sqrt(k * P₁)
     = 2 * sqrt(k * r * P₀)
```

### Step 4: Compute Hold Value

If the LP had just held x₀ and y₀:

```
V_hold = x₀ * P₁ + y₀
       = sqrt(k / P₀) * r * P₀ + sqrt(k * P₀)
       = r * sqrt(k * P₀) + sqrt(k * P₀)
       = (1 + r) * sqrt(k * P₀)
```

### Step 5: Derive IL

```
IL = V_lp / V_hold - 1
   = [2 * sqrt(k * r * P₀)] / [(1 + r) * sqrt(k * P₀)] - 1
   = 2 * sqrt(r) / (1 + r) - 1
```

**Final formula:**

```
IL(r) = 2 * sqrt(r) / (1 + r) - 1
```

Where r = P₁ / P₀ (price ratio, always positive).

### Properties

- IL(1) = 0: No IL when price unchanged
- IL(r) = IL(1/r): Symmetric — 2x up and 2x down give the same IL
- IL(r) ≤ 0 for all r: IL is always a loss
- IL(r) → -1 as r → ∞ or r → 0: Maximum IL approaches 100%
- IL is convex: the loss accelerates as r deviates further from 1

## Complete IL Table

| r (P₁/P₀) | Price Change | IL        |
|-----------|-------------|-----------|
| 0.10      | -90%        | -42.54%   |
| 0.20      | -80%        | -25.46%   |
| 0.25      | -75%        | -20.00%   |
| 0.33      | -67%        | -13.40%   |
| 0.50      | -50%        | -5.72%    |
| 0.67      | -33%        | -1.85%    |
| 0.75      | -25%        | -0.60%    |
| 0.80      | -20%        | -0.27%    |
| 0.90      | -10%        | -0.03%    |
| 0.95      | -5%         | -0.01%    |
| 1.00      | 0%          | 0.00%     |
| 1.05      | +5%         | -0.01%    |
| 1.10      | +10%        | -0.02%    |
| 1.20      | +20%        | -0.08%    |
| 1.25      | +25%        | -0.12%    |
| 1.50      | +50%        | -0.46%    |
| 1.75      | +75%        | -1.03%    |
| 2.00      | +100%       | -5.72%    |
| 3.00      | +200%       | -13.40%   |
| 5.00      | +400%       | -25.46%   |
| 10.00     | +900%       | -42.54%   |
| 20.00     | +1900%      | -57.17%   |
| 50.00     | +4900%      | -72.46%   |
| 100.00    | +9900%      | -81.91%   |

## Concentrated Liquidity (CLMM) IL

### Setup

LP provides liquidity in range [P_l, P_u] where P_l < P₀ < P_u.

### Concentration Factor

The virtual liquidity multiplier for a concentrated position:

```
c = 1 / (1 - sqrt(P_l / P_u))
```

Examples:
- ±5% range: c ≈ 20.5x
- ±10% range: c ≈ 10.5x
- ±20% range: c ≈ 5.4x
- ±50% range: c ≈ 2.4x
- Full range: c = 1x (same as constant-product)

### CLMM IL When Price Stays in Range

For price P₁ within [P_l, P_u], the IL relative to holding is amplified:

```
IL_clmm ≈ IL_constant_product(r) * c
```

This is an approximation that works well for small-to-moderate moves. The exact formula uses the virtual reserves framework from Uniswap v3.

### Exact CLMM Value Formula

For current price P within range [P_l, P_u], the value of L units of liquidity:

```
V_lp(P) = L * (sqrt(P) - sqrt(P_l) + P * (1/sqrt(P) - 1/sqrt(P_u)))
         = L * (2 * sqrt(P) - sqrt(P_l) - P / sqrt(P_u))
```

The hold value (proportional to initial deposit at price P₀):

```
V_hold(P) = L * (sqrt(P₀) - sqrt(P_l)) * P / P₀
          + L * (1/sqrt(P₀) - 1/sqrt(P_u)) * 1
```

(Simplified for the case where initial deposit is at P₀.)

### Price Exits Range

**Price drops below P_l:**
- Position becomes 100% token X (the depreciating one)
- Value: L * (1/sqrt(P_l) - 1/sqrt(P_u)) * P (entirely in X, valued at current P)
- IL is at maximum for downward moves

**Price rises above P_u:**
- Position becomes 100% token Y (the relatively depreciating one)
- Value: L * (sqrt(P_u) - sqrt(P_l)) (entirely in Y)
- IL is at maximum for upward moves — you sold all your X into Y too early

## Multi-Asset Pool IL

For pools with N assets with equal weights (like Balancer uniform pools):

```
IL_N(r₁, r₂, ..., rₙ) = (∏ rᵢ^(1/N)) / (Σ rᵢ / N) - 1
```

Where rᵢ = P_new_i / P_initial_i for each token.

For a 2-token pool, this simplifies to the standard formula:

```
IL_2(r) = sqrt(r) / ((1 + r) / 2) - 1 = 2*sqrt(r) / (1+r) - 1
```

For a 3-token equal-weight pool with one token moving by r and others stable:

```
IL_3(r) = (r^(1/3)) / ((1 + 1 + r) / 3) - 1 = 3 * r^(1/3) / (2 + r) - 1
```

Multi-asset pools have **less IL** than 2-token pools for the same price move, because the moving token is a smaller fraction of the portfolio.

## IL in SOL Terms vs USD Terms

For Solana-native traders who measure portfolio value in SOL:

If you LP a SOL/USDC pool and SOL goes up:
- **USD-denominated IL**: You have less USD value than holding.
- **SOL-denominated IL**: You have fewer SOL than holding, because the AMM sold SOL for USDC.

The formula is identical — only the numeraire changes. If you think in SOL, your "hold" position is measured in SOL, and the IL percentage is the same.

**Key consideration**: If your goal is to accumulate SOL, LPing SOL/USDC during SOL uptrends means the AMM sells your SOL. You accumulate less SOL than holding. The fees earned (in both SOL and USDC) need to compensate.

## Small-Move IL Approximation

For small price changes (|r - 1| << 1), using Taylor expansion around r = 1:

```
IL ≈ -(r - 1)² / 8 = -δ² / 8
```

Where δ = r - 1 is the fractional price change. This shows IL grows quadratically with price deviation, which is why small daily moves accumulate IL slowly but large moves are devastating.

Equivalently, for log returns σ over a period:

```
E[IL] ≈ -σ² / 8
```

This is the key formula for breakeven analysis.
