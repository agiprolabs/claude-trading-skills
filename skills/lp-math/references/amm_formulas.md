# AMM Formulas — Complete Derivations

## Constant Product AMM (xy = k)

### Price from Reserves

For a pool with reserves `x` (token X) and `y` (token Y):

```
Spot price of X in terms of Y:  P_x = y / x
Spot price of Y in terms of X:  P_y = x / y
```

The price is simply the ratio of reserves. This is the marginal price — the price for an infinitesimally small trade.

### Trade Execution: Selling Token X for Token Y

A trader deposits `Δx` of token X and receives `Δy` of token Y.

The invariant must hold after the trade (ignoring fees):

```
(x + Δx) * (y - Δy) = k = x * y
```

Solving for Δy:

```
y - Δy = x * y / (x + Δx)
Δy = y - x * y / (x + Δx)
Δy = y * (1 - x / (x + Δx))
Δy = y * Δx / (x + Δx)
```

**Key result**: `Δy = y * Δx / (x + Δx)`

### Inverse: Required Input for Desired Output

If you want exactly `Δy` of token Y, how much token X do you need?

```
(x + Δx) * (y - Δy) = x * y
x + Δx = x * y / (y - Δy)
Δx = x * y / (y - Δy) - x
Δx = x * (y / (y - Δy) - 1)
Δx = x * Δy / (y - Δy)
```

**Key result**: `Δx = x * Δy / (y - Δy)`

Note: This diverges as `Δy → y` — you can never drain a pool completely.

### With Fees

Most AMMs charge a fee `f` (e.g., 0.003 for 0.3%). The fee is taken from the input:

```
effective_input = Δx * (1 - f)
Δy = y * effective_input / (x + effective_input)
```

After the trade, the new reserves are:

```
x_new = x + Δx                    # Full input added (fee stays in pool)
y_new = y - Δy                    # Output removed
k_new = x_new * y_new > k         # k increases because fee stays
```

The fee causes k to grow monotonically, which is how LPs earn returns.

### Price Impact

Effective execution price vs spot price:

```
spot_price = y / x
execution_price = Δy / Δx
price_impact = 1 - (execution_price / spot_price)
            = 1 - (y * x) / ((x + Δx) * Δx * (y/x))  # simplifies to:
            = Δx / (x + Δx)
```

**Key result**: Price impact = `Δx / (x + Δx)`

For small trades where `Δx << x`: impact ≈ `Δx / x`

### Worked Example

Pool: 100 SOL / 10,000 USDC. Fee: 0.3%.

**Trade**: Sell 5 SOL into the pool.

```
x = 100 SOL, y = 10,000 USDC, k = 1,000,000
Δx = 5 SOL, fee = 0.003

Step 1: Effective input
  effective = 5 * (1 - 0.003) = 4.985 SOL

Step 2: Output
  Δy = 10,000 * 4.985 / (100 + 4.985) = 474.76 USDC

Step 3: New reserves
  x_new = 100 + 5 = 105 SOL
  y_new = 10,000 - 474.76 = 9,525.24 USDC
  k_new = 105 * 9,525.24 = 1,000,150.2 (> 1,000,000)

Step 4: Prices
  Spot before: 10,000 / 100 = 100 USDC/SOL
  Execution:   474.76 / 5 = 94.95 USDC/SOL
  Spot after:  9,525.24 / 105 = 90.72 USDC/SOL
  Impact:      5 / (100 + 5) = 4.76%

Step 5: Fees earned by LPs
  Fee in USDC terms: 474.76 * 0.003 / (1 - 0.003) ≈ 1.43 USDC
```

---

## Concentrated Liquidity (CLMM)

### Virtual Reserves

In a CLMM, liquidity `L` is concentrated in range `[P_lower, P_upper]`. The relationship to virtual reserves:

```
L = sqrt(x_virtual * y_virtual)
L² = x_virtual * y_virtual
```

Where virtual reserves represent what the pool "acts like" within the range.

### Real vs Virtual Reserves

Real token amounts for liquidity `L` in range `[P_a, P_b]` at current price `P`:

```
x_real = L * (1/sqrt(P) - 1/sqrt(P_b))     when P_a ≤ P ≤ P_b
y_real = L * (sqrt(P) - sqrt(P_a))          when P_a ≤ P ≤ P_b
```

Outside the range:
```
If P < P_a:  x_real = L * (1/sqrt(P_a) - 1/sqrt(P_b)),  y_real = 0
If P > P_b:  x_real = 0,  y_real = L * (sqrt(P_b) - sqrt(P_a))
```

### Position Value

Total value in terms of token Y (e.g., USDC):

```
If P ≤ P_a:
  V = L * (1/sqrt(P_a) - 1/sqrt(P_b)) * P    # All token X, valued at P

If P_a < P < P_b:
  V = L * (sqrt(P) - sqrt(P_a))               # Y component
    + L * (1/sqrt(P) - 1/sqrt(P_b)) * P       # X component valued at P
  V = L * (2*sqrt(P) - sqrt(P_a) - P/sqrt(P_b))

If P ≥ P_b:
  V = L * (sqrt(P_b) - sqrt(P_a))             # All token Y
```

### Liquidity from Deposit

Given a deposit of `Δx` and `Δy` in range `[P_a, P_b]` at price `P`:

```
L_from_x = Δx / (1/sqrt(P) - 1/sqrt(P_b))
L_from_y = Δy / (sqrt(P) - sqrt(P_a))
L = min(L_from_x, L_from_y)
```

The minimum ensures the deposit is balanced for the current price.

### Capital Efficiency

A CLMM position in range `[P_a, P_b]` provides the same depth as a full-range position with:

```
efficiency = sqrt(P_b / P_a) / (sqrt(P_b / P_a) - 1)
```

Examples:
```
±1%  range:  P_b/P_a = 1.02/0.98 = 1.0408 → efficiency ≈ 50x
±5%  range:  P_b/P_a = 1.05/0.95 = 1.1053 → efficiency ≈ 20x
±10% range:  P_b/P_a = 1.10/0.90 = 1.2222 → efficiency ≈ 10x
±25% range:  P_b/P_a = 1.25/0.75 = 1.6667 → efficiency ≈ 4x
±50% range:  P_b/P_a = 1.50/0.50 = 3.0000 → efficiency ≈ 2.4x
```

### Tick Math

Prices are discretized into ticks:

```
price_at_tick = 1.0001^tick
tick_at_price = log(price) / log(1.0001)
```

Tick spacing determines the minimum granularity of price ranges:
- Spacing 1: every tick (~0.01% price increment)
- Spacing 10: every 10 ticks (~0.1% price increment)
- Spacing 60: every 60 ticks (~0.6% price increment)

---

## LP Token Math

### Minting (Initial Deposit)

The first depositor defines the initial price and receives:

```
shares = sqrt(Δx * Δy) - MINIMUM_LIQUIDITY
```

`MINIMUM_LIQUIDITY` (typically 1000 units) is permanently locked to prevent manipulation.

### Minting (Subsequent Deposits)

```
shares = min(Δx / x_reserve, Δy / y_reserve) * total_supply
```

If the depositor provides tokens in a different ratio than the pool, only the proportional amount is used. The excess should be returned or the transaction reverts.

### Burning (Withdrawal)

```
x_out = (shares_burned / total_supply) * x_reserve
y_out = (shares_burned / total_supply) * y_reserve
```

This always returns both tokens in the current pool ratio.

### No-Arbitrage Property

LP share value tracks the pool value. If the pool price deviates from the market price, arbitrageurs trade until they converge. This means:

```
share_price = (x_reserve * P_x + y_reserve * P_y) / total_supply
```

The share price changes when:
1. Trades move the reserves (causes impermanent loss)
2. Fees accumulate (increases share value)
3. External rewards are added (if applicable)

Net LP return = Fee APR - Impermanent Loss + External Rewards
