# PumpFun Bonding Curve — Mathematical Reference

## Invariant

PumpFun uses a virtual constant-product market maker (CPMM):

```
k = V_sol × V_tok = constant
```

Where `V_sol` and `V_tok` are **virtual** reserves that include both real (withdrawable) and phantom reserves.

## Initial State

| Variable | Value | Raw |
|----------|-------|-----|
| V_sol (virtual SOL) | 30 SOL | 30,000,000,000 lamports |
| V_tok (virtual tokens) | ~1.073B | 1,073,000,000,000,000 |
| R_tok (real tokens) | ~793M | 793,000,000,000,000 |
| R_sol (real SOL) | 0 | 0 |
| Supply | 1B | 1,000,000,000,000,000 |
| k | — | 3.219 × 10²⁵ |

The virtual-real gap: V_tok - R_tok ≈ 280M tokens are virtual — they shape the curve but cannot be withdrawn.

## Spot Price

At any point on the curve:

```
P = V_sol / V_tok   (in lamports per raw token)

P_human = (V_sol / 10⁹) / (V_tok / 10⁶)   (SOL per token)
```

### Price progression examples

| Fill % | R_sol | V_sol | V_tok | Price (SOL) | Multiplier |
|--------|-------|-------|-------|-------------|------------|
| 0% | 0 | 30B | 1.073T | 2.796e-8 | 1.0x |
| 5% | 3.75B | 33.75B | 953.7B | 3.539e-8 | 1.27x |
| 25% | 21.9B | 51.9B | 620.7B | 8.354e-8 | 2.99x |
| 50% | 45.8B | 75.8B | 424.7B | 1.784e-7 | 6.38x |
| 75% | 63.8B | 93.8B | 343.2B | 2.733e-7 | 9.78x |
| 100% | 85B | 115B | 279.9B | 4.109e-7 | 14.70x |

A token that goes from launch to graduation (100% fill) achieves approximately **14.7x** price appreciation.

## Buy Formula

Given SOL input `Δsol` (after 1% fee is deducted externally):

```
V_sol' = V_sol + Δsol
V_tok' = ⌊k / V_sol'⌋ + 1          (ceiling division match)
tokens_out = V_tok - V_tok'
result = min(tokens_out, R_tok)     (can't buy more than real reserves)
```

The `+1` on V_tok' matches on-chain rounding behavior. Validated against 9K+ live trades.

### Worked Example: Buy 1 SOL at genesis

```
V_sol = 30,000,000,000
V_tok = 1,073,000,000,000,000
k = 30,000,000,000 × 1,073,000,000,000,000 = 3.219e25

sol_in = 1,000,000,000 (1 SOL, before fee; actual to curve = 990,000,000)
V_sol' = 30,990,000,000
V_tok' = 3.219e25 / 30,990,000,000 + 1 = 1,038,722,168,441,433
tokens_out = 1,073,000,000,000,000 - 1,038,722,168,441,433 = 34,277,831,558,567

Result: ~34.28M tokens (34,277,831,558,567 raw / 10^6 = 34,277,831.56)
```

## Sell Formula

Given `Δtok` tokens to sell:

```
V_tok' = V_tok + Δtok
V_sol' = ⌊k / V_tok'⌋
sol_out = V_sol - V_sol' - 1         (floor division match)
result = min(sol_out, R_sol)         (can't withdraw more than real SOL)
```

The `-1` is critical for matching on-chain floor division behavior.

## Buy Cost Formula

Given exact `tokens_wanted`:

```
V_tok' = V_tok - tokens_wanted
V_sol' = ⌊k / V_tok'⌋ + 1
cost = V_sol' - V_sol
```

Returns infinity if `tokens_wanted >= V_tok`.

## Price Impact

```
impact = (execution_price / spot_price - 1) × 100%

Where:
  spot_price = V_sol / V_tok
  execution_price = sol_in / tokens_out
```

### Impact at genesis for various sizes

| Buy Size | Tokens | Impact | % of Supply |
|----------|--------|--------|-------------|
| 0.1 SOL | ~3.5M | 0.33% | 0.35% |
| 1 SOL | ~34.3M | 3.33% | 3.43% |
| 5 SOL | ~152M | 16.7% | 15.2% |
| 10 SOL | ~268M | 33.3% | 26.8% |

Impact grows super-linearly due to the constant-product curve.

## Fee Structure

| Action | Fee | Deducted From |
|--------|-----|---------------|
| Buy | 1% (100 bps) | SOL input (before curve) |
| Sell | 1% (100 bps) | SOL output (after curve) |
| Create | Free | — |

Fee is applied by the on-chain program, NOT by the curve math. Always calculate curve math with pre-fee amounts, then apply fee externally.

### Roundtrip Cost

```
Roundtrip loss = 1 - (1 - 0.01) × (1 - 0.01) × (1 - impact_buy) × (1 - impact_sell)
              ≈ 2% + 2 × avg_impact

For a 1 SOL buy at genesis: ~2% + 2 × 3.3% ≈ 8.6% roundtrip loss
```

## Edge Cases

1. **Zero reserves**: If `R_tok = 0`, no more buys possible (curve depleted)
2. **Zero real SOL**: If `R_sol = 0`, sells return 0 (no SOL to withdraw)
3. **Dust trades**: For amounts < 100K lamports, the `+1/-1` rounding corrections become significant
4. **Completed curve**: After graduation (`complete = true`), all buy/sell calls revert
