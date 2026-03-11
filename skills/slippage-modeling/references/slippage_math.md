# Slippage Math — AMM Derivations & Multi-Pool Routing

## Constant-Product AMM (x * y = k)

### Setup

A pool has reserves `(x, y)` where:
- `x` = SOL reserves
- `y` = token reserves
- `k = x * y` = constant invariant (ignoring fees)

Spot price of token in SOL: `P_spot = x / y`

### Buy: Swapping Δx SOL for Tokens

After depositing Δx SOL, new SOL reserves = `x + Δx`. To maintain invariant:

```
(x + Δx) * (y - Δy) = k = x * y
y - Δy = x * y / (x + Δx)
Δy = y - x * y / (x + Δx)
Δy = y * Δx / (x + Δx)
```

**Effective price** (SOL per token):
```
P_eff = Δx / Δy = Δx * (x + Δx) / (y * Δx) = (x + Δx) / y
```

**Price impact** (fractional):
```
impact = P_eff / P_spot - 1
       = [(x + Δx) / y] / [x / y] - 1
       = (x + Δx) / x - 1
       = Δx / x
```

Wait — this gives `Δx / x`, but the commonly cited formula is `Δx / (x + Δx)`. The difference is reference frame:

- `Δx / x` = price impact relative to pre-trade spot price
- `Δx / (x + Δx)` = fraction of output lost vs. a hypothetical zero-impact trade

**Output loss fraction** (more practically useful):
```
ideal_output = y * Δx / x        (at spot price, no impact)
actual_output = y * Δx / (x + Δx)
loss_fraction = 1 - actual/ideal = Δx / (x + Δx)
```

This `Δx / (x + Δx)` is what traders experience as "slippage."

### Worked Example

Pool: 1000 SOL / 10,000,000 tokens (spot price = 0.0001 SOL/token)

**Trade: Buy with 10 SOL**
```
Δy = 10,000,000 * 10 / (1000 + 10) = 99,009.90 tokens
Ideal output = 10,000,000 * 10 / 1000 = 100,000 tokens
Slippage = 1 - 99,009.90 / 100,000 = 0.99% ≈ 99 bps
Check: Δx/(x+Δx) = 10/1010 = 0.99% ✓
```

**Trade: Buy with 100 SOL**
```
Δy = 10,000,000 * 100 / (1000 + 100) = 909,090.9 tokens
Ideal output = 1,000,000 tokens
Slippage = 1 - 909,090.9 / 1,000,000 = 9.09% ≈ 909 bps
Check: 100/1100 = 9.09% ✓
```

### Sell: Swapping Δy Tokens for SOL

Depositing Δy tokens, new token reserves = `y + Δy`:

```
(x - Δx_out) * (y + Δy) = k = x * y
Δx_out = x * Δy / (y + Δy)
```

**Output loss fraction**:
```
ideal_sol = x * Δy / y
actual_sol = x * Δy / (y + Δy)
loss_fraction = Δy / (y + Δy)
```

### Slippage Asymmetry

Buying and selling the same dollar amount produce **different** slippage because they draw from different reserves. If SOL reserves are 1000 and token reserves are 10M:

- Buying 10 SOL worth: slippage = 10/1010 = 0.99%
- Selling 100,000 tokens (worth ~10 SOL): slippage = 100,000/10,100,000 = 0.99%

The slippage is symmetric in value terms for constant-product. But if reserves are imbalanced in value (price moved from initial), the side with less value has higher slippage per dollar.

## Fee-Adjusted Slippage

Most AMMs take fees **before** the swap. For a fee rate `f` (e.g., 0.0025 for 0.25%):

```
effective_input = Δx * (1 - f)
Δy = y * effective_input / (x + effective_input)
total_slippage = 1 - Δy / ideal_output
             = 1 - (1-f) * x / (x + Δx*(1-f))
```

For small trades, total slippage ≈ `f + Δx/x` (fee plus impact).

## Concentrated Liquidity (CLMM)

### How Concentration Affects Slippage

In CLMMs (Orca Whirlpools, Meteora DLMM), liquidity providers specify a price range `[P_low, P_high]`. Within this range, the effective reserves are amplified:

```
effective_x = real_x * concentration_factor
concentration_factor ≈ 1 / (1 - sqrt(P_low/P_high))
```

For a position spanning ±5% around current price:
```
concentration ≈ 1 / (1 - sqrt(0.95/1.05)) ≈ 1 / (1 - 0.951) ≈ 20x
```

**Slippage within active range**:
```
clmm_slippage ≈ cp_slippage / concentration_factor
```

A trade that would cause 100 bps slippage on constant-product only causes ~5 bps on a 20x concentrated position.

### Tick Boundary Crossings

When a trade is large enough to exhaust liquidity in the current tick range, it crosses into the next tick where:
- Liquidity may be different (higher, lower, or zero)
- Each crossing adds a discrete jump in slippage

This makes CLMM slippage **non-smooth** — it can jump sharply at tick boundaries. Empirical measurement (via Jupiter quotes) captures this better than theoretical models.

## Multi-Pool Routing

### Optimal Split Across Pools

When Jupiter routes across `n` pools with reserves `(x_1, y_1), ..., (x_n, y_n)`, the optimal split minimizes total slippage.

For constant-product pools, the optimal fraction to route through pool `i`:

```
fraction_i = sqrt(x_i * y_i) / sum_j(sqrt(x_j * y_j))
           = sqrt(L_i) / sum_j(sqrt(L_j))
```

Where `L_i = x_i * y_i` is the pool's liquidity (k-value).

### Routing Through Intermediaries

Jupiter may route SOL → USDC → TOKEN if the SOL/TOKEN direct pool is thin. Total slippage compounds:

```
total_slippage ≈ slippage_hop1 + slippage_hop2
```

(Approximate for small slippage values; exact: `1 - (1-s1)*(1-s2)`)

### Why Empirical > Theoretical

Theoretical models assume:
- Known pool reserves (may be stale)
- Single pool type (ignoring CLMM/AMM mix)
- No intermediary routing

Jupiter's actual quotes incorporate all of this. Querying at multiple sizes gives the true executable slippage curve.

## Power-Law Slippage Model

Empirically, slippage curves follow a power law:

```
slippage_bps = a * trade_size_sol ^ b
```

Where:
- `a` = slippage coefficient (higher = less liquid)
- `b` = slippage exponent (typically 0.8–1.2; 1.0 = perfectly linear)

**Fitting**: Use log-linear regression on `(log(size), log(slippage))` pairs from Jupiter quotes.

**Inverting** (find max size for a slippage limit):
```
max_size = (limit_bps / a) ^ (1/b)
```

This model works well for interpolation within the fitted range. Extrapolation beyond the largest tested size is unreliable.
