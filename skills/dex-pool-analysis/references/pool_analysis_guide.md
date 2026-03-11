# Pool Analysis Guide — Health Metrics, Red Flags & Best Pool Selection

Practical guide for evaluating DEX pool quality, detecting risks, and selecting optimal execution venues.

---

## Pool Health Metrics

### TVL (Total Value Locked)

Minimum TVL thresholds by trade size:

| Trade Size | Minimum TVL | Rationale |
|-----------|-------------|-----------|
| < $100 | $5,000 | < 2% impact |
| $100–$1K | $50,000 | Acceptable slippage |
| $1K–$10K | $250,000 | Professional execution |
| $10K–$100K | $1,000,000 | Institutional quality |
| > $100K | $5,000,000 | Deep liquidity required |

For concentrated liquidity pools, the relevant metric is **liquidity at the current price**, not total TVL. A $100K CLMM pool concentrated in a tight range can handle larger trades than a $500K constant-product pool.

### Volume/TVL Ratio (Volume Efficiency)

```python
volume_efficiency = volume_24h / tvl
```

| Ratio | Classification | Interpretation |
|-------|---------------|----------------|
| > 10.0 | Extreme | Almost certainly wash trading or bot loops |
| 5.0–10.0 | Very high | Suspicious — verify with tx analysis |
| 1.0–5.0 | High | Active, healthy pool |
| 0.3–1.0 | Moderate | Normal for mid-cap tokens |
| 0.05–0.3 | Low | Light trading, may have wide spreads |
| < 0.05 | Very low | Stale pool — check if still active |

### Fee APR Estimate

```python
# For constant-product pools
fee_apr = (volume_24h * fee_rate * 365) / tvl * 100

# For concentrated liquidity (position-specific)
fee_apr = (volume_24h * fee_rate * 365) / position_value * concentration_factor * 100
```

Note: Fee APR does not account for impermanent loss. Net LP return = Fee APR - IL.

### Pool Age

```python
pool_age_hours = (current_time - pool_created_at) / 3600
```

| Age | Risk Level | Notes |
|-----|-----------|-------|
| < 1 hour | Very high | Sniper bots active, volatile |
| 1–6 hours | High | Initial price discovery ongoing |
| 6–24 hours | Elevated | Settling but still risky |
| 1–7 days | Moderate | Established but young |
| > 7 days | Lower | Track record available |
| > 30 days | Base | Enough history for analysis |

### LP Count

Number of distinct liquidity providers. Higher LP count indicates more distributed (safer) liquidity.

| LP Count | Risk |
|----------|------|
| 1 | Critical — single entity controls all liquidity |
| 2–5 | High — few LPs, easy to rug |
| 5–20 | Moderate — reasonable distribution |
| 20–100 | Low — well distributed |
| > 100 | Very low — organic, mature pool |

---

## Red Flags Checklist

### Critical (Do Not Trade)

1. **Single LP with > 90% of liquidity**: Creator can rug by removing liquidity
2. **Pool age < 5 minutes with > $50K TVL**: Likely still in sniper phase
3. **TVL dropped > 50% in last hour**: Active liquidity removal in progress
4. **Zero volume for 24+ hours on a token with market cap > $100K**: Possible frozen/broken pool

### Warning (Proceed with Caution)

5. **V/TVL > 10**: Probable wash trading — real liquidity may be much lower
6. **Pool age < 24 hours**: Limited price history, higher manipulation risk
7. **TVL < $10,000**: High slippage even on small trades
8. **Only one pool exists**: No alternative venue if pool is compromised
9. **LP tokens not burned/locked**: Creator can remove liquidity at any time

### Informational

10. **Multiple pools on different DEXes**: Normal — compare for best execution
11. **V/TVL < 0.1**: Low activity but not necessarily dangerous
12. **Fee tier mismatch** (e.g., 0.01% fee on a meme token): Pool may not attract LPs

---

## Pool Creation Patterns

### PumpFun Graduation Flow

```
Bonding Curve Phase → ~$69K Market Cap → Migration → AMM Pool
```

**Timeline analysis**:
1. **T=0**: Token deploys on PumpFun bonding curve
2. **T=minutes to hours**: Trading on bonding curve (no traditional LP)
3. **T=graduation**: Market cap hits ~$69K, migration triggered
4. **T=graduation+seconds**: Pool created on Raydium V4 or PumpSwap
5. **T=graduation+minutes**: Sniper bots front-run organic traders
6. **T=graduation+1h**: Initial volatility settling

**Key checks after graduation**:
- Was the migration to Raydium V4 or PumpSwap?
- Is initial LP burned? (Check burn transaction)
- How many unique wallets traded in first hour?
- Did creator wallets sell in first 10 minutes?

### Organic Pool Creation

Non-PumpFun tokens may have pools created manually on any DEX:
- Check who created the pool (team wallet vs random)
- Verify initial liquidity amount is reasonable
- Look for simultaneous pool creation on multiple DEXes (professional launch)

---

## Best Pool Selection Algorithm

When a token has multiple pools across DEXes, use this ranking process:

### Step 1: Filter by Minimum Requirements

```python
def passes_minimum(pool: dict, trade_size_usd: float) -> bool:
    """Check if pool meets minimum requirements for execution."""
    min_tvl = trade_size_usd * 50  # Trade must be < 2% of TVL
    return (
        pool["tvl_usd"] >= min_tvl
        and pool["volume_24h"] > 0  # Must have recent activity
        and pool["pool_age_hours"] > 1  # Not brand new
    )
```

### Step 2: Estimate Execution Cost

```python
def estimate_execution_cost(pool: dict, trade_size_usd: float) -> float:
    """Estimate total cost: fee + slippage."""
    fee_cost = trade_size_usd * pool["fee_rate"]

    # Slippage depends on pool type
    if pool["pool_type"] in ("clmm", "whirlpool", "dlmm"):
        # Concentrated liquidity — lower slippage per TVL
        slippage_pct = (trade_size_usd / pool["tvl_usd"]) * 0.3
    else:
        # Constant product — standard slippage
        slippage_pct = trade_size_usd / pool["tvl_usd"]

    slippage_cost = trade_size_usd * slippage_pct
    return fee_cost + slippage_cost
```

### Step 3: Score and Rank

```python
def rank_pools(pools: list[dict], trade_size_usd: float) -> list[dict]:
    """Rank pools by total execution quality."""
    valid = [p for p in pools if passes_minimum(p, trade_size_usd)]

    for pool in valid:
        cost = estimate_execution_cost(pool, trade_size_usd)
        health = compute_health_score(pool)

        # Lower cost is better (invert for scoring)
        pool["cost_score"] = 1.0 / max(cost, 0.01)
        pool["health_score"] = health
        pool["total_score"] = pool["cost_score"] * 0.6 + health * 0.4

    return sorted(valid, key=lambda p: p["total_score"], reverse=True)
```

### Step 4: Verify Route

For the top-ranked pool, verify:
- Pool has had a trade in the last 30 minutes (still active)
- Current price in pool matches other pools within 2% (no stale pricing)
- Sufficient balance in the pool for the quote token you want to receive

---

## Practical Workflow: Token Pool Analysis

```python
# 1. Fetch all pools for a token
pools = fetch_pools_from_dexscreener(token_mint)

# 2. Classify each pool
for pool in pools:
    pool["pool_type"] = classify_by_dex(pool["dex_id"])
    pool["health"] = compute_health_score(pool)
    pool["flags"] = check_red_flags(pool)

# 3. Filter out critical-flag pools
safe_pools = [p for p in pools if not p["flags"]["critical"]]

# 4. Rank for execution
ranked = rank_pools(safe_pools, trade_size_usd=500)

# 5. Select best pool
best = ranked[0] if ranked else None
```

---

*This guide provides analytical frameworks for pool evaluation. It does not constitute financial advice or trading recommendations.*
