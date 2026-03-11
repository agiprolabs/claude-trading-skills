---
name: liquidity-analysis
description: DEX liquidity depth assessment, slippage estimation, and pool composition analysis for Solana tokens
---

# Liquidity Analysis — DEX Depth Assessment for Solana Tokens

Liquidity analysis answers three critical questions before every trade: **Can I get in at a reasonable price?** **Can I get out when I need to?** and **Is this pool safe?** Without it, you risk excessive slippage, failed exits, and rug pulls.

## Why Liquidity Analysis Matters

**Position sizing**: Maximum position size is bounded by available liquidity. A $10K position in a pool with $20K TVL will move the price significantly. Rule of thumb: keep trade size under 2% of pool depth to limit slippage below 1%.

**Execution cost**: Slippage is a direct cost. On a 5 SOL buy, the difference between 0.3% and 3% slippage is real money lost on every entry and exit.

**Rug risk detection**: Thin liquidity, single pools, unlocked LP tokens, and newly created pools are warning signs. Liquidity analysis catches these before you enter.

**Exit planning**: Entry liquidity may differ from exit liquidity. If LP is unlocked and owned by one wallet, it can be pulled at any time.

## Key Concepts

### Total Value Locked (TVL)

Total value of assets deposited in a pool. For a SOL/TOKEN pool with 100 SOL and 1M TOKEN at $0.01 each, TVL = 100 * SOL_price + 1M * $0.01. TVL alone is insufficient — you need depth at the current price range.

### Liquidity Depth

How much can be traded before moving the price X%. In constant-product AMMs, depth is uniform. In concentrated liquidity (CLMM), depth varies by price range — thick near the current price, thin or zero outside active ranges.

### Concentration Factor (CLMM)

Concentrated liquidity pools focus capital in a narrow price range, providing deeper liquidity within that range but nothing outside it. A pool with $50K TVL concentrated in a +/-5% range provides the same depth as a $500K constant-product pool within that range, but zero depth beyond it.

### Slippage Curve

Slippage is not linear. Plotting slippage against trade size produces a curve that's gentle for small trades and steep for large ones. The shape depends on pool type, TVL, and concentration.

### Pool Composition

Who provides liquidity matters. Locked LP tokens cannot be withdrawn (safer). Single-sided liquidity means the pool is imbalanced. Pool age indicates stability — pools older than 7 days with consistent TVL are more reliable.

## Data Sources

Four complementary data sources, from free to comprehensive:

| Source | Auth Required | Best For | Limitations |
|--------|--------------|----------|-------------|
| DexScreener | None | Quick pool lookup, liquidity.usd | No on-chain pool details |
| Jupiter Quote API | None | Empirical slippage at any size | Aggregate across pools |
| Birdeye | API key | Detailed pool data, trade history | Rate limited on free tier |
| On-chain | RPC only | LP lock status, exact reserves | Requires program knowledge |

See `references/data_sources.md` for complete endpoint documentation and usage examples.

## Core Analysis Pipeline

### Step 1: Identify Pools

Fetch all pools for a token. Most Solana tokens have multiple pools across Raydium, Orca, and Meteora.

```python
import httpx

def get_pools(mint: str) -> list[dict]:
    """Fetch all DEX pools for a token from DexScreener."""
    resp = httpx.get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}")
    resp.raise_for_status()
    pairs = resp.json()
    return [p for p in pairs if p.get("liquidity", {}).get("usd", 0) > 0]
```

### Step 2: Measure Depth

For each pool, extract liquidity metrics:

```python
def extract_depth(pool: dict) -> dict:
    """Extract liquidity metrics from a DexScreener pool."""
    return {
        "dex": pool.get("dexId", "unknown"),
        "liquidity_usd": pool.get("liquidity", {}).get("usd", 0),
        "volume_24h": pool.get("volume", {}).get("h24", 0),
        "pool_age_hours": _pool_age_hours(pool.get("pairCreatedAt", 0)),
        "pair_address": pool.get("pairAddress", ""),
    }
```

### Step 3: Estimate Slippage

Use Jupiter quotes at multiple sizes to build an empirical slippage curve. This captures real routing across all pools:

```python
import httpx

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS = 1_000_000_000

async def estimate_slippage(token_mint: str, sol_amounts: list[float]) -> list[dict]:
    """Query Jupiter for slippage at multiple trade sizes.

    Args:
        token_mint: Token mint address to buy.
        sol_amounts: List of SOL amounts to test (e.g., [0.1, 0.5, 1, 5, 10]).

    Returns:
        List of dicts with sol_amount, output_tokens, price_per_token, slippage_bps.
    """
    results = []
    base_price = None
    async with httpx.AsyncClient() as client:
        for sol in sol_amounts:
            lamports = int(sol * LAMPORTS)
            resp = await client.get(
                "https://api.jup.ag/quote/v1",
                params={
                    "inputMint": SOL_MINT,
                    "outputMint": token_mint,
                    "amount": str(lamports),
                    "slippageBps": 5000,
                },
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            out_amount = int(data["outAmount"])
            price = sol / out_amount if out_amount > 0 else 0
            if base_price is None:
                base_price = price
            slippage_bps = int((price - base_price) / base_price * 10000) if base_price > 0 else 0
            results.append({
                "sol_amount": sol,
                "output_tokens": out_amount,
                "price_per_token": price,
                "slippage_bps": max(0, slippage_bps),
            })
    return results
```

### Step 4: Assess Concentration

For CLMM pools (Orca Whirlpool, Raydium CLMM, Meteora DLMM), liquidity may be concentrated in a narrow range. Check if the current price is within the active range and how deep liquidity extends:

```python
def assess_concentration(pools: list[dict]) -> dict:
    """Assess concentration risk from pool data."""
    clmm_pools = [p for p in pools if p.get("dexId") in ("raydium", "orca") and "clmm" in p.get("labels", [])]
    cpmm_pools = [p for p in pools if p not in clmm_pools]

    total_clmm = sum(p.get("liquidity", {}).get("usd", 0) for p in clmm_pools)
    total_cpmm = sum(p.get("liquidity", {}).get("usd", 0) for p in cpmm_pools)
    total = total_clmm + total_cpmm

    return {
        "clmm_ratio": total_clmm / total if total > 0 else 0,
        "cpmm_liquidity": total_cpmm,
        "clmm_liquidity": total_clmm,
        "concentration_risk": "high" if total_clmm / total > 0.8 and total > 0 else "low",
    }
```

### Step 5: Compute Liquidity Score

Composite score from 0 (dangerous) to 100 (deep, safe liquidity):

```python
def compute_liquidity_score(
    total_liquidity_usd: float,
    pool_count: int,
    largest_pool_pct: float,
    oldest_pool_hours: float,
    max_slippage_bps_at_1sol: int,
) -> int:
    """Compute composite liquidity score (0-100).

    Components:
        Depth (40%): log-scaled TVL from $1K (0) to $1M+ (40)
        Diversity (15%): more pools = more resilient
        Concentration (15%): penalty if one pool dominates
        Age (15%): older pools are more reliable
        Slippage (15%): lower slippage = better
    """
    import math
    # Depth: 0-40 points
    depth = min(40, int(40 * math.log10(max(total_liquidity_usd, 1)) / 6))

    # Diversity: 0-15 points
    diversity = min(15, pool_count * 3)

    # Concentration: 0-15 points (penalty for single-pool dominance)
    concentration = int(15 * (1 - largest_pool_pct))

    # Age: 0-15 points (7+ days = full marks)
    age = min(15, int(15 * oldest_pool_hours / 168))

    # Slippage: 0-15 points
    slippage = max(0, 15 - max_slippage_bps_at_1sol // 10)

    return max(0, min(100, depth + diversity + concentration + age + slippage))
```

## Risk Flags

Flag these conditions before entering any position:

| Flag | Condition | Risk Level |
|------|-----------|------------|
| Single Pool | Only 1 DEX pool exists | High |
| Thin Liquidity | Total TVL < $10,000 | Critical |
| New Pool | Pool created < 2 hours ago | High |
| Unlocked LP | LP tokens not burned/locked | Medium |
| Volume Mismatch | Volume >> TVL (wash trading) | Medium |
| Price Deviation | >5% price difference across pools | High |
| Concentrated CLMM | >80% liquidity in CLMM with narrow range | Medium |

```python
def detect_risk_flags(pools: list[dict]) -> list[str]:
    """Detect liquidity risk flags from pool data."""
    flags = []
    if len(pools) < 2:
        flags.append("SINGLE_POOL: Only 1 pool exists — exit may be difficult")

    total_liq = sum(p.get("liquidity", {}).get("usd", 0) for p in pools)
    if total_liq < 10_000:
        flags.append(f"THIN_LIQUIDITY: Total TVL ${total_liq:,.0f} < $10,000")

    for p in pools:
        age_ms = p.get("pairCreatedAt", 0)
        if age_ms > 0:
            import time
            age_hours = (time.time() * 1000 - age_ms) / 3_600_000
            if age_hours < 2:
                flags.append(f"NEW_POOL: {p.get('dexId')} pool is {age_hours:.1f}h old")

    volumes = [p.get("volume", {}).get("h24", 0) for p in pools]
    liqs = [p.get("liquidity", {}).get("usd", 0) for p in pools]
    for v, l, p in zip(volumes, liqs, pools):
        if l > 0 and v / l > 10:
            flags.append(f"VOLUME_MISMATCH: {p.get('dexId')} volume/TVL = {v/l:.1f}x")

    prices = [float(p.get("priceUsd", 0)) for p in pools if float(p.get("priceUsd", 0)) > 0]
    if len(prices) >= 2:
        deviation = (max(prices) - min(prices)) / min(prices)
        if deviation > 0.05:
            flags.append(f"PRICE_DEVIATION: {deviation:.1%} across pools")

    return flags
```

## Position Sizing from Liquidity

Maximum position size should keep slippage under your threshold:

| Trade Type | Max Slippage | Max Position % of TVL |
|------------|-------------|----------------------|
| Scalp | 0.5% (50 bps) | 1% |
| Swing | 2% (200 bps) | 2-5% |
| Position | 5% (500 bps) | 5-10% |

```python
def max_position_from_liquidity(
    total_liquidity_usd: float,
    max_slippage_pct: float = 1.0,
    trade_type: str = "swing",
) -> float:
    """Estimate maximum position size in USD based on liquidity.

    Uses rule-of-thumb: max_position = tvl_fraction * total_liquidity.
    For constant-product AMM, 1% of TVL produces ~2% slippage.

    Args:
        total_liquidity_usd: Total liquidity across all pools.
        max_slippage_pct: Maximum acceptable slippage percentage.
        trade_type: "scalp", "swing", or "position".

    Returns:
        Maximum position size in USD.
    """
    fractions = {"scalp": 0.01, "swing": 0.03, "position": 0.07}
    base_fraction = fractions.get(trade_type, 0.03)
    adjusted = base_fraction * (max_slippage_pct / 2.0)
    return total_liquidity_usd * adjusted
```

## Slippage Estimation

For detailed slippage mathematics including constant-product formulas, CLMM models, and empirical curve fitting, see `references/slippage_curves.md`.

Key formula for constant-product AMM:

```
slippage = Δx / (x + Δx)
```

Where `Δx` is trade size and `x` is pool reserve of the input token. For a 1 SOL trade on a pool with 100 SOL reserve, slippage = 1/101 = 0.99%.

## Pool Types

Solana DEXes use different AMM designs with different liquidity characteristics. See `references/pool_types.md` for comprehensive coverage including:

- **Constant Product** (Raydium V4, Orca Legacy): Uniform liquidity, predictable slippage
- **Concentrated Liquidity** (Raydium CLMM, Orca Whirlpool): Deep at current price, zero outside range
- **Dynamic AMM** (Meteora DLMM): Adaptive fees, bin-based liquidity

## Integration with Other Skills

**token-holder-analysis**: Check LP token holder distribution before entering. If one wallet holds >50% of LP tokens and they are unlocked, exit risk is high.

**position-sizing**: Feed `max_position_from_liquidity()` output into position sizing models as an upper bound.

**slippage-modeling**: Use the empirical slippage curves from this skill as input to execution cost models.

**birdeye-api**: Fetch detailed pool data including trade history and LP events.

**dexscreener-api**: Free pool discovery and basic liquidity metrics.

## Example Workflow

```python
# Full liquidity assessment for a token
import httpx

TOKEN = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK

# 1. Get pools
resp = httpx.get(f"https://api.dexscreener.com/tokens/v1/solana/{TOKEN}")
pools = [p for p in resp.json() if p.get("liquidity", {}).get("usd", 0) > 0]

# 2. Analyze
total_liq = sum(p["liquidity"]["usd"] for p in pools)
largest = max(p["liquidity"]["usd"] for p in pools)
largest_pct = largest / total_liq if total_liq > 0 else 1.0

# 3. Risk flags
flags = detect_risk_flags(pools)

# 4. Score
score = compute_liquidity_score(total_liq, len(pools), largest_pct, 1000, 50)

# 5. Position sizing
max_pos = max_position_from_liquidity(total_liq, max_slippage_pct=1.0, trade_type="swing")

print(f"Total Liquidity: ${total_liq:,.0f}")
print(f"Pools: {len(pools)}")
print(f"Score: {score}/100")
print(f"Max Position (swing, 1% slip): ${max_pos:,.0f}")
for f in flags:
    print(f"  WARNING: {f}")
```

## Files

| File | Description |
|------|-------------|
| `references/slippage_curves.md` | Slippage math for constant-product and CLMM pools, empirical curve fitting |
| `references/pool_types.md` | AMM designs on Solana: constant product, concentrated, dynamic |
| `references/data_sources.md` | API endpoints and on-chain methods for fetching liquidity data |
| `scripts/analyze_liquidity.py` | Full liquidity assessment with scoring and risk flags |
| `scripts/pool_comparison.py` | Compare pools across DEXes for a token |
