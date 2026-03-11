# Valuation Frameworks Reference

Comprehensive guide to revenue-based valuation, network value metrics, comparable analysis, and token value accrual assessment for crypto assets.

## Revenue-Based Valuation

### Price-to-Earnings (P/E)

```
P/E = FDV / annualized_net_revenue
```

- **Net revenue** = protocol fees retained (not distributed to LPs or users)
- Most directly comparable to traditional P/E
- Only applicable to fee-generating protocols

**Crypto P/E ranges** (as of 2025, highly variable):

| Range | Interpretation | Typical Protocols |
|-------|---------------|-------------------|
| <10x | Potentially undervalued or declining | Legacy protocols losing share |
| 10-30x | Reasonable for mature protocols | Established DEXs, lending |
| 30-100x | Growth premium | Fast-growing protocols |
| 100-500x | High growth expectations | New category leaders |
| >500x | Speculative or minimal revenue | Most tokens |

### Price-to-Sales (P/S)

```
P/S = FDV / annualized_total_volume
```

- Uses total volume, not just protocol revenue
- Better for comparing protocols with different fee structures
- Lower P/S suggests better value per unit of activity

### Price-to-Fees (P/F)

```
P/F = FDV / annualized_total_fees
```

- Total fees generated (including LP fees, not just protocol take)
- Measures total economic activity, not just protocol capture
- Useful for comparing DEXs with different fee splits

### Revenue Quality Assessment

Not all revenue is equal:

| Revenue Type | Quality | Sustainability |
|-------------|---------|----------------|
| Trading fees (organic) | High | Scales with market activity |
| Lending interest | High | Consistent in all markets |
| Liquidation fees | Medium | Spikes in volatility, zero otherwise |
| LM-incentivized volume | Low | Disappears when incentives end |
| MEV revenue | Medium | Structural but variable |
| Bridge fees | Medium | Dependent on cross-chain activity |

```python
def revenue_quality_score(
    organic_fees_pct: float,
    incentivized_fees_pct: float,
    one_time_pct: float,
    months_of_data: int
) -> dict:
    """Score revenue quality for valuation purposes.

    Args:
        organic_fees_pct: Percentage of fees from organic activity.
        incentivized_fees_pct: Percentage from LM-incentivized activity.
        one_time_pct: Percentage from one-time events.
        months_of_data: How many months of revenue history.

    Returns:
        Quality assessment with adjustment factor.
    """
    base = organic_fees_pct * 1.0 + incentivized_fees_pct * 0.3 + one_time_pct * 0.1
    history_factor = min(months_of_data / 12, 1.0)  # penalize short history
    score = base * history_factor

    if score > 70:
        quality = "High"
        valuation_discount = 0  # no discount needed
    elif score > 40:
        quality = "Medium"
        valuation_discount = 20  # apply 20% discount to revenue multiple
    else:
        quality = "Low"
        valuation_discount = 50  # apply 50% discount

    return {
        "quality": quality,
        "score": round(score, 1),
        "valuation_discount_pct": valuation_discount,
    }
```

## Network Value to Transactions (NVT)

### Calculation

```
NVT = market_cap / daily_on_chain_transaction_volume_usd
```

NVT is the crypto equivalent of P/E for networks without traditional revenue. It measures how much the market values each dollar of on-chain activity.

### Interpretation

| NVT Range | Signal | Context |
|-----------|--------|---------|
| <20 | Potentially undervalued | High activity relative to valuation |
| 20-50 | Fair value zone | Balanced activity and valuation |
| 50-100 | Potentially overvalued | Low activity relative to valuation |
| >100 | Overvalued or store-of-value | May be justified for BTC-like assets |

### NVT Signal (smoothed)

```python
def nvt_signal(
    market_cap: float,
    daily_volumes: list[float],
    window: int = 90
) -> float:
    """Calculate smoothed NVT Signal using moving average of volume.

    Args:
        market_cap: Current market capitalization.
        daily_volumes: List of daily on-chain volumes (most recent last).
        window: Moving average window in days.

    Returns:
        NVT Signal value.
    """
    if len(daily_volumes) < window:
        window = len(daily_volumes)
    avg_volume = sum(daily_volumes[-window:]) / window
    return market_cap / avg_volume if avg_volume > 0 else float("inf")
```

NVT Signal smooths out daily volume noise, giving a more reliable valuation indicator than raw NVT.

## Market Value to Realized Value (MVRV)

### Concept

**Realized value** sums each token at the price it last moved on-chain, representing the aggregate cost basis of all holders.

```
MVRV = market_cap / realized_value
```

### Interpretation

| MVRV | Zone | Historical Meaning |
|------|------|--------------------|
| <0.8 | Deep undervalue | Aggregate holders at a loss, capitulation |
| 0.8-1.0 | Undervalue | Most holders near breakeven or slightly down |
| 1.0-2.0 | Fair value | Moderate unrealized gains |
| 2.0-3.0 | Overvalue caution | Significant unrealized gains, profit-taking likely |
| >3.0 | Overvalue danger | Historical tops often occur here |

### Limitations

- Only available for UTXO chains (BTC) and some account-based chains
- Not applicable to most DeFi tokens (insufficient on-chain transfer data)
- Realized value can be skewed by exchange movements
- Works best as a macro cycle indicator, not for short-term trading

## Comparable Analysis

### Methodology

1. **Select peer group**: Tokens in the same sector (DEX, lending, L1, L2, etc.)
2. **Gather metrics**: FDV, revenue, TVL, users, volume for each
3. **Calculate ratios**: FDV/Revenue, FDV/TVL, FDV/DAU
4. **Rank**: Where does the target fall vs peers?
5. **Assess premium/discount**: Is it justified by growth, moat, risk?

### Standard Comparison Metrics

```python
def build_comp_table(protocols: list[dict]) -> list[dict]:
    """Build comparable analysis table for a set of protocols.

    Args:
        protocols: List of dicts with keys: name, fdv, revenue, tvl, dau, volume.

    Returns:
        List of dicts with calculated valuation ratios.
    """
    result = []
    for p in protocols:
        row = {"name": p["name"], "fdv": p["fdv"]}
        row["fdv_revenue"] = p["fdv"] / p["revenue"] if p.get("revenue", 0) > 0 else None
        row["fdv_tvl"] = p["fdv"] / p["tvl"] if p.get("tvl", 0) > 0 else None
        row["fdv_dau"] = p["fdv"] / p["dau"] if p.get("dau", 0) > 0 else None
        row["revenue_per_tvl"] = p.get("revenue", 0) / p["tvl"] if p.get("tvl", 0) > 0 else None
        result.append(row)
    return result
```

### Sector-Specific Benchmarks (approximate ranges, 2025)

| Sector | FDV/Revenue | FDV/TVL | Notes |
|--------|-------------|---------|-------|
| DEX | 20-100x | 1-10x | Higher for growing DEXs |
| Lending | 30-150x | 0.5-5x | Stable revenue, lower multiples |
| L1 | 50-500x | 5-50x | Premium for ecosystem size |
| L2 | 100-1000x | 10-100x | Early stage, growth premium |
| Perpetuals | 15-80x | 2-15x | High revenue efficiency |

## Token Value Accrual

### Fee Sharing

Tokens that distribute protocol revenue directly to holders:

```python
def fee_share_yield(
    annualized_fees: float,
    fee_share_pct: float,
    token_fdv: float
) -> float:
    """Calculate implied yield from fee sharing.

    Args:
        annualized_fees: Total protocol fees per year in USD.
        fee_share_pct: Percentage of fees distributed to token holders.
        token_fdv: Fully diluted valuation of the token.

    Returns:
        Implied annual yield as a percentage.
    """
    distributed = annualized_fees * (fee_share_pct / 100)
    return (distributed / token_fdv) * 100
```

### Buyback & Burn Valuation

```python
def buyback_burn_impact(
    annual_burn_usd: float,
    circulating_supply: float,
    token_price: float
) -> dict:
    """Calculate the supply reduction from buyback and burn.

    Args:
        annual_burn_usd: USD value of annual buyback and burn.
        circulating_supply: Current circulating supply.
        token_price: Current token price.

    Returns:
        Annual supply reduction metrics.
    """
    tokens_burned = annual_burn_usd / token_price
    supply_reduction_pct = (tokens_burned / circulating_supply) * 100
    return {
        "tokens_burned_annually": tokens_burned,
        "supply_reduction_pct": supply_reduction_pct,
        "implied_yield_pct": supply_reduction_pct,  # equivalent to dividend yield
    }
```

### veToken Model

Tokens locked for governance + boosted rewards (e.g., CRV -> veCRV):

**Value drivers:**
- Reduces circulating supply (locked for 1-4 years typically)
- Generates yield from fees + bribes
- Governance power over emissions
- Longer lock = more power (incentivizes long-term holding)

**Assessment:**
```python
def ve_token_metrics(total_supply: float, locked_in_ve: float,
                     annual_fees_to_ve: float, annual_bribes: float,
                     ve_token_price: float) -> dict:
    """Calculate veToken model metrics."""
    lock_pct = (locked_in_ve / total_supply) * 100
    ve_value = locked_in_ve * ve_token_price
    total_yield = annual_fees_to_ve + annual_bribes
    yield_pct = (total_yield / ve_value) * 100 if ve_value > 0 else 0
    return {
        "lock_pct": round(lock_pct, 2),
        "ve_yield_pct": round(yield_pct, 2),
        "health": "Strong" if lock_pct > 50 and yield_pct > 5 else "Moderate" if lock_pct > 30 else "Weak",
    }
```

## Summary: Valuation Workflow

1. **Supply**: FDV/MCap ratio, inflation rate, upcoming unlocks
2. **Revenue**: P/E, P/F — is there real, sustainable revenue?
3. **Peers**: Compare ratios to similar protocols
4. **Accrual**: How does the token capture value (fees, burns, utility)?
5. **Risks**: Dilution, insider allocation, revenue sustainability
