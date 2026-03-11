# Supply Analysis Reference

Comprehensive guide to tracking circulating supply, modeling inflation, analyzing unlock schedules, and evaluating burn mechanisms.

## Circulating Supply Tracking

### Data Sources

**CoinGecko API (free tier)**:
```python
import httpx

resp = httpx.get(
    "https://api.coingecko.com/api/v3/coins/solana",
    params={"localization": "false", "tickers": "false",
            "community_data": "false", "developer_data": "false"}
)
data = resp.json()
circulating = data["market_data"]["circulating_supply"]
total = data["market_data"]["total_supply"]
max_supply = data["market_data"]["max_supply"]  # None if unlimited
```

**On-chain calculation** (Solana SPL tokens):
```
circulating = total_minted - burned - locked_in_vesting - treasury_held - staked_locked
```

Common locked account types:
- Team vesting contracts (PDA accounts with time-lock)
- DAO treasury multisigs
- Staking contracts (may or may not count as circulating)
- Burn address (`1111111111111111111111111111111111`)

### Supply Classification

| Category | Counts as Circulating? | Notes |
|----------|----------------------|-------|
| Trading on DEX/CEX | Yes | Active market supply |
| In user wallets | Yes | Potentially tradeable |
| Staked (liquid staking) | Yes | Can be unstaked and sold |
| Staked (locked period) | Depends | Locked for fixed term |
| Team vesting (locked) | No | Cannot be sold yet |
| Treasury (DAO-controlled) | Depends | Requires governance vote |
| Burned | No | Permanently removed |

## Inflation Modeling

### Emission Sources

1. **Block rewards / Staking rewards**: Continuous issuance to validators/stakers
2. **Liquidity mining**: Token incentives for LPs (often largest source)
3. **Ecosystem grants**: Foundation distributing to builders
4. **Vesting unlocks**: Scheduled release of locked tokens

### Calculating Current Inflation Rate

```python
def annual_inflation_rate(
    daily_staking_rewards: float,
    daily_lm_emissions: float,
    monthly_vesting_unlocks: float,
    annual_grants: float,
    circulating_supply: float
) -> float:
    """Calculate annualized inflation rate as a percentage.

    Args:
        daily_staking_rewards: Tokens issued as staking rewards per day.
        daily_lm_emissions: Tokens emitted for liquidity mining per day.
        monthly_vesting_unlocks: Tokens unlocking from vesting per month.
        annual_grants: Tokens distributed as ecosystem grants per year.
        circulating_supply: Current circulating supply.

    Returns:
        Annualized inflation rate as percentage.
    """
    annual_new = (
        daily_staking_rewards * 365
        + daily_lm_emissions * 365
        + monthly_vesting_unlocks * 12
        + annual_grants
    )
    return (annual_new / circulating_supply) * 100
```

### Inflation Impact Tiers

| Annual Inflation | Impact | Examples |
|-----------------|--------|----------|
| 0-2% | Minimal | Bitcoin (post-2024 halving) |
| 2-5% | Low | Mature L1s, established protocols |
| 5-15% | Moderate | Growing protocols with LM programs |
| 15-30% | High | Early-stage with aggressive emissions |
| >30% | Severe | Yield farms, Ponzi-adjacent |

### Projecting Supply Over Time

```python
def project_supply(
    current_circulating: float,
    total_supply: float,
    monthly_emissions: float,
    monthly_burns: float,
    vesting_schedule: list[float],  # monthly unlock amounts, 12 entries
    months: int = 12
) -> list[dict]:
    """Project circulating supply month by month.

    Args:
        current_circulating: Starting circulating supply.
        total_supply: Maximum total supply cap.
        monthly_emissions: New tokens from emissions per month.
        monthly_burns: Tokens burned per month.
        vesting_schedule: List of monthly vesting unlock amounts.
        months: Number of months to project.

    Returns:
        List of monthly projections with supply and inflation data.
    """
    projections = []
    circ = current_circulating

    for m in range(months):
        vest = vesting_schedule[m] if m < len(vesting_schedule) else 0
        new_tokens = monthly_emissions + vest
        net_new = new_tokens - monthly_burns
        circ = min(circ + net_new, total_supply)
        monthly_rate = net_new / (circ - net_new) * 100 if circ > net_new else 0

        projections.append({
            "month": m + 1,
            "circulating": circ,
            "circulating_pct": circ / total_supply * 100,
            "monthly_inflation_pct": monthly_rate,
            "net_new_tokens": net_new,
        })
    return projections
```

## Unlock Schedule Analysis

### Unlock Types and Impact

**Cliff unlocks** (one-time large release):
- Typically 10-25% of allocation at cliff expiration
- Often the highest-impact event
- Price impact: correlates with unlock_amount / daily_volume ratio

**Linear vesting** (continuous drip):
- Steady daily/monthly release after cliff
- Creates consistent but manageable sell pressure
- Impact spread over time

**Stepped unlocks** (periodic releases):
- Quarterly or monthly batch releases
- Each step is a mini-cliff event
- Plan for each step individually

### Estimating Price Impact

```python
def estimate_unlock_impact(
    unlock_tokens: float,
    token_price: float,
    avg_daily_volume_usd: float,
    sell_assumption: float = 0.30
) -> dict:
    """Estimate the price impact of a token unlock event.

    Args:
        unlock_tokens: Number of tokens being unlocked.
        token_price: Current token price in USD.
        avg_daily_volume_usd: Average daily trading volume in USD.
        sell_assumption: Fraction of unlocked tokens expected to be sold.

    Returns:
        Impact assessment with severity rating.
    """
    unlock_value = unlock_tokens * token_price
    expected_sell = unlock_value * sell_assumption
    days_to_absorb = expected_sell / avg_daily_volume_usd if avg_daily_volume_usd > 0 else float("inf")

    if days_to_absorb < 0.5:
        severity = "Minor"
        est_drawdown = "0-2%"
    elif days_to_absorb < 2:
        severity = "Moderate"
        est_drawdown = "2-5%"
    elif days_to_absorb < 5:
        severity = "Significant"
        est_drawdown = "5-15%"
    else:
        severity = "Severe"
        est_drawdown = "15-30%+"

    return {
        "unlock_value_usd": unlock_value,
        "expected_sell_usd": expected_sell,
        "days_to_absorb": round(days_to_absorb, 2),
        "severity": severity,
        "estimated_drawdown": est_drawdown,
    }
```

### Historical Unlock Behavior

Empirical observations from major token unlocks:
- **Team/founder tokens**: ~30-50% sold within 30 days of unlock
- **VC/investor tokens**: ~40-70% sold within 30 days (profit-taking)
- **Ecosystem/community**: ~10-20% sold (often redistributed, not dumped)
- **Staking unlocks**: ~5-15% sold (most restake)

## Burn Mechanisms

### Types of Burns

| Mechanism | Predictability | Examples |
|-----------|---------------|----------|
| Fee burn (per-tx) | High (scales with usage) | Ethereum EIP-1559, Solana partial burns |
| Buyback & burn | Medium (depends on revenue) | BNB quarterly burns, MKR surplus auctions |
| Manual/scheduled burn | High (announced schedule) | Periodic planned burns |
| Deflationary tax | High (on every transfer) | Reflection tokens (often unsustainable) |

### Net Inflation Calculation

```python
def net_inflation(
    annual_emissions: float,
    annual_burns: float,
    circulating_supply: float
) -> dict:
    """Calculate net inflation accounting for burns.

    Args:
        annual_emissions: Total new tokens emitted per year.
        annual_burns: Total tokens burned per year.
        circulating_supply: Current circulating supply.

    Returns:
        Net inflation metrics.
    """
    net = annual_emissions - annual_burns
    rate = (net / circulating_supply) * 100
    return {
        "gross_inflation_pct": (annual_emissions / circulating_supply) * 100,
        "burn_rate_pct": (annual_burns / circulating_supply) * 100,
        "net_inflation_pct": rate,
        "is_deflationary": net < 0,
        "years_to_double": 72 / rate if rate > 0 else None,  # Rule of 72
    }
```

## Worked Example: Analyzing SOL Supply Dynamics

**Solana (SOL) as of early 2025:**
- Total supply: ~590M SOL
- Circulating supply: ~430M SOL
- Circulating %: ~73%
- FDV/MCap ratio: ~1.37 (low dilution risk)
- Staking rewards: ~5.5% APY (inflationary but offset by 50% fee burn)
- Annual inflation: ~5% gross, ~4.5% net (after fee burns)
- No vesting events remaining (all early vesting completed)

**Assessment:**
- Low dilution risk (FDV/MCap near 1)
- Moderate net inflation (~4.5%/year)
- Fee burns increasing with network usage
- Path to net deflation if transaction volume grows significantly
