---
name: token-economics
description: Token supply dynamics, vesting analysis, inflation modeling, and valuation frameworks for crypto tokens
---

# Token Economics

Tokenomics — the study of token supply dynamics, distribution, and value accrual — is one of the most important factors in crypto asset analysis. Supply changes directly affect price: new tokens entering circulation create selling pressure, while burns and locks reduce it. Understanding these dynamics lets you estimate dilution risk, identify overvalued or undervalued tokens, and anticipate price-moving unlock events.

## Why Tokenomics Matters

Price is a function of demand **and** supply. In crypto, supply is programmable and constantly changing:

- A token inflating at 50%/year needs 50% demand growth just to maintain price
- A large unlock releasing 10% of circulating supply in one day often causes 5-20% drawdowns
- Tokens with >80% of supply locked have extreme dilution risk ahead
- Protocols that burn fees can become net deflationary, creating structural price support

## Key Supply Concepts

### Total Supply vs Circulating Supply

```
total_supply      = maximum tokens that will ever exist (or current total minted)
circulating_supply = tokens currently available for trading
locked_supply     = total_supply - circulating_supply
circulating_pct   = circulating_supply / total_supply * 100
```

### Market Cap vs Fully Diluted Valuation

```
market_cap = price * circulating_supply
fdv        = price * total_supply
fdv_mcap_ratio = fdv / market_cap
```

The **FDV/MCap ratio** measures future dilution risk:

| FDV/MCap | Dilution Risk | Interpretation |
|----------|---------------|----------------|
| 1.0-1.5  | Low           | Most supply already circulating |
| 1.5-3.0  | Moderate      | Significant supply still locked |
| 3.0-5.0  | High          | Majority of supply not yet released |
| >5.0     | Very High     | Token will face massive dilution |

### Net Inflation Rate

```python
annual_new_tokens = emissions + vesting_unlocks + rewards
annual_burned     = fee_burns + buyback_burns
net_new_tokens    = annual_new_tokens - annual_burned
net_inflation_rate = net_new_tokens / circulating_supply * 100  # percent per year
```

## Supply Dynamics

### Inflationary Pressure (tokens entering circulation)

- **Emissions**: Block rewards, liquidity mining, staking rewards
- **Vesting unlocks**: Team, investor, and advisor tokens unlocking on schedule
- **Unlock events**: Large one-time releases (cliff expirations)
- **Treasury spending**: DAO or foundation distributing tokens

### Deflationary Pressure (tokens leaving circulation)

- **Fee burns**: Protocol burns a portion of transaction fees (like EIP-1559)
- **Buyback and burn**: Protocol uses revenue to buy and permanently destroy tokens
- **Staking locks**: Tokens locked in staking (temporarily removed from circulation)
- **Lost tokens**: Permanently inaccessible tokens (lost keys, burn addresses)

### Selling Pressure Estimation

```python
daily_emissions_usd = daily_new_tokens * token_price
percent_sold = 0.50  # assume 50% of new tokens are sold (conservative)
daily_sell_pressure = daily_emissions_usd * percent_sold
sell_pressure_ratio = daily_sell_pressure / daily_volume
# > 0.05 (5%) = significant selling pressure
# > 0.10 (10%) = heavy selling pressure
```

## Vesting and Unlock Schedules

### Key Concepts

- **Cliff**: Period before any tokens unlock (typically 6-12 months)
- **Linear vesting**: Constant rate of unlock after cliff (monthly or daily)
- **Stepped vesting**: Periodic unlocks at set intervals (quarterly)
- **TGE unlock**: Percentage released at Token Generation Event

### Analyzing Unlock Impact

```python
unlock_amount_tokens = 10_000_000
avg_daily_volume_tokens = 5_000_000
unlock_volume_ratio = unlock_amount_tokens / avg_daily_volume_tokens

# Impact assessment:
# < 1x daily volume: minor impact
# 1-5x daily volume: moderate impact, expect 2-5% drawdown
# 5-10x daily volume: major impact, expect 5-15% drawdown
# > 10x daily volume: severe impact, expect 10-30% drawdown
```

### Tracking Sources

- **CoinGecko / CoinMarketCap**: Basic supply data
- **Token Terminal**: Revenue and valuation metrics
- **Token Unlocks (token.unlocks.app)**: Detailed unlock schedules
- **Project documentation**: Whitepapers, tokenomics pages
- **On-chain**: Vesting contract state, treasury balances

## Token Distribution Analysis

### Typical Allocation Ranges

| Category | Typical Range | Red Flag |
|----------|---------------|----------|
| Team/Founders | 15-25% | >30% |
| Investors (Seed+Series) | 10-30% | >40% |
| Community/Ecosystem | 20-40% | <15% |
| Treasury/DAO | 10-20% | <5% |
| Public Sale | 5-20% | <2% |
| Advisors | 2-5% | >10% |

### Distribution Red Flags

- **>50% insider allocation** (team + investors): Insiders control price
- **Short vesting** (<1 year): Quick dump risk
- **No cliff**: Immediate selling from day one
- **Large single wallets**: Concentration risk (use `token-holder-analysis` skill)
- **Unlabeled large allocations**: Hidden insider holdings

### Distribution Quality Score

```python
def distribution_score(team_pct: float, investor_pct: float,
                       community_pct: float, cliff_months: int,
                       vesting_months: int) -> str:
    """Rate token distribution quality."""
    score = 0
    insider_pct = team_pct + investor_pct

    if insider_pct < 30: score += 3
    elif insider_pct < 50: score += 1

    if community_pct > 30: score += 2
    elif community_pct > 20: score += 1

    if cliff_months >= 12: score += 2
    elif cliff_months >= 6: score += 1

    if vesting_months >= 36: score += 2
    elif vesting_months >= 24: score += 1

    if score >= 8: return "Excellent"
    if score >= 6: return "Good"
    if score >= 4: return "Moderate"
    return "Poor"
```

## Valuation Frameworks

### Revenue-Based Metrics

```python
# Price-to-Earnings (for fee-generating protocols)
pe_ratio = fdv / annualized_net_revenue

# Price-to-Sales
ps_ratio = fdv / annualized_total_volume

# Price-to-Fees
pf_ratio = fdv / annualized_protocol_fees

# Revenue Multiple (adjusted for token value accrual)
rev_multiple = fdv / (annualized_fees * fee_share_to_token_holders)
```

**Typical ranges** (crypto, highly variable):
- P/E: 10x-100x+ (DeFi protocols)
- P/S: 0.5x-50x
- P/F: 20x-500x

### Network Value Metrics

```python
# Network Value to Transactions (NVT)
nvt = market_cap / daily_transaction_volume_usd
# High NVT (>100): potentially overvalued or store-of-value
# Low NVT (<20): potentially undervalued or high activity

# Market Value to Realized Value (MVRV)
# realized_value = sum of each token at its last-moved price
mvrv = market_cap / realized_value
# MVRV > 3.0: historically overvalued zone
# MVRV < 1.0: historically undervalued zone
```

### Comparable Analysis

```python
def comparable_analysis(target: dict, peers: list[dict]) -> dict:
    """Compare target token metrics against peer group.

    Each dict has: name, fdv, revenue, tvl, users
    Returns premium/discount percentages.
    """
    peer_fdv_rev = [p["fdv"] / p["revenue"] for p in peers if p["revenue"] > 0]
    peer_fdv_tvl = [p["fdv"] / p["tvl"] for p in peers if p["tvl"] > 0]

    avg_fdv_rev = sum(peer_fdv_rev) / len(peer_fdv_rev) if peer_fdv_rev else 0
    avg_fdv_tvl = sum(peer_fdv_tvl) / len(peer_fdv_tvl) if peer_fdv_tvl else 0

    target_fdv_rev = target["fdv"] / target["revenue"] if target["revenue"] > 0 else 0
    target_fdv_tvl = target["fdv"] / target["tvl"] if target["tvl"] > 0 else 0

    return {
        "fdv_rev_premium": (target_fdv_rev / avg_fdv_rev - 1) * 100 if avg_fdv_rev else None,
        "fdv_tvl_premium": (target_fdv_tvl / avg_fdv_tvl - 1) * 100 if avg_fdv_tvl else None,
    }
```

### Token Value Accrual Mechanisms

| Mechanism | Description | Valuation Impact |
|-----------|-------------|-----------------|
| Fee sharing | Holders receive protocol revenue | Direct cash flow, use DCF |
| Governance | Voting rights on protocol | Hard to value, often overpriced |
| Utility | Required for protocol use | Demand scales with usage |
| Buyback & burn | Protocol buys and burns | Reduces supply, structural bid |
| Staking rewards | Yield from staking | Inflationary if from emissions |
| veToken model | Lock for boosted rewards + governance | Reduces circulating supply |

## PumpFun Token Economics

PumpFun tokens on Solana have simplified tokenomics:

- **Fixed supply**: 1,000,000,000 tokens (1 billion)
- **No vesting**: All tokens available immediately at launch
- **No team allocation**: 100% available on bonding curve
- **Bonding curve pricing**: Price determined by curve math, not supply changes
- **Post-graduation**: After bonding curve completes, supply is fully liquid on Raydium
- **No inflation**: No emissions, no staking rewards, no additional minting

Analysis focus for PumpFun tokens shifts from supply dynamics to:
- Holder concentration (use `token-holder-analysis`)
- Volume sustainability
- Liquidity depth (use `liquidity-analysis`)
- Dev wallet behavior

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `defillama-api` | Fetch TVL, revenue, fees for valuation metrics |
| `token-holder-analysis` | Analyze holder concentration and whale behavior |
| `coingecko-api` | Fetch supply data, market cap, FDV |
| `liquidity-analysis` | Assess trading liquidity relative to supply |
| `risk-management` | Supply dilution as risk factor |
| `position-sizing` | Adjust size for dilution risk |

## Files

### References
- `references/supply_analysis.md` — Circulating supply tracking, inflation modeling, unlock analysis, burn mechanics
- `references/valuation_frameworks.md` — Revenue-based valuation, NVT, MVRV, comparable analysis, value accrual

### Scripts
- `scripts/tokenomics_analyzer.py` — Fetch and analyze token supply metrics from CoinGecko, calculate dilution risk and basic valuations
- `scripts/supply_modeler.py` — Project token supply over 12 months given emission and burn parameters, scenario analysis
