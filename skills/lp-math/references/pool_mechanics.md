# Solana Pool Mechanics

## Raydium V4 (Constant Product)

### Overview
Standard xy = k AMM, the most common pool type on Solana for new token launches.

### Fee Structure
- Total fee: 0.25% per swap
- LP share: 0.22% (88% of fees go to LPs)
- Protocol: 0.03% (12% used for RAY buyback)

### OpenBook Integration
Raydium V4 pools are linked to an OpenBook (formerly Serum) market. This means:
- Limit orders from OpenBook can fill against the AMM liquidity
- Additional volume flows through the pool from orderbook traders
- Pool creation requires creating an OpenBook market first

### Pool Creation
1. Create an OpenBook market for the token pair
2. Initialize the Raydium AMM pool with initial liquidity
3. Set the initial price via the token ratio deposited
4. LP tokens are minted as SPL tokens

### Characteristics
- Always active across all prices (full range)
- Simple to understand and manage
- Higher impermanent loss for volatile pairs
- No position management needed after deposit
- Suitable for long-tail tokens with unpredictable price movement

---

## Orca Whirlpool (Concentrated Liquidity)

### Overview
Concentrated liquidity AMM similar to Uniswap V3. LPs choose a price range for their liquidity.

### Fee Tiers
| Tier | Fee | Tick Spacing | Best For |
|------|-----|-------------|----------|
| 0.01% | 1 bp | 1 | Stablecoin pairs (USDC/USDT) |
| 0.05% | 5 bp | 8 | Correlated pairs |
| 0.30% | 30 bp | 64 | Standard pairs (SOL/USDC) |
| 1.00% | 100 bp | 128 | Exotic/volatile pairs |

### Position Representation
Each LP position is an NFT. This means:
- Positions are non-fungible (each has unique range)
- Can transfer or sell positions
- Multiple positions in the same pool at different ranges
- Position tracks uncollected fees separately

### Tick Spacing and Precision
- Tick spacing determines minimum range granularity
- Lower spacing = finer control but more gas for swaps crossing many ticks
- Price at tick i: `P = 1.0001^i`
- Ticks must be multiples of the tick spacing

### Fee Collection
Fees are not auto-compounded. LPs must:
1. Collect fees manually (transaction required)
2. Optionally re-deposit collected fees as new liquidity
3. Fees accrue in the tokens of the pool (not LP tokens)

### Characteristics
- Capital efficient for predictable ranges
- Requires active management for optimal returns
- Position goes inactive if price moves outside range
- Higher IL risk for narrow ranges
- Fee income concentrated among in-range LPs

---

## Raydium CLMM

### Overview
Raydium's concentrated liquidity implementation, similar to Orca Whirlpool.

### Fee Tiers and Tick Spacing
| Tier | Fee | Tick Spacing | Use Case |
|------|-----|-------------|----------|
| 0.01% | 1 bp | 1 | Stablecoins |
| 0.05% | 5 bp | 10 | Correlated assets |
| 0.25% | 25 bp | 60 | Major pairs |
| 1.00% | 100 bp | 200 | Volatile pairs |

### Differences from Orca Whirlpool
- Different tick spacing values (10 vs 8, 60 vs 64, etc.)
- Integrated with Raydium's broader ecosystem
- Different fee distribution mechanics
- Protocol fee taken from LP fees

### Position Management
- Positions are represented as on-chain accounts
- Can open multiple positions in the same pool
- Fees tracked per-position and collected manually
- Position can be closed at any time, returning tokens + uncollected fees

---

## Meteora DLMM (Dynamic Liquidity Market Maker)

### Overview
Uses discrete price bins instead of continuous ticks. Each bin holds liquidity at a single price point.

### Bin System
- Price space divided into discrete bins
- Each bin represents a fixed price: `price = (1 + bin_step)^bin_id`
- Bin step determines price granularity (e.g., 0.1% between bins)
- Active bin: the bin containing the current price

### Liquidity Distribution Strategies
| Strategy | Distribution | Best For |
|----------|-------------|----------|
| Spot | Uniform across bins | General purpose, passive LPs |
| Curve | Concentrated around current price | Active LPs expecting range-bound |
| Bid-Ask | Split around current price | Market makers |

### Dynamic Fees
Meteora adjusts fees based on market conditions:
- Base fee: Set at pool creation
- Variable fee: Increases with volatility
- Total fee = base_fee + variable_fee
- Variable component uses an exponential moving average of recent volatility

### Single-Sided Deposits
Unlike constant product pools, DLMM allows:
- Depositing only one token (into bins on one side of the current price)
- Useful for building a position gradually
- Deposit only token X in bins above current price (limit sell behavior)
- Deposit only token Y in bins below current price (limit buy behavior)

### Characteristics
- Most flexible liquidity distribution
- Dynamic fees protect LPs during volatile periods
- Single-sided deposits enable limit-order-like strategies
- Bins make position management more intuitive than ticks
- Rebalancing is straightforward: remove from old bins, add to new bins

---

## Comparison Table

| Feature | Raydium V4 | Orca Whirlpool | Raydium CLMM | Meteora DLMM |
|---------|-----------|---------------|-------------|-------------|
| Model | xy = k | Concentrated | Concentrated | Discrete bins |
| Capital efficiency | 1x | Up to 4000x | Up to 4000x | Up to 4000x |
| Fee tiers | 0.25% fixed | 4 tiers | 4 tiers | Dynamic |
| Position type | Fungible LP token | NFT | Account | Account |
| Active management | Not needed | Recommended | Recommended | Recommended |
| Range selection | Full range only | Custom range | Custom range | Custom bins |
| Single-sided deposit | No | No | No | Yes |
| Fee auto-compound | Yes (in k) | No (manual) | No (manual) | No (manual) |
| Best for | New tokens | Major pairs | Major pairs | Active LPs |
| Complexity | Low | Medium | Medium | Medium-High |

---

## Pool Selection Guide

### By Asset Type
- **Stablecoin pairs**: CLMM with tight range (±0.5%), lowest fee tier
- **Major pairs (SOL/USDC)**: CLMM with ±10-25% range, 0.3% fee tier
- **New token launches**: Raydium V4 constant product
- **Volatile meme tokens**: Raydium V4 or DLMM with wide distribution
- **Actively managed**: Meteora DLMM with frequent rebalancing

### By LP Style
- **Passive**: Raydium V4 (set and forget, no range to manage)
- **Semi-active**: CLMM with wide range, rebalance weekly
- **Active**: Meteora DLMM, rebalance daily based on volatility
- **Professional**: Multiple narrow CLMM positions, algorithmic rebalancing
