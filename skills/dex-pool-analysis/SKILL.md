---
name: dex-pool-analysis
description: AMM pool mechanics comparison across Raydium, Orca, and Meteora including fee structures, pool types, creation patterns, and volume efficiency
---

# DEX Pool Analysis — Solana AMM Pool Mechanics & Comparison

Solana's DEX ecosystem spans multiple AMM designs: constant-product pools (Raydium V4), concentrated liquidity (Raydium CLMM, Orca Whirlpool), and bin-based liquidity (Meteora DLMM). Each pool type has distinct fee structures, capital efficiency characteristics, and risk profiles. Understanding these differences is essential for selecting the best execution venue, evaluating liquidity quality, and identifying pool-level risks.

This skill covers:
- Pool type mechanics and fee structures across Solana DEXes
- Pool health metrics (TVL, volume efficiency, fee APR, LP count)
- Pool creation patterns (PumpFun graduation, manual creation)
- Best pool selection for trade execution
- Pool age and risk assessment

**Related skills**: See `lp-math` for AMM formulas, `liquidity-analysis` for depth assessment, `impermanent-loss` for LP risk, `slippage-modeling` for execution cost.

---

## 1. Pool Types on Solana

### Raydium V4 (Constant Product)

The most common pool type for newly launched tokens. Uses the classic `xy = k` invariant with a fixed 0.25% swap fee. Integrated with OpenBook (formerly Serum) for combined AMM + orderbook liquidity.

```
Program ID: 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
Fee: 0.25% per swap (0.22% to LPs, 0.03% to RAY buyback)
```

**Key characteristics**:
- Full-range liquidity (infinite price range)
- Simple LP provisioning — deposit both tokens in equal value
- Lower capital efficiency than concentrated liquidity
- OpenBook market ID required for pool creation

### Raydium CLMM (Concentrated Liquidity)

Concentrated Liquidity Market Maker pools allow LPs to specify price ranges, improving capital efficiency by 10-100x compared to V4.

```
Program ID: CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK
Fee tiers: 0.01%, 0.05%, 0.25%, 1%, 2%
Tick spacing: 1, 10, 60, 120, 240 (corresponding to fee tiers)
```

**Key characteristics**:
- LPs choose min/max price for their position
- Positions represented as NFTs
- Higher fee income per dollar deposited (when in range)
- Risk of position going out of range (no fees earned)
- Multiple fee tiers for different volatility profiles

### Orca Whirlpool (Concentrated Liquidity)

Orca's concentrated liquidity implementation, dominant for major token pairs (SOL/USDC, SOL/USDT).

```
Program ID: whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc
Fee tiers: 0.01%, 0.02%, 0.04%, 0.05%, 0.16%, 0.30%, 0.65%, 1%, 2%
Tick spacing: 1, 2, 4, 8, 16, 64, 128, 256, 512 (varies by fee)
```

**Key characteristics**:
- Positions as NFTs (similar to Uniswap V3)
- Wide fee tier selection for granular control
- Strong SDK and developer tooling
- Dominant for blue-chip Solana pairs

### Meteora DLMM (Dynamic Liquidity Market Maker)

Bin-based liquidity where each bin holds a fixed price. LPs distribute liquidity across bins using strategy modes.

```
Program ID: LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo
Fee: Dynamic (base fee + variable fee based on volatility)
Bin step: 1-100 basis points per bin
```

**Key characteristics**:
- Discrete price bins instead of continuous ticks
- Dynamic fees that increase during high volatility
- Strategy modes: Spot, Curve, Bid-Ask
- Zero slippage within a single bin
- Extremely capital efficient for stablecoin pairs

### Meteora Dynamic Pools

Multi-token pools with single-sided deposit capability and volatility-adjusted fees.

```
Program ID: Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB
Fee: Volatility-based dynamic fee
```

**Key characteristics**:
- Single-sided deposits allowed
- Dynamic fee based on recent price volatility
- Multi-token pool support
- Simpler LP experience than concentrated liquidity

### PumpSwap (PumpFun AMM)

PumpFun's native AMM for tokens that graduate from the bonding curve.

```
Program ID: PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP
Fee: 0.25% per swap (0.20% to LPs, 0.05% protocol)
Migration fee: 0 SOL (post-March 2025)
```

**Key characteristics**:
- Constant-product (`xy = k`) mechanics
- Automatic migration from PumpFun bonding curve at ~$69K market cap
- Creator coin rewards (10% of protocol fees to coin creators)

---

## 2. Fee Structure Comparison

| DEX | Pool Type | Fee Range | LP Share | Protocol Share |
|-----|-----------|-----------|----------|----------------|
| Raydium V4 | Constant Product | 0.25% fixed | 0.22% | 0.03% (RAY) |
| Raydium CLMM | Concentrated | 0.01%–2% | ~84% | ~16% |
| Orca Whirlpool | Concentrated | 0.01%–2% | 87% | 13% |
| Meteora DLMM | Bin-based | Dynamic | 80% | 20% |
| Meteora Dynamic | Dynamic | Variable | ~80% | ~20% |
| PumpSwap | Constant Product | 0.25% fixed | 0.20% | 0.05% |

**Fee tier selection guidance**:
- **0.01%**: Stablecoin pairs (USDC/USDT) — minimal price movement
- **0.05%**: Correlated assets (mSOL/SOL, jitoSOL/SOL) — low volatility
- **0.25%–0.30%**: Standard pairs (SOL/USDC) — moderate volatility
- **1%–2%**: Volatile/meme tokens — high impermanent loss risk

---

## 3. Pool Creation Patterns

### PumpFun Graduation Flow

Most new Solana meme tokens follow this lifecycle:

```
PumpFun Bonding Curve → ~$69K market cap → Migration → Raydium V4 or PumpSwap
```

1. Token launches on PumpFun bonding curve
2. As buys push market cap to ~$69K, the bonding curve completes
3. Liquidity migrates automatically to either Raydium V4 or PumpSwap
4. Since March 2025, PumpFun defaults migration to PumpSwap (their own AMM)
5. Post-migration, additional pools may be created on other DEXes

**Analysis implications**:
- Pools created via PumpFun graduation have known initial liquidity (~$12K)
- Very new graduated pools carry higher rug risk
- Check if creator LP tokens are locked or burnable

### Manual Pool Creation

Tokens not launched via PumpFun have pools created manually:
- Raydium V4 requires an OpenBook market + pool initialization
- Raydium CLMM, Orca, and Meteora allow direct pool creation
- Manual creation allows arbitrary initial liquidity amounts

---

## 4. Volume Efficiency (Volume/TVL Ratio)

Volume efficiency measures how actively a pool's liquidity is utilized:

```python
volume_efficiency = volume_24h / tvl
```

| V/TVL Ratio | Interpretation |
|-------------|---------------|
| > 5.0 | Very high turnover — likely wash trading or bot activity |
| 1.0–5.0 | Active trading — healthy, well-utilized pool |
| 0.1–1.0 | Moderate activity — normal for mid-cap tokens |
| < 0.1 | Low activity — stale or abandoned pool |
| 0.0 | No trades — dead pool |

**Fee APR estimation from volume efficiency**:

```python
fee_apr = volume_efficiency * fee_rate * 365
# Example: V/TVL of 2.0 at 0.25% fee = 2.0 * 0.0025 * 365 = 182.5% APR
```

This is a theoretical maximum — actual LP returns depend on impermanent loss, position range (for concentrated liquidity), and fee share.

---

## 5. Pool Health Metrics

### Core Metrics

```python
pool_health = {
    "tvl_usd": 150_000,          # Total value locked
    "volume_24h_usd": 300_000,   # 24-hour trading volume
    "volume_tvl_ratio": 2.0,     # Volume efficiency
    "fee_apr_estimate": 182.5,   # Annualized fee rate (%)
    "pool_age_hours": 720,       # Time since creation
    "lp_count_estimate": 45,     # Number of LP positions
    "tvl_trend_24h": -0.05,      # TVL change (-5%)
    "price_change_24h": 0.12,    # Price change (+12%)
}
```

### Red Flags

Watch for these warning signs when evaluating pools:

| Red Flag | Threshold | Risk |
|----------|-----------|------|
| Very new pool | < 24 hours old | Rug pull, unvetted token |
| Single LP | LP count = 1 | Creator can pull all liquidity |
| Declining TVL | > 20% drop in 24h | Liquidity flight |
| Zero volume | No trades in 6h+ | Dead or abandoned |
| Extreme V/TVL | > 10x | Wash trading, bot manipulation |
| Tiny TVL | < $1,000 | Massive slippage on any trade |

### Health Score Algorithm

```python
def compute_health_score(
    tvl_usd: float,
    volume_24h: float,
    pool_age_hours: float,
    lp_count: int,
    tvl_change_24h: float,
) -> float:
    """Score from 0-100 indicating pool health.

    Components (each 0-20):
    - TVL adequacy: Is there enough liquidity?
    - Volume efficiency: Is the pool actively traded?
    - Maturity: How long has the pool existed?
    - LP diversity: How many independent LPs?
    - TVL stability: Is liquidity growing or shrinking?
    """
    # TVL score (0-20): logarithmic scale, peaks at $1M+
    tvl_score = min(20, max(0, 5 * math.log10(max(tvl_usd, 1)) - 10))

    # Volume score (0-20): V/TVL ratio, sweet spot 0.5-3.0
    v_tvl = volume_24h / max(tvl_usd, 1)
    volume_score = min(20, max(0, v_tvl * 10)) if v_tvl < 5 else max(0, 20 - (v_tvl - 5) * 4)

    # Age score (0-20): older = more trusted
    age_score = min(20, pool_age_hours / 72 * 20)  # Max at 72h

    # LP diversity score (0-20)
    lp_score = min(20, lp_count * 2)  # Max at 10 LPs

    # Stability score (0-20): penalize large negative TVL changes
    stability_score = max(0, 20 + tvl_change_24h * 40)  # -50% → 0, 0% → 20

    return tvl_score + volume_score + age_score + lp_score + stability_score
```

---

## 6. Best Pool Selection for Execution

When multiple pools exist for a token pair, select the best one for trade execution:

```python
def rank_pools_for_execution(pools: list[dict], trade_size_usd: float) -> list[dict]:
    """Rank pools by execution quality for a given trade size.

    Factors:
    1. Sufficient TVL (trade size < 2% of TVL for acceptable slippage)
    2. Active volume (recent trades confirm the pool is live)
    3. Lowest fee tier (when liquidity is sufficient)
    4. Pool type efficiency (concentrated > constant product for same TVL)
    5. Pool health score (age, LP count, stability)
    """
    for pool in pools:
        size_ratio = trade_size_usd / max(pool["tvl_usd"], 1)
        pool["estimated_slippage"] = size_ratio * 100  # Rough % estimate

        # Prefer pools where trade is < 2% of TVL
        pool["size_ok"] = size_ratio < 0.02

        # Concentrated liquidity is more efficient
        efficiency_mult = 1.0
        if pool["pool_type"] in ("clmm", "whirlpool", "dlmm"):
            efficiency_mult = 0.3  # ~3x less slippage per TVL dollar

        pool["adjusted_slippage"] = pool["estimated_slippage"] * efficiency_mult
        pool["execution_score"] = (
            (1.0 / max(pool["adjusted_slippage"], 0.001)) * 0.5
            + pool.get("health_score", 50) * 0.3
            + (1.0 / max(pool["fee_rate"], 0.0001)) * 0.2
        )

    return sorted(pools, key=lambda p: p["execution_score"], reverse=True)
```

---

## 7. Program IDs Quick Reference

```python
PROGRAM_IDS = {
    "raydium_v4": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "raydium_clmm": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "orca_whirlpool": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "meteora_dlmm": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "meteora_dynamic": "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",
    "pumpswap": "PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP",
    "pumpfun_bonding": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
}
```

---

## 8. Integration Points

### With `liquidity-analysis`
Use pool analysis to feed liquidity depth assessment. Pool type determines which liquidity model applies (constant product vs concentrated vs bin-based).

### With `lp-math`
Pool type determines which math formulas apply. Raydium V4 uses `xy = k`, CLMM/Whirlpool use tick-based math, DLMM uses bin math. See `lp-math` for full derivations.

### With `slippage-modeling`
Best pool selection directly feeds slippage estimation. Concentrated liquidity pools have different slippage curves than constant-product pools.

### With `jupiter-api`
Jupiter aggregates across all pool types automatically. Pool analysis helps understand *why* Jupiter routes through specific pools and validate route quality.

---

## 9. Workflow Example

```python
import httpx

# Step 1: Fetch all pools for a token from DexScreener
async def analyze_token_pools(token_mint: str) -> dict:
    url = f"https://api.dexscreener.com/tokens/v1/solana/{token_mint}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        pools = resp.json()

    results = []
    for pool in pools:
        dex = pool.get("dexId", "unknown")
        pool_info = {
            "dex": dex,
            "pool_address": pool.get("pairAddress"),
            "tvl_usd": pool.get("liquidity", {}).get("usd", 0),
            "volume_24h": pool.get("volume", {}).get("h24", 0),
            "age_hours": pool.get("pairCreatedAt", 0),
            "fee_rate": estimate_fee_rate(dex),
            "pool_type": classify_pool_type(dex),
        }
        pool_info["volume_efficiency"] = (
            pool_info["volume_24h"] / max(pool_info["tvl_usd"], 1)
        )
        results.append(pool_info)

    return {"token": token_mint, "pool_count": len(results), "pools": results}
```

---

## Files

### References
- `references/pool_mechanics.md` — Detailed mechanics for each pool type with program IDs and formulas
- `references/pool_analysis_guide.md` — Pool health metrics, red flags, volume efficiency, and best pool selection

### Scripts
- `scripts/analyze_pools.py` — Fetch and analyze all pools for a token, rank by execution quality
- `scripts/pool_monitor.py` — Monitor pool metrics over time, detect liquidity events

---

*This skill provides analysis tools and information for evaluating DEX pool characteristics. It does not provide financial advice or trading recommendations.*
