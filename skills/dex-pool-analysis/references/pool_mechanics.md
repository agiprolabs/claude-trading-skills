# DEX Pool Mechanics — Solana AMM Comparison

Detailed mechanics for each major AMM pool type on Solana, including formulas, fee structures, and program IDs.

---

## Raydium V4 (Constant Product)

**Program ID**: `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`

### Mechanics
- Uses the constant-product invariant: `x * y = k`
- Full-range liquidity — every LP position covers price 0 to infinity
- Integrated with OpenBook (Serum successor) for hybrid AMM + orderbook routing

### Fee Structure
- **Swap fee**: 0.25% per trade
- **LP share**: 0.22% (88% of fee)
- **Protocol share**: 0.03% used for RAY token buyback

### Pool Creation
- Requires an OpenBook market ID
- Initial liquidity set by creator (both tokens deposited in equal USD value)
- Pool creation fee: ~0.4 SOL (for OpenBook market + pool accounts)

### Swap Formula
```
output = (reserve_out * amount_in * 9975) / (reserve_in * 10000 + amount_in * 9975)
```

The `9975/10000` factor encodes the 0.25% fee.

### Price Impact
```
price_impact = amount_in / (reserve_in + amount_in)
```

For a $1,000 trade against a pool with $100,000 in reserves: ~1% price impact.

---

## Raydium CLMM (Concentrated Liquidity)

**Program ID**: `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`

### Mechanics
- Concentrated liquidity (Uniswap V3-style) on Solana
- LPs choose a price range [P_low, P_high] for their position
- Liquidity only active when current price is within range
- Position represented as an NFT

### Fee Tiers and Tick Spacing

| Fee Tier | Tick Spacing | Use Case |
|----------|-------------|----------|
| 0.01% | 1 | Stablecoin pairs |
| 0.05% | 10 | Correlated assets (LSTs) |
| 0.25% | 60 | Standard pairs |
| 1.00% | 120 | Volatile pairs |
| 2.00% | 240 | Very volatile / meme tokens |

### Price-Tick Relationship
```
price = 1.0001^tick
tick = log(price) / log(1.0001)
```

### Liquidity Concentration Factor
```
concentration = sqrt(P_high / P_low) / (sqrt(P_high / P_low) - 1)
```

A position covering a +/-5% range has ~10x concentration vs full range. A +/-1% range has ~50x.

### Capital Efficiency
For a given TVL, concentrated positions provide more liquidity depth at the current price:
```
effective_liquidity = tvl * concentration_factor
```

---

## Orca Whirlpool (Concentrated Liquidity)

**Program ID**: `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`

### Mechanics
- Concentrated liquidity similar to Raydium CLMM
- Positions as NFTs with per-position fee tracking
- Mature SDK with strong TypeScript and Rust support

### Fee Tiers

| Fee Tier | Tick Spacing | Typical Use |
|----------|-------------|-------------|
| 0.01% | 1 | Stable pairs |
| 0.02% | 2 | Tightly correlated |
| 0.04% | 4 | LST pairs |
| 0.05% | 8 | Correlated assets |
| 0.16% | 16 | Mid-vol pairs |
| 0.30% | 64 | Standard pairs |
| 0.65% | 128 | Higher vol |
| 1.00% | 256 | Volatile pairs |
| 2.00% | 512 | Meme / high vol |

### Fee Distribution
- **LP share**: ~87% of swap fees
- **Protocol share**: ~13% to Orca treasury

### Key Differences from Raydium CLMM
- More fee tier options (9 vs 5)
- Different tick spacing mapping
- Separate reward mechanism for liquidity mining
- Generally higher TVL for major pairs (SOL/USDC, SOL/USDT)

---

## Meteora DLMM (Dynamic Liquidity Market Maker)

**Program ID**: `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`

### Mechanics
- **Bin-based** liquidity: each bin holds liquidity at a single discrete price
- Current active bin determines the current price
- LPs distribute tokens across multiple bins using strategy modes
- Zero slippage for trades that fit within a single bin

### Bin System
```
bin_price = (1 + bin_step / 10000) ^ (bin_id - 8388608)
```
- `bin_step`: 1-100 basis points between adjacent bins
- `bin_id`: integer index, 8388608 is the "zero" bin (price = 1.0)

### Strategy Modes

| Mode | Distribution | Best For |
|------|-------------|----------|
| **Spot** | Uniform across bins | General purpose, balanced exposure |
| **Curve** | Gaussian/bell curve around current price | Concentrated around expected price |
| **Bid-Ask** | Heavy on outer bins | Market-making, earning on mean reversion |

### Dynamic Fee
```
total_fee = base_fee + variable_fee
variable_fee = bin_step * volatility_accumulator
```

The variable fee increases during high-volatility periods (many bin crossings in recent swaps) and decays over time. This protects LPs from adverse selection during volatile moves.

### Fee Distribution
- **LP share**: ~80% of total fee
- **Protocol share**: ~20% to Meteora treasury

---

## Meteora Dynamic Pools

**Program ID**: `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB`

### Mechanics
- Constant-product base with dynamic fee adjustment
- Single-sided deposits permitted (the protocol rebalances internally)
- Fees adjust based on recent price volatility

### Key Features
- Lower barrier for LPs (no price range selection required)
- Volatility-based fee: higher fees during volatile periods, lower during calm
- Virtual price mechanism for fair LP token valuation

---

## PumpSwap

**Program ID**: `PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP`

### Mechanics
- Standard constant-product AMM (`xy = k`)
- Designed as the destination for PumpFun bonding curve graduations
- Launched March 2025, replacing Raydium V4 as default migration target

### Fee Structure
- **Swap fee**: 0.25% per trade
- **LP share**: 0.20% (80%)
- **Protocol share**: 0.05% (20%), with 10% of protocol fees going to coin creators

### Migration Details
- Migration from bonding curve is automatic at ~$69K market cap
- Migration fee: 0 SOL (reduced from 6 SOL in original Raydium migration)
- Initial pool liquidity: ~85 SOL + all remaining tokens from bonding curve

---

## Program ID Quick Reference

| DEX | Program ID |
|-----|-----------|
| Raydium V4 | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` |
| Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` |
| Orca Whirlpool | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` |
| Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` |
| Meteora Dynamic | `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` |
| PumpSwap | `PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP` |
| PumpFun Bonding | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` |

---

## Comparison Summary

| Feature | Raydium V4 | Raydium CLMM | Orca Whirlpool | Meteora DLMM | PumpSwap |
|---------|-----------|-------------|----------------|-------------|----------|
| Model | xy=k | Concentrated | Concentrated | Bin-based | xy=k |
| Fee | 0.25% fixed | 0.01-2% | 0.01-2% | Dynamic | 0.25% fixed |
| Capital efficiency | 1x | 10-100x | 10-100x | 10-50x | 1x |
| LP complexity | Low | High | High | Medium | Low |
| Slippage model | Continuous | Tick-based | Tick-based | Bin-based | Continuous |
| Position type | LP tokens | NFT | NFT | NFT | LP tokens |
| Dynamic fee | No | No | No | Yes | No |

*This reference provides technical information about pool mechanics. It does not constitute financial advice.*
