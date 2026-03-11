---
name: slippage-modeling
description: Execution cost estimation, slippage curve modeling, and optimal trade sizing based on AMM liquidity depth
---

# Slippage Modeling

Estimate execution costs, model slippage curves from AMM mechanics and empirical quotes, and determine optimal trade sizes that keep costs within acceptable thresholds.

## What Is Slippage?

Slippage is the difference between the **expected price** at the time you decide to trade and the **actual execution price** you receive. On decentralized exchanges, slippage is deterministic and measurable — unlike CEX slippage, which depends on hidden order book dynamics.

**Example**: You expect to buy a token at 0.001 SOL. Your trade executes at 0.00105 SOL. That 5% difference is slippage — it directly reduces your profit and increases your break-even threshold.

## Sources of Slippage

### 1. AMM Price Impact (Primary Source)

Automated market makers use bonding curves that move price as liquidity is consumed. On a constant-product AMM (`x * y = k`):

```
price_impact = Δx / (x + Δx)
```

Where `x` is the reserve of the input token and `Δx` is your trade size. A 1 SOL trade against a pool with 100 SOL reserves produces ~1% price impact. Against 10 SOL reserves, it produces ~10%.

See `references/slippage_math.md` for full derivations and CLMM adjustments.

### 2. DEX Fees

Every swap incurs a fee taken from the trade:

| DEX      | Fee       | Notes                          |
|----------|-----------|--------------------------------|
| Raydium  | 0.25%     | Standard AMM pools             |
| Orca     | 0.30%     | Whirlpool concentrated pools   |
| Meteora  | 0.1–2.0%  | Dynamic fees based on volatility|
| PumpFun  | 1.0%      | Bonding curve phase            |

### 3. Priority Fees

Solana validators prioritize transactions with higher compute unit prices. During congestion or for time-sensitive trades:
- Normal: 0.0001 SOL (negligible)
- Competitive: 0.001–0.01 SOL
- High congestion: 0.01–0.1 SOL

### 4. MEV (Sandwich Attacks)

Searchers detect pending swaps and sandwich them — buying before your trade (raising the price) and selling after (capturing the difference). MEV cost depends on:
- Trade size (larger = more attractive target)
- Token liquidity (thin pools = easier to manipulate)
- Slippage tolerance setting (higher tolerance = more extractable)

Typical MEV cost: 0–200 bps on vulnerable trades.

### 5. Stale Quotes

Between receiving a quote and landing the transaction on-chain (0.4–2 seconds on Solana), the price may move. Volatile tokens can shift 50–500 bps in that window.

## Constant-Product Slippage Formula

For a pool with reserves `(x, y)` and invariant `k = x * y`:

**Buying tokens with SOL** (input Δx SOL):
```
tokens_received = y * Δx / (x + Δx)
effective_price = Δx / tokens_received = (x + Δx) / y
spot_price      = x / y
price_impact    = effective_price / spot_price - 1 = Δx / (x + Δx)
```

**Selling tokens for SOL** (input Δy tokens):
```
sol_received   = x * Δy / (y + Δy)
effective_price = sol_received / Δy = x / (y + Δy)
spot_price      = x / y
price_impact    = 1 - effective_price / spot_price = Δy / (y + Δy)
```

**Key insight**: Slippage scales with `trade_size / (reserves + trade_size)`. This is approximately linear for small trades and accelerates sharply as trade size approaches reserve size.

### Quick Reference Table

| Trade / Reserve Ratio | Approximate Slippage |
|----------------------|---------------------|
| 0.1%                 | 0.1% (1 bp)         |
| 1%                   | 1.0% (100 bps)      |
| 5%                   | 4.8% (476 bps)      |
| 10%                  | 9.1% (909 bps)      |
| 25%                  | 20% (2000 bps)      |
| 50%                  | 33% (3333 bps)      |

## CLMM Slippage

Concentrated Liquidity Market Makers (Orca Whirlpools, Meteora DLMM) concentrate liquidity in specific price ranges:

- Within the active range: slippage is **lower** than constant-product by a concentration factor
- Crossing tick boundaries: additional slippage as the next tick's liquidity may be sparse
- Approximation: `clmm_slippage ≈ cp_slippage / concentration_factor`

Typical concentration factors: 5–50x for well-managed positions.

## Empirical Slippage Measurement

Theoretical formulas assume single-pool routing. In practice, Jupiter aggregates across multiple pools and routes. **Empirical measurement** is more accurate:

1. Query Jupiter `/quote` at multiple trade sizes (0.01, 0.1, 1, 5, 10, 50 SOL)
2. Record output amount and effective price at each size
3. Compute slippage in bps relative to smallest trade (proxy for spot)
4. Fit a power-law model: `slippage_bps = a * trade_size^b`

This captures real routing behavior, multi-pool splitting, and available liquidity.

See `scripts/slippage_curve.py` for the full implementation.

## Total Execution Cost Model

```
total_cost_bps = price_impact_bps + fee_bps + priority_fee_bps + mev_risk_bps
total_cost_sol = trade_size_sol * total_cost_bps / 10_000
```

See `references/cost_model.md` for component breakdowns and worked examples.

### Break-Even Analysis

For a roundtrip (buy + sell):
```
roundtrip_cost_bps = entry_impact + exit_impact + 2 * fee_bps + 2 * priority_bps + mev_bps
```

The token must move **more than** `roundtrip_cost_bps` in your favor to be profitable. For a token with 200 bps entry slippage, 200 bps exit slippage, and 50 bps fees:
```
roundtrip = 200 + 200 + 50 = 450 bps = 4.5%
```

You need at least a 4.5% price move just to break even.

See `scripts/execution_cost.py` for automated cost estimation.

## Optimal Trade Sizing

### Maximum Size for Slippage Threshold

Given a slippage curve `s(q) = a * q^b`, solve for max trade size:
```
q_max = (threshold_bps / a) ^ (1/b)
```

### Multi-Tranche Execution

For large orders, splitting reduces total slippage because each tranche faces a partially-reset order book (on CLMMs) or allows arbitrageurs to rebalance between tranches:

```
n_tranches = ceil(total_size / q_max)
tranche_size = total_size / n_tranches
wait_between = 2-10 seconds (allow arb rebalancing)
```

### TWAP Strategy

Time-Weighted Average Price execution:
- Divide total order into equal-sized tranches
- Execute one tranche per interval (e.g., every 10 seconds)
- Total slippage is significantly lower than single execution
- Tradeoff: price may move against you during execution window

## Slippage by Token Category

| Category      | Typical Pool TVL | Slippage for 1 SOL | Slippage for 10 SOL |
|---------------|-----------------|---------------------|----------------------|
| Blue chip     | >$10M           | <5 bps              | <20 bps              |
| Mid-cap       | $100K–$10M      | 10–50 bps           | 50–500 bps           |
| Small-cap     | $10K–$100K      | 50–200 bps          | 500–2000 bps         |
| Micro/PumpFun | <$10K           | 200–2000 bps        | Often impossible      |

## Integration Points

- **liquidity-analysis**: Get pool TVL and reserve data to feed slippage estimates
- **position-sizing**: Use max trade size from slippage curve as a position size constraint
- **jupiter-api**: Fetch real quotes for empirical slippage measurement
- **risk-management**: Include execution costs in risk/reward calculations
- **dex-pool-analysis**: Understand pool mechanics that drive slippage

## Files

### References
| File | Description |
|------|-------------|
| `references/slippage_math.md` | AMM slippage derivations, CLMM adjustments, multi-pool routing math |
| `references/cost_model.md` | Total execution cost components, break-even analysis, cost comparison tables |

### Scripts
| File | Description |
|------|-------------|
| `scripts/slippage_curve.py` | Build empirical slippage curves from Jupiter quotes, fit power-law model |
| `scripts/execution_cost.py` | Estimate total execution cost and break-even for a specific trade |
